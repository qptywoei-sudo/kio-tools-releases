"""Stdlib-only source patch using the app's bundled Python; no private settings."""
from __future__ import annotations
import argparse, ast, contextlib, ctypes, hashlib, json, os, shutil, stat, struct, tempfile, time
from pathlib import Path

PATCH_VERSION = "4.0.1"
APP_VERSION = "4.0.0"
MUTEX_NAME = r"Local\GalaxyCapturePortableSingleInstance"
WINDOW_CLASS = "GalaxyCaptureMain"
EXPECTED_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAz68kBD7C8zjkZ23gZPYJkwMG4rW419Bi4qjC2ke+5a2uu+9QVnQ2abQE5H9eYKPvVri+FNe7Eo/tOZmi0lznR3p7QMcKioF9IDfl8qPkPngAIrdenj+awOf7/TWXN2Ncmu9vgJIVlpDLebZHaykh7UFUOg/yG692vxI54fu4/YWb/eHXFNz1Q9Li/I3S7X+9Ci+sVClbeiygK4sxF0pk9xgUw7ugtzzL3yI4dj9AZGMfDMconfDMOwaiiHl2qaUxipdZktQwfXFesBI6vKDlvqYcSItNGRxsRt+6pDGq8QZhr5GdjIjrbtxurojENQhtUKfh+jUkGL8quFsv4c3ElwIDAQAB"
EXTENSION_FILES = (
    "agent-endpoint.js", "background.js", "capture-core.js", "manifest.json",
    "popup.css", "popup.html", "popup.js",
    "_locales/en/messages.json", "_locales/ja/messages.json",
    "_locales/ko/messages.json", "_locales/vi/messages.json",
    "_locales/zh_CN/messages.json",
)
RELATIVE_FILES = (
    "tools/engine/agent/server.py",
    *("tools/browser-extension/" + name for name in EXTENSION_FILES),
    "tools/source/GalaxyControl-source.zip",
)
BACKUP_RELATIVE = "tools/updates/browser-capture-before-4.0.1"

class UpdateError(Exception):
    pass

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def checked_path(root, relative):
    """Reject linked target components and traversal outside the selected app."""
    if relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
        raise UpdateError("unsafePath")
    target = root.joinpath(*relative.split("/"))
    for component in (target, *target.parents):
        if component == root:
            break
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise UpdateError("linkedTarget")
    if not target.resolve(strict=False).is_relative_to(root):
        raise UpdateError("unsafePath")
    return target

def read_json(path, maximum=256_000):
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise UpdateError("oversizeMetadata")
    return json.loads(data.decode("utf-8"))

def validate_installation(folder):
    root = folder.resolve(strict=True)
    if not root.is_dir():
        raise UpdateError("notInstalled")
    with checked_path(root, "GalaxyControl.exe").open("rb") as stream:
        first = stream.read(64)
        if len(first) != 64 or first[:2] != b"MZ":
            raise UpdateError("notInstalled")
        offset = struct.unpack_from("<I", first, 0x3C)[0]
        if offset < 64 or offset > 1_048_576:
            raise UpdateError("notInstalled")
        stream.seek(offset)
        header = stream.read(96)
    if (len(header) < 96 or header[:4] != b"PE\0\0"
            or struct.unpack_from("<H", header, 4)[0] != 0x8664
            or struct.unpack_from("<H", header, 24)[0] != 0x20B
            or struct.unpack_from("<H", header, 24 + 68)[0] != 2):
        raise UpdateError("notInstalled")
    with checked_path(root, "tools/engine/agent/common.py").open("rb") as stream:
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise UpdateError("unsupportedVersion")
    versions = []
    for node in ast.parse(raw.decode("utf-8-sig")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets):
            versions.append(ast.literal_eval(node.value))
    if versions != [APP_VERSION]:
        raise UpdateError("unsupportedVersion")
    manifest = read_json(checked_path(root, "tools/browser-extension/manifest.json"))
    if manifest.get("manifest_version") != 3 or manifest.get("key") != EXPECTED_KEY:
        raise UpdateError("differentExtension")
    if not checked_path(root, "tools/python/python.exe").is_file():
        raise UpdateError("missingRuntime")
    return root

def _windows_apis():
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    user.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user.FindWindowW.restype = wintypes.HWND
    return kernel, user

def ensure_not_running():
    if os.name != "nt":
        return
    kernel, user = _windows_apis()
    handle = kernel.OpenMutexW(0x00100000, False, MUTEX_NAME)
    if handle:
        kernel.CloseHandle(handle)
        raise UpdateError("appRunning")
    if ctypes.get_last_error() == 5 or user.FindWindowW(WINDOW_CLASS, None):
        raise UpdateError("appRunning")

@contextlib.contextmanager
def update_lock():
    """Hold the existing singleton name so the app cannot launch mid-patch."""
    if os.name != "nt":
        yield
        return
    kernel, user = _windows_apis()
    ensure_not_running()
    ctypes.set_last_error(0)
    handle = kernel.CreateMutexW(None, False, MUTEX_NAME)
    error = ctypes.get_last_error()
    if not handle:
        raise UpdateError("mutexUnavailable")
    try:
        if error == 183 or user.FindWindowW(WINDOW_CLASS, None):
            raise UpdateError("appRunning")
        yield
    finally:
        kernel.CloseHandle(handle)

def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".capture-update-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_stream:
            shutil.copyfileobj(input_stream, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if digest(temporary) != digest(source):
            raise UpdateError("copyMismatch")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".capture-update-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def validate_payload(payload):
    root = payload.resolve(strict=True)
    receipt = read_json(checked_path(root, "update-payload.json"))
    if (receipt.get("version") != PATCH_VERSION or receipt.get("extension_key") != EXPECTED_KEY
            or set(receipt.get("files", {})) != set(RELATIVE_FILES)):
        raise UpdateError("invalidPayload")
    for relative, item in receipt["files"].items():
        path = checked_path(root, relative)
        if path.stat().st_size != item.get("bytes") or digest(path) != item.get("sha256"):
            raise UpdateError("payloadMismatch")
    manifest = read_json(checked_path(root, "tools/browser-extension/manifest.json"))
    if manifest.get("key") != EXPECTED_KEY or manifest.get("version") != PATCH_VERSION:
        raise UpdateError("invalidPayload")
    return root, receipt

def apply_update(folder, payload, replace_copy=atomic_copy):
    root = validate_installation(folder)
    payload_root, receipt = validate_payload(payload)
    with update_lock():
        backup = checked_path(root, BACKUP_RELATIVE)
        backup.mkdir(parents=True, exist_ok=True)
        updates = checked_path(root, "tools/updates")
        transaction = Path(tempfile.mkdtemp(prefix=".browser-capture-transaction-", dir=updates))
        original, replaced, rollback_errors = {}, [], []
        try:
            for relative in RELATIVE_FILES:
                destination = checked_path(root, relative)
                existed = destination.is_file()
                original[relative] = {"present": existed, "sha256": digest(destination) if existed else None}
                if existed:
                    atomic_copy(destination, checked_path(transaction, "prior/" + relative))
                atomic_copy(checked_path(payload_root, relative), checked_path(transaction, "staged/" + relative))
            # Preserve the first pre-update snapshot, including across retries.
            backup_manifest = checked_path(backup, "backup-manifest.json")
            if not backup_manifest.exists():
                for relative, item in original.items():
                    if item["present"]:
                        atomic_copy(checked_path(transaction, "prior/" + relative), checked_path(backup, relative))
                atomic_json(backup_manifest, {"before": PATCH_VERSION, "files": original})
            else:
                first = read_json(backup_manifest)
                if set(first.get("files", {})) != set(RELATIVE_FILES):
                    raise UpdateError("invalidBackup")
                for relative, item in first["files"].items():
                    if item.get("present") and digest(checked_path(backup, relative)) != item.get("sha256"):
                        raise UpdateError("backupMismatch")
            for relative in RELATIVE_FILES:
                destination = checked_path(root, relative)
                item = original[relative]
                if destination.exists() != item["present"] or (item["present"] and digest(destination) != item["sha256"]):
                    raise UpdateError("targetChanged")
                # Track first: even a write-then-raise failure must restore this target.
                replaced.append(relative)
                replace_copy(checked_path(transaction, "staged/" + relative), destination)
            for relative, item in receipt["files"].items():
                if digest(checked_path(root, relative)) != item["sha256"]:
                    raise UpdateError("installedMismatch")
            atomic_json(checked_path(root, "tools/updates/browser-capture-4.0.1.json"),
                        {"version": PATCH_VERSION, "updated_at": time.time(), "files": receipt["files"]})
        except Exception as error:
            for relative in reversed(replaced):
                try:
                    destination = checked_path(root, relative)
                    if original[relative]["present"]:
                        atomic_copy(checked_path(transaction, "prior/" + relative), destination)
                    else:
                        destination.unlink(missing_ok=True)
                except Exception as rollback_error:
                    rollback_errors.append({"file": relative, "error": type(rollback_error).__name__})
            if rollback_errors:
                atomic_json(checked_path(transaction, "rollback-needed.json"), {"files": rollback_errors})
                raise UpdateError("rollbackIncomplete") from error
            raise
        finally:
            if not rollback_errors:
                shutil.rmtree(transaction, ignore_errors=True)
    return {"success": True, "version": PATCH_VERSION, "replaced": len(RELATIVE_FILES), "backup": BACKUP_RELATIVE}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("validate", "apply"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("payload", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.operation == "validate":
            validate_installation(args.folder)
            ensure_not_running()
            result = {"success": True, "version": APP_VERSION}
        else:
            if args.payload is None:
                raise UpdateError("invalidPayload")
            result = apply_update(args.folder, args.payload)
        print(json.dumps(result))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, UpdateError) else type(error).__name__
        print(json.dumps({"success": False, "error": code}))
        return 3 if code == "appRunning" else 2

if __name__ == "__main__":
    raise SystemExit(main())

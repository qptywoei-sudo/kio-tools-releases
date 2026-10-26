"""Read-only GalaxyControl 4.2.1 staged payload/source audit.

This checks packaging and corresponding source, not a physical Windows UI,
installation, login, clipboard interoperability, or screen-capture execution.
It writes only its own receipt outside the staged payload.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import posixpath
import re
import stat
import struct
import subprocess
import sys
import time
import zipfile

BASE = Path(__file__).resolve().parents[2]
TASK = BASE / "work/desktop-single-ui-20261008"
PORTS = [4323, 4324, 4325, 4321]
LANGUAGES = ["ko", "en", "vi", "ja", "zh"]
CATEGORIES = ["files", "image", "pdf", "signature", "capture", "record", "web", "phone", "codes", "media", "organize"]
TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".mjs", ".json", ".html", ".txt", ".swift", ".c", ".cpp", ".h", ".hpp", ".sh", ".ps1", ".bat", ".cmd", ".ini", ".cfg", ".toml", ".yaml", ".yml", ".xml", ".plist", ".pem", ".key", ".nsi", ".rc"}
PRIVATE_NAMES = {"desktop-session.json", "device.json", "settings.json", "pairings.json", "files.json", "credentials", "credentials.json", "service-account.json", "id_rsa", "id_ed25519", "id_ecdsa", "build-private-key.pem"}
AI_PACKAGES = ("onnxruntime", "rembg", "torch", "tensorflow", "transformers")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def safe_member(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return bool(parts) and not name.startswith("/") and "\\" not in name and "\0" not in name and not re.match(r"^[A-Za-z]:", name) and all(part not in (".", "..") for part in parts)


def sensitive_filename(name: str) -> bool:
    basename = PurePosixPath(name).name.lower()
    return basename.startswith(".env") or basename in PRIVATE_NAMES or basename.endswith((".p12", ".pfx"))


def secret_kinds(data: bytes) -> set[str]:
    """Return marker types only. Secret contents must never enter a receipt."""
    kinds = set()
    private_key = rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----\s*[A-Za-z0-9+/=\r\n]{80,}-----END (?:[A-Z ]+ )?PRIVATE KEY-----"
    if re.search(private_key, data):
        kinds.add("PEM private key")
    # Standard service-account JSON uses escaped newlines in private_key.
    # Decode JSON strings rather than copying key text into diagnostics.
    try:
        def inspect_json(value):
            if isinstance(value, str) and re.search(private_key, value.encode()):
                kinds.add("PEM private key")
            elif isinstance(value, dict):
                for nested in value.values():
                    inspect_json(nested)
            elif isinstance(value, list):
                for nested in value:
                    inspect_json(nested)
        inspect_json(json.loads(data))
    except (ValueError, UnicodeError, RecursionError):
        pass
    if re.search(rb"\b(?:sb_secret_[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{25,})\b", data):
        kinds.add("secret API key")
    for token in re.findall(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{32,}", data):
        try:
            payload = token.split(b".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + b"=" * ((4 - len(payload) % 4) % 4)))
            if isinstance(claims, dict) and claims.get("role") == "service_role":
                kinds.add("service_role JWT")
        except (ValueError, UnicodeError):
            pass
    return kinds


def pe_machine(path: Path) -> int | None:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            return None
        stream.seek(struct.unpack_from("<I", header, 60)[0])
        signature = stream.read(6)
    return struct.unpack_from("<H", signature, 4)[0] if len(signature) == 6 and signature[:4] == b"PE\0\0" else None


def pe_versions(data: bytes) -> list[tuple[int, int, int, int]]:
    """Read VS_FIXEDFILEINFO signatures; do not execute the Windows binary."""
    values = []
    marker = struct.pack("<I", 0xFEEF04BD)
    for match in re.finditer(re.escape(marker), data):
        offset = match.start()
        if len(data) >= offset + 16:
            signature, structure, high, low = struct.unpack_from("<4I", data, offset)
            if signature == 0xFEEF04BD and structure == 0x10000:
                values.append((high >> 16, high & 65535, low >> 16, low & 65535))
    return values


class Audit:
    def __init__(self, stage: Path, work: Path, admin: Path, version: str, allow_helper_snapshot=False):
        self.stage, self.work, self.admin, self.version = stage, work, admin, version
        self.checks: list[dict] = []
        self.secrets: list[dict] = []
        self.file_count = 0
        self.total_bytes = 0
        self.sources = []
        self.release = {}
        self.allow_helper_snapshot = allow_helper_snapshot
        self.helper_snapshots = []
        self.version_metadata = {}

    def check(self, passed: bool, label: str, detail=None):
        self.checks.append({"check": label, "passed": bool(passed), **({"detail": detail} if detail is not None else {})})

    def required(self, base: Path, name: str) -> Path:
        path = base / name
        self.check(path.is_file() and path.stat().st_size > 0, "Required file: " + path.relative_to(self.stage).as_posix())
        return path

    def guarded(self, label: str, callback):
        try:
            callback()
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, struct.error) as error:
            # Neither credentials nor arbitrary file contents appear here.
            self.check(False, label, {"errorType": type(error).__name__})

    def scan_text(self, name: str, data: bytes):
        for kind in sorted(secret_kinds(data)):
            self.secrets.append({"path": name, "kind": kind})

    def inventory(self):
        forbidden_ai = []
        for path in sorted(self.stage.rglob("*")):
            name = path.relative_to(self.stage).as_posix()
            mode = path.lstat().st_mode
            if sensitive_filename(name):
                self.secrets.append({"path": name, "kind": "private state or sensitive filename"})
            parts = [part.lower() for part in path.relative_to(self.stage).parts]
            legal_notice = any(part in ("licenses", "licenses-agent") for part in parts) and "license" in path.name.lower()
            if path.suffix.lower() == ".onnx" or (not legal_notice and any(part.startswith("u2net") or any(part == package or part.startswith(package + "-") for package in AI_PACKAGES) for part in parts)):
                forbidden_ai.append(name)
            if stat.S_ISLNK(mode):
                link = os.readlink(path)
                self.check(not os.path.isabs(link) and path.exists() and path.resolve().is_relative_to(self.stage.resolve()), "Contained payload symlink: " + name)
            elif stat.S_ISREG(mode):
                self.file_count += 1
                self.total_bytes += path.stat().st_size
                if path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size < 5 * 1024 * 1024:
                    self.scan_text(name, path.read_bytes())
            elif not stat.S_ISDIR(mode):
                self.check(False, "Regular payload entry: " + name)
        self.check(not forbidden_ai, "No packaged ONNX/U2Net or AI inference libraries", {"unexpectedPaths": forbidden_ai[:40]})

    def metadata(self):
        self.release = json.loads(self.required(self.stage, "release.json").read_text())
        expected = {"version": self.version, "macExecutable": "Mac/GalaxyControl.app", "windowsExecutable": "Windows/GalaxyControl.exe", "sharedPort": 4323, "candidatePorts": PORTS, "languages": LANGUAGES, "standaloneDesktop": True, "requiresAdmin": False, "aiFeatures": False}
        self.check(all(self.release.get(key) == value for key, value in expected.items()), "Standalone release metadata, version, ports and language order", {"expected": expected})
        app = self.stage / "Mac/GalaxyControl.app"
        info = plistlib.loads(self.required(app, "Contents/Info.plist").read_bytes())
        self.check(info.get("CFBundleShortVersionString") == self.version and info.get("CFBundleVersion") == "12", "Mac app native version/build", {"version": info.get("CFBundleShortVersionString"), "build": info.get("CFBundleVersion")})
        self.check(bool(info.get("CFBundleIconFile")) and (app / "Contents/Resources" / info["CFBundleIconFile"]).is_file(), "Mac app icon is present")
        self.check("NSAppTransportSecurity" not in info, "No added Mac ATS bypass")
        win = self.required(self.stage / "Windows", "GalaxyControl.exe")
        versions = pe_versions(win.read_bytes())
        wanted = tuple(int(item) for item in self.version.split(".")) + (0,)
        self.check(("GalaxyControl " + self.version).encode("utf-16le") in win.read_bytes(), "Windows native embedded title version", {"expected": self.version})
        self.check(not versions or wanted in versions, "Any Windows VERSIONINFO resource agrees with release", {"expected": list(wanted), "found": [list(version) for version in versions], "resourcePresent": bool(versions)})
        self.version_metadata["Windows"] = {"embeddedTitleVersion": self.version, "nativeExeSha256": sha256(win), "fileVersionResource": [list(version) for version in versions] or "not provided by existing native host"}
        if sys.platform == "darwin":
            result = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True, text=True)
            self.check(result.returncode == 0, "Mac staged app ad-hoc signature verification")
            binary = app / "Contents/MacOS/GalaxyControl"
            result = subprocess.run(["lipo", "-archs", str(binary)], capture_output=True, text=True)
            self.check(result.returncode == 0 and set(result.stdout.split()) == {"arm64", "x86_64"}, "Mac universal native host architectures")

    def source(self, base: Path, expected_hash: str | None):
        archive = self.required(base, "tools/source/GalaxyControl-source.zip")
        source_hash = sha256(archive)
        if expected_hash:
            self.check(source_hash == expected_hash, "Parent-confirmed frozen source SHA256: " + base.relative_to(self.stage).as_posix())
        required = {"agent/server.py", "agent/common.py", "agent/index.py", "agent/phone.py", "engine/engine.py", "engine/engine_extra.py", "engine/office_export.py", "engine/requirements.txt", "mac/GalaxyControl.swift", "mac/AgentHost.swift", "mac/NativeBridge.swift", "mac/CaptureHub.swift", "mac/CaptureEditor.swift", "mac/ScreenRecord.swift", "windows/GalaxyControl.c", "windows/SharedHost.cpp", "windows/SharedHostPolicy.h", "windows/SharedHostPolicySelftest.cpp", "windows/NativeBridge.cpp", "windows/NativeProtocol.h", "windows/AgentEndpoint.h", "windows/Installer.nsi", "browser-extension/manifest.json", "browser-extension/agent-endpoint.js", "browser-extension/background.js", "admin/src/local-tools-standalone.tsx", "admin/src/features/local-tools/ToolsApp.tsx", "admin/src/features/local-tools/CanvasEditor.tsx", "admin/src/features/local-tools/ResultActions.tsx", "admin/src/features/local-tools/desktop-events.ts", "admin/src/features/local-tools/catalog.ts", "admin/src/features/local-tools/translations.ts", "admin/src/services/local-agent.ts", "admin/package.json", "admin/package-lock.json", "admin/tsconfig.local-tools.json", "admin/build-tools.mjs", "SOURCE-MANIFEST.json", "source_collector.py", "local_tools_source_graph.mjs", "i18n/locales.json", "BUILDING.txt", "COPYING"}
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            members = set(names)
            self.check(len(names) == len(members) and all(safe_member(name) for name in names), "Source ZIP safe paths and no duplicate members")
            self.check(bundle.testzip() is None, "Frozen source ZIP CRC for every member")
            self.check(required <= members, "Corresponding source includes desktop policy, phone and shared UI", {"missing": sorted(required - members)})
            self.check("admin/src/services/local-tools-rank.ts" not in members, "Standalone source graph excludes removed AI rank module")
            for name in names:
                if sensitive_filename(name):
                    self.secrets.append({"path": "source::" + name, "kind": "private state or sensitive filename"})
                if PurePosixPath(name).suffix.lower() in TEXT_SUFFIXES:
                    self.scan_text("source::" + name, bundle.read(name))
            manifest = json.loads(bundle.read("SOURCE-MANIFEST.json"))
            rows = manifest.get("files", [])
            row_names = {row.get("path") for row in rows}
            self.check(len(rows) == len(row_names) and row_names | {"SOURCE-MANIFEST.json"} == members, "Source manifest exact member set")
            mismatch = [row["path"] for row in rows if row["path"] not in members or len(bundle.read(row["path"])) != row.get("bytes") or hashlib.sha256(bundle.read(row["path"])).hexdigest() != row.get("sha256")]
            self.check(not mismatch, "Source manifest member byte sizes and SHA256", {"mismatches": mismatch[:20]})
            graph = manifest.get("graph", {})
            fixed = {"package.json", "package-lock.json", "tsconfig.json", "tsconfig.local-tools.json", "build-tools.mjs"}
            admin_names = {name.removeprefix("admin/") for name in members if name.startswith("admin/")}
            self.check(admin_names == set(graph.get("files", [])) | fixed, "Standalone UI source is exact parsed import closure plus build inputs")
            self.check(all("admin/" + edge.get("target", "") in members for edge in graph.get("edges", [])), "Source module/type/dynamic/HTML/CSS import targets included")
            excluded = ("admin/public/", "admin/supabase/", "admin/n8n/", "admin/api/", "admin/backend/", "admin/output/")
            self.check(not any(name.startswith(excluded) for name in members), "Source excludes unrelated ADMIN backend, uploads and environment trees")
            original_mismatches = []
            compared = 0
            for row in rows:
                if "source" not in row:
                    continue
                actual = (self.admin if row["path"].startswith("admin/") else self.work) / row["source"]
                current_hash = sha256(actual) if actual.is_file() else None
                if current_hash != row.get("sourceSHA256"):
                    if self.allow_helper_snapshot and row["path"] == "integration-tests/desktop_single_ui_release_tests.py" and actual.resolve() == Path(__file__).resolve() and current_hash:
                        snapshot = {"path": row["path"], "frozenSourceSha256": row.get("sourceSHA256"), "currentQaHelperSha256": current_hash, "reason": "Explicit parent-approved packaging-audit helper refinement after application source freeze; not runtime/UI/native/source-builder code"}
                        if snapshot not in self.helper_snapshots:
                            self.helper_snapshots.append(snapshot)
                        compared += 1
                        continue
                    original_mismatches.append(row["path"])
                compared += 1
            self.check(compared > 50 and not original_mismatches, "Frozen application source matches current ADMIN/native sources; explicit QA snapshot differences reported", {"compared": compared, "mismatches": original_mismatches[:30], "qaHelperSnapshotDifferences": self.helper_snapshots})
            component_count = {}
            component_mismatch = []
            runtime_files = {
                "agent": {"common.py", "signature_library.py", "phone.py", "index.py", "job_runner.py", "process_group.py", "rename.py", "server.py", "extension-origin.json"},
                "engine": {"engine.py", "engine_extra.py", "office_export.py", "agent-dependencies.json", "ffmpeg-build.json"},
                "browser-extension": {"manifest.json", "background.js", "popup.html", "popup.css", "popup.js", "capture-core.js", "agent-endpoint.js"} | {name.removeprefix("browser-extension/") for name in members if name.startswith("browser-extension/_locales/")},
            }
            for component, packaged in (("agent", base / "tools/engine/agent"), ("engine", base / "tools/engine"), ("browser-extension", base / "tools/browser-extension")):
                component_count[component] = 0
                actual_files = {file.relative_to(packaged).as_posix() for file in (packaged.glob("*") if component == "engine" else packaged.rglob("*")) if file.is_file()}
                self.check(actual_files == runtime_files[component], "Exact packaged runtime file set: " + component, {"missing": sorted(runtime_files[component] - actual_files), "extra": sorted(actual_files - runtime_files[component])})
                for relative in sorted(runtime_files[component]):
                    file = packaged / relative
                    name = component + "/" + relative
                    if name == "engine/ffmpeg-build.json":
                        continue  # Generated packaging metadata, independently checked below.
                    if name not in members or not file.is_file() or file.is_symlink() or sha256(file) != hashlib.sha256(bundle.read(name)).hexdigest():
                        component_mismatch.append(name)
                    else:
                        component_count[component] += 1
            self.check(all(count >= 4 for count in component_count.values()) and not component_mismatch, "Packaged agent, engine and extension exactly match frozen source", {"compared": component_count, "mismatches": component_mismatch})
            locales = json.loads(bundle.read("i18n/locales.json"))
            self.check(locales == json.loads((base / "tools/i18n/locales.json").read_text()), "Native translations equal corresponding source")
            category_source = bundle.read("admin/src/features/local-tools/catalog.ts").decode()
            match = re.search(r"toolCategories\s*:\s*Category\[\]\s*=\s*\[([^\]]+)\]", category_source)
            categories = re.findall(r"['\"]([a-z]+)['\"]", match[1]) if match else []
            self.check(categories == CATEGORIES, "Exactly 11 shared home cards, including phone and local file search", {"categories": categories})
            self.check(not re.search(r"check\(['\"]faces['\"]", category_source), "No automatic face detection UI option")
            tools = bundle.read("admin/src/features/local-tools/ToolsApp.tsx").decode()
            standalone = bundle.read("admin/src/local-tools-standalone.tsx").decode()
            self.check("local-tools-rank" not in tools and "rankLocalFiles" not in tools and "aiRank" not in tools, "Toolbox has no optional external AI rank call or UI")
            self.check("loadReleaseManifest" not in standalone and "standalone" in tools and "GalaxyControl" in tools, "Native standalone uses shared toolbox without startup download fetch")
            events = bundle.read("admin/src/features/local-tools/desktop-events.ts").decode()
            for key in ("galaxycontrol:navigate", "galaxycontrol:shortcut", "desktopReady", "captureReady", "captureClosed", "captureCancelled", "galaxycontrol:clipboard-result"):
                self.check(key in events, "Native data-only event contract: " + key)
            policy = bundle.read("windows/SharedHostPolicy.h").decode()
            self.check(all('"' + key + '"' in policy for key in ("token", "origin", "deviceId", "ownerId", "version", "clientName")) and "value.size()!=6" in policy and "value[\"origin\"]!=origin" in policy, "Windows six-field private bootstrap policy validates exact origin")
            client = bundle.read("admin/src/services/local-agent.ts").decode()
            self.check("__galaxyDesktopSession" in client and "validDesktopSession" in client and "desktopHostSession=true" in client and "persistedPairing=false" in client, "Native session consumed in memory without replacing persistent ADMIN pairing")
            translations = bundle.read("admin/src/features/local-tools/translations.ts").decode()
            literal = r'''((?:'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"))'''
            row_pattern = r"\brow\(\s*" + r"\s*,\s*".join([literal] * 6) + r"\s*\)"
            rows_text = re.findall(row_pattern, translations)
            translation_count = len(rows_text)
            incomplete = [row[0][1:-1] for row in rows_text if not all(value[1:-1] for value in row)]
            if translation_count != len(re.findall(r"\brow\(", translations)):
                incomplete.append("unparsed translation row")
            self.check(translation_count > 100 and not incomplete, "Shared toolbox five-language nonempty translation rows", {"rows": translation_count, "incomplete": incomplete[:20]})
            self.check(all(value in translations for value in ("파일 찾기", "Find files", "Tìm tệp", "ファイル検索", "查找文件", "배경 편집")), "Five-language AI-free file search and manual background labels")
            self.sources.append({"path": str(archive), "sha256": source_hash, "members": len(members), "originalSourcesCompared": compared, "allMembersCRCChecked": True})

    def payload(self, base: Path, arches: tuple[str, ...], mac: bool):
        engine = base / "tools/engine"
        for file in ("engine.py", "engine_extra.py", "office_export.py", "agent/server.py", "agent/common.py", "agent/signature_library.py", "agent/index.py", "agent/phone.py", "agent/job_runner.py", "agent/process_group.py", "agent/rename.py", "agent-dependencies.json", "fonts/NotoSansCJK-Regular.ttc"):
            self.required(engine, file)
        dependency_rows = json.loads((engine / "agent-dependencies.json").read_text())
        self.check(not any(row.get("name", "").lower().startswith(AI_PACKAGES) for row in dependency_rows), "Dependency manifest excludes AI inference runtime")
        expected_dependencies = {"numpy", "watchdog", "imageio-ffmpeg", "opencv-python-headless", "packaging", "python-pptx", "lxml", "xlsxwriter"}
        for arch in arches:
            names = {row.get("name", "").lower() for row in dependency_rows if row.get("arch") == arch}
            self.check(expected_dependencies <= names, "Remaining dependency manifest coverage: " + arch)
            deps = engine / "deps-agent" / arch
            for file in ("numpy/__init__.py", "watchdog/observers/__init__.py", "watchdog/events.py", "imageio_ffmpeg/__init__.py", "pptx/__init__.py", "xlsxwriter/__init__.py", "lxml/__init__.py", "packaging/__init__.py"):
                self.required(deps, file)
            self.check(bool(list((deps / "cv2").glob("*.so" if mac else "*.pyd"))), "Traditional QR/retouch OpenCV native library: " + arch)
            if mac:
                python = base / "tools/python" / arch
                for file in ("bin/python3.13", "lib/libpython3.13.dylib", "lib/python3.13/site-packages/PIL/_imaging.cpython-313-darwin.so", "lib/python3.13/site-packages/pymupdf/_mupdf.so"):
                    self.required(python, file)
                for file in ("adb", "scrcpy", "scrcpy-server"):
                    self.required(base / "tools" / arch, file)
                if sys.platform == "darwin":
                    for path in (python / "bin/python3.13", base / "tools" / arch / "scrcpy", base / "tools" / arch / "adb"):
                        result = subprocess.run(["lipo", "-archs", str(path)], capture_output=True, text=True)
                        self.check(result.returncode == 0 and arch in result.stdout.split() and bool(path.stat().st_mode & 0o111), "Native executable architecture/mode: " + path.relative_to(self.stage).as_posix())
            else:
                for file in ("python.exe", "pythonw.exe", "python313.dll", "python313.zip", "python313._pth", "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "Lib/site-packages/PIL/_imaging.cp313-win_amd64.pyd", "Lib/site-packages/pymupdf/_mupdf.pyd"):
                    self.required(base / "tools/python", file)
                for file in ("scrcpy.exe", "adb.exe", "scrcpy-server", "AdbWinApi.dll", "AdbWinUsbApi.dll", "SDL3.dll", "avcodec-62.dll", "avformat-62.dll", "avutil-60.dll", "swresample-6.dll", "libusb-1.0.dll"):
                    self.required(base / "tools/scrcpy", file)
                for path in (base / "GalaxyControl.exe", base / "tools/webview2/WebView2Loader.dll", base / "tools/python/python.exe", base / "tools/scrcpy/scrcpy.exe", base / "tools/scrcpy/adb.exe"):
                    machine = pe_machine(path)
                    self.check(machine == (0x14C if path.name == "adb.exe" else 0x8664), "Windows PE machine: " + path.relative_to(self.stage).as_posix(), {"machine": hex(machine) if machine is not None else None})
        ffmpeg = json.loads(self.required(engine, "ffmpeg-build.json").read_text())
        self.check(ffmpeg.get("license") == "LGPL-2.1-or-later" and all(ffmpeg.get(key) is False for key in ("network", "gpl", "nonfree")), "FFmpeg remains local LGPL build")
        for arch in arches:
            row = ffmpeg["binaries"][arch]
            binary = self.required(engine, row["path"])
            self.check(sha256(binary) == row["sha256"], "FFmpeg binary matches provenance SHA256: " + arch)
        font_rows = json.loads(self.required(engine, "fonts/manifest.json").read_text())
        self.check(all(sha256(engine / row["file"]) == row["sha256"] for row in font_rows), "Bundled CJK font manifest hashes")
        native_locales = json.loads(self.required(base, "tools/i18n/locales.json").read_text())
        incomplete = [key for key, values in native_locales.items() if not key or not isinstance(values, dict) or any(not isinstance(values.get(language), str) or not values.get(language) for language in LANGUAGES[1:])]
        self.check(len(native_locales) > 100 and not incomplete, "Native catalog Korean source plus four nonempty languages", {"keys": len(native_locales), "incomplete": incomplete[:20]})
        extension = base / "tools/browser-extension"
        extension_manifest = json.loads(self.required(extension, "manifest.json").read_text())
        self.check(extension_manifest.get("version") == self.release.get("browserExtensionVersion"), "Browser extension version matches release metadata")
        self.check(extension_manifest.get("host_permissions") == ["http://127.0.0.1:" + str(port) + "/*" for port in PORTS], "Extension four-port exact loopback host permissions")
        for file in ("background.js", "capture-core.js", "agent-endpoint.js", "popup.js", "popup.html"):
            self.required(extension, file)
        for language in ("ko", "en", "vi", "ja", "zh_CN"):
            rows = json.loads(self.required(extension, "_locales/" + language + "/messages.json").read_text())
            self.check(bool(rows) and all(isinstance(row, dict) and row.get("message") for row in rows.values()), "Extension nonempty language: " + language)
        for file in ("ffmpeg-7.1-zlib-1.3.2-rebuild.tar.xz", "mupdf-1.28.2-source.tar.gz", "pymupdf-1.28.2-source.tar.gz"):
            self.required(base / "tools/source", file)

    def common_ui(self):
        mac_ui = self.stage / "Mac/GalaxyControl.app/Contents/Resources/tools-ui"
        windows_ui = self.stage / "Windows/resources/tools-ui"
        receipt = json.loads((TASK / "ui-receipt.json").read_text())
        frozen_rows = receipt["build"]["files"]
        expected = {row["path"]: row for row in frozen_rows}
        for ui in (mac_ui, windows_ui):
            actual = {path.relative_to(ui).as_posix() for path in ui.rglob("*") if path.is_file()}
            self.check(actual == set(expected), "Native UI exact frozen build file set: " + ui.relative_to(self.stage).as_posix(), {"missing": sorted(set(expected) - actual), "extra": sorted(actual - set(expected))})
            mismatches = [name for name, row in expected.items() if not (ui / name).is_file() or sha256(ui / name) != row["sha256"] or (ui / name).stat().st_size != row["bytes"]]
            self.check(not mismatches, "Native UI exact frozen build hashes: " + ui.relative_to(self.stage).as_posix(), {"mismatches": mismatches})
            html = (ui / "index.html").read_text()
            references = re.findall(r"(?:src|href)=[\"'](/tools/assets/[^\"']+)[\"']", html)
            self.check(bool(references) and all((ui / reference.removeprefix("/tools/")).is_file() for reference in references), "Compiled UI HTML asset closure")
            scripts = "\n".join(path.read_text() for path in (ui / "assets").glob("*.js"))
            self.check(all(key in scripts for key in ("GalaxyControl", "galaxycontrol:navigate", "galaxycontrol:shortcut", "__galaxyDesktopSession", "desktopReady", "captureClosed", "Find files", "Tìm tệp", "ファイル検索", "查找文件")), "Compiled native UI contains common home, five languages and native contracts")
            self.check("AI 파일 찾기" not in scripts and "rankLocalFiles" not in scripts, "Compiled native UI excludes AI file-search home and ranking")
        identical = all((mac_ui / name).is_file() and (windows_ui / name).is_file() and sha256(mac_ui / name) == sha256(windows_ui / name) for name in expected)
        self.check(identical, "Windows/macOS use byte-identical frozen toolbox UI")

    def run(self, expected_hash: str | None):
        self.guarded("Stage inventory and secret scan", self.inventory)
        self.guarded("Release and native versions", self.metadata)
        self.guarded("Shared frozen standalone UI", self.common_ui)
        for base, arches, mac in ((self.stage / "Mac/GalaxyControl.app/Contents/Resources", ("arm64", "x86_64"), True), (self.stage / "Windows", ("win64",), False)):
            self.guarded("Payload dependencies: " + ("macOS" if mac else "Windows"), lambda base=base, arches=arches, mac=mac: self.payload(base, arches, mac))
            self.guarded("Corresponding source: " + ("macOS" if mac else "Windows"), lambda base=base: self.source(base, expected_hash))
        self.check(len(self.sources) == 2 and self.sources[0]["sha256"] == self.sources[1]["sha256"], "Windows/macOS bundle the identical frozen source archive")
        self.check(not self.secrets, "No packaged private credentials, state or private keys", {"findings": self.secrets})


def self_test():
    assert safe_member("admin/src/features/local-tools/desktop-events.ts")
    assert not any(safe_member(value) for value in ("../secret", "/tmp/secret", "C:/secret", "safe\\secret", "x\0y"))
    assert sensitive_filename("state/desktop-session.json") and sensitive_filename("build-private-key.pem")
    assert not sensitive_filename("agent/protocol.json")
    assert secret_kinds(b"no real credentials here") == set()
    escaped_pem = json.dumps({"nested": {"private_key": "-----BEGIN " + "PRIVATE KEY-----\n" + "A" * 100 + "\n-----END " + "PRIVATE KEY-----"}}).encode()
    assert secret_kinds(escaped_pem) == {"PEM private key"}
    fixture = struct.pack("<4I", 0xFEEF04BD, 0x10000, (4 << 16) | 2, (1 << 16))
    assert pe_versions(fixture) == [(4, 2, 1, 0)]
    print("Read-only audit helper self-tests: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, default=TASK / "release/GalaxyControl")
    parser.add_argument("--work", type=Path, default=BASE / "work")
    parser.add_argument("--admin", type=Path, default=Path("/Users/leechangmin/Projects/ADMIN"))
    parser.add_argument("--version", default="4.2.1")
    parser.add_argument("--source-sha256", help="Optional parent-confirmed frozen source SHA256")
    parser.add_argument("--allow-audit-helper-snapshot", action="store_true", help="Explicitly record only this QA helper's post-freeze snapshot difference; all application sources stay strict")
    parser.add_argument("--receipt", type=Path, default=TASK / "desktop-single-ui-release-audit.json")
    parser.add_argument("--self-test", action="store_true", help="Test pure audit helpers without reading or altering a release")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("--version must be a three-part numeric version")
    if args.source_sha256 and not re.fullmatch(r"[0-9a-f]{64}", args.source_sha256):
        parser.error("--source-sha256 must be a lowercase SHA256")
    stage, receipt = args.stage.resolve(), args.receipt.resolve()
    if not stage.is_dir():
        parser.error("Stage does not exist; run only after the new release has been staged")
    if receipt.is_relative_to(stage) or receipt.exists():
        parser.error("Receipt must be a new file outside the stage; existing receipts are preserved")
    start = time.monotonic()
    audit = Audit(stage, args.work.resolve(), args.admin.resolve(), args.version, args.allow_audit_helper_snapshot)
    audit.run(args.source_sha256)
    errors = [check["check"] for check in audit.checks if not check["passed"]]
    result = {"schemaVersion": 1, "scope": "Read-only staged package and corresponding-source checks only", "stage": str(stage), "version": args.version, "createdAt": time.time(), "seconds": round(time.monotonic() - start, 3), "status": "PASS" if not errors else "FAIL", "checksPassed": len(audit.checks) - len(errors), "checksTotal": len(audit.checks), "filesScanned": audit.file_count, "payloadBytes": audit.total_bytes, "sourceArchives": audit.sources, "nativeVersionMetadata": audit.version_metadata, "approvedQaHelperSnapshotDifferences": audit.helper_snapshots, "checks": audit.checks, "errors": errors, "physicalWindowsUI": "unverified", "physicalMacCapture": "not exercised by this packaging audit", "installationAndLogin": "not exercised", "clipboardPasteIntoThirdPartyApps": "not exercised", "deployment": "not exercised"}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("status", "checksPassed", "checksTotal", "filesScanned", "seconds")}, ensure_ascii=False))
    print("Receipt:", receipt)
    if errors:
        print("Failed checks:", json.dumps(errors, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

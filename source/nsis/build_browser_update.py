"""Build and fully hash-verify a small, real NSIS source updater on macOS."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, shutil, struct, subprocess, tempfile, time, zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HELPER = ROOT / "work/windows/BrowserCaptureUpdate.py"
spec = importlib.util.spec_from_file_location("browser_update_helper", HELPER)
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)

def digest(path):
    return update.digest(path)

def inventory(stage):
    files = [stage / "GalaxyControl.exe"]
    for name in ("tools", "resources"):
        files.extend(sorted(p for p in (stage / name).rglob("*") if p.is_file()))
    return {str(p.relative_to(stage)): digest(p) for p in files}

def selftests():
    """Synthetic/local file fixtures; these do not execute Windows programs."""
    def fixture(folder, extension_version="4.0.0"):
        folder.mkdir(parents=True)
        pe = bytearray(512)
        pe[:2] = b"MZ"
        struct.pack_into("<I", pe, 0x3c, 128)
        pe[128:132] = b"PE\0\0"
        struct.pack_into("<H", pe, 132, 0x8664)
        struct.pack_into("<H", pe, 152, 0x20b)
        struct.pack_into("<H", pe, 220, 2)
        (folder / "GalaxyControl.exe").write_bytes(pe)
        for relative in update.RELATIVE_FILES:
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture:" + relative, encoding="utf-8")
        manifest = {"manifest_version":3, "version":extension_version, "key":update.EXPECTED_KEY}
        (folder / "tools/browser-extension/manifest.json").write_text(json.dumps(manifest))
        common = folder / "tools/engine/agent/common.py"
        common.write_text("VERSION = '4.0.0'\n")
        runtime = folder / "tools/python/python.exe"
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(b"mock runtime: not executed")
    def payload(folder):
        receipt = {"version":update.PATCH_VERSION,"extension_key":update.EXPECTED_KEY,
                   "files":{r:{"sha256":digest(folder/r),"bytes":(folder/r).stat().st_size} for r in update.RELATIVE_FILES}}
        (folder / "update-payload.json").write_text(json.dumps(receipt))
    passed = []
    with tempfile.TemporaryDirectory(prefix="browser-update-test-",dir=HERE) as directory:
        base = Path(directory)
        app, new = base/"앱 portable", base/"payload"
        fixture(app);fixture(new,"4.0.1");payload(new)
        old = {r:digest(app/r) for r in update.RELATIVE_FILES}
        immutable = {r:digest(app/r) for r in ("GalaxyControl.exe","tools/python/python.exe","tools/engine/agent/common.py")}
        result = update.apply_update(app,new)
        assert result["replaced"] == 14
        assert all(digest(app/r)==digest(new/r) for r in update.RELATIVE_FILES)
        assert all(digest(app/r)==value for r,value in immutable.items())
        assert all(digest(app/update.BACKUP_RELATIVE/r)==value for r,value in old.items())
        passed.append("14 program files updated; first backups and native/runtime/common preserved")
        update.apply_update(app,new)
        assert all(digest(app/update.BACKUP_RELATIVE/r)==value for r,value in old.items())
        passed.append("reapplication preserves first pre-update backup")
        common = app/"tools/engine/agent/common.py"
        common.write_text("VERSION = '9.9.9'\n")
        try:update.validate_installation(app)
        except update.UpdateError as e:assert str(e)=="unsupportedVersion"
        else:raise AssertionError("wrong app version accepted")
        common.write_text("VERSION = '4.0.0'\n")
        manifest = app/"tools/browser-extension/manifest.json"
        right = manifest.read_bytes()
        manifest.write_text('{"manifest_version":3,"key":"other"}')
        try:update.validate_installation(app)
        except update.UpdateError as e:assert str(e)=="differentExtension"
        else:raise AssertionError("wrong extension accepted")
        manifest.write_bytes(right)
        passed.append("wrong app version/extension key rejected without writes")
        fault_app = base/"fault-app";fixture(fault_app)
        before = {r:digest(fault_app/r) for r in update.RELATIVE_FILES}
        calls = 0
        def fault_copy(source,destination):
            nonlocal calls
            calls += 1
            update.atomic_copy(source,destination)
            if calls==3:raise OSError("injected write-then-raise fixture")
        try:update.apply_update(fault_app,new,fault_copy)
        except OSError:pass
        else:raise AssertionError("fault did not propagate")
        assert all(digest(fault_app/r)==value for r,value in before.items())
        passed.append("write-then-raise failure restores every original program file")
        alias = base/"linked-app";fixture(alias)
        target = alias/"tools/engine/agent/server.py"
        outside = base/"outside.py";outside.write_text("do not touch")
        target.unlink();target.symlink_to(outside)
        try:update.apply_update(alias,new)
        except update.UpdateError as e:assert str(e)=="linkedTarget"
        else:raise AssertionError("linked target accepted")
        assert outside.read_text()=="do not touch"
        passed.append("symlink target rejected; outside file preserved")
        # Corrupt an otherwise-valid payload and verify rejection before any update.
        damaged = new/"tools/browser-extension/popup.js"
        damaged.write_text("tampered")
        prior = {r:digest(app/r) for r in update.RELATIVE_FILES}
        try:update.apply_update(app,new)
        except update.UpdateError as e:assert str(e)=="payloadMismatch"
        else:raise AssertionError("tampered payload accepted")
        assert all(digest(app/r)==value for r,value in prior.items())
        passed.append("payload corruption rejected before target writes")
    return passed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage",type=Path)
    parser.add_argument("--frozen",action="store_true")
    parser.add_argument("--source-sha256")
    parser.add_argument("--self-test",action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps({"tests":selftests(),"windows_program_executed":False},ensure_ascii=False))
        return
    if not args.stage or not args.frozen or not args.source_sha256:
        parser.error("Building requires --stage ABS --frozen --source-sha256 EXACT_HASH")
    stage = args.stage.resolve(strict=True)
    update.validate_installation(stage)
    native = json.loads((ROOT/"work/windows/unified-validation.json").read_text())
    if digest(stage/"GalaxyControl.exe") != native["sha256"]:
        raise RuntimeError("Native app differs from validated build")
    extension = stage/"tools/browser-extension"
    actual = {str(p.relative_to(extension)).replace("\\","/") for p in extension.rglob("*") if p.is_file()}
    if actual != set(update.EXTENSION_FILES):
        raise RuntimeError("Unexpected extension file set: "+str(actual.symmetric_difference(update.EXTENSION_FILES)))
    manifest = json.loads((extension/"manifest.json").read_text())
    if manifest["version"]!="4.0.1" or manifest["key"]!=update.EXPECTED_KEY:
        raise RuntimeError("Wrong version or changed extension identity")
    source = stage/"tools/source/GalaxyControl-source.zip"
    if digest(source)!=args.source_sha256:
        raise RuntimeError("Frozen corresponding-source ZIP differs from root's expected SHA")
    # The distributed corresponding source must contain this exact updater/build source.
    source_paths = {"windows/BrowserCaptureUpdate.py":HELPER,
                    "windows/BrowserCaptureUpdate.nsi":ROOT/"work/windows/BrowserCaptureUpdate.nsi",
                    "nsis/build_browser_update.py":Path(__file__).resolve()}
    with zipfile.ZipFile(source) as archive:
        for name,path in source_paths.items():
            if archive.read(name)!=path.read_bytes():
                raise RuntimeError("Frozen ZIP does not contain current updater source: "+name)
        source_entries = len(archive.infolist())
    payload = {"version":"4.0.1","extension_key":update.EXPECTED_KEY,
               "files":{r:{"sha256":digest(stage/r),"bytes":(stage/r).stat().st_size} for r in update.RELATIVE_FILES}}
    payload_manifest = HERE/"browser-update-payload.json"
    payload_manifest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    tests = selftests()
    before = inventory(stage)
    env = dict(os.environ,NSISDIR=str(HERE/"nsis-3.13"))
    command = [str(HERE/"nsis-3.13/makensis"),"-NOCD","-V3",
               "-DGALAXY_PACKAGE="+str(stage),"-DUPDATE_MANIFEST="+str(payload_manifest),
               str(ROOT/"work/windows/BrowserCaptureUpdate.nsi")]
    start = time.time()
    with (HERE/"browser-update-build.log").open("w") as stream:
        process = subprocess.run(command,cwd=HERE,env=env,stdout=stream,stderr=subprocess.STDOUT)
    if process.returncode:
        raise RuntimeError("NSIS update build failed; see work/nsis/browser-update-build.log")
    installer = HERE/"GalaxyControl-BrowserCapture-Update.exe"
    if not installer.is_file() or not 100_000<installer.stat().st_size<100_000_000:
        raise RuntimeError("Update installer missing or exceeds the 100 MB upload limit")
    if inventory(stage)!=before:
        raise RuntimeError("Stage changed during compilation; discard and rebuild from a frozen stage")
    extract = HERE/"browser-update-extracted"
    if extract.exists():shutil.rmtree(extract)
    extract.mkdir()
    with (HERE/"browser-update-extract.log").open("w") as stream:
        process = subprocess.run([str(ROOT/"work/vc-runtime/tools/7zip/7zz"),"x","-y","-o"+str(extract),str(installer)],stdout=stream,stderr=subprocess.STDOUT)
    if process.returncode:raise RuntimeError("Update installer extraction failed")
    candidates = [p.parent for p in extract.rglob("update-payload.json")
                  if digest(p)==digest(payload_manifest)]
    if len(candidates)!=1:raise RuntimeError("Update extracted payload is missing or ambiguous")
    extracted = candidates[0]
    for relative,item in payload["files"].items():
        if digest(extracted/relative)!=item["sha256"]:
            raise RuntimeError("Extracted update payload mismatch: "+relative)
    helpers = [p for p in extract.rglob("BrowserCaptureUpdate.py") if digest(p)==digest(HELPER)]
    if len(helpers)!=1:raise RuntimeError("Extracted updater helper mismatch")
    data = installer.read_bytes()
    offset = struct.unpack_from("<I",data,0x3c)[0]
    if data[:2]!=b"MZ" or data[offset:offset+4]!=b"PE\0\0":raise RuntimeError("Not a real PE installer")
    subsystem = struct.unpack_from("<H",data,offset+24+68)[0]
    if subsystem!=2:raise RuntimeError("Update installer is not a GUI subsystem executable")
    header = data[:57344]
    if b"asInvoker" not in header and "asInvoker".encode("utf-16le") not in header:
        raise RuntimeError("Update installer does not contain per-user asInvoker manifest")
    report = {"version":"4.0.1","installer":str(installer),"bytes":len(data),
              "sha256":digest(installer),"payload_file_count":len(payload["files"]),
              "payload_hash_mismatches":0,"stage_changed_during_build":False,
              "corresponding_source_sha256":args.source_sha256,"source_snapshot_entries":source_entries,
              "native_app_sha256":native["sha256"],"per_user_manifest":"asInvoker",
              "NSIS":"3.13 native macOS compiler + official Unicode Windows stub",
              "languages":["ko","en","vi","ja","zh"],"backup_location":update.BACKUP_RELATIVE,
              "native_and_runtime_written":False,"private_user_config_written":False,
              "existing_extension_identity_preserved":True,"fixture_tests":tests,
              "elapsed_seconds":round(time.time()-start,2),
              "actual_windows_runtime_executed":False,"signature":"Unsigned",
              "runtime_limit":"Native compilation, extracted-file hashes and local synthetic file fixtures verified on macOS. Windows installer UI, mutex APIs, and bundled Windows Python execution have not been run.",
              "commands":command,"files":payload["files"],
              "helper_sha256":digest(HELPER),"script_sha256":digest(ROOT/"work/windows/BrowserCaptureUpdate.nsi"),
              "build_script_sha256":digest(Path(__file__).resolve())}
    (HERE/"browser-update-validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()

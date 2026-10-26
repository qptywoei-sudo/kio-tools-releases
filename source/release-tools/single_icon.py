"""Build customer ZIPs containing one app/icon; keep signed updater payloads separate.

Only the audited baseline runtime and collected corresponding source are included.
No account state, credentials, signing keys or repository history are packaged.
"""
from pathlib import Path
import argparse, hashlib, json, os, plistlib, shutil, stat, struct, subprocess, sys, zipfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from source_collector import write_source_bundle
from prepare_update import inspect_zip


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def tree_zip(path, tree, prefix):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(tree.rglob('*')):
            if '__pycache__' in file.parts or file.name == '.DS_Store': continue
            if file.is_dir() and not file.is_symlink(): continue
            name = prefix + '/' + file.relative_to(tree).as_posix()
            if file.is_symlink():
                info = zipfile.ZipInfo(name); info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, str(file.readlink()).encode())
            else: archive.write(file, name)


def refresh_runtime(tools, source_zip):
    agent = tools / 'engine/agent'
    for file in (SOURCE / 'agent').iterdir():
        if file.is_file() and file.suffix in ('.py', '.json') and not file.name.endswith('_tests.py'):
            shutil.copy2(file, agent / file.name)
    for file in (SOURCE / 'i18n').glob('*.json'): shutil.copy2(file, tools / 'i18n' / file.name)
    # Refresh the packaged extension too: the baseline contains the old icon,
    # popup and localized product name. Public key/origin/permission IDs stay.
    for file in (SOURCE / 'browser-extension').rglob('*'):
        if not file.is_file() or file.is_symlink(): continue
        relative = file.relative_to(SOURCE / 'browser-extension')
        runtime = (len(relative.parts) == 1 and file.name in ('manifest.json', 'popup.html', 'popup.css', 'popup.js', 'background.js', 'agent-endpoint.js', 'capture-core.js')) or (relative.parts[0] in ('icons', '_locales') and file.suffix in ('.png', '.json'))
        if runtime:
            destination = tools / 'browser-extension' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
    shutil.copy2(source_zip, tools / 'source/KIO-Control-source.zip')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--baseline-version', required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--mac-stage', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--zig', required=True)
    args = parser.parse_args(); out = args.out.resolve(); version = args.version
    out.mkdir(parents=True, exist_ok=False)
    source_zip = out / f'Bogo-Tools-{version}-source.zip'
    write_source_bundle(SOURCE, SOURCE / 'desktop-ui', json.loads((SOURCE / 'i18n/locales.json').read_text()), source_zip, desktop_ui=SOURCE / 'desktop-ui')
    stage = out / 'stage'; stage.mkdir()
    app = stage / 'Bogo Tools.app'
    shutil.copytree(args.mac_stage, app, symlinks=True, ignore=shutil.ignore_patterns('__pycache__', '.DS_Store'))
    resources = app / 'Contents/Resources'
    shutil.copy2(SOURCE / 'mac/build/GalaxyControl', app / 'Contents/MacOS/KIOControl')
    info = app / 'Contents/Info.plist'; meta = plistlib.loads(info.read_bytes())
    meta.update(CFBundleShortVersionString=version, CFBundleVersion=version.replace('.', ''), CFBundleDisplayName='Bogo Tools', CFBundleName='Bogo Tools', CFBundleIconFile='KIOTools.icns', NSScreenCaptureUsageDescription='Bogo Tools captures only the screen or window you choose.')
    meta['LSHasLocalizedDisplayName'] = True
    info.write_bytes(plistlib.dumps(meta))
    for locale in ('en', 'ko', 'vi', 'ja', 'zh-Hans', 'zh-Hant'):
        localized = resources / (locale + '.lproj')
        localized.mkdir(exist_ok=True)
        (localized / 'InfoPlist.strings').write_text('\"CFBundleDisplayName\" = \"Bogo Tools\";\n\"CFBundleName\" = \"Bogo Tools\";\n', encoding='utf-8')
    shutil.copy2(SOURCE / 'mac/KIOTools.icns', resources / 'KIOTools.icns')
    shutil.rmtree(resources / 'tools-ui'); shutil.copytree(SOURCE / 'desktop-ui/dist', resources / 'tools-ui')
    refresh_runtime(resources / 'tools', source_zip)
    subprocess.run([sys.executable, str(SOURCE / 'mac/sign-local.py'), '--setup', str(app)], check=True)
    subprocess.run([str(app / 'Contents/MacOS/KIOControl'), '--self-check'], check=True)
    customer_mac = out / f'Bogo-Tools-{version}-Mac-Portable.zip'
    tree_zip(customer_mac, app, 'Bogo Tools.app')
    update_mac = out / f'Bogo-Tools-{version}-Mac-Update.zip'
    tree_zip(update_mac, app, 'KIO-Control-Mac/Bogo Tools.app')
    # Inspect before extraction; all version, containment and private-data checks stay active.
    inspect_zip(args.baseline, 'Windows', args.baseline_version)
    with zipfile.ZipFile(args.baseline) as archive: archive.extractall(stage)
    windows = stage / 'KIO-Control-Windows'
    shutil.copy2(SOURCE / 'windows/KIOControl.exe', windows / 'KIOControl.exe')
    shutil.rmtree(windows / 'resources/tools-ui'); shutil.copytree(SOURCE / 'desktop-ui/dist', windows / 'resources/tools-ui')
    refresh_runtime(windows / 'tools', source_zip)
    # Exact content-named icon prevents the prior installation's Explorer cache
    # from supplying a yellow icon. Existing AUMID/EXE/data paths stay stable.
    taskbar_icon = 'bogo-tools-app-' + sha(SOURCE / 'windows/GalaxyControl.ico')[:8] + '.ico'
    shutil.copy2(SOURCE / 'windows/GalaxyControl.ico', windows / 'resources' / taskbar_icon)
    notices = windows / 'tools/licenses/previous-release-notices'; notices.mkdir(exist_ok=True)
    for file in windows.iterdir():
        if file.is_file() and file.name != 'KIOControl.exe': shutil.move(str(file), str(notices / file.name))
    update_windows = out / f'Bogo-Tools-{version}-Windows-Update.zip'
    tree_zip(update_windows, windows, 'KIO-Control-Windows')
    audit = {platform: inspect_zip(path, platform, version) for platform, path in [('Mac', update_mac), ('Windows', update_windows)]}
    launcher = stage / 'Bogo Tools.exe'
    subprocess.run([args.zig, 'c++', '-target', 'x86_64-windows-gnu', '-std=c++17', '-municode', '-O2', '-Wl,--subsystem,windows', '-DKIO_RELEASE=L"' + version + '"', '-DKIO_PAYLOAD_SHA256="' + sha(update_windows) + '"', str(SOURCE / 'windows/PortableLauncher.cpp'), str(SOURCE / 'windows/GalaxyControl.res'), '-lshell32', '-lole32', '-lbcrypt', '-o', str(launcher)], check=True)
    with launcher.open('ab') as output, update_windows.open('rb') as payload:
        shutil.copyfileobj(payload, output); output.write(struct.pack('<Q', update_windows.stat().st_size) + b'KIOTOOLS')
    customer_windows = out / f'Bogo-Tools-{version}-Windows-Portable.zip'
    with zipfile.ZipFile(customer_windows, 'w', zipfile.ZIP_STORED) as archive: archive.write(launcher, 'Bogo Tools.exe')
    for path, root in [(customer_windows, 'Bogo Tools.exe'), (customer_mac, 'Bogo Tools.app')]:
        with zipfile.ZipFile(path) as archive:
            assert {name.split('/')[0] for name in archive.namelist()} == {root}
            assert archive.testzip() is None
    # Inspect the actual embedded payload, not just the build input.
    with launcher.open('rb') as stream:
        stream.seek(-16, 2); size, magic = struct.unpack('<Q8s', stream.read(16))
        assert magic == b'KIOTOOLS' and size == update_windows.stat().st_size
        stream.seek(-16-size, 2); digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(min(1024*1024, size)), b''):
            digest.update(chunk); size -= len(chunk)
            if size == 0: break
        assert digest.hexdigest() == sha(update_windows)
    report = {'version': version, 'updatePayloads': audit, 'customerRoots': {'Mac': ['Bogo Tools.app'], 'Windows': ['Bogo Tools.exe']}, 'embeddedWindowsPayloadVerified': True, 'windowsGUIVerified': False, 'appleNotarized': False,
              'assets': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in [customer_mac, customer_windows, source_zip, update_mac, update_windows]}}
    (out / 'package-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()

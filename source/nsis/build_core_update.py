"""Compile and extract/hash-check a 4.2 program updater from a frozen release."""
from pathlib import Path
import xml.etree.ElementTree as ET
import argparse,hashlib,importlib.util,json,os,shutil,struct,subprocess,tempfile,time,zipfile
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
HELPER=ROOT/'work/windows/CoreUpdate.py'
spec=importlib.util.spec_from_file_location('galaxy_core_update',HELPER)
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)
digest=update.digest

def manifest_as_invoker(data):
    """Read RT_MANIFEST from PE sections; icon size must not affect this check."""
    u16=lambda at:struct.unpack_from('<H',data,at)[0]
    u32=lambda at:struct.unpack_from('<I',data,at)[0]
    pe=u32(0x3c);optional=pe+24;directories=optional+(112 if u16(optional)==0x20b else 96)
    resource_rva,resource_size=u32(directories+16),u32(directories+20)
    if not resource_rva or not resource_size:return False
    sections=[];table=optional+u16(pe+20)
    for number in range(u16(pe+6)):
        at=table+number*40;sections.append((u32(at+12),max(u32(at+8),u32(at+16)),u32(at+20)))
    def offset(rva):
        for virtual,length,raw in sections:
            if virtual<=rva<virtual+length:return raw+rva-virtual
        raise RuntimeError('Manifest RVA outside PE sections')
    base=offset(resource_rva)
    def walk(relative,path=()):
        if len(path)>3 or relative+16>resource_size:raise RuntimeError('Invalid PE resource directory')
        at=base+relative
        for number in range(u16(at+12)+u16(at+14)):
            entry=at+16+number*8;ident,child=u32(entry),u32(entry+4)
            if not path and ident!=24:continue
            names=(*path,ident)
            if child&0x80000000:yield from walk(child&0x7fffffff,names)
            else:
                if child+16>resource_size:raise RuntimeError('Invalid PE manifest entry')
                descriptor=base+child;start,length=offset(u32(descriptor)),u32(descriptor+4)
                if start+length>len(data):raise RuntimeError('Truncated PE manifest')
                yield data[start:start+length]
    for payload in walk(0):
        try:manifest=ET.fromstring(payload.rstrip(b'\0'))
        except ET.ParseError:continue
        if any(element.tag.rsplit('}',1)[-1]=='requestedExecutionLevel' and element.get('level')=='asInvoker' for element in manifest.iter()):return True
    return False

def files_for(stage):
    files=set(update.REQUIRED_FILES)
    files.update(str(p.relative_to(stage)).replace('\\','/') for p in (stage/'resources/tools-ui').rglob('*') if p.is_file())
    if not all(update.program_path(r) for r in files):raise RuntimeError('Unsupported program payload path')
    if not all((stage/r).is_file() for r in files):raise RuntimeError('Missing required update files')
    return sorted(files)

def inventory(stage):
    return {str(p.relative_to(stage)):digest(p) for p in sorted(stage.rglob('*')) if p.is_file()}

def payload_for(stage):
    return {'version':update.PATCH_VERSION,'extension_key':update.EXPECTED_KEY,
            'files':{r:{'sha256':digest(stage/r),'bytes':(stage/r).stat().st_size} for r in files_for(stage)},
            'unchanged_files':{r:digest(stage/r) for r in update.UNCHANGED_FILES}}

def selftests():
    def fixture(folder,version='4.0.0'):
        folder.mkdir(parents=True)
        pe=bytearray(512);pe[:2]=b'MZ';struct.pack_into('<I',pe,0x3c,128);pe[128:132]=b'PE\0\0'
        struct.pack_into('<H',pe,132,0x8664);struct.pack_into('<H',pe,152,0x20b);struct.pack_into('<H',pe,220,2)
        for r in update.REQUIRED_FILES|set(update.UNCHANGED_FILES)|{'resources/tools-ui/assets/app-new.js'}:
            p=folder/r;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('fixture '+r).encode())
        (folder/'GalaxyControl.exe').write_bytes(pe)
        (folder/'tools/engine/agent/common.py').write_text('VERSION = '+repr(version)+'\n')
        (folder/'tools/browser-extension/manifest.json').write_text(json.dumps({'manifest_version':3,'key':update.EXPECTED_KEY,'version':version}))
    passed=[]
    with tempfile.TemporaryDirectory(prefix='core-update-test-',dir=HERE) as directory:
        base=Path(directory);app=base/'원래 앱';new=base/'payload'
        fixture(app);fixture(new,'4.2.1');(new/'update-payload.json').write_text(json.dumps(payload_for(new)))
        files=files_for(new);old={r:digest(app/r) for r in files}
        preserved={r:digest(app/r) for r in update.UNCHANGED_FILES}
        user=app/'user-results/sample.png';user.parent.mkdir();user.write_bytes(b'preserve user result')
        # New program module/assets must be supported without changing runtime.
        (app/'tools/engine/agent/phone.py').unlink()
        (app/'resources/tools-ui/assets/app-new.js').unlink()
        result=update.apply_update(app,new)
        assert result['replaced']==len(files)
        assert all(digest(app/r)==digest(new/r) for r in files)
        assert all(digest(app/r)==value for r,value in preserved.items())
        assert user.read_bytes()==b'preserve user result'
        assert (app/update.BACKUP_RELATIVE/'tools/engine/agent/common.py').read_text()=="VERSION = '4.0.0'\n"
        passed.append('Native/app/agent/UI update, new phone module and assets; runtime/user results preserved')
        update.apply_update(app,new)
        assert (app/update.BACKUP_RELATIVE/'tools/engine/agent/common.py').read_text()=="VERSION = '4.0.0'\n"
        passed.append('Reapplication preserves first 4.0 program backup')
        previous=base/'previous-4.1';fixture(previous,'4.1.0')
        update.apply_update(previous,new)
        assert all(digest(previous/r)==digest(new/r) for r in files)
        assert (previous/update.BACKUP_RELATIVE/'tools/engine/agent/common.py').read_text()=="VERSION = '4.1.0'\n"
        passed.append('4.1 program update creates a recoverable 4.1 source backup')
        fault=base/'fault';fixture(fault);before={r:digest(fault/r) for r in files};calls=0
        def fault_copy(source,destination):
            nonlocal calls
            calls+=1;update.atomic_copy(source,destination)
            if calls==3:raise OSError('write then raise fixture')
        try:update.apply_update(fault,new,fault_copy)
        except OSError:pass
        else:raise AssertionError('Expected injected filesystem failure')
        assert all(digest(fault/r)==h for r,h in before.items())
        passed.append('Write-then-raise failure rolls back every original including native EXE')
        runtime=app/update.UNCHANGED_FILES[0];prior=runtime.read_bytes();runtime.write_bytes(b'different runtime')
        before={r:digest(app/r) for r in files}
        try:update.apply_update(app,new)
        except update.UpdateError as e:assert str(e)=='unsupportedRuntime'
        else:raise AssertionError('Different runtime accepted')
        assert all(digest(app/r)==h for r,h in before.items());runtime.write_bytes(prior)
        passed.append('Unsupported runtime rejected before replacing program files')
        linked=base/'linked';fixture(linked);outside=base/'outside';outside.write_text('unchanged')
        dest=linked/'tools/engine/agent/server.py';dest.unlink();dest.symlink_to(outside)
        try:update.apply_update(linked,new)
        except update.UpdateError as e:assert str(e)=='linkedTarget'
        else:raise AssertionError('Linked target accepted')
        assert outside.read_text()=='unchanged'
        passed.append('Linked target rejected without touching outside file')
        meta=new/'update-payload.json';valid=meta.read_bytes();obj=json.loads(valid)
        obj['files']['tools/python/python.exe']={'sha256':'0'*64,'bytes':0};meta.write_text(json.dumps(obj))
        try:update.apply_update(app,new)
        except update.UpdateError as e:assert str(e)=='invalidPayload'
        else:raise AssertionError('Runtime overwrite accepted')
        meta.write_bytes(valid)
        assert not any(update.program_path(p) for p in ['../GalaxyControl.exe','/GalaxyControl.exe','resources/tools-ui/../secret','tools/python/python.exe','resources/tools-ui/a\".js','resources/tools-ui/a\n.js','tools/engine/agent/settings.json'])
        passed.append('Only sealed program allowlist accepted; runtime/config/traversal injection rejected')
        damaged=new/'resources/tools-ui/index.html';damaged.write_text('corrupt')
        before={r:digest(app/r) for r in files}
        try:update.apply_update(app,new)
        except update.UpdateError as e:assert str(e)=='payloadMismatch'
        else:raise AssertionError('Corrupt payload accepted')
        assert all(digest(app/r)==h for r,h in before.items())
        passed.append('Tampered payload rejected before any target write')
    return passed

def nsis_quote(value):return str(value).replace('$','$$').replace('"','$\\"')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',type=Path);parser.add_argument('--frozen',action='store_true');parser.add_argument('--source-sha256');parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:print(json.dumps({'fixture_tests':selftests(),'actual_windows_runtime_executed':False},ensure_ascii=False));return
    if not args.stage or not args.frozen or not args.source_sha256:parser.error('Use --stage ABS --frozen --source-sha256 ROOT_FROZEN_HASH')
    stage=args.stage.resolve(strict=True);update.validate_installation(stage)
    native=json.loads((ROOT/'work/windows/unified-validation.json').read_text())
    if native['version']!='4.2.1' or digest(stage/'GalaxyControl.exe')!=native['sha256']:raise RuntimeError('Unvalidated native 4.2 app')
    source=stage/'tools/source/GalaxyControl-source.zip'
    if digest(source)!=args.source_sha256:raise RuntimeError('Unexpected frozen corresponding-source archive')
    with zipfile.ZipFile(source) as z:
        for name,path in {'windows/CoreUpdate.py':HELPER,'windows/GalaxyControlUpdate.nsi':ROOT/'work/windows/GalaxyControlUpdate.nsi','nsis/build_core_update.py':Path(__file__).resolve()}.items():
            if z.read(name)!=path.read_bytes():raise RuntimeError('Stale installer corresponding source: '+name)
        source_entries=len(z.infolist())
    before=inventory(stage);payload=payload_for(stage);manifest=HERE/'core-update-payload.json';manifest.write_text(json.dumps(payload,indent=2)+'\n')
    include=HERE/'core-update-payload.nsh';commands=[]
    for r in payload['files']:
        parent=str(Path(r).parent).replace('/','\\')
        commands+=['SetOutPath "$PLUGINSDIR\\payload'+('\\'+parent if parent!='.' else '')+'"','File "'+nsis_quote(stage/r)+'"']
    include.write_text('\n'.join(commands)+'\n');tests=selftests()
    command=[str(HERE/'nsis-3.13/makensis'),'-NOCD','-V3','-DGALAXY_PACKAGE='+str(stage),'-DUPDATE_MANIFEST='+str(manifest),'-DCORE_PAYLOAD_INCLUDE='+str(include),str(ROOT/'work/windows/GalaxyControlUpdate.nsi')]
    started=time.time()
    with (HERE/'core-update-build.log').open('w') as log:
        result=subprocess.run(command,cwd=HERE,env=dict(os.environ,NSISDIR=str(HERE/'nsis-3.13')),stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('NSIS failed; see core-update-build.log')
    installer=HERE/'GalaxyControl-Update.exe'
    if not installer.is_file() or not 100_000<installer.stat().st_size<100_000_000:raise RuntimeError('Update missing or exceeds connector 100 MB limit')
    if inventory(stage)!=before:raise RuntimeError('Stage changed while building; discard output')
    extract=HERE/'core-update-extracted'
    if extract.exists():shutil.rmtree(extract)
    extract.mkdir()
    with (HERE/'core-update-extract.log').open('w') as log:
        result=subprocess.run([str(ROOT/'work/vc-runtime/tools/7zip/7zz'),'x','-y','-o'+str(extract),str(installer)],stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Updater extraction failed')
    roots=[p.parent for p in extract.rglob('update-payload.json') if digest(p)==digest(manifest)]
    if len(roots)!=1:raise RuntimeError('Missing/ambiguous extracted payload')
    for r,item in payload['files'].items():
        if digest(roots[0]/r)!=item['sha256']:raise RuntimeError('Extracted payload hash mismatch '+r)
    helpers=[p for p in extract.rglob('CoreUpdate.py') if digest(p)==digest(HELPER)]
    if len(helpers)!=1:raise RuntimeError('Extracted helper mismatch')
    data=installer.read_bytes();at=struct.unpack_from('<I',data,0x3c)[0]
    if data[:2]!=b'MZ' or data[at:at+4]!=b'PE\0\0' or struct.unpack_from('<H',data,at+24+68)[0]!=2:raise RuntimeError('Not a PE GUI installer')
    if not manifest_as_invoker(data):raise RuntimeError('No per-user manifest')
    report={'version':'4.2.1','installer':str(installer),'bytes':len(data),'sha256':digest(installer),'payload_file_count':len(payload['files']),'payload_hash_mismatches':0,'stage_changed_during_build':False,'corresponding_source_sha256':args.source_sha256,'source_snapshot_entries':source_entries,'native_app_sha256':native['sha256'],'per_user_manifest':'asInvoker','languages':['ko','en','vi','ja','zh'],'backup_location':update.BACKUP_RELATIVE,'native_written':True,'runtime_written':False,'private_settings_written':False,'existing_extension_identity_preserved':True,'fixture_tests':tests,'elapsed_seconds':round(time.time()-started,2),'actual_windows_runtime_executed':False,'runtime_limit':'Real NSIS compiled and extracted on macOS; every payload hash and synthetic file rollback fixture verified. Windows installer UI, registry/mutex APIs and Windows Python/app execution were not tested.','signature':'Unsigned','commands':command,'files':payload['files'],'unchanged_files':payload['unchanged_files'],'helper_sha256':digest(HELPER),'script_sha256':digest(ROOT/'work/windows/GalaxyControlUpdate.nsi'),'build_script_sha256':digest(Path(__file__).resolve())}
    (HERE/'core-update-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()

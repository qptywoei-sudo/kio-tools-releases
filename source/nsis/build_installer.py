"""Build an actual NSIS installer only from an explicitly frozen portable stage.
No Windows executable is run. Native makensis and native 7-Zip are local tools.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,struct,subprocess,time
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while True:
   data=f.read(1024*1024)
   if not data:break
   h.update(data)
 return h.hexdigest()

def inventory(stage):
 files=[stage/'GalaxyControl.exe']
 for name in ('tools','resources'):
  files.extend(sorted(p for p in (stage/name).rglob('*') if p.is_file()))
 return {str(p.relative_to(stage)):digest(p) for p in files}

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--stage',required=True,type=Path)
 parser.add_argument('--frozen',action='store_true',required=True)
 args=parser.parse_args();stage=args.stage.resolve()
 required=['GalaxyControl.exe','tools/python/python.exe','tools/python/msvcp140.dll','tools/python/msvcp140_1.dll','tools/engine/agent/server.py','tools/engine/agent/phone.py','tools/engine/agent/process_group.py','tools/engine/deps-agent/win64/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe','tools/webview2/WebView2Loader.dll','resources/tools-ui/index.html','tools/licenses/NSIS-COPYING.txt','tools/source/nsis-3.13-src.tar.bz2']
 missing=[s for s in required if not (stage/s).is_file()]
 if missing:raise RuntimeError('Frozen stage missing required files: '+str(missing))
 manifest=json.loads((ROOT/'work/windows/unified-validation.json').read_text())
 if digest(stage/'GalaxyControl.exe')!=manifest['sha256']:raise RuntimeError('Stage native application differs from frozen build')
 ffmpeg=stage/'tools/engine/deps-agent/win64/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
 expected_ffmpeg=json.loads((ROOT/'work/ffmpeg-lgpl/release-validation.json').read_text())['binaries']['win64']['sha256']
 if digest(ffmpeg)!=expected_ffmpeg:raise RuntimeError('Stage FFmpeg differs from validated LGPL-only build')
 for name in ('msvcp140.dll','msvcp140_1.dll'):
  if digest(stage/'tools/python'/name)!=digest(ROOT/'work/vc-runtime/app-local'/name):raise RuntimeError('Stage VC runtime differs from official prepared payload: '+name)
 before=inventory(stage);(HERE/'installer-inputs.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
 env=dict(os.environ,NSISDIR=str(HERE/'nsis-3.13'))
 command=[str(HERE/'nsis-3.13/makensis'),'-NOCD','-V3','-DGALAXY_PACKAGE='+str(stage),str(ROOT/'work/windows/Installer.nsi')]
 output=HERE/'GalaxyControl-Setup.exe';log=HERE/'installer-build.log';start=time.time()
 with log.open('w') as f:
  run=subprocess.run(command,cwd=HERE,env=env,stdout=f,stderr=subprocess.STDOUT)
 if run.returncode:raise RuntimeError('NSIS build failed; see '+str(log))
 if not output.is_file() or output.stat().st_size<1_000_000:raise RuntimeError('No real installer payload was created')
 after=inventory(stage)
 if before!=after:raise RuntimeError('Stage changed during compilation; rebuild after freezing')
 extract=HERE/'installer-extracted'
 if extract.exists():shutil.rmtree(extract)
 extract.mkdir()
 with (HERE/'installer-extract.log').open('w') as f:
  run=subprocess.run([str(ROOT/'work/vc-runtime/tools/7zip/7zz'),'x','-y','-o'+str(extract),str(output)],stdout=f,stderr=subprocess.STDOUT)
 if run.returncode:raise RuntimeError('Installer extraction failed')
 roots=[p.parent for p in extract.rglob('GalaxyControl.exe') if (p.parent/'tools/python/python.exe').is_file() and (p.parent/'resources/tools-ui/index.html').is_file()]
 if len(roots)!=1:raise RuntimeError('Installer payload root is missing or ambiguous: '+str(roots))
 payload_root=roots[0]
 errors=[]
 for relative,expected in before.items():
  p=payload_root/relative
  if not p.is_file():errors.append({'file':relative,'error':'missing'})
  elif digest(p)!=expected:errors.append({'file':relative,'error':'hash mismatch'})
 if errors:
  (HERE/'installer-payload-errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n')
  raise RuntimeError('Installer payload differs from portable stage: '+str(len(errors))+' files')
 data=output.read_bytes();at=struct.unpack_from('<I',data,0x3c)[0];assert data[:2]==b'MZ' and data[at:at+4]==b'PE\0\0';machine=struct.unpack_from('<H',data,at+4)[0];subsystem=struct.unpack_from('<H',data,at+24+68)[0]
 report={'version':'4.2.1','installer':str(output.relative_to(ROOT)),'bytes':len(data),'sha256':digest(output),'NSIS':'3.13 native macOS compiler + matching official Windows Unicode stubs','PE_machine':hex(machine),'subsystem':subsystem,'payload_architecture':'Windows x64 application; NSIS x86 Unicode bootstrapper','stage':str(stage),'payload_file_count':len(before),'extracted_payload_root':str(payload_root.relative_to(extract)),'payload_hash_mismatches':0,'stage_changed_during_build':False,'elapsed_seconds':round(time.time()-start,2),'script_sha256':digest(ROOT/'work/windows/Installer.nsi'),'native_app_sha256':manifest['sha256'],'FFmpeg_LGPL_sha256':expected_ffmpeg,'test':'Installer actually compiled; extracted with native 7-Zip and every included payload file hash matched the frozen input. No installer or Windows program was executed.','runtime_limit':'Installation, upgrade/uninstall, Windows policy and runtime behavior were not tested on this macOS host.','signature':'Unsigned installer; no signing key was used.','scope':'Per-user application folder and Start Menu/HKCU uninstaller entry; desktop shortcut and login autostart selected by default, with installer choices and app settings to disable them. Existing disabled login startup is preserved on updates. User pictures/results/private settings are not removed by uninstall.','commands':command}
 (HERE/'installer-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()

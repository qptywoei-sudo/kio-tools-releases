"""Only this program's persistent ADB may be stopped for a Windows update."""
import json,os,sys,subprocess,tempfile,shutil,time,unittest,hashlib,io,threading,base64,zipfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'agent'),str(root/'engine/deps-agent/win64')]
from update_helper import close_owned_windows_tools,restore_program,replace_program,main
from updater import Updater
from common import atomic_json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
class OwnedToolTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 @unittest.skipUnless(os.name=='nt' and os.environ.get('KIO_LOCK_FIXTURE'),'Windows lock fixture executable needed')
 def test_real_adb_directory_lock_is_released_without_stopping_other_adb(self):
  owned=self.root/'installed';other=self.root/'unrelated';processes=[]
  try:
   for folder in (owned,other):
    tools=folder/'tools/scrcpy';tools.mkdir(parents=True);shutil.copy2(os.environ['KIO_LOCK_FIXTURE'],tools/'adb.exe');processes.append(subprocess.Popen([str(tools/'adb.exe')],cwd=tools,creationflags=subprocess.CREATE_NO_WINDOW))
   time.sleep(.2)
   with self.assertRaises(OSError):owned.rename(self.root/'probe')
   self.assertEqual(close_owned_windows_tools(owned),[processes[0].pid]);processes[0].wait(timeout=5);self.assertIsNone(processes[1].poll())
   owned.rename(self.root/'renamed')
  finally:
   for process in processes:
    if process.poll() is None:process.terminate();process.wait(timeout=5)
 def test_restore_previous_program_keeps_user_files_created_or_changed_after_install(self):
  old=self.root/'installed';stage=self.root/'staged';old.mkdir();stage.mkdir();(old/'KIOControl.exe').write_text('old');(stage/'KIOControl.exe').write_text('new');(old/'notes').write_text('before')
  backup=replace_program(stage,old,'Windows');(old/'notes').write_text('after');(old/'new-user-file').write_text('keep')
  failed=restore_program(old,backup,'Windows');self.assertEqual((old/'KIOControl.exe').read_text(),'old');self.assertEqual((old/'notes').read_text(),'after');self.assertEqual((old/'new-user-file').read_text(),'keep');self.assertEqual((Path(failed)/'KIOControl.exe').read_text(),'new')
 def fixture_plan(self):
  old=self.root/'installed';old.mkdir();(old/'KIOControl.exe').write_bytes(b'old')
  archive=self.root/'release.zip'
  with zipfile.ZipFile(archive,'w') as z:
   z.writestr('KIO-Control-Windows/KIOControl.exe',b'new');z.writestr('KIO-Control-Windows/tools/engine/agent/common.py',b'VERSION="99.0.0"');z.writestr('KIO-Control-Windows/fixture-padding',b'x'*1200)
  key=Ed25519PrivateKey.generate();public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
  package={'root':'KIO-Control-Windows','url':'https://drive.google.com/uc?export=download&id=fixture','size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
  payload={'format':1,'product':'kio-control','version':'99.0.0','notes':[],'packages':{'Windows':package,'Mac':{**package,'root':'KIO-Control-Mac'}}};envelope={'payload':payload,'signature':base64.b64encode(key.sign(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())).decode()}
  receipt=self.root/'receipt.json';atomic_json(self.root/'plan.json',{'target':str(old),'receipt':str(receipt),'pids':[],'version':'99.0.0','platform':'Windows','archive':str(archive),'publicKey':public,'envelope':envelope})
  return old,receipt
 def test_failed_replacement_records_stage_and_reopens_existing_program(self):
  old,receipt=self.fixture_plan()
  with patch('update_helper.close_owned_windows_tools',return_value=[]),patch('update_helper.replace_program',side_effect=PermissionError(13,'busy')),patch('update_helper.launch_program') as launch:main(self.root/'plan.json')
  launch.assert_called_once_with(str(old),'Windows');value=json.loads(receipt.read_text(encoding='utf-8'));self.assertEqual(value['phase'],'failed');self.assertEqual(value['failedStage'],'installing');self.assertTrue(value['reopened']);self.assertEqual((old/'KIOControl.exe').read_bytes(),b'old')
 def test_startup_failure_restores_previous_binary_and_reopens_it(self):
  old,receipt=self.fixture_plan()
  with patch('update_helper.close_owned_windows_tools',return_value=[]),patch('update_helper.launch_program',return_value=SimpleNamespace(poll=lambda:0)) as launch,patch('update_helper.wait_for_started_app',side_effect=ValueError('updateRestartFailed')):main(self.root/'plan.json')
  value=json.loads(receipt.read_text(encoding='utf-8'));self.assertEqual(value['failedStage'],'restartingApp');self.assertTrue(value['restored']);self.assertTrue(value['reopened']);self.assertEqual(launch.call_count,2);self.assertEqual((old/'KIOControl.exe').read_bytes(),b'old')
 def test_verified_download_is_reused_but_corrupted_cache_is_not(self):
  old,receipt=self.fixture_plan();plan=json.loads((self.root/'plan.json').read_text(encoding='utf-8'))
  folder=self.root/'download-fixture';folder.mkdir();cached=folder/'release.zip';shutil.copyfile(plan['archive'],cached)
  agent=SimpleNamespace(state=self.root,stopping=threading.Event(),jobs={},ai=SimpleNamespace(active=None),health=lambda:{})
  updater=Updater(agent);updater.root=self.root;updater.config={'feedUrl':'https://drive.google.com/uc?export=download&id=fixture','publicKey':plan['publicKey']}
  with patch('updater.download_response',return_value=io.BytesIO(json.dumps(plan['envelope']).encode())):updater._run('check')
  self.assertEqual(updater.value['phase'],'ready');self.assertEqual(updater.archive,cached)
  data=bytearray(cached.read_bytes());data[0]^=1;cached.write_bytes(data);updater.archive=None
  with patch('updater.download_response',return_value=io.BytesIO(json.dumps(plan['envelope']).encode())):updater._run('check')
  self.assertEqual(updater.value['phase'],'available');self.assertIsNone(updater.archive)
if __name__=='__main__':unittest.main()

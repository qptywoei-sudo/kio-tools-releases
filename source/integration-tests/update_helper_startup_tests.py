"""Installer startup contracts: Unicode plans and no quit before readiness."""
import json,locale,os,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'agent'),str(root/'engine/deps-agent/win64')]
from common import atomic_json,AgentError
from updater import Updater,wait_helper_ready
from update_helper import alive

class InstallerStartupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.receipt=self.root/'receipt.json'
 def tearDown(self):self.temp.cleanup()
 def test_dead_installer_never_authorizes_app_exit(self):
  process=SimpleNamespace(pid=123,poll=lambda:1)
  atomic_json(self.receipt,{'phase':'waitingForExit','helperId':'current','version':'4.4.7','pid':123})
  with self.assertRaisesRegex(ValueError,'updateInstallFailed'):wait_helper_ready(process,self.receipt,'current','4.4.7',.01)
 def test_stale_installer_receipt_never_authorizes_exit(self):
  process=SimpleNamespace(pid=123,poll=lambda:None)
  for mismatch in ({'helperId':'old'},{'pid':122},{'version':'4.4.6'},{'phase':'failed'}):
   atomic_json(self.receipt,{'phase':'waitingForExit','helperId':'current','version':'4.4.7','pid':123,**mismatch})
   with self.assertRaisesRegex(ValueError,'updateInstallFailed'):wait_helper_ready(process,self.receipt,'current','4.4.7',.01)
 def test_matching_live_installer_authorizes_exit(self):
  process=SimpleNamespace(pid=123,poll=lambda:None)
  atomic_json(self.receipt,{'phase':'waitingForExit','helperId':'current','version':'4.4.7','pid':123})
  wait_helper_ready(process,self.receipt,'current','4.4.7',.01)
 @unittest.skipUnless(os.name=='nt','Windows process-handle lifetime contract')
 def test_exited_process_with_retained_handle_does_not_block_installer(self):
  process=subprocess.Popen([sys.executable,'-c','pass'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  process.wait(timeout=5)
  self.assertFalse(alive(process.pid))
 def test_actual_isolated_helper_reads_korean_plan_before_waiting(self):
  helper=self.root/'설치 준비';helper.mkdir();script=helper/'update_helper.py';script.write_bytes((root/'agent/update_helper.py').read_bytes())
  plan=helper/'plan.json';atomic_json(plan,{'receipt':str(self.receipt),'version':'4.4.7','target':str(self.root/'내 드라이브/키오'),'pids':[os.getpid()]})
  process=subprocess.Popen([sys.executable,'-I','-B','-X','utf8=0',str(script),str(plan)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  try:
   wait_helper_ready(process,self.receipt,helper.name,'4.4.7',5)
   value=json.loads(self.receipt.read_text(encoding='utf-8'));self.assertEqual(value['helperId'],'설치 준비');self.assertEqual(value['phase'],'waitingForExit')
  finally:
   process.terminate();process.wait(timeout=5);process.stderr.close()
 def test_failed_helper_start_keeps_current_app_running(self):
  agent=SimpleNamespace(state=self.root,stopping=threading.Event(),jobs={},ai=SimpleNamespace(active=None),health=lambda:{},bridge=SimpleNamespace(call=lambda *a:None))
  updater=Updater(agent);updater.value.update(phase='ready',latestVersion='4.4.7');updater.archive=self.root/'release.zip'
  atomic_json(self.root/'bridge/status.json',{'pid':os.getpid()})
  runtime=self.root/'runtime';runtime.mkdir();(runtime/'python.exe').write_bytes(b'fixture')
  process=SimpleNamespace(pid=123,poll=lambda:1)
  target=self.root/'KIO 컨트롤.app';target.mkdir()
  with patch('updater.install_layout',return_value=(target,runtime,'win64')),patch('updater.subprocess.Popen',return_value=process) as launch,patch.object(updater,'_quit') as quit_:
   with self.assertRaisesRegex(AgentError,'updateInstallFailed'):updater.install()
   quit_.assert_not_called()
   self.assertEqual(launch.call_args.kwargs['cwd'].parent,updater.root)
   self.assertNotEqual(launch.call_args.kwargs['cwd'],self.root)
  self.assertEqual(updater.status()['phase'],'error');self.assertEqual(json.loads(updater.receipt.read_text(encoding='utf-8'))['phase'],'failed')

if __name__=='__main__':unittest.main()

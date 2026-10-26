"""Startup transport uses native confirmed state, not stale settings JSON; no real user registry."""
from pathlib import Path
from types import SimpleNamespace
import json,sys,tempfile,threading,unittest
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'agent'),str(root/'engine')]
from server import Agent
from common import AgentError

class StartupSettingsTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory();self.agent=object.__new__(Agent)
    self.agent.settings={'autoStart':False,'saveFolder':self.temp.name,'captureFormat':'png','shortcuts':{'areaCapture':'Control+Shift+A'}}
    self.agent.settings_path=Path(self.temp.name)/'settings.json';self.agent.lock=threading.RLock();self.events=[];self.calls=[]
    self.native={'autoStart':True,'autoStartStatus':'blocked'}
    self.agent.emit=lambda event:self.events.append(event)
    def apply(operation,body):
        self.calls.append((operation,body));self.native={'autoStart':body.get('autoStart',self.native['autoStart']),'autoStartStatus':'enabled' if body.get('autoStart',self.native['autoStart']) else 'disabled'}
        return {'applied':True,'settings':dict(self.native)}
    self.agent.bridge=SimpleNamespace(ready=lambda:True,status=lambda:{'settings':dict(self.native)},call=apply)
 def tearDown(self):self.temp.cleanup()
 def test_get_uses_native_requested_choice_and_reports_windows_block(self):
    public=self.agent.public_settings();self.assertTrue(public['autoStart']);self.assertEqual(public['autoStartStatus'],'blocked');self.assertNotIn('saveFolder',public)
 def test_explicit_enable_returns_confirmed_state_without_waiting_for_heartbeat(self):
    saved=self.agent.apply_settings({'autoStart':True})['settings']
    self.assertTrue(saved['autoStart']);self.assertEqual(saved['autoStartStatus'],'enabled');self.assertEqual(self.calls,[('settings.apply',{'autoStart':True})])
    self.assertTrue(json.loads(self.agent.settings_path.read_text())['autoStart']);self.assertEqual(saved['shortcuts']['areaCapture'],'Control+Shift+A')
 def test_capture_settings_do_not_resubmit_startup_choice(self):
    self.agent.apply_settings({'captureFormat':'jpg'});self.assertEqual(self.calls,[('settings.apply',{'captureFormat':'jpg'})])
 def test_native_failure_preserves_saved_choice_and_does_not_emit_success(self):
    def fail(*args):raise AgentError('settingsFailed')
    self.agent.bridge.call=fail
    with self.assertRaises(AgentError):self.agent.apply_settings({'autoStart':True})
    self.assertFalse(self.agent.settings['autoStart']);self.assertFalse(self.agent.settings_path.exists());self.assertEqual(self.events,[])
 def test_off_is_confirmed_and_invalid_native_status_is_ignored(self):
    saved=self.agent.apply_settings({'autoStart':False})['settings'];self.assertFalse(saved['autoStart']);self.assertEqual(saved['autoStartStatus'],'disabled')
    self.assertEqual(Agent.startup_snapshot({'autoStart':'yes','autoStartStatus':'surprise'}),{})
    self.assertEqual(Agent.startup_snapshot(None),{})

if __name__=='__main__':unittest.main()

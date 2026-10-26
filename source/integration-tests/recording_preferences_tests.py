import sys,unittest,tempfile,threading,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'agent'),str(root/'engine')]
from server import Agent
from common import AgentError

class RecordingPreferencesTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.settings_path=Path(self.temp.name)/'settings.json'
  self.bridge=SimpleNamespace(call=Mock())
  self.subject=SimpleNamespace(settings={'language':'ko','shortcuts':{'areaCapture':'Control+Shift+F9'}},settings_path=self.settings_path,lock=threading.RLock(),bridge=self.bridge,emit=Mock())
  self.subject.public_settings=lambda:self.subject.settings.copy()
 def tearDown(self):self.temp.cleanup()
 def test_monitor_choice_persists_without_native_settings_side_effects(self):
  pref={'mode':'full','monitor':2,'monitorName':'DISPLAY3'}
  Agent.apply_settings(self.subject,{'recording':pref})
  self.assertEqual(json.loads(self.settings_path.read_text())['recording'],pref)
  self.assertEqual(self.subject.settings['shortcuts']['areaCapture'],'Control+Shift+F9')
  self.bridge.call.assert_not_called()
 def test_invalid_monitor_settings_are_rejected(self):
  for pref in ({'mode':'all'},{'mode':'full','monitor':-1},{'mode':'full','monitor':True},{'mode':'full','monitorName':'a\0b'},{'mode':'area','command':'run'}):
   with self.subTest(pref=pref),self.assertRaises(AgentError):Agent.apply_settings(self.subject,{'recording':pref})
 def test_area_shortcut_reaches_native_and_keeps_existing_bindings(self):
  Agent.apply_settings(self.subject,{'shortcuts':{'recordArea':'Control+Shift+R'}})
  self.bridge.call.assert_called_once_with('settings.apply',{'shortcuts':{'recordArea':'Control+Shift+R'}})
  self.assertEqual(self.subject.settings['shortcuts']['areaCapture'],'Control+Shift+F9')

if __name__=='__main__':unittest.main()

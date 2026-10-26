"""Real local HTTP contracts; storage/native services are isolated fixtures."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import desktop_session_tests as fixture

class RetiredAIFeatureTests(unittest.TestCase):
 setUp=fixture.DesktopSessionTests.setUp
 tearDown=fixture.DesktopSessionTests.tearDown
 start=fixture.DesktopSessionTests.start
 request=fixture.DesktopSessionTests.request
 def test_removed_import_and_photo_routes_are_unavailable(self):
  s=self.start()
  self.assertEqual(self.request('POST','/ai/import',{'id':'old'},token=s['token'])[0],404)
  for action in ('logo','removeBackground','removePeople','excel'):
   self.assertEqual(self.request('POST','/ai/creative',{'action':action,'scanId':'old'},token=s['token'])[0],404)
 def test_retired_assets_and_export_routes_are_unavailable(self):
  s=self.start()
  self.assertEqual(self.request('GET','/ai/assets/test',token=s['token'])[0],404)
  self.assertEqual(self.request('POST','/ai/export',{'id':'test'},token=s['token'])[0],404)
 def test_native_hotkey_failure_does_not_publish_new_foreground_key(self):
  from common import AgentError
  s=self.start();before=dict(self.agent.settings)
  self.agent.bridge.call=lambda *args:(_ for _ in ()).throw(AgentError('shortcutConflict'))
  status,_,_=self.request('PATCH','/settings',{'shortcuts':{'aiTranslate':'Control+Shift+S'}},token=s['token'])
  self.assertEqual(status,400);self.assertEqual(self.agent.settings,before)

if __name__=='__main__':unittest.main()

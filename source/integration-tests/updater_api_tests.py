"""Desktop authentication and update API contracts over an actual local server."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import desktop_session_tests as fixture
class UpdateAPITests(unittest.TestCase):
 setUp=fixture.DesktopSessionTests.setUp
 tearDown=fixture.DesktopSessionTests.tearDown
 start=fixture.DesktopSessionTests.start
 request=fixture.DesktopSessionTests.request
 def test_native_desktop_can_check_preferences_and_invalid_install_is_rejected(self):
  session=self.start();token=session['token']
  code,data,_=self.request('GET','/updates/status',token=token);self.assertEqual(code,200);self.assertIn('currentVersion',json.loads(data))
  code,data,_=self.request('POST','/updates/preferences',{'autoCheck':False},token=token);self.assertEqual(code,200);self.assertFalse(json.loads(data)['autoCheck'])
  code,data,_=self.request('POST','/updates/install',{},token=token);self.assertEqual(json.loads(data)['errorCode'],'updateNotReady');self.assertNotEqual(code,200)
  code,_,_=self.request('POST','/updates/check',{'url':'https://evil.test'},token=token);self.assertNotEqual(code,200)
 def test_unauthenticated_requests_cannot_operate_updates(self):
  self.start()
  for method,path,body in [('GET','/updates/status',None),('POST','/updates/check',{}),('POST','/updates/download',{}),('POST','/updates/install',{})]:
   code,_,_=self.request(method,path,body);self.assertIn(code,(401,403))
if __name__=='__main__':unittest.main()

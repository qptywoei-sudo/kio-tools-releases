"""Actual locking/timing with a deliberately stalled fixture cloud, never real tokens."""
import sys,time,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'agent'),str(ROOT/'engine'),str(ROOT/'integration-tests')]
from common import AgentError
from kio_account import KIOAccount
from kio_account_tests import USER,MemoryVault

class AccountLatencyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.now=time.time();self.entered=threading.Event();self.release=threading.Event();self.calls=[]
  def cloud(route,body,headers,method):
   self.calls.append(route);self.entered.set();self.release.wait(3)
   return {'credential':'synthetic-rotation'+'x'*50,'user':USER,'expires':self.now+3600,'drive':{'connected':True}}
  self.account=KIOAccount(self.tmp.name,store=MemoryVault(),transport=cloud,clock=lambda:self.now)
  self.account._accept({'credential':'synthetic-initial'+'x'*50,'user':USER,'expires':self.now+3600})
 def tearDown(self):self.release.set();self.account.close();self.tmp.cleanup()
 def test_cloud_io_cannot_delay_signed_in_status_or_local_identity(self):
  thread=threading.Thread(target=lambda:self.account.cloud('/control/drive/status',method='GET'));thread.start();self.assertTrue(self.entered.wait(1))
  start=time.perf_counter()
  for _ in range(100):self.assertTrue(self.account.status()['signedIn']);self.assertEqual(self.account.require()['id'],USER['id'])
  self.assertLess(time.perf_counter()-start,.15)
  self.assertEqual(self.calls,['/control/drive/status'])
  self.release.set();thread.join(2);self.assertFalse(thread.is_alive())
 def test_periodic_refresh_does_not_block_local_work_or_duplicate_requests(self):
  self.now+=301;start=time.perf_counter();self.assertEqual(self.account.require()['id'],USER['id']);self.assertLess(time.perf_counter()-start,.15)
  self.assertTrue(self.entered.wait(1))
  for _ in range(20):self.assertEqual(self.account.require()['id'],USER['id'])
  self.assertEqual(self.calls,['/control/native/session'])
  self.release.set()
  for _ in range(100):
   if not self.account.refresh_gate.locked():break
   time.sleep(.01)
  self.assertFalse(self.account.refresh_gate.locked());self.assertTrue(self.account.status()['signedIn'])
 def test_failed_refresh_preserves_verified_unexpired_login_with_bounded_retry(self):
  self.now+=301
  with patch.object(self.account,'_request',side_effect=AgentError('accountCloudUnavailable',503)) as request:
   self.account.require()
   for _ in range(100):
    if not self.account.refresh_gate.locked():break
    time.sleep(.01)
   for _ in range(20):self.assertEqual(self.account.require()['id'],USER['id'])
   self.assertEqual(request.call_count,1);self.assertTrue(self.account.status()['signedIn'])
 def test_credential_revocation_still_relocks_local_tools(self):
  with patch.object(self.account,'_request',side_effect=AgentError('accountReconnect',401)):
   with self.assertRaisesRegex(AgentError,'accountReconnect'):self.account.require(online=True)
  self.assertFalse(self.account.status()['signedIn'])
  with self.assertRaises(AgentError):self.account.require()
if __name__=='__main__':unittest.main(verbosity=2)

import json,tempfile,threading,unittest,uuid
from pathlib import Path
from server import Agent
from common import AgentError
from kio_account import CLOUD_ORIGIN

class ArtifactHistoryTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.account=str(uuid.uuid4());self.other=str(uuid.uuid4());self.origin='http://127.0.0.1:4323';self.a=self.make({})
 def tearDown(self):self.temp.cleanup()
 def make(self,files):
  a=Agent.__new__(Agent);a.lock=threading.RLock();a.files=files;a.desktop_origin=self.origin;a.require_account=lambda:{'id':self.account};a.private_control_file=lambda p:False;return a
 def add(self,name,kind='artifact',account=None,owner=None,created=1):
  ident=str(uuid.uuid4());p=self.root/name;p.write_bytes(b'fixture');self.a.files[ident]={'path':str(p),'name':name,'kind':kind,'accountId':account or self.account,'owner':owner or self.origin,'created':created};return ident
 def test_restored_registry_keeps_generated_files_but_not_uploads_or_other_accounts(self):
  image=self.add('my.png');video=self.add('video.mp4','recording');self.add('private.png',account=self.other);self.add('other-origin.png',owner='chrome-extension://'+'b'*32);self.add('upload.png','upload');self.add('native.png','native')
  restored=self.make(json.loads(json.dumps(self.a.files)));result=restored.artifact_history(self.origin);self.assertEqual({f['id'] for f in result['files']},{image,video});self.assertNotIn('path',result['files'][0]);self.assertEqual(result['nextCursor'],'')
 def test_pages_to_the_end_without_duplicates(self):
  expected={self.add(str(i)+'.png',created=i) for i in range(107)};first=self.a.artifact_history(self.origin);second=self.a.artifact_history(self.origin,first['nextCursor']);self.assertEqual(len(first['files']),100);self.assertEqual(len(second['files']),7);self.assertEqual(second['nextCursor'],'');self.assertEqual({f['id'] for f in first['files']+second['files']},expected)
 def test_missing_outputs_are_skipped_and_cloud_origin_obeys_existing_owner_policy(self):
  missing=self.add('missing.png');Path(self.a.files[missing]['path']).unlink();valid=self.add('allowed.png',owner=CLOUD_ORIGIN);self.assertEqual([f['id'] for f in self.a.artifact_history(self.origin)['files']],[valid])
 def test_foreign_or_invalid_cursor_never_exposes_metadata(self):
  foreign=self.add('private.png',account=self.other)
  for cursor in [foreign,'../x','unknown']:
   with self.assertRaises(AgentError):self.a.artifact_history(self.origin,cursor)
 def test_signed_out_account_cannot_list_saved_results(self):
  self.a.require_account=lambda:(_ for _ in ()).throw(AgentError('accountRequired',401))
  with self.assertRaises(AgentError):self.a.artifact_history(self.origin)
if __name__=='__main__':unittest.main()

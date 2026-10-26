"""Local HTTP feature routes with disposable files and explicit native approval fixtures.
No real browser capture, physical clipboard, production state or user folders are used.
"""
import sys,unittest,io
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'engine'),str(root/'agent'),str(root/'integration-tests')]
from PIL import Image,ImageDraw
from index import FileIndex
import test_local_system as local_fixture

class FeatureRouteTests(unittest.TestCase):
 def setUp(self):
  self.loop=patch.object(FileIndex,'loop',return_value=None);self.watch=patch.object(FileIndex,'watch',return_value=None);self.loop.start();self.watch.start();self.fixture=local_fixture.APITests();self.fixture.setUp();self.req=self.fixture.req;self.a=self.fixture.a
 def tearDown(self):self.fixture.tearDown();self.loop.stop();self.watch.stop()
 def test_structured_search_and_preview_routes_are_authenticated_and_bounded(self):
  folder=self.fixture.path/'selected';folder.mkdir();source=folder/'search.txt';source.write_text('needle '+('x'*21_000));self.a.index.reconcile(self.a.index.add(folder))
  status,result,_=self.req('POST','/search',{'query':'needle','filters':{'extensions':['txt'],'path':str(folder)}});self.assertEqual(status,200);self.assertEqual(len(result['files']),1);ident=result['files'][0]['id']
  self.assertEqual(self.req('GET',f'/files/{ident}/preview',token=False)[0],401);status,preview,_=self.req('GET',f'/files/{ident}/preview');self.assertEqual(status,200);self.assertEqual(preview['kind'],'text');self.assertTrue(preview['truncated']);self.assertLessEqual(len(preview['text']),20_000);self.assertEqual(Path(preview['path']).resolve(),source.resolve())
  self.assertEqual(self.req('POST','/search',{'query':'','filters':{'dateFrom':'2026-02-30'}})[0],400)
 def test_cancel_endpoint_preserves_indexed_and_original_files(self):
  folder=self.fixture.path/'selected';folder.mkdir();source=folder/'search.txt';source.write_text('needle');ident=self.a.index.add(folder);self.a.index.reconcile(ident)
  self.assertEqual(self.req('POST',f'/roots/{ident}/cancel',{},token=False)[0],401);status,result,_=self.req('POST',f'/roots/{ident}/cancel',{});self.assertEqual(status,200);self.assertEqual(result['status'],'cancelled');self.assertTrue(source.exists());self.assertEqual(len(self.req('POST','/search',{'query':'needle'})[1]['files']),1)
 def test_signature_routes_copy_private_and_keep_owner_aliases_separate(self):
  image=Image.new('RGBA',(100,50),(0,0,0,0));ImageDraw.Draw(image).line([(10,10),(40,40),(90,20)],fill='black',width=3);buffer=io.BytesIO();image.save(buffer,'PNG');data=buffer.getvalue()
  status,upload,_=self.req('POST','/uploads',raw=data,extra={'Content-Type':'image/png','X-File-Name':'drawn.png'});self.assertEqual(status,201);source=self.a.resolve(upload['id'],self.fixture.origin);original=source.read_bytes()
  self.assertEqual(self.req('GET','/signatures',token=False)[0],401);self.assertEqual(self.req('POST','/signatures',{'id':upload['id'],'name':'Reusable'},token=False)[0],401)
  status,saved,_=self.req('POST','/signatures',{'id':upload['id'],'name':'Reusable'});self.assertEqual(status,201);signature=saved['signature'];self.assertEqual(self.req('GET','/signatures')[1]['signatures'][0]['id'],signature['id']);self.assertEqual(source.read_bytes(),original)
  other='chrome-extension://'+'b'*32;self.a.origins.add(other);other_token=self.req('POST','/pair',{'clientName':'Approved mock owner'},origin=other,token=False)[1]['token'];self.assertEqual(self.req('GET','/artifacts/'+signature['id'],origin=other,token=other_token)[0],403)
  status,other_assets,_=self.req('GET','/signatures',origin=other,token=other_token);self.assertEqual(status,200);alias=other_assets['signatures'][0];self.assertNotEqual(alias['id'],signature['id']);self.assertEqual(alias['signatureId'],signature['signatureId']);self.assertEqual(self.req('GET','/artifacts/'+alias['id'],origin=other,token=other_token)[0],200)
 def test_url_validation_keeps_normal_browser_permission_path(self):
  for value in ['file:///etc/hosts','javascript:alert(1)','https://user:pass@example.com','x'*6001]:self.assertEqual(self.req('POST','/browser/capture',{'format':'png','url':value})[0],400)
  # Public and private addresses both require a connected, normally granted extension.
  for value in ['https://example.com/','http://127.0.0.1:8000/']:
   status,result,_=self.req('POST','/browser/capture',{'format':'png','url':value});self.assertEqual(status,409);self.assertEqual(result['errorCode'],'browserRequired')
 def test_existing_extension_target_contract_is_accepted_before_browser_connection(self):
  origin='chrome-extension://'+'a'*32;self.a.origins.add(origin);token=self.req('POST','/pair',{'clientName':'Extension fixture'},origin=origin,token=False)[1]['token']
  self.assertEqual(self.req('POST','/browser/register',{'browser':'Chrome'},origin=origin,token=token)[0],200)
  request={'format':'png','split':False,'captureRequestId':'01111111-1111-4111-8111-111111111111','captureTarget':{'id':1,'windowId':1,'url':'https://example.com/'}}
  status,result,_=self.req('POST','/browser/capture',request,origin=origin,token=token)
  self.assertEqual(status,409);self.assertEqual(result['errorCode'],'browserRequired')
  self.assertEqual(self.req('POST','/browser/capture',request)[0],403)
  self.assertEqual(self.req('POST','/browser/capture',{**request,'captureRequestId':'untrusted'},origin=origin,token=token)[0],400)
  self.assertEqual(self.req('POST','/browser/capture',{**request,'captureTarget':{**request['captureTarget'],'id':True}},origin=origin,token=token)[0],400)
  self.assertEqual(self.req('POST','/browser/capture',{**request,'captureTarget':{**request['captureTarget'],'script':'unapproved'}},origin=origin,token=token)[0],400)

if __name__=='__main__':unittest.main(verbosity=2)

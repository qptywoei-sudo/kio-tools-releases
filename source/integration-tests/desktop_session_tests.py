"""Owned native WebView credential bootstrap with real disposable loopback API.

Native approval is explicitly simulated only for the external pairing tests.
No production credentials, user state, UI or real operating-system permissions.
"""
import hashlib,http.client,io,json,os,queue,socket,stat,sys,tempfile,threading,unittest,uuid
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'engine'),str(root/'agent'),str(root/'integration-tests')]
from common import AgentError,VERSION,atomic_json
from index import FileIndex
from server import Server,DESKTOP_SESSION_FILE,private_desktop_session_write
from kio_fixture import VerifiedAgent as Agent
from test_local_system import ApprovalFixture
from PIL import Image

class DesktopSessionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name).resolve();self.state=self.path/'state';self.ui=self.path/'ui';self.ui.mkdir();(self.ui/'index.html').write_text('<h1>Tools</h1>')
  self.loop=patch.object(FileIndex,'loop',return_value=None);self.watch=patch.object(FileIndex,'watch',return_value=None);self.loop.start();self.watch.start()
  with socket.socket() as connection:connection.bind(('127.0.0.1',0));self.port=connection.getsockname()[1]
  self.agent=None;self.server=None
 def tearDown(self):
  if self.server:self.server.shutdown();self.server.server_close()
  if self.agent:self.agent.close()
  self.loop.stop();self.watch.stop();self.temp.cleanup()
 def start(self):
  self.agent=Agent(self.state,self.ui,self.port);bridge_root=self.agent.bridge.root;self.agent.bridge=ApprovalFixture();self.agent.bridge.root=bridge_root
  self.server=Server(self.agent);threading.Thread(target=self.server.serve_forever,daemon=True).start()
  return json.loads((self.state/DESKTOP_SESSION_FILE).read_text())
 def restart(self,port=None):
  self.server.shutdown();self.server.server_close();self.server=None;self.agent.close();self.agent=None
  if port is not None:self.port=port
  return self.start()
 def request(self,method,path,body=None,origin=None,token=None):
  origin=f'http://127.0.0.1:{self.port}' if origin is None else origin;headers={'Host':f'127.0.0.1:{self.port}','Origin':origin}
  if token:headers['X-Local-Agent-Token']=token
  if body is not None:body=json.dumps(body);headers['Content-Type']='application/json'
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);connection.request(method,path,body,headers);response=connection.getresponse();data=response.read();result=(response.status,data,response.getheader('Access-Control-Allow-Origin'));connection.close();return result
 def test_owned_native_session_is_private_and_authenticates_without_approval(self):
  session=self.start();self.assertEqual(set(session),{'token','origin','deviceId','ownerId','clientName','version'});self.assertRegex(session['token'],r'^[A-Za-z0-9_-]{32,256}$');self.assertEqual(session['origin'],f'http://127.0.0.1:{self.port}');self.assertEqual(session['deviceId'],self.agent.identity['deviceId']);self.assertEqual(session['ownerId'],'desktop');self.assertEqual(session['clientName'],'GalaxyControl');self.assertEqual(session['version'],VERSION)
  if os.name!='nt':self.assertEqual(stat.S_IMODE((self.state/DESKTOP_SESSION_FILE).stat().st_mode),0o600);self.assertEqual(stat.S_IMODE(self.state.stat().st_mode),0o700)
  self.assertEqual(self.request('GET','/settings',token=session['token'])[0],200);self.assertEqual(self.agent.bridge.approvals,[])
 def test_unknown_loopback_is_denied_and_extension_requires_native_approval(self):
  session=self.start();self.assertEqual(self.request('GET','/settings')[0],401)
  status,data,_=self.request('POST','/pair',{'clientName':'Browser client'});self.assertEqual(status,403);self.assertEqual(json.loads(data)['errorCode'],'forbiddenOrigin');self.assertEqual(self.agent.bridge.approvals,[])
  extension='chrome-extension://'+'a'*32;self.agent.origins.add(extension)
  status,data,_=self.request('POST','/pair',{'clientName':'Approved mock extension'},origin=extension);self.assertEqual(status,200);browser_token=json.loads(data)['token'];self.assertNotEqual(browser_token,session['token']);self.assertEqual(self.agent.bridge.approvals,[(extension,'Approved mock extension')]);self.assertEqual(self.request('GET','/settings',origin=extension,token=browser_token)[0],200);self.assertEqual(self.request('GET','/settings',token=session['token'])[0],200)
  self.request('DELETE','/pair',origin=extension,token=browser_token);self.assertEqual(self.request('GET','/settings',origin=extension,token=browser_token)[0],401);self.assertEqual(self.request('GET','/settings',token=session['token'])[0],200)
 def test_desktop_secret_is_never_served_by_http_or_public_snapshots(self):
  session=self.start();secret=session['token'].encode()
  # Even an authenticated request cannot obtain the private native bootstrap.
  for path in ['/desktop-session.json','/tools/desktop-session.json','/tools/../state/desktop-session.json','/tools/%2e%2e/state/desktop-session.json','/tools/%2e%2e%2fstate%2fdesktop-session.json']:
   status,data,_=self.request('GET',path,token=session['token']);self.assertIn(status,(400,403,404));self.assertNotIn(secret,data)
  # A symlink planted in public UI must not expose the private state either.
  symlink_or_skip(self.ui/'secret.json',self.state/DESKTOP_SESSION_FILE);status,data,_=self.request('GET','/tools/secret.json',token=session['token']);self.assertEqual(status,404);self.assertNotIn(secret,data)
  for path in ['/health','/settings','/browser','/roots']:
   status,data,_=self.request('GET',path,token=session['token']);self.assertEqual(status,200);self.assertNotIn(secret,data);self.assertNotIn(b'desktop-session',data)
 def test_bootstrap_token_cannot_be_used_for_other_origin_or_missing_origin(self):
  session=self.start()
  for origin in ['',f'http://localhost:{self.port}','https://supabase-app-liard.vercel.app','http://127.0.0.1:5173','chrome-extension://'+'a'*32,'https://evil.example']:
   status,_,cors=self.request('GET','/settings',origin=origin,token=session['token']);self.assertIn(status,(401,403));self.assertNotEqual(cors,'*')
 def test_admin_is_unconditionally_blocked_and_extension_still_requires_consent(self):
  session=self.start();admin='https://supabase-app-liard.vercel.app';extension='chrome-extension://'+'a'*32;self.agent.origins.add(extension)
  self.agent.bridge.approved=False
  status,data,cors=self.request('POST','/pair',{'clientName':'Forbidden ADMIN'},origin=admin);self.assertEqual(status,403);self.assertEqual(json.loads(data)['errorCode'],'forbiddenOrigin');self.assertIsNone(cors);self.assertEqual(len(self.agent.bridge.approvals),0)
  for origin,error in [(extension,'pairingDenied'),(session['origin'],'forbiddenOrigin')]:
   status,data,_=self.request('POST','/pair',{'clientName':'Denied client'},origin=origin);self.assertEqual(status,403);self.assertEqual(json.loads(data)['errorCode'],error);self.assertNotIn(origin,self.agent.tokens)
  self.assertEqual(len(self.agent.bridge.approvals),1);self.assertEqual(self.request('GET','/settings',token=session['token'])[0],200)
  self.agent.bridge.approved=True
  status,data,_=self.request('POST','/pair',{'clientName':'Approved capture extension'},origin=extension);self.assertEqual(status,200);token=json.loads(data)['token'];self.assertEqual(self.request('GET','/settings',origin=extension,token=token)[0],200)
  self.agent.origins.add(admin) # Even an accidentally broadened list cannot reopen remote access.
  self.agent.tokens[admin]={'digest':hashlib.sha256(token.encode()).hexdigest()}
  for path in ['/health','/settings','/phone/status']:
   self.assertEqual(self.request('GET',path,origin=admin,token=token)[0],403)
  self.assertEqual(self.request('POST','/pair',{'clientName':'ADMIN'},origin=admin)[0],403)
 def test_env_cannot_restore_remote_admin_or_dev_access(self):
  with patch.dict(os.environ,{'ADMIN_LOCAL_ALLOWED_ORIGINS':'https://supabase-app-liard.vercel.app,http://localhost:5173'}):session=self.start()
  for origin in ['https://supabase-app-liard.vercel.app','http://localhost:5173']:
   self.assertNotIn(origin,self.agent.origins);self.assertEqual(self.request('GET','/health',origin=origin,token=session['token'])[0],403)
 def test_existing_all_origin_pairings_are_byte_preserved_at_startup_and_restart(self):
  self.state.mkdir();origin=f'http://127.0.0.1:{self.port}';old_token='existing-browser-token';records={origin:{'digest':hashlib.sha256(old_token.encode()).hexdigest(),'clientName':'Original local browser','createdAt':'kept'},'https://supabase-app-liard.vercel.app':{'digest':'keep-admin','createdAt':'kept'},'chrome-extension://'+'b'*32:{'digest':'keep-extension','createdAt':'kept'}};atomic_json(self.state/'pairings.json',records);before=(self.state/'pairings.json').read_bytes()
  session=self.start();self.assertEqual((self.state/'pairings.json').read_bytes(),before);self.assertEqual(self.request('GET','/settings',token=old_token)[0],401);self.assertEqual(self.request('GET','/settings',token=session['token'])[0],200)
  restarted=self.restart();self.assertEqual(restarted,session);self.assertEqual((self.state/'pairings.json').read_bytes(),before);self.assertEqual(self.request('GET','/settings',token=old_token)[0],401);self.assertEqual(self.request('GET','/settings',token=session['token'])[0],200)
 def test_restart_updates_version_without_rotating_device_token(self):
  session=self.start();stored={**session,'version':'1.0.0'};atomic_json(self.state/DESKTOP_SESSION_FILE,stored)
  restarted=self.restart();self.assertEqual(restarted['token'],session['token']);self.assertEqual(restarted['version'],VERSION);self.assertEqual(restarted['deviceId'],session['deviceId'])
 def test_new_port_rotates_only_private_desktop_session(self):
  first=self.start();extension='chrome-extension://'+'a'*32;self.agent.origins.add(extension);status,data,_=self.request('POST','/pair',{'clientName':'Extension preserved'},origin=extension);self.assertEqual(status,200);extension_token=json.loads(data)['token'];before=(self.state/'pairings.json').read_bytes()
  with socket.socket() as connection:connection.bind(('127.0.0.1',0));next_port=connection.getsockname()[1]
  second=self.restart(next_port);self.assertNotEqual(second['token'],first['token']);self.assertNotEqual(second['origin'],first['origin']);self.assertEqual(second['deviceId'],first['deviceId']);self.assertEqual((self.state/'pairings.json').read_bytes(),before);self.agent.origins.add(extension);self.assertEqual(self.request('GET','/settings',origin=extension,token=extension_token)[0],200)
 def test_private_session_symlink_and_nonregular_paths_are_rejected(self):
  self.state.mkdir();target=self.path/'unrelated.json';target.write_text('preserve me');path=self.state/DESKTOP_SESSION_FILE;symlink_or_skip(path,target)
  with self.assertRaisesRegex(AgentError,'unsafePath'):Agent(self.state,self.ui,self.port)
  self.assertTrue(path.is_symlink());self.assertEqual(target.read_text(),'preserve me');path.unlink();path.mkdir()
  with self.assertRaisesRegex(AgentError,'unsafePath'):Agent(self.state,self.ui,self.port)
  self.assertTrue(path.is_dir())
 def test_atomic_native_session_write_rejects_symlinked_directory(self):
  target=self.path/'target';target.mkdir();linked=self.path/'linked';symlink_or_skip(linked,target,target_is_directory=True)
  with self.assertRaises((AgentError,OSError)):private_desktop_session_write(linked,{'token':'private'})
  self.assertFalse((target/DESKTOP_SESSION_FILE).exists())
 def test_live_program_owns_global_shortcut_results_before_admin(self):
  session=self.start();admin='https://supabase-app-liard.vercel.app';self.agent.tokens[admin]={'digest':'already-approved'};desktop=queue.Queue();remote=queue.Queue();self.agent.listeners=[(admin,remote),(session['origin'],desktop)]
  self.assertEqual(self.agent.native_owner(admin),session['origin']);self.agent.emit({'type':'fixture','value':'owned native result'},self.agent.native_owner(admin));self.assertEqual(desktop.get_nowait()['value'],'owned native result');self.assertTrue(remote.empty())
  self.agent.listeners=[(admin,remote)];self.assertEqual(self.agent.native_owner(admin),session['origin'])
 def test_public_recording_status_is_strict_boolean_and_has_no_private_bridge_fields(self):
  session=self.start()
  for native,expected in [({'recording':True,'paused':True},(True,True)),({'recording':True,'paused':False},(True,False)),({'recording':False,'paused':True},(False,False)),({'recording':1,'paused':'true'},(False,False))]:
   with patch.object(self.agent.bridge,'status',return_value={**native,'token':'must-stay-private','file':'/private/recording/path'}):
    status,data,_=self.request('GET','/health',token=session['token']);self.assertEqual(status,200);health=json.loads(data);self.assertEqual((health['recording'],health['paused']),expected);self.assertNotIn(b'must-stay-private',data);self.assertNotIn(b'/private/recording/path',data)
  with patch.object(self.agent.bridge,'ready',return_value=False),patch.object(self.agent.bridge,'status',return_value={'recording':True,'paused':True}):
   health=json.loads(self.request('GET','/health',token=session['token'])[1]);self.assertFalse(health['nativeReady']);self.assertFalse(health['recording']);self.assertFalse(health['paused'])
 def test_parent_folder_index_keeps_user_files_but_excludes_all_agent_private_state(self):
  session=self.start();source=self.path/'user-document.txt';source.write_text('ordinary searchable user content');before=source.read_bytes();ident=self.agent.index.add(self.path);self.agent.index.reconcile(ident)
  status,data,_=self.request('POST','/search',{'query':'ordinary'},token=session['token']);self.assertEqual(status,200);self.assertEqual(json.loads(data)['files'][0]['name'],source.name)
  for query in ['desktop-session',session['token'],'GalaxyControl']:
   status,data,_=self.request('POST','/search',{'query':query},token=session['token']);self.assertEqual(status,200);self.assertEqual(json.loads(data)['files'],[])
  with self.agent.index.lock:
   rows=list(self.agent.index.db.execute('SELECT relative,text FROM files WHERE root=?',(ident,)))
  self.assertFalse(any(row['relative'].startswith('state'+os.sep) for row in rows));self.assertFalse(any(session['token'] in row['text'] for row in rows));self.assertEqual(source.read_bytes(),before)
  with self.assertRaisesRegex(AgentError,'unsafePath'):self.agent.index.add(self.state)
 def test_native_private_file_selection_and_old_registered_alias_cannot_download_secret(self):
  session=self.start();path=self.state/DESKTOP_SESSION_FILE
  with patch.object(self.agent.bridge,'call',return_value={'paths':[str(path)]}):
   status,data,_=self.request('POST','/files/choose',{'kind':'any','multiple':True},token=session['token']);self.assertEqual(status,403);self.assertEqual(json.loads(data)['errorCode'],'forbiddenFile')
  self.assertEqual(self.agent.files,{})
  ident=str(uuid.uuid4());self.agent.files[ident]={'path':str(path),'owner':session['origin'],'kind':'native','name':path.name}
  for method,url,body in [('GET','/artifacts/'+ident,None),('GET','/files/'+ident+'/preview',None),('POST','/files/open',{'id':ident})]:
   status,data,_=self.request(method,url,body,token=session['token']);self.assertEqual(status,403);self.assertNotIn(session['token'].encode(),data)
 def test_legitimate_opaque_upload_and_generated_output_inside_state_remain_usable(self):
  session=self.start();image=io.BytesIO();Image.new('RGB',(5,3),'red').save(image,'PNG');upload=self.state/'uploads'/str(uuid.uuid4())/'own.png';upload.parent.mkdir();upload.write_bytes(image.getvalue());saved=self.agent.register(upload,session['origin'],'upload');status,data,_=self.request('GET','/artifacts/'+saved['id'],token=session['token']);self.assertEqual(status,200);self.assertEqual(data,image.getvalue())
  output=self.state/'tasks'/str(uuid.uuid4())/'outputs'/'edited.png';output.parent.mkdir(parents=True);output.write_bytes(image.getvalue());saved=self.agent.register(output,session['origin'],'artifact');self.assertEqual(self.request('GET','/artifacts/'+saved['id'],token=session['token'])[0],200)
 def test_restart_purges_old_private_index_rows_without_touching_files(self):
  session=self.start();ident=self.agent.index.add(self.path);self.agent.index.reconcile(ident);private_id=str(uuid.uuid4());path=self.state/DESKTOP_SESSION_FILE;before=path.read_bytes()
  with self.agent.index.lock:
   self.agent.index.db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?)',(private_id,ident,'state/'+DESKTOP_SESSION_FILE,DESKTOP_SESSION_FILE,'.json',len(before),0,0,'old-fixture',session['token']));self.agent.index.db.commit()
  self.restart()
  with self.agent.index.lock:self.assertIsNone(self.agent.index.db.execute('SELECT id FROM files WHERE id=?',(private_id,)).fetchone())
  self.assertEqual(path.read_bytes(),before)

def symlink_or_skip(path,target,**kwargs):
 try:path.symlink_to(target,**kwargs)
 except OSError as error:
  if getattr(error,'winerror',None)==1314:raise unittest.SkipTest('Windows symlink privilege unavailable; fixture not executed')
  raise

if __name__=='__main__':unittest.main(verbosity=2)

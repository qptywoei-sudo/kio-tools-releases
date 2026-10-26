"""Security contract tests; KIO cloud and OS vault are explicitly test fixtures.

Callback and installed local API tests use real ephemeral loopback HTTP servers.
They do not establish OAuth provider compatibility or live cloud credentials.
"""
import hashlib, http.client, io, json, queue, socket, sys, tempfile, threading, time, unittest, urllib.parse, uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'agent'),str(ROOT/'integration-tests')]
from common import AgentError
from kio_account import KIOAccount,CLOUD_ORIGIN,PROJECT_REF,expiry_seconds
from server import Agent,Server
from index import FileIndex
from test_local_system import ApprovalFixture

USER={'id':'19a3b744-b887-4dd8-b019-43306f7610f3','email':'fixture@example.invalid','name':'KIO fixture','provider':'google'}
OTHER={**USER,'id':'1998bf7c-1fe0-419d-80be-eccfb9c93f40','email':'other@example.invalid'}

class MemoryVault:
    def __init__(self): self.data=None; self.fail=False
    def load(self): return self.data
    def save(self,data):
        if self.fail: raise AgentError('accountSecureStorageUnavailable')
        self.data=data
    def delete(self): self.data=None

class CloudFixture:
    def __init__(self,clock): self.clock=clock; self.calls=[]; self.user=USER; self.fail=None; self.serial=0
    def __call__(self,route,body,headers,method):
        self.calls.append((route,dict(body),dict(headers),method))
        if self.fail: raise AgentError(self.fail,503 if self.fail=='accountCloudUnavailable' else 401)
        self.serial+=1
        value={'credential':'test-only-opaque-'+str(self.serial)+'x'*60,'user':dict(self.user),'expires':int((self.clock()+86400)*1000),'credentialExpires':int((self.clock()+86400)*1000)}
        if route=='/control/web/verify': value.update(web=True,expires=int((self.clock()+900)*1000))
        return value

class BinaryResponse(io.BytesIO):
    status=200
    def __init__(self,data,headers):super().__init__(data);self.headers=headers

class BinaryOpener:
    def __init__(self,data,headers):self.data=data;self.headers=headers;self.requests=[]
    def open(self,request,timeout=0):self.requests.append(request);return BinaryResponse(self.data,self.headers)

class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.now=1750000000.;self.clock=lambda:self.now
        self.vault=MemoryVault();self.cloud=CloudFixture(self.clock);self.urls=[]
        self.account=KIOAccount(self.path,store=self.vault,transport=self.cloud,clock=self.clock,open_browser=lambda url:self.urls.append(url) or True)
    def tearDown(self): self.account.close();time.sleep(.55);self.temp.cleanup()
    def sign_in(self,user=USER): self.account._accept({'credential':'test-only-initial-opaque'+'x'*60,'user':user,'expires':self.now+3600})
    def test_unsigned_requires_login_and_does_not_expose_credentials(self):
        self.assertFalse(self.account.status()['signedIn'])
        with self.assertRaisesRegex(AgentError,'ACCOUNT_REQUIRED'):self.account.require()
        self.sign_in();status=self.account.status();self.assertTrue(status['signedIn']);self.assertEqual(status['user']['id'],USER['id']);self.assertNotIn('credential',json.dumps(status))
    def test_signed_session_survives_restart_only_in_secure_vault(self):
        self.sign_in();restored=KIOAccount(self.path,store=self.vault,transport=self.cloud,clock=self.clock)
        self.assertEqual(restored.require()['id'],USER['id']);self.assertNotIn(self.account.credential.encode(),b''.join(p.read_bytes() for p in self.path.rglob('*') if p.is_file()))
    def test_failed_secure_persistence_never_activates_session(self):
        self.vault.fail=True
        with self.assertRaisesRegex(AgentError,'accountSecureStorageUnavailable'):self.sign_in()
        self.assertFalse(self.account.status()['signedIn'])
    def test_foreign_project_vault_is_not_accepted(self):
        self.sign_in();saved=json.loads(self.vault.data);saved['projectRef']='foreign';self.vault.data=json.dumps(saved).encode()
        restored=KIOAccount(self.path,store=self.vault,clock=self.clock)
        self.assertFalse(restored.status()['signedIn']);self.assertEqual(restored.status()['error'],'accountReconnect')
    def test_fixed_cloud_routes_reject_endpoint_injection(self):
        self.sign_in()
        for route in ['https://evil.invalid','/control/../other','/control/a?bad=1','/anything']:
            with self.assertRaisesRegex(AgentError,'accountInvalidEndpoint'):self.account._request(route)
        self.assertEqual(self.cloud.calls,[])
    def test_pkce_callback_requires_host_and_exact_state(self):
        self.account.login('google');query=urllib.parse.parse_qs(urllib.parse.urlparse(self.urls[0]).query);callback=urllib.parse.urlparse(query['redirect_uri'][0]);port=callback.port
        self.assertEqual(urllib.parse.urlparse(self.urls[0]).hostname,'kio-library.vercel.app');self.assertEqual(len(query['code_challenge'][0]),43)
        for state,host in [('wrong',f'127.0.0.1:{port}'),(query['state'][0],f'localhost:{port}')]:
            connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3);connection.request('GET','/kio/callback?'+urllib.parse.urlencode({'state':state,'grant':'test-only-grant'+'x'*30}),headers={'Host':host});response=connection.getresponse();self.assertEqual(response.status,400);response.read();connection.close()
        self.assertEqual(self.cloud.calls,[])
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3);connection.request('GET','/kio/callback?'+urllib.parse.urlencode({'state':query['state'][0],'grant':'test-only-grant'+'x'*30}),headers={'Host':f'127.0.0.1:{port}'});response=connection.getresponse();payload=response.read();connection.close();self.assertEqual(response.status,200)
        self.assertTrue(self.account.status()['signedIn']);call=self.cloud.calls[0];self.assertEqual(call[0],'/control/native/exchange');self.assertNotIn('Authorization',call[2]);self.assertNotIn('Origin',call[2]);self.assertNotIn('Cookie',call[2]);verifier=call[1]['code_verifier']
        import base64
        self.assertEqual(base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),query['code_challenge'][0]);self.assertNotIn(verifier.encode(),payload);self.assertNotIn(self.account.credential.encode(),payload)
    def test_expected_identity_prevents_drive_reauth_account_switch(self):
        self.sign_in();self.cloud.user=OTHER;self.account.login('google',expected_user=USER['id']);query=urllib.parse.parse_qs(urllib.parse.urlparse(self.urls[0]).query);port=urllib.parse.urlparse(query['redirect_uri'][0]).port
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3);connection.request('GET','/kio/callback?'+urllib.parse.urlencode({'state':query['state'][0],'grant':'test-only-grant'+'x'*30}),headers={'Host':f'127.0.0.1:{port}'});response=connection.getresponse();response.read();connection.close()
        self.assertEqual(self.account.status()['user']['id'],USER['id']);self.assertEqual(self.account.status()['error'],'accountChanged')
    def test_offline_local_use_is_limited_to_unexpired_verified_credential(self):
        self.sign_in();self.now+=301;self.cloud.fail='accountCloudUnavailable';self.assertEqual(self.account.require()['id'],USER['id'])
        with self.assertRaisesRegex(AgentError,'accountCloudUnavailable'):self.account.require(online=True)
        self.now+=3600
        with self.assertRaises(AgentError):self.account.require()
    def test_cloud_revocation_clears_local_identity(self):
        self.sign_in();self.now+=301;self.cloud.fail='accountReconnect'
        with self.assertRaisesRegex(AgentError,'accountReconnect'):self.account.require(online=True)
        self.assertFalse(self.account.status()['signedIn']);self.assertIsNone(self.vault.data)
    def test_invalid_expiry_and_user_schema_fail_closed(self):
        for expiry in [True,float('nan'),float('inf'),self.now-1,self.now+400*86400]:
            with self.assertRaises(AgentError):self.account._accept({'credential':'x'*60,'user':USER,'expires':expiry})
        with self.assertRaises(AgentError):self.account._accept({'credential':'x'*60,'user':{**USER,'id':'not-a-uuid'},'expires':self.now+60})
    def test_binary_download_persists_rotation_and_keeps_file_name(self):
        self.sign_in();payload=b'fixture PNG bytes';headers={'Content-Length':str(len(payload)),'Content-Type':'image/png','X-KIO-Control-File-Name':urllib.parse.quote('키오 사진.png'),'X-KIO-Native-Credential':'test-only-rotated-binary'+'x'*60,'X-KIO-Credential-Expires':str(int((self.now+86400)*1000))}
        opener=BinaryOpener(payload,headers);self.account.opener=opener;target=self.path.resolve()/'download.png';metadata=self.account.binary_download('fixture-drive-id',target)
        self.assertEqual(target.read_bytes(),payload);self.assertEqual(metadata,{'name':'키오 사진.png','size':len(payload),'mime':'image/png'});self.assertEqual(json.loads(self.vault.data)['credential'],headers['X-KIO-Native-Credential']);url=urllib.parse.urlparse(opener.requests[0].full_url);self.assertEqual(url.hostname,'kio-library.vercel.app');self.assertEqual(urllib.parse.parse_qs(url.query)['fileId'],['fixture-drive-id']);self.assertNotIn('Origin',dict(opener.requests[0].header_items()))
        with self.assertRaisesRegex(AgentError,'unsafePath'):self.account.binary_download('fixture-drive-id',target)
        self.assertEqual(target.read_bytes(),payload)
    def test_binary_download_rejects_oversize_and_removes_partial(self):
        self.sign_in();self.account.opener=BinaryOpener(b'too many bytes',{});target=self.path.resolve()/'oversize.png'
        with self.assertRaisesRegex(AgentError,'fileTooLarge'):self.account.binary_download('fixture-drive-id',target,maxbytes=3)
        self.assertFalse(target.exists());self.assertEqual(list(target.parent.glob('.kio-download-*.tmp')),[])
    def test_drive_connection_purpose_is_explicit_and_identity_bound(self):
        self.sign_in();self.account.login('google',expected_user=USER['id'],connect_drive=True);query=urllib.parse.parse_qs(urllib.parse.urlparse(self.urls[0]).query);self.assertEqual(query['controlDrive'],['1']);self.account.cancel()
        with self.assertRaisesRegex(AgentError,'invalidRequest'):self.account.login('google',connect_drive=True)
    def test_cloud_side_effects_are_fenced_before_any_request_after_account_switch(self):
        self.sign_in(OTHER);target=self.path.resolve()/'wrong-user.png'
        with self.assertRaisesRegex(AgentError,'accountChanged'):self.account.cloud('/control/drive/upload/start',{'name':'private.png'},expected_user=USER['id'])
        with self.assertRaisesRegex(AgentError,'accountChanged'):self.account.binary_download('fixture-drive-id',target,expected_user=USER['id'])
        self.assertEqual(self.cloud.calls,[]);self.assertFalse(target.exists())

class LocalAccountApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name).resolve();self.ui=self.path/'ui';self.ui.mkdir();(self.ui/'index.html').write_text('<h1>Fixture</h1>')
        self.vault=MemoryVault();self.cloud=CloudFixture(time.time)
        self.loop=patch.object(FileIndex,'loop',return_value=None);self.watch=patch.object(FileIndex,'watch',return_value=None);self.loop.start();self.watch.start()
        with socket.socket() as connection:connection.bind(('127.0.0.1',0));self.port=connection.getsockname()[1]
        with patch('server.KIOAccount',side_effect=lambda state:KIOAccount(state,store=self.vault,transport=self.cloud)):
            self.agent=Agent(self.path/'state',self.ui,self.port)
        bridge_root=self.agent.bridge.root;self.agent.bridge=ApprovalFixture();self.agent.bridge.root=bridge_root
        self.server=Server(self.agent);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.origin=f'http://127.0.0.1:{self.port}';self.token=self.agent.desktop_session['token']
    def tearDown(self): self.server.shutdown();self.server.server_close();self.agent.close();self.loop.stop();self.watch.stop();self.temp.cleanup()
    def request(self,method,path,body=None,origin=None,token=None):
        headers={'Host':f'127.0.0.1:{self.port}','Origin':origin or self.origin}
        if token:headers['X-Local-Agent-Token']=token
        if body is not None:headers['Content-Type']='application/json';body=json.dumps(body)
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);connection.request(method,path,body,headers);response=connection.getresponse();payload=response.read();value=(response.status,json.loads(payload) if payload else {});connection.close();return value
    def sign_in(self,user=USER):self.agent.account._accept({'credential':'test-only-initial-opaque'+'x'*60,'user':user,'expires':time.time()+3600})
    def test_signed_out_blocks_tools_and_native_shortcuts_but_allows_account_gate(self):
        self.assertEqual(self.request('GET','/account/status',token=self.token)[0],200)
        status,data=self.request('GET','/settings',token=self.token);self.assertEqual((status,data['errorCode']),(401,'ACCOUNT_REQUIRED'))
        self.assertEqual(self.request('POST','/desktop/dispatch',{'action':'areaCapture'},token=self.token),(200,{'destination':'login'}))
        self.assertEqual(self.request('GET','/kio/web/challenge',origin=CLOUD_ORIGIN)[0],403)
    def test_cloud_token_cannot_take_native_account_or_update_authority(self):
        self.sign_in();token='old-web-capability'+'x'*48
        self.assertEqual(self.request('GET','/settings',origin=self.origin,token=token)[0],401)
        self.assertEqual(self.request('GET','/account/status',origin=CLOUD_ORIGIN,token=token)[0],403)
        for path,body in [('/account/logout',{}),('/updates/check',{}),('/desktop/dispatch',{'action':'areaCapture'})]:self.assertEqual(self.request('POST',path,body,origin=self.origin,token=token)[0],401)
        self.assertEqual(self.request('GET','/settings',origin='https://evil.invalid',token=token)[0],403)
    def test_files_share_between_same_account_web_native_but_not_other_account(self):
        self.sign_in();image=self.path/'fixture.png';image.write_bytes(b'fixture image bytes');file=self.agent.register(image,self.origin)
        self.assertEqual(self.agent.resolve(file['id'],CLOUD_ORIGIN),image)
        self.sign_in(OTHER)
        with self.assertRaisesRegex(AgentError,'unauthorized'):self.agent.resolve(file['id'],self.origin)
    def test_legacy_files_bind_only_once_not_to_next_login(self):
        image=self.path/'legacy.png';image.write_bytes(b'preserved fixture');ident=str(uuid.uuid4());self.agent.files[ident]={'path':str(image),'owner':self.origin,'name':image.name,'kind':'artifact'}
        self.sign_in();self.assertEqual(self.agent.resolve(ident,self.origin),image)
        self.sign_in(OTHER)
        with self.assertRaisesRegex(AgentError,'unauthorized'):self.agent.resolve(ident,self.origin)
    def test_profile_switch_isolates_ai_signatures_index_and_upload_queue(self):
        self.sign_in();self.agent.require_account();original=(self.agent.ai.account.state,self.agent.signatures.root,self.agent.index.private_state,self.agent.storage.state)
        self.agent.ai.scans['fixture']={'private':'first account'}
        self.sign_in(OTHER);self.agent.require_account();self.assertEqual(self.agent.ai.scans,{});self.assertIn(OTHER['id'],str(self.agent.ai.account.state));self.assertIn(OTHER['id'],str(self.agent.signatures.root));self.assertIn(OTHER['id'],str(self.agent.storage.state));self.assertEqual(self.agent.index.private_state,self.agent.state);self.assertTrue(self.agent.index.private_path(self.agent.state/'kio-account'))
        self.sign_in(USER);self.agent.require_account();self.assertEqual((self.agent.ai.account.state,self.agent.signatures.root,self.agent.index.private_state,self.agent.storage.state),original)
    def test_legacy_loopback_pairings_cannot_bypass_native_or_web_credentials(self):
        self.sign_in();legacy='fixture-old-loopback-pairing';self.agent.tokens[self.origin]={'digest':hashlib.sha256(legacy.encode()).hexdigest()}
        self.assertEqual(self.request('GET','/settings',token=legacy)[0],401)
        self.assertEqual(self.request('POST','/pair',{'clientName':'Unknown local browser'},token=legacy)[0],403);self.assertEqual(self.agent.bridge.approvals,[])
        extension='chrome-extension://'+'a'*32;self.agent.origins.add(extension)
        status,pair=self.request('POST','/pair',{'clientName':'Capture extension'},origin=extension);self.assertEqual(status,200);self.assertEqual(self.agent.bridge.approvals,[(extension,'Capture extension')]);self.assertEqual(self.request('GET','/settings',origin=extension,token=pair['token'])[0],200)
    def test_native_ui_cannot_be_embedded_as_a_web_remote(self):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);connection.request('GET','/tools/',headers={'Host':f'127.0.0.1:{self.port}'});response=connection.getresponse();csp=response.getheader('Content-Security-Policy');response.read();connection.close();self.assertEqual(response.status,200);self.assertIn("frame-ancestors 'none';",csp);self.assertNotIn('*',csp)

class DesktopOnlyAccountTests(unittest.TestCase):
    setUp=LocalAccountApiTests.setUp
    tearDown=LocalAccountApiTests.tearDown
    request=LocalAccountApiTests.request
    sign_in=LocalAccountApiTests.sign_in
    def test_all_shortcuts_stay_on_desktop_even_with_legacy_web_presence(self):
        self.sign_in()
        self.agent.account.web_active=lambda:True
        self.agent.account.active_connection=lambda:'old-connection'
        for action in ('areaCapture','fullCapture','webCapture','recordToggle','recordArea','aiTranslate'):
            status,result=self.request('POST','/desktop/dispatch',{'action':action},token=self.token)
            self.assertEqual((status,result),(200,{'destination':'desktop'}))
        self.assertEqual(self.agent.native_owner(CLOUD_ORIGIN),self.origin)
        # General local mutations are no longer blocked by a web presence lease.
        self.assertEqual(self.request('PATCH','/settings',{'captureFormat':'jpg'},token=self.token)[0],200)
    def test_retired_remote_routes_cannot_grant_access_to_any_browser(self):
        self.sign_in()
        for origin in (CLOUD_ORIGIN,'https://evil.invalid'):
            for method,path,body in [('GET','/kio/web/challenge',None),('POST','/kio/web/pair',{}),('POST','/kio/web/presence',{'active':True})]:
                self.assertEqual(self.request(method,path,body,origin=origin,token='old-web-token')[0],403)
        self.assertEqual(self.request('POST','/kio/web/presence',{},token=self.token)[0],410)
    def test_logout_relocks_tools_preserves_preferences_and_survives_restart(self):
        self.sign_in();self.agent.require_account()
        self.agent.settings['shortcuts']={'areaCapture':'Control+Shift+Q'}
        before=dict(self.agent.settings)
        self.assertEqual(self.request('POST','/account/logout',{},token=self.token)[0],200)
        self.assertEqual(self.request('GET','/settings',token=self.token)[0],401)
        self.assertEqual(self.request('POST','/desktop/dispatch',{'action':'aiTranslate'},token=self.token),(200,{'destination':'login'}))
        self.assertEqual(self.agent.settings,before)
        restored=KIOAccount(self.agent.state,store=self.vault,transport=self.cloud)
        self.assertFalse(restored.status()['signedIn']);self.assertIsNone(self.vault.data)

if __name__=='__main__':unittest.main(verbosity=2)

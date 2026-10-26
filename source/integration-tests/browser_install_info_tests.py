"""Disposable local HTTP/manifest tests. Native reveal is mocked; no user state."""
import hashlib,json,socket,sys,tempfile,threading,unittest,urllib.error,urllib.request
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1];sys.path[:0]=[str(source/'engine'),str(source/'agent')]
from common import atomic_json
from server import Server
from kio_fixture import VerifiedAgent as Agent

class BrowserInstallInfoTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.install=self.root/'사용자별 설치 경로';(self.install/'engine').mkdir(parents=True);self.extension=self.install/'browser-extension';self.extension.mkdir()
  self.manifest=self.extension/'manifest.json';atomic_json(self.manifest,{'manifest_version':3,'name':'KIO 웹 전체 캡처','version':'4.4.0'})
  with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
  self.agent=Agent(self.root/'state',source/'desktop-ui'/'dist',port);self.server=Server(self.agent);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.origin=f'http://127.0.0.1:{port}';self.token=self.agent.desktop_session['token']
  self.engine=patch('server.engine.__file__',str(self.install/'engine'/'engine.py'));self.engine.start()
  self.native=patch.object(self.agent.bridge,'call',return_value={});self.reveal=self.native.start()
 def tearDown(self):
  self.native.stop();self.engine.stop();self.server.shutdown();self.server.server_close();self.agent.close();self.thread.join(3);self.temp.cleanup()
 def request(self,path,body=None,token=None):
  request=urllib.request.Request(self.origin+path,data=None if body is None else json.dumps(body).encode(),headers={'Origin':self.origin,'X-Local-Agent-Token':token or self.token,'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.load(response)
  except urllib.error.HTTPError as response:return response.code,json.load(response)
 def test_read_only_info_is_manifest_based_and_never_opens_a_folder(self):
  before=self.manifest.read_bytes();status,info=self.request('/browser/install-info')
  self.assertEqual(status,200);self.assertEqual(info,{'folderPath':str(self.extension.resolve()),'extensionName':'KIO 웹 전체 캡처'});self.reveal.assert_not_called();self.assertEqual(self.manifest.read_bytes(),before)
 def test_explicit_open_returns_same_info_and_reveals_packaged_manifest(self):
  status,result=self.request('/browser/install',{});self.assertEqual(status,200);self.assertTrue(result['prepared']);self.assertEqual(result['folderPath'],str(self.extension.resolve()))
  self.reveal.assert_called_once_with('file.reveal',{'path':str(self.manifest.resolve())})
 def test_paired_non_desktop_tokens_cannot_read_install_path_or_open_it(self):
  token='a'*48;self.agent.tokens[self.origin]={'digest':hashlib.sha256(token.encode()).hexdigest()}
  # A legacy loopback pairing is rejected at authentication, before native-only
  # authorization or path disclosure. This is the current account-gated contract.
  self.assertEqual(self.request('/browser/install-info',token=token)[0],401);self.assertEqual(self.request('/browser/install',{},token=token)[0],401);self.reveal.assert_not_called()
 def test_missing_or_invalid_manifest_never_returns_guessed_path(self):
  for contents in [[],{}, {'name':''},{'name':12},{'name':'bad\nname'}]:
   atomic_json(self.manifest,contents);self.assertEqual(self.request('/browser/install-info')[0],404);self.assertEqual(self.request('/browser/install',{})[0],404)
  self.manifest.unlink();self.assertEqual(self.request('/browser/install-info')[0],404);self.reveal.assert_not_called()
 def test_install_rejects_client_supplied_paths(self):
  self.assertEqual(self.request('/browser/install',{'path':'C:/untrusted'})[0],400);self.reveal.assert_not_called()
 def localized_manifest(self,default='en'):
  atomic_json(self.manifest,{'manifest_version':3,'name':'__MSG_name__','default_locale':default})
  for locale,name in [('en','KIO Control Web Capture'),('ko','KIO 컨트롤 웹 캡처'),('zh_CN','KIO 中文网页截图')]:
   folder=self.extension/'_locales'/locale;folder.mkdir(parents=True,exist_ok=True);atomic_json(folder/'messages.json',{'name':{'message':name}})
 def test_localized_name_prefers_settings_and_maps_chinese_locale(self):
  self.localized_manifest()
  for locale,name in [('ko','KIO 컨트롤 웹 캡처'),('en','KIO Control Web Capture'),('zh','KIO 中文网页截图')]:
   self.agent.settings['language']=locale;status,info=self.request('/browser/install-info');self.assertEqual(status,200);self.assertEqual(info['extensionName'],name)
  self.assertEqual(self.request('/browser/install',{})[1]['extensionName'],'KIO 中文网页截图')
 def test_missing_or_invalid_translation_uses_manifest_default_locale(self):
  self.localized_manifest();self.agent.settings['language']='ja'
  self.assertEqual(self.request('/browser/install-info')[1]['extensionName'],'KIO Control Web Capture')
  self.agent.settings['language']='ko';atomic_json(self.extension/'_locales'/'ko'/'messages.json',{'name':{'message':'bad\nname'}})
  self.assertEqual(self.request('/browser/install-info')[1]['extensionName'],'KIO Control Web Capture')
 def test_unsafe_locale_and_macro_never_read_outside_locales(self):
  self.localized_manifest();self.agent.settings['language']='../../outside'
  self.assertEqual(self.request('/browser/install-info')[1]['extensionName'],'KIO Control Web Capture')
  atomic_json(self.manifest,{'name':'__MSG_name__','default_locale':'../../outside'})
  self.assertEqual(self.request('/browser/install-info')[0],404)
  for macro in ['__MSG_../name__','__MSG_name/../outside__','__MSG___']:
   atomic_json(self.manifest,{'name':macro,'default_locale':'en'});self.assertEqual(self.request('/browser/install-info')[0],404)
  self.reveal.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)

"""Disposable phone HTTP contract tests. Native approval/ADB/scrcpy are simulated.
Synthetic signed-in identity, secure vault and cloud are supplied only by the
reviewed VerifiedAgent fixture. No OS credential or live account is read.
These fixtures do not prove physical Mac or Windows phone input, audio, or clipboard behavior.
"""
import hashlib,http.client,json,queue,socket,sys,tempfile,threading,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parent/'engine'),str(HERE.parent/'integration-tests')]
from server import Server
from kio_fixture import VerifiedAgent as Agent
from common import AgentError
from phone import lan_address
class NativePhoneFixture:
 def __init__(self,root):self.root=root;self.calls=[];self.supported=True;self.running=False;self.entered=None;self.release=None
 def ready(self):return True
 def status(self):return {'updatedAt':time.time(),'settings':{},'phoneControl':self.supported}
 def approve(self,origin,name):
  if origin!='chrome-extension://'+'b'*32 or not name:raise AgentError('pairingDenied',403)
 def call(self,operation,args=None,timeout=90):
  args=args or {};self.calls.append((operation,dict(args)))
  if operation=='phone.status':return {'available':True,'devices':[{'serial':'SERIAL_TEST_ONLY','label':'Galaxy fixture','transport':'usb','status':'device'},{'serial':'UNAPPROVED_TEST_ONLY','label':'Pending fixture','transport':'usb','status':'unauthorized'},{'serial':'bad;arbitrary-shell','label':'Rejected fixture','transport':'wifi','status':'device'}],'running':self.running,'activeSerial':'SERIAL_TEST_ONLY' if self.running else '', 'options':{'keyboard':'uhid','mouse':'sdk','audio':'output','clipboard':True}}
  if operation=='phone.start':
   if self.entered:self.entered.set();self.release.wait(3)
   self.running=True
  if operation=='phone.stop':self.running=False
  return {'success':True}
class PhoneTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name);ui=base/'ui';ui.mkdir()
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
  self.origin=f'http://127.0.0.1:{self.port}';self.other='chrome-extension://'+'b'*32
  self.agent=Agent(base/'state',ui,self.port);self.native=NativePhoneFixture(self.agent.bridge.root);self.agent.bridge=self.native
  # Use the current native bootstrap and one explicitly approved mock extension.
  # Generic loopback origins and invented digest-only tokens are not trusted.
  self.agent.origins.add(self.other)
  self.token=self.agent.desktop_session['token'];self.otherToken=self.agent.pair(self.other,'Only approved phone ownership fixture')['token']
  self.server=Server(self.agent);threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.agent.close();self.temp.cleanup()
 def request(self,method,path,body=None,origin=None,token=None):
  origin=origin or self.origin;connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);headers={'Origin':origin,'X-Local-Agent-Token':token or self.token}
  if body is not None:body=json.dumps(body);headers['Content-Type']='application/json'
  connection.request(method,path,body,headers);response=connection.getresponse();status=response.status;value=json.loads(response.read());connection.close();return status,value
 def selected(self):return self.request('GET','/phone')[1]['devices'][0]['id']
 def test_status_requires_previous_native_pairing_token(self):
  self.assertEqual(self.request('GET','/phone',token='not-paired')[0],401);self.assertFalse(self.native.calls)
  self.assertEqual(self.request('POST','/phone/stop',{},origin='https://unapproved.example')[0],403);self.assertFalse(self.native.calls)
 def test_devices_are_opaque_owner_scoped_and_keep_usb_authorization_status(self):
  status,value=self.request('GET','/phone');self.assertEqual(status,200);self.assertEqual(len(value['devices']),2);self.assertEqual(value['devices'][1]['status'],'unauthorized')
  self.assertNotIn('SERIAL_TEST_ONLY',json.dumps(value));self.assertNotIn('serial',json.dumps(value));self.assertNotIn('bad;',json.dumps(value))
  other=self.request('GET','/phone',origin=self.other,token=self.otherToken)[1];self.assertNotEqual(value['devices'][0]['id'],other['devices'][0]['id'])
  self.assertEqual(self.request('POST','/phone/start',{'deviceId':value['devices'][0]['id']},origin=self.other,token=self.otherToken)[0],404)
 def test_uhid_keyboard_and_mouse_clipboard_defaults_reuse_native_start(self):
  ident=self.selected();self.assertEqual(self.request('POST','/phone/start',{'deviceId':ident})[1],{'success':True})
  start=next(args for op,args in self.native.calls if op=='phone.start');self.assertEqual(start,{'serial':'SERIAL_TEST_ONLY','keyboard':'uhid','mouse':'uhid','audio':'output','clipboard':True})
  value=self.request('GET','/phone')[1];self.assertTrue(value['running']);self.assertEqual(value['activeDeviceId'],ident)
 def test_sdk_compatibility_audio_and_clipboard_options_are_typed(self):
  ident=self.selected();self.assertEqual(self.request('POST','/phone/start',{'deviceId':ident,'keyboard':'sdk','mouse':'uhid','audio':'aac','clipboard':False})[0],200)
  start=next(args for op,args in self.native.calls if op=='phone.start');self.assertEqual(start['keyboard'],'sdk');self.assertFalse(start['clipboard'])
  for body in ({'deviceId':ident,'keyboard':'shell'},{'deviceId':ident,'clipboard':1},{'deviceId':ident,'command':'rm'},{'serial':'SERIAL_TEST_ONLY'},{'deviceId':ident,'audio':[]},{'deviceId':ident,'path':'/private/file'}):self.assertEqual(self.request('POST','/phone/start',body)[0],400)
 def test_non_authorized_phone_cannot_start(self):
  value=self.request('GET','/phone')[1];self.assertEqual(self.request('POST','/phone/start',{'deviceId':value['devices'][1]['id']})[1]['errorCode'],'phoneUnauthorized')
  self.assertFalse(any(op=='phone.start' for op,args in self.native.calls))
 def test_pairing_code_is_never_returned_or_emitted(self):
  events=queue.Queue();self.agent.listeners.append((self.origin,events));code='123456'
  status,value=self.request('POST','/phone/pair',{'address':'192.168.1.6:34323','code':code});self.assertEqual(status,200);self.assertNotIn(code,json.dumps(value));event=events.get(timeout=1);self.assertEqual(event,{'type':'phone','changed':True});self.assertNotIn(code,json.dumps(event));self.assertEqual(self.native.calls[-1],('phone.pair',{'address':'192.168.1.6:34323','code':code}))
 def test_pair_and_connect_reject_public_hosts_argument_injection_and_invalid_codes(self):
  for address in ('example.com:5555','8.8.8.8:5555','192.168.1.6:65536','192.168.1.6:0','192.168.1.6:5555;echo','192.168.001.6:5555','::1:5555'):
   self.assertEqual(self.request('POST','/phone/connect',{'address':address})[0],400)
  for code in ('12345','１２３４５６',123456,'123456\n'):self.assertEqual(self.request('POST','/phone/pair',{'address':'192.168.1.6:5555','code':code})[0],400)
  self.assertFalse(self.native.calls)
  self.assertEqual(self.request('POST','/phone/connect',{'address':'192.168.1.6:37123'})[0],200)
 def test_stop_and_keyboard_use_only_owned_native_commands(self):
  self.assertEqual(self.request('POST','/phone/keyboard-settings',{'deviceId':self.selected()})[0],200)
  self.assertEqual(self.request('POST','/phone/stop',{})[0],200)
  self.assertIn(('phone.keyboard',{'serial':'SERIAL_TEST_ONLY'}),self.native.calls);self.assertEqual(self.native.calls[-1],('phone.stop',{}))
  self.assertEqual(self.request('POST','/phone/stop',{'pid':123})[0],400)
 def test_conflicting_starts_are_serialized_without_second_native_launch(self):
  ident=self.selected();self.native.entered=threading.Event();self.native.release=threading.Event();answer=[]
  thread=threading.Thread(target=lambda:answer.append(self.request('POST','/phone/start',{'deviceId':ident})));thread.start();self.assertTrue(self.native.entered.wait(2))
  self.assertEqual(self.request('POST','/phone/start',{'deviceId':ident})[1]['errorCode'],'busy');self.native.release.set();thread.join(timeout=3);self.assertFalse(thread.is_alive());self.assertEqual(answer[0][0],200);self.assertEqual(sum(op=='phone.start' for op,args in self.native.calls),1)
  self.assertEqual(self.request('POST','/phone/start',{'deviceId':ident})[1]['errorCode'],'phoneAlreadyRunning')
 def test_old_native_app_does_not_advertise_new_phone_controls(self):
  self.native.supported=False;self.assertNotIn('phone_start',self.agent.operations());self.assertIn('phone_open',self.agent.operations());self.assertEqual(self.request('GET','/phone')[1]['errorCode'],'phoneUnavailable');self.assertFalse(self.native.calls)
 def test_change_events_are_not_sent_to_other_paired_origin(self):
  own=queue.Queue();other=queue.Queue();self.agent.listeners.extend([(self.origin,own),(self.other,other)]);self.assertEqual(self.request('POST','/phone/stop',{})[0],200);self.assertEqual(own.get(timeout=1),{'type':'phone','changed':True});self.assertTrue(other.empty())
 def test_phone_controls_cannot_be_submitted_as_an_untyped_background_job(self):
  self.assertEqual(self.request('POST','/jobs',{'operation':'phone_start','options':{'serial':'SERIAL_TEST_ONLY'}})[1]['errorCode'],'unsupported');self.assertFalse(self.native.calls)
 def test_lan_addresses_support_private_link_local_and_explicit_loopback_only(self):
  for address in ('10.0.0.2:5555','172.16.1.2:65535','192.168.1.6:37123','169.254.4.0:5555','127.0.0.1:5555'):self.assertTrue(lan_address(address))
  for address in ('172.32.1.2:5555','127.0.0.2:5555','224.0.0.1:5555'):self.assertFalse(lan_address(address))
 def test_desktop_and_extension_tokens_cannot_be_swapped_between_owners(self):
  self.assertEqual(self.request('GET','/phone',origin=self.other,token=self.token)[0],401)
  self.assertEqual(self.request('POST','/phone/stop',{},origin=self.origin,token=self.otherToken)[0],401)
  self.assertFalse(self.native.calls)
 def test_explicit_sdk_mouse_choice_preserves_compatibility(self):
  self.assertEqual(self.request('POST','/phone/start',{'deviceId':self.selected(),'mouse':'sdk'})[0],200)
  start=next(args for op,args in self.native.calls if op=='phone.start')
  self.assertEqual(start['mouse'],'sdk');self.assertEqual(start['keyboard'],'uhid');self.assertTrue(start['clipboard'])
if __name__=='__main__':unittest.main(verbosity=2)

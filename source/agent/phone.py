"""Typed phone controls over the existing native scrcpy/ADB implementation.
No executable names, shell commands, file paths, or raw ADB device serials enter the HTTP contract.
"""
from __future__ import annotations
import hashlib,hmac,ipaddress,re,threading
from common import AgentError
OPTIONS={'keyboard':('uhid','sdk'),'mouse':('sdk','uhid'),'audio':('output','aac','off')}
DEFAULT_OPTIONS={'keyboard':'uhid','mouse':'uhid','audio':'output','clipboard':True}
OPERATIONS={'phone_status','phone_pair','phone_connect','phone_start','phone_stop','phone_keyboard_settings'}

def lan_address(value):
 if not isinstance(value,str) or not re.fullmatch(r'[0-9.]{7,15}:[0-9]{1,5}',value):return False
 host,port=value.rsplit(':',1)
 try:
  ip=ipaddress.IPv4Address(host);number=int(port)
 except (ValueError,TypeError):return False
 allowed=any(ip in ipaddress.IPv4Network(network) for network in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','127.0.0.1/32'))
 return allowed and 1<=number<=65535

def serial_valid(value):return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value) is not None and not value.startswith('emulator-')

class PhoneControls:
 def __init__(self,agent):self.agent=agent;self.lock=threading.Lock()
 def available(self):return self.agent.bridge.ready() and self.agent.bridge.status().get('phoneControl') is True
 def ident(self,serial,owner):
  key=self.agent.tokens.get(owner,{}).get('digest','')
  return 'phone-'+hmac.new(key.encode(),serial.encode(),hashlib.sha256).hexdigest()[:32]
 def native_status(self):
  if not self.available():raise AgentError('phoneUnavailable',503)
  value=self.agent.bridge.call('phone.status',{},timeout=25)
  if not isinstance(value.get('devices'),list) or not isinstance(value.get('running'),bool):raise AgentError('processingFailed')
  return value
 def public(self,value,owner):
  devices=[]
  for item in value.get('devices',[])[:100]:
   if not isinstance(item,dict) or not serial_valid(item.get('serial')) or item.get('status') not in ('device','unauthorized','offline') or item.get('transport') not in ('usb','wifi'):continue
   devices.append({'id':self.ident(item['serial'],owner),'label':str(item.get('label','Galaxy') if item.get('label')!=item['serial'] else 'Galaxy')[:160],'transport':item['transport'],'status':item['status']})
  options={**DEFAULT_OPTIONS};provided=value.get('options');provided=provided if isinstance(provided,dict) else {}
  for key,allowed in OPTIONS.items():
   if provided.get(key) in allowed:options[key]=provided[key]
  if isinstance(provided.get('clipboard'),bool):options['clipboard']=provided['clipboard']
  active=value.get('activeSerial');active_id=self.ident(active,owner) if serial_valid(active) else None
  result={'available':value.get('available') is True,'devices':devices,'running':value.get('running') is True,'activeDeviceId':active_id,'options':options}
  if value.get('errorCode') in ('phoneUnavailable','phoneStartFailed','phoneDeviceMissing','phoneUnauthorized'):result['errorCode']=value['errorCode']
  return result
 def status(self,owner):return self.public(self.native_status(),owner)
 def action(self,operation,body,owner):
  if operation not in ('pair','connect','start','stop','keyboard-settings') or not isinstance(body,dict):raise AgentError('invalidRequest')
  keys={'pair':{'address','code'},'connect':{'address'},'start':{'deviceId','keyboard','mouse','audio','clipboard'},'stop':set(),'keyboard-settings':{'deviceId'}}[operation]
  if set(body)-keys:raise AgentError('invalidRequest')
  args={};native='phone.'+('keyboard' if operation=='keyboard-settings' else operation)
  if operation in ('pair','connect'):
   if not lan_address(body.get('address')):raise AgentError('invalidRequest')
   args['address']=body['address']
  if operation=='pair':
   if not isinstance(body.get('code'),str) or not re.fullmatch(r'[0-9]{6}',body['code']):raise AgentError('invalidRequest')
   args['code']=body['code']
  if operation in ('start','keyboard-settings'):
   if not isinstance(body.get('deviceId'),str) or not re.fullmatch(r'phone-[a-f0-9]{32}',body['deviceId']):raise AgentError('invalidRequest')
  if operation=='start':
   for key,allowed in OPTIONS.items():
    args[key]=body.get(key,DEFAULT_OPTIONS[key])
    if not isinstance(args[key],str) or args[key] not in allowed:raise AgentError('invalidRequest')
   args['clipboard']=body.get('clipboard',True)
   if not isinstance(args['clipboard'],bool):raise AgentError('invalidRequest')
  if not self.lock.acquire(blocking=False):raise AgentError('busy',409)
  try:
   if not self.available():raise AgentError('phoneUnavailable',503)
   if operation in ('start','keyboard-settings'):
    status=self.native_status();selected=next((item for item in status['devices'] if isinstance(item,dict) and serial_valid(item.get('serial')) and self.ident(item['serial'],owner)==body['deviceId']),None)
    if not selected:raise AgentError('phoneDeviceMissing',404)
    if selected.get('status')!='device':raise AgentError('phoneUnauthorized',409)
    if operation=='start' and status['running']:raise AgentError('phoneAlreadyRunning',409)
    args['serial']=selected['serial']
   result=self.agent.bridge.call(native,args,timeout=35 if operation=='pair' else 30)
   if result.get('success') is not True:raise AgentError('processingFailed')
   # Success/refresh events stay with the approved origin; never expose the pairing code or raw ADB output.
   self.agent.emit({'type':'phone','changed':True},owner)
   return {'success':True}
  finally:self.lock.release()

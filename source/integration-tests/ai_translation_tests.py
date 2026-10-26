"""Synthetic, isolated SIWC/translation contracts. Network/native selection mocked explicitly."""
import copy,io,json,os,sys,tempfile,threading,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'agent'),str(root/'engine/deps-agent/win64')]
from common import AgentError
from ai_translate import AITranslate,TRANSLATION,REPLY_SCHEMA,IMAGE_SCHEMA,validate_result,POLICY,IMAGE_POLICY
from chatgpt_account import ChatGPTAccount,AUTH,RESOURCE,PLAN_SCOPE
from PIL import Image

def result():return {'contentType':'conversation','originalLanguage':'ja','detectedReplyLanguage':'wrong','replyTarget':0,'messages':[{'speaker':'A','isMine':False,'originalText':'明日9:30','translatedText':'내일9:30','language':'ja','confidence':.99,'isTruncated':False}]}
def stream(events):return io.BytesIO(b''.join(('data: '+json.dumps(e)+'\n\n').encode() for e in events))
def completed(value):return {'type':'response.completed','response':{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}}
class AITests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.ai=AITranslate(self.path,None);self.account=self.ai.account
  self.account.data={'active':'A','accounts':{'A':{'client_id':'fixture-client','subject':'fixture-user','scopes':[PLAN_SCOPE],'access_token':'secret-access','refresh_token':'secret-refresh','expires_at':time.time()+3600}}}
  self.account.models=[{'id':POLICY['model'],'vision':True,'verified':False,'name':'Luna','reasoningLevels':['low','medium']}]
  self.job={'id':'test-job','kind':'capture','status':'running','error':'','result':None,'received':0,'created':time.monotonic(),'cancel':threading.Event(),'generation':0,'settings':{'model':'auto','reasoning':'recommended','language':'ko'},'stage':'capture','timings':{}}
 def tearDown(self):
  self.ai.clear()
  if self.account.keychain is not None:self.account.keychain.delete()
  self.temp.cleanup()
 def infer(self,events):
  self.account.raw=Mock(return_value=stream(events));return self.ai.infer(self.job,'instructions',[{'type':'input_text','text':'SENSITIVE'}],TRANSLATION,True)
 def test_complete_request_is_single_store_false_streaming_and_account_model(self):
  value,model=self.infer([completed(result())]);self.assertEqual(model,POLICY['model']);self.assertEqual(value['detectedReplyLanguage'],'ja');self.assertTrue(self.account.models[0]['verified'])
  args=self.account.raw.call_args.args;payload=json.loads(args[2]);self.assertEqual(args[0],RESOURCE+'/responses');self.assertFalse(payload['store']);self.assertTrue(payload['stream']);self.assertEqual(len(payload['input']),1);self.assertNotIn('api_key',payload);self.assertEqual(payload['reasoning']['effort'],POLICY['reasoning'])
 def test_partial_json_is_never_a_completed_result(self):
  with self.assertRaisesRegex(AgentError,'aiIncomplete'):self.infer([{'type':'response.output_text.delta','delta':json.dumps(result())}])
 def test_late_stream_failure_discards_partial_content(self):
  with self.assertRaisesRegex(AgentError,'aiQuota'):self.infer([{'type':'response.output_text.delta','delta':'secret partial'}, {'type':'response.failed','response':{'error':{'code':'subscription_sharing_usage_limit_exceeded'}}}])
 def test_incomplete_response_is_rejected(self):
  with self.assertRaisesRegex(AgentError,'aiIncomplete'):self.infer([{'type':'response.incomplete'}])
 def test_invalid_schema_is_rejected(self):
  value=result();value['messages'][0]['confidence']=float('nan')
  with self.assertRaisesRegex(AgentError,'aiInvalidResponse'):self.infer([completed(value)])
 def test_no_silent_model_fallback(self):
  self.account.models[0]['id']='other-account-model'
  with self.assertRaisesRegex(AgentError,'aiRecommendedUnavailable'):self.infer([completed(result())])
  self.account.raw.assert_not_called()
 def test_image_translation_uses_requested_sol_model_and_its_own_reasoning(self):
  self.account.models.append({'id':'gpt-6.1-sol','vision':True,'verified':False,'name':'GPT-6.1 Sol','reasoningLevels':['low','medium','high']})
  self.job['settings'].update(model=POLICY['model'],reasoning='none')
  self.account.raw=Mock(return_value=stream([completed({'regions':[],'originalLanguage':None})]))
  value,model=self.ai.infer(self.job,'image instructions',[],IMAGE_SCHEMA,True)
  payload=json.loads(self.account.raw.call_args.args[2])
  self.assertEqual(model,'gpt-6.1-sol');self.assertEqual(payload['model'],'gpt-6.1-sol')
  self.assertEqual(payload['reasoning']['effort'],'medium');self.assertFalse(payload['store'])
  self.assertEqual(self.job['settings']['model'],POLICY['model'])
 def test_image_translation_never_falls_back_to_luna_when_sol_is_unavailable(self):
  self.account.raw=Mock()
  with self.assertRaisesRegex(AgentError,'aiImageModelUnavailable'):
   self.ai.infer(self.job,'image instructions',[],IMAGE_SCHEMA,True)
  self.account.raw.assert_not_called()
 def test_nonvision_model_is_not_used(self):
  self.account.models[0]['vision']=False
  with self.assertRaisesRegex(AgentError,'aiModelUnavailable'):self.infer([completed(result())])
 def test_models_are_not_fetched_each_translation(self):
  self.account.list_models=Mock();self.infer([completed(result())]);self.infer([completed(result())]);self.account.list_models.assert_not_called()
 def test_cancel_before_request_sends_nothing(self):
  self.job['cancel'].set()
  with self.assertRaisesRegex(AgentError,'cancelled'):self.infer([completed(result())])
  self.account.raw.assert_not_called()
 def test_account_switch_invalidates_session(self):
  self.account.generation=1
  with self.assertRaisesRegex(AgentError,'aiAccountChanged'):self.infer([completed(result())])
 def test_ambiguous_targets_remain_unselected(self):
  for field,value in [('isMine',True),('language',None),('confidence',.3)]:
   r=result();r['messages'][0][field]=value;self.assertIsNone(validate_result(r)['replyTarget'])
 def test_duplicate_frame_and_cancelled_job_cannot_receive_pixels(self):
  self.ai.jobs['test-job']=self.job;self.ai.accept_frame('test-job',b'image')
  with self.assertRaises(AgentError):self.ai.accept_frame('test-job',b'image')
  self.ai.cancel('test-job');self.assertIsNone(self.job['result'])
 def test_capture_frame_stays_memory_only_and_reply_reuses_text(self):
  png=io.BytesIO();Image.new('RGB',(32,20),'white').save(png,'PNG');self.ai.jobs[self.job['id']]=self.job
  def capture(op,args,*a,**kw):self.assertEqual(op,'capture.start');self.ai.accept_frame(args['aiJobId'],png.getvalue());return {'selectedAt':time.time()*1000,'overlayShownAt':time.time()*1000-100}
  self.ai.bridge=Mock();self.ai.bridge.call=capture;self.account.raw=Mock(return_value=stream([completed(result())]));self.ai._work(self.job,{})
  self.assertEqual(self.job['status'],'complete');self.assertNotIn('png',self.job);self.assertEqual(list(self.path.rglob('*.png')),[])
  replyjob={**self.job,'id':'reply','kind':'reply','status':'running','result':None};self.account.raw=Mock(return_value=stream([completed({'replyText':'はい','translatedText':'네'})]));self.ai._work(replyjob,{'sessionId':'test-job','target':0,'intent':'동의'})
  self.assertEqual(replyjob['status'],'complete');payload=json.loads(self.account.raw.call_args.args[2]);self.assertNotIn('input_image',json.dumps(payload));self.assertIn('replyLanguage',json.dumps(payload));self.assertNotIn('data:image',json.dumps(payload))
 def test_memory_sessions_expire_without_serialization(self):
  self.ai.sessions['old']={'created':time.monotonic()-901,'generation':0,'data':result()};self.ai.status();self.assertEqual(self.ai.sessions,{})
 def test_metrics_never_log_text_image_or_credentials(self):
  self.job.update(model=POLICY['model'],reasoning='low',result=result());self.job['timings']={'startedAt':1000,'overlayShownAt':1120,'selectedAt':2000,'requestStartedAt':2050,'firstResponseAt':2300,'completedAt':3000,'popupCompletedAt':3100};self.ai.record_performance(self.job)
  text=self.ai.performance_path.read_text();self.assertNotIn('明日',text);self.assertNotIn('secret',text);self.assertNotIn('speaker',text);self.assertEqual(self.ai.performance[0]['popupCompleteMs'],1100);self.assertEqual(self.ai.performance[0]['capturePrepareMs'],120)
 def test_dpapi_persistence_and_reload_no_plaintext(self):
  self.account.persist()
  if sys.platform=='darwin':self.assertFalse(self.account.path.exists());self.assertEqual(self.account.keychain.service,'com.kio.control.chatgpt')
  else:self.assertNotIn(b'secret-refresh',self.account.path.read_bytes())
  loaded=ChatGPTAccount(self.path);self.assertEqual(loaded.access()[0],'secret-access')
 def test_token_refresh_rotates_and_persists(self):
  self.account.current()['expires_at']=0;self.account.token_request=Mock(return_value={'access_token':'new-access','refresh_token':'new-refresh','token_type':'Bearer','scope':PLAN_SCOPE,'expires_in':3600});self.assertEqual(self.account.access()[0],'new-access');self.assertEqual(ChatGPTAccount(self.path).current()['refresh_token'],'new-refresh');self.account.access();self.account.token_request.assert_called_once()
 def test_login_scope_without_plan_does_not_start_inference(self):
  self.account.current()['scopes']=['openid']
  with self.assertRaisesRegex(AgentError,'aiPermission'):self.account.access()
 def test_endpoint_guard_refuses_nonofficial_hosts(self):
  for url in ['https://attacker.invalid/responses','http://api.openai.com/v1/responses','https://api.openai.com@attacker.invalid/','https://api.openai.com:8080/v1']:
   with self.assertRaisesRegex(AgentError,'aiInvalidEndpoint'):self.account.raw(url)
 def test_jwt_signature_nonce_audience_and_expiry(self):
  import jwt
  from cryptography.hazmat.primitives.asymmetric import rsa
  private=rsa.generate_private_key(public_exponent=65537,key_size=2048);key=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()));key.update(kid='test',use='sig');self.account.jwks_cache={'keys':[key]}
  claims={'iss':AUTH,'aud':'fixture-client','sub':'fixture-user','iat':int(time.time()),'exp':int(time.time())+60,'nonce':'expected'}
  token=jwt.encode(claims,private,algorithm='RS256',headers={'kid':'test'});self.assertEqual(self.account.validate(token,'fixture-client','expected')['sub'],'fixture-user')
  for client,nonce in [('wrong','expected'),('fixture-client','wrong')]:
   with self.assertRaisesRegex(AgentError,'aiInvalidIdentity'):self.account.validate(token,client,nonce)
  claims['exp']=int(time.time())-120;token=jwt.encode(claims,private,algorithm='RS256',headers={'kid':'test'})
  with self.assertRaisesRegex(AgentError,'aiInvalidIdentity'):self.account.validate(token,'fixture-client','expected')
 def test_disconnect_clears_tokens_preserves_registration(self):
  self.account.discovery=Mock(return_value={});self.account.disconnect();r=ChatGPTAccount(self.path).current();self.assertNotIn('access_token',r);self.assertNotIn('refresh_token',r);self.assertEqual(r['client_id'],'fixture-client')
if __name__=='__main__':unittest.main()

"""Smart scan memory/call-count/schema contracts; inference/native capture mocked."""
import sys,io,time,json,threading,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from ai_translate import AITranslate
from ai_smart_scan import SCHEMAS,validate,PROMPTS,validate_reply_language
from common import AgentError
from PIL import Image
class SmartTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.a=AITranslate(Path(self.temp.name),None);b=io.BytesIO();Image.new('RGB',(80,30),'yellow').save(b,format='PNG');self.png=b.getvalue();self.a.scans['scan']={'png':self.png,'created':time.monotonic(),'generation':0,'results':{}}
  self.job={'id':'job','kind':'scan','status':'running','stage':'capture','error':'','result':None,'received':0,'cancel':threading.Event(),'generation':0,'created':time.monotonic(),'settings':{'model':'auto','reasoning':'recommended','language':'ko'},'timings':{}}
 def tearDown(self):self.a.clear();self.temp.cleanup()
 def test_mac_local_scan_without_login_or_consent_reaches_native_capture(self):
  self.a.account.access=Mock(side_effect=AssertionError('local selection must not authenticate'))
  self.a.infer=Mock(side_effect=AssertionError('local selection must not transmit'))
  done=threading.Event()
  def capture(op,args,*unused,**kwargs):
   self.assertEqual(op,'capture.start');self.assertTrue(args['ephemeral'])
   self.a.accept_frame(args['aiJobId'],self.png);done.set();return {}
  self.a.bridge=Mock();self.a.bridge.call=capture
  with patch('ai_translate.sys.platform','darwin'):
   started=self.a.submit('scan',{})
   self.assertTrue(done.wait(3))
   for _ in range(100):
    result=self.a.job(started['id'])
    if result['status']!='running':break
    time.sleep(.01)
  self.assertEqual(result['status'],'complete',result)
  self.a.account.access.assert_not_called();self.a.infer.assert_not_called()
  self.assertEqual(self.a.scan(started['id'])['png'],self.png)
  with self.assertRaisesRegex(AgentError,'aiConsentRequired'):self.a.submit('analyze',{'scanId':started['id'],'task':'extract'})
  self.a.settings['consent']=True
  self.a.account.access=Mock(side_effect=AgentError('aiNotConnected'))
  with self.assertRaisesRegex(AgentError,'aiNotConnected'):self.a.submit('analyze',{'scanId':started['id'],'task':'extract'})
 def test_scan_finishes_without_any_gpt_or_model_call_and_keeps_only_selected_png(self):
  self.a.infer=Mock(side_effect=AssertionError('must not call GPT'));self.a.account.list_models=Mock(side_effect=AssertionError('must not discover'))
  def capture(*args,**kwargs):self.job['png']=self.png;return {'selectedAt':time.time()*1000,'overlayShownAt':time.time()*1000}
  self.a.bridge=Mock();self.a.bridge.call=capture;self.a._work(self.job,{})
  self.assertEqual(self.job['status'],'complete');self.assertEqual(self.job['result'],{'scanId':'job','width':80,'height':30});self.assertEqual(self.a.scans['job']['png'],self.png);self.assertNotIn('png',self.job);self.assertFalse(list(Path(self.temp.name).rglob('*.png')))
 def test_same_scan_cached_result_no_second_call_and_other_feature_reuses_png(self):
  self.a.infer=Mock(return_value=({'text':'hello','uncertain':[]},'gpt-6-luna'));body={'scanId':'scan','task':'extract'}
  first=self.a.analyze(self.job,body);again=self.a.analyze(self.job,body);self.assertEqual(first,again);self.assertEqual(self.a.infer.call_count,1)
  image=self.a.infer.call_args.args[2][1];self.a.infer.return_value=({'points':['hello'],'uncertain':[]},'gpt-6-luna');self.a.analyze(self.job,{'scanId':'scan','task':'summary'});self.assertEqual(self.a.infer.call_args.args[2][1],image);self.assertEqual(self.a.infer.call_count,2)
 def test_followup_uses_only_last_result_and_does_not_accumulate_chat_history(self):
  self.a.infer=Mock(return_value=({'text':'first','uncertain':[]},'gpt-6-luna'));body={'scanId':'scan','task':'extract'};self.a.analyze(self.job,body)
  self.a.infer.return_value=({'text':'second','uncertain':[]},'gpt-6-luna');self.a.analyze(self.job,{**body,'instruction':'preserve line breaks'})
  context=json.loads(self.a.infer.call_args.args[2][0]['text']);self.assertEqual(context['previousResult']['text'],'first');self.assertNotIn('history',context)
  self.a.analyze(self.job,{**body,'instruction':'one more'});context=json.loads(self.a.infer.call_args.args[2][0]['text']);self.assertEqual(context['previousResult']['text'],'second')
 def test_changing_base_language_invalidates_cached_output(self):
  self.a.infer=Mock(return_value=({'text':'hello','uncertain':[]},'gpt-6-luna'));body={'scanId':'scan','task':'extract'};self.a.analyze(self.job,body);self.job['settings']['language']='ja';self.a.analyze(self.job,body);self.assertEqual(self.a.infer.call_count,2)
 def test_expiry_account_switch_and_close_clear_image(self):
  self.a.scans['scan']['created']-=901;self.a.prune();self.assertFalse(self.a.scans)
  self.a.scans['other']={'created':time.monotonic(),'generation':-1,'png':self.png};self.a.prune();self.assertFalse(self.a.scans)
  self.a.scans['other']={'created':time.monotonic(),'generation':0,'png':self.png};self.a.clear();self.assertFalse(self.a.scans)
 def test_nine_tasks_and_strict_schemas_reject_missing_extra_and_wrong_types(self):
  self.assertEqual(len(PROMPTS),9)
  for schema in SCHEMAS.values():
   for value in ({},{'extra':'bad'},[]):
    with self.assertRaises(AgentError):validate(value,schema)
 def test_ambiguous_writing_cannot_return_a_guessed_reply(self):
  self.a.infer=Mock(return_value=({'text':'guessed','meaning':'guessed','language':None,'needsTarget':True,'uncertain':['Choose recipient']},'gpt-6-luna'))
  value=self.a.analyze(self.job,{'scanId':'scan','task':'write'});self.assertEqual(value['text'],'');self.assertTrue(value['needsTarget'])
 def test_cancellation_sends_no_request(self):
  self.job['cancel'].set();self.a.infer=Mock()
  with self.assertRaisesRegex(AgentError,'cancelled'):self.a.analyze(self.job,{'scanId':'scan','task':'extract'})
  self.a.infer.assert_not_called()
 def test_wrong_script_and_non_code_language_are_not_successful_replies(self):
  with self.assertRaises(AgentError):validate_reply_language({'language':'en','text':'감사하지만 내일 참석할 수 없습니다.'})
  with self.assertRaises(AgentError):validate({'language':'영어','text':'Hello','meaning':'안녕','needsTarget':False,'uncertain':[]},SCHEMAS['write'])
  validate_reply_language({'language':'en','text':'Thank you, Alice. I cannot attend tomorrow.'})
if __name__=='__main__':unittest.main()

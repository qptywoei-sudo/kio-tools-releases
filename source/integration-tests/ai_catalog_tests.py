"""Account catalog isolation and full reasoning menus; no external requests."""
import io,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r/'agent'),str(r/'engine/deps-agent/win64')]
from ai_catalog import model_catalog
from chatgpt_account import ChatGPTAccount,PLAN_SCOPE
from ai_translate import AITranslate,TRANSLATION,POLICY
from common import AgentError

def catalog(ident='gpt-6-luna',efforts=('low','medium','high','xhigh','max','ultra','future-effort')):
 return [{'slug':ident,'display_name':'Account model','visibility':'list','input_modalities':['text','image'],'default_reasoning_level':'medium','supported_reasoning_levels':[{'effort':e,'description':'Provider description '+e} for e in efforts]}]

class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.a=AITranslate(Path(self.temp.name),None);self.c=self.a.account
  row={'client_id':'fixture','subject':'fixture','scopes':[PLAN_SCOPE],'access_token':'fixture-not-a-real-token','expires_at':time.time()+3600}
  self.c.data={'active':'A','accounts':{'A':dict(row),'B':dict(row)}};self.c.persist=Mock()
 def tearDown(self):self.a.clear();self.temp.cleanup()
 def test_preserves_server_order_defaults_descriptions_and_future_levels(self):
  rows=catalog()+catalog('future-model',('none','minimal','high'))+[{'slug':'hidden','visibility':'hide'}]
  models=model_catalog(rows);self.assertEqual([m['id'] for m in models],['gpt-6-luna','future-model'])
  self.assertEqual(models[0]['reasoningLevels'],['low','medium','high','xhigh','max','ultra','future-effort'])
  self.assertEqual(models[0]['defaultReasoning'],'medium');self.assertEqual(models[0]['reasoningDescriptions']['ultra'],'Provider description ultra')
 def test_invalid_duplicate_levels_and_rows_do_not_create_choices(self):
  rows=catalog();rows[0]['supported_reasoning_levels']=['low','low',None,{},'HIGH','bad value',{'effort':'max'}]
  self.assertEqual(model_catalog(rows+rows)[0]['reasoningLevels'],['low','max']);self.assertEqual(len(model_catalog(rows+rows)),1)
 def test_account_switch_clears_catalog_and_verification_including_switch_back(self):
  self.c.json=Mock(return_value={'models':catalog()});self.c.list_models();self.c.models[0]['verified']=True
  self.c.select('B');self.assertEqual(self.c.models,[])
  self.c.json.return_value={'models':catalog('other-account-model',('high',))};self.c.list_models()
  self.assertEqual(self.c.models[0]['id'],'other-account-model');self.assertFalse(self.c.models[0]['verified'])
  self.c.select('A');self.assertEqual(self.c.models,[])
 def test_late_catalog_for_old_account_cannot_publish_into_new_account(self):
  entered=threading.Event();release=threading.Event();errors=[]
  def response(*args,**kwargs):entered.set();release.wait(3);return {'models':catalog()}
  self.c.json=response
  def load():
   try:self.c.list_models()
   except AgentError as e:errors.append(e.code)
  thread=threading.Thread(target=load);thread.start();self.assertTrue(entered.wait(2));self.c.select('B');release.set();thread.join(3)
  self.assertEqual(errors,['aiAccountChanged']);self.assertEqual(self.c.models,[])
 def test_every_provided_effort_can_be_saved_and_unprovided_is_rejected(self):
  self.c.models=model_catalog(catalog())
  for effort in self.c.models[0]['reasoningLevels']:
   if effort in self.c.models[0].get('reasoningUnavailable',{}):
    with self.assertRaisesRegex(AgentError,'aiReasoningUnavailable'):self.a.configure({'reasoning':effort})
    continue
   self.a.configure({'reasoning':effort});self.assertEqual(self.a.settings['reasoning'],effort)
  for effort in ('none','unbounded'):
   with self.assertRaisesRegex(AgentError,'aiReasoningUnavailable'):self.a.configure({'reasoning':effort})
  self.a.configure({'reasoning':'model-default'});self.a.configure({'reasoning':'recommended'})
 def test_supported_effort_and_catalog_default_are_sent_exactly(self):
  self.c.models=model_catalog(catalog());result={'contentType':'document','originalLanguage':'en','detectedReplyLanguage':None,'replyTarget':None,'messages':[]}
  event={'type':'response.completed','response':{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(result)}]}]}}
  for effort in ('high','xhigh','max','future-effort','model-default','recommended'):
   self.c.raw=Mock(return_value=io.BytesIO(('data: '+json.dumps(event)+'\n\n').encode()))
   job={'id':'test','status':'running','cancel':threading.Event(),'generation':self.c.generation,'settings':{'model':'auto','reasoning':effort,'language':'ko'},'timings':{}}
   self.a.infer(job,'test',[{'type':'input_text','text':'fixture'}],TRANSLATION)
   payload=json.loads(self.c.raw.call_args.args[2])
   if effort=='model-default':self.assertEqual(payload['reasoning']['effort'],'medium')
   else:self.assertEqual(payload['reasoning']['effort'],POLICY['reasoning'] if effort=='recommended' else effort)
 def test_global_benchmark_none_is_not_injected_into_another_accounts_options(self):
  self.c.models=model_catalog(catalog(efforts=('low','high')))
  job={'id':'test','status':'running','cancel':threading.Event(),'generation':0,'settings':{'model':'auto','reasoning':'none'},'timings':{}}
  self.c.raw=Mock()
  with self.assertRaisesRegex(AgentError,'aiReasoningUnavailable'):self.a.infer(job,'test',[],TRANSLATION)
  self.c.raw.assert_not_called()
 def test_unknown_provider_default_is_left_to_service_without_inventing_an_effort(self):
  self.c.models=model_catalog(catalog('other-model'));self.c.models[0].pop('defaultReasoning')
  result={'contentType':'document','originalLanguage':'en','detectedReplyLanguage':None,'replyTarget':None,'messages':[]}
  event={'type':'response.completed','response':{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(result)}]}]}}
  for effort in ('model-default','recommended'):
   self.c.raw=Mock(return_value=io.BytesIO(('data: '+json.dumps(event)+'\n\n').encode()))
   job={'id':'test','status':'running','cancel':threading.Event(),'generation':0,'settings':{'model':'other-model','reasoning':effort},'timings':{}}
   self.a.infer(job,'test',[],TRANSLATION);self.assertNotIn('reasoning',json.loads(self.c.raw.call_args.args[2]))
 def test_delegation_mode_stays_visible_but_is_rejected_before_direct_request(self):
  self.c.models=model_catalog(catalog());self.assertIn('ultra',self.c.models[0]['reasoningLevels']);self.assertIn('ultra',self.c.models[0]['reasoningUnavailable'])
  job={'id':'test','status':'running','cancel':threading.Event(),'generation':0,'settings':{'model':'auto','reasoning':'ultra'},'timings':{}};self.c.raw=Mock()
  with self.assertRaisesRegex(AgentError,'aiReasoningUnavailable'):self.a.infer(job,'test',[],TRANSLATION)
  self.c.raw.assert_not_called()

if __name__=='__main__':unittest.main()

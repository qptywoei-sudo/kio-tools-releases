"""Reply selection and settings regression: no network or personal credentials."""
from pathlib import Path
import sys,tempfile,threading,time,json,unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from ai_translate import AITranslate
from common import AgentError

class AutomaticReplyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.a=AITranslate(Path(self.temp.name),None)
  self.data={'sessionId':'session','baseLanguage':'ko','replyTarget':0,'messages':[{'speaker':'An','originalText':'Xin chào','translatedText':'안녕하세요','isMine':False,'language':'vi','confidence':.99},{'speaker':'Alex','originalText':'Hello','translatedText':'안녕하세요','isMine':False,'language':'en','confidence':.99}]}
  self.a.sessions['session']={'data':self.data,'generation':0,'created':time.monotonic()}
  self.job={'id':'reply','kind':'reply','status':'running','stage':'reply','error':'','result':None,'received':0,'cancel':threading.Event(),'generation':0,'settings':{'model':'auto','reasoning':'recommended','language':'ko'},'timings':{}}
  self.a.infer=Mock(return_value=({'replyText':'Hello, Alex.','translatedText':'안녕하세요, 알렉스.'},'gpt-6-luna'))
 def tearDown(self):self.a.clear();self.temp.cleanup()
 def test_automatic_draft_reuses_selected_target_language_and_context_once(self):
  self.a._work(self.job,{'sessionId':'session','target':1,'intent':''})
  self.assertEqual(self.job['status'],'complete');self.assertEqual(self.job['result']['replyLanguage'],'en');self.a.infer.assert_called_once()
  content=self.a.infer.call_args.args[2];self.assertEqual(len(content),1);self.assertEqual(content[0]['type'],'input_text');context=json.loads(content[0]['text']);self.assertEqual(context['target'],1);self.assertEqual(context['replyLanguage'],'en');self.assertEqual(context['intent'],'');self.assertEqual(context['messages'],self.data['messages'])
 def test_unknown_language_does_not_send_a_reply_request(self):
  self.data['messages'][1]['language']=None;self.a._work(self.job,{'sessionId':'session','target':1,'intent':''})
  self.assertEqual(self.job['error'],'aiReplyTargetRequired');self.a.infer.assert_not_called()
 def test_medium_can_be_selected_but_unrecognized_efforts_are_rejected(self):
  self.a.configure({'reasoning':'medium'});self.assertEqual(self.a.settings['reasoning'],'medium')
  self.a.configure({'reasoning':'recommended'});self.assertEqual(self.a.settings['reasoning'],'recommended')
  with self.assertRaises(AgentError):self.a.configure({'reasoning':'unbounded'})
if __name__=='__main__':unittest.main()

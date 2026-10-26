"""Account connection contracts with an in-memory cloud and no OS vault/network."""
import copy, json, sys, threading, time, unittest, urllib.parse, uuid
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from chatgpt_account import ChatGPTAccount, PLAN_SCOPE
from common import AgentError, NativeBridge, atomic_json
import tempfile

class Cloud:
    def __init__(self): self.owner='fixture-kio-user';self.signed=True;self.revision=-1;self.grant=None;self.calls=[]
    def cloud(self,route,body=None,method='POST',expected_user=None):
        if not self.signed: raise AgentError('ACCOUNT_REQUIRED')
        if expected_user!=self.owner: raise AgentError('accountChanged')
        self.calls.append(route);op=route.rsplit('/',1)[-1]
        if op=='connect':
            if body['revision']!=self.revision: raise AgentError('aiConnectionChanged')
            self.grant=copy.deepcopy(body['grant']);self.revision+=1
        if op=='disconnect': self.grant=None;self.revision+=1;return {'chatgpt':{'disconnected':True,'allDevices':True}}
        if op=='access' and not self.grant: raise AgentError('aiNotConnected')
        value={'connected':self.grant is not None,'persistent':self.grant is not None,'revision':self.revision,'accountId':'fixture-openai-user' if self.grant else '', 'email':'fixture@example.invalid' if self.grant else ''}
        if op=='access': value.update(access_token=self.grant['access_token'],client_id=self.grant['client_id'],scopes=[PLAN_SCOPE])
        return {'chatgpt':value}

def local(cloud,legacy=False):
    account=ChatGPTAccount.__new__(ChatGPTAccount)
    account.lock=threading.RLock();account.pending=None;account.error='';account.generation=0;account.models=[]
    account.kio=None;account.kio_user='';account.shared_status=None;account.shared_checked=0
    account.data={'active':'A','accounts':{'A':{'client_id':'fixture-client','subject':'fixture-openai-user','email':'fixture@example.invalid'}}}
    if legacy: account.data['accounts']['A'].update(access_token='private-fixture-access',refresh_token='private-fixture-refresh',id_token='private-fixture-identity',scopes=[PLAN_SCOPE],expires_at=time.time()+3600)
    account.persist=lambda:None;account.bind_kio(cloud,cloud.owner);return account

class SharedConnectionTests(unittest.TestCase):
    def test_legacy_grant_migrates_once_and_refresh_credentials_never_enter_status(self):
        cloud=Cloud();account=local(cloud,True)
        state=account.status();self.assertTrue(state['connected']);self.assertTrue(state['persistent'])
        for key in ['access_token','refresh_token','id_token']:self.assertNotIn(key,account.current());self.assertNotIn(key,json.dumps(state))
        self.assertEqual(account.access()[0],'private-fixture-access');account.status()
        self.assertEqual(cloud.calls.count('/control/chatgpt/connect'),1)
    def test_other_installation_and_relogin_restore_same_cloud_connection(self):
        cloud=Cloud();local(cloud,True).status();second=local(cloud)
        self.assertTrue(second.status()['connected']);cloud.signed=False
        with self.assertRaisesRegex(AgentError,'aiNetwork'):second.access()
        cloud.signed=True;self.assertEqual(second.access()[0],'private-fixture-access')
        self.assertEqual(cloud.calls.count('/control/chatgpt/connect'),1)
    def test_disconnect_from_either_installation_blocks_the_other_without_stale_reupload(self):
        cloud=Cloud();first=local(cloud,True);first.status();second=local(cloud,True)
        self.assertTrue(second.status()['connected']);first.disconnect()
        with self.assertRaisesRegex(AgentError,'aiNotConnected'):second.access()
        self.assertNotIn('refresh_token',second.current());self.assertEqual(cloud.calls.count('/control/chatgpt/connect'),1)
    def test_wrong_kio_identity_cannot_fetch_or_publish_another_profiles_grant(self):
        cloud=Cloud();first=local(cloud,True);first.status();cloud.owner='other-kio-user'
        with self.assertRaisesRegex(AgentError,'aiNetwork'):first.access()
    def test_reconnect_on_another_installation_reuses_the_saved_registration(self):
        cloud=Cloud();local(cloud,True).status();account=local(cloud)
        account.data={'accounts':{},'active':''};account.host='urn:uuid:'+str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            account.state=Path(root)/'chatgpt';account.state.mkdir();account._callback=lambda pending:None
            with patch('chatgpt_account.webbrowser.open',return_value=True) as browser:
                account.connect('fixture-openai-user')
                query=urllib.parse.parse_qs(urllib.parse.urlparse(browser.call_args.args[0]).query)
                self.assertEqual(query['client_id'],['fixture-client'])
                self.assertNotIn('agent_name_hint',query)
            account.pending['server'].server_close()
    def test_native_hosts_have_distinct_command_queues_even_with_same_user_state(self):
        with tempfile.TemporaryDirectory() as root:
            old=NativeBridge(root);a=NativeBridge(root,101);b=NativeBridge(root,202)
            atomic_json(a.root/'status.json',{'pid':101,'updatedAt':time.time()})
            atomic_json(old.root/'status.json',{'pid':999,'updatedAt':time.time()})
            self.assertEqual(a.status()['pid'],101);self.assertFalse(b.ready())
            self.assertNotEqual(a.root,b.root);self.assertNotEqual(a.root,old.root)

if __name__=='__main__':unittest.main()

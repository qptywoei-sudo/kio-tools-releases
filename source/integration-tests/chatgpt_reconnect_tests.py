"""SIWC reconnect and cloud handoff regressions with synthetic grants only."""
import json, sys, tempfile, threading, time, unittest, urllib.parse, uuid
from pathlib import Path
from unittest.mock import Mock, patch

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'agent'),str(root/'integration-tests')]
from chatgpt_account import ChatGPTAccount, PLAN_SCOPE, RESOURCE, failure
from common import AgentError
from shared_connection_tests import Cloud, local

class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.cloud=Cloud();self.account=local(self.cloud)
        self.account.state=Path(self.temp.name)/'chatgpt';self.account.state.mkdir()
        self.account.host='urn:uuid:'+str(uuid.uuid4())
        self.account.persist=Mock()
        self.original_callback=self.account._callback
        self.account._callback=Mock()
    def tearDown(self):
        if self.account.pending:
            self.account.pending['cancel'].set();self.account.pending['server'].server_close()
        self.temp.cleanup()
    def authorize(self,*args,**kwargs):
        with patch('chatgpt_account.webbrowser.open',return_value=True) as browser:
            self.account.connect(*args,**kwargs)
        return urllib.parse.parse_qs(urllib.parse.urlparse(browser.call_args.args[0]).query)
    def test_successful_cloud_handoff_does_not_read_scopes_after_credentials_are_stripped(self):
        account=self.account
        done=threading.Event();done.set()
        pending={'cloudRevision':-1,'done':done,'cancel':threading.Event(),'server':Mock(),'previous':None,
                 'query':{'code':['fixture-code'],'client_id':['fixture-client']},'verifier':'fixture-verifier','nonce':'fixture-nonce','redirect':'http://127.0.0.1:12345/auth/callback'}
        account.pending=pending;account.error='aiLoginFailed'
        account.token_request=Mock(return_value={'access_token':'private-fixture-access','refresh_token':'private-fixture-refresh','id_token':'private-fixture-id','token_type':'Bearer','scope':PLAN_SCOPE,'expires_in':3600})
        account.validate=Mock(return_value={'sub':'fixture-openai-user','email':'fixture@example.invalid'})
        self.original_callback(pending)
        self.assertEqual(account.error,'');self.assertIsNone(account.pending)
        self.assertTrue(account.status()['connected']);self.assertTrue(account.status()['planApproved'])
        self.assertEqual(account.generation,2) # initial KIO profile binding plus successful sign-in
        self.assertNotIn('scopes',account.current());self.assertNotIn('access_token',account.current())
        self.assertEqual(self.cloud.grant['scopes'],[PLAN_SCOPE])
        self.assertNotIn('private-fixture',json.dumps(account.status()))
        pending['server'].server_close.assert_called_once()
    def test_default_reconnect_keeps_local_issued_client_and_identity_hints(self):
        account=self.account;account.kio=None
        account.current().update(id_token='private-fixture-id',scopes=[PLAN_SCOPE])
        query=self.authorize()
        self.assertEqual(query['client_id'],['fixture-client'])
        self.assertEqual(query['id_token_hint'],['private-fixture-id'])
        self.assertEqual(query['login_hint'],['fixture@example.invalid'])
        self.assertNotIn('agent_name_hint',query);self.assertNotIn('prompt',query)
    def test_new_installation_default_reconnect_uses_cloud_registration(self):
        local(self.cloud,True).status();self.account.data={'accounts':{},'active':''}
        query=self.authorize()
        self.assertEqual(query['client_id'],['fixture-client'])
        self.assertNotIn('agent_name_hint',query);self.assertNotIn('prompt',query)
        self.assertIn('resource.invoke',query['scope'][0].split())
        self.assertIn(PLAN_SCOPE,query['scope'][0].split())
        self.assertEqual(query['resource'],[RESOURCE])
    def test_declined_legacy_grant_does_not_block_same_client_reconsent(self):
        self.account.current().update(access_token='private-fixture-access',refresh_token='private-fixture-refresh',scopes=['openid'],expires_at=time.time()+3600)
        query=self.authorize()
        self.assertEqual(query['client_id'],['fixture-client'])
        self.assertEqual(query['prompt'],['consent'])
        self.assertNotIn('agent_name_hint',query)
        self.assertIsNone(self.cloud.grant)
        self.assertEqual(self.account.current()['client_id'],'fixture-client')
    def test_invalid_grant_legacy_refresh_does_not_block_same_client_reauthorization(self):
        self.account.current().update(access_token='private-fixture-expired',refresh_token='private-fixture-refresh',scopes=[PLAN_SCOPE],expires_at=0)
        self.account.token_request=Mock(side_effect=AgentError(failure('invalid_grant',400)))
        query=self.authorize()
        self.assertEqual(query['client_id'],['fixture-client'])
        self.assertNotIn('agent_name_hint',query);self.assertNotIn('prompt',query)
        self.account.token_request.assert_called_once()
        self.assertIsNone(self.cloud.grant)
        self.assertEqual(self.account.current()['subject'],'fixture-openai-user')
    def test_temporary_legacy_refresh_failure_preserves_grant_without_starting_oauth(self):
        self.account.current().update(access_token='private-fixture-expired',refresh_token='private-fixture-refresh',scopes=[PLAN_SCOPE],expires_at=0)
        self.account.token_request=Mock(side_effect=AgentError('aiNetwork'))
        with patch('chatgpt_account.webbrowser.open') as browser:
            with self.assertRaisesRegex(AgentError,'aiNetwork'):self.account.connect()
        browser.assert_not_called();self.assertIsNone(self.account.pending)
        self.assertEqual(self.account.current()['refresh_token'],'private-fixture-refresh')
        self.assertIsNone(self.cloud.grant)
    def test_new_account_is_the_only_explicit_dynamic_registration_path(self):
        local(self.cloud,True).status()
        query=self.authorize(new_account=True)
        self.assertEqual(query['client_id'],['dynamic_agent_client'])
        self.assertEqual(query['agent_name_hint'],['Bogo Tools'])
        self.assertNotIn('id_token_hint',query);self.assertNotIn('login_hint',query)
    def test_missing_plan_permission_requests_consent_with_same_registration(self):
        self.account.kio=None;self.account.current()['scopes']=['openid']
        query=self.authorize()
        self.assertEqual(query['client_id'],['fixture-client'])
        self.assertEqual(query['prompt'],['consent']);self.assertNotIn('force_reconsent',query)
    def test_permission_recovery_requests_consent_without_changing_client(self):
        local(self.cloud,True).status();self.account.error='aiPermission'
        query=self.authorize()
        self.assertEqual(query['client_id'],['fixture-client']);self.assertEqual(query['prompt'],['consent'])
    def test_invalid_new_account_argument_does_not_open_browser(self):
        with patch('chatgpt_account.webbrowser.open') as browser:
            for args in ({'new_account':'true'},{'new_account':True,'account_id':'A'}):
                with self.assertRaisesRegex(AgentError,'invalidRequest'):self.account.connect(**args)
            browser.assert_not_called()
    def test_cloud_access_without_plan_scope_stops_before_model_catalog_request(self):
        local(self.cloud,True).status();original=self.cloud.cloud
        def without_permission(route,*args,**kwargs):
            value=original(route,*args,**kwargs)
            if route.endswith('/access'):value['chatgpt']['scopes']=['openid']
            return value
        self.cloud.cloud=without_permission;self.account.json=Mock()
        with self.assertRaisesRegex(AgentError,'aiPermission'):self.account.list_models()
        self.account.json.assert_not_called();self.assertEqual(self.account.error,'aiPermission')
        state=self.account.status();self.assertTrue(state['connected']);self.assertFalse(state['planApproved'])
        self.cloud.cloud=original;self.account.json=Mock(return_value={'models':[]})
        state=self.account.list_models();self.assertTrue(state['planApproved']);self.assertEqual(state['error'],'')
    def test_catalog_failure_is_visible_and_successful_recheck_clears_it(self):
        local(self.cloud,True).status();self.account.models=[{'id':'old-model'}]
        self.account.json=Mock(side_effect=AgentError('aiReauthenticate'))
        with self.assertRaisesRegex(AgentError,'aiReauthenticate'):self.account.list_models()
        self.assertEqual(self.account.status()['error'],'aiReauthenticate');self.assertEqual(self.account.models,[])
        self.account.json=Mock(return_value={'models':[{'slug':'fixture-model','display_name':'Fixture','visibility':'list'}]})
        state=self.account.list_models()
        self.assertEqual(state['error'],'');self.assertEqual(state['models'][0]['id'],'fixture-model')
        self.assertEqual(self.account.json.call_args.kwargs['headers'],{'Authorization':'Bearer private-fixture-access'})
    def test_new_authorization_never_inherits_previous_plan_permission(self):
        previous={'scopes':[PLAN_SCOPE],'refresh_token':'private-fixture-refresh'}
        response={'access_token':'private-fixture-replacement','token_type':'Bearer','expires_in':3600}
        self.assertEqual(self.account.credentials(response,previous)['scopes'],[])
        self.assertEqual(self.account.credentials(response,previous,inherit_scopes=True)['scopes'],[PLAN_SCOPE])
    def test_direct_permission_errors_are_distinguished_from_account_ineligibility(self):
        self.assertEqual(failure('chatpass_v2_scope_not_authorized',403),'aiPermission')
        self.assertEqual(failure('chatpass_v2_invalid_authorization_context',403),'aiPermission')
        self.assertEqual(failure('subscription_sharing_user_not_eligible',403),'aiUnsupportedAccount')

if __name__=='__main__':unittest.main()

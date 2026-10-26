import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from chatgpt_account import failure
class PolicyTests(unittest.TestCase):
 def test_organization_denial_is_distinct_from_expired_login(self):
  self.assertEqual(failure('3p_delegated_access_policy_denied'),'aiOrganizationPolicy')
  self.assertEqual(failure('3p_delegated_access_policy_denied',403),'aiOrganizationPolicy')
  self.assertEqual(failure('subscription_sharing_user_not_eligible',403),'aiUnsupportedAccount')
  self.assertEqual(failure('access_denied'),'aiPermission')
  self.assertEqual(failure('invalid_grant',401),'aiReauthenticate')
if __name__=='__main__':unittest.main()

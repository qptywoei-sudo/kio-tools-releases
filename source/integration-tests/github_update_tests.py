import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from update_security import allowed_url
class GitHubUpdateTests(unittest.TestCase):
 def test_pinned_github_repo_and_asset_cdn(self):
  for u in ('https://github.com/qptywoei-sudo/kio-tools-releases/releases/download/tools-update-channel/latest.json','https://release-assets.githubusercontent.com/github-production-release-asset/test?sig=test','https://objects.githubusercontent.com/github-production-release-asset/test'):
   self.assertTrue(allowed_url(u),u)
 def test_deny_other_repo_http_credentials_and_host_lookalikes(self):
  for u in ('https://github.com/other/repo/releases/download/x/package.zip','http://github.com/qptywoei-sudo/kio-tools-releases/releases/download/a/x','https://github.com.evil.test/a','https://user:pass@github.com/qptywoei-sudo/kio-tools-releases/releases/download/a/x','https://github.com/qptywoei-sudo/kio-tools-releases/releases/download/a/../secret','https://github.com/qptywoei-sudo/kio-tools-releases/releases/download/a/%2e%2e/secret'):
   self.assertFalse(allowed_url(u),u)
 def test_packaged_feed_has_no_drive_dependency(self):
  config=json.loads((Path(__file__).resolve().parents[1]/'agent/update-channel.json').read_text())
  self.assertTrue(config['feedUrl'].startswith('https://github.com/qptywoei-sudo/kio-tools-releases/releases/download/'))
  self.assertTrue(allowed_url(config['feedUrl']))
 def test_other_account_is_not_an_update_source(self):
  self.assertFalse(allowed_url('https://github.com/qptywoei777-rgb/kio-native-apps/releases/download/tools-v4.6.16/package.zip'))
if __name__=='__main__':unittest.main()

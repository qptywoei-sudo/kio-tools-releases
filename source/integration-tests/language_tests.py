"""Six-language tests. All OAuth credentials/cloud responses are explicit mocks."""
import base64, hashlib, http.client, json, sys, tempfile, time, unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'agent'),str(ROOT/'engine'),str(ROOT/'integration-tests')]
from language import LANGUAGES, normalize, resolve, LanguagePreference, callback_page, text, system_languages
from kio_account import KIOAccount
from kio_account_tests import MemoryVault, CloudFixture, USER, LocalAccountApiTests

class LanguagePolicyTests(unittest.TestCase):
    def test_regional_and_script_tags(self):
        cases={'zh-CN':'zh-CN','zh-SG':'zh-CN','zh-Hans':'zh-CN','zh-Hans-TW':'zh-CN','zh':'zh-CN','zh-TW':'zh-TW','zh-HK':'zh-TW','zh-MO':'zh-TW','zh-Hant':'zh-TW','zh-Hant-CN':'zh-TW','ZH_hant_HK':'zh-TW','ko-KR':'ko','en-US':'en','en-GB':'en','vi-VN':'vi','ja-JP':'ja','fr-FR':None,'':None,None:None}
        for source,expected in cases.items():
            with self.subTest(source=source):self.assertEqual(normalize(source),expected)
    def test_precedence_and_unsupported_primary(self):
        self.assertEqual(resolve('vi',['ko-KR'],'ja'),('vi','user'))
        self.assertEqual(resolve(None,['fr-FR','ja-JP'],'ko'),('en','system'))
        self.assertEqual(resolve(None,[],'ja-JP'),('ja','account'))
        self.assertEqual(resolve(None,[],None),('en','fallback'))
    def test_six_first_runs_os_change_and_durable_independent_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            current=['vi-VN'];pref=LanguagePreference(folder,lambda:current.copy())
            for code in LANGUAGES:
                current[:]=[code];self.assertEqual(pref.snapshot()['language'],code)
                self.assertFalse(pref.path.exists(),'automatic detection must not persist a manual choice')
            pref.select('ja');current[:]=['ko-KR']
            self.assertEqual(LanguagePreference(folder,lambda:current).snapshot()['language'],'ja')
            with tempfile.TemporaryDirectory() as other:self.assertEqual(LanguagePreference(other,lambda:['vi-VN']).snapshot()['language'],'vi')
    def test_corrupt_preference_safely_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            pref=LanguagePreference(folder,lambda:['zh-HK']);pref.path.write_text('[]')
            self.assertEqual(pref.snapshot()['language'],'zh-TW')
    def test_mac_display_preferences_are_read_without_login(self):
        import plistlib
        for code in LANGUAGES:
            result=type('Result',(),{'stdout':plistlib.dumps({'AppleLanguages':[code]})})()
            with patch('language.os',__import__('types').SimpleNamespace(name='posix')),patch('language.sys.platform','darwin'),patch('language.subprocess.run',return_value=result):self.assertEqual(system_languages(),[code])
    def test_windows_user_ui_api_and_locale_fallback_without_webview(self):
        import types
        class Kernel:
            preferred=True
            code='vi-VN'
            def GetUserPreferredUILanguages(self,flags,count,buffer,size):
                self_flags=flags
                if not self.preferred:return 0
                payload=self.code+'\0en-US\0\0'
                count._obj.value=2;size._obj.value=len(payload)
                if buffer is not None:buffer[:len(payload)]=payload
                return int(self_flags==8)
            def GetUserDefaultLocaleName(self,buffer,size):buffer.value=self.code;return len(self.code)+1
        kernel=Kernel()
        with patch('language.os',types.SimpleNamespace(name='nt')),patch('language.ctypes.WinDLL',return_value=kernel,create=True):
            for code in LANGUAGES:
                kernel.code=code;self.assertEqual(system_languages(),[code,'en-US'])
            kernel.preferred=False;kernel.code='ja-JP';self.assertEqual(system_languages(),['ja-JP'])
    def test_callback_html_has_locale_no_foreign_korean_or_secrets(self):
        for code in LANGUAGES:
            for key in ('auth.success','auth.failure','auth.invalid','driveAuth.success','driveAuth.failure','aiAuth.received'):
                page=callback_page(key,code).decode();self.assertIn('lang="'+code+'"',page);self.assertIn(text(key,code),page)
                self.assertNotIn('access_token',page);self.assertNotIn('code_verifier',page)
                if code!='ko':self.assertFalse(any('가'<=c<='힣' for c in page))
    def test_packaged_engine_agent_finds_shared_catalog(self):
        import language, shutil
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'tools';agent=root/'engine/agent';agent.mkdir(parents=True)
            (root/'i18n').mkdir();shutil.copyfile(ROOT/'i18n/messages.json',root/'i18n/messages.json')
            with patch.object(language,'__file__',str(agent/'language.py')),patch.object(language,'_messages',None):
                for code in LANGUAGES:self.assertEqual(language.text('auth.success',code),text('auth.success',code))

class LocalLanguageApiTests(unittest.TestCase):
    setUp=LocalAccountApiTests.setUp
    tearDown=LocalAccountApiTests.tearDown
    request=LocalAccountApiTests.request
    sign_in=LocalAccountApiTests.sign_in
    def test_six_prelogin_selections_survive_signin_logout_and_restart(self):
        before=dict(self.agent.settings['shortcuts'])
        for code in LANGUAGES:
            with self.subTest(language=code):
                self.assertEqual(self.request('POST','/preferences/language',{'language':code},token=self.token)[0],200)
                self.sign_in();self.agent.require_account();self.assertEqual(self.agent.settings['language'],code)
                self.assertEqual(self.request('POST','/account/logout',{},token=self.token)[0],200)
                self.assertEqual(self.request('GET','/preferences/language',token=self.token)[1]['language'],code)
                self.assertEqual(LanguagePreference(self.agent.state,lambda:['ko-KR']).snapshot()['language'],code)
                self.assertEqual(self.agent.settings['shortcuts'],before)
    def test_other_origins_cannot_change_device_language(self):
        self.assertEqual(self.request('POST','/preferences/language',{'language':'vi'},origin='https://evil.invalid',token=self.token)[0],403)
        self.assertEqual(self.request('POST','/preferences/language',{'language':'zh'},token=self.token)[0],400)
    def test_bootstrap_has_os_language_before_any_account_access(self):
        self.agent.language_preference.system_reader=lambda:['vi-VN']
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=4)
        conn.request('GET','/tools/language-bootstrap.js',headers={'Host':f'127.0.0.1:{self.port}'})
        response=conn.getresponse();page=response.read().decode();conn.close()
        self.assertEqual(response.status,200);self.assertIn('"language": "vi"',page);self.assertNotIn(self.token,page)
    def test_account_locale_is_used_only_when_os_is_unavailable(self):
        self.sign_in()
        credential,user,expires,verified=self.agent.account.snapshot
        self.agent.account.snapshot=(credential,{**user,'locale':'zh-TW'},expires,verified)
        self.agent.language_preference.system_reader=lambda:[]
        self.assertEqual(self.agent.language_state()['language'],'zh-TW')
        self.agent.language_preference.system_reader=lambda:['vi-VN']
        self.assertEqual(self.agent.language_state()['language'],'vi')
        self.agent.language_preference.select('ja')
        self.assertEqual(self.agent.language_state()['language'],'ja')

class LocalizedOAuthTests(unittest.TestCase):
    def test_six_login_and_drive_success_failure_keep_starting_locale_and_pkce(self):
        for code in LANGUAGES:
            for drive in (False,True):
                for fails in (False,True):
                    with self.subTest(language=code,drive=drive,failure=fails),tempfile.TemporaryDirectory() as folder:
                        urls=[];cloud=CloudFixture(time.time);vault=MemoryVault();current=[code]
                        account=KIOAccount(Path(folder),store=vault,transport=cloud,open_browser=lambda u:urls.append(u) or True,language_provider=lambda:current[0])
                        try:
                            if drive:account._accept({'credential':'fixture-only-'+'x'*60,'user':USER,'expires':time.time()+3600})
                            account.login('google',expected_user=USER['id'] if drive else None,connect_drive=drive)
                            query=parse_qs(urlparse(urls[0]).query);target=urlparse(query['redirect_uri'][0]);self.assertEqual(query['language'],[code])
                            if drive:self.assertEqual(query['controlDrive'],['1'])
                            current[0]='ko' # Browser callback must retain the language at OAuth start.
                            if fails:cloud.fail='accountCloudUnavailable'
                            conn=http.client.HTTPConnection('127.0.0.1',target.port,timeout=4)
                            conn.request('GET',target.path+'?'+urlencode({'state':query['state'][0],'grant':'fixture-only-grant-'+'x'*30}),headers={'Host':f'127.0.0.1:{target.port}'})
                            response=conn.getresponse();page=response.read();conn.close();self.assertEqual(response.status,200)
                            self.assertIn(text('auth.failure' if fails else 'auth.success',code).encode(),page)
                            self.assertNotIn(b'fixture-only-grant',page);self.assertNotIn(b'fixture-only-',page)
                            verifier=cloud.calls[0][1]['code_verifier'];challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
                            self.assertEqual(query['code_challenge'],[challenge]);self.assertNotIn(verifier.encode(),page)
                        finally:account.close()

if __name__=='__main__':unittest.main(verbosity=2)

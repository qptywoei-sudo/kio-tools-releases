"""Explicitly mocked KIO cloud identity and OS vault for legacy engine fixtures.

Only disposable test state uses this helper. Production KIOAccount validation,
profile ownership, expiry and require() contracts still run. No OS credentials,
live Supabase, OAuth provider, screen permissions or real login are exercised.
"""
import json,time
from pathlib import Path
from unittest.mock import patch
from kio_account import KIOAccount
from server import Agent as ProductionAgent

MOCK_USER={'id':'19a3b744-b887-4dd8-b019-43306f7610f3','email':'fixture@example.invalid','name':'Mock KIO legacy regression identity','provider':'google'}
class MockOSVault:
    def __init__(self):self.data=None
    def load(self):return self.data
    def save(self,data):self.data=data
    def delete(self):self.data=None
class MockKIOCloud:
    def __init__(self):self.calls=[]
    def __call__(self,route,body,headers,method):
        self.calls.append((route,dict(body),dict(headers),method))
        if route=='/control/drive/status':return {'connected':False,'configured':True}
        # Same typed identity proof as the dedicated new account contract tests.
        return {'credential':'mock-only-kio-credential-'+('x'*64),'user':dict(MOCK_USER),'expires':int((time.time()+86400)*1000),'credentialExpires':int((time.time()+86400)*1000)}
_vaults={}
def verified_account(state):
    # A mock secure vault survives process-local Agent restarts. It never writes
    # any credential to files or reads the real platform credential store.
    vault=_vaults.setdefault(str(Path(state).resolve()),MockOSVault())
    account=KIOAccount(state,store=vault,transport=MockKIOCloud(),clock=time.time,open_browser=lambda url:False)
    if not account.status()['signedIn']:
        account._accept({'credential':'mock-only-kio-credential-'+('x'*64),'user':dict(MOCK_USER),'expires':time.time()+86400})
    return account
class VerifiedAgent(ProductionAgent):
    """Real Agent with only its test identity/vault/cloud dependency injected."""
    def __init__(self,*args,**kwargs):
        with patch('server.KIOAccount',side_effect=verified_account):
            super().__init__(*args,**kwargs)

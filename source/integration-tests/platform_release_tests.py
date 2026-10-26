"""Signed platform extension compatibility and publication rollback (isolated fixtures)."""
import sys,copy,json,base64,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
r=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(r/'agent'),str(r/'release-tools'),str(r/'engine/deps-agent/arm64')]
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from update_security import verified_manifest,platform_release
import prepare_update as signer
from publish_windows import commit_feed
class PlatformReleaseTests(unittest.TestCase):
 def setUp(self):
  self.key=Ed25519PrivateKey.generate();self.public=base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
  package=lambda p:{'url':'https://drive.google.com/uc?export=download&id=fixture','size':1234,'sha256':'a'*64,'root':'KIO-Control-'+p}
  self.payload={'format':1,'product':'kio-control','version':'4.4.6','notes':[],'packages':{p:package(p) for p in ['Windows','Mac']}}
  self.payload['platformReleases']={p:{'version':'4.4.6','notes':[],'package':package(p)} for p in ['Windows','Mac']}
 def signed(self,p):
  raw=json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();return {'payload':copy.deepcopy(p),'signature':base64.b64encode(self.key.sign(raw)).decode()}
 def test_windows_only_preserves_bridge_and_mac(self):
  original=copy.deepcopy(self.payload)
  with patch.object(signer,'PUBLIC_KEY',self.public):updated=signer.publish_platform(self.signed(original),'Windows','4.4.7',dict(original['packages']['Windows'],sha256='b'*64),['Windows fix'])
  verified=verified_manifest(self.signed(updated),self.public)
  self.assertEqual(verified['version'],'4.4.6');self.assertEqual(verified['packages'],original['packages'])
  self.assertEqual(platform_release(verified,'Mac'),original['platformReleases']['Mac']);self.assertEqual(platform_release(verified,'Windows')['version'],'4.4.7')
 def test_old_v1_verifier_accepts_extended_bridge(self):
  # Execute the actual 4.4.5 verifier, not a rewritten approximation.
  scope={};exec((r/'integration-tests/legacy_update_security_v1.py').read_text(),scope)
  self.assertEqual(scope['verified_manifest'](self.signed(self.payload),self.public)['version'],'4.4.6')
 def test_signed_invalid_platform_version_or_package_rejected(self):
  for field,value in [('version','4.4.5'),('version','garbage'),('notes','bad'),('package',{})]:
   p=copy.deepcopy(self.payload);p['platformReleases']['Mac'][field]=value
   with self.assertRaises(ValueError):verified_manifest(self.signed(p),self.public)
 def test_unsigned_platform_mutation_rejected(self):
  e=self.signed(self.payload);e['payload']['platformReleases']['Mac']['version']='9.0.0'
  with self.assertRaises(ValueError):verified_manifest(e,self.public)
 def test_legacy_without_extension_still_selects_legacy_release(self):
  del self.payload['platformReleases'];p=verified_manifest(self.signed(self.payload),self.public)
  self.assertEqual(platform_release(p,'Mac')['version'],'4.4.6')
 def test_publish_success_preserves_inode(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'latest.json';p.write_bytes(b'old');inode=p.stat().st_ino
   commit_feed(p,b'old',b'new',fetch=lambda:p.read_bytes());self.assertEqual(p.read_bytes(),b'new');self.assertEqual(p.stat().st_ino,inode)
 def test_failure_restores_old_feed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'latest.json';p.write_bytes(b'old')
   with self.assertRaises(ValueError):commit_feed(p,b'old',b'new',fetch=lambda:b'old',wait_seconds=0)
   self.assertEqual(p.read_bytes(),b'old')
 def test_concurrent_publish_refused(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'latest.json';p.write_bytes(b'other')
   with self.assertRaises(ValueError):commit_feed(p,b'old',b'new',fetch=lambda:b'old')
   self.assertEqual(p.read_bytes(),b'other')
 def test_encrypted_key_load_wrong_password_and_wrong_identity(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'encrypted.pem';p.write_bytes(self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(b'fixture-only-password')))
   with patch.object(signer,'PUBLIC_KEY',self.public),patch.object(signer.getpass,'getpass',return_value='fixture-only-password'):
    self.assertEqual(signer.load_signing_key(p).public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw),self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
   with patch.object(signer.getpass,'getpass',return_value='incorrect'):
    with self.assertRaises(ValueError):signer.load_signing_key(p)
   with patch.object(signer.getpass,'getpass',return_value='fixture-only-password'):
    with self.assertRaises(ValueError):signer.load_signing_key(p)
if __name__=='__main__':unittest.main()


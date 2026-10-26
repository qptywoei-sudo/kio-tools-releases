"""Real filesystem safety for the post-update Bogo bundle-name transaction."""
import sys,os,json,plistlib,tempfile,unittest,hashlib,time,subprocess,types
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import mac_bundle_migration as migration

@unittest.skipUnless(sys.platform=='darwin','Darwin atomic app-directory migration')
class MigrationFilesystemTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.app=self.root/'KIO Tools.app';self.app.mkdir(mode=0o700)
  (self.app/'Contents/MacOS').mkdir(parents=True);(self.app/'Contents/MacOS/KIOControl').write_bytes(b'fixture executable')
  (self.app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':migration.BUNDLE_ID,'CFBundleName':'Bogo Tools','CFBundleDisplayName':'Bogo Tools','CFBundleShortVersionString':'4.6.23','CFBundleExecutable':'KIOControl'}))
  self.document=self.root/'기존 문서.txt';self.document.write_text('사용자 자료 giữ nguyên 資料',encoding='utf-8')
  self.profile=self.root/'private-profile';self.profile.mkdir(mode=0o700);(self.profile/'canary').write_bytes(b'profile untouched')
 def tearDown(self):self.temp.cleanup()
 def test_atomic_rename_preserves_all_file_ids_and_external_data(self):
  before=migration.fingerprint(self.app);root_id=self.app.stat().st_ino;doc=self.document.read_bytes();profile=(self.profile/'canary').read_bytes()
  identity=migration.bundle_layout(self.app,'4.6.23');target=self.app.with_name('Bogo Tools.app')
  migration.atomic_rename(self.app,target)
  self.assertFalse(self.app.exists());self.assertEqual(target.stat().st_ino,root_id);self.assertEqual(migration.fingerprint(target),before)
  self.assertEqual(self.document.read_bytes(),doc);self.assertEqual((self.profile/'canary').read_bytes(),profile)
  self.assertEqual(identity['inode'],root_id)
 def test_collision_and_broken_symlink_never_overwrite(self):
  target=self.app.with_name('Bogo Tools.app');target.mkdir();(target/'foreign').write_bytes(b'do not touch')
  before=migration.fingerprint(self.app)
  with self.assertRaises(migration.MigrationError):migration.bundle_layout(self.app,'4.6.23')
  with self.assertRaises(OSError):migration.atomic_rename(self.app,target)
  self.assertEqual((target/'foreign').read_bytes(),b'do not touch');self.assertEqual(migration.fingerprint(self.app),before)
  (target/'foreign').unlink();target.rmdir();target.symlink_to(self.root/'missing',target_is_directory=True)
  with self.assertRaises(migration.MigrationError):migration.bundle_layout(self.app,'4.6.23')
 def test_foreign_id_brand_version_and_symlink_refused(self):
  path=self.app/'Contents/Info.plist';original=plistlib.loads(path.read_bytes())
  for key,bad in [('CFBundleIdentifier','foreign.app'),('CFBundleName','KIO Tools'),('CFBundleDisplayName','Other'),('CFBundleShortVersionString','4.6.21')]:
   path.write_bytes(plistlib.dumps(dict(original,**{key:bad})))
   with self.subTest(key=key),self.assertRaises(migration.MigrationError):migration.bundle_layout(self.app,'4.6.23')
  path.write_bytes(plistlib.dumps(original));alias=self.root/'alias';alias.symlink_to(self.app,target_is_directory=True)
  with self.assertRaises(migration.MigrationError):migration.bundle_layout(alias,'4.6.23')
 def test_owner_and_writable_parent_checks(self):
  with patch.object(migration.os,'geteuid',return_value=os.getuid()+1),self.assertRaises(migration.MigrationError):migration.bundle_layout(self.app,'4.6.23')
  self.root.chmod(0o777)
  try:
   with self.assertRaises(migration.MigrationError):migration.bundle_layout(self.app,'4.6.23')
  finally:self.root.chmod(0o700)
 def test_live_pid_blocks_with_no_move_or_force_signal(self):
  before=migration.fingerprint(self.app)
  with self.assertRaises(migration.MigrationError):migration.wait_for_pids([1234],timeout=.001,alive=lambda pid:True)
  self.assertTrue(self.app.exists());self.assertEqual(migration.fingerprint(self.app),before)
  migration.wait_for_pids([1234],timeout=.01,alive=lambda pid:False)
 def test_original_transaction_fields_must_authorize_this_app(self):
  plan={'target':str(self.app),'platform':'Mac','version':'4.6.23','receipt':str(self.profile/'updates/last-install.json')}
  receipt={'phase':'complete','reopened':True,'version':'4.6.23','pid':5432,'helperId':'install-'+'a'*32,'backup':str(self.app)+'.previous-123-abc'}
  migration.transaction_fields(receipt,plan,self.app,'4.6.23',self.profile/'updates/last-install.json')
  for key,bad in [('phase','installed'),('reopened',False),('version','4.6.21'),('pid',0),('backup',str(self.root/'foreign.app.previous-1'))]:
   with self.subTest(key=key),self.assertRaises(migration.MigrationError):migration.transaction_fields(dict(receipt,**{key:bad}),plan,self.app,'4.6.23',self.profile/'updates/last-install.json')
  with self.assertRaises(migration.MigrationError):migration.transaction_fields(receipt,dict(plan,target=str(self.root/'other.app')),self.app,'4.6.23',self.profile/'updates/last-install.json')
 def test_owned_startup_path_only_retargeted_with_all_other_settings_preserved(self):
  path=self.root/'login.plist';target=self.app.with_name('Bogo Tools.app');original={'Label':'local.galaxycontrol.login','ProgramArguments':['/usr/bin/open','-g','-j','-a',str(self.app),'--args','--background'],'RunAtLoad':False,'custom-canary':['preserve',7]}
  path.write_bytes(plistlib.dumps(original));migration.retarget_startup(self.app,target,path)
  updated=plistlib.loads(path.read_bytes());expected=dict(original,ProgramArguments=[*original['ProgramArguments']]);expected['ProgramArguments'][4]=str(target)
  self.assertEqual(updated,expected)
  foreign=dict(original,Label='other.job');path.write_bytes(plistlib.dumps(foreign));before=path.read_bytes();migration.retarget_startup(self.app,target,path);self.assertEqual(path.read_bytes(),before)
 def test_requirement_cannot_change_signer_or_identifier(self):
  good='designated => identifier "local.galaxycontrol.portable" and certificate leaf = H"72287f8a5048cd206db014ead6723c75cd459379"\n'
  migration.requirement_matches(0,good)
  for code,text in [(1,good),(0,''),(0,good.replace('local.galaxycontrol.portable','foreign.app')),(0,good.replace('72287f8a5048cd206db014ead6723c75cd459379','0'*40))]:
   with self.subTest(code=code),self.assertRaises(migration.MigrationError):migration.requirement_matches(code,text)
 def helper_plan(self):
  updates=self.profile/'updates';updates.mkdir(mode=0o700);folder=updates/('name-migration-'+'b'*32);folder.mkdir(mode=0o700)
  authorized={'helperId':'install-'+'a'*32,'helperPid':2222,'receiptSha256':'a'*64,'planSha256':'b'*64}
  value={'state':str(self.profile),'source':str(self.app),'target':str(self.app.with_name('Bogo Tools.app')),'version':'4.6.23','identity':migration.bundle_layout(self.app,'4.6.23'),'transaction':authorized,'pids':[3333,4444]}
  path=folder/'plan.json';migration.atomic_json(path,value)
  return path,authorized,updates/'bogo-name-migration.json'
 def test_helper_normal_transaction_waits_owned_exits_then_exclusive_move(self):
  path,authorized,result=self.helper_plan();before=migration.fingerprint(self.app)
  with patch.object(migration,'default_state',return_value=self.profile),patch.object(migration,'verify_signature') as verify,patch.object(migration,'transaction',return_value=authorized) as transaction,patch.object(migration,'wait_for_pids') as wait,patch.object(migration,'bundle_pids',return_value=[]),patch.object(migration,'retarget_startup',return_value='absent'),patch.object(migration.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as opened:
   self.assertTrue(migration.execute(path));wait.assert_called_once_with([3333,4444]);self.assertEqual(transaction.call_count,2);self.assertEqual(verify.call_count,3)
   self.assertEqual(opened.call_args.args[0],['/usr/bin/open',str(self.root/'Bogo Tools.app')])
  self.assertEqual(migration.fingerprint(self.root/'Bogo Tools.app'),before);receipt=migration.private_json(result);self.assertEqual(receipt['phase'],'complete');self.assertTrue(receipt['fileIdsAndBytesPreserved'])
 def test_helper_live_native_or_backend_keeps_original_and_never_opens(self):
  path,authorized,result=self.helper_plan();before=migration.fingerprint(self.app)
  with patch.object(migration,'default_state',return_value=self.profile),patch.object(migration,'verify_signature'),patch.object(migration,'transaction',return_value=authorized),patch.object(migration,'wait_for_pids',side_effect=migration.MigrationError('nameMigrationExitCancelled')),patch.object(migration,'bundle_pids',return_value=[3333]),patch.object(migration.subprocess,'run') as opened:
   self.assertFalse(migration.execute(path));opened.assert_not_called()
  self.assertEqual(migration.fingerprint(self.app),before);self.assertFalse((self.root/'Bogo Tools.app').exists());self.assertFalse(migration.private_json(result)['renamed'])
 def test_failed_reopen_rolls_back_with_file_ids_and_data_intact(self):
  path,authorized,result=self.helper_plan();before=migration.fingerprint(self.app)
  with patch.object(migration,'default_state',return_value=self.profile),patch.object(migration,'verify_signature'),patch.object(migration,'transaction',return_value=authorized),patch.object(migration,'wait_for_pids'),patch.object(migration,'bundle_pids',return_value=[]),patch.object(migration,'retarget_startup',return_value='absent'),patch.object(migration.subprocess,'run',side_effect=[subprocess.CompletedProcess([],1),subprocess.CompletedProcess([],0)]) as opened:
   self.assertFalse(migration.execute(path));self.assertEqual(opened.call_count,2);self.assertEqual(opened.call_args.args[0],['/usr/bin/open',str(self.app)])
  self.assertEqual(migration.fingerprint(self.app),before);self.assertFalse((self.root/'Bogo Tools.app').exists());receipt=migration.private_json(result);self.assertTrue(receipt['restored']);self.assertFalse(receipt['renamed']);self.assertTrue(receipt['reopenedOld'])
 def test_helper_late_collision_is_not_overwritten(self):
  path,authorized,result=self.helper_plan();before=migration.fingerprint(self.app);real=migration.atomic_rename
  def collide(source,target):
   target.mkdir();(target/'foreign').write_bytes(b'foreign document');return real(source,target)
  with patch.object(migration,'default_state',return_value=self.profile),patch.object(migration,'verify_signature'),patch.object(migration,'transaction',return_value=authorized),patch.object(migration,'wait_for_pids'),patch.object(migration,'bundle_pids',return_value=[]),patch.object(migration,'atomic_rename',side_effect=collide),patch.object(migration.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
   self.assertFalse(migration.execute(path))
  self.assertEqual((self.root/'Bogo Tools.app/foreign').read_bytes(),b'foreign document');self.assertEqual(migration.fingerprint(self.app),before)
 def test_newly_reopened_legacy_app_blocks_move_after_planned_pids_exit(self):
  path,authorized,result=self.helper_plan();before=migration.fingerprint(self.app)
  with patch.object(migration,'default_state',return_value=self.profile),patch.object(migration,'verify_signature'),patch.object(migration,'transaction',return_value=authorized),patch.object(migration,'wait_for_pids'),patch.object(migration,'bundle_pids',return_value=[5555]),patch.object(migration.subprocess,'run') as opened:
   self.assertFalse(migration.execute(path));opened.assert_not_called()
  self.assertEqual(migration.fingerprint(self.app),before);self.assertEqual(migration.private_json(result)['error'],'nameMigrationAppStillRunning')
 def test_private_plan_symlink_and_oversized_input_refused(self):
  path=self.root/'plan.json';migration.atomic_json(path,{'safe':True});alias=self.root/'alias.json';alias.symlink_to(path)
  with self.assertRaises(migration.MigrationError):migration.private_json(alias)
  path.write_bytes(b'x'*(1024*1024+1))
  with self.assertRaises(migration.MigrationError):migration.private_json(path)
 def test_original_helper_must_be_dead_and_standard_private_plan_signed(self):
  updates=self.profile/'updates';updates.mkdir(mode=0o700);helper=updates/('install-'+'a'*32);helper.mkdir(mode=0o700);receipt_path=updates/'last-install.json'
  plan={'target':str(self.app),'platform':'Mac','version':'4.6.23','receipt':str(receipt_path),'publicKey':migration.PUBLIC_KEY,'envelope':{'public-test-envelope':True}}
  receipt={'phase':'complete','reopened':True,'version':'4.6.23','pid':os.getpid(),'helperId':helper.name,'backup':str(self.app)+'.previous-1-abc'}
  migration.atomic_json(helper/'plan.json',plan);migration.atomic_json(receipt_path,receipt)
  verified=[]
  security=types.SimpleNamespace(verified_manifest=lambda envelope,key:verified.append((envelope,key)) or {'verified':True},platform_release=lambda payload,platform:{'version':'4.6.23','package':{'root':'KIO-Control-Mac'}})
  with patch.dict(sys.modules,{'update_security':security}):
   with self.assertRaisesRegex(migration.MigrationError,'UpdaterStillRunning'):migration.transaction(self.profile,self.app,'4.6.23',migration.PUBLIC_KEY)
   with patch.object(migration,'alive',return_value=False):
    identity=migration.transaction(self.profile,self.app,'4.6.23',migration.PUBLIC_KEY);self.assertEqual(identity['helperPid'],os.getpid())
    with self.assertRaisesRegex(migration.MigrationError,'UpdateKey'):migration.transaction(self.profile,self.app,'4.6.23','different-signing-key')
  self.assertEqual(verified[0],(plan['envelope'],migration.PUBLIC_KEY));self.assertTrue(self.app.exists())
 def test_helper_plan_alias_and_startup_parent_symlink_refused_without_write(self):
  path,authorized,result=self.helper_plan();alias=path.with_name('alias.json');alias.symlink_to(path)
  with self.assertRaises(migration.MigrationError):migration.execute(alias)
  folder=self.root/'real-startup';folder.mkdir();link=self.root/'startup-alias';link.symlink_to(folder,target_is_directory=True)
  job=folder/'login.plist';original=plistlib.dumps({'Label':'local.galaxycontrol.login','ProgramArguments':['/usr/bin/open','-a',str(self.app)]});job.write_bytes(original)
  with self.assertRaises(migration.MigrationError):migration.retarget_startup(self.app,self.app.with_name('Bogo Tools.app'),link/'login.plist')
  self.assertEqual(job.read_bytes(),original);self.assertTrue(self.app.exists())

if __name__=='__main__':unittest.main()

"""Validate the independently rebuildable program source, never ADMIN or user files."""
import hashlib,json,os,subprocess,sys,tempfile,unittest,zipfile,shutil
from pathlib import Path
work=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(work),str(work/'agent')]
from source_collector import collect_source_entries,write_source_bundle

class IndependentSourceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ui=work/'desktop-ui'
  cls.entries,cls.manifest=collect_source_entries(work,cls.ui,{},desktop_ui=cls.ui)
 def test_no_admin_backend_credentials_or_legacy_build_inputs(self):
  for name in self.entries:
   self.assertFalse(name.startswith('admin/'),name)
   self.assertNotIn('node_modules/',name)
   self.assertFalse(Path(name).name.startswith('.env'),name)
  self.assertNotIn('desktop-ui/vite.local-tools.config.ts',self.entries)
  self.assertNotIn('desktop-ui/scripts/local-tools-release-plugin.ts',self.entries)
  self.assertFalse(self.manifest['requiresAdmin'])
 def test_every_actual_import_and_hash_is_in_the_archive(self):
  for edge in self.manifest['graph']['edges']:
   self.assertIn('desktop-ui/'+edge['target'],self.entries)
  for row in self.manifest['files']:
   self.assertEqual(hashlib.sha256(self.entries[row['path']]).hexdigest(),row['sha256'])
 def test_native_program_and_dependency_licenses_preserved(self):
  for name in ('agent/server.py','agent/common.py','engine/requirements.txt','mac/AgentHost.swift','windows/SharedHost.cpp','windows/webview2/LICENSE.txt','COPYING','desktop-ui/tsconfig.json','desktop-ui/qa/editor.test.cjs','desktop-ui/qa/events.test.cjs','desktop-ui/qa/workspace.test.cjs','desktop-ui/qa/load-source.cjs','desktop-ui/qa/README.md','integration-tests/capture_copy_tests.py','integration-tests/capture_target_tests.py','integration-tests/pdf_workspace_tests.mjs','integration-tests/pdf_workspace_engine_tests.py','integration-tests/barcode_catalog_tests.py','integration-tests/pdf_preview_cache_tests.py','mac/native-capture-tests.py'):
   self.assertIn(name,self.entries)
  self.assertNotIn('integration-tests/source_collector_tests.py',self.entries)
 def test_dependency_manifest_does_not_require_supabase_or_admin(self):
  package=json.loads(self.entries['desktop-ui/package.json'])
  self.assertEqual(package['name'],'galaxycontrol-desktop-ui')
  self.assertEqual(package['version'],__import__('common').VERSION)
  self.assertNotIn('@supabase/supabase-js',package['dependencies'])
  self.assertNotIn('deploy',package['scripts'])
 def test_source_zip_crc_and_scope(self):
  with tempfile.TemporaryDirectory() as directory:
   target=Path(directory)/'source.zip'
   write_source_bundle(work,self.ui,{},target,desktop_ui=self.ui)
   with zipfile.ZipFile(target) as archive:
    self.assertIsNone(archive.testzip())
    self.assertEqual(set(archive.namelist()),set(self.entries))
 def test_extracted_source_builds_without_an_admin_checkout(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   for name,data in self.entries.items():
    # The existing six-language suite reads its packaged native bridge catalog.
    if name.startswith('desktop-ui/') or name=='i18n/native-bridge.json':
     target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
   ui=root/'desktop-ui'
   try:(ui/'node_modules').symlink_to(self.ui/'node_modules',target_is_directory=True)
   except OSError as exc:
    if getattr(exc,'winerror',None)!=1314:raise
    # Ordinary Windows accounts need no administrator/symlink privilege to test.
    shutil.copytree(self.ui/'node_modules',ui/'node_modules')
   env={key:value for key,value in os.environ.items() if not key.startswith(('VITE_','SUPABASE_','VERCEL_','LOCAL_AGENT_','GALAXY_TOOLS_UI_OUT_DIR'))}
   for args in (['node',str(ui/'node_modules/typescript/bin/tsc'),'-p','tsconfig.json'],['node','--test',*(str(p) for p in sorted((ui/'qa').glob('*.test.cjs')))],['node',str(ui/'node_modules/vite/bin/vite.js'),'build']):
    result=subprocess.run(args,cwd=ui,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    self.assertEqual(result.returncode,0,' '.join(args)+'\n'+result.stdout[-2000:]+result.stderr[-2000:])
   self.assertTrue((ui/'dist/index.html').is_file())
   self.assertFalse((ui/'dist/demo').exists())
   self.assertFalse((ui/'public').exists())

if __name__=='__main__':unittest.main(verbosity=2)

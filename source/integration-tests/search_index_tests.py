"""Disposable local files only: structured search, document preview and cancellation.
No user folders, remote database, network requests or real browser are touched.
"""
import sys,unittest,tempfile,zipfile,os
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'engine'),str(root/'agent')]
import engine
import index as module
from index import FileIndex
from common import AgentError

class SearchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.state=self.root/'state';self.state.mkdir();self.folder=self.root/'selected';self.folder.mkdir()
  self.loop=patch.object(FileIndex,'loop',return_value=None);self.watch=patch.object(FileIndex,'watch',return_value=None);self.loop.start();self.watch.start()
  self.events=[];self.index=FileIndex(self.state,self.events.append)
 def tearDown(self):
  self.index.close();self.loop.stop();self.watch.stop();self.temp.cleanup()
 def index_files(self):
  ident=self.index.add(self.folder);self.index.reconcile(ident);return ident
 def test_filters_are_intersection_and_date_to_includes_entire_day(self):
  archive=self.folder/'Finance_100%';archive.mkdir();a=archive/'qc.txt';a.write_text('Inspection finance');b=archive/'qc.csv';b.write_text('Inspection finance');c=self.folder/'qc.txt';c.write_text('Inspection finance')
  stamp=datetime(2026,4,15,23,59,59).timestamp()
  for p in [a,b,c]:os.utime(p,(stamp,stamp))
  self.index_files()
  filters={'extensions':['TXT'],'dateFrom':'2026-04-15','dateTo':'2026-04-15','path':str(archive)}
  found=self.index.search('Inspection',filters=filters)
  self.assertEqual([x['name'] for x in found],['qc.txt']);self.assertEqual(found[0]['folder'],'selected/Finance_100%')
  self.assertEqual(self.index.search('',filters={'extensions':['.csv']} )[0]['name'],'qc.csv')
  self.assertEqual(self.index.search('Inspection',filters={'dateTo':'2026-04-14'}),[])
 def test_date_extension_and_path_are_validated_before_sql(self):
  self.index_files()
  for filters in [{'extensions':['txt);DROP TABLE files;--']},{'extensions':'txt'},{'dateFrom':'2026-02-30'},{'dateFrom':'2026-06-01','dateTo':'2026-05-01'},{'path':'x\0y'},{'unapproved':'value'}]:
   with self.assertRaises(AgentError):self.index.search('',filters=filters)
  self.assertEqual(self.index.roots()[0]['path'],str(self.folder))
 def test_document_content_search_and_bounded_preview_preserve_originals(self):
  names={'docx':'word/document.xml','xlsx':'xl/worksheets/sheet1.xml'}
  originals={}
  for extension,part in names.items():
   p=self.folder/('input.'+extension)
   with zipfile.ZipFile(p,'w') as z:z.writestr(part,'<root><t>needle document '+('A'*21_000)+'</t></root>')
   originals[p]=p.read_bytes()
  pdf=self.folder/'input.pdf'
  with engine.fitz.open() as document:document.new_page().insert_text((30,40),'needle PDF');document.save(pdf)
  originals[pdf]=pdf.read_bytes()
  self.index_files();found=self.index.search('needle');self.assertEqual(len(found),3)
  for file in found:
   preview=self.index.preview(file['id']);self.assertIn('needle',preview['text']);self.assertTrue(Path(preview['path']).is_relative_to(self.folder));self.assertEqual(preview['name'],file['name']);self.assertLessEqual(len(preview['text']),20_000)
   if preview['extension']=='.pdf':self.assertEqual(preview['pages'],1)
   else:self.assertTrue(preview['truncated'])
  for p,original in originals.items():self.assertEqual(p.read_bytes(),original)
 def test_cancel_during_extraction_preserves_previous_index_and_files(self):
  p=self.folder/'first.txt';p.write_text('original needle');ident=self.index_files();old=self.index.search('needle')[0]['id'];p.write_text('new needle');before=p.read_bytes();extract=module.extract_text
  def interrupt(path):
   text=extract(path);self.index.cancel(ident);return text
  with patch.object(module,'extract_text',side_effect=interrupt):self.index.reconcile(ident)
  self.assertEqual(self.index.roots()[0]['status'],'cancelled');self.assertEqual(self.index.search('needle')[0]['id'],old);self.assertEqual(p.read_bytes(),before)
  self.assertEqual(self.index.add(self.folder),ident);self.index.reconcile(ident);self.assertEqual(self.index.roots()[0]['status'],'complete')
 def test_removed_root_cannot_be_reinserted_by_inflight_scan(self):
  p=self.folder/'first.txt';p.write_text('needle');ident=self.index.add(self.folder);extract=module.extract_text
  def interrupt(path):
   text=extract(path);self.index.remove(ident);return text
  with patch.object(module,'extract_text',side_effect=interrupt):self.index.reconcile(ident)
  self.assertEqual(self.index.roots(),[]);self.assertEqual(self.index.search('needle'),[]);self.assertEqual(self.index.db.execute('SELECT COUNT(*) FROM files').fetchone()[0],0);self.assertTrue(p.exists())
 def test_preview_rejects_ancestor_symlink_replacement(self):
  p=self.folder/'first.txt';p.write_text('needle');self.index_files();ident=self.index.search('needle')[0]['id'];old=self.root/'old';self.folder.rename(old);self.folder.symlink_to(old,target_is_directory=True)
  with self.assertRaises(AgentError):self.index.preview(ident)
 def test_cancel_persists_and_reselect_resumes(self):
  (self.folder/'first.txt').write_text('needle');ident=self.index_files();self.index.cancel(ident);self.index.close();self.index=FileIndex(self.state,self.events.append)
  self.assertFalse(self.index.active(ident));self.assertEqual(self.index.roots()[0]['status'],'cancelled');self.index.add(self.folder);self.assertTrue(self.index.active(ident))

if __name__=='__main__':unittest.main(verbosity=2)

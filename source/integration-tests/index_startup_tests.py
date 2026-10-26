"""A dormant legacy index must not delay startup or expose private state."""
import sys,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1];sys.path[:0]=[str(source/'agent')]
from index import FileIndex,LazyFileIndex
from common import AgentError

class DormantIndexTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.state=self.root/'state';self.state.mkdir();self.visible=self.root/'public-secret.txt';self.visible.write_text('public fixture')
  self.private=self.state/'secret-token.txt';self.private.write_text('private fixture')
  index=FileIndex(self.state,background=False)
  index.db.execute('INSERT INTO roots VALUES(?,?,?,?,?,?)',('root',str(self.root),'fixture','indexing',0,10002))
  rows=[(str(n),'root',f'old/folder-{n}/item.txt','item.txt','.txt',1,0,0,'old','') for n in range(10000)]
  rows.extend([('public','root',self.visible.name,self.visible.name,'.txt',14,0,0,'fixture','secret'),('private','root','state/'+self.private.name,self.private.name,'.txt',15,0,0,'fixture','secret')])
  try:index.db.executemany('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?)',rows);index.db.commit()
  finally:index.close()
 def tearDown(self):self.tmp.cleanup()
 def test_dormant_startup_does_not_scan_or_mutate_existing_rows(self):
  with patch.object(FileIndex,'private_path',side_effect=AssertionError('Unexpected per-file startup path check')) as checked:
   index=LazyFileIndex(self.state,background=False)
  try:
   checked.assert_not_called();self.assertIsNone(index._instance)
   # Read the preserved fixture directly. Accessing index.db would intentionally
   # open the concrete index and run its mandatory private-row cleanup.
   with sqlite3.connect(self.state/'index.sqlite') as db:
    self.assertEqual(db.execute('SELECT COUNT(*) FROM files').fetchone()[0],10002)
    self.assertEqual(db.execute('SELECT status FROM roots').fetchone()[0],'indexing')
  finally:index.close()
 def test_dormant_queries_still_filter_private_paths(self):
  index=FileIndex(self.state,background=False)
  try:
   self.assertEqual(index.resolve('public'),self.visible)
   with self.assertRaisesRegex(AgentError,'fileMissing'):index.resolve('private')
   found=index.search('secret');self.assertEqual([row['id'] for row in found],['public'])
   self.assertIsNone(index.thread)
  finally:index.close()
 def test_explicit_add_starts_background_lazily(self):
  index=FileIndex(self.state,background=False);folder=self.root/'chosen';folder.mkdir()
  try:
   with patch.object(index,'watch') as watch:
    ident=index.add(folder);self.assertIsNotNone(index.thread);self.assertTrue(index.thread.is_alive());watch.assert_any_call(ident,folder.resolve())
  finally:index.close()

if __name__=='__main__':unittest.main(verbosity=2)

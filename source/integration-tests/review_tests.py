"""Independent disposable-state security/preservation regression cases.
Native pairing is simulated only by this fixture; production files and approval paths are unchanged.
Run with the bundled Python interpreter and -I -B. No existing user file is read or changed.
"""
import sys,unittest,tempfile,threading,time,json,http.client,hashlib,zipfile,io,weakref,gc,os,subprocess,socket
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'engine'),str(root/'agent')]
import engine,engine_extra as extra,office_export
import index as index_module,rename as rename_module
from PIL import Image
from common import AgentError
from index import FileIndex,contained
from server import Server
from kio_fixture import VerifiedAgent as Agent
from process_group import spawn

class ReviewEngineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name).resolve();self.out=self.path/'out';self.out.mkdir()
 def tearDown(self):self.temp.cleanup()
 def test_stitch_does_not_retain_all_rgba_segments(self):
  tile=self.path/'tile.png';Image.new('RGBA',(20,20),'red').save(tile)
  references=[];live=[];original=Image.new
  def tracking(mode,size,*args,**kwargs):
   image=original(mode,size,*args,**kwargs)
   if mode=='RGBA' and size==(20,500):
    references.append(weakref.ref(image));gc.collect();live.append(sum(r() is not None for r in references))
   return image
  with patch.object(extra.Image,'new',side_effect=tracking):
   result=extra.web_stitch({'tiles':[{'path':str(tile),'viewportWidth':20,'viewportHeight':20}],'width':20,'height':2000,'dpr':1,'format':'png','split':True,'maxHeight':500,'output_dir':str(self.out)})
  self.assertEqual(result['data']['segments'],4)
  self.assertLessEqual(max(live),2,'Segment splitting must bound peak retained image buffers; observed '+str(live))
 def test_docx_second_signature_keeps_first_media_and_unique_object_ids(self):
  path=self.path/'original.docx';ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
  with zipfile.ZipFile(path,'w') as z:
   z.writestr('word/document.xml',f'<w:document xmlns:w="{ns}"><w:body><w:p><w:r><w:t>Original document</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
   z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
  original=hashlib.sha256(path.read_bytes()).digest()
  first=Path(office_export.docx_signature(path,Image.new('RGBA',(20,10),'red'),{'output_dir':str(self.out)})['files'][0]);first_hash=hashlib.sha256(first.read_bytes()).digest()
  with zipfile.ZipFile(first) as z:media={n:z.read(n) for n in z.namelist() if n.startswith('word/media/')}
  second=Path(office_export.docx_signature(first,Image.new('RGBA',(20,10),'blue'),{'output_dir':str(self.out)})['files'][0])
  with zipfile.ZipFile(second) as z:
   for name,data in media.items():self.assertEqual(z.read(name),data,'An existing signature/image part was replaced')
   import xml.etree.ElementTree as ET
   document=ET.fromstring(z.read('word/document.xml'));ids=[e.get('id') for e in document.iter() if e.tag.endswith('}docPr')]
   self.assertEqual(len(ids),len(set(ids)),'Word drawing object IDs must remain unique')
  self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),original);self.assertEqual(hashlib.sha256(first.read_bytes()).digest(),first_hash)
 def test_atomic_output_does_not_overwrite_new_destination_data(self):
  expected=self.out/'result.txt';external=b'Unrelated data created while export was running'
  def writer(temporary):
   expected.write_bytes(external)
   temporary.write_bytes(b'Export output')
  try:engine.write_atomic(self.out,'result','.txt',writer)
  except (OSError,ValueError):pass
  self.assertEqual(expected.read_bytes(),external,'Atomic export replaced a concurrently changed destination')
 def test_pdf_pptx_rejects_large_render_before_pixmap_allocation(self):
  path=self.path/'large-page.pdf'
  with engine.fitz.open() as document:document.new_page(width=4000,height=4000);document.save(path)
  actual=engine.fitz.Page.get_pixmap
  def checked(page,*args,**kwargs):
   dpi=kwargs.get('dpi',72)
   if page.rect.width*page.rect.height*(dpi/72)**2>80_000_000:raise AssertionError('Pixmap allocated before page pixel-budget validation')
   return actual(page,*args,**kwargs)
  with patch.object(engine.fitz.Page,'get_pixmap',checked):
   with self.assertRaises(ValueError):office_export.pdf_pptx({'path':str(path),'dpi':300,'output_dir':str(self.out)})
 def test_video_playlist_cannot_read_unselected_segment(self):
  import subprocess,imageio_ffmpeg
  outside=self.path/'unselected';outside.mkdir();segment=outside/'private.mp4';selected=self.path/'selected';selected.mkdir()
  subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-filter_complex','color=c=red:size=32x32:rate=4','-t','1','-c:v','mpeg4','-f','mp4',str(segment)],check=True,timeout=10)
  playlist=selected/'uploaded.m3u8';playlist.write_text('#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:1.0,\n'+str(segment)+'\n#EXT-X-ENDLIST\n')
  with self.assertRaises(ValueError):extra.video_gif({'inputs':[str(playlist)],'output_dir':str(self.out),'ranges':[{'start':0,'end':.5}],'width':64,'fps':2})
 def test_regular_mp4_watermark_gif_still_exports(self):
  import subprocess,imageio_ffmpeg
  source=self.path/'source.mp4'
  subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-filter_complex','testsrc=size=64x48:rate=4','-t','1','-c:v','mpeg4','-pix_fmt','yuv420p',str(source)],check=True,timeout=10)
  before=source.read_bytes()
  answer=extra.video_gif({'inputs':[str(source)],'output_dir':str(self.out),'ranges':[{'start':0,'end':1}],'width':64,'fps':4,'watermark':'TEST'})
  self.assertEqual(source.read_bytes(),before)
  self.assertEqual(len(answer['files']),1)
  with Image.open(answer['files'][0]) as gif:
   self.assertEqual(gif.format,'GIF');self.assertEqual(gif.size,(64,48));self.assertGreater(gif.n_frames,1)
  self.assertFalse(list(self.out.glob('.watermark-*')))
 def test_huge_tile_resize_rejected_before_allocation(self):
  tile=self.path/'tile.png';Image.new('RGBA',(20,20),'red').save(tile)
  actual_resize=Image.Image.resize
  def safe_resize(image,size,*args,**kwargs):
   if size[0]*size[1]>engine.Image.MAX_IMAGE_PIXELS:raise AssertionError('Unbounded resize attempted: '+str(size))
   return actual_resize(image,size,*args,**kwargs)
  with patch.object(Image.Image,'resize',safe_resize):
   with self.assertRaises(ValueError):
    extra.web_stitch({'tiles':[{'path':str(tile),'viewportWidth':30000,'viewportHeight':30000}],'width':20,'height':20,'dpr':1,'output_dir':str(self.out),'format':'png'})
 def test_arrow_padding_budget_checked_before_allocation(self):
  image=Image.new('RGBA',(64,64));actual_new=Image.new
  def bounded_new(mode,size,*args,**kwargs):
   if size[0]*size[1]>engine.Image.MAX_IMAGE_PIXELS:raise AssertionError('Expanded arrow allocated before pixel budget: '+str(size))
   return actual_new(mode,size,*args,**kwargs)
  with patch.object(extra.Image,'new',side_effect=bounded_new):
   with self.assertRaises(ValueError):extra.layers(image,[{'type':'arrow','x':0,'y':0,'width':30000,'height':1,'lineWidth':1000,'points':[[0,.5],[29999,.5]]}],[])

class ReviewIndexTests(unittest.TestCase):
 def test_index_discards_content_when_root_ancestor_changes_during_read(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();state=root/'state';state.mkdir();parent=root/'authorized';selected=parent/'selected';selected.mkdir(parents=True);file=selected/'known.txt';file.write_text('authorized original')
   outside=root/'outside';(outside/'selected').mkdir(parents=True);(outside/'selected'/'known.txt').write_text('UNSELECTED_PRIVATE_SECRET')
   reader=index_module.extract_text;swapped=False
   def raced(path):
    nonlocal swapped
    if not swapped:
     parent.rename(root/'moved');parent.symlink_to(outside,target_is_directory=True);swapped=True
    return reader(path)
   with patch.object(FileIndex,'watch',return_value=None):index=FileIndex(state)
   try:
    ident=index.add(selected)
    with patch.object(index_module,'extract_text',side_effect=raced):index.reconcile(ident)
    self.assertEqual(index.search('UNSELECTED_PRIVATE_SECRET'),[], 'Changed ancestor exposed unselected file text in search candidates')
   finally:index.close()
 def test_replaced_root_ancestor_does_not_authorize_outside_files(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();state=root/'state';state.mkdir();parent=root/'authorized';selected=parent/'selected';selected.mkdir(parents=True);file=selected/'known.txt';file.write_text('authorized original')
   index=FileIndex(state)
   try:
    ident=index.add(selected);index.reconcile(ident);fid=index.search('authorized')[0]['id']
    parent.rename(root/'moved');outside=root/'outside';(outside/'selected').mkdir(parents=True);(outside/'selected'/'known.txt').write_text('private outside')
    parent.symlink_to(outside,target_is_directory=True)
    self.assertFalse(contained(selected/'known.txt',selected))
    with self.assertRaises(AgentError):index.resolve(fid)
   finally:index.close()

class ApprovalFixture:
 def ready(self):return True
 def status(self):return {'updatedAt':time.time(),'settings':{}}
 def approve(self,origin,name):pass
 def call(self,operation,args=None,timeout=90):raise AgentError('nativeUnavailable')

class ReviewRenameTests(unittest.TestCase):
 def test_partial_rename_failure_rolls_back_original_names_and_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();first=root/'first.txt';second=root/'second.txt';first.write_bytes(b'first original');second.write_bytes(b'second original');sources={'a':first,'b':second}
   renamer=rename_module.Renamer(lambda ident,owner:sources[ident]);preview=renamer.preview(['a','b'],{'name':'changed'},'fixture');actual=rename_module.publish_exclusive;count=0
   def failing(source,target):
    nonlocal count
    count+=1
    if count==2:raise OSError('fixture failure on second rename')
    return actual(source,target)
   with patch.object(rename_module,'publish_exclusive',side_effect=failing):
    with self.assertRaises(AgentError):renamer.commit(preview['previewId'],'fixture')
   self.assertEqual(first.read_bytes(),b'first original');self.assertEqual(second.read_bytes(),b'second original');self.assertFalse(list(root.glob('changed*')))

class ReviewWorkerTests(unittest.TestCase):
 @unittest.skipIf(os.name=='nt','Windows Job Object runtime needs a Windows host')
 def test_posix_cancellation_terminates_owned_descendant(self):
  with tempfile.TemporaryDirectory() as tmp:
   marker=Path(tmp).resolve()/'child-pid.txt'
   script='import sys,time,subprocess;from pathlib import Path;p=subprocess.Popen([sys.executable,"-I","-c","import time;time.sleep(60)"]);Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)'
   process=spawn([sys.executable,'-I','-c',script,str(marker)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    deadline=time.monotonic()+5
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
    self.assertTrue(marker.exists());pid=int(marker.read_text());process.terminate_tree(timeout=2)
    deadline=time.monotonic()+2;state=''
    while time.monotonic()<deadline:
     state=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
     if not state or state.startswith('Z'):break
     time.sleep(.02)
    self.assertTrue(not state or state.startswith('Z'),'Owned descendant remained active after worker cancellation: '+state)
   finally:process.close()

class ReviewServerBoundsTests(unittest.TestCase):
 def test_header_receive_has_socket_timeout_before_dispatch(self):
  class Fixture:port=0
  server=Server(Fixture());client=socket.create_connection(server.server_address,timeout=2);accepted=None
  try:
   accepted,_=server.get_request()
   self.assertIsNotNone(accepted.gettimeout(),'Initial unauthenticated request headers can retain a thread indefinitely')
   self.assertLessEqual(accepted.gettimeout(),30)
  finally:
   client.close()
   if accepted:accepted.close()
   server.server_close()
 def test_slow_connections_do_not_exceed_configured_limit(self):
  class Fixture:port=0
  server=Server(Fixture());server.connections=threading.BoundedSemaphore(2);threading.Thread(target=server.serve_forever,daemon=True).start();clients=[]
  try:
   for _ in range(2):
    client=socket.create_connection(server.server_address,timeout=2);clients.append(client)
   deadline=time.monotonic()+2
   while server.connections._value and time.monotonic()<deadline:time.sleep(.01)
   self.assertEqual(server.connections._value,0)
   rejected=socket.create_connection(server.server_address,timeout=2);clients.append(rejected);rejected.settimeout(1)
   self.assertEqual(rejected.recv(1),b'','Additional slow connection was not refused at connection limit')
  finally:
   for client in clients:client.close()
   server.shutdown();server.server_close()

class ReviewAPITests(unittest.TestCase):
 def setUp(self):
  import socket
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name).resolve();self.ui=self.path/'ui';self.ui.mkdir();(self.ui/'index.html').write_text('test')
  with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
  self.origin='http://127.0.0.1:'+str(self.port);self.other='chrome-extension://'+'b'*32
  self.agent=Agent(self.path/'state',self.ui,self.port);fixture=ApprovalFixture();fixture.root=self.agent.bridge.root;self.agent.bridge=fixture;self.agent.settings['saveFolder']=str(self.path/'results')
  # Native UI receives its private bootstrap; the second owner is an explicitly
  # approved mock extension, never a newly trusted generic loopback browser.
  self.agent.origins.add(self.other)
  self.tokens={self.origin:self.agent.desktop_session['token'],self.other:self.agent.pair(self.other,'Only approved mock ownership fixture')['token']}
  self.server=Server(self.agent);threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.agent.close();self.temp.cleanup()
 def request(self,method,path,body=None,origin=None):
  origin=origin or self.origin;c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
  headers={'Origin':origin,'X-Local-Agent-Token':self.tokens[origin]}
  if body is not None:body=json.dumps(body);headers['Content-Type']='application/json'
  c.request(method,path,body,headers);response=c.getresponse();data=response.read();status=response.status;c.close()
  try:data=json.loads(data)
  except (ValueError,UnicodeError):pass
  return status,data
 def test_registered_file_id_remains_openable_after_rename(self):
  file=self.path/'original.txt';file.write_text('Original contents');artifact=self.agent.register(file,self.origin,'native')
  status,preview=self.request('POST','/rename/preview',{'ids':[artifact['id']],'options':{'name':'renamed','number':False}});self.assertEqual(status,200)
  self.assertEqual(self.request('POST','/rename/commit',{'previewId':preview['previewId']})[0],200)
  status,data=self.request('GET','/artifacts/'+artifact['id']);self.assertEqual(status,200,'Successful rename invalidated the current file ID');self.assertEqual(data,b'Original contents')
 def test_cancelled_job_does_not_become_failed_when_native_call_raises(self):
  started=threading.Event();release=threading.Event()
  def failing(*args,**kwargs):started.set();release.wait(2);raise RuntimeError('Fixture transport closure')
  self.agent.bridge.call=failing
  ident=self.agent.submit({'operation':'capture','options':{}},self.origin)['job']['id']
  try:
   self.assertTrue(started.wait(2));self.agent.cancel(ident);release.set()
   deadline=time.monotonic()+2
   while self.agent.jobs_limit._value<8 and time.monotonic()<deadline:time.sleep(.01)
   self.assertEqual(self.agent.jobs[ident]['status'],'cancelled','Late transport error changed completed cancellation into failed')
  finally:release.set()
 def test_registered_file_replaced_ancestor_denied(self):
  parent=self.path/'authorized';parent.mkdir();file=parent/'same.txt';file.write_text('authorized');artifact=self.agent.register(file,self.origin,'native')
  parent.rename(self.path/'moved');outside=self.path/'outside';outside.mkdir();(outside/'same.txt').write_text('outside private');parent.symlink_to(outside,target_is_directory=True)
  self.assertNotEqual(self.request('GET','/artifacts/'+artifact['id'])[0],200)
 def test_origin_file_ownership_and_cancel_ownership(self):
  file=self.path/'source.png';Image.new('RGB',(20,20),'red').save(file);artifact=self.agent.register(file,self.origin,'native')
  self.assertEqual(self.request('GET','/artifacts/'+artifact['id'],origin=self.other)[0],403)
  status,answer=self.request('POST','/jobs',{'operation':'image_process','inputs':[artifact['id']],'options':{'format':'png'}});self.assertEqual(status,202);job=answer['job']['id']
  self.assertEqual(self.request('GET','/jobs/'+job,origin=self.other)[0],404)
  self.assertEqual(self.request('POST','/jobs/'+job+'/cancel',{},origin=self.other)[0],404)
  for _ in range(50):
   if self.request('GET','/jobs/'+job)[1]['job']['status'] not in ('queued','running'):break
   time.sleep(.05)
 def test_event_reconnect_with_large_job_history_emits_ready(self):
  import socket
  with self.agent.lock:
   for i in range(120):
    ident='history-'+str(i);self.agent.jobs[ident]={'id':ident,'status':'complete'};self.agent.job_owners[ident]=self.origin
  c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=1)
  try:
   c.request('GET','/events',headers={'Origin':self.origin,'X-Local-Agent-Token':self.tokens[self.origin]})
   response=c.getresponse();self.assertEqual(response.status,200)
   try:line=response.readline()
   except (TimeoutError,socket.timeout):self.fail('SSE reconnect stalled before ready with120 retained jobs')
   self.assertIn(b'ready',line)
  finally:c.close()
 def test_static_traversal_and_symlink_denied(self):
  outside=self.path/'private.txt';outside.write_text('not public');(self.ui/'escape.txt').symlink_to(outside)
  for path in ('/tools/../private.txt','/tools/%2e%2e/private.txt','/tools/escape.txt'):
   self.assertNotEqual(self.request('GET',path)[0],200)

if __name__=='__main__':unittest.main(verbosity=2)

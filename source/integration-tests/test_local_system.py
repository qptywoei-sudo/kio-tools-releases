"""Real local engine/API regression fixtures; native approval is explicitly simulated only in tests."""
import sys,unittest,tempfile,threading,time,json,http.client,hashlib,zipfile,io,os
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'engine'),str(root/'agent')]
import engine,engine_extra as extra
from PIL import Image,ImageDraw
from common import AgentError
from index import FileIndex
from server import Server
from kio_fixture import VerifiedAgent as Agent
class EngineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.out=self.path/'out';self.out.mkdir();self.image=self.path/'source.png';im=Image.new('RGBA',(240,160),'white');ImageDraw.Draw(im).rectangle((60,30,180,130),fill='red');im.save(self.image)
  self.pdf=self.path/'source.pdf'
  with engine.fitz.open() as doc:
   for n in range(3):p=doc.new_page(width=240,height=160);p.insert_text((10,20),f'QC defect inspection page {n+1}')
   doc.save(self.pdf)
  self.hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.image,self.pdf)}
 def tearDown(self):
  for p,h in self.hashes.items():self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),h,'Original changed')
  self.temp.cleanup()
 def job(self,**kw):return {'inputs':[str(self.image)],'path':str(self.image),'output_dir':str(self.out),**kw}
 def test_split_adjustable_zip_pixels(self):
  r=extra.image_split(self.job(count=4,columns=2,rows=2,xCuts=[.25],yCuts=[.75]));self.assertEqual(len(r['files']),5)
  self.assertEqual(Image.open(r['files'][0]).size,(60,120));self.assertEqual(Image.open(r['files'][3]).size,(180,40))
  with zipfile.ZipFile(r['files'][-1]) as z:self.assertEqual(len(z.namelist()),4)
  with self.assertRaises(ValueError):extra.image_split(self.job(count=4,xCuts=[1]))
 def test_edit_shapes_draw_and_text(self):
  r=extra.image_edit(self.job(layers=[{'type':'rect','x':5,'y':5,'width':40,'height':40,'fill':'#0000ff'},{'type':'draw','points':[[100,10],[120,20]],'width':0,'height':0,'lineWidth':4},{'type':'text','x':10,'y':100,'text':'ADMIN','width':0,'height':0}],brightness=1.1));image=Image.open(r['files'][0]);self.assertEqual(image.getpixel((20,20))[:3],(0,0,255));self.assertNotEqual(image.getpixel((110,15))[:3],(255,255,255))
 def test_manual_background_and_replace(self):
  r=extra.image_background(self.job(background='transparent',strokes=[{'points':[[5,5],[15,5]],'radius':10}]))
  im=Image.open(r['files'][0]);self.assertEqual(im.size,(240,160));self.assertEqual(im.getpixel((5,5))[3],0);self.assertEqual(im.getpixel((120,100))[3],255)
  r=extra.image_background(self.job(background='solid',color='#00ff00'));im=Image.open(r['files'][0]);self.assertEqual(im.getchannel('A').getextrema(),(255,255))
 def test_inpaint_and_mosaic_preserve_outside(self):
  r=extra.image_retouch(self.job(rectangles=[[100,70,10,10]]));im=Image.open(r['files'][0]);self.assertEqual(im.getpixel((0,0)),(255,255,255,255))
  r=extra.image_mosaic(self.job(regions=[{'x':50,'y':20,'width':150,'height':120,'mode':'pixel','shape':'ellipse','strength':20}]));im=Image.open(r['files'][0]);self.assertEqual(im.getpixel((0,0)),(255,255,255,255))
 def test_pdf_signature_text_preserved_and_split(self):
  r=extra.signature_apply(self.job(path=str(self.pdf),inputs=[str(self.pdf)],text='ADMIN',width=80,height=30,allPages=True))
  with engine.open_pdf(r['files'][0]) as d:self.assertEqual(d.page_count,3);self.assertIn('QC defect',d[1].get_text());self.assertEqual(len(d[1].get_images()),1)
  r=extra.pdf_split(self.job(path=str(self.pdf),mode='groups',groupSize=2));self.assertEqual(len(r['files']),3)
  with engine.open_pdf(r['files'][0]) as d:self.assertEqual(d.page_count,2)
 def test_office_exports_valid_packages(self):
  r=extra.pdf_docx(self.job(path=str(self.pdf)));self.assertTrue(zipfile.is_zipfile(r['files'][0]));self.assertIn(b'QC defect',zipfile.ZipFile(r['files'][0]).read('word/document.xml'))
  r=extra.pdf_pptx(self.job(path=str(self.pdf)));from pptx import Presentation
  self.assertEqual(len(Presentation(r['files'][0]).slides),3)
  table=self.path/'table.pdf'
  with engine.fitz.open() as d:
   p=d.new_page(width=240,height=180)
   for x in (10,110,210):p.draw_line((x,40),(x,120))
   for y in (40,80,120):p.draw_line((10,y),(210,y))
   for x,y,text in [(20,60,'Name'),(120,60,'Count'),(20,100,'QC'),(120,100,'12')]:p.insert_text((x,y),text)
   d.save(table)
  r=extra.pdf_xlsx(self.job(path=str(table)));self.assertTrue(zipfile.is_zipfile(r['files'][0]));self.assertIn(b'QC',zipfile.ZipFile(r['files'][0]).read('xl/worksheets/sheet1.xml'))
 def test_qr_formats_read_roundtrip_wifi(self):
  for fmt in ('png','jpg','svg'):
   r=extra.code_generate(self.job(kind='qr',text='https://example.com/ADMIN',format=fmt,foreground='#112233'))
   if fmt!='svg':self.assertEqual(engine.code_read({'path':r['files'][0]})['data']['results'][0]['text'],'https://example.com/ADMIN')
   else:self.assertIn('<svg',Path(r['files'][0]).read_text())
  r=extra.code_generate(self.job(kind='qr',qr_type='wifi',ssid='QC;WiFi',password='a:b',format='png'));self.assertEqual(engine.code_read({'path':r['files'][0]})['data']['results'][0]['text'],r['data']['text'])
 def test_multi_canvas_pdf_gif(self):
  pages=[{'layers':[{'type':'rect','x':0,'y':0,'width':50,'height':50,'fill':c}]} for c in ('red','blue')]
  r=extra.canvas_export(self.job(width=100,height=80,pages=pages,format='gif'));self.assertEqual(Image.open(r['files'][0]).n_frames,2)
  r=extra.canvas_export(self.job(width=100,height=80,pages=pages,format='pdf'))
  with engine.open_pdf(r['files'][0]) as d:self.assertEqual(d.page_count,2)
 def test_web_stitch_overlap_and_split(self):
  a=self.path/'tile1.png';b=self.path/'tile2.png';Image.new('RGBA',(100,100),'red').save(a);Image.new('RGBA',(100,100),'blue').save(b)
  r=extra.web_stitch({'tiles':[{'path':str(a),'x':0,'y':0,'viewportWidth':100,'viewportHeight':100},{'path':str(b),'x':0,'y':75,'viewportWidth':100,'viewportHeight':100}],'width':100,'height':175,'dpr':1,'output_dir':str(self.out),'format':'png'})
  im=Image.open(r['files'][0]);self.assertEqual(im.size,(100,175));self.assertEqual(im.getpixel((50,120))[:3],(0,0,255));self.assertEqual(im.getpixel((50,20))[:3],(255,0,0))
 def test_web_stitch_crops_native_scrollbar_gutters_without_scaling_content(self):
  for dpr in (1,1.25,2):
   for rtl in (False,True):
    width,height=round(100*dpr),round(80*dpr);gutter=round(12*dpr);path=self.path/f'gutters-{dpr}-{rtl}.png'
    tile=Image.new('RGBA',(width+gutter,height+gutter),'magenta');tile.paste(Image.new('RGBA',(width,height),'blue'),(gutter if rtl else 0,0));tile.save(path)
    result=extra.web_stitch({'tiles':[{'path':str(path),'x':0,'y':0,'viewportWidth':100,'viewportHeight':80,'captureWidth':112,'captureHeight':92,'clipLeft':12 if rtl else 0}],'width':100,'height':80,'dpr':dpr,'output_dir':str(self.out),'format':'png'})
    with Image.open(result['files'][0]) as image:self.assertEqual(image.size,(width,height));self.assertEqual(image.convert('RGB').getcolors(width*height),[(width*height,(0,0,255))])
 def test_video_multiple_ranges_gif(self):
  import imageio_ffmpeg,subprocess
  video=self.path/'input.mp4';subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-filter_complex','testsrc=size=160x120:rate=12','-t','2','-c:v','mpeg4','-pix_fmt','yuv420p','-y',str(video)],check=True)
  r=extra.video_gif(self.job(inputs=[str(video)],ranges=[{'start':0,'end':.6},{'start':1,'end':1.6}],width=160,fps=8,zip=True));self.assertEqual(len(r['files']),3);self.assertGreater(Image.open(r['files'][0]).n_frames,1)

class ApprovalFixture:
 """Test-only native responder; no production bypass or silent approval path."""
 def __init__(self):self.approvals=[];self.approved=True
 def ready(self):return True
 def status(self):return {'updatedAt':time.time(),'settings':{}}
 def approve(self,origin,name):
  self.approvals.append((origin,name))
  if not self.approved:raise AgentError('pairingDenied',403)
 def call(self,op,args=None,timeout=90):
  if op=='permissions.get':return {'screenCapture':'needsPermission','accessibility':'needsPermission','files':'available'}
  if op=='settings.apply':
   if args.get('shortcuts',{}).get('areaCapture')=='Control+C':raise AgentError('shortcutConflict',409)
   return {'applied':True}
  if op in ('folder.choose','files.choose'):raise AgentError('cancelled')
  raise AgentError('nativeUnavailable')

class APITests(unittest.TestCase):
 def setUp(self):
  import socket
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name).resolve();self.ui=self.path/'ui';self.ui.mkdir();(self.ui/'index.html').write_text('<h1>Tools</h1>')
  with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
  self.origin='http://127.0.0.1:'+str(self.port);self.a=Agent(self.path/'state',self.ui,self.port);bridgeRoot=self.a.bridge.root;self.a.bridge=ApprovalFixture();self.a.bridge.root=bridgeRoot;self.a.settings['saveFolder']=str(self.path/'results')
  self.server=Server(self.a);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.token=self.a.desktop_session['token']
 def tearDown(self):self.server.shutdown();self.server.server_close();self.a.close();self.temp.cleanup()
 def req(self,method,path,body=None,token=None,origin=None,host=None,raw=None,extra=None):
  c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10);headers={'Origin':self.origin if origin is None else origin,'Host':host or '127.0.0.1:'+str(self.port)}
  if token is not False and (token or hasattr(self,'token')):headers['X-Local-Agent-Token']=token or self.token
  if body is not None:body=json.dumps(body);headers['Content-Type']='application/json'
  if extra:headers.update(extra)
  c.request(method,path,raw if raw is not None else body,headers);r=c.getresponse();data=r.read();status=r.status;cors=r.getheader('Access-Control-Allow-Origin');c.close()
  try:data=json.loads(data)
  except (ValueError,UnicodeError):pass
  return status,data,cors
 def test_host_origin_token_denials_and_revocation(self):
  self.assertEqual(self.req('GET','/health',origin='https://evil.example')[0],403)
  self.assertEqual(self.req('GET','/health',host='evil.example:'+str(self.port))[0],403)
  self.assertEqual(self.req('GET','/settings',token=False)[0],401)
  self.assertEqual(self.req('POST','/pair',{},origin='null')[0],403)
  self.assertEqual(len(self.a.bridge.approvals),0)
  self.assertEqual(self.req('DELETE','/pair',token=False)[0],401)
  extension='chrome-extension://'+'a'*32;self.a.origins.add(extension)
  status,pair,_=self.req('POST','/pair',{'clientName':'Approved mock extension'},origin=extension,token=False);self.assertEqual(status,200)
  self.assertEqual(self.req('DELETE','/pair',origin=extension,token=pair['token'])[0],200)
  self.assertEqual(self.req('GET','/settings',origin=extension,token=pair['token'])[0],401)
  self.assertEqual(self.req('GET','/settings')[0],200,'Extension revocation must preserve the private native session')
 def test_pair_native_denial_no_token(self):
  self.a.bridge.approved=False;status,error,_=self.req('POST','/pair',{});self.assertEqual(status,403);self.assertEqual(error['errorCode'],'forbiddenOrigin');self.assertEqual(self.a.bridge.approvals,[])
  extension='chrome-extension://'+'a'*32;self.a.origins.add(extension);status,error,_=self.req('POST','/pair',{},origin=extension,token=False);self.assertEqual(status,403);self.assertEqual(error['errorCode'],'pairingDenied');self.assertNotIn(extension,self.a.tokens)
 def test_options_no_wildcard_and_private_network(self):
  status,data,cors=self.req('OPTIONS','/settings',token=False);self.assertEqual(status,200);self.assertEqual(cors,self.origin)
 def test_folder_cancel_settings_unchanged(self):
  before=self.a.settings.copy();self.assertEqual(self.req('POST','/settings/save-folder',{})[1]['errorCode'],'cancelled');self.assertEqual(self.a.settings,before)
  self.assertEqual(self.req('PATCH','/settings',{'saveFolder':'/tmp'})[0],400)
  self.assertEqual(self.req('PATCH','/settings',{'language':'ru'})[0],400)
  self.assertEqual(self.req('PATCH','/settings',{'shortcuts':{'areaCapture':'Control+C'}})[0],409)
 def test_upload_job_result_and_path_injection(self):
  buf=io.BytesIO();Image.new('RGB',(100,50),'red').save(buf,'PNG');status,f,_=self.req('POST','/uploads',raw=buf.getvalue(),extra={'X-File-Name':'test.png'});self.assertEqual(status,201)
  self.assertEqual(self.req('POST','/jobs',{'operation':'image_process','inputs':[f['id']],'options':{'output_dir':'/tmp'}})[0],400)
  status,data,_=self.req('POST','/jobs',{'operation':'image_process','inputs':[f['id']],'options':{'width':40,'format':'png'}});self.assertEqual(status,202);ident=data['job']['id']
  for _ in range(100):
   j=self.req('GET','/jobs/'+ident)[1]['job']
   if j['status'] not in ('queued','running'):break
   time.sleep(.1)
  self.assertEqual(j['status'],'complete',j);self.assertEqual(j['progress'],100);artifact=j['result']['files'][0]
  status,b,_=self.req('GET','/artifacts/'+artifact['id']);self.assertEqual(status,200);self.assertEqual(Image.open(io.BytesIO(b)).size,(40,20));self.assertNotIn('path',artifact)
 def test_index_incremental_symlink_search_and_rename_preview(self):
  folder=self.path/'files';folder.mkdir();p=folder/'QC_defect.txt';p.write_text('inspection criteria Japanese wifi');outside=self.path/'outside.txt';outside.write_text('private')
  (folder/'escape.txt').symlink_to(outside);rid=self.a.index.add(folder);self.a.index.reconcile(rid)
  rows=self.a.index.search('QC 검사');self.assertTrue(rows);self.assertFalse(any(x['name']=='escape.txt'for x in self.a.index.search('private')))
  ident=rows[0]['id'];status,preview,_=self.req('POST','/rename/preview',{'ids':[ident],'options':{'name':'QC_IMAGE','start':1,'digits':3}});self.assertEqual(status,200);self.assertTrue(p.exists());self.assertEqual(preview['items'][0]['after'],'QC_IMAGE_001.txt')
  self.assertEqual(self.req('POST','/rename/commit',{'previewId':preview['previewId']})[0],200);self.assertFalse(p.exists());self.assertTrue((folder/'QC_IMAGE_001.txt').exists())
  self.a.index.reconcile(rid);new=self.a.index.search('QC_IMAGE')[0];preview=self.req('POST','/rename/preview',{'ids':[new['id']],'options':{'name':'Changed'}})[1];(folder/'QC_IMAGE_001.txt').write_text('updated')
  self.assertEqual(self.req('POST','/rename/commit',{'previewId':preview['previewId']})[0],409)
if __name__=='__main__':unittest.main(verbosity=2)

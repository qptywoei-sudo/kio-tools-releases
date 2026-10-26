"""Real synthetic FFmpeg timelines: pixels, timing, sound, guards and cleanup."""
import array,copy,hashlib,math,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1];sys.path[:0]=[str(source/'engine'),str(source/'agent')]
import engine_extra,video_editor
from PIL import Image
import imageio_ffmpeg

class VideoEditorEngineTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
  cls.red=cls.root/'원본 영상.mp4';cls.blue=cls.root/'no-audio.mp4';cls.wave=cls.root/'music.wav';cls.still=cls.root/'사진.png';cls.overlay=cls.root/'overlay.png'
  def generate(args,path):subprocess.run([cls.ffmpeg,'-hide_banner','-loglevel','error','-nostdin',*args,'-y',str(path)],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  generate(['-f','lavfi','-i','color=c=red:s=160x90:r=20','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3','-c:v','mpeg4','-pix_fmt','yuv420p','-c:a','aac'],cls.red)
  generate(['-f','lavfi','-i','color=c=blue:s=90x160:r=20','-t','3','-c:v','mpeg4','-pix_fmt','yuv420p'],cls.blue)
  generate(['-f','lavfi','-i','sine=frequency=880:sample_rate=48000','-t','3','-c:a','pcm_s16le'],cls.wave)
  Image.new('RGB',(160,90),'green').save(cls.still);Image.new('RGB',(40,20),'yellow').save(cls.overlay)
  cls.inputs=list(map(str,[cls.red,cls.blue,cls.wave,cls.still,cls.overlay]));cls.digests={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in cls.inputs}
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def setUp(self):
  self.output=Path(tempfile.mkdtemp(dir=self.root));self.job={'op':'video_edit','inputs':self.inputs,'output_dir':str(self.output),'width':160,'height':90,'fps':20,'clips':[{'source':0,'kind':'video','start':.5,'end':1.5,'volume':0},{'source':3,'kind':'image','start':0,'end':1},{'source':1,'kind':'video','start':.25,'end':1.25}]}
 def tearDown(self):
  for path,digest in self.digests.items():self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),digest)
  self.assertFalse(list(self.output.glob('.video-*')));self.assertFalse(list(self.output.glob('.*.tmp*')))
 def run_job(self,job=None):
  values=[];result=engine_extra.run(job or self.job,values.append);self.assertTrue(result['success']);self.assertEqual(len(result['files']),1);self.assertEqual(values[-1],95);return Path(result['files'][0]),result['data']
 def frame(self,path,at):
  data=subprocess.check_output([self.ffmpeg,'-hide_banner','-loglevel','error','-ss',str(at),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],timeout=15)
  return Image.frombytes('RGB',(160,90),data)
 def rms(self,path,at,duration=.2):
  data=subprocess.check_output([self.ffmpeg,'-hide_banner','-loglevel','error','-ss',str(at),'-i',str(path),'-t',str(duration),'-vn','-ar','48000','-ac','1','-f','s16le','pipe:1'],timeout=15)
  samples=array.array('h',data);return math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))
 def test_concat_trim_still_overlay_music_and_mute_render_real_pixels_and_audio(self):
  self.job.update(overlays=[{'source':4,'start':0,'end':.5,'x':0,'y':0,'width':.25}],audio=[{'source':2,'start':.2,'end':1.2,'at':1,'volume':.5}])
  path,data=self.run_job();self.assertEqual(data['duration'],3);self.assertEqual(data['clipCount'],3)
  self.assertGreater(self.frame(path,.25).getpixel((10,10))[1],200)
  self.assertLess(self.frame(path,.75).getpixel((10,10))[1],20)
  self.assertGreater(self.frame(path,1.5).getpixel((80,45))[1],100)
  self.assertGreater(self.frame(path,2.5).getpixel((80,45))[2],200)
  self.assertLess(self.rms(path,.6),10);self.assertGreater(self.rms(path,1.5),500);self.assertLess(self.rms(path,2.5),10)
 def test_original_audio_kept_and_normalized_without_music(self):
  self.job['clips']=[{'source':0,'kind':'video','start':1,'end':2,'volume':1}]
  path,_=self.run_job();self.assertGreater(self.rms(path,.25),1000)
 def test_audio_only_trim_placement_and_silence_gap(self):
  self.job.update(format='m4a',clips=[],audio=[{'source':0,'start':.5,'end':1,'at':0,'volume':1},{'source':2,'start':1,'end':1.5,'at':1,'volume':.5}])
  path,data=self.run_job();self.assertEqual(path.suffix,'.m4a');self.assertTrue(data['audioOnly']);self.assertEqual(data['duration'],1.5)
  self.assertGreater(self.rms(path,.15),1000);self.assertLess(self.rms(path,.7),20);self.assertGreater(self.rms(path,1.2),500)
 def test_korean_subtitle_is_visible_only_inside_requested_time(self):
  self.job['clips']=[{'source':3,'kind':'image','start':0,'end':1.5}]
  self.job['texts']=[{'text':'한글 자막\n\'[]; hello','start':.2,'end':1,'x':.5,'y':.15,'fontSize':18,'color':'#ffffff','background':True}]
  path,_=self.run_job();early=self.frame(path,.05);active=self.frame(path,.5);late=self.frame(path,1.2)
  region=lambda image:sum(1 for r,g,b in image.crop((10,12,150,75)).getdata() if min(r,g,b)>170)
  self.assertGreater(region(active),50);self.assertLess(region(early),5);self.assertLess(region(late),5)
 def test_invalid_schema_rejected_before_launching_ffmpeg(self):
  invalid=[{'clips':[{'source':'C:/secret','kind':'video','start':0,'end':1}]},{'clips':[{'source':True,'kind':'video','start':0,'end':1}]},{'width':1920,'height':1920},{'fps':float('inf')},{'clips':self.job['clips']*21},{'audio':[{'source':2,'start':0,'end':2,'at':1800}]},{'texts':[{'text':'bad','start':0,'end':1,'color':"red;movie=http://example"}]},{'overlays':[{'source':4,'start':0,'end':1801}]},{'duration':1}]
  for changes in invalid:
   with self.subTest(changes=changes),patch.object(video_editor.subprocess,'run') as run:
    with self.assertRaises(ValueError):self.run_job({**self.job,**changes})
    run.assert_not_called()
 def test_playlist_spoof_and_out_of_bounds_source_interval_leave_no_output(self):
  playlist=self.root/'malicious.mp4';playlist.write_text('#EXTM3U\nhttp://127.0.0.1/private\n')
  bad={**self.job,'inputs':[str(playlist)],'clips':[{'source':0,'kind':'video','start':0,'end':1}]}
  with patch.object(video_editor.subprocess,'run') as run:
   with self.assertRaisesRegex(ValueError,'unsupported'):self.run_job(bad)
   run.assert_not_called()
  self.job['clips']=[{'source':0,'kind':'video','start':2,'end':4}]
  with self.assertRaisesRegex(ValueError,'invalidRequest'):self.run_job()
  self.assertEqual(list(self.output.iterdir()),[])
 def test_video_extends_with_black_tail_to_music_and_overlay_end(self):
  self.job.update(clips=[{'source':0,'kind':'video','start':0,'end':.5,'volume':0}],audio=[{'source':2,'start':0,'end':1.5,'at':0}],overlays=[{'source':4,'start':1,'end':2,'x':0,'y':0,'width':.25}])
  path,data=self.run_job();self.assertEqual(data['duration'],2);self.assertGreater(self.rms(path,1),500)
  self.assertLess(max(self.frame(path,1.25).getpixel((80,45))),10);self.assertGreater(self.frame(path,1.25).getpixel((10,10))[1],200);self.assertLess(self.rms(path,1.7),20)
 def test_audio_export_includes_original_clip_sound_and_music_with_requested_silent_tail(self):
  self.job.update(format='m4a',clips=[{'source':0,'kind':'video','start':0,'end':.5,'volume':1}],audio=[{'source':2,'start':0,'end':.5,'at':1}],duration=2)
  path,data=self.run_job();self.assertEqual(data['duration'],2);self.assertGreater(self.rms(path,.1),1000);self.assertLess(self.rms(path,.7),20);self.assertGreater(self.rms(path,1.2),1000);self.assertLess(self.rms(path,1.7),20)
 def test_encoder_failure_cleans_partial_exports(self):
  with patch.object(video_editor.Renderer,'run',side_effect=ValueError('processingFailed')):
   with self.assertRaisesRegex(ValueError,'processingFailed'):self.run_job()
  self.assertEqual(list(self.output.iterdir()),[])

if __name__=='__main__':unittest.main(verbosity=2)

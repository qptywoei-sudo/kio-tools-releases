import sys,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import ffmpeg_runtime

class FFmpegRuntimeTests(unittest.TestCase):
 def test_moved_package_resolves_neighbor_tools_directory_without_environment(self):
  with tempfile.TemporaryDirectory() as root:
   tools=Path(root)/'새 설치 경로'/'tools';engine=tools/'engine';engine.mkdir(parents=True);binary=tools/'ffmpeg'/'ffmpeg.exe';binary.parent.mkdir();binary.write_bytes(b'fixture')
   with patch.object(ffmpeg_runtime,'__file__',str(engine/'ffmpeg_runtime.py')),patch.object(ffmpeg_runtime,'sys',SimpleNamespace(platform='win32')),patch.object(ffmpeg_runtime,'os',SimpleNamespace(name='nt')):
    self.assertEqual(ffmpeg_runtime.executable(),str(binary.resolve()))
 def test_missing_package_keeps_imageio_fallback(self):
  with tempfile.TemporaryDirectory() as root,patch.object(ffmpeg_runtime,'__file__',str(Path(root)/'engine'/'ffmpeg_runtime.py')),patch.dict(sys.modules,{'imageio_ffmpeg':SimpleNamespace(get_ffmpeg_exe=lambda:'legacy-or-explicit-test-runtime')}):
   self.assertEqual(ffmpeg_runtime.executable(),'legacy-or-explicit-test-runtime')
if __name__=='__main__':unittest.main(verbosity=2)

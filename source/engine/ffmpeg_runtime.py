"""Resolve a relocatable packaged FFmpeg before the legacy imageio fallback."""
import os,platform,sys
from pathlib import Path

def executable():
    if sys.platform=='darwin':
        arch='arm64' if platform.machine() in ('arm64','aarch64') else 'x86_64'
        root=Path(__file__).resolve().parent
        for packaged in (root.parent/'ffmpeg'/arch/'ffmpeg',root.parent.parent/'tools'/'ffmpeg'/arch/'ffmpeg'):
            if packaged.is_file() and not packaged.is_symlink():return str(packaged)
    if os.name=='nt':
        root=Path(__file__).resolve().parent
        for packaged in (root.parent/'ffmpeg'/'ffmpeg.exe',root.parent.parent/'tools'/'ffmpeg'/'ffmpeg.exe'):
            if packaged.is_file() and not packaged.is_symlink():return str(packaged)
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

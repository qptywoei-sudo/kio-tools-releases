"""Local U2NETP subject mask; no network, account or external image transfer."""
from pathlib import Path
import hashlib,threading

MODEL_SHA256='309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8'
_net=None
_lock=threading.Lock()

def subject_alpha(image):
 import cv2,numpy as np
 from PIL import Image
 global _net
 if min(image.size)<4 or max(image.size)>16384 or image.width*image.height>64000000:raise ValueError('invalidRequest')
 path=Path(__file__).resolve().parent/'models'/'u2netp.onnx'
 with _lock:
  if _net is None:
   if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=MODEL_SHA256:raise ValueError('modelUnavailable')
   _net=cv2.dnn.readNetFromONNX(str(path));_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV);_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
  rgb=np.asarray(image.convert('RGB').resize((320,320),Image.Resampling.LANCZOS),dtype=np.float32)
  rgb/=max(float(rgb.max()),1.0)
  if float(rgb.std(axis=(0,1)).max())<1e-4:raise ValueError('subjectNotFound')
  normalized=(rgb-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
  _net.setInput(np.transpose(normalized,(2,0,1))[None].copy())
  # ONNX has seven outputs; 1959 is the fused d0 prediction in the pinned model.
  names=_net.getUnconnectedOutLayersNames();out=_net.forward(names)
  prediction=out[names.index('1959') if '1959' in names else 0][0,0]
  low=float(prediction.min());high=float(prediction.max())
  if high-low<1e-6:raise ValueError('subjectNotFound')
  alpha=np.clip((prediction-low)/(high-low)*255,0,255).astype(np.uint8)
  if np.count_nonzero(alpha>128)<16:raise ValueError('subjectNotFound')
  return Image.fromarray(alpha).resize(image.size,Image.Resampling.LANCZOS)

def automatic_cutout(image):
 from PIL import ImageChops
 result=image.convert('RGBA').copy();result.putalpha(ImageChops.multiply(subject_alpha(result),result.getchannel('A')))
 return result

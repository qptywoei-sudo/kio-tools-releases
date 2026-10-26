"""Load optional document/code engines only when that feature is actually used."""
import importlib
import threading

class DeferredModule:
    def __init__(self,name):
        self._name=name
        self._module=None
        self._lock=threading.RLock()
    def __getattr__(self,key):
        with self._lock:
            if self._module is None:self._module=importlib.import_module(self._name)
            return getattr(self._module,key)

def barcode_image_writer(*args,**kwargs):
    from barcode.writer import ImageWriter
    return ImageWriter(*args,**kwargs)

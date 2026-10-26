"""Actual private-spool cancellation protocol, without OS UI or user files."""
import json,sys,tempfile,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from common import NativeBridge,AgentError,atomic_json

class NativeCancelTests(unittest.TestCase):
 def run_capture(self,timeout=False,complete=False):
  with tempfile.TemporaryDirectory() as folder:
   bridge=NativeBridge(folder);atomic_json(bridge.root/'status.json',{'updatedAt':time.time()})
   accepted=threading.Event();stop=threading.Event();seen=[];original=[]
   def native():
    while not stop.is_set():
     for file in (bridge.root/'requests').glob('*.json'):
      try:r=json.loads(file.read_text())
      except (OSError,ValueError):continue
      file.unlink(missing_ok=True);seen.append(r)
      if r['operation']=='capture.start':
       original.append(r['id']);accepted.set()
       if complete:atomic_json(bridge.root/'responses'/f"{r['id']}.json",{'id':r['id'],'ok':True,'data':{'paths':['test.png']}})
      elif r['operation']=='capture.cancel':
       atomic_json(bridge.root/'responses'/f"{r['id']}.json",{'id':r['id'],'ok':True,'data':{'cancelledCapture':r['args']['requestId'] in original}})
     stop.wait(.01)
   worker=threading.Thread(target=native);worker.start()
   try:
    if complete:self.assertEqual(bridge.call('capture.start',{},2)['paths'],['test.png'])
    else:
     with self.assertRaises(AgentError) as error:bridge.call('capture.start',{},.3 if timeout else 2,cancel=None if timeout else accepted.is_set)
     self.assertEqual(error.exception.code,'timeout' if timeout else 'cancelled')
   finally:stop.set();worker.join(2)
   cancellations=[r for r in seen if r['operation']=='capture.cancel']
   self.assertEqual(len(cancellations),0 if complete else 1)
   if cancellations:self.assertEqual(cancellations[0]['args'],{'requestId':original[0]})
   self.assertEqual(list((bridge.root/'requests').glob('*.json')),[])
   self.assertEqual(list((bridge.root/'responses').glob('*.json')),[])
 def test_cancel_ends_only_matching_native_request(self):self.run_capture()
 def test_timeout_also_releases_native_selection(self):self.run_capture(timeout=True)
 def test_success_does_not_cancel_another_capture(self):self.run_capture(complete=True)
 def test_queued_start_removed_before_cancel_can_run(self):
  with tempfile.TemporaryDirectory() as folder:
   cancelled=[]
   class QueuedBridge(NativeBridge):
    def call(inner,operation,args=None,timeout=90,cancel=None):
     if operation=='capture.cancel':
      self.assertEqual(list((inner.root/'requests').glob('*.json')),[])
      cancelled.append(args['requestId']);return {'cancelledCapture':False}
     return super().call(operation,args,timeout,cancel)
   bridge=QueuedBridge(folder);atomic_json(bridge.root/'status.json',{'updatedAt':time.time()})
   with self.assertRaises(AgentError) as error:bridge.call('capture.start',{},2,cancel=lambda:True)
   self.assertEqual(error.exception.code,'cancelled');self.assertEqual(len(cancelled),1)
if __name__=='__main__':unittest.main()

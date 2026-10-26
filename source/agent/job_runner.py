"""Isolated bounded worker for trusted typed jobs, never a command/shell broker."""
import json,sys
from pathlib import Path
# Windows pipes otherwise use the ANSI code page, while the agent reads UTF-8.
# Korean result messages and file names must survive this subprocess boundary.
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='strict')
if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8',errors='replace')
_engine_dir=Path(__file__).resolve().parent.parent
if not (_engine_dir/'engine.py').is_file():_engine_dir=_engine_dir/'engine'
sys.path.insert(0,str(_engine_dir))
import engine,engine_extra

def progress(value):
 print(json.dumps({'progress':int(value)}),flush=True)
if __name__=='__main__':
 try:
  job=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));op=job['op']
  if op=='pdf_annotate':
   if len(job.get('inputs',[]))<2:raise ValueError('inputMissing')
   job['overlay_path']=job['inputs'][1]
  if op in engine.OPERATIONS and not (op=='code_generate'):answer=engine.run(job)
  elif op=='web_stitch':answer=engine_extra.web_stitch(job,progress)
  else:answer=engine_extra.run(job,progress)
  print(json.dumps({'result':answer},ensure_ascii=False),flush=True)
  sys.exit(0 if answer.get('success',True) else 1)
 except Exception as error:
  known={'unsupported','inputMissing','invalidRequest','fileTooLarge','modelMissing','textPdfRequired','tableNotFound','qrScanFailed'}
  code=str(error) if str(error) in known else 'processingFailed'
  print(json.dumps({'errorCode':code}),flush=True);sys.exit(1)

"""Explicit local synthetic-image evaluation; SIWC only, no API key or automatic policy changes.
Usage (bundled Python): ai_model_benchmark.py --output PATH [--model gpt-6-luna]
Reports contain synthetic fixtures/results only. Never run during another active AI job.
"""
import argparse,io,json,os,re,statistics,sys,threading,time,unicodedata
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parent.parent/'engine/deps-agent/win64')]
from ai_translate import AITranslate
from PIL import Image,ImageDraw,ImageFont
from difflib import SequenceMatcher

CASES=[
 ('ja-ko','ko','ja',['田中','明日の会議は午前9:30です。','資料を3部持ってきてください。'],['9:30','3']),
 ('en-ko','ko','en',['INVOICE KIO-1042','Total: USD 1,250.50','Due date: 2026-10-31','Please pay by bank transfer.'],['1,250.50','2026','10','31']),
 ('vi-ko','ko','vi',['Minh','Ngày mai gặp nhau lúc 14:30 nhé.','Tôi sẽ gửi 2 tài liệu trước cuộc họp.'],['14:30','2']),
 ('zh-ko','ko','zh',['订单确认','数量：12件','总金额：人民币350元','请在10月20日前确认地址。'],['12','350','10','20']),
 ('ko-en','en','ko',['배송 안내','주문번호: KIO-2026','배송은 10월 15일 오후 3시입니다.','주소가 바뀌면 미리 알려주세요.'],['KIO-2026','15','3']),
 ('mixed-group','ko','mixed',['TEAM CHAT','Alice: Could we meet at 10:00?','Minh: Tôi rảnh lúc 11:30.','田中: 私は午後なら大丈夫です。'],['10:00','11:30']),
 ('clipped','ko','en',['Alice','The delivery date is 2026-10-','Please confirm the next ord'],['2026','10']),
 ('kakao-style','ko','en',['TEAM CHAT','Alex: Can you send 3 photos before 16:30?','Me: I can send them after lunch.','Alex: Great. Keep the original file names.','Me: Should I include the invoice?','Alex: Yes, the total should be USD 125.50.'],['3','16:30','125.50']),
 ('long-document','ko','en',['PROJECT DELIVERY NOTICE','Reference: KIO-2026-1042','Delivery date: 2026-10-20 at 09:30.','The package contains 12 files and 3 images.','Please review every page before approval.','Do not change the original file names.','The total amount is USD 1,250.50.','Payment is due within 14 days.','If the address changes, contact our team.','A second copy will be kept for 30 days.','The revised document replaces version 2.','Please confirm receipt by Friday.','Thank you for your cooperation.'],['KIO-2026-1042','09:30','12','3','1,250.50','14','30','2']),
]
def normalized(text):return re.sub(r'\s','',unicodedata.normalize('NFKC',text))
def run(output,model,efforts=('none','low'),case_names=None,repeats=1):
 app=AITranslate(Path(os.environ['LOCALAPPDATA'])/'GalaxyControl/Agent',None)
 app.account.list_models();available=next((m for m in app.account.models if m['id']==model),None)
 if not available or available['vision'] is False:raise RuntimeError('Requested account model unavailable for image input')
 output.mkdir(parents=True,exist_ok=True);rows=[]
 fonts={code:ImageFont.truetype('C:/Windows/Fonts/'+name,32) for code,name in {'ko':'malgun.ttf','ja':'meiryo.ttc','zh':'msyh.ttc','vi':'arial.ttf','en':'arial.ttf'}.items()}
 cases=[row for row in CASES if not case_names or row[0] in case_names]
 for index,(ident,base,language,lines,numbers) in enumerate(cases*repeats):
  image=Image.new('RGB',(1080,100+60*len(lines)),'#fffef8');draw=ImageDraw.Draw(image)
  for n,line in enumerate(lines):
   code=('vi' if n==2 else 'ja' if n==3 else 'en') if language=='mixed' else language
   draw.text((30,30+n*60),line,font=fonts[code],fill='#17202a')
  image.save(output/(ident+'.png'));stream=io.BytesIO();image.save(stream,'PNG')
  for effort in (efforts if index%2==0 else list(reversed(efforts))):
   job={'id':'benchmark-'+ident,'settings':{'language':base,'customLanguage':'','model':model,'reasoning':effort},'cancel':threading.Event(),'generation':app.account.generation,'stage':'','received':0,'_benchmarkReasoningProbe':True}
   started=time.perf_counter();record={'case':ident,'baseLanguage':base,'effort':effort,'expectedText':'\n'.join(lines),'expectedLanguage':language}
   try:
    result=app.translate_png(job,stream.getvalue());original='\n'.join(m['originalText'] for m in result['messages']);translated='\n'.join(m['translatedText'] for m in result['messages'])
    actual='\n'.join((m['speaker']+'\n' if m['speaker'] and m['speaker'] not in m['originalText'] else '')+m['originalText'] for m in result['messages'])
    record.update(ok=True,result=result,ocrSimilarity=round(SequenceMatcher(None,normalized(record['expectedText']),normalized(actual)).ratio(),4),numbersPreserved=all(number in original and number in translated for number in numbers),timings={k:round(v-job['timings']['requestStartedAt'],2) for k,v in job.get('timings',{}).items() if k in ('firstResponseAt','completedAt')})
   except Exception as e:record.update(ok=False,error=getattr(e,'code',type(e).__name__))
   record['seconds']=round(time.perf_counter()-started,3);rows.append(record)
   (output/'benchmark.json').write_text(json.dumps({'model':model,'accountModel':available,'cases':rows},ensure_ascii=False,indent=2),encoding='utf-8')
   print(json.dumps({k:v for k,v in record.items() if k not in ('result','expectedText')},ensure_ascii=False),flush=True)
 summary={effort:{'samples':len([r for r in rows if r['effort']==effort]),'success':sum(r['ok'] for r in rows if r['effort']==effort),'medianSeconds':round(statistics.median(r['seconds'] for r in rows if r['effort']==effort),3),'meanSeconds':round(statistics.mean(r['seconds'] for r in rows if r['effort']==effort),3),'maxSeconds':max(r['seconds'] for r in rows if r['effort']==effort)} for effort in efforts}
 (output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--model',default='gpt-6-luna');parser.add_argument('--efforts',nargs='+',default=['none','low']);parser.add_argument('--cases',nargs='+');parser.add_argument('--repeats',type=int,default=1);args=parser.parse_args();run(args.output,args.model,args.efforts,args.cases,args.repeats)

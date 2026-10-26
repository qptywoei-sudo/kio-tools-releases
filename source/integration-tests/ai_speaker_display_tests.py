import sys,unittest,copy
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'agent'),str(root/'engine/deps-agent/win64')]
from ai_translate import validate_result
def row(name,body,translated):return dict(speaker=name,isMine=False,originalText=body,translatedText=translated,language='vi',confidence=.98,isTruncated=False)
def data(rows,target):return dict(contentType='conversation',originalLanguage='vi',detectedReplyLanguage='vi',replyTarget=target,messages=rows)
class SpeakerTests(unittest.TestCase):
 def test_merge_exact_speaker_label_and_remap_reply(self):
  name='Đỗ Thành Đăng (CS)';result=validate_result(data([row(name,name,'도 탄 당 (CS)'),row(name,'Khách BH chuẩn bị vào audit a','고객이 감사에 들어올 준비 중입니다.')],1))
  self.assertEqual(len(result['messages']),1);self.assertEqual(result['messages'][0]['speakerTranslated'],'도 탄 당 (CS)');self.assertEqual(result['replyTarget'],0);self.assertEqual(result['detectedReplyLanguage'],'vi')
 def test_actual_message_and_unrelated_headings_are_never_dropped(self):
  result=validate_result(data([row('A','A','에이'),row('B','A','에이'),row('B','Hi','안녕')],2));self.assertEqual(len(result['messages']),3);self.assertEqual(result['replyTarget'],2)
 def test_truncated_name_is_preserved(self):
  first=row('A','A','에이');first['isTruncated']=True;result=validate_result(data([first,row('A','Hi','안녕')],1));self.assertEqual(len(result['messages']),2)
if __name__=='__main__':unittest.main(verbosity=2)

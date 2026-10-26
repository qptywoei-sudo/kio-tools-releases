const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server'),load=require('./load-source.cjs');
const {canReplyTo,replyRequest,AIReplyComposer}=load('features/local-tools/AIReplyComposer.tsx');
const row={speaker:'Quân - OQC',speakerTranslated:'꾸언 - OQC',originalText:'NO01. Lỗi mất chip',translatedText:'NO01. 칩 누락 불량',language:'vi',isMine:false,confidence:.98,isTruncated:false};
const data={sessionId:'session',messages:[row,{...row,speaker:'나',isMine:true},{...row,speaker:'uncertain',language:null},{...row,speaker:'low-confidence',confidence:.4}]};
test('automatic reply uses selected message context, empty intent and no image',()=>{
 assert.deepEqual(replyRequest(data,0,'typed content must not leak into automatic mode','auto'),{sessionId:'session',target:0,intent:''});
 assert.deepEqual(replyRequest(data,0,' 정중하게 거절 ','intent'),{sessionId:'session',target:0,intent:'정중하게 거절'});
 assert.deepEqual(replyRequest(data,0,'unused','retranslate','Xin chào'),{sessionId:'session',target:0,intent:'',replyText:'Xin chào'});
});
test('unknown, own and low-confidence targets cannot generate a reply',()=>{
 for(const target of [null,-1,1,2,3,4])assert.equal(replyRequest(data,target,'','auto'),null);
 assert.equal(replyRequest(data,0,'   ','intent'),null);assert.equal(replyRequest(data,0,'','retranslate','  '),null);
 assert.ok(canReplyTo({...row,isMine:null}));
});
test('target picker excludes unsafe candidates and offers explicit automatic generation',()=>{
 const html=renderToStaticMarkup(React.createElement(AIReplyComposer,{messages:data.messages,target:0,working:false,intent:'',edited:'',reply:null,onTarget(){},onIntent(){},onEdited(){},onGenerate(){},copyButton(){return null;}}));
 assert.ok(html.includes('자동 답장 생성'));assert.ok(html.includes('Quân - OQC'));assert.ok(!html.includes('low-confidence'));assert.ok(!html.includes('uncertain'));assert.ok(!html.includes('<textarea'));
 const disabled=renderToStaticMarkup(React.createElement(AIReplyComposer,{messages:[{...row,language:null}],target:null,working:false,intent:'',edited:'',reply:null,onTarget(){},onIntent(){},onEdited(){},onGenerate(){},copyButton(){return null;}}));
 assert.match(disabled,/button[^>]*disabled/);assert.ok(disabled.includes('언어를 확인할 수 없습니다'));
});

const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server'),load=require('./load-source.cjs');
const {TranslationMessages,translationMessageText}=load('features/local-tools/TranslationMessages.tsx');
const {SmartScanResult,smartText,noCorrectionNeeded}=load('features/local-tools/SmartScanPanel.tsx');
test('speaker and pronunciation share one line and copy as three compact lines',()=>{
 const row={speaker:'Đỗ Thành Đăng (CS)',speakerTranslated:'도 탄 당 (CS)',originalText:'Khách BH chuẩn bị vào audit a',translatedText:'보험 고객이 감사를 받으러 들어갈 준비를 하고 있어요.',language:'vi',isMine:false,confidence:.99,isTruncated:false};
 const html=renderToStaticMarkup(React.createElement(TranslationMessages,{messages:[row],target:0,replyOpen:false,working:false,onTarget(){},copyButton(){return null;}}));
 assert.equal((html.match(/<article/g)||[]).length,1);assert.equal(html.split(row.speaker).length-1,1);assert.equal(html.split(row.speakerTranslated).length-1,1);
 assert.equal(translationMessageText(row),[row.speaker+' / '+row.speakerTranslated,row.originalText,row.translatedText].join('\n'));
});
test('unchanged correction clearly says no correction without a duplicate text block',()=>{
 const value={task:'correct',model:'test',baseLanguage:'ko',originalText:'The meeting starts at 9:30.',text:'The meeting starts at 9:30.',changes:[],uncertain:[]};
 const html=renderToStaticMarkup(React.createElement(SmartScanResult,{value,onCopy(){},onTranslate(){}}));
 assert.ok(noCorrectionNeeded(value));assert.ok(html.includes('교정할 사항이 없습니다.'));assert.equal(html.split(value.text).length-1,1);assert.ok(smartText(value).includes('교정할 사항이 없습니다.'));
 assert.ok(!noCorrectionNeeded({...value,text:'The meeting started at 9:30.'}));assert.ok(!noCorrectionNeeded({...value,uncertain:['Clipped text']}));
});

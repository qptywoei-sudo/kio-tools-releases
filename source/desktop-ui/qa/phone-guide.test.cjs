const test=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const load=require('./load-source.cjs');
const {PhoneSetupGuide}=load('features/local-tools/PhoneSetupGuide.tsx');
const {phoneSetupText,phoneGuideSources}=load('features/local-tools/phone-setup-text.ts');
const render=(device,language='ko',connected=true)=>renderToStaticMarkup(React.createElement(PhoneSetupGuide,{device,language,connected,onDeviceChange(){},onOpenWireless(){},onRefresh(){}}));
test('phone help states iPhone capability separately from Android in every supported language',()=>{
 for(const language of ['ko','en','ja','zh','vi']){
  const text=phoneSetupText(language),html=render('iphone',language);
  assert.ok(html.includes(text.iphoneLimit));
  assert.ok(html.includes(text.iphoneCableTitle));
  assert.equal((html.match(/class="kio-phone-step"/g)||[]).length,3);
  assert.ok(!html.includes(text.usbDebugging));
  assert.notEqual(text.pairAddress,text.connectAddress);
 }
});
test('setup illustrations do not expose pretend device-setting controls',()=>{
 const html=render('android');
 assert.equal((html.match(/class="kio-phone-step"/g)||[]).length,4);
 assert.ok(html.includes('× 7'));
 assert.ok(html.includes('class="kio-phone-toggle"'));
 assert.ok(!html.includes('type="checkbox"'));
 assert.ok(!html.includes('role="switch"'));
 assert.ok(render('android','ko',false).includes('disabled=""'));
});
test('official setup links use verified provider domains and safe external navigation',()=>{
 for(const url of Object.values(phoneGuideSources)){
  const parsed=new URL(url);
  assert.equal(parsed.protocol,'https:');
  assert.ok(['www.samsung.com','www.samsungsvc.co.kr','developer.samsung.com','developer.android.com','support.apple.com','support.microsoft.com'].includes(parsed.hostname));
 }
 const html=render('iphone');
 assert.ok(html.includes('target="_blank" rel="noreferrer"'));
});

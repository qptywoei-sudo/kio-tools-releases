const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),load=require('./load-source.cjs');
const {toolLanguageOrder,orderedToolLanguages,normalizeToolLanguage,uiText,ToolsLocaleProvider}=load('features/local-tools/tool-locale.tsx');
const {localToolsTranslations,localToolsTranslator}=load('features/local-tools/translations.ts');
const {browserToolsTranslator}=load('features/browser-tools/translations.ts');
const {loginCopy}=load('features/local-tools/login-copy.ts');
const {editorText}=load('features/local-tools/editor-text.ts');
const {phoneSetupText}=load('features/local-tools/phone-setup-text.ts');
const {extensionGuideText}=load('features/local-tools/extension-guide-text.ts');
const {GeneralSettings}=load('features/local-tools/GeneralSettings.tsx');
const {SmartScanPicker}=load('features/local-tools/SmartScanPanel.tsx');
const {StampDesigner}=load('features/local-tools/StampDesigner.tsx');
const copy=require('../src/features/local-tools/ui-copy.json');
const fields=text=>[...text.matchAll(/\{(\w+)\}/g)].map(x=>x[1]).sort();
test('six languages match the web order and always place the saved choice first',()=>{
 assert.deepEqual(toolLanguageOrder,['vi','en','ko','ja','zh-TW','zh']);for(const language of toolLanguageOrder)assert.deepEqual(orderedToolLanguages(language),[language,...toolLanguageOrder.filter(code=>code!==language)]);assert.equal(normalizeToolLanguage('zh-CN'),'zh');assert.equal(normalizeToolLanguage('zh-TW'),'zh-TW');assert.equal(normalizeToolLanguage('invalid'),null);
});
test('all static tool catalogs have complete six-language rows and preserve placeholders',()=>{
 for(const row of localToolsTranslations)for(const lang of toolLanguageOrder){assert.ok(row[lang]?.trim(),row.key+' '+lang);assert.deepEqual(fields(row[lang]),fields(row.ko),row.key+' '+lang);}
 for(const [key,row]of Object.entries(copy))for(const lang of toolLanguageOrder.filter(l=>l!=='ko')){assert.ok(row[lang]?.trim(),key+' '+lang);assert.deepEqual(fields(row[lang]),fields(key),key+' '+lang);}
});
test('Traditional Chinese is independent across login, capture, phone, extension and navigation',()=>{
 for(const language of toolLanguageOrder){assert.ok(loginCopy[language].title);assert.ok(editorText(language,'toolOptions'));assert.ok(phoneSetupText(language).title);assert.ok(extensionGuideText(language));assert.ok(browserToolsTranslator(language)('web.home'));assert.notEqual(localToolsTranslator(language)('tools.image'),'tools.image');}
 assert.notEqual(loginCopy['zh-TW'].continue,loginCopy.zh.continue);assert.notEqual(uiText('zh-TW','사진 추가'),uiText('zh','사진 추가'));
});
test('real settings, ten scan buttons and stamp font options render in every UI language',()=>{
 const geometry=load('features/local-tools/signature-geometry.ts'),original=geometry.stampImage;geometry.stampImage=()=>''; // This case checks labels; pixel rendering is exercised in the browser.
 const render=(language,element)=>renderToStaticMarkup(React.createElement(ToolsLocaleProvider,{language},element));
 try{for(const language of toolLanguageOrder){
  const t=localToolsTranslator(language),general=render(language,React.createElement(GeneralSettings,{settings:{shortcuts:{}},onSettings(){},permissions:{},t,onPermission(){},onApply(){},onShortcutsChange:async()=>true,windows:true}));
  const scan=render(language,React.createElement(SmartScanPicker,{preview:'',onChoose(){},disabled:false}));
  const stamp=render(language,React.createElement(StampDesigner,{stamp:{shape:'circle',color:'#f00',name:'Alice',company:'KIO',date:''},url:'',onChange(){},onNew(){},editing:false,disabled:false}));
  assert.equal((scan.match(/<button/g)||[]).length,10);assert.equal((stamp.match(/<optgroup/g)||[]).length,2);assert.equal((stamp.match(/value="(?:ko-|hanja-)/g)||[]).length,6);
  if(language!=='ko')for(const html of [general,scan,stamp])assert.ok(!/[가-힣]/.test(html.replace(/src="[^"]*"/g,'').replace(/\d{4}년 \d{1,2}월 \d{1,2}일/g,'')),'untranslated UI in '+language+' '+JSON.stringify(html.match(/.{0,35}[가-힣].{0,35}/g)));
 }}finally{geometry.stampImage=original;}
});
test('UI translation does not alter user filenames or interpolated messages',()=>assert.equal(uiText('en','{v0} 삭제',{v0:'회사 자료.png'}),'Delete 회사 자료.png'));
test('native connection and capture/install guidance include all six languages',()=>{
 const bridge=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../../i18n/native-bridge.json'),'utf8'));
 for(const [key,row] of Object.entries(bridge))for(const lang of ['vi','en','ko','ja','zh-TW','zh-CN'])assert.ok(row[lang]?.trim(),key+' '+lang);
 for(const language of toolLanguageOrder){const t=localToolsTranslator(language);for(const key of ['installMac','installWindows','capturePermissionHint'])assert.ok(t('tools.'+key).trim());assert.ok(t('tools.installMac').includes('ZIP'));assert.ok(!t('tools.installMac').includes('DMG'));}
});

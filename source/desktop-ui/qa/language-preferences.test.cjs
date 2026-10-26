const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-source.cjs');
const {languages,normalizeLanguage,resolveLanguage,orderedLanguages,initialLanguage,saveLanguage}=load('i18n/language.ts');
test('normalization and precedence match the native policy',()=>{
 const cases={'zh-CN':'zh-CN','zh-SG':'zh-CN','zh-Hans':'zh-CN','zh-Hans-TW':'zh-CN','zh-TW':'zh-TW','zh-HK':'zh-TW','zh-MO':'zh-TW','zh-Hant':'zh-TW','zh-Hant-CN':'zh-TW','zh':'zh-CN','ko-KR':'ko','en-US':'en','en-GB':'en','ja-JP':'ja','vi-VN':'vi'};
 for(const [raw,code]of Object.entries(cases))assert.equal(normalizeLanguage(raw),code);
 assert.deepEqual(resolveLanguage('ja',['vi-VN'],'ko'),{language:'ja',source:'user'});
 assert.deepEqual(resolveLanguage(null,['fr-FR','ko-KR'],'ja'),{language:'en',source:'system'});
 assert.deepEqual(resolveLanguage(null,[],'zh-HK'),{language:'zh-TW',source:'account'});
});
test('first launch, changing OS locale and explicit migration do not require an account',()=>{
 const descriptors={};for(const key of ['navigator','localStorage','location','__kioLocale'])descriptors[key]=Object.getOwnPropertyDescriptor(globalThis,key);
 const data=new Map();Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v)}});
 Object.defineProperty(globalThis,'location',{configurable:true,value:new URL('http://127.0.0.1:4323/tools/')});
 try{
  for(const language of languages){Object.defineProperty(globalThis,'navigator',{configurable:true,value:{languages:[language],language:'ko-KR'}});assert.deepEqual(initialLanguage(),{language,source:'system'});assert.equal(data.size,0);}
  saveLanguage('vi');globalThis.__kioLocale={language:'ko',source:'system'};assert.equal(initialLanguage().language,'vi');
  globalThis.__kioLocale={language:'zh-TW',source:'user'};assert.equal(initialLanguage().language,'zh-TW');
  data.clear();delete globalThis.__kioLocale;data.set('focus-base.language','zh');assert.equal(initialLanguage().language,'zh-CN');
  data.clear();Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw Error('blocked');}});assert.equal(initialLanguage().source,'system');
 }finally{for(const [key,value]of Object.entries(descriptors)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key];}}
});

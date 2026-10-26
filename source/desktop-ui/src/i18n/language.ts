export const languages = ['vi','en','ko','ja','zh-TW','zh-CN'] as const;
export type Language = typeof languages[number];
export type LanguageSource = 'user'|'system'|'account'|'fallback';
export type LanguagePreference = {language:Language;source:LanguageSource;systemLanguages?:string[]};
export const languageNames:Record<Language,string> = {vi:'Tiếng Việt',en:'English',ko:'한국어',ja:'日本語','zh-TW':'繁體中文','zh-CN':'简体中文'};
export function normalizeLanguage(raw:unknown):Language|undefined {
 if(typeof raw!=='string')return;
 const [base,...tags]=raw.trim().replaceAll('_','-').toLowerCase().split('-');
 if(['vi','en','ko','ja'].includes(base))return base as Language;
 if(base!=='zh')return;
 if(tags.includes('hant'))return 'zh-TW';
 if(tags.includes('hans'))return 'zh-CN';
 return tags.some(tag=>['tw','hk','mo'].includes(tag))?'zh-TW':'zh-CN';
}
export function resolveLanguage(saved:unknown,system:readonly string[]=[],account?:unknown):LanguagePreference {
 const manual=normalizeLanguage(saved);if(manual)return {language:manual,source:'user'};
 if(system.length)return {language:normalizeLanguage(system[0])??'en',source:'system'};
 const known=normalizeLanguage(account);return known?{language:known,source:'account'}:{language:'en',source:'fallback'};
}
export function orderedLanguages(selected:Language){return [selected,...languages.filter(code=>code!==selected)];}
const preferenceKey='kio-tools.language.v1';
export function initialLanguage():LanguagePreference {
 let saved:unknown;
 try{const item=localStorage.getItem(preferenceKey);if(item)saved=JSON.parse(item).language;}catch{}
 const bootstrap=(globalThis as {__kioLocale?:LanguagePreference}).__kioLocale;
 // The native durable preference is authoritative across WebView port changes.
 if(bootstrap?.source==='user'&&normalizeLanguage(bootstrap.language))return bootstrap;
 if(!saved)try{saved=localStorage.getItem('focus-base.language');}catch{}
 if(normalizeLanguage(saved))return resolveLanguage(saved);
 if(bootstrap&&normalizeLanguage(bootstrap.language))return bootstrap;
 const native=typeof location==='undefined'?null:new URLSearchParams(location.search).get('language');
 const system=native?[native]:typeof navigator==='undefined'?[]:navigator.languages?.length?[...navigator.languages]:navigator.language?[navigator.language]:[];
 return resolveLanguage(undefined,system);
}
export function saveLanguage(language:Language){try{localStorage.setItem(preferenceKey,JSON.stringify({schemaVersion:1,language,source:'user'}));}catch{console.warn('Bogo i18n: browserPreferenceUnavailable');}}

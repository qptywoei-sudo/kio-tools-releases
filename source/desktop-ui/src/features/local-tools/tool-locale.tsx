import {createContext,useContext,useMemo,type ReactNode} from 'react';
import type {ToolLanguage} from './types';
import copy from './ui-copy.json';
export const toolLanguageOrder:ToolLanguage[]=['vi','en','ko','ja','zh-TW','zh'];
export const toolLanguageNames:Record<ToolLanguage,string>={vi:'Tiếng Việt',en:'English',ko:'한국어',ja:'日本語','zh-TW':'繁體中文',zh:'简体中文'};
export function orderedToolLanguages(current:ToolLanguage){return[current,...toolLanguageOrder.filter(l=>l!==current)];}
export function normalizeToolLanguage(value:unknown):ToolLanguage|null{if(value==='zh-CN')return'zh';return typeof value==='string'&&toolLanguageOrder.includes(value as ToolLanguage)?value as ToolLanguage:null;}
export type UiTranslate=(text:string,values?:Record<string,string|number>)=>string;
export const identityUi:UiTranslate=(text,values={})=>Object.entries(values).reduce((result,[key,value])=>result.replaceAll('{'+key+'}',String(value)),text);
export function uiText(language:ToolLanguage,text:string,values:Record<string,string|number>={}){let result=language==='ko'?text:(copy as Record<string,Partial<Record<ToolLanguage,string>>>)[text]?.[language]??text;for(const[key,value]of Object.entries(values))result=result.replaceAll('{'+key+'}',String(value));return result;}
const Locale=createContext<ToolLanguage>('ko');
export function ToolsLocaleProvider({language,children}:{language:ToolLanguage;children:ReactNode}){return <Locale.Provider value={language}>{children}</Locale.Provider>;}
export function useToolsLocale(){const language=useContext(Locale);return useMemo(()=>({language,ui:(text:string,values?:Record<string,string|number>)=>uiText(language,text,values)}),[language]);}

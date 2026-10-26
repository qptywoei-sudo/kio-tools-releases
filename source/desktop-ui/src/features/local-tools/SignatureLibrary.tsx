import {RefreshCw} from 'lucide-react';
import type {AgentFile,ToolLanguage,ToolTranslate} from './types';
import type {LocalAgentClient} from '@/services/local-agent';
import {PdfThumbnail} from './PdfPages';
export type SignatureAsset=AgentFile&{signatureId:string;label:string;width:number;height:number;created:string};
const words={ko:{title:'저장한 서명',use:'서명 사용',empty:'편집창에서 그리거나 가져온 서명을 저장하면 다시 사용할 수 있습니다.'},en:{title:'Saved signatures',use:'Use signature',empty:'Save a drawn or imported signature from the editor to reuse it.'},vi:{title:'Chữ ký đã lưu',use:'Dùng chữ ký',empty:'Lưu chữ ký vẽ hoặc nhập trong trình sửa để dùng lại.'},ja:{title:'保存した署名',use:'署名を使用',empty:'編集画面で描画・読み込んだ署名を保存して再利用できます。'},zh:{title:'保存的签名',use:'使用签名',empty:'在编辑器中保存绘制或导入的签名，以便重复使用。'}, "zh-TW":{title:'儲存的簽名',use:'使用簽名',empty:'在編輯器中儲存繪製或匯入的簽名，以便重複使用。'}};
export function SignatureLibrary({client,assets,language,t,busy=false,onRefresh,onUse}:{client:LocalAgentClient;assets:SignatureAsset[];language:ToolLanguage;t:ToolTranslate;busy?:boolean;onRefresh:()=>void;onUse:(asset:SignatureAsset)=>void}){
 const labels=words[language];
 return <section className="lt-panel"><div className="lt-section-heading"><h2>{labels.title}</h2><button className="lt-button lt-icon-button" disabled={busy} title={t('tools.refresh')} aria-label={t('tools.refresh')} onClick={onRefresh}><RefreshCw size={18}/></button></div>{!assets.length&&<p className="lt-note">{labels.empty}</p>}<ul className="lt-files">{assets.map(asset=><li className="lt-file" key={asset.signatureId}><div><strong>{asset.label}</strong><small>{asset.width} × {asset.height}</small><PdfThumbnail client={client} file={asset} t={t}/></div><button className="lt-button" disabled={busy} onClick={()=>onUse(asset)}>{labels.use}</button></li>)}</ul></section>;
}

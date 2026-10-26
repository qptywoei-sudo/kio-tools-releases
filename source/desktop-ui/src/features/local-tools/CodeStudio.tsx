import {useToolsLocale} from './tool-locale';
import type {ReactNode} from 'react';
import {ArrowRight,Check,FolderOpen,ImagePlus,LoaderCircle,QrCode,ScanLine,ShieldCheck,SlidersHorizontal} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {ToolField} from './catalog';
import type {AgentFile,AgentJob,ToolTranslate} from './types';
import {PdfThumbnail} from './PdfPages';
import {CodeResults,ImageResultActions} from './ResultActions';
import {EmptyFileWorkspace} from './FileWorkspace';
import {QrLogoControls,type QrLogoSelection} from './QrLogoControls';
import './code-studio.css';

type CodeStudioProps={
 client:LocalAgentClient;t:ToolTranslate;operation:string;values:Record<string,unknown>;
 fields:ToolField[];renderField:(field:ToolField)=>ReactNode;inputs:AgentFile[];
 logo:QrLogoSelection|null;onLogo:(logo:QrLogoSelection|null)=>void;onBusyChange:(busy:boolean)=>void;
 result:AgentJob|null;busy:boolean;connected:boolean;supported:boolean;nativeClipboard:boolean;
 onChoose:()=>void;onRemove:(id:string)=>void;onRun:()=>void;onEdit:(file:AgentFile)=>void;
 action:(work:()=>Promise<unknown>)=>Promise<unknown>;
};

/** A focused workspace; code generation and file operations stay on the existing agent. */
export function CodeStudio({client,t,operation,values,fields,renderField,inputs,logo,onLogo,onBusyChange,result,busy,connected,supported,nativeClipboard,onChoose,onRemove,onRun,onEdit,action}:CodeStudioProps){
 const {ui}=useToolsLocale();

 const creating=operation==='code_generate',qr=(values.kind??'qr')==='qr',disabled=busy||!connected;
 const basic=fields.filter(field=>field.basic),format=fields.find(field=>field.name==='format');
 const advanced=fields.filter(field=>!field.basic&&field.name!=='format');
 const files=result?.result?.files??result?.result?.artifacts??result?.artifacts??[];
 const data=result?.result?.data,verified=data?.scanVerified===true,failed=result?.status==='failed';
 return <div className={'kio-code-studio'+(!creating?' is-reading':'')}>
  <section className="kio-code-settings" aria-label={creating?ui("코드 만들기 설정"):ui("코드 읽기 설정")}>
   <div className="kio-code-section-title"><span className="kio-code-section-icon">{creating?<QrCode size={19}/>:<ScanLine size={19}/>}</span><div><h2>{creating?ui("나만의 코드를 만들어 보세요"):ui("사진에서 코드를 읽어 보세요")}</h2><p>{creating?ui("내용을 입력하고, 필요한 만큼 꾸며 주세요."):ui("QR과 바코드에 담긴 내용을 확인합니다.")}</p></div></div>
   {creating?<>
    <fieldset className="kio-code-primary" disabled={disabled}><legend className="kio-code-subtitle">{ui("내용")}</legend><div className="kio-code-fields">{basic.map(field=><div className={'kio-code-field kio-code-field-'+field.name} key={field.name}>{renderField(field)}</div>)}</div></fieldset>
    {qr&&<QrLogoControls client={client} value={logo} onChange={onLogo} disabled={disabled} onBusyChange={onBusyChange}/>}
    {advanced.length>0&&<details className="kio-code-advanced"><summary><SlidersHorizontal size={15}/><span>{t('tools.advanced')}</span></summary><fieldset disabled={disabled}><div className="kio-code-fields">{advanced.map(field=>renderField(field))}</div></fieldset></details>}
   </>:<div className="kio-code-source">
    {inputs.length?<><div className="kio-code-source-heading"><strong>{ui("선택한 사진")}<span>{inputs.length}</span></strong><button type="button" className="lt-button" disabled={disabled} onClick={onChoose}><ImagePlus size={15}/>{ui("사진 추가")}</button></div><ul className="kio-code-source-files">{inputs.map(file=><li key={file.id}><div className="kio-code-source-thumb"><PdfThumbnail client={client} file={file} t={t}/></div><span title={file.name}>{file.name}</span><button type="button" className="lt-button" disabled={busy} onClick={()=>onRemove(file.id)}>{t('tools.remove')}</button></li>)}</ul></>:<EmptyFileWorkspace title={ui("QR · 바코드 사진 선택")} detail={ui("여기에 끌어놓거나 사진을 선택하세요")} disabled={disabled} onChoose={onChoose}/>}
   </div>}
   {!supported&&<p className="lt-note">{t('tools.unsupported')}</p>}
   <div className="kio-code-submit"><div className="kio-code-submit-row">{creating&&format&&<fieldset className="kio-code-format" disabled={disabled}>{renderField({...format,label:'format'})}</fieldset>}<button type="button" className="lt-button primary" disabled={disabled||!supported||(!creating&&!inputs.length)} onClick={onRun}>{busy?<LoaderCircle size={17} className="kio-code-spinner"/>:creating?<QrCode size={17}/>:<ScanLine size={17}/>}<span>{busy?(creating?ui("만드는 중…"):ui("읽는 중…")):creating?(qr?ui("QR 코드 만들기"):ui("바코드 만들기")):ui("코드 읽기")}</span>{!busy&&<ArrowRight size={17}/>}</button></div>{creating&&<p>{ui("완성한 파일은 저장 위치에 자동으로 저장됩니다.")}</p>}</div>
  </section>
  <section className="kio-code-preview" aria-label={creating?ui("코드 결과 미리보기"):ui("코드 읽기 결과")} aria-busy={busy}>
   <header className="kio-code-preview-heading"><div><span className="kio-code-eyebrow">{creating?'PREVIEW':'SCAN RESULT'}</span><h2>{creating?ui("완성된 코드"):ui("읽은 내용")}</h2></div>{result&&!failed&&!busy&&<span className="kio-code-complete"><Check size={13}/>{t('tools.complete')}</span>}</header>
   {busy?<div className="kio-code-empty" role="status"><span className="kio-code-empty-icon is-working"><LoaderCircle size={32} className="kio-code-spinner"/></span><strong>{creating?ui("코드를 만들고 있어요"):ui("코드를 읽고 있어요")}</strong><p>{creating&&qr?ui("스캔이 잘 되는지 함께 확인합니다."):ui("잠시만 기다려 주세요.")}</p></div>:result?<>
    {failed&&<p className="lt-error" role="status">{t('tools.failed')}</p>}
    {files.map(file=><article className="kio-code-artifact" key={file.id}><div className={'kio-code-preview-stage'+(!qr?' is-barcode':'')}><PdfThumbnail client={client} file={file} t={t}/></div><div className="kio-code-file-info"><span>{file.mime?.split('/')[1]?.toUpperCase()??'FILE'}</span><p title={file.name}>{file.name}</p></div>{data?.kind==='qr'&&<div className={'kio-code-scan-status '+(verified?'verified':'warning')} role="status"><ShieldCheck size={17}/><div><strong>{verified?ui("자동 스캔 검사 통과"):ui("자동 스캔 검사 실패")}</strong><p>{verified?ui("입력한 QR 내용과 정확히 일치합니다."):ui("색상 대비 또는 크기를 조정해 주세요.")}{verified&&data.logoIncluded?ui(" 로고가 함께 저장되었습니다."):''}</p></div></div>}<div className="kio-code-result-actions"><ImageResultActions client={client} file={file} t={t} action={action} nativeClipboard={nativeClipboard} onEdit={()=>onEdit(file)}/><button type="button" className="lt-button" disabled={disabled} onClick={()=>void action(()=>client.fileAction('reveal',file.id))}><FolderOpen size={16}/>{t(nativeClipboard?'tools.reveal':'tools.download')}</button><button type="button" className="lt-button" disabled={disabled} onClick={()=>void action(()=>client.fileAction('open',file.id))}>{t('tools.open')}</button></div></article>)}
    <CodeResults results={data?.results} t={t} action={action} nativeClipboard={nativeClipboard}/>
   </>:<div className="kio-code-empty"><span className="kio-code-empty-icon">{creating?<QrCode size={42}/>:<ScanLine size={42}/>}</span><strong>{creating?ui("완성된 코드가 여기에 나타나요"):ui("코드에 담긴 내용을 보여 드려요")}</strong><p>{creating?ui("왼쪽에서 내용을 입력한 후 만들기를 눌러 주세요."):ui("사진을 선택하고 코드 읽기를 눌러 주세요.")}</p>{creating&&qr&&<span className="kio-code-empty-note"><ShieldCheck size={14}/>{ui("스캔 자동 검사 · 오류보정 H")}</span>}</div>}
  </section>
 </div>;
}

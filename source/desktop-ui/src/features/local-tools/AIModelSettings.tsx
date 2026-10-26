import {useToolsLocale} from './tool-locale';
import {RefreshCw} from 'lucide-react';
import type {AISettings,AIStatus} from './ai-types';
import {automaticReasoningLabel,defaultReasoningLabel,effectiveReasoningLabel,modelReasoningOptions,modelSelectionPatch,selectedAIModel} from './ai-model-options';

export function AIModelSettings({status,disabled,onChange,onRefresh}:{status:AIStatus|null;disabled:boolean;onChange:(patch:Partial<AISettings>)=>void;onRefresh:()=>void}){
 const {ui}=useToolsLocale();

 const model=status?selectedAIModel(status):undefined,options=modelReasoningOptions(model,ui),choice=status?.settings.reasoning??'recommended';
 const available=Boolean(status?.models.some(item=>item.id===status.recommendation?.model&&item.vision!==false)),locked=disabled||!status?.planApproved;
 const missingModel=status?.settings.model&&status.settings.model!=='auto'&&!model;
 const missingEffort=!['recommended','model-default'].includes(choice)&&!options.some(item=>item.value===choice);
 const blockedEffort=Boolean(model?.reasoningUnavailable?.[choice]);
 const auto=status?automaticReasoningLabel(status,ui):ui("자동 추천 · 계정 연결 후 확인");
 const recommended=status?.models.find(item=>item.id===status.recommendation?.model);
 return <div className="kio-ai-model-settings">
  <div className="kio-ai-setting-grid">
   <label>{ui("AI 모델")}<select aria-label={ui("AI 모델")} value={status?.settings.model??'auto'} disabled={locked} onChange={event=>{if(status)onChange(modelSelectionPatch(status,event.target.value));}}>
    <option value="auto" disabled={Boolean(status?.models.length)&&!available}>{ui("자동 추천 ·")} {recommended?.name??status?.recommendation?.model??ui("계정 연결 후 확인")}{status?.models.length&&!available?ui(" · 계정 미지원"):''}</option>
    {missingModel&&<option value={status?.settings.model} disabled>{status?.settings.model} {ui("· 현재 계정 목록에 없음")}</option>}
    {status?.models.map(item=><option key={item.id} value={item.id} disabled={item.vision===false}>{item.name}{item.vision===false?ui(" · 이미지 미지원"):''}</option>)}
   </select></label>
   <label>{ui("추론 수준")}<select aria-label={ui("AI 추론 수준")} value={choice} disabled={locked||!model} onChange={event=>onChange({reasoning:event.target.value})}>
    <option value="recommended">{auto}</option>
    <option value="model-default">{ui("모델 기본값 ·")} {defaultReasoningLabel(model,ui)}</option>
    {missingEffort&&<option value={choice} disabled>{choice} {ui("· 현재 계정 목록에 없음")}</option>}
    {options.map(item=><option key={item.value} value={item.value} disabled={Boolean(item.unavailable)} title={item.unavailable??item.description}>{item.label}{item.unavailable?ui(" · 현재 연결 미지원"):''}</option>)}
   </select></label>
  </div>
  <div className="kio-ai-model-current" role="status"><span>{ui("적용 모델")}<strong>{model?.name??(status?.models.length?ui("선택 필요"):ui("계정 모델 확인 중"))}</strong></span><span>{ui("추론")}<strong>{missingModel||missingEffort||blockedEffort?ui("선택 필요"):status&&model?effectiveReasoningLabel(status,ui):ui("확인 중")}</strong></span></div>
  {status?.imageRecommendation&&<p className="kio-ai-hint">{ui('이미지 번역')} · GPT-6.1 Sol · {status.imageRecommendation.reasoning}{!!status.models.length&&!status.models.some(item=>item.id===status.imageRecommendation?.model&&item.vision!==false)?ui(' · 계정 미지원'):''}</p>}
  {(missingModel||missingEffort)&&<p className="kio-ai-hint">{ui("저장한 선택이 현재 계정 목록에 없습니다. 사용 가능한 모델과 추론을 선택해 주세요.")}</p>}
  <div className="kio-ai-actions"><small>{ui("계정에서 제공한 모델")}{status?.models.length??0}{ui("개 · 선택 모델의 추론")}{options.length}{ui("개")}</small><button className="lt-button" disabled={locked} onClick={onRefresh}><RefreshCw size={14}/>{ui("목록 새로고침")}</button></div>
  <p className="kio-ai-hint">{ui("모델·추론 목록은 로그인한 계정과 선택한 모델에 따라 달라집니다. 자동 추천은 Bogo의 번역 추천값을 사용하고, 모델 기본값은 ChatGPT가 제공한 기본 설정을 사용합니다.")}</p>
  {!!model?.reasoningUnavailable?.ultra&&<p className="kio-ai-hint">{ui("ultra도 계정 목록에 포함되어 표시됩니다.")}{model.reasoningUnavailable.ultra}</p>}
 </div>;
}

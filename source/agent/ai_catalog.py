"""Bounded, account-specific picker metadata from the official model catalog."""
import re

def effort_id(value):
    return isinstance(value,str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',value) is not None

def model_catalog(rows):
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('visibility')!='list':continue
        ident=row.get('slug')
        if not isinstance(ident,str) or not ident or len(ident)>120 or ident in seen:continue
        seen.add(ident)
        modalities=row.get('input_modalities',row.get('supported_input_modalities',[]))
        vision='image' in modalities if isinstance(modalities,list) and modalities else None
        levels=[];descriptions={}
        values=row.get('supported_reasoning_levels',[])
        for value in values if isinstance(values,list) else []:
            effort=value.get('effort') if isinstance(value,dict) else value
            if not effort_id(effort) or effort in levels:continue
            levels.append(effort)
            if isinstance(value,dict) and isinstance(value.get('description'),str):descriptions[effort]=value['description'][:1200]
        model={'id':ident,'name':str(row.get('display_name') or ident)[:200],'vision':vision,'verified':False,'reasoningLevels':levels,'reasoningDescriptions':descriptions}
        # ultra in this catalog is a client-side task-delegation mode. The
        # direct SIWC Responses route rejects it as reasoning.effort (live
        # contract checked 2026-10-13). Retain it visibly, with the limitation.
        if 'ultra' in levels:model['reasoningUnavailable']={'ultra':'자동 작업 분담은 현재 화면 스캔 연결에서 지원되지 않습니다.'}
        default=row.get('default_reasoning_level')
        if effort_id(default):model['defaultReasoning']=default
        result.append(model)
    return result

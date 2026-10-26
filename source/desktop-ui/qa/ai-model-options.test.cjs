const test=require('node:test'),assert=require('node:assert/strict'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),load=require('./load-source.cjs');
const {AIModelSettings}=load('features/local-tools/AIModelSettings.tsx');
const {modelSelectionPatch,automaticReasoningLabel,effectiveReasoningLabel}=load('features/local-tools/ai-model-options.ts');
const luna={id:'gpt-6-luna',name:'GPT-6 Luna',vision:true,verified:false,defaultReasoning:'medium',reasoningLevels:['low','medium','high','xhigh','max','future-effort']};
const status={connected:true,planApproved:true,models:[luna,{id:'gpt-6-astra',name:'GPT-6 Astra',vision:true,defaultReasoning:'high',reasoningLevels:['high','ultra']},{id:'text-only',name:'Text only',vision:false,reasoningLevels:['minimal']}],settings:{model:'auto',reasoning:'recommended'},recommendation:{model:'gpt-6-luna',reasoning:'low',verifiedReasoning:['none','low']}};
const render=s=>renderToStaticMarkup(React.createElement(AIModelSettings,{status:s,disabled:false,onChange(){},onRefresh(){}}));
test('automatic picker names the actual low effort and keeps all supplied levels',()=>{
 const html=render(status);assert.match(html,/자동 추천 · low · 가벼운 추론/);for(const effort of luna.reasoningLevels)assert.ok(html.includes(`value="${effort}"`));assert.ok(!html.includes('value="none"'),'global benchmark must not inject options absent from this account');assert.ok(html.includes('Text only'));assert.match(html,/value="text-only" disabled=""/);assert.ok(html.includes('모델 기본값 · medium'));
});
test('different models and accounts expose exactly their own options, including ultra and future values',()=>{
 const astra={...status,settings:{model:'gpt-6-astra',reasoning:'ultra'}},html=render(astra);assert.ok(html.includes('value="ultra"'));assert.ok(!html.includes('value="low"'));assert.equal(automaticReasoningLabel(astra),'모델 기본값 · high · 높은 추론');
 const another={...status,models:[{...luna,id:'other-user-model',reasoningLevels:['none','minimal']}],settings:{model:'other-user-model',reasoning:'none'}};const h=render(another);assert.ok(h.includes('value="none"'));assert.ok(h.includes('value="minimal"'));assert.ok(!h.includes('value="ultra"'));assert.ok(!h.includes('GPT-6 Astra'));
});
test('model change resets an unsupported old effort but keeps a supported explicit choice',()=>{
 assert.deepEqual(modelSelectionPatch({...status,settings:{model:'gpt-6-luna',reasoning:'max'}},'gpt-6-astra'),{model:'gpt-6-astra',reasoning:'recommended'});
 assert.deepEqual(modelSelectionPatch({...status,settings:{model:'gpt-6-luna',reasoning:'high'}},'gpt-6-astra'),{model:'gpt-6-astra'});
 assert.equal(effectiveReasoningLabel({...status,settings:{model:'auto',reasoning:'model-default'}}),'모델 기본값: medium · 보통 추론');
});
test('a saved unavailable model or effort is visible as unavailable rather than mislabeled',()=>{
 const html=render({...status,settings:{model:'old-account-model',reasoning:'none'}});assert.ok(html.includes('현재 계정 목록에 없음'));assert.ok(html.includes('선택 필요'));assert.ok(!html.includes('추론 없음</strong>'),'unsupported effort cannot be advertised as active');
});
test('catalog-provided ultra remains visible with the tested direct-route limitation',()=>{
 const models=status.models.map(m=>m.id==='gpt-6-astra'?{...m,reasoningUnavailable:{ultra:'자동 작업 분담은 현재 연결에서 지원되지 않습니다.'}}:m),s={...status,models,settings:{model:'gpt-6-astra',reasoning:'recommended'}};
 const html=render(s);assert.match(html,/value="ultra" disabled=""/);assert.ok(html.includes('현재 연결 미지원'));assert.deepEqual(modelSelectionPatch({...s,settings:{model:'gpt-6-astra',reasoning:'ultra'}},'gpt-6-astra'),{model:'gpt-6-astra',reasoning:'recommended'});
});

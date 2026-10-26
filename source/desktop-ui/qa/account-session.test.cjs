const test=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const load=require('./load-source.cjs');
const {createAccountObserver,publishAccountLogout,acknowledgedLogout,accountChangedEvent}=load('features/local-tools/account-session.ts');
const {KIOAccountGate}=load('features/local-tools/KIOAccountGate.tsx');
const {ControlSettings}=load('features/local-tools/ControlSettings.tsx');
const signedIn={signedIn:true,connecting:false,user:{id:'fixture-account',email:'fixture@example.invalid'}};
const signedOut={signedIn:false,connecting:false,user:null};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};

test('logout immediately replaces the screen and an older signed-in response cannot restore it',async()=>{
 const old=deferred(),seen=[];const observer=createAccountObserver(()=>old.promise,v=>seen.push(v),()=>assert.fail('unexpected error'));
 const pending=observer.refresh();await Promise.resolve();observer.replace(signedOut);
 assert.deepEqual(seen,[signedOut]);old.resolve(signedIn);await pending;assert.deepEqual(seen,[signedOut]);observer.close();
});
test('a failed pre-logout status request cannot add an error to the signed-out screen',async()=>{
 const old=deferred();let errors=0;const observer=createAccountObserver(()=>old.promise,()=>{},()=>errors++);
 const pending=observer.refresh();await Promise.resolve();observer.replace(signedOut);old.reject(Error('offline'));await pending;assert.equal(errors,0);observer.close();
});
test('a forced account refresh supersedes in-flight polling without dropping the new pending request',async()=>{
 const old=deferred(),fresh=deferred(),seen=[];let reads=0;
 const observer=createAccountObserver(()=>++reads===1?old.promise:fresh.promise,v=>seen.push(v),()=>assert.fail('unexpected error'));
 const first=observer.refresh();await Promise.resolve();const second=observer.refresh(true);await Promise.resolve();
 old.resolve(signedIn);await first;assert.equal(observer.refresh(),second);assert.equal(reads,2);
 fresh.resolve(signedOut);await second;assert.deepEqual(seen,[signedOut]);observer.close();
});
test('closing the gate ignores completion, stops polling and does not update unmounted state',async()=>{
 const request=deferred();let seen=0,errors=0,reads=0;
 const observer=createAccountObserver(()=>{reads++;return request.promise;},()=>seen++,()=>errors++);
 const pending=observer.refresh();await Promise.resolve();observer.close();request.resolve(signedIn);await pending;await observer.refresh();assert.deepEqual({seen,errors,reads},{seen:0,errors:0,reads:1});
});
test('normal status polling is deduplicated and a current network failure is reported once',async()=>{
 const request=deferred();let reads=0,errors=0;
 const observer=createAccountObserver(()=>{reads++;return request.promise;},()=>assert.fail('unexpected status'),()=>errors++);
 const first=observer.refresh(),second=observer.refresh();assert.equal(first,second);await Promise.resolve();assert.equal(reads,1);
 request.reject(Error('offline'));await first;assert.equal(errors,1);observer.close();
});
test('only a server-acknowledged logout publishes an immediate signed-out account event',()=>{
 const before=globalThis.window;globalThis.window=new EventTarget();let state=null,count=0;
 globalThis.window.addEventListener(accountChangedEvent,event=>{count++;state=acknowledgedLogout(event);});
 try{assert.throws(()=>publishAccountLogout(signedIn));assert.equal(count,0);publishAccountLogout(signedOut);assert.deepEqual(state,signedOut);assert.equal(count,1);assert.equal(acknowledgedLogout(new Event(accountChangedEvent)),null);}
 finally{globalThis.window=before;}
});
test('the signed-out gate has one accessible language control and no company or theme action',()=>{
 const html=renderToStaticMarkup(React.createElement(KIOAccountGate,{client:{webContext:false},language:'ko',onLanguageChange(){}},'private tool content'));
 assert.equal((html.match(/<select/g)||[]).length,1);assert.match(html,/aria-label="언어 선택"/);assert.match(html,/Bogo Tools/);assert.match(html,/Bogo 계정으로 계속하기/);
 assert.doesNotMatch(html,/회사 로그인|auth-theme-button|private tool content/);assert.equal((html.match(/<option/g)||[]).length,6);
});
test('pre-login language changes render translated controls without revealing tools',()=>{
 const html=renderToStaticMarkup(React.createElement(KIOAccountGate,{client:{webContext:false},language:'vi',onLanguageChange(){}},'private tools'));
 assert.match(html,/Tiếp tục với Bogo/);assert.match(html,/Chọn ngôn ngữ/);assert.doesNotMatch(html,/private tools/);
});
test('settings expose a single horizontal tablist with five keyboard-accessible sections',()=>{
 const html=renderToStaticMarkup(React.createElement(ControlSettings,{client:{},section:'account',onSection(){},general:null,storage:null,ai:null,updates:null}));
 assert.equal((html.match(/role="tablist"/g)||[]).length,1);assert.match(html,/aria-orientation="horizontal"/);assert.equal((html.match(/role="tab" /g)||[]).length,5);assert.match(html,/aria-labelledby="settings-tab-account"/);
});

// Current product chrome must be visible in every supported sign-in locale.
test('Bogo Tools identity renders in all six sign-in languages without the retired brand',()=>{
 for(const language of ['vi','en','ko','ja','zh','zh-TW']){
  const html=renderToStaticMarkup(React.createElement(KIOAccountGate,{client:{webContext:false},language,onLanguageChange(){}},'private tools'));
  assert.match(html,/Bogo Tools/);assert.doesNotMatch(html,/KIO Tools|KIO 계정|KIOアカウント|KIO账号|KIO賬號|private tools/);
  assert.equal((html.match(/<option/g)||[]).length,6);
 }
});

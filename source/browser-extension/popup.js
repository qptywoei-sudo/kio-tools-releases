import {createAgentClient} from './agent-endpoint.js';
import {supportedPage} from './capture-core.js';

export const CAPTURE_PERMISSIONS=Object.freeze({origins:Object.freeze(['<all_urls>'])});
export const POPUP_WORDS={
 ko:{title:'웹 전체 캡처',connect:'브라우저 연결',capture:'현재 페이지 캡처',disconnect:'연결 해제',connected:'연결됨',connecting:'연결 중…',offline:'연결 안 됨',working:'캡처 중…',done:'완료',failed:'캡처를 완료하지 못했습니다',open:'열기',edit:'편집',save:'저장',unsupportedPage:'일반 웹페이지를 열고 다시 캡처하세요',tabChanged:'페이지가 바뀌었습니다. 다시 캡처하세요',browserPermissionRequired:'브라우저 연결을 눌러 캡처 권한을 허용하세요',browserRequired:'브라우저에 연결한 뒤 다시 시도하세요',agentUnavailable:'Bogo Tools를 실행한 뒤 다시 시도하세요',pairingRequired:'브라우저 연결을 눌러 연결을 승인하세요',pairingDenied:'연결이 승인되지 않았습니다',pairingBusy:'다른 연결 승인창을 먼저 확인하세요',busy:'다른 작업이 끝난 뒤 다시 시도하세요',fileTooLarge:'페이지가 너무 큽니다. 작은 영역을 캡처하세요'},
 en:{title:'Full page capture',connect:'Connect browser',capture:'Capture this page',disconnect:'Disconnect',connected:'Connected',connecting:'Connecting…',offline:'Disconnected',working:'Capturing…',done:'Done',failed:'Capture failed',open:'Open',edit:'Edit',save:'Save',unsupportedPage:'Open a regular webpage and try again',tabChanged:'The page changed. Capture it again',browserPermissionRequired:'Click Connect browser to allow capture access',browserRequired:'Connect the browser and try again',agentUnavailable:'Open Bogo Tools and try again',pairingRequired:'Click Connect browser and approve the connection',pairingDenied:'Connection was not approved',pairingBusy:'Check the other connection prompt first',busy:'Wait for the other task to finish',fileTooLarge:'The page is too large. Capture a smaller area'},
 vi:{title:'Chụp toàn trang',connect:'Kết nối trình duyệt',capture:'Chụp trang hiện tại',disconnect:'Ngắt kết nối',connected:'Đã kết nối',connecting:'Đang kết nối…',offline:'Chưa kết nối',working:'Đang chụp…',done:'Xong',failed:'Không thể chụp',open:'Mở',edit:'Sửa',save:'Lưu',unsupportedPage:'Mở trang web thông thường rồi chụp lại',tabChanged:'Trang đã thay đổi. Hãy chụp lại',browserPermissionRequired:'Bấm Kết nối trình duyệt để cho phép chụp',browserRequired:'Kết nối trình duyệt rồi thử lại',agentUnavailable:'Mở Bogo Tools rồi thử lại',pairingRequired:'Bấm Kết nối trình duyệt và cho phép kết nối',pairingDenied:'Kết nối chưa được cho phép',pairingBusy:'Kiểm tra yêu cầu kết nối khác trước',busy:'Đợi tác vụ khác hoàn tất rồi thử lại',fileTooLarge:'Trang quá lớn. Hãy chụp vùng nhỏ hơn'},
 ja:{title:'ページ全体を撮影',connect:'ブラウザを接続',capture:'現在のページを撮影',disconnect:'接続を解除',connected:'接続済み',connecting:'接続中…',offline:'未接続',working:'撮影中…',done:'完了',failed:'撮影できませんでした',open:'開く',edit:'編集',save:'保存',unsupportedPage:'通常のウェブページを開いて撮影してください',tabChanged:'ページが変わりました。もう一度撮影してください',browserPermissionRequired:'ブラウザを接続して撮影を許可してください',browserRequired:'ブラウザを接続して再試行してください',agentUnavailable:'Bogo Toolsを起動して再試行してください',pairingRequired:'ブラウザを接続して接続を承認してください',pairingDenied:'接続が承認されませんでした',pairingBusy:'先に別の接続確認画面を確認してください',busy:'ほかの処理が終わるまでお待ちください',fileTooLarge:'ページが大きすぎます。小さい範囲を撮影してください'},
 zh:{title:'网页长截图',connect:'连接浏览器',capture:'截取当前网页',disconnect:'断开连接',connected:'已连接',connecting:'正在连接…',offline:'未连接',working:'正在截图…',done:'完成',failed:'截图失败',open:'打开',edit:'编辑',save:'保存',unsupportedPage:'请打开普通网页后重新截图',tabChanged:'页面已更改，请重新截图',browserPermissionRequired:'请点击连接浏览器并允许截图访问',browserRequired:'请连接浏览器后重试',agentUnavailable:'请运行 Bogo Tools 后重试',pairingRequired:'请点击连接浏览器并批准连接',pairingDenied:'连接未获批准',pairingBusy:'请先处理其他连接请求',busy:'请等待其他任务完成',fileTooLarge:'页面太大，请截取较小区域'},
 'zh-TW':{title:'網頁長截圖',connect:'連線瀏覽器',capture:'擷取當前網頁',disconnect:'斷開連線',connected:'已連線',connecting:'正在連線…',offline:'未連線',working:'正在截圖…',done:'完成',failed:'截圖失敗',open:'開啟',edit:'編輯',save:'儲存',unsupportedPage:'請開啟普通網頁後重新截圖',tabChanged:'頁面已更改，請重新截圖',browserPermissionRequired:'請點選連線瀏覽器並允許截圖訪問',browserRequired:'請連線瀏覽器後重試',agentUnavailable:'請執行 Bogo Tools 後重試',pairingRequired:'請點選連線瀏覽器並批准連線',pairingDenied:'連線未獲批准',pairingBusy:'請先處理其他連線請求',busy:'請等待其他任務完成',fileTooLarge:'頁面太大，請擷取較小區域'}
};
const errorKeys=new Set(['unsupportedPage','tabChanged','browserPermissionRequired','browserRequired','agentUnavailable','pairingRequired','pairingDenied','pairingBusy','busy','fileTooLarge']);

export async function mountPopup({document,chrome,agent=createAgentClient({storage:chrome.storage.local}),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))}){
 const saved=await chrome.storage.local.get('language');let language=Object.hasOwn(POPUP_WORDS,saved.language)?saved.language:'ko',busy=false,statusKey='offline',actionGeneration=0;
 const selector=document.querySelector('#language'),controls=['connect','capture','disconnect','format'].map(id=>document.querySelector('#'+id));
 const order=['vi','en','ko','ja','zh-TW','zh'],names={vi:'Tiếng Việt',en:'English',ko:'한국어',ja:'日本語','zh-TW':'繁體中文',zh:'简体中文'};const orderLanguages=()=>{selector.replaceChildren(...[language,...order.filter(code=>code!==language)].map(code=>new Option(names[code],code)));selector.value=language;};orderLanguages();const t=key=>POPUP_WORDS[language][key];
 function status(key){statusKey=key;document.querySelector('#status').textContent=t(key);}
 function showError(error){const code=error?.message==='pageUnsupported'?'unsupportedPage':error?.message;status(errorKeys.has(code)?code:'failed');}
 function localize(){document.querySelectorAll('[data-text]').forEach(el=>{el.textContent=t(el.dataset.text);});status(statusKey);}
 function setBusy(value){busy=value;if(value)actionGeneration++;controls.forEach(control=>{control.disabled=value;});}
 localize();
 selector.addEventListener('change',async()=>{language=Object.hasOwn(POPUP_WORDS,selector.value)?selector.value:'ko';await chrome.storage.local.set({language});orderLanguages();localize();});
 async function api(path,body,method='POST'){
  const response=await agent.request(path,{method,headers:body===undefined?{}:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.errorCode||'processingFailed');}
  return response.headers.get('Content-Type')?.startsWith('application/json')?response.json():response.blob();
 }
 document.querySelector('#connect').addEventListener('click',async()=>{
  if(busy)return;setBusy(true);status('connecting');
  try{
   // Check the browser's persistent grant rather than storing our own flag.
   // Only this user-click handler may request a missing or revoked grant.
   const alreadyAllowed=await chrome.permissions.contains(CAPTURE_PERMISSIONS);
   if(!alreadyAllowed&&!await chrome.permissions.request(CAPTURE_PERMISSIONS))throw Error('browserPermissionRequired');
   const result=await chrome.runtime.sendMessage({type:'connect'});
   if(result?.errorCode)throw Error(result.errorCode);
   if(result?.connected!==true)throw Error('browserRequired');
   status('connected');
  }catch(error){showError(error);}finally{setBusy(false);}
 });
 document.querySelector('#disconnect').addEventListener('click',async()=>{
  if(busy)return;setBusy(true);
  try{const result=await chrome.runtime.sendMessage({type:'disconnect'});if(result?.errorCode)throw Error(result.errorCode);status('offline');}
  catch(error){showError(error);}finally{setBusy(false);}
 });
 document.querySelector('#capture').addEventListener('click',async()=>{
  if(busy)return;setBusy(true);status('working');
  // Start selecting the user's tab at the click, before reconnecting the agent.
  // The worker must retain this target while it waits for its event stream.
  try{
   const selectedTab=chrome.tabs.query({active:true,lastFocusedWindow:true});
   const [tab]=await selectedTab;
   if(!Number.isInteger(tab?.id)||tab.id<0||!Number.isInteger(tab.windowId)||tab.windowId<0||!supportedPage(tab.url))throw Error('unsupportedPage');
   const target={id:tab.id,windowId:tab.windowId,url:tab.url};
   const result=await chrome.runtime.sendMessage({type:'capture',format:document.querySelector('#format').value.toLowerCase(),target});
   if(result?.errorCode)throw Error(result.errorCode);if(!result?.job)throw Error('processingFailed');let job=result.job;
   while(['queued','running'].includes(job.status)){await sleep(1000);job=(await api('/jobs/'+job.id,undefined,'GET')).job;}
   if(job?.status!=='complete')throw Error(job?.errorCode||'processingFailed');
   status('done');const holder=document.querySelector('#results');holder.replaceChildren();
   for(const file of job.result.files){
    const row=document.createElement('div');row.className='result';const label=document.createElement('span');label.textContent=file.name;row.append(label);
    for(const [name,action]of [['open',()=>api('/files/open',{id:file.id})],['edit',()=>api('/files/edit',{id:file.id})],['save',async()=>{const blob=await api('/artifacts/'+file.id,undefined,'GET');const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=file.name;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),60000);}]]){
     const button=document.createElement('button');button.textContent=t(name);button.onclick=()=>void action().catch(showError);row.append(button);
    }
    holder.append(row);
   }
  }catch(error){showError(error);}finally{setBusy(false);}
 });
 const initialGeneration=actionGeneration,state=await chrome.runtime.sendMessage({type:'status'}).catch(()=>({connected:false}));
 // Merely opening the popup must never show a new approval dialog.
 if(!busy&&actionGeneration===initialGeneration){
  if(state?.errorCode)showError(Error(state.errorCode));
  else{const allowed=state?.connected===true&&await chrome.permissions.contains(CAPTURE_PERMISSIONS).catch(()=>false);if(!busy&&actionGeneration===initialGeneration)status(state?.connected?(allowed?'connected':'browserPermissionRequired'):'offline');}
 }
}

if(globalThis.document&&globalThis.chrome)await mountPopup({document:globalThis.document,chrome:globalThis.chrome});

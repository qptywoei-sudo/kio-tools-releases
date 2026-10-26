// Pure scroll-plan primitives shared by capture and regression tests.
export function planPositions(width,height,viewportWidth,viewportHeight,maxTiles=200){
 if(![width,height,viewportWidth,viewportHeight].every(v=>Number.isFinite(v)&&v>0))throw Error('invalidRequest');
 if(!Number.isInteger(maxTiles)||maxTiles<1||maxTiles>200)throw Error('invalidRequest');
 // Reject oversized pages before creating axis arrays or their Cartesian product.
 const columns=Math.ceil(width/viewportWidth),rows=Math.ceil(height/viewportHeight);
 if(columns>maxTiles||rows>maxTiles||columns*rows>maxTiles)throw Error('fileTooLarge');
 const axis=(total,view)=>{const out=[0];for(let p=view;p<total;p+=view)out.push(Math.min(p,Math.max(0,total-view)));return [...new Set(out)];};
 const positions=axis(height,viewportHeight).flatMap(y=>axis(width,viewportWidth).map(x=>({x,y})));
 if(positions.length>maxTiles)throw Error('fileTooLarge');return positions;
}
export function supportedPage(url){try{return ['http:','https:'].includes(new URL(url).protocol);}catch{return false;}}
// USER-origin injection also works on pages whose CSP blocks inline styles.
// Keep overflow enabled: hiding overflow would crop wide/long page content.
export const captureCss=':root,body,*{scrollbar-width:none!important;scrollbar-gutter:auto!important;scroll-behavior:auto!important;scroll-snap-type:none!important}*::-webkit-scrollbar{display:none!important;width:0!important;height:0!important}';
export async function pageOperation(operation,args={}){
 // Executed only by chrome.scripting in the currently authorized, user-visible tab.
 const key='__ADMIN_CAPTURE_STATE__';
 const viewport=()=>{
  const root=document.documentElement;
  const viewportWidth=Math.min(innerWidth,root.clientWidth||innerWidth),viewportHeight=Math.min(innerHeight,root.clientHeight||innerHeight);
  return {viewportWidth,viewportHeight,captureWidth:innerWidth,captureHeight:innerHeight,clipLeft:getComputedStyle(root).direction==='rtl'?innerWidth-viewportWidth:0,dpr:devicePixelRatio};
 };
 if(operation==='begin'){
  if(window[key])throw Error('busy');
  const root=document.documentElement,body=document.body;
  const width=Math.max(root.scrollWidth,body?.scrollWidth??0,innerWidth),height=Math.max(root.scrollHeight,body?.scrollHeight??0,innerHeight);
  const elements=[];
  for(const element of document.querySelectorAll('body *')){
   if(elements.length>=5000)break;
   const style=getComputedStyle(element);
   if(style.position==='fixed'||style.position==='sticky')elements.push({element,visibility:element.style.visibility});
  }
  window[key]={x:scrollX,y:scrollY,behavior:root.style.scrollBehavior,elements};root.style.scrollBehavior='auto';
  return {width,height,viewportWidth:innerWidth,viewportHeight:innerHeight,dpr:devicePixelRatio};
 }
 if(operation==='scroll'){
  const state=window[key];if(!state)throw Error('invalidRequest');
  for(const {element,visibility}of state.elements)element.style.visibility=args.first?visibility:'hidden';
  scrollTo(args.x,args.y);await new Promise(resolve=>setTimeout(resolve,180));await new Promise(requestAnimationFrame);
  return {x:scrollX,y:scrollY,...viewport()};
 }
 if(operation==='measure'){
  if(!window[key])throw Error('invalidRequest');
  // Recalculate after scrollbars are hidden and layout has settled.
  await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
  const root=document.documentElement,body=document.body;
  const view=viewport();
  return {width:Math.max(root.scrollWidth,body?.scrollWidth??0,view.viewportWidth),height:Math.max(root.scrollHeight,body?.scrollHeight??0,view.viewportHeight),...view,captureRevision:2};
 }
 if(operation==='position')return {x:scrollX,y:scrollY,...viewport()};
 if(operation==='restore'){
  const state=window[key];if(!state)return;
  for(const {element,visibility}of state.elements)element.style.visibility=visibility;
  scrollTo({left:state.x,top:state.y,behavior:'instant'});document.documentElement.style.scrollBehavior=state.behavior;delete window[key];
 }
}

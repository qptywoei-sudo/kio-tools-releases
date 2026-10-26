import {notifyDesktopCapture} from './desktop-events';
/** Keep the first HTML running image until the login or tool screen is usable. */
export function finishToolsStartup(){
 if(typeof document==='undefined')return()=>{};
 const frame=requestAnimationFrame(()=>{
  document.getElementById('kio-tools-startup')?.remove();
  notifyDesktopCapture('surfaceReady');
 });
 return()=>cancelAnimationFrame(frame);
}

import {useState,type ReactNode} from 'react';
import {Bluetooth,Cable,Check,ChevronRight,ExternalLink,Info,Monitor,RefreshCw,ShieldCheck,Smartphone,Wifi} from 'lucide-react';
import type {ToolLanguage} from './types';
import {phoneGuideSources,phoneSetupText} from './phone-setup-text';
import './phone-setup-guide.css';

export type PhoneGuideDevice='android'|'iphone';
export type PhoneWirelessMode='pair'|'connect';

function Step({number,title,body,children}:{number:number;title:string;body:string;children?:ReactNode}){
 return <li className="kio-phone-step"><span className="kio-phone-step-number" aria-hidden="true">{number}</span><div><h4>{title}</h4><p>{body}</p>{children}</div></li>;
}
function Example({label,children}:{label:string;children:ReactNode}){
 return <div className="kio-phone-example"><small>{label}</small><div aria-hidden="true">{children}</div></div>;
}
function ToggleExample({label}:{label:string}){
 return <div className="kio-phone-setting"><span>{label}</span><span className="kio-phone-toggle"><i/></span><b>ON</b></div>;
}
function Source({href,children}:{href:string;children:ReactNode}){
 return <a href={href} target="_blank" rel="noreferrer">{children}<ExternalLink size={12} aria-hidden="true"/></a>;
}

export function PhoneSetupGuide({language='ko',device,onDeviceChange,onOpenWireless,onRefresh,busy=false,connected=true}:{language?:ToolLanguage;device:PhoneGuideDevice;onDeviceChange:(device:PhoneGuideDevice)=>void;onOpenWireless:(mode:PhoneWirelessMode)=>void;onRefresh:()=>void;busy?:boolean;connected?:boolean}){
 const [transport,setTransport]=useState<'usb'|'wifi'>('usb');
 const text=phoneSetupText(language),android=device==='android',usb=transport==='usb';
 return <section className="kio-phone-guide" aria-label={text.title}>
  <div className="kio-phone-guide-heading"><h3><Smartphone size={17} aria-hidden="true"/>{text.title}</h3><div className="kio-phone-device-tabs" role="group" aria-label={text.device}>
   <button type="button" aria-pressed={android} onClick={()=>onDeviceChange('android')}><Smartphone size={16} aria-hidden="true"/><span>{text.android}<small>{text.supported}</small></span>{android&&<Check size={14} aria-hidden="true"/>}</button>
   <button type="button" aria-pressed={!android} onClick={()=>onDeviceChange('iphone')}><Smartphone size={16} aria-hidden="true"/><span>{text.iphone}<small>{text.external}</small></span>{!android&&<Check size={14} aria-hidden="true"/>}</button>
  </div></div>
  <div className="kio-phone-transport" role="group" aria-label={text.transport}><button type="button" aria-pressed={usb} onClick={()=>setTransport('usb')}><Cable size={16} aria-hidden="true"/>{text.usb}</button><button type="button" aria-pressed={!usb} onClick={()=>setTransport('wifi')}><Wifi size={16} aria-hidden="true"/>{text.wifi}</button></div>
  {!android&&<p className="kio-phone-capability" role="note"><Info size={18} aria-hidden="true"/>{text.iphoneLimit}</p>}
  <p className="kio-phone-intro">{android?(usb?text.androidUsbIntro:text.androidWifiIntro):(usb?text.iphoneUsbIntro:text.iphoneWifiIntro)}</p>
  {android&&!usb&&<p className="kio-phone-port-note"><Info size={16} aria-hidden="true"/>{text.portWarning}</p>}
  <ol className={'kio-phone-steps'+(!android&&!usb?' kio-phone-alternatives':'')} key={`${device}-${transport}`}>
   {android&&usb&&<>
    <Step number={1} title={text.developerTitle} body={text.developerBody}><Example label={text.example}><div className="kio-phone-build"><span>{text.developerMenu}</span><strong>× 7</strong><small>{text.developerTap}</small></div></Example></Step>
    <Step number={2} title={text.debuggingTitle} body={text.debuggingBody}><Example label={text.example}><small>{text.developerOptions}</small><ToggleExample label={text.usbDebugging}/></Example></Step>
    <Step number={3} title={text.cableTitle} body={text.cableBody}><Example label={text.example}><div className="kio-phone-approval"><ShieldCheck size={22}/><span>{text.authorize}</span><b>{text.allow}</b></div></Example></Step>
    <Step number={4} title={text.startTitle} body={text.startBody}><div className="kio-phone-ready"><Cable size={17} aria-hidden="true"/><span>{text.ready}</span></div><button type="button" className="lt-button kio-phone-guide-action" disabled={!connected||busy} onClick={onRefresh}><RefreshCw size={15} aria-hidden="true"/>{text.refresh}</button></Step>
   </>}
   {android&&!usb&&<>
    <Step number={1} title={text.wifiReadyTitle} body={text.wifiReadyBody}><Example label={text.example}><div className="kio-phone-network"><Smartphone size={22}/><span className="kio-phone-network-line"/><Wifi size={24}/><span className="kio-phone-network-line"/><Monitor size={24}/></div><small>{text.sameWifi}</small></Example></Step>
    <Step number={2} title={text.wifiToggleTitle} body={text.wifiToggleBody}><Example label={text.example}><small>{text.developerOptions}</small><ToggleExample label={text.wirelessDebugging}/></Example></Step>
    <Step number={3} title={text.pairTitle} body={text.pairBody}><Example label={text.example}><small>{text.pairDialog}</small><div className="kio-phone-port-example"><span>{text.pairAddress}</span><code>192.168.0.8:<b>37123</b></code><span>{text.pairCode}</span><code className="kio-phone-code">123 456</code></div></Example><button type="button" className="lt-button kio-phone-guide-action" disabled={!connected||busy} onClick={()=>onOpenWireless('pair')}>{text.openPair}<ChevronRight size={15} aria-hidden="true"/></button></Step>
    <Step number={4} title={text.connectTitle} body={text.connectBody}><Example label={text.example}><small>{text.wirelessDebugging}</small><div className="kio-phone-port-example"><span>{text.connectAddress}</span><code>192.168.0.8:<b>39541</b></code></div></Example><button type="button" className="lt-button kio-phone-guide-action" disabled={!connected||busy} onClick={()=>onOpenWireless('connect')}>{text.openConnect}<ChevronRight size={15} aria-hidden="true"/></button></Step>
   </>}
   {!android&&usb&&<>
    <Step number={1} title={text.iphoneCableTitle} body={text.iphoneCableBody}><Example label={text.example}><div className="kio-phone-approval"><Cable size={22}/><span>{text.trust}</span><ShieldCheck size={19}/></div></Example></Step>
    <Step number={2} title={text.iphoneImportTitle} body={text.iphoneImportBody}><div className="kio-phone-ready"><Monitor size={20} aria-hidden="true"/><span>{text.photos}</span></div><Source href={phoneGuideSources.photos}>{text.applePhotos}</Source></Step>
    <Step number={3} title={text.iphoneEditTitle} body={text.iphoneEditBody}><div className="kio-phone-ready"><Smartphone size={18} aria-hidden="true"/><span>{text.photoFlow}</span></div></Step>
   </>}
   {!android&&!usb&&<>
    <Step number={1} title={text.phoneLinkTitle} body={text.phoneLinkBody}><div className="kio-phone-ready"><Bluetooth size={20} aria-hidden="true"/><span>{text.bluetooth}</span></div><p className="kio-phone-requirements">{text.phoneLinkRequirements}</p><Source href={phoneGuideSources.phoneLink}>{text.phoneLink}</Source></Step>
    <Step number={2} title={text.mirroringTitle} body={text.mirroringBody}><div className="kio-phone-ready"><Wifi size={18} aria-hidden="true"/><Bluetooth size={18} aria-hidden="true"/><Monitor size={20} aria-hidden="true"/></div><p className="kio-phone-requirements">{text.mirroringRequirements}</p><Source href={phoneGuideSources.mirroring}>{text.appleMirroring}</Source></Step>
   </>}
  </ol>
  <details className="kio-phone-troubleshooting"><summary>{text.troubleshooting}</summary><dl>{android?<><dt>{text.usbProblem}</dt><dd>{text.usbSolution}</dd><dt>{text.authProblem}</dt><dd>{text.authSolution}</dd><dt>{text.wifiProblem}</dt><dd>{text.wifiSolution}</dd><dt>{text.blockedProblem}</dt><dd>{text.blockedSolution}</dd></>:<><dt>{text.iphoneProblem}</dt><dd>{text.iphoneSolution}</dd></>}</dl></details>
  <footer className="kio-phone-sources"><small>{text.sources}</small>{android?<><Source href={phoneGuideSources.samsung}>{text.samsungGuide}</Source><Source href={phoneGuideSources.android}>{text.androidGuide}</Source><Source href={phoneGuideSources.driver}>{text.driver}</Source><Source href={phoneGuideSources.blocker}>{text.blocker}</Source></>:<><Source href={phoneGuideSources.photos}>{text.applePhotos}</Source><Source href={phoneGuideSources.phoneLink}>{text.phoneLink}</Source><Source href={phoneGuideSources.mirroring}>{text.appleMirroring}</Source></>}<small className="kio-phone-menu-note">{text.menuNote}</small></footer>
 </section>;
}

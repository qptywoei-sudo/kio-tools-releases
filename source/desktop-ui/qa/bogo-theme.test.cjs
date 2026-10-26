const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const postcss=require('postcss');
const root=path.resolve(__dirname,'../src');
const read=file=>postcss.parse(fs.readFileSync(path.join(root,file),'utf8'));
const tools=file=>read('features/local-tools/'+file);
function values(css,selector,property){const result=[];css.walkRules(rule=>{if(rule.selector.split(',').includes(selector))rule.walkDecls(property,decl=>result.push(decl.value));});return result;}
function has(css,selector,property,value){assert.ok(values(css,selector,property).includes(value),`${selector} ${property}: ${value}`);}
function staleControlYellow(css){
 const found=[];
 css.walkDecls(decl=>{
  const selector=decl.parent.selector||'';
  if(!/(?:\.kio-|\.gc-|\.ps-|\.photo-studio|\.ve-|\.vgs-|\.source-|\.file-source)/.test(selector))return;
  // These small state indicators encode recording/connection health, not brand selection.
  if(selector==='.gc-record-status.paused')return;
  for(const hex of decl.value.match(/#[\da-f]{6}(?:[\da-f]{2})?\b/ig)||[]){
   const[r,g,b]=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
   const max=Math.max(r,g,b),min=Math.min(r,g,b),delta=max-min;
   const hue=60*(delta===0?0:max===r?((g-b)/delta+6)%6:max===g?(b-r)/delta+2:(r-g)/delta+4);
   const saturation=max===0?0:delta/max;
   if(hue>=40&&hue<=65&&saturation>.2)found.push(`${selector} ${decl.prop} ${hex}`);
  }
 });
 return found;
}
function allCss(directory){return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?allCss(path.join(directory,entry.name)):entry.name.endsWith('.css')?[path.join(directory,entry.name)]:[]);}

test('login paper, surface, border and readable ink inherit warm Bogo tokens in either appearance',()=>{
 const css=tools('kio-account.css');
 const bindings={'--login-paper':'var(--color-bg)','--login-surface':'var(--color-surface)','--login-border':'var(--color-border)','--login-ink':'var(--color-text)','--login-muted':'var(--color-text-muted)'};
 for(const selector of ['.kio-login-gate',':root[data-theme=dark] .kio-login-gate'])for(const[prop,value]of Object.entries(bindings))has(css,selector,prop,value);
 has(css,'.kio-login-continue','border','1px solid var(--color-border)');
 has(css,'.kio-login-continue:hover:not(:disabled)','background','var(--color-primary-soft)');
 has(css,'.kio-login-continue:focus-visible','outline','2px solid var(--color-primary)');
 has(css,'.kio-login-language:hover','background','var(--color-primary-soft)');
});

test('Tools CSS has no stale yellow control border, focus, selected or paper declarations',()=>{
 for(const file of allCss(root))assert.deepEqual(staleControlYellow(postcss.parse(fs.readFileSync(file,'utf8'))),[],path.relative(root,file));
});

test('the yellow control regression gate rejects a yellow hover or selected-state override',()=>{
 for(const css of ['.kio-login-continue:hover:not(:disabled){background:#f6df00}',
                   '.source-history-list>button.selected{border-color:#c3a000}',
                   '.ps-range input[type=range]{accent-color:#d4b800}'])assert.ok(staleControlYellow(postcss.parse(css)).length>0);
 assert.deepEqual(staleControlYellow(postcss.parse('.gc-record-status.paused{background:#d49a2920}')),[]);
});

test('small native form controls use official orange while text emphasis remains readable',()=>{
 has(tools('photo-studio.css'),'.ps-range input[type=range]','accent-color','var(--bogo-brand-orange)');
 has(tools('document-studio.css'),'.kio-signature-check input','accent-color','var(--bogo-brand-orange)');
 has(tools('kio-theme.css'),'input[type=checkbox]','accent-color','var(--bogo-brand-orange)');
 has(tools('general-settings.css'),'.kio-setting-line input[role=switch]:checked','background','var(--bogo-brand-orange)');
 has(tools('video-gif-studio.css'),'.vgs-handle i','background','var(--color-on-primary)');
});

test('fixed pale selections keep dark on-primary ink in dark appearance too',()=>{
 for(const[file,selector]of [['control-settings.css','.kio-settings-tabs button[aria-selected=true]'],
                            ['phone-setup-guide.css','.kio-phone-device-tabs button[aria-pressed=true]'],
                            ['photo-studio.css','.ps-primary'],
                            ['storage-settings.css','.kio-storage-modes>button[aria-pressed=true]'],
                            ['video-editor.css','.ve-transport>button']])has(tools(file),selector,'color','var(--color-on-primary)');
 has(tools('extension-setup.css'),'.kio-extension-number','background','var(--kio-yellow,#FFE7D4)');
 has(tools('extension-setup.css'),'.kio-web-guide header>svg','color','var(--color-on-primary)');
 has(tools('photo-studio.css'),'.ps-empty>span','color','var(--color-on-primary)');
 has(tools('local-tools.css'),'.lt-button.primary','background','var(--kio-yellow,var(--color-primary-soft))');
});

test('media, actual document paper, transparency grid and semantic timeline/status colors stay intact',()=>{
 has(tools('document-studio.css'),'.kio-ink-pad','background','#fff');
 has(tools('document-studio.css'),'.kio-stamp-preview','background','#fff');
 has(tools('document-studio.css'),'.kio-signature-sheet','background','#fff');
 has(tools('qr-logo.css'),'.kio-qr-logo-preview','background','#fff');
 has(tools('photo-studio.css'),'.ps-stage','background-color','#f1f2f5');
 has(tools('photo-studio.css'),'.ps-stage','background-image','linear-gradient(45deg,#e3e5eb 25%,transparent 25%),linear-gradient(-45deg,#e3e5eb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#e3e5eb 75%),linear-gradient(-45deg,transparent 75%,#e3e5eb 75%)');
 has(tools('video-editor.css'),'.ve-preview-frame','background','#000');
 has(tools('video-editor.css'),'.ve-audio','border-color','#38a990');
 has(tools('video-editor.css'),'.ve-text','border-color','#aa75dd');
 has(tools('video-editor.css'),'.ve-overlay','border-color','#6699da');
 has(tools('video-gif-studio.css'),'.vgs-watermark','color','#fff');
 has(tools('local-tools.css'),'.lt-status-dot.checking','background','#dca22a');
 has(tools('desktop-workspace.css'),'.gc-record-status.paused','background','#d49a2920');
});

if(process.env.BOGO_TOOLS_COMPILED_CSS)test('the actual compiled CSS retains Bogo login bindings and excludes stale control yellow',()=>{
 const css=postcss.parse(fs.readFileSync(process.env.BOGO_TOOLS_COMPILED_CSS,'utf8'));
 assert.deepEqual(staleControlYellow(css),[]);
 has(css,'.kio-login-gate','--login-paper','var(--color-bg)');
 has(css,'.kio-login-gate','--login-border','var(--color-border)');
 has(css,'.kio-login-continue:hover:not(:disabled)','background','var(--color-primary-soft)');
});

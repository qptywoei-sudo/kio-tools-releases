const test=require('node:test');
const assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {captureImageResult}=load('features/local-tools/capture-export.ts');
const {notifyDesktopCaptureSize}=load('features/local-tools/desktop-events.ts');
const file={id:'fixture-image',mime:'image/png',name:'capture.png'};
test('capture save and copy require a completed job with an image before closing',()=>{
 for(const status of ['complete','completed'])assert.equal(captureImageResult({status,result:{files:[file]}}),file);
 for(const status of ['pending','running','failed','cancelled'])assert.throws(()=>captureImageResult({status,result:{files:[file]}}),/processingFailed/);
 for(const files of [[],[{...file,id:''}],[{...file,mime:'application/pdf'}]])assert.throws(()=>captureImageResult({status:'complete',result:{files}}),/processingFailed/);
 assert.throws(()=>captureImageResult({status:'complete'}),/processingFailed/);
});
test('copy requires a PNG receipt while save accepts JPEG',()=>{
 const jpeg={...file,mime:'image/jpeg'},job={status:'complete',result:{files:[jpeg]}};
 assert.equal(captureImageResult(job),jpeg);assert.throws(()=>captureImageResult(job,true),/processingFailed/);
 assert.equal(captureImageResult({status:'complete',result:{files:[file]}},true),file);
});
test('capture fit passes bounded dimensions and measured chrome only to the native host',()=>{
 const sent=[],target={chrome:{webview:{postMessage:message=>sent.push(message)}}};
 assert.equal(notifyDesktopCaptureSize(693,506,88.25,target),true);
 assert.deepEqual(sent,[{action:'captureFit',width:693,height:506,chromeHeight:89}]);
 for(const [w,h,c]of [[0,100,80],[693.1,506,80],[64001,1,80],[10000,10000,80],[100,100,601],[100,100,NaN]])assert.equal(notifyDesktopCaptureSize(w,h,c,target),false);
 assert.equal(sent.length,1);assert.equal(notifyDesktopCaptureSize(100,100,88,{}),false);
 assert.equal(notifyDesktopCaptureSize(100,100,88,{chrome:{webview:{postMessage(){throw Error('closed');}}}}),false);
});

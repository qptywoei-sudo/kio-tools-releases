import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
const base=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),ui=path.join(base,'desktop-ui');
const require=createRequire(path.join(ui,'package.json')),ts=require('typescript');
async function sourceModule(name){const source=fs.readFileSync(path.join(ui,'src/features/local-tools',name),'utf8'),compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}});return import('data:text/javascript;base64,'+Buffer.from(compiled.outputText).toString('base64'));}
const {pdfPageOrder,pdfPageBatch,movePdfPage,moveSelectedPdfPages,removeSelectedPdfPages,selectedPdfPages,PdfThumbnailLoader,PDF_PAGE_BATCH_SIZE,PDF_THUMBNAIL_CACHE_SIZE}=await sourceModule('pdf-workspace.ts');
const {pdfWorkspaceCopy}=await sourceModule('pdf-workspace-copy.ts');
const file=number=>({id:'page-'+number,name:'page-'+number+'.png',mime:'image/png'}),render=async pages=>pages.map(file);
const deferred=()=>{let resolve,reject;const promise=new Promise((done,fail)=>{resolve=done;reject=fail;});return {promise,resolve,reject};};

test('large PDF page sets stay bounded to twelve visible cards',()=>{
 const order=pdfPageOrder(10000);assert.equal(order.length,10000);assert.equal(pdfPageBatch(order,0).pages.length,12);assert.deepEqual(pdfPageBatch(order,1).pages,[13,14,15,16,17,18,19,20,21,22,23,24]);
 const last=pdfPageBatch(order,99999,10000);assert.equal(last.index,833);assert.deepEqual(last.pages,[9997,9998,9999,10000]);assert.equal(pdfPageBatch(order,-2).index,0);
 for(const count of [0,-1,10001,1.5,NaN])assert.throws(()=>pdfPageOrder(count));
});
test('single and grouped reordering preserve all pages and selection order',()=>{
 const order=[1,2,3,4,5,6];assert.deepEqual(movePdfPage(order,2,-1),[1,3,2,4,5,6]);
 assert.deepEqual(moveSelectedPdfPages(order,[2,3],-1),[2,3,1,4,5,6]);assert.deepEqual(moveSelectedPdfPages(order,[2,4],1),[1,3,2,5,4,6]);assert.deepEqual(order,[1,2,3,4,5,6]);
 assert.equal(moveSelectedPdfPages(order,[1,3],-1),order);assert.equal(moveSelectedPdfPages(order,[4,6],1),order);assert.equal(moveSelectedPdfPages(order,[7],1),order);assert.equal(movePdfPage(order,0,-1),order);assert.equal(movePdfPage(order,0,2),order);
});
test('extraction follows visible order and exclusion always retains a page',()=>{
 const order=[4,1,3,2];assert.deepEqual(selectedPdfPages(order,[2,4]),[4,2]);assert.deepEqual(removeSelectedPdfPages(order,[1,3]),[4,2]);assert.equal(removeSelectedPdfPages(order,order),order);assert.equal(removeSelectedPdfPages([1],[1])[0],1);assert.deepEqual(order,[4,1,3,2]);
});
test('thumbnail loader rejects oversized and invalid batches before any renderer',async()=>{
 const loader=new PdfThumbnailLoader();let calls=0;const read=async pages=>{calls++;return render(pages);};
 for(const pages of [[],Array.from({length:13},(_,index)=>index+1),[1,1],[0],[10001],[1.5]])await assert.rejects(loader.load(pages,read));assert.equal(calls,0);
});
test('thumbnails beyond first twelve are mapped by original page number',async()=>{
 const loader=new PdfThumbnailLoader();assert.equal((await loader.load([13,24,99],render))[24].id,'page-24');assert.equal(loader.cached([1,13])[13].id,'page-13');assert.equal(loader.cached([1])[1],undefined);
});
test('overlapping requests serialize and reuse cached pages',async()=>{
 const loader=new PdfThumbnailLoader(),gate=deferred();let active=0,max=0;const batches=[];
 const read=async pages=>{active++;max=Math.max(max,active);batches.push(pages);if(batches.length===1)await gate.promise;active--;return render(pages);};
 const first=loader.load([1,2],read),next=loader.load([2,3],read);await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(batches,[[1,2]]);gate.resolve();await Promise.all([first,next]);assert.deepEqual(batches,[[1,2],[3]]);assert.equal(max,1);
});
test('cache eviction is bounded and keeps the most recently displayed batch',async()=>{
 const loader=new PdfThumbnailLoader();for(let start=1;start<=60;start+=PDF_PAGE_BATCH_SIZE)await loader.load(Array.from({length:PDF_PAGE_BATCH_SIZE},(_,index)=>start+index),render);
 assert.equal(loader.size,PDF_THUMBNAIL_CACHE_SIZE);assert.equal(loader.cached([1])[1],undefined);assert.equal(loader.cached([60])[60].id,'page-60');
 const latest=Array.from({length:PDF_PAGE_BATCH_SIZE},(_,index)=>49+index);let calls=0;await loader.load(latest,async pages=>{calls++;return render(pages);});assert.equal(calls,0);
});
test('file replacement discards inflight thumbnails and skips old queued work',async()=>{
 const loader=new PdfThumbnailLoader(),gate=deferred();let calls=0;const old=loader.load([1],async pages=>{calls++;await gate.promise;return render(pages);}),queued=loader.load([2],async pages=>{calls++;return render(pages);});
 await new Promise(resolve=>setImmediate(resolve));loader.reset();const next=loader.load([1],async()=>[{id:'new-file-page-1',name:'new.png',mime:'image/png'}]);gate.resolve();assert.deepEqual(await old,{});assert.deepEqual(await queued,{});assert.equal((await next)[1].id,'new-file-page-1');assert.equal(calls,1);
});
test('failed render does not poison a later retry',async()=>{
 const loader=new PdfThumbnailLoader();await assert.rejects(loader.load([8],async()=>{throw Error('processingFailed');}));assert.equal((await loader.load([8],render))[8].id,'page-8');
});
test('missing render pages are rejected without partial cache insertion',async()=>{
 const loader=new PdfThumbnailLoader();await assert.rejects(loader.load([7,8],async()=>[file(7)]));assert.equal(loader.size,0);assert.equal((await loader.load([7,8],render))[8].id,'page-8');
});
test('non-image artifacts cannot become PDF page previews',async()=>{
 const loader=new PdfThumbnailLoader();await assert.rejects(loader.load([1],async()=>[{id:'unexpected',name:'result.pdf',mime:'application/pdf'}]));assert.equal(loader.size,0);
});
test('all five languages describe adding annotations without claiming PDF text replacement',()=>{
 const keys=Object.keys(pdfWorkspaceCopy('ko')).sort();for(const language of ['ko','en','vi','ja','zh']){const copy=pdfWorkspaceCopy(language);assert.deepEqual(Object.keys(copy).sort(),keys);assert.ok(Object.values(copy).every(value=>typeof value==='string'&&value.length));}assert.match(pdfWorkspaceCopy('en').annotate,/Add text/);
});

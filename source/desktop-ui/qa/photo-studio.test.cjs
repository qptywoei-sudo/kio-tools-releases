const test=require('node:test');
const assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {resizedPhotoSize,collageLayout,collageBox,collageImagePlacement,photoName}=load('features/local-tools/photo-studio.ts');

test('photo resize preserves aspect ratio, supports enlargement and protects canvas allocation',()=>{
 assert.deepEqual(resizedPhotoSize(4000,3000,25),{width:1000,height:750});
 assert.deepEqual(resizedPhotoSize(800,600,150),{width:1200,height:900});
 assert.deepEqual(resizedPhotoSize(1,1,5),{width:1,height:1});
 for(const args of [[0,10,100],[100,100,NaN],[16000,16000,100],[16000,100,200]])assert.throws(()=>resizedPhotoSize(...args));
});
test('all collage layouts remain in bounds and cannot overlap',()=>{
 for(let count=2;count<=9;count++)for(const style of ['grid','hero','strips']){
  const rects=collageLayout(count,style);assert.equal(rects.length,count);
  for(let i=0;i<rects.length;i++){
   const a=rects[i];assert(a.x>=0&&a.y>=0&&a.x+a.width<=1.0001&&a.y+a.height<=1.0001);
   for(const b of rects.slice(i+1))assert(Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)<.0001||Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y)<.0001);
  }
 }
});
test('collage center fit covers a cell and normalized drag changes exported position',()=>{
 const box=collageBox({x:.5,y:0,width:.5,height:1},1600,1200,12);
 assert.deepEqual(box,{x:806,y:6,width:788,height:1188});
 const cell={zoom:1,panX:0,panY:0};const fit=collageImagePlacement(3000,2000,box,cell);
 assert(fit.width>=box.width&&fit.height>=box.height);assert.equal(fit.x+fit.width/2,box.x+box.width/2);
 const moved=collageImagePlacement(3000,2000,box,{...cell,panX:.1,panY:-.2});assert.equal(moved.x,fit.x+box.width*.1);assert.equal(moved.y,fit.y-box.height*.2);
 const zoom=collageImagePlacement(3000,2000,box,{...cell,zoom:2});assert.equal(zoom.width,fit.width*2);
});
test('photo output name preserves Unicode and replaces source extension',()=>assert.equal(photoName('회사.사진.jpeg','edited','webp'),'회사.사진_edited.webp'));

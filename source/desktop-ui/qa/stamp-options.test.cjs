const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-source.cjs');
const {paintStamp,stampFonts,stampBorders,stampDimensions}=load('features/local-tools/signature-geometry.ts');
test('all border, shape and font combinations allow empty company and date',()=>{
 for(const shape of ['circle','oval','square','rect','diamond','hexagon'])for(const [border] of stampBorders)for(const font of stampFonts){
  const text=[],fonts=[],ctx=new Proxy({measureText(){return {width:100}},fillText(value){text.push(value);fonts.push(this.font)}},{get:(target,key)=>target[key]??(()=>{}),set:(target,key,value)=>{target[key]=value;return true}});
  const canvas={getContext(){return ctx}};paintStamp(canvas,{shape,border,font:font.id,name:font.group==='한국어'?'홍길동':'洪吉童',company:'',date:'',color:'#c93131'});
  assert.equal(text.length,1);assert.ok(fonts[0].includes(font.family));assert.equal(canvas.width,stampDimensions(shape).width);
 }
});
test('font options have separate Korean and Hanja families',()=>{assert.equal(stampFonts.filter(f=>f.group==='한국어').length,3);assert.equal(stampFonts.filter(f=>f.group==='한자').length,3);assert.equal(new Set(stampFonts.map(f=>f.family)).size,6)});

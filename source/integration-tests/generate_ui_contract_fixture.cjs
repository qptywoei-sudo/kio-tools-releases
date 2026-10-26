// Recreate the missing UI/engine boundary fixture from actual production TS.
// This does not run a browser, connect an account or invoke a native program.
const fs=require('node:fs');
const path=require('node:path');
const load=require('../desktop-ui/qa/load-source.cjs');
const {normalizeCanvasLayer}=load('features/local-tools/canvas-geometry.ts');
const {toolTasks,taskOptions}=load('features/local-tools/catalog.ts');
const layer=(type,points)=>normalizeCanvasLayer({type,x:0,y:0,width:0,height:0,points,color:'#ff0000',fill:'none',lineWidth:6});
const fixture={producer:'production normalizeCanvasLayer + QR taskOptions; explicit canvas API dimensions/pages supplied by Python fixture',taskOptions:{canvas_export:{},...Object.fromEntries(['code_generate'].map(operation=>{
 const task=toolTasks.find(item=>item.operation===operation);if(!task)throw Error('Missing production UI operation '+operation);return [operation,taskOptions(task,{})];
}))},draw:layer('draw',[[20,20],[60,40],[90,70]]),line:layer('line',[[20,50],[60,50],[99,50]]),arrow:layer('arrow',[[20,50],[100,50]]),dot:layer('draw',[[20,20]])};
fs.writeFileSync(path.join(__dirname,'ui-contract-fixture.json'),JSON.stringify(fixture,null,2)+'\n');

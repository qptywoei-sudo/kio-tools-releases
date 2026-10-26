const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');const load=require('./load-source.cjs');
const {tableTSV,smartText,SmartScanResult,scanTools}=load('features/local-tools/SmartScanPanel.tsx');
test('TSV preserves rows and quotes multiline cells without executing image formulas',()=>{
 const t={columns:['Name','Value'],rows:[['Camera','120.50'],['=SUM(A1:A2)','-3'],['a\tb','say "yes"']],uncertain:[],task:'table'};
 assert.equal(tableTSV(t),'Name\tValue\nCamera\t120.50\n\'=SUM(A1:A2)\t-3\n"a\tb"\t"say ""yes"""');
});
test('formula result escapes untrusted markup and offers formula-only copy',()=>{
 const value={task:'formula',formula:'=IF(A1<3,"<script>","")',originalText:'A1',explanation:'Test',uncertain:[]};
 const html=renderToStaticMarkup(React.createElement(SmartScanResult,{value,onCopy(){},onTranslate(){}}));assert.ok(html.includes('수식만 복사'));assert.ok(!html.includes('<script>'));assert.ok(smartText(value).includes(value.formula));
});
test('all ten tools share one picker and cell text remains ordinary selectable HTML',()=>{
 assert.equal(new Set(scanTools.map(t=>t.id)).size,10);
 const html=renderToStaticMarkup(React.createElement(SmartScanResult,{value:{task:'table',columns:['A'],rows:[['text']],uncertain:[]},onCopy(){},onTranslate(){}}));assert.match(html,/<td[^>]*>text<\/td>/);assert.ok(html.includes('Excel용 표 (TSV) 복사'));
});

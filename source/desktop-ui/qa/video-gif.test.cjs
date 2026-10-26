const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-source.cjs');
const {gifDuration,initialGifRange,changeGifRange,nextGifRange,gifTimeAt,gifTimeLabel,validGifRanges}=load('features/local-tools/video-gif.ts');
test('metadata rejects live, invalid and too long videos and rounds down at the actual end',()=>{
 for(const duration of [0,NaN,Infinity,.01,86401])assert.equal(gifDuration(duration),0);
 assert.equal(gifDuration(12.3456),12.34);assert.deepEqual(initialGifRange(1.238),{start:0,end:1.23});
});
test('dragging either GIF handle never crosses the other, the video end or 120 seconds',()=>{
 assert.deepEqual(changeGifRange({start:10,end:15},'start',19,30),{start:14.98,end:15});
 assert.deepEqual(changeGifRange({start:10,end:15},'end',-5,30),{start:10,end:10.02});
 assert.deepEqual(changeGifRange({start:140,end:200},'start',0,250),{start:80,end:200});
 assert.deepEqual(changeGifRange({start:10,end:15},'end',999,300),{start:10,end:130});
 assert.deepEqual(changeGifRange({start:10,end:15},'end',99,16.019),{start:10,end:16.01});
});
test('adding GIF ranges reaches the video end then reuses a valid last segment',()=>{
 assert.deepEqual(nextGifRange([{start:0,end:5}],7),{start:5,end:7});
 assert.deepEqual(nextGifRange([{start:5,end:7}],7),{start:2,end:7});
 assert.deepEqual(nextGifRange([{start:0,end:.03}],.03),{start:0,end:.03});
});
test('timeline coordinates and labels support precise long videos',()=>{
 assert.equal(gifTimeAt(200,100,200,12),6);assert.equal(gifTimeAt(-50,100,200,12),0);assert.equal(gifTimeAt(700,100,200,12),12);
 assert.equal(gifTimeLabel(3665.27),'1:01:05.27');assert.equal(gifTimeLabel(NaN),'00:00.00');assert.equal(gifTimeLabel(59.999),'01:00.00');
});
test('export validates all segments including subsecond and maximum count',()=>{
 assert(validGifRanges([{start:4.98,end:5}],5));assert(!validGifRanges([],5));assert(!validGifRanges([{start:0,end:6}],5));assert(!validGifRanges([{start:0,end:121}],150));assert(!validGifRanges(Array.from({length:31},()=>({start:0,end:1})),5));
});

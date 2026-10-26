export type SignatureRect={x:number;y:number;width:number;height:number};
export function clampSignature(rect:SignatureRect):SignatureRect{
 const width=Math.max(.025,Math.min(1,rect.width)),height=Math.max(.025,Math.min(1,rect.height));
 return {width,height,x:Math.max(0,Math.min(1-width,rect.x)),y:Math.max(0,Math.min(1-height,rect.y))};
}
export function resizeSignature(rect:SignatureRect,factor:number):SignatureRect{
 const limit=Math.min(1/rect.width,1/rect.height),scale=Math.max(.025/Math.min(rect.width,rect.height),Math.min(limit,factor));
 return clampSignature({width:rect.width*scale,height:rect.height*scale,x:rect.x+rect.width*(1-scale)/2,y:rect.y+rect.height*(1-scale)/2});
}
export const stampLayouts=[['stacked','기본 3줄'],['name-first','이름 강조'],['date-band','날짜 띠'],['vertical','세로 이름'],['seal','인장 배열'],['split','좌우 배치']] as const;
export type StampLayout=typeof stampLayouts[number][0];
export const stampDateFormats=[['ymd-dash','년-월-일'],['ymd-slash','년/월/일'],['ymd-dot','년.월.일'],['dmy-slash','일/월/년'],['dmy-dash','일-월-년'],['dmy-dot','일.월.년'],['mdy-slash','월/일/년'],['mdy-dash','월-일-년'],['korean','년 월 일 (한글)'],['compact','년월일 (숫자)']] as const;
export type StampDateFormat=typeof stampDateFormats[number][0];
export const stampBorders=[['double','이중 테두리'],['single','가는 테두리'],['bold','굵은 테두리'],['dashed','점선 테두리'],['none','테두리 없음']] as const;
export const stampFonts=[
 {id:'ko-gothic',group:'한국어',label:'고딕 · 또렷하게',family:'"Malgun Gothic", "Apple SD Gothic Neo", sans-serif'},
 {id:'ko-batang',group:'한국어',label:'바탕 · 문서용',family:'"Batang", "AppleMyungjo", serif'},
 {id:'ko-gungseo',group:'한국어',label:'궁서 · 전통 도장',family:'"Gungsuh", "GungSeo", "Batang", serif'},
 {id:'hanja-ming',group:'한자',label:'명조 · 정자',family:'"MingLiU", "Songti SC", "Batang", serif'},
 {id:'hanja-kai',group:'한자',label:'해서 · 붓글씨',family:'"KaiTi", "Kaiti SC", "Gungsuh", serif'},
 {id:'hanja-hei',group:'한자',label:'흑체 · 또렷하게',family:'"Microsoft JhengHei", "PingFang TC", "Malgun Gothic", sans-serif'},
] as const;
export type StampOptions={shape:'circle'|'oval'|'rect'|'square'|'diamond'|'hexagon';border?:typeof stampBorders[number][0];font?:typeof stampFonts[number]['id'];name:string;company:string;date:string;dateFormat?:StampDateFormat;color:string;layout?:StampLayout;nameSize?:number;companySize?:number;dateSize?:number};
export function formatStampDate(date:string,format:StampDateFormat='ymd-dash'){
 const parts=/^(\d{4})[-/.](\d{2})[-/.](\d{2})$/.exec(date);if(!parts)return date.slice(0,20);
 const [,year,month,day]=parts;
 switch(format){
  case 'ymd-slash':return `${year}/${month}/${day}`;case 'ymd-dot':return `${year}.${month}.${day}`;
  case 'dmy-slash':return `${day}/${month}/${year}`;case 'dmy-dash':return `${day}-${month}-${year}`;case 'dmy-dot':return `${day}.${month}.${year}`;
  case 'mdy-slash':return `${month}/${day}/${year}`;case 'mdy-dash':return `${month}-${day}-${year}`;
  case 'korean':return `${year}년 ${Number(month)}월 ${Number(day)}일`;case 'compact':return year+month+day;
  default:return `${year}-${month}-${day}`;
 }
}
export function stampFontSize(value:number|undefined,fallback:number){return typeof value==='number'&&Number.isFinite(value)?Math.max(12,Math.min(180,value)):fallback;}
export function stampDimensions(shape:StampOptions['shape']){return {width:shape==='oval'||shape==='rect'?960:640,height:640};}
export function stampImage(options:StampOptions){const canvas=document.createElement('canvas');paintStamp(canvas,options);return canvas.toDataURL('image/png');}
export function paintStamp(canvas:HTMLCanvasElement,options:StampOptions){
 const dimensions=stampDimensions(options.shape);canvas.width=dimensions.width;canvas.height=dimensions.height;
 const ctx=canvas.getContext('2d');if(!ctx)return;
 const w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);ctx.strokeStyle=options.color;ctx.fillStyle=options.color;ctx.lineWidth=12;
 const outline=(inset:number)=>{ctx.beginPath();if(options.shape==='circle'||options.shape==='oval')ctx.ellipse(w/2,h/2,w/2-inset,h/2-inset,0,0,Math.PI*2);else if(options.shape==='diamond'||options.shape==='hexagon'){const sides=options.shape==='diamond'?4:6;for(let i=0;i<sides;i++){const angle=-Math.PI/2+i*Math.PI*2/sides,x=w/2+Math.cos(angle)*(w/2-inset),y=h/2+Math.sin(angle)*(h/2-inset);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.closePath();}else ctx.roundRect(inset,inset,w-inset*2,h-inset*2,options.shape==='rect'?24:8);ctx.stroke();};
 const border=options.border??'double';if(border!=='none'){ctx.lineWidth=border==='bold'?22:border==='single'?6:12;if(border==='dashed')ctx.setLineDash([20,12]);outline(24);if(border==='dashed')ctx.setLineDash([]);if(border==='double'){ctx.lineWidth=3;outline(43);}}
 const name=Array.from(options.name).slice(0,30).join(''),company=Array.from(options.company).slice(0,40).join(''),date=options.dateFormat?formatStampDate(options.date,options.dateFormat):options.date.slice(0,20);
 const ns=stampFontSize(options.nameSize,100),cs=stampFontSize(options.companySize,50),ds=stampFontSize(options.dateSize,39);
 const family=stampFonts.find(font=>font.id===options.font)?.family??stampFonts[0].family;
 const font=(size:number)=>`700 ${size}px ${family}`;
 const text=(value:string,x:number,y:number,size:number,maxWidth:number,maxHeight:number)=>{if(!value)return;size=Math.min(size,maxHeight);ctx.font=font(size);const measured=ctx.measureText(value).width;if(measured>maxWidth)size*=maxWidth/measured;ctx.font=font(size);ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(value,x,y);};
 const line=(x1:number,y1:number,x2:number,y2:number)=>{ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();};
 const layout=options.layout??'stacked';
 // Reflow optional fields instead of leaving holes for an absent company/date.
 if((!company||!date)&&layout!=='vertical'&&layout!=='seal'){
  const rows=layout==='name-first'?[[name,ns],[company,cs],[date,ds]]:[[company,cs],[name,ns],[date,ds]];
  const present=rows.filter(([value])=>Boolean(value));present.forEach(([value,size],i)=>text(String(value),w/2,h*(.5+(i-(present.length-1)/2)*.23),Number(size),w*(options.shape==='diamond'?.45:.65),h*.22));return;
 }
 switch(layout){
  case 'name-first':
   text(name,w/2,h*.31,ns,w*.65,h*.21);text(company,w/2,h*.53,cs,w*.74,h*.15);if(date)line(w*.28,h*.65,w*.72,h*.65);text(date,w/2,h*.75,ds,w*.64,h*.14);break;
  case 'date-band':
   text(company,w/2,h*.28,cs,w*.65,h*.16);text(name,w/2,h*.48,ns,w*.76,h*.20);
   if(date){ctx.fillRect(w*.19,h*.65,w*.62,h*.16);ctx.save();ctx.globalCompositeOperation='destination-out';text(date,w/2,h*.73,ds,w*.55,h*.12);ctx.restore();}break;
  case 'vertical':{
   text(company,w/2,h*.21,cs,w*.60,h*.14);const chars=Array.from(name),step=h*.46/Math.max(1,chars.length);
   chars.forEach((char,i)=>text(char,w/2,h*.31+step*(i+.5),ns,w*.38,step*.9));text(date,w/2,h*.84,ds,w*.51,h*.1);break;
  }
  case 'seal':{
   text(company,w/2,h*.19,cs,w*.54,h*.12);const chars=Array.from(name),columns=Math.max(1,Math.ceil(Math.sqrt(chars.length))),rows=Math.max(1,Math.ceil(chars.length/columns)),cw=w*.55/columns,ch=h*.48/rows;
   chars.forEach((char,i)=>{const col=columns-1-Math.floor(i/rows),row=i%rows;text(char,w*.225+cw*(col+.5),h*.29+ch*(row+.5),ns,cw*.85,ch*.9);});text(date,w/2,h*.83,ds,w*.53,h*.11);break;
  }
  case 'split':
   text(company,w/2,h*.26,cs,w*.61,h*.17);line(w*.2,h*.39,w*.8,h*.39);text(name,w*.32,h*.57,ns,w*.29,h*.23);line(w*.5,h*.44,w*.5,h*.74);text(date,w*.68,h*.57,ds,w*.28,h*.18);break;
  default:
   text(company,w/2,h*.29,cs,w*.65,h*.17);text(name,w/2,h*.51,ns,w*.75,h*.23);if(date)line(w*.25,h*.66,w*.75,h*.66);text(date,w/2,h*.75,ds,w*.62,h*.14);
 }
}

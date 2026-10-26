export type Category='image'|'pdf'|'signature'|'capture'|'record'|'web'|'codes'|'files'|'organize'|'media'|'phone'|'settings'|'ai';
export type ToolField={name:string;label:string;type:'text'|'number'|'select'|'checkbox'|'color'|'password';value:string|number|boolean;basic?:boolean;min?:number;max?:number;choices?:Array<{value:string;label?:string}>};
export type ToolTask={operation:string;category:Category;kind:'image'|'pdf'|'video'|'any'|'none';fields:ToolField[];canvas?:boolean};
const number=(name:string,label:string,value:number,min=0,max=30000):ToolField=>({name,label,type:'number',value,min,max});
const text=(name:string,label:string,value=''):ToolField=>({name,label,type:'text',value});
const choiceLabels:Record<string,string>={none:'none',horizontal:'horizontal',vertical:'vertical',rect:'rect',ellipse:'ellipse',image:'image',original:'originalRatio',square:'square',rounded:'rounded',circle:'circle',nopass:'noPassword'};
const select=(name:string,label:string,value:string,choices:string[]):ToolField=>({name,label,type:'select',value,choices:choices.map(item=>({value:item,...(choiceLabels[item]?{label:choiceLabels[item]}:{})}))});
const check=(name:string,label:string,value:boolean):ToolField=>({name,label,type:'checkbox',value});
const mode:ToolField={name:'mode',label:'mode',type:'select',value:'area',basic:true,choices:['area','full','window'].map(value=>({value,label:value}))};
const format=select('format','format','png',['png','jpg','webp']);
const pages=text('pages','pages');
// Catalog for the independent native program.
export const toolCategories:Category[]=['image','pdf','signature','capture','record','web','phone','codes','media','ai'];
export const toolTasks:ToolTask[]=[
 {category:'image',operation:'image_process',kind:'image',fields:[{...format,value:'jpg',basic:true},{...number('width','width',1920),basic:true},number('quality','quality',85,1,100),number('height','height',0),number('scale_percent','percent',100,1,400),check('keep_ratio','ratio',true),check('no_upscale','noUpscale',true)]},
 {category:'image',operation:'image_edit',kind:'image',canvas:true,fields:[format,number('rotate','rotation',0,-360,360),select('flip','flip','none',['none','horizontal','vertical']),number('brightness','brightness',1,0,4),number('contrast','contrast',1,0,4),number('saturation','saturation',1,0,4),number('cropX','cropLeftPercent',0,0,100),number('cropY','cropTopPercent',0,0,100),number('cropWidth','cropWidthPercent',100,0,100),number('cropHeight','cropHeightPercent',100,0,100),number('border','border',0,0,1000),{name:'borderColor',label:'color',type:'color',value:'#ffffff'}]},
 {category:'image',operation:'image_collage',kind:'image',fields:[]},
 {category:'image',operation:'image_background',kind:'image',canvas:true,fields:[{...select('background','background','transparent',['transparent','solid','gradient','image']),choices:['transparent','solid','gradient','image'].map(value=>({value,label:value}))},{name:'color',label:'color',type:'color',value:'#ffffff'},{name:'color2',label:'color2',type:'color',value:'#dbeafe'},format]},
 {category:'signature',operation:'signature_apply',kind:'any',canvas:true,fields:[{...text('text','signatureName'),basic:true},number('x','xPosition',20),number('y','yPosition',20),number('width','width',160,1,5000),number('height','height',60,1,5000),number('rotation','rotation',0,-360,360),number('opacity','opacity',1,0,1),pages,check('allPages','allPages',false),{name:'color',label:'color',type:'color',value:'#111827'}]},
 {category:'pdf',operation:'pdf_manage',kind:'pdf',fields:[pages]},
 {category:'pdf',operation:'pdf_merge',kind:'pdf',fields:[]},
 {category:'pdf',operation:'pdf_extract',kind:'pdf',fields:[{...pages,basic:true}]},
 {category:'pdf',operation:'images_pdf',kind:'image',fields:[select('page_size','pageSize','a4',['a4','image']),{name:'orientation',label:'orientation',type:'select',value:'portrait',choices:['portrait','landscape'].map(value=>({value,label:value}))},number('margin_mm','margin',10,0,100)]},
 {category:'pdf',operation:'pdf_render',kind:'pdf',fields:[pages,select('format','format','png',['png','jpg']),number('dpi','dpi',150,36,600)]},
 {category:'pdf',operation:'pdf_annotate',kind:'pdf',canvas:true,fields:[number('page','pages',1,1,10000)]},
 {category:'pdf',operation:'pdf_split',kind:'pdf',fields:[pages,number('groupSize','pages',1,1,10000),check('zip','zip',true)]},
 {category:'capture',operation:'capture',kind:'none',fields:[mode,number('monitor','monitor',0,0,32)]},
 {category:'web',operation:'web_capture',kind:'none',fields:[{...text('url','url'),basic:true},{...select('format','format','png',['png','jpg','pdf']),basic:true},check('split','splitLong',false)]},
 {category:'record',operation:'record_start',kind:'none',fields:[{...mode,value:'full'},number('monitor','monitor',0,0,32),number('fps','fps',30,5,60),number('width','width',0,0,7680),number('scale_percent','percent',100,10,100),select('format','format','mp4',['mp4']),check('microphone','microphone',false),check('systemAudio','systemAudio',false)]},
 {category:'record',operation:'record_pause',kind:'none',fields:[]},
 {category:'record',operation:'record_resume',kind:'none',fields:[]},
 {category:'record',operation:'record_stop',kind:'none',fields:[]},
 {category:'record',operation:'record_gif',kind:'none',fields:[number('width','width',720,64,1920),number('fps','fps',12,1,30)]},
 {category:'media',operation:'video_edit',kind:'none',fields:[]},
 {category:'media',operation:'video_gif',kind:'video',fields:[{...number('start','start',0,0,86400),basic:true},{...number('duration','duration',5,1,120),basic:true},number('width','width',720,64,1920),number('fps','fps',12,1,30),select('aspect','ratio','original',['original','16:9','9:16','1:1']),text('watermark','watermark'),check('zip','zip',false)]},
 {category:'codes',operation:'code_generate',kind:'none',fields:[{...select('kind','kind','qr',['qr','code128','ean13','ean8','upca','code39']),basic:true},{name:'qr_type',label:'qrType',type:'select',value:'text',basic:true,choices:[{value:'text',label:'plainText'},{value:'url',label:'url'},{value:'wifi',label:'wifi'}]},{...text('text','text'),basic:true},{...text('ssid','ssid'),basic:true},{name:'password',label:'password',type:'password',value:'',basic:true},select('security','security','WPA',['WPA','WEP','nopass']),select('format','format','png',['png','jpg','svg']),select('style','style','square',['square','rounded','circle']),number('size','size',512,128,4096),{name:'foreground',label:'color',type:'color',value:'#111827'},{name:'background',label:'background',type:'color',value:'#ffffff'}]},
 {category:'codes',operation:'code_read',kind:'image',fields:[]},
 {category:'phone',operation:'phone_open',kind:'none',fields:[]}
];
export function taskOptions(task:ToolTask,values:Record<string,unknown>){const options:Record<string,unknown>={};for(const field of task.fields){const value=values[field.name]??field.value;if(field.type==='number'){const number=Number(value);if(!Number.isFinite(number)||number<(field.min??0)||number>(field.max??30000))throw Error('invalidRequest');options[field.name]=number;}else if(field.type==='checkbox')options[field.name]=value===true;else options[field.name]=String(value).slice(0,6000);}
 if(task.operation==='video_gif'){const start=Number(options.start),end=start+Number(options.duration);options.ranges=[{start,end}];delete options.start;delete options.duration;}
 if(task.operation==='image_split'){const count=Number(options.count);const grids:Record<number,[number,number]>={2:[2,1],4:[2,2],8:[4,2],16:[4,4]};if(!grids[count])throw Error('invalidRequest');options.count=count;[options.columns,options.rows]=grids[count];}
 if(task.operation==='code_generate'&&options.kind==='qr'){if(options.qr_type==='wifi'){const escape=(v:unknown)=>String(v??'').replace(/[\\;,:"]/g,'\\$&');options.text=`WIFI:T:${options.security};S:${escape(options.ssid)};P:${escape(options.password)};;`;}else if(options.qr_type==='url'){const url=new URL(String(options.text));if(!['http:','https:'].includes(url.protocol))throw Error('invalidRequest');}delete options.qr_type;delete options.ssid;delete options.password;delete options.security;}
 return options;
}

export function batchImageFilters(values:Record<string,unknown>,count:number):Record<string,unknown>{if(!Number.isInteger(count)||count<1||count>100||['cropX','cropY','cropWidth','cropHeight'].some(key=>typeof values[key]==='boolean'))throw Error('invalidRequest');const task=toolTasks.find(task=>task.operation==='image_edit')!;const options=taskOptions(task,values);const x=Number(options.cropX),y=Number(options.cropY),width=Number(options.cropWidth),height=Number(options.cropHeight);if(width<=0||height<=0||x+width>100||y+height>100)throw Error('invalidRequest');return {...options,baseCount:count,layers:[]};}

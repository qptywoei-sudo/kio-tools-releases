export type MediaKind='video'|'image'|'audio';
export type VideoClip={id:string;source:string;kind:'video'|'image';start:number;end:number;volume:number};
export type AudioClip={id:string;source:string;start:number;end:number;at:number;volume:number};
export type ImageOverlay={id:string;source:string;start:number;end:number;x:number;y:number;width:number};
export type TextOverlay={id:string;text:string;start:number;end:number;x:number;y:number;fontSize:number;color:string;background:boolean};
export type VideoProject={clips:VideoClip[];audio:AudioClip[];overlays:ImageOverlay[];texts:TextOverlay[]};
export type Selection={kind:'clip'|'audio'|'overlay'|'text';id:string};
export const emptyVideoProject=():VideoProject=>({clips:[],audio:[],overlays:[],texts:[]});
export const bound=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,Number.isFinite(value)?value:min));
export const clipLength=(item:{start:number;end:number})=>Math.max(0,item.end-item.start);
export function timelineClips(clips:VideoClip[]){let at=0;return clips.map(clip=>{const entry={...clip,at};at+=clipLength(clip);return entry;});}
export function projectDuration(project:VideoProject){return Math.max(0,...timelineClips(project.clips).map(c=>c.at+clipLength(c)),...project.audio.map(c=>c.at+clipLength(c)),...project.overlays.map(c=>c.end),...project.texts.map(c=>c.end));}
export function sourceKind(name:string,mime=''):MediaKind|null{if(mime.startsWith('image/')||/\.(png|jpe?g|webp|bmp)$/i.test(name))return 'image';if(mime.startsWith('audio/')||/\.(mp3|wav|m4a|aac|flac|ogg)$/i.test(name))return 'audio';if(mime.startsWith('video/')||/\.(mp4|mov|m4v|webm|mkv|avi)$/i.test(name))return 'video';return null;}
export function splitVideoItem(project:VideoProject,selection:Selection,time:number,newId:string):VideoProject{
 if(selection.kind==='clip'){
  if(project.clips.length>=60)return project;
  const item=timelineClips(project.clips).find(c=>c.id===selection.id);if(!item)return project;
  const offset=time-item.at;if(offset<.05||offset>clipLength(item)-.05)return project;
  return {...project,clips:project.clips.flatMap(c=>c.id===item.id?[{...c,end:c.start+offset},{...c,id:newId,start:c.start+offset}]:[c])};
 }
 if(selection.kind==='audio'){
  if(project.audio.length>=60)return project;
  const item=project.audio.find(c=>c.id===selection.id);if(!item)return project;
  const offset=time-item.at;if(offset<.05||offset>clipLength(item)-.05)return project;
  return {...project,audio:project.audio.flatMap(c=>c.id===item.id?[{...c,end:c.start+offset},{...c,id:newId,start:c.start+offset,at:time}]:[c])};
 }
 const key=selection.kind==='overlay'?'overlays':'texts',items=project[key];
 if(items.length>=(selection.kind==='overlay'?30:60))return project;
 const item=items.find(c=>c.id===selection.id);if(!item||time<item.start+.05||time>item.end-.05)return project;
 return {...project,[key]:items.flatMap(c=>c.id===item.id?[{...c,end:time},{...c,id:newId,start:time}]:[c])};
}
export function videoExportOptions(project:VideoProject,sourceIds:string[],width:number,height:number,format:'mp4'|'m4a'='mp4'){
 const index=(id:string)=>{const n=sourceIds.indexOf(id);if(n<0)throw Error('사용 중인 파일이 없습니다. 파일을 다시 추가해 주세요.');return n;};
 const clean=<T extends {id:string}>(item:T)=>{const {id,...data}=item;return data;};
 return {width,height,fps:30,format,duration:projectDuration(project),clips:project.clips.map(c=>({...clean(c),source:index(c.source)})),audio:project.audio.map(c=>({...clean(c),source:index(c.source)})),overlays:format==='m4a'?[]:project.overlays.map(c=>({...clean(c),source:index(c.source)})),texts:format==='m4a'?[]:project.texts.map(clean)};
}
export function clockLabel(seconds:number){const value=Math.max(0,seconds);return `${Math.floor(value/60).toString().padStart(2,'0')}:${(value%60).toFixed(1).padStart(4,'0')}`;}


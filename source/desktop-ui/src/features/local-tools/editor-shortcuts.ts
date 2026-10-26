type EditorKey = {key:string;code?:string;ctrlKey:boolean;metaKey:boolean;altKey:boolean;shiftKey:boolean;defaultPrevented:boolean};
export function editorShortcut(event:EditorKey):'copy'|'save'|'undo'|'redo'|null {
 if(event.defaultPrevented||event.altKey||!(event.ctrlKey||event.metaKey))return null;
 const key=(event.code&&/^Key[CSZY]$/.test(event.code)?event.code.slice(3):event.key).toLowerCase();
 if(key==='c'&&!event.shiftKey)return 'copy';
 if(key==='s'&&!event.shiftKey)return 'save';
 if(key==='z')return event.shiftKey?'redo':'undo';
 if(key==='y'&&!event.shiftKey)return 'redo';
 return null;
}

/** A copy/save race must never close a different image or launch two exports. */
export function createEditorExportController(){
 let busy=false;
 return {
  get busy(){return busy;},
  async perform(request:{run:()=>Promise<void>;isCurrent?:()=>boolean;onSuccess?:()=>void}){
   if(busy)return false;
   busy=true;
   try{
    await request.run();
    if(request.isCurrent?.()!==false)request.onSuccess?.();
    return true;
   }finally{busy=false;}
  },
 };
}

export function fitEditorImage(width:number,height:number,availableWidth:number,availableHeight:number){
 if(![width,height,availableWidth,availableHeight].every(value=>Number.isFinite(value)&&value>0))return 1;
 return Math.min(1,availableWidth/width,availableHeight/height);
}

/** Backspace is the unmodified Delete key on Mac keyboards; inputs keep native editing. */
export function isEditorDeleteShortcut(event:EditorKey){
 return !event.defaultPrevented&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.shiftKey&&['Delete','Backspace'].includes(event.key);
}

type CopyContextElement = {
 isContentEditable?: boolean;
 closest?: (selector: string) => unknown;
 parentElement?: CopyContextElement | null;
};
type CopyShortcut = {key:string;ctrlKey:boolean;metaKey:boolean;altKey:boolean;shiftKey:boolean;defaultPrevented:boolean};
export type ImageCopyRequest = {
 copy: () => Promise<void>;
 captureSession: boolean;
 closeAfterCaptureCopy?: boolean;
 onCopySuccess?: () => void;
 isCurrent?: () => boolean;
};

// Native text copy retains its selection, clipboard formats, and undo behavior.
export function textCopyHasPriority(target: EventTarget | null, selection?: Pick<Selection,'isCollapsed'> | null): boolean {
 if(selection&&!selection.isCollapsed)return true;
 const node=target as CopyContextElement|null,element=node?.closest?node:node?.parentElement;
 return !!element&&(element.isContentEditable===true||!!element.closest?.('input,textarea,[contenteditable=""],[contenteditable="true"],[contenteditable="plaintext-only"]'));
}

export function isImageCopyShortcut(event: CopyShortcut): boolean {
 return !event.defaultPrevented&&(event.ctrlKey||event.metaKey)&&!event.altKey&&!event.shiftKey&&event.key.toLowerCase()==='c';
}

// Invoke this before awaiting image processing so browsers retain user activation.
export function writePngToBrowserClipboard(png: Promise<Blob>): Promise<void> {
 if(!navigator.clipboard?.write||typeof ClipboardItem==='undefined')throw Error('unsupported');
 const image=png.then(blob=>{if(blob.type!=='image/png'||!blob.size)throw Error('processingFailed');return blob;});
 // A permission error can arrive before image processing finishes.
 void image.catch(()=>{});
 return Promise.all([image,navigator.clipboard.write([new ClipboardItem({'image/png':image})])]).then(()=>{});
}

export function createImageCopyController() {
 let copying=false;
 return {
  get copying(){return copying;},
  async copy(request: ImageCopyRequest): Promise<boolean> {
   if(copying)return false;
   copying=true;
   try {
    // Both native and browser adapters resolve only after a successful write.
    await request.copy();
    if(request.captureSession&&request.closeAfterCaptureCopy!==false&&request.isCurrent?.()!==false)request.onCopySuccess?.();
    return true;
   } finally {copying=false;}
  },
 };
}

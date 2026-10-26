import type {AgentFile} from './types';
export type DriveStatus={configured:boolean;connected:boolean;connecting:boolean;checking?:boolean;email:string;displayName:string;accountId?:string;folderName:string;rootId:string;scopeLimited?:boolean;error:string};
export type StorageStatus={mode:'local'|'drive'|'both';localFolderName:string;layout:string;pending:number;failed:number;uploading:number;drive:DriveStatus;recent:Array<{assetId:string;name:string;status:string;error?:string;driveUrl?:string}>};
export type DriveFolder={id:string;name:string;parentId?:string};
export type DriveFile={id:string;name:string;mimeType:string;size?:string|number;modifiedTime?:string;webViewLink?:string;kind?:string;parents?:string[]};
export type DriveFoldersResponse={folders:DriveFolder[];nextPageToken?:string};
export type DriveFilesResponse={files:DriveFile[];nextPageToken?:string;scopeLimited?:boolean;parentId?:string};
export type DriveUploadResponse={queued:number;files:Array<{id:string;name:string;assetId:string}>;storage:StorageStatus};
export type DriveDownloadResponse={file:AgentFile;metadata:DriveFile;downloaded:true};
export const driveFolderMime='application/vnd.google-apps.folder';
/** Restored sessions and canceled account switches must never steal window focus. */
export function driveConnectionCompleted(previous:DriveStatus|null,next:DriveStatus){return Boolean(previous?.connecting&&!next.connecting&&next.connected&&!next.error);}
export function mergeDriveItems<T extends {id:string}>(previous:T[],next:T[]){const items=new Map(previous.map(item=>[item.id,item]));for(const item of next)items.set(item.id,item);return [...items.values()];}
export function driveFileSize(value:unknown){const bytes=Number(value);if(!Number.isFinite(bytes)||bytes<0)return '';if(bytes<1024)return bytes+' B';if(bytes<1024**2)return (bytes/1024).toFixed(1)+' KB';if(bytes<1024**3)return (bytes/1024**2).toFixed(1)+' MB';return (bytes/1024**3).toFixed(1)+' GB';}

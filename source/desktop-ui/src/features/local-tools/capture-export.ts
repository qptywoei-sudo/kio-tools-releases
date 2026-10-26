import type {AgentFile,AgentJob} from './types';

/** A render is not a successful save/copy until the agent confirms its output. */
export function captureImageResult(job:AgentJob,pngOnly=false):AgentFile{
 if(job.status!=='complete'&&job.status!=='completed')throw Error('processingFailed');
 const file=job.result?.files?.find(file=>typeof file.id==='string'&&!!file.id&&(pngOnly?file.mime==='image/png':file.mime?.startsWith('image/')));
 if(!file)throw Error('processingFailed');
 return file;
}

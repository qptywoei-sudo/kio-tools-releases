export const kioCloudOrigin='https://kio-library.vercel.app';
export type KIOAccountStatus={signedIn:boolean;connecting:boolean;user:{id:string;email:string;name?:string;provider?:string}|null;error?:string;executionHost?:'desktop';expiresAt?:number};

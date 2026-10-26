const test=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const load=require('./load-source.cjs');
const {driveConnectionCompleted,mergeDriveItems}=load('features/local-tools/drive-library.ts');
const {StorageSettings}=load('features/local-tools/StorageSettings.tsx');
const {LocalAgentClient}=load('services/local-agent.ts');
const connected={configured:true,connected:true,connecting:false,email:'person@example.test',accountId:'person',displayName:'',folderName:'KIO',rootId:'folder',error:''};

test('Google window return requires a completed login; restoring an account or canceling never focuses',()=>{
 assert.equal(driveConnectionCompleted(null,connected),false);
 assert.equal(driveConnectionCompleted(connected,connected),false);
 const pending={...connected,connecting:true};
 assert.equal(driveConnectionCompleted(pending,{...connected,connecting:true}),false);
 assert.equal(driveConnectionCompleted(pending,{...connected,error:'driveLoginCancelled'}),false);
 assert.equal(driveConnectionCompleted(pending,{...connected,connected:false,error:'driveLoginFailed'}),false);
 assert.equal(driveConnectionCompleted(pending,connected),true);
 // The confirmed connect response primes the transition before the first poll.
 assert.equal(driveConnectionCompleted({...pending,connected:false},connected),true);
});
test('Drive pagination deduplicates changing pages without losing already listed files',()=>{
 const first=[{id:'a',name:'old'},{id:'b',name:'keep'}],next=[{id:'a',name:'new'},{id:'c',name:'added'}];
 assert.deepEqual(mergeDriveItems(first,next),[{id:'a',name:'new'},{id:'b',name:'keep'},{id:'c',name:'added'}]);
 assert.equal(first[0].name,'old');
});
test('ordinary storage UI never asks users for API keys, JSON, or Cloud developer configuration',()=>{
 const html=renderToStaticMarkup(React.createElement(StorageSettings,{client:{},connected:true,settings:{saveMode:'local'},onSettings(){}}));
 assert.match(html,/Google Drive 연결/);
 assert.doesNotMatch(html,/JSON|OAuth|API|Google Cloud|배포용 연결 설정/);
 assert.match(html,/두 곳에 저장/);
});
test('Drive UI actions use authenticated bounded endpoints and preserve typed folder/file IDs',async()=>{
 const locationBefore=globalThis.location,sessionBefore=globalThis.__galaxyDesktopSession;
 const origin='http://127.0.0.1:4324',deviceId='cf1b6406-4c6b-4977-a998-c7b33e08130d';
 globalThis.location={origin,pathname:'/tools/local-tools-standalone.html',hostname:'127.0.0.1',port:'4324'};
 globalThis.__galaxyDesktopSession={origin,deviceId,ownerId:'desktop',clientName:'GalaxyControl',token:'a'.repeat(48)};
 const calls=[];
 try{
  const client=new LocalAgentClient(async(url,init={})=>{const path=new URL(url).pathname;if(path==='/health')return new Response(JSON.stringify({connected:true,version:'4.2.3',deviceId,os:'Windows',nativeReady:true,operations:['image_edit']}));calls.push({path,body:JSON.parse(init.body),token:init.headers.get('X-Local-Agent-Token')});return new Response(JSON.stringify({folders:[],files:[],queued:1,downloaded:true}));});
  await client.driveConnect(true);await client.driveFolders({parentId:'folder-A',pageToken:'next token'});await client.driveCreateFolder('사진 2026','folder-A');await client.driveSelectFolder('folder-B');await client.driveFiles({parentId:'folder-A',query:"literal ' query"});await client.driveUpload(['local-file_1'],'person');await client.driveDownload('google-file_1');await client.driveCancel();
  assert.deepEqual(calls.map(x=>x.path),['/drive/connect','/drive/folders/list','/drive/folders/create','/drive/folders/select','/drive/files/list','/drive/files/upload','/drive/files/download','/drive/cancel']);
  assert.deepEqual(calls[0].body,{switchAccount:true});assert.deepEqual(calls[2].body,{name:'사진 2026',parentId:'folder-A'});assert.equal(calls[4].body.query,"literal ' query");assert.deepEqual(calls[5].body,{inputIds:['local-file_1'],expectedAccountId:'person'});assert.equal(calls[6].body.fileId,'google-file_1');assert.ok(calls.every(x=>x.token==='a'.repeat(48)));
  const before=calls.length;await assert.rejects(client.driveDownload('../escape'),/INVALID_ID/);await assert.rejects(client.driveUpload(['bad/path']),/INVALID_ID/);assert.equal(calls.length,before);
 }finally{globalThis.location=locationBefore;globalThis.__galaxyDesktopSession=sessionBefore;}
});

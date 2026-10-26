const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-source.cjs');
const {chatGPTConnectionAction,aiReadinessError}=load('features/local-tools/ai-connection-state.ts');
const connected={connected:true,planApproved:true,error:'',settings:{consent:true}};

test('approved sessions check the existing model connection instead of reopening OAuth',()=>{
 assert.equal(chatGPTConnectionAction(connected),'models');
 for(const error of ['aiLoginFailed','aiNetwork','aiQuota','aiUnsupportedAccount','aiModelUnavailable']){
  assert.equal(chatGPTConnectionAction({...connected,error}),'models',error);
 }
});

test('screen consent and expired authentication have distinct recovery instructions',()=>{
 assert.equal(aiReadinessError(connected),null);
 assert.equal(aiReadinessError({...connected,settings:{consent:false}}),'aiConsentRequired');
 assert.equal(aiReadinessError({...connected,error:'aiReauthenticate'}),'aiReauthenticate');
 assert.equal(aiReadinessError({...connected,planApproved:false}),'aiPermission');
 assert.equal(aiReadinessError(null),'aiNotConnected');
});

test('missing permission and terminal authentication failures explicitly require sign-in',()=>{
 assert.equal(chatGPTConnectionAction(null),'connect');
 assert.equal(chatGPTConnectionAction({...connected,connected:false}),'connect');
 assert.equal(chatGPTConnectionAction({...connected,planApproved:false}),'connect');
 for(const error of ['aiReauthenticate','aiInvalidIdentity','aiPermission','aiNotConnected']){
  assert.equal(chatGPTConnectionAction({...connected,error}),'connect',error);
 }
});

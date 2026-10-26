import type {AIStatus} from './ai-types';

// A granted session should be checked with its saved credentials. OAuth is an
// explicit recovery step, rather than the primary action for a connected user.
export function chatGPTConnectionAction(status:AIStatus|null):'connect'|'models'{
 if(!status?.connected||!status.planApproved)return 'connect';
 return ['aiReauthenticate','aiInvalidIdentity','aiPermission','aiNotConnected'].includes(status.error)?'connect':'models';
}

export function aiReadinessError(status:AIStatus|null):string|null{
 if(!status?.connected)return 'aiNotConnected';
 if(!status.planApproved)return 'aiPermission';
 if(chatGPTConnectionAction(status)==='connect')return status.error;
 return status.settings.consent?null:'aiConsentRequired';
}

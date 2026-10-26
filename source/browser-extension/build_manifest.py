import subprocess,base64,hashlib,json
from pathlib import Path
here=Path(__file__).resolve().parent;key=here/'build-private-key.pem';existing=here/'manifest.json'
# Distributed source intentionally contains no private signing key. The existing
# public key is enough to retain the extension ID and the user's saved approval.
if existing.exists():
    try:
        old=json.loads(existing.read_text());public=old['key']
        if not isinstance(public,str) or not public:raise ValueError()
        der=base64.b64decode(public,validate=True)
        try:
            canonical=subprocess.check_output(['openssl','pkey','-pubin','-inform','DER','-pubout','-outform','DER'],input=der,stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            # Windows source builds may have Python cryptography without OpenSSL CLI.
            from cryptography.hazmat.primitives.serialization import load_der_public_key,Encoding,PublicFormat
            canonical=load_der_public_key(der).public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo)
        if canonical!=der:raise ValueError()
    except (OSError,KeyError,TypeError,ValueError,ImportError,subprocess.CalledProcessError):
        raise SystemExit('Invalid extension public key; existing manifest was not changed.')
else:
    if not key.exists():subprocess.run(['openssl','genrsa','-out',str(key),'2048'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);key.chmod(0o600)
    der=subprocess.check_output(['openssl','rsa','-in',str(key),'-pubout','-outform','DER'],stderr=subprocess.DEVNULL)
id=''.join(chr(97+int(c,16)) for c in hashlib.sha256(der).hexdigest()[:32])
origin_file=here.parent/'agent'/'extension-origin.json'
if origin_file.exists():
    try:
        old_origin=json.loads(origin_file.read_text())
        if not isinstance(old_origin,dict):raise ValueError()
        if old_origin.get('extensionId')!=id or old_origin.get('origin')!='chrome-extension://'+id:raise ValueError()
    except (OSError,TypeError,ValueError):
        raise SystemExit('Extension identity mismatch; existing manifest and origin were not changed.')
manifest={'manifest_version':3,'name':'__MSG_name__','version':'4.6.23','description':'__MSG_description__','key':base64.b64encode(der).decode(),'permissions':['activeTab','scripting','storage','alarms'],'host_permissions':[f'http://127.0.0.1:{port}/*' for port in (4323,4324,4325,4321)],'optional_host_permissions':['<all_urls>'],'background':{'service_worker':'background.js','type':'module'},'action':{'default_popup':'popup.html','default_title':'__MSG_name__'},'commands':{'capture-current-page':{'description':'__MSG_capture__'}},'content_security_policy':{'extension_pages':"script-src 'self'; object-src 'none'"},'default_locale':'en'}
manifest['icons']={str(n):f'icons/icon-{n}.png' for n in (16,32,48,128)}
manifest['action']['default_icon']=dict(manifest['icons'])
origin_file.parent.mkdir(exist_ok=True)
existing.write_text(json.dumps(manifest,indent=2));origin_file.write_text(json.dumps({'origin':'chrome-extension://'+id,'extensionId':id},indent=2));print(id)

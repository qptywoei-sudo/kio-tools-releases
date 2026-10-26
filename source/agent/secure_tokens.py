"""Native macOS Keychain storage. Secret bytes never enter a shell or argv."""
import ctypes,hashlib,sys
from common import AgentError

class MacKeychain:
    def __init__(self,profile,service="com.kio.control.google-drive"):
        if sys.platform!='darwin':raise AgentError('driveSecureStorageUnavailable')
        self.service=service
        self.account=hashlib.sha256(str(profile.resolve()).encode()).hexdigest()
        try:
            self.cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
            self.sec=ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
            p=ctypes.c_void_p;n=ctypes.c_long
            signatures={
                'CFStringCreateWithCString':([p,ctypes.c_char_p,ctypes.c_uint32],p),
                'CFDataCreate':([p,p,n],p),'CFDataGetLength':([p],n),'CFDataGetBytePtr':([p],p),
                'CFDictionaryCreateMutable':([p,n,p,p],p),'CFDictionarySetValue':([p,p,p],None),'CFRelease':([p],None)}
            for name,(args,result) in signatures.items():fn=getattr(self.cf,name);fn.argtypes=args;fn.restype=result
            for name,args in [('SecItemCopyMatching',[p,ctypes.POINTER(p)]),('SecItemAdd',[p,ctypes.POINTER(p)]),('SecItemUpdate',[p,p]),('SecItemDelete',[p])]:
                fn=getattr(self.sec,name);fn.argtypes=args;fn.restype=ctypes.c_int32
        except (OSError,AttributeError):raise AgentError('driveSecureStorageUnavailable')
    def symbol(self,name):return ctypes.c_void_p.in_dll(self.sec,name).value
    def dictionary(self):
        cf=self.cf
        return cf.CFDictionaryCreateMutable(None,0,ctypes.addressof(ctypes.c_byte.in_dll(cf,'kCFTypeDictionaryKeyCallBacks')),ctypes.addressof(ctypes.c_byte.in_dll(cf,'kCFTypeDictionaryValueCallBacks')))
    def string(self,text):return self.cf.CFStringCreateWithCString(None,text.encode('utf-8'),0x08000100)
    def query(self):
        q=self.dictionary()
        self.cf.CFDictionarySetValue(q,self.symbol('kSecClass'),self.symbol('kSecClassGenericPassword'))
        for key,text in [('kSecAttrService',self.service),('kSecAttrAccount',self.account)]:
            value=self.string(text)
            try:self.cf.CFDictionarySetValue(q,self.symbol(key),value)
            finally:self.cf.CFRelease(value)
        # Never bring up a background authentication dialog or sync refresh tokens.
        self.cf.CFDictionarySetValue(q,self.symbol('kSecUseAuthenticationUI'),self.symbol('kSecUseAuthenticationUIFail'))
        return q
    def load(self):
        q=self.query();out=ctypes.c_void_p()
        try:
            self.cf.CFDictionarySetValue(q,self.symbol('kSecReturnData'),ctypes.c_void_p.in_dll(self.cf,'kCFBooleanTrue').value)
            status=self.sec.SecItemCopyMatching(q,ctypes.byref(out))
            if status==-25300:return None
            if status or not out.value:raise AgentError('driveSecureStorageUnavailable')
            size=self.cf.CFDataGetLength(out)
            if size<0 or size>65536:raise AgentError('driveSecureStorageUnavailable')
            return ctypes.string_at(self.cf.CFDataGetBytePtr(out),size)
        finally:
            if out.value:self.cf.CFRelease(out)
            self.cf.CFRelease(q)
    def save(self,data):
        if not isinstance(data,bytes) or len(data)>65536:raise AgentError('driveSecureStorageUnavailable')
        q=self.query();attrs=self.dictionary();buffer=ctypes.create_string_buffer(data);value=self.cf.CFDataCreate(None,buffer,len(data))
        try:
            self.cf.CFDictionarySetValue(attrs,self.symbol('kSecValueData'),value)
            status=self.sec.SecItemUpdate(q,attrs)
            if status==-25300:
                self.cf.CFDictionarySetValue(q,self.symbol('kSecValueData'),value)
                self.cf.CFDictionarySetValue(q,self.symbol('kSecAttrAccessible'),self.symbol('kSecAttrAccessibleWhenUnlockedThisDeviceOnly'))
                self.cf.CFDictionarySetValue(q,self.symbol('kSecAttrSynchronizable'),ctypes.c_void_p.in_dll(self.cf,'kCFBooleanFalse').value)
                status=self.sec.SecItemAdd(q,None)
            if status:raise AgentError('driveSecureStorageUnavailable')
        finally:self.cf.CFRelease(value);self.cf.CFRelease(attrs);self.cf.CFRelease(q)
    def delete(self):
        q=self.query()
        try:
            if self.sec.SecItemDelete(q) not in (0,-25300):raise AgentError('driveSecureStorageUnavailable')
        finally:self.cf.CFRelease(q)

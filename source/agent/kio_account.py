"""KIO account bridge for both installed hosts.

Only the existing KIO cloud issues account credentials. Browser sign-in uses
PKCE and an ephemeral loopback callback; credentials remain in Keychain/DPAPI.
KIO web is an account and download entry point, never a local tool controller.
"""
from __future__ import annotations
import base64, hashlib, hmac, json, math, os, re, secrets, sys, threading, time
import urllib.error, urllib.parse, urllib.request, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from common import AgentError, private_dir, atomic_json
from secure_tokens import MacKeychain
from language import normalize, callback_page

CLOUD_ORIGIN = 'https://kio-library.vercel.app'
PROJECT_REF = 'kmvddaccuefindbprbis'
LOGIN_TIMEOUT = 300


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


class AccountStore:
    """Separate service from Drive and AI accounts; never plaintext fallback."""
    def __init__(self, state):
        self.state = private_dir(Path(state) / 'kio-account')
        self.path = self.state / 'credential.dpapi'
        self.keychain = MacKeychain(self.state, service='com.kio.control.account') if sys.platform == 'darwin' else None

    def load(self):
        if self.keychain is not None: return self.keychain.load()
        if not self.path.exists(): return None
        if os.name != 'nt' or self.path.is_symlink() or self.path.stat().st_size > 65536:
            raise AgentError('accountSecureStorageUnavailable')
        from google_drive import protect
        return protect(self.path.read_bytes(), True)

    def save(self, data):
        if not isinstance(data, bytes) or len(data) > 65536: raise AgentError('accountSecureStorageUnavailable')
        if self.keychain is not None: return self.keychain.save(data)
        if os.name != 'nt': raise AgentError('accountSecureStorageUnavailable')
        from google_drive import protect
        encrypted = protect(data)
        temporary = self.path.with_name('credential-' + secrets.token_hex(12) + '.tmp')
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(encrypted); stream.flush(); os.fsync(stream.fileno())
            if self.path.is_symlink(): raise AgentError('accountSecureStorageUnavailable')
            os.replace(temporary, self.path)
        finally: temporary.unlink(missing_ok=True)

    def delete(self):
        if self.keychain is not None: self.keychain.delete()
        self.path.unlink(missing_ok=True)


def expiry_seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value): raise AgentError('accountInvalidResponse')
    return value / 1000 if value > 100000000000 else value


def public_user(value):
    if not isinstance(value, dict): raise AgentError('accountInvalidResponse')
    try: ident = str(uuid.UUID(value.get('id', '')))
    except (ValueError, TypeError, AttributeError): raise AgentError('accountInvalidResponse') from None
    email = value.get('email', '')
    if not isinstance(email, str) or len(email) > 320: raise AgentError('accountInvalidResponse')
    user = {'id': ident, 'email': email, 'name': str(value.get('name', ''))[:256], 'provider': str(value.get('provider', 'email'))[:40]}
    locale = normalize(value.get('locale') or value.get('language'))
    if locale: user['locale'] = locale
    return user


class KIOAccount:
    def __init__(self, state, *, store=None, transport=None, open_browser=None, clock=None, language_provider=None):
        self.language_provider = language_provider or (lambda: 'en')
        self.state = private_dir(Path(state) / 'kio-account')
        self.lock = threading.RLock()
        self.snapshot = None; self.refresh_gate = threading.Lock(); self.retry_after = 0; self.closing = False; self.revoking = False
        self.store = store or AccountStore(state)
        self.transport = transport
        self.open_browser = open_browser or webbrowser.open
        self.clock = clock or time.time
        self.opener = urllib.request.build_opener(NoRedirect())
        self.snapshot = None
        self.credential = ''; self.user = None; self.expires = 0; self.verified_at = 0
        self.error = ''; self.pending = None; self.generation = 0
        self.logout_marker = self.state / 'signed-out.json'
        try:
            saved = None if self.logout_marker.exists() else self.store.load()
            if saved:
                data = json.loads(saved)
                if data.get('projectRef') != PROJECT_REF or data.get('cloudOrigin') != CLOUD_ORIGIN: raise ValueError()
                self._accept(data, persist=False)
        except Exception:
            self.credential = ''; self.user = None; self.expires = 0
            self.error = 'accountReconnect'

    def _accept(self, data, *, persist=True, expected_user=None):
        if not isinstance(data, dict): raise AgentError('accountInvalidResponse')
        credential = data.get('credential') or self.credential
        if not isinstance(credential, str) or not 32 <= len(credential) <= 48000 or any(ord(c) < 33 for c in credential):
            raise AgentError('accountInvalidResponse')
        user = public_user(data.get('user'))
        if expected_user is not None and user['id'] != expected_user: raise AgentError('accountChanged', 409)
        expires = expiry_seconds(data.get('expires'))
        if expires <= self.clock() or expires > self.clock() + 366 * 86400: raise AgentError('accountInvalidResponse')
        record = {'credential': credential, 'user': user, 'expires': expires, 'projectRef': PROJECT_REF, 'cloudOrigin': CLOUD_ORIGIN}
        # Persistence must succeed before a newly logged-in identity is usable.
        if persist: self.store.save(json.dumps(record, separators=(',', ':')).encode())
        if persist: self.logout_marker.unlink(missing_ok=True)
        self.credential = credential; self.user = user; self.expires = expires
        self.verified_at = self.clock(); self.error = ''
        self.snapshot = (credential, dict(user), expires, self.verified_at)

    def status(self):
        # One immutable identity snapshot keeps local UI and tools responsive
        # while a background Drive request holds the network/rotation lock.
        snapshot = self.snapshot
        signed = bool(not self.revoking and snapshot and snapshot[2] > self.clock())
        return {'signedIn': signed, 'connecting': self.pending is not None, 'user': dict(snapshot[1]) if signed else None,
                'expiresAt': int(snapshot[2] * 1000) if signed else None, 'error': self.error,
                'cloudOrigin': CLOUD_ORIGIN, 'projectRef': PROJECT_REF,
                'providers': ['google','github','azure','chatgpt','email'], 'executionHost': 'desktop'}

    def refresh_in_background(self):
        if self.closing or self.revoking or self.clock() < self.retry_after or not self.refresh_gate.acquire(False): return
        def refresh():
            try:
                if not self.closing and not self.revoking: self.require(online=True)
            except AgentError:
                # A temporary connection failure preserves an unexpired identity
                # and cannot cause one refresh request per capture or poll.
                self.retry_after = self.clock() + 30
            finally: self.refresh_gate.release()
        threading.Thread(target=refresh,daemon=True).start()

    def _request(self, route, body=None, *, authenticated=True, method='POST'):
        if not isinstance(route, str) or not route.startswith('/control/') or '?' in route or '#' in route or '..' in route:
            raise AgentError('accountInvalidEndpoint')
        url = CLOUD_ORIGIN + '/api/cloud?' + urllib.parse.urlencode({'route': route})
        data = json.dumps(body or {}, separators=(',', ':')).encode() if method != 'GET' else None
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if authenticated:
            if not self.credential: raise AgentError('ACCOUNT_REQUIRED', 401)
            headers['Authorization'] = 'Bearer ' + self.credential
        if self.transport is not None:
            result = self.transport(route, body or {}, headers, method)
            return self._response(result, authenticated)
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                payload = response.read(8 * 1024 * 1024 + 1)
                if len(payload) > 8 * 1024 * 1024: raise AgentError('accountInvalidResponse')
        except urllib.error.HTTPError as error:
            if route.startswith('/control/chatgpt/'):
                try:code=json.loads(error.read(65536)).get('error','')
                except Exception:code=''
                if code in ('aiNotConnected','aiReauthenticate','aiConnectionChanged','aiRefreshInProgress','aiPermission','aiNetwork','aiAccountChanged','aiInvalidIdentity','aiConnectionStorageRequired'):raise AgentError(code,error.code) from None
            if error.code in (401, 403): raise AgentError('accountReconnect', 401) from None
            raise AgentError('accountCloudUnavailable', 503) from None
        except (OSError, urllib.error.URLError, TimeoutError): raise AgentError('accountCloudUnavailable', 503) from None
        try: result = json.loads(payload)
        except (ValueError, UnicodeError): raise AgentError('accountInvalidResponse') from None
        return self._response(result, authenticated)

    def _response(self, result, authenticated):
        if not isinstance(result, dict): raise AgentError('accountInvalidResponse')
        if authenticated and result.get('credential'):
            # Cloud refreshes dedicated Supabase credentials during any request.
            # Persist each returned rotation, including Drive and web pairing.
            expiration = result.get('credentialExpires', self.expires)
            if 'credentialExpires' not in result and result.get('web') is not True and result.get('user') and result.get('expires'):
                expiration = result['expires']
            self._accept({'credential': result['credential'], 'user': result.get('user') or self.user, 'expires': expiration}, expected_user=self.user['id'] if self.user else None)
        return result

    def require(self, *, online=False):
        if self.revoking: raise AgentError('ACCOUNT_REQUIRED',401)
        snapshot = self.snapshot
        if not online and snapshot and snapshot[2] > self.clock():
            if self.clock() >= min(snapshot[2]-60,snapshot[3]+300): self.refresh_in_background()
            return dict(snapshot[1])
        with self.lock:
            if not self.credential or not self.user: raise AgentError('ACCOUNT_REQUIRED', 401)
            if online or self.clock() >= min(self.expires - 60, self.verified_at + 300):
                ident = self.user['id']
                try: self._accept(self._request('/control/native/session'), expected_user=ident)
                except AgentError as error:
                    if error.code in ('accountReconnect', 'accountChanged'):
                        self._clear(); self.error = error.code
                        raise
                    # Previously verified, encrypted identity may use local tools
                    # offline until its actual signed credential expires.
                    if online or self.clock() >= self.expires: self.error = error.code; raise
            if self.clock() >= self.expires: raise AgentError('accountReconnect', 401)
            return dict(self.user)

    def cloud(self, route, body=None, *, method='POST', expected_user=None):
        with self.lock:
            if expected_user is not None and (not self.user or self.user['id']!=expected_user):raise AgentError('accountChanged',409)
            user=self.require()
            if expected_user is not None and user['id']!=expected_user:raise AgentError('accountChanged',409)
            # Every native Drive endpoint verifies and refreshes the same session.
            # A second /native/session request adds no authorization guarantee.
            return self._request(route, body, method=method)

    def binary_download(self, file_id, destination, maxbytes=512 * 1024 * 1024, *, expected_user=None):
        """Stream only the fixed KIO server; publish a new destination atomically."""
        if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', file_id): raise AgentError('invalidRequest')
        if type(maxbytes) is not int or not 1 <= maxbytes <= 512 * 1024 * 1024: raise AgentError('invalidRequest')
        target = Path(destination)
        if not target.is_absolute() or not target.parent.is_dir() or target.exists() or target.is_symlink(): raise AgentError('unsafePath')
        for parent in target.parents:
            if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()): raise AgentError('unsafePath')
        temporary = target.with_name('.kio-download-' + secrets.token_hex(16) + '.tmp')
        with self.lock:
            if expected_user is not None and (not self.user or self.user['id']!=expected_user):raise AgentError('accountChanged',409)
            user=self.require(online=True)
            if expected_user is not None and user['id']!=expected_user:raise AgentError('accountChanged',409)
            url = CLOUD_ORIGIN + '/api/cloud?' + urllib.parse.urlencode({'route': '/control/drive/download', 'fileId': file_id})
            request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + self.credential}, method='GET')
            try:
                with self.opener.open(request, timeout=60) as response:
                    if response.status != 200: raise AgentError('accountCloudUnavailable')
                    rotated = response.headers.get('X-KIO-Native-Credential')
                    expires = response.headers.get('X-KIO-Credential-Expires')
                    if rotated:
                        try: expiration = float(expires)
                        except (TypeError, ValueError): raise AgentError('accountInvalidResponse') from None
                        self._accept({'credential': rotated, 'user': self.user, 'expires': expiration}, expected_user=self.user['id'])
                    declared = response.headers.get('Content-Length')
                    if declared is not None:
                        try: declared = int(declared)
                        except ValueError: raise AgentError('accountInvalidResponse') from None
                        if not 0 <= declared <= maxbytes: raise AgentError('fileTooLarge', 413)
                    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    length = 0
                    with os.fdopen(descriptor, 'wb') as stream:
                        while True:
                            part = response.read(min(1024 * 1024, maxbytes - length + 1))
                            if not part: break
                            length += len(part)
                            if length > maxbytes: raise AgentError('fileTooLarge', 413)
                            stream.write(part)
                        if declared is not None and length != declared: raise AgentError('accountCloudUnavailable')
                        stream.flush(); os.fsync(stream.fileno())
                    # Linking refuses an existing destination even if another
                    # operation creates it after the initial existence check.
                    os.link(temporary, target)
                    name = urllib.parse.unquote(response.headers.get('X-KIO-Control-File-Name', target.name))
                    if not name or len(name) > 1000 or any(ord(character)<32 for character in name): name = target.name
                    name = Path(name.replace('\\','/')).name
                    return {'size': length, 'mime': response.headers.get('Content-Type', 'application/octet-stream'), 'name': name}
            except urllib.error.HTTPError as error:
                raise AgentError('accountReconnect' if error.code in (401,403) else 'accountCloudUnavailable',401 if error.code in (401,403) else 503) from None
            except (OSError, urllib.error.URLError, TimeoutError): raise AgentError('accountCloudUnavailable', 503) from None
            finally: temporary.unlink(missing_ok=True)

    def login(self, provider='google', expected_user=None, connect_drive=False):
        if provider not in ('google', 'github', 'azure', 'chatgpt', 'email'): raise AgentError('invalidRequest')
        if type(connect_drive) is not bool or (connect_drive and (provider!='google' or expected_user is None)): raise AgentError('invalidRequest')
        if expected_user is not None:
            try: expected_user = str(uuid.UUID(expected_user))
            except (ValueError, TypeError, AttributeError): raise AgentError('invalidRequest') from None
        with self.lock:
            if self.pending is not None: return self.status()
            self.generation += 1; generation = self.generation
            verifier = secrets.token_urlsafe(64); nonce = secrets.token_urlsafe(32)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            account = self
            class Callback(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def setup(self): super().setup(); self.connection.settimeout(5)
                def do_GET(self):
                    parsed = urllib.parse.urlparse(self.path); query = urllib.parse.parse_qs(parsed.query)
                    valid = parsed.path == '/kio/callback' and self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
                    valid = valid and len(query.get('state', [])) == 1 and hmac.compare_digest(query['state'][0].encode('utf-8'), nonce.encode('ascii'))
                    if not valid:
                        data=callback_page('auth.invalid',language)
                        self.send_response(400);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
                    message = 'auth.success'
                    try:
                        grants = query.get('grant', [])
                        if query.get('error') or len(grants) != 1 or not 16 <= len(grants[0]) <= 48000: raise AgentError('accountLoginCancelled')
                        with account.lock:
                            if generation != account.generation or self.server.completed: raise AgentError('accountLoginCancelled')
                            # Mark consumed before contacting cloud: duplicate
                            # callbacks cannot rotate or switch this identity.
                            self.server.completed = True
                            result = account._request('/control/native/exchange', {'grant': grants[0], 'code_verifier': verifier, 'redirect_uri': redirect}, authenticated=False)
                            account._accept(result,expected_user=expected_user)
                    except Exception as error:
                        with account.lock:
                            if generation == account.generation: account.error = error.code if isinstance(error, AgentError) else 'accountLoginFailed'
                        message = 'auth.failure'
                    finally: self.server.completed = True
                    data = callback_page(message, language)
                    self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(data))); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'"); self.end_headers(); self.wfile.write(data)
            server = HTTPServer(('127.0.0.1', 0), Callback); server.timeout = .5; server.completed = False
            redirect = f'http://127.0.0.1:{server.server_port}/kio/callback'
            self.pending = server; self.error = ''
            language = normalize(self.language_provider()) or 'en'
            query = {'language': language, 'controlLogin': '1', 'redirect_uri': redirect, 'code_challenge': challenge, 'state': nonce, 'provider': provider}
            if connect_drive: query['controlDrive'] = '1'
            url = CLOUD_ORIGIN + '/?' + urllib.parse.urlencode(query)
        def wait():
            deadline = time.monotonic() + LOGIN_TIMEOUT
            try:
                while not server.completed and time.monotonic() < deadline and generation == account.generation: server.handle_request()
                with account.lock:
                    if not server.completed and generation == account.generation: account.error = 'accountLoginTimeout'
            finally:
                server.server_close()
                with account.lock:
                    if account.pending is server: account.pending = None
        threading.Thread(target=wait, daemon=True, name='KIO-Account-Login').start()
        try:
            if not self.open_browser(url): raise OSError()
        except Exception:
            self.cancel(); self.error = 'accountBrowserFailed'; raise AgentError('accountBrowserFailed') from None
        return self.status()

    def cancel(self):
        with self.lock:
            self.generation += 1; self.pending = None
            return self.status()

    def _clear(self):
        self.snapshot = None
        self.credential = ''; self.user = None; self.expires = 0; self.verified_at = 0
        # If locked OS storage cannot delete, a non-secret tombstone still
        # prevents an old stored session from returning after restart.
        atomic_json(self.logout_marker, {'signedOut': True})
        self.store.delete()

    def logout(self):
        self.revoking = True
        try:
            with self.lock:
                self.cancel()
                if self.credential:
                    try: self._request('/control/native/logout')
                    except AgentError: pass
                self._clear(); self.error = ''
                return self.status()
        finally: self.revoking = False

    def close(self): self.closing = True; self.cancel()

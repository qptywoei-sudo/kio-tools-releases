"""Private filesystem tests with an explicitly mocked KIO cloud account.

These tests never use a Google grant, OS keychain, real account, or network.
They exercise the adapter contract independently of the cloud implementation.
"""
import base64, hashlib, json, os, sys, tempfile, threading, time, unittest, uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'agent')]
from common import AgentError, atomic_json, read_json
from kio_cloud_drive import KIOCloudDrive, DEFAULT_ROOT, FOLDER, PATH

CHUNK = 2 * 1024 * 1024
USER = {'id': '19a3b744-b887-4dd8-b019-43306f7610f3', 'email': 'fixture@example.invalid', 'name': 'Fixture', 'provider': 'google'}
OTHER = {**USER, 'id': '1998bf7c-1fe0-419d-80be-eccfb9c93f40', 'email': 'other@example.invalid'}


class MockAccount:
    """Only the fixed KIO API contract is simulated; no external HTTP fallback."""
    def __init__(self):
        self.user = dict(USER); self.lock = threading.RLock(); self.calls = []; self.logins = []
        self.connected = True; self.connecting = False; self.root = 'fixture-control-root'
        self.sessions = {}; self.completed = {}; self.chunk_calls = []; self.on_status = None; self.on_chunk = None
        self.drop_final = False; self.bad_next = None; self.download_data = b'private fixture PNG bytes'
        self.download_name = '키오 사진.png'; self.download_mime = 'image/png'; self.download_calls = []
    def status(self):
        return {'signedIn': self.user is not None, 'user': dict(self.user) if self.user else None, 'connecting': self.connecting}
    def require(self, **kwargs):
        if self.user is None: raise AgentError('ACCOUNT_REQUIRED', 401)
        return dict(self.user)
    def login(self, provider, **kwargs):
        self.logins.append((provider, dict(kwargs))); self.connecting = True
    def cancel(self): self.connecting = False
    def cloud(self, route, body=None, *, method='POST', **kwargs):
        body = dict(body or {}); self.calls.append((route, body, method, self.user['id']))
        if kwargs.get('expected_user') and kwargs['expected_user'] != self.user['id']: raise AgentError('driveAccountChanged')
        if route == '/control/drive/status':
            if self.on_status: self.on_status(self)
            return {'drive': {'connected': self.connected, 'rootId': self.root, 'accountId': self.user['id'], 'email': self.user['email']}}
        if route == '/control/drive/connect': return {'drive': {'connected': True, 'rootId': self.root}}
        if route == '/control/drive/disconnect':
            assert body=={'confirmed':True};self.connected=False;return {'disconnected':True,'allDevices':True}
        if route == '/control/drive/list':
            return {'files': [{'id': 'fixture-folder', 'name': '사진', 'mimeType': FOLDER},
                              {'id': 'fixture-output', 'name': '키오 사진.png', 'mime': 'image/png', 'webUrl': 'https://drive.google.com/file/d/fixture/view'}],
                    'nextPageToken': 'fixture-next-page'}
        if route == '/control/drive/upload/start':
            if body['assetId'] in self.completed:
                previous = self.completed[body['assetId']]
                if previous['userId'] != self.user['id'] or previous['metadata'] != body: raise AgentError('driveInvalidResponse')
                return {'complete': True, 'file': dict(previous['file']), 'nextOffset': body['size']}
            ticket = 'mock-opaque-ticket-' + str(uuid.uuid4())
            self.sessions[ticket] = {'metadata': body, 'userId': self.user['id'], 'data': bytearray()}
            return {'ticket': ticket, 'chunkBytes': CHUNK, 'size': body['size'], 'expires': int((time.time() + 86400) * 1000)}
        if route == '/control/drive/upload/chunk':
            session = self.sessions[body['ticket']]
            if session['userId'] != self.user['id']: raise AgentError('driveAccountChanged')
            data = base64.b64decode(body['data'], validate=True)
            if len(data) > CHUNK or body['offset'] != len(session['data']): raise AgentError('driveInvalidResponse')
            self.chunk_calls.append((body['offset'], data, session['userId'], body['ticket']))
            session['data'].extend(data); metadata = session['metadata']; complete = len(session['data']) == metadata['size']
            response = {'complete': complete, 'nextOffset': self.bad_next if self.bad_next is not None else len(session['data'])}
            if complete:
                if hashlib.sha256(session['data']).hexdigest() != metadata['sha256']: raise AgentError('driveInvalidResponse')
                file = {'id': 'fixture-output-' + metadata['assetId'], 'webUrl': 'https://drive.google.com/file/d/fixture/view'}
                self.completed[metadata['assetId']] = {'file': file, 'userId': self.user['id'], 'metadata': metadata, 'data': bytes(session['data'])}
                response['file'] = file
            if self.on_chunk: self.on_chunk(self)
            if complete and self.drop_final:
                self.drop_final = False; raise AgentError('accountCloudUnavailable', 503)
            return response
        raise AssertionError('Unexpected mocked cloud endpoint: ' + route)
    def binary_download(self, file_id, destination, maxbytes, *, expected_user=None):
        if expected_user is not None and expected_user != self.user['id']: raise AgentError('driveAccountChanged')
        self.download_calls.append((file_id, Path(destination), maxbytes, self.user['id']))
        if len(self.download_data) > maxbytes: raise AgentError('fileTooLarge', 413)
        Path(destination).write_bytes(self.download_data)
        return {'name': self.download_name, 'mime': self.download_mime, 'size': len(self.download_data)}


class CloudDriveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name)
        self.account = MockAccount(); self.drive = KIOCloudDrive(self.path / 'state', self.account)
    def tearDown(self): self.temp.cleanup()
    def source(self, size=CHUNK * 2 + 19):
        data = (bytes(range(251)) * (size // 251 + 1))[:size]
        source = self.path / '테스트 원본.png'; source.write_bytes(data)
        meta = {'assetId': str(uuid.uuid4()), 'name': source.name, 'bytes': size, 'mime': 'image/png',
                'sha256': hashlib.sha256(data).hexdigest(), 'relativePath': '사진/2026/10/' + source.name,
                'accountId': self.account.user['id'], 'driveRootId': self.account.root}
        return source, data, meta
    def upload_requests(self): return [call for call in self.account.calls if '/upload/' in call[0]]
    def test_upload_uses_cloud_two_mib_chunks_exact_metadata_and_private_ticket_cleanup(self):
        source, data, meta = self.source(); before = source.read_bytes()
        result = self.drive.upload(source, meta)
        self.assertEqual(result['id'], 'fixture-output-' + meta['assetId'])
        self.assertEqual([offset for offset, *_ in self.account.chunk_calls], [0, CHUNK, CHUNK * 2])
        self.assertEqual([len(chunk) for _, chunk, *_ in self.account.chunk_calls], [CHUNK, CHUNK, 19])
        self.assertEqual(b''.join(chunk for _, chunk, *_ in self.account.chunk_calls), data)
        start = next(body for route, body, *_ in self.account.calls if route.endswith('/start'))
        self.assertEqual(start, {'name': meta['name'], 'mime': meta['mime'], 'size': len(data), 'sha256': meta['sha256'],
                                'assetId': meta['assetId'], 'relativePath': meta['relativePath']})
        self.assertEqual(source.read_bytes(), before); self.assertEqual(list(self.drive.tickets.glob('*.json')), [])
    def test_restarted_adapter_resumes_saved_offset_with_existing_ticket(self):
        source, data, meta = self.source(CHUNK + 47)
        self.drive.status()
        metadata = {'name': meta['name'], 'mime': meta['mime'], 'size': len(data), 'sha256': meta['sha256'],
                    'assetId': meta['assetId'], 'relativePath': meta['relativePath']}
        start = self.account.cloud('/control/drive/upload/start', metadata); ticket = start['ticket']
        self.account.sessions[ticket]['data'].extend(data[:CHUNK])
        saved = {**start, 'userId': USER['id'], 'sha256': meta['sha256'], 'offset': CHUNK}
        filename = self.drive.tickets / (meta['assetId'] + '.json'); atomic_json(filename, saved)
        if os.name != 'nt': self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
        before = len(self.upload_requests()); restored = KIOCloudDrive(self.path / 'state', self.account)
        self.assertEqual(restored.upload(source, meta)['id'], 'fixture-output-' + meta['assetId'])
        self.assertEqual(len(self.upload_requests()) - before, 1)
        self.assertEqual(self.account.chunk_calls[0][0], CHUNK); self.assertEqual(self.account.chunk_calls[0][3], ticket)
        self.assertEqual(self.account.chunk_calls[0][1], data[CHUNK:]); self.assertFalse(filename.exists())
    def test_lost_final_response_recovers_completed_asset_without_second_commit_or_reupload(self):
        source, data, meta = self.source(CHUNK + 21); self.account.drop_final = True
        result = self.drive.upload(source, meta)
        starts = [body for route, body, *_ in self.account.calls if route.endswith('/start')]
        self.assertEqual(len(starts), 2); self.assertEqual(starts[0], starts[1])
        self.assertEqual(len(self.account.sessions), 1); self.assertEqual(len(self.account.completed), 1)
        self.assertEqual(self.account.completed[meta['assetId']]['data'], data)
        self.assertEqual(result['id'], 'fixture-output-' + meta['assetId'])
        self.assertEqual(len(self.account.chunk_calls), 2); self.assertEqual(list(self.drive.tickets.glob('*.json')), [])
    def test_foreign_account_and_root_queue_entries_fail_before_upload(self):
        source, _, meta = self.source(123)
        for changes in ({'accountId': OTHER['id']}, {'driveRootId': 'different-control-root'}):
            with self.subTest(changes=changes), self.assertRaisesRegex(AgentError, 'driveAccountChanged'):
                self.drive.upload(source, {**meta, **changes})
            self.assertEqual(self.upload_requests(), [])
        self.assertEqual(self.drive.upload(source, {**meta, 'driveRootId': DEFAULT_ROOT})['id'], 'fixture-output-' + meta['assetId'])
    def test_foreign_user_saved_ticket_is_never_sent_and_new_upload_is_bound_to_current_user(self):
        source, _, meta = self.source(121)
        atomic_json(self.drive.tickets / (meta['assetId'] + '.json'), {'ticket': 'foreign-opaque-ticket', 'chunkBytes': CHUNK,
                    'offset': 0, 'userId': OTHER['id'], 'sha256': meta['sha256'], 'expires': int((time.time() + 86400) * 1000)})
        self.drive.upload(source, meta)
        self.assertNotIn('foreign-opaque-ticket', [body.get('ticket') for _, body, *_ in self.upload_requests()])
        self.assertEqual({owner for _, _, owner, _ in self.account.chunk_calls}, {USER['id']})
    def test_account_change_during_chunk_stops_before_next_chunk(self):
        source, _, meta = self.source(CHUNK + 61)
        self.account.on_chunk = lambda account: setattr(account, 'user', dict(OTHER))
        with self.assertRaisesRegex(AgentError, 'driveAccountChanged'): self.drive.upload(source, meta)
        self.assertEqual(len(self.account.chunk_calls), 1)
        self.assertEqual(self.account.chunk_calls[0][2], USER['id'])
    def test_changed_account_during_status_cannot_initialize_another_users_upload(self):
        source, _, meta = self.source(121)
        def switch(account): account.user = dict(OTHER); account.root = 'other-private-control-root'
        self.account.on_status = switch
        with self.assertRaisesRegex(AgentError, 'driveAccountChanged|driveNotConnected'): self.drive.upload(source, meta)
        self.assertEqual(self.upload_requests(), [])
    def test_malformed_chunk_acknowledgement_is_not_recorded_as_completion(self):
        for next_offset in (True, 0, -1, CHUNK + 100):
            with self.subTest(next_offset=next_offset):
                source, _, meta = self.source(123); self.account.bad_next = next_offset
                with self.assertRaisesRegex(AgentError, 'driveInvalidResponse'): self.drive.upload(source, meta)
                saved = read_json(self.drive.tickets / (meta['assetId'] + '.json'))
                self.assertEqual(saved['offset'], 0)
    def test_download_retains_cloud_mime_name_bytes_and_digest_for_image_and_pdf(self):
        for name, mime, data in [('키오 사진.png', 'image/png', b'fixture PNG bytes'), ('업무 문서.pdf', 'application/pdf', b'%PDF-1.7 fixture bytes')]:
            with self.subTest(mime=mime):
                self.account.download_name = name; self.account.download_mime = mime; self.account.download_data = data
                target = self.path / ('private-' + name); result = self.drive.download('fixture-file', target, 512)
                self.assertEqual(target.read_bytes(), data); self.assertEqual(result['bytes'], len(data))
                self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(result['metadata'], {'id': 'fixture-file', 'name': name, 'mimeType': mime})
                self.assertEqual(self.account.download_calls[-1][2], 512)
    def test_connect_requests_explicit_drive_consent_for_the_existing_supabase_user(self):
        self.account.connected = False
        status = self.drive.connect()
        self.assertTrue(status['connecting']); self.assertFalse(status['connected'])
        self.assertEqual(self.account.logins, [('google', {'expected_user': USER['id'], 'connect_drive': True})])
        self.account.connected = True; self.account.connecting = False; self.drive.checked = 0
        connected = self.drive.connect(); self.assertTrue(connected['connected'])
        self.assertEqual(len(self.account.logins), 1)
        self.assertEqual(connected['path'], PATH); self.assertEqual(connected['scope'], 'kio-control-private-subtree')
        with self.assertRaisesRegex(AgentError, 'drivePermissionRequired'): self.drive.select_root('unrelated-folder')
    def test_account_disconnect_stops_other_device_and_later_shared_reconnect_restores_both(self):
        second = KIOCloudDrive(self.path / 'second', self.account)
        self.assertTrue(self.drive.status()['connected']); self.assertTrue(second.status()['connected'])
        self.assertFalse(self.drive.disconnect()['connected'])
        second.checked = 0
        with self.assertRaisesRegex(AgentError, 'driveNotConnected'): second.list_library()
        self.assertFalse(second.status()['connected'])
        self.account.connected = True  # Explicit fresh OAuth completed on the web/another device.
        self.drive.checked = 0; second.checked = 0
        self.assertTrue(self.drive.status()['connected']); self.assertTrue(second.status()['connected'])
        self.assertEqual(self.account.logins, [])

    def test_listing_forwards_scoped_query_and_normalizes_cloud_mime_link_aliases(self):
        listed = self.drive.list_library('fixture-child', 'next-page', '사진', 'image')
        body = next(body for route, body, *_ in self.account.calls if route.endswith('/list'))
        self.assertEqual(body, {'parentId': 'fixture-child', 'pageToken': 'next-page', 'query': '사진', 'kind': 'image'})
        self.assertEqual(listed['files'][1]['mimeType'], 'image/png')
        self.assertEqual(listed['files'][1]['webViewLink'], 'https://drive.google.com/file/d/fixture/view')
        self.assertTrue(listed['scopeLimited']); self.assertEqual(listed['nextPageToken'], 'fixture-next-page')


if __name__ == '__main__': unittest.main(verbosity=2)

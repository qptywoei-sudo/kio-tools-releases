"""OAuth callback through shared storage and inference; synthetic transport only."""
import copy
import io
import json
import sys
import threading
import types
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'agent'), str(ROOT / 'engine/deps-agent/win64')]
from ai_translate import AITranslate, POLICY, TRANSLATION
from chatgpt_account import PLAN_SCOPE, RESOURCE, TOKEN, ChatGPTAccount


class SharedCloud:
    """Deep-copy the handoff as the separate KIO service does."""
    def __init__(self):
        self.revision = -1
        self.grant = None
        self.captures = 0

    def cloud(self, route, body=None, method='POST', expected_user=None):
        assert expected_user == 'fixture-kio-user'
        operation = route.rsplit('/', 1)[-1]
        if operation == 'connect':
            assert method == 'POST' and body['revision'] == self.revision
            self.grant = copy.deepcopy(body['grant'])
            self.captures += 1
            self.revision += 1
        elif operation == 'status':
            assert method == 'GET'
        elif operation != 'access':
            raise AssertionError('Unexpected cloud operation')
        value = {
            'connected': self.grant is not None,
            'persistent': self.grant is not None,
            'revision': self.revision,
            'accountId': self.grant['subject'] if self.grant else '',
            'email': self.grant['email'] if self.grant else '',
        }
        if operation == 'access':
            assert self.grant is not None
            value.update({key: self.grant[key] for key in
                          ('access_token', 'client_id', 'scopes', 'expires_at')})
        return {'chatgpt': value}


class SharedOAuthInferenceTests(unittest.TestCase):
    def test_approved_callback_handoff_remains_usable_for_completed_inference(self):
        cloud = SharedCloud()
        account = ChatGPTAccount.__new__(ChatGPTAccount)
        account.lock = threading.RLock()
        account.error = ''
        account.generation = 0
        account.models = []
        account.kio = None
        account.kio_user = ''
        account.shared_status = None
        account.shared_checked = 0
        account.data = {'accounts': {}, 'active': ''}
        account.bind_kio(cloud, 'fixture-kio-user')
        saved = []
        account.persist = lambda: saved.append(copy.deepcopy(account.data))
        account.validate = Mock(return_value={
            'sub': 'fixture-openai-user', 'email': 'fixture@example.invalid',
        })

        oauth = {
            'access_token': 'fixture-access-not-a-real-token',
            'refresh_token': 'fixture-refresh-not-a-real-token',
            'id_token': 'fixture-id-not-a-real-token',
            'token_type': 'Bearer',
            'scope': 'openid profile email offline_access resource.invoke ' + PLAN_SCOPE,
            'expires_in': 3600,
        }
        result = {
            'contentType': 'document', 'originalLanguage': 'en',
            'detectedReplyLanguage': None, 'replyTarget': None,
            'messages': [{
                'speaker': '', 'speakerTranslated': '', 'isMine': None,
                'originalText': 'fixture source', 'translatedText': 'fixture translation',
                'language': 'en', 'confidence': 1, 'isTruncated': False,
            }],
        }
        requests = []

        def transport(url, method='GET', data=None, headers=None, timeout=25):
            requests.append((url, method))
            if url == TOKEN:
                fields = urllib.parse.parse_qs(data.decode())
                self.assertEqual(fields['grant_type'], ['authorization_code'])
                self.assertEqual(fields['client_id'], ['fixture-issued-client'])
                self.assertEqual(fields['redirect_uri'], ['http://127.0.0.1:9999/auth/callback'])
                self.assertEqual(fields['resource'], [RESOURCE])
                return io.BytesIO(json.dumps(oauth).encode())
            self.assertEqual(headers['Authorization'], 'Bearer ' + oauth['access_token'])
            if url == RESOURCE + '/models':
                self.assertEqual(method, 'GET')
                return io.BytesIO(json.dumps({'models': [{
                    'slug': POLICY['model'], 'display_name': 'Fixture account model',
                    'visibility': 'list', 'input_modalities': ['text', 'image'],
                    'supported_reasoning_levels': [POLICY['reasoning']],
                }]}).encode())
            self.assertEqual((url, method), (RESOURCE + '/responses', 'POST'))
            payload = json.loads(data)
            self.assertEqual(payload['model'], POLICY['model'])
            self.assertIs(payload['store'], False)
            self.assertIs(payload['stream'], True)
            self.assertEqual(payload['input'][0]['content'][0]['text'], 'fixture source')
            event = {'type': 'response.completed', 'response': {
                'status': 'completed', 'output': [{
                    'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(result)}],
                }],
            }}
            return io.BytesIO(('data: ' + json.dumps(event) + '\n\n').encode())

        account.raw = transport
        done = threading.Event()
        done.set()
        pending = {
            'done': done, 'cancel': threading.Event(),
            'query': {'code': ['fixture-code'], 'client_id': ['fixture-issued-client']},
            'previous': None, 'nonce': 'fixture-nonce', 'verifier': 'fixture-verifier',
            'redirect': 'http://127.0.0.1:9999/auth/callback', 'cloudRevision': -1,
            'server': types.SimpleNamespace(server_close=Mock()),
        }
        account.pending = pending
        account._callback(pending)

        self.assertIsNone(account.pending)
        self.assertEqual(cloud.captures, 1)
        self.assertEqual(account.error, '')
        account.validate.assert_called_once_with(oauth['id_token'], 'fixture-issued-client', 'fixture-nonce', None)
        pending['server'].server_close.assert_called_once()
        self.assertGreaterEqual(len(saved), 2)
        for key in ('access_token', 'refresh_token', 'id_token', 'scopes', 'expires_at'):
            self.assertNotIn(key, account.current())
        status = account.status()
        self.assertTrue(status['connected'])
        self.assertTrue(status['planApproved'])
        self.assertEqual(status['error'], '')
        for credential in oauth['access_token'], oauth['refresh_token'], oauth['id_token']:
            self.assertNotIn(credential, json.dumps(status))

        ai = AITranslate.__new__(AITranslate)
        ai.account = account
        job = {
            'id': 'fixture-job', 'status': 'running', 'received': 0,
            'cancel': threading.Event(), 'generation': account.generation,
            'settings': {'model': 'auto', 'reasoning': 'recommended'},
            'timings': {},
        }
        translated, model = ai.infer(job, 'Fixture translation instructions',
                                     [{'type': 'input_text', 'text': 'fixture source'}], TRANSLATION)
        self.assertEqual(translated, result)
        self.assertEqual(model, POLICY['model'])
        self.assertEqual(requests, [(TOKEN, 'POST'), (RESOURCE + '/models', 'GET'),
                                    (RESOURCE + '/responses', 'POST')])
        self.assertEqual(account.status()['error'], '')
        self.assertGreater(job['timings']['completedAt'], 0)


if __name__ == '__main__':
    unittest.main()

"""Device-local UI preference, independent of account and OAuth credentials."""
from __future__ import annotations
import ctypes, json, logging, os, re, subprocess, sys
from pathlib import Path
from common import atomic_json, read_json

LANGUAGES = ('vi', 'en', 'ko', 'ja', 'zh-TW', 'zh-CN')

def normalize(value):
    if not isinstance(value, str): return None
    parts = value.strip().replace('_', '-').split('-')
    base = parts[0].lower()
    if base in ('vi', 'en', 'ko', 'ja'): return base
    if base != 'zh': return None
    tags = {part.lower() for part in parts[1:]}
    if 'hant' in tags: return 'zh-TW'
    if 'hans' in tags: return 'zh-CN'
    return 'zh-TW' if tags & {'tw', 'hk', 'mo'} else 'zh-CN'

def system_languages():
    """Read display-language preferences, never WebView's default locale."""
    try:
        if os.name == 'nt':
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            count, size = ctypes.c_ulong(), ctypes.c_ulong()
            if kernel.GetUserPreferredUILanguages(8, ctypes.byref(count), None, ctypes.byref(size)) and 1 < size.value < 65536:
                buffer = ctypes.create_unicode_buffer(size.value)
                if kernel.GetUserPreferredUILanguages(8, ctypes.byref(count), buffer, ctypes.byref(size)):
                    return [part for part in buffer[:size.value].split('\0') if part]
            buffer = ctypes.create_unicode_buffer(85)
            if kernel.GetUserDefaultLocaleName(buffer, 85): return [buffer.value]
        elif sys.platform == 'darwin':
            # defaults reads the same global preference used by NSLocale.
            import plistlib
            result = subprocess.run(['/usr/bin/defaults', 'export', '-g', '-'], capture_output=True, timeout=3, check=True)
            values = plistlib.loads(result.stdout).get('AppleLanguages', [])
            if isinstance(values, list): return [v for v in values if isinstance(v, str) and v.strip()]
        else:
            import locale
            value = locale.getlocale()[0]
            if value: return [value]
    except (OSError, ValueError, subprocess.SubprocessError):
        logging.getLogger('kio.i18n').warning('osLanguageUnavailable')
    return []

def resolve(saved=None, system=(), account=None):
    if normalize(saved): return normalize(saved), 'user'
    # An available but unsupported primary OS language intentionally uses English.
    if system: return normalize(system[0]) or 'en', 'system'
    if normalize(account): return normalize(account), 'account'
    return 'en', 'fallback'

class LanguagePreference:
    def __init__(self, state, system_reader=system_languages):
        self.path = Path(state) / 'language-preference.json'
        self.system_reader = system_reader
    def snapshot(self, account=None):
        saved = read_json(self.path, {})
        if not isinstance(saved,dict): saved = {}
        languages = self.system_reader()
        if not isinstance(languages,(list,tuple)): languages = []
        languages = [v for v in languages if isinstance(v,str) and v.strip()]
        code, source = resolve(saved.get('language') if saved.get('source') == 'user' else None, languages, account)
        return {'language': code, 'source': source, 'systemLanguages': languages}
    def select(self, value):
        if value not in LANGUAGES: raise ValueError('invalidLanguage')
        atomic_json(self.path, {'schemaVersion': 1, 'language': value, 'source': 'user'})
        return self.snapshot()

_messages = None
def text(key, language):
    global _messages
    if _messages is None:
        _messages = {}
        base = Path(__file__).resolve().parent
        # Source uses agent/; installed hosts use tools/engine/agent/.
        for directory in (base.parent / 'i18n', base.parent.parent / 'i18n'):
            try:
                _messages = json.loads((directory / 'messages.json').read_text(encoding='utf-8'))
                break
            except (OSError, ValueError): pass
    entry = _messages.get(key, {})
    result = entry.get(normalize(language) or 'en') or entry.get('en')
    if not result:
        logging.getLogger('kio.i18n').warning('missingTranslation:%s', key)
        return 'Bogo Tools'
    return result

def callback_page(key, language):
    from html import escape
    code = normalize(language) or 'en'
    return ('<!doctype html><html lang="' + code + '"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bogo Tools</title>'
            '<body style="font:18px system-ui;padding:clamp(20px,8vw,60px);background:#FFFAF6;color:#342B26"><h1 style="color:#A94700">Bogo Tools</h1><p>'
            + escape(text(key, code)) + '</p></body></html>').encode('utf-8')

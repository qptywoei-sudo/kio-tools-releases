"""Closed preservation guards for the audited Windows Unicode extraction change.

Actual Windows behavior is verified separately with synthetic filesystem tests
and the normal packaged SFX; these source guards preserve the original native
authentication, startup, factory settings and compatibility paths byte-for-byte.
"""
from pathlib import Path
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
APPROVED_CPP_SHA = '718136871df5ec36550d4dca50dc8249362ee61c32ed1442f48f76d8844f3629'
ORIGINAL_CPP_SHA = '4c9dbc3c63da77f8ce77555ded0d2fcd9e0e8aab8c4141305ca2d85d0cdabab2'
FACTORY_C_SHA = '2b6d16a1ec80403bfba281b4457f4fa01448598951a4dd7a2b00978506b19f46'
SCRIPT_SHA = '920404707aac452cf55fb3567a4e18e4a356299da62b0a1a1f0be7182bfc45a1'
OLD_CALL = 'if(ok){UINT count=GetSystemDirectoryW(path,32768);DWORD result=1;ok=count&&count<32768&&run(std::wstring(path)+L"\\\\tar.exe",L"-xf "+quote(archive)+L" -C "+quote(root),&result);}'
NEW_COMMENT = '// The normal system PowerShell/.NET ZIP reader preserves UTF-8 names; no downloads or policy changes.'
OLD_COMMENT = '// Windows 10 (1803+) includes the system tar.exe used here; no shell or downloads.'


def original_launcher_bytes(raw):
    text = raw.decode('utf-8')
    start = 'static std::wstring utf16Base64('
    end = 'static bool payload('
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('Unexpected extraction-helper boundary')
    left = text.index(start)
    right = text.index(end, left)
    text = text[:left] + text[right:]
    if text.count('if(ok)ok=extract(archive,root);') != 1 or text.count(NEW_COMMENT) != 1:
        raise ValueError('Unexpected extraction-call or header shape')
    text = text.replace('if(ok)ok=extract(archive,root);', OLD_CALL, 1)
    text = text.replace(NEW_COMMENT, OLD_COMMENT, 1)
    return text.encode('utf-8')


class PortableExtractionTests(unittest.TestCase):
    def test_approved_cpp_and_embedded_script_identity(self):
        raw = (ROOT / 'windows/PortableLauncher.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), APPROVED_CPP_SHA)
        script = raw.split(b'script+=LR"BOGO_EXTRACT(\n', 1)[1].split(b')BOGO_EXTRACT";', 1)[0]
        self.assertEqual(hashlib.sha256(script).hexdigest(), SCRIPT_SHA)

    def test_exact_inverse_preserves_all_original_authentication_and_startup_bytes(self):
        raw = (ROOT / 'windows/PortableLauncher.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(original_launcher_bytes(raw)).hexdigest(), ORIGINAL_CPP_SHA)

    def test_inverse_rejects_changes_outside_authorized_extractor(self):
        raw = (ROOT / 'windows/PortableLauncher.cpp').read_bytes()
        for before, after in [(b'BCRYPT_SHA256_ALGORITHM', b'BCRYPT_SHA1_ALGORITHM'),
                              (b'Local\\\\KIOToolsSingleIconExtract', b'Local\\\\ForeignExtract'),
                              (b'KIOTOOLS', b'FOREIGN!')]:
            self.assertIn(before, raw)
            changed = raw.replace(before, after, 1)
            self.assertNotEqual(hashlib.sha256(original_launcher_bytes(changed)).hexdigest(), ORIGINAL_CPP_SHA)
        with self.assertRaises(ValueError):
            original_launcher_bytes(raw.replace(b'if(ok)ok=extract(archive,root);', b'', 1))

    def test_native_factory_and_ini_identity_remain_original(self):
        raw = (ROOT / 'windows/GalaxyControl.c').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FACTORY_C_SHA)
        self.assertIn(b'KIOControl.ini', raw)
        expected = b'[input]\r\nkeyboard=uhid\r\nmouse=uhid\r\n'
        self.assertEqual(len(expected), 36)
        self.assertEqual(hashlib.sha256(expected).hexdigest(), '85321301107c054874655bcde48dcb4ab6a47f1fc056fabe820320b23be8b321')


if __name__ == '__main__':
    unittest.main(verbosity=2)

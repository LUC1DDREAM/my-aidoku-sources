import shutil
from pathlib import Path
import tempfile
import unittest
import mirror

class MirrorTests(unittest.TestCase):
    def test_snapshot(self):
        mirror.validate(Path('seed'))
    def test_paths(self):
        for bad in ['../secret','/root','https://evil/x','a\\b','%2e%2e/x','x?y','a/../b','a//b','']:
            with self.subTest(path=bad), self.assertRaises(ValueError): mirror.safe_path(bad)
    def test_tampered_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'site'; shutil.copytree('seed',p)
            (p/'index.json').write_text('{}')
            with self.assertRaises(ValueError): mirror.validate(p)
    def test_extra_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'site'; shutil.copytree('seed',p)
            (p/'unexpected').touch()
            with self.assertRaises(ValueError): mirror.validate(p)
    def test_duplicate_manifest(self):
        line='0'*64+'  index.json\n'
        with self.assertRaises(ValueError): mirror.manifest((line*20).encode())

class PublicationTests(unittest.TestCase):
    def test_seed_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'dist'; mirror.run(out,seed=True)
            self.assertEqual(mirror.validate(out),mirror.validate(Path('seed')))

    def test_failed_download_never_publishes(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'dist'
            with patch.object(mirror,'fetch',side_effect=OSError('network unavailable')):
                with self.assertRaises(OSError): mirror.run(out)
            self.assertFalse(out.exists())

    def test_mixed_deployment_never_publishes(self):
        from unittest.mock import patch
        def fetch(name):
            return b'corrupted' if name=='index.html' else (Path('seed')/name).read_bytes()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'dist'
            with patch.object(mirror,'fetch',side_effect=fetch):
                with self.assertRaisesRegex(ValueError,'Hash mismatch'): mirror.run(out)
            self.assertFalse(out.exists())

    def test_changed_initial_asset_never_publishes(self):
        from unittest.mock import patch
        import hashlib
        name='experimental/icons/en.luc1d-asurascans-v3.png'
        entries=mirror.manifest((Path('seed')/'CHECKSUMS.sha256').read_bytes())
        entries[name]=hashlib.sha256(b'changed').hexdigest()
        data=''.join(f'{digest}  {path}\n' for path,digest in entries.items()).encode()
        def fetch(path):
            if path=='CHECKSUMS.sha256': return data
            return b'changed' if path==name else (Path('seed')/path).read_bytes()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'dist'
            with patch.object(mirror,'fetch',side_effect=fetch):
                with self.assertRaisesRegex(ValueError,'icon mismatch'): mirror.run(out)
            self.assertFalse(out.exists())

    def test_no_redirects(self):
        with self.assertRaises(ValueError):
            mirror.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://evil.invalid/')

    def test_dot_path(self):
        with self.assertRaises(ValueError): mirror.safe_path('.')

if __name__=='__main__': unittest.main()

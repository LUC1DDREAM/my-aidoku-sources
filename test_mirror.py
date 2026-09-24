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
    def test_manifest_entry_limit_covers_live_compatibility_tree(self):
        # The canonical PanelNest tree currently contains more than 300 files.
        accepted=''.join('0'*64+f'  sources/package-{i:04}.aix\n' for i in range(306))
        self.assertEqual(len(mirror.manifest(accepted.encode())),306)
        too_many=''.join('0'*64+f'  sources/package-{i:04}.aix\n' for i in range(mirror.MAX_MANIFEST_ENTRIES+1))
        with self.assertRaisesRegex(ValueError,'Unexpected manifest size'):
            mirror.manifest(too_many.encode())

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

    def test_legitimate_version_bump_keeps_installed_assets(self):
        # Test fixture only: simulate a new package version, retaining old URLs.
        from unittest.mock import patch
        import hashlib, json, zipfile
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)/'site'; shutil.copytree('seed',site)
            cat=json.loads((site/'experimental/index.json').read_bytes())
            item=cat['sources'][0]; old_package=site/'experimental'/item['downloadURL']
            item['version']+=1
            stem=f"{item['id']}-v{item['version']}"
            item['downloadURL']='sources/'+stem+'.aix'
            old_icon=site/'experimental'/item['iconURL']
            item['iconURL']='icons/'+stem+'.png'
            shutil.copyfile(old_icon,site/'experimental'/item['iconURL'])
            with zipfile.ZipFile(old_package) as src, zipfile.ZipFile(site/'experimental'/item['downloadURL'],'w') as dst:
                for name in src.namelist():
                    data=src.read(name)
                    if name=='Payload/source.json':
                        manifest=json.loads(data); manifest['info']['version']=item['version']
                        data=json.dumps(manifest).encode()
                    dst.writestr(name,data)
            for name in ['index.json','index.min.json']:
                (site/'experimental'/name).write_text(json.dumps(cat))
            lines=[]
            for path in sorted(site.rglob('*')):
                if path.is_file() and path != site/'CHECKSUMS.sha256':
                    lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(site).as_posix())
            (site/'CHECKSUMS.sha256').write_text('\n'.join(lines)+'\n')
            out=Path(d)/'out'
            with patch.object(mirror,'fetch',side_effect=lambda name:(site/name).read_bytes()):
                mirror.run(out)
            self.assertEqual(mirror.validate(out),mirror.validate(site))
            for old in (Path('seed')/'experimental/sources').iterdir():
                self.assertEqual(old.read_bytes(),(out/'experimental/sources'/old.name).read_bytes())

    def test_no_redirects(self):
        with self.assertRaises(ValueError):
            mirror.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://evil.invalid/')

    def test_dot_path(self):
        with self.assertRaises(ValueError): mirror.safe_path('.')


    def test_authorized_public_catalog_aliases(self):
        import json, hashlib
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)/'site'; shutil.copytree('seed',site)
            cat=json.loads((site/'experimental/index.json').read_bytes())
            for name in ('index.json','index.min.json'):
                (site/name).write_text(json.dumps(cat))
            for folder in ('sources','icons'):
                shutil.copytree(site/'experimental'/folder,site/folder)
            report=json.loads((site/'experimental/build-report.json').read_bytes())
            report['release']=True
            for source in report['sources']:
                source.update(user_reported_working=True,release_authorized=True)
            (site/'experimental/build-report.json').write_text(json.dumps(report))
            def checksums():
                (site/'CHECKSUMS.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(site).as_posix()+'\n' for p in sorted(site.rglob('*')) if p.is_file() and p!=site/'CHECKSUMS.sha256'))
            checksums()
            mirror.validate(site)
            report['sources'][0]['release_authorized']=False
            (site/'experimental/build-report.json').write_text(json.dumps(report)); checksums()
            with self.assertRaises(ValueError): mirror.validate(site)

if __name__=='__main__': unittest.main()

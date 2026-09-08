"""Fail-closed, credential-free full-tree mirror of our canonical Pages.
The checksum manifest is fetched once; any mixed deployment fails validation.
No source rebuilding, URL rewriting, redirects or catalog metadata changes.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import urllib.request
import zipfile

BASE = 'https://luc1ddream.github.io/panelnest/'
IDS = {'en.luc1d-asurascans', 'en.luc1d-weebcentral', 'multi.luc1d-hentaifox',
       'multi.luc1d-imhentai', 'multi.luc1d-nhentai', 'multi.luc1d-webtoon'}
LIMIT = 32 * 1024 * 1024

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Unexpected redirect: '+newurl)

opener = urllib.request.build_opener(NoRedirect)

def safe_path(value):
    p = PurePosixPath(value)
    if not value or value == '.' or p.is_absolute() or '..' in p.parts or '\\' in value or ':' in value or '%' in value or '?' in value or '#' in value or value != p.as_posix():
        raise ValueError('Unsafe path: '+value)
    return value

def fetch(path):
    with opener.open(BASE+safe_path(path), timeout=45) as response:
        if response.status != 200:
            raise ValueError('Non-200 response')
        data = response.read(LIMIT+1)
    if len(data)>LIMIT:
        raise ValueError('Download limit exceeded')
    return data

def manifest(data):
    entries = {}
    for line in data.decode('utf-8').splitlines():
        digest, name = line.split('  ', 1)
        safe_path(name)
        if not re.fullmatch('[0-9a-f]{64}', digest) or name in entries or name=='CHECKSUMS.sha256':
            raise ValueError('Invalid checksum manifest')
        entries[name] = digest
    if not 15 <= len(entries) <= 200:
        raise ValueError('Unexpected manifest size')
    return entries

def validate(root):
    if root.is_symlink() or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Symlinks are forbidden')
    entries = manifest((root/'CHECKSUMS.sha256').read_bytes())
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(entries)|{'CHECKSUMS.sha256'}:
        raise ValueError('Unmanifested or missing files')
    for name,digest in entries.items():
        p = root/name
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Hash mismatch: '+name)
    catalog = json.loads((root/'experimental/index.min.json').read_bytes())
    if catalog != json.loads((root/'experimental/index.json').read_bytes()):
        raise ValueError('Catalog aliases disagree')
    if len(catalog['sources'])!=len(IDS) or {s['id'] for s in catalog['sources']}!=IDS:
        raise ValueError('Unexpected source set; review required')
    report=json.loads((root/'experimental/build-report.json').read_bytes())
    public = report.get('release') is True
    if report.get('release') not in (True, False):
        raise ValueError('Missing publication classification')
    for name in ('index.json','index.min.json'):
        top = json.loads((root/name).read_bytes())
        if public and top != catalog:
            raise ValueError('Public catalog aliases disagree')
        if not public and top['sources'] != []:
            raise ValueError('Unapproved public catalog')
    if public:
        evidence = report.get('sources', [])
        if len(evidence) != len(IDS) or {s['id'] for s in evidence} != IDS or not all(s.get('package_verified') is True and s.get('release_authorized') is True for s in evidence):
            raise ValueError('Missing public release approval')
        for item in catalog['sources']:
            for key in ('downloadURL','iconURL'):
                path = safe_path(item[key])
                if (root/path).read_bytes() != (root/'experimental'/path).read_bytes():
                    raise ValueError('Public/legacy asset mismatch')
    for item in catalog['sources']:
        package=root/'experimental'/safe_path(item['downloadURL'])
        icon=root/'experimental'/safe_path(item['iconURL'])
        with zipfile.ZipFile(package) as z:
            names = z.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate package members')
            for member in names:
                safe_path(member.rstrip('/'))
            if sum(i.file_size for i in z.infolist())>LIMIT:
                raise ValueError('Package expansion limit')
            info=json.loads(z.read('Payload/source.json'))['info']
            for key in ['id','version','languages','contentRating','minAppVersion','name']:
                if info.get(key)!=item.get(key):
                    raise ValueError('Package/catalog mismatch: '+key)
            if z.read('Payload/icon.png')!=icon.read_bytes():
                raise ValueError('Package icon mismatch')
            if not z.read('Payload/main.wasm').startswith(b'\x00asm\x01\x00\x00\x00'):
                raise ValueError('Invalid WASM header')
    return entries

def run(output, seed=False):
    with tempfile.TemporaryDirectory() as temporary:
        stage=Path(temporary)/'site'
        if seed:
            shutil.copytree(Path(__file__).parent/'seed',stage)
        else:
            stage.mkdir()
            data=fetch('CHECKSUMS.sha256')
            entries=manifest(data)
            (stage/'CHECKSUMS.sha256').write_bytes(data)
            total=0
            for name in entries:
                payload=fetch(name); total+=len(payload)
                if total>LIMIT:
                    raise ValueError('Tree download limit')
                path=stage/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
        entries=validate(stage)
        # Never publish different bytes at an initial versioned package/icon URL.
        baseline=Path(__file__).parent/'seed/experimental'
        for folder in ['sources','icons']:
            for old in (baseline/folder).iterdir():
                new=stage/'experimental'/folder/old.name
                if not new.is_file() or new.read_bytes()!=old.read_bytes():
                    raise ValueError('Versioned asset changed: '+old.name)
        if output.exists():
            raise ValueError('Output already exists; use a clean staging directory')
        shutil.copytree(stage,output)
        print(json.dumps({'files':len(entries)+1,'sources':len(IDS),'mode':'seed' if seed else 'canonical','manifest_sha256':hashlib.sha256((stage/'CHECKSUMS.sha256').read_bytes()).hexdigest()}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--seed',action='store_true'); parser.add_argument('--output',type=Path,default=Path('dist'))
    args=parser.parse_args(); run(args.output,args.seed)

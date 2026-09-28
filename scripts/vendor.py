"""Load pinned parser code bundled for offline builds and generated scripts."""
import atexit
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1] / 'vendor'


def zip_bytes(name):
    entry = json.loads((ROOT / 'manifest.json').read_text())[name]
    path = ROOT / entry['file']
    if path.is_symlink() or path.parent != ROOT:
        raise ValueError('Invalid vendored package path')
    data = path.read_bytes()
    if len(data) != entry['size'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise ValueError(f'Vendored {name} checksum mismatch')
    return data


def toml_parser():
    try:
        return importlib.import_module('tomllib')
    except ImportError:
        directory = tempfile.TemporaryDirectory(prefix='linspace-tomli-')
        atexit.register(directory.cleanup)
        path = Path(directory.name) / 'tomli.zip'
        path.write_bytes(zip_bytes('tomli'))
        sys.path.insert(0, str(path))
        return importlib.import_module('tomli')

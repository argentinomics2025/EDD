"""Offline version/hash probe for fixed wheels. No SQL, sockets or environment dump."""
import ctypes
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    import psycopg
    import psycopg_binary
    if psycopg.pq.__impl__!='binary':raise RuntimeError('Bundled wheel required')
    base=Path(psycopg_binary.__file__).resolve().parent.parent
    dist=importlib.metadata.distribution('psycopg-binary')
    libraries=[];paths={}
    for file in dist.files or []:
        path=Path(dist.locate_file(file)).resolve()
        if path.parent.name!='psycopg_binary.libs' or '.so' not in path.name:continue
        if not path.is_relative_to(base) or not re.fullmatch(r'[A-Za-z0-9_.+-]+',path.name):
            raise RuntimeError('Unexpected bundled library')
        libraries.append({'name':path.name,'sha256':sha256(path)})
        for name in ('libpq','libcrypto'):
            if path.name.startswith(name+'-') or path.name.startswith(name+'.'):
                if name in paths:raise RuntimeError('Ambiguous library')
                paths[name]=path
    if set(paths)!={'libpq','libcrypto'}:raise RuntimeError('Missing private libraries')
    pq=ctypes.CDLL(str(paths['libpq']));pq.PQlibVersion.argtypes=[];pq.PQlibVersion.restype=ctypes.c_int
    pq_version=pq.PQlibVersion()
    if pq_version!=psycopg.pq.version():raise RuntimeError('Different libpq loaded')
    ssl=ctypes.CDLL(str(paths['libcrypto']))
    ssl.OpenSSL_version.argtypes=[ctypes.c_int];ssl.OpenSSL_version.restype=ctypes.c_char_p
    openssl=ssl.OpenSSL_version(0).decode('ascii')
    if not re.fullmatch(r'OpenSSL [0-9A-Za-z.+ -]{1,100}',openssl):raise RuntimeError('Invalid version')
    extensions=[]
    for package in ('psycopg-binary','pydantic-core'):
        wheel=importlib.metadata.distribution(package)
        for file in wheel.files or []:
            path=Path(wheel.locate_file(file)).resolve()
            if path.suffix=='.so' and path.is_relative_to(base) and path.parent.name!='psycopg_binary.libs':
                extensions.append({'package':package,'version':wheel.version,
                                   'name':path.name,'sha256':sha256(path)})
    return {'psycopg':psycopg.__version__,'psycopg_binary':dist.version,
            'implementation':'binary','libpq_version':pq_version,'openssl_version':openssl,
            'private_libraries':sorted(libraries,key=lambda item:item['name']),
            'extensions':extensions,'transitive_advisory_coverage':'not_established'}


if __name__=='__main__':
    try:print(json.dumps(inventory(),sort_keys=True))
    except Exception:
        print('EC017_NATIVE_INVENTORY_FAILED')
        raise SystemExit(1) from None

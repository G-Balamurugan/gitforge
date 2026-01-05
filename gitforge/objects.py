import hashlib
import json
import os
import shutil
import time
import zlib

from collections import namedtuple
from contextlib import contextmanager

# Will be initialized in cli.main()
GIT_DIR = None


class ConflictException (Exception):
    """Raised when an operation cannot proceed due to merge conflicts in the index."""
    def __init__ (self, message, conflicted_files=None):
        super ().__init__ (message)
        self.conflicted_files = conflicted_files or []


def has_conflicts (index):
    """Check if the index has any conflicted entries."""
    return any (entry.get ('state') == 'conflict' for entry in index.values ())


def get_conflicted_files (index):
    """Return list of file paths that have conflicts in the index."""
    return [path for path, entry in index.items () if entry.get ('state') == 'conflict']

@contextmanager
def change_git_dir (new_dir):
    global GIT_DIR
    old_dir = GIT_DIR
    GIT_DIR = f'{new_dir}/.gitforge'
    yield
    GIT_DIR = old_dir

def init ():
    os.makedirs (GIT_DIR)
    os.makedirs (f'{GIT_DIR}/objects')

RefValue = namedtuple ('RefValue', ['symbolic', 'value'])

def update_ref (ref, value, deref=True):
    ref = _get_ref_internal (ref, deref)[0]

    assert value.value
    if value.symbolic:
        value = f'ref: {value.value}'
    else:
        value = value.value

    ref_path = f'{GIT_DIR}/{ref}'
    os.makedirs (os.path.dirname (ref_path), exist_ok=True)
    with open (ref_path, 'w') as f:
        f.write (value)

def get_ref (ref, deref=True):
    return _get_ref_internal (ref, deref)[1]

def delete_ref (ref, deref=True):
    ref = _get_ref_internal (ref, deref)[0]
    os.remove (f'{GIT_DIR}/{ref}')

def _get_ref_internal (ref, deref):
    ref_path = f'{GIT_DIR}/{ref}'
    value = None
    if os.path.isfile (ref_path):
        with open (ref_path) as f:
            value = f.read ().strip ()
    """
    1. If the file that represents a ref contains an OID, we'll assume that the ref points to an OID. 
    2. If the file contains the content ref: <refname>, we'll assume that the ref points to <refname> and we will dereference it recursively.
    """
    symbolic = bool (value) and value.startswith ('ref:')
    if symbolic:
        value = value.split (':', 1)[1].strip ()
        if deref:       # To make recursive to call until we find the OID ( i.e., non-symbolic reference )
            return _get_ref_internal (value, deref=True)

    return ref, RefValue (symbolic=symbolic, value=value)

def iter_refs (prefix='', deref=True):
    refs = ['HEAD', 'MERGE_HEAD', 'ORIG_HEAD', 'CHERRY_PICK_HEAD']
    for root, _, filenames in os.walk (f'{GIT_DIR}/refs/'):
        root = os.path.relpath (root, GIT_DIR)
        refs.extend (f'{root}/{name}' for name in filenames)

    for refname in refs:
        if not refname.startswith (prefix):
            continue
        ref = get_ref (refname, deref=deref)
        if ref.value:
            yield refname, ref

@contextmanager
def get_index ():
    index = {}
    if os.path.isfile (f'{GIT_DIR}/index'):
        with open (f'{GIT_DIR}/index') as f:
            index = json.load (f)

    yield index

    with open (f'{GIT_DIR}/index', 'w') as f:
        json.dump (index, f)

def hash_object (data, type_='blob'):
    obj = type_.encode () + b'\x00' + data
    oid = hashlib.sha1 (obj).hexdigest ()
    os.makedirs (f'{GIT_DIR}/objects/{oid[:2]}', exist_ok=True)
    with open (f'{GIT_DIR}/objects/{oid[:2]}/{oid[2:]}', 'wb') as out:
        out.write (zlib.compress (obj))
    return oid


def get_object (oid, expected='blob'):
    with open (f'{GIT_DIR}/objects/{oid[:2]}/{oid[2:]}', 'rb') as f:
        obj = zlib.decompress (f.read ())

    type_, _, content = obj.partition (b'\x00')
    type_ = type_.decode ()

    if expected is not None:
        assert type_ == expected, f'Expected {expected}, got {type_}'
    return content

def object_exists (oid):
    return os.path.isfile (f'{GIT_DIR}/objects/{oid[:2]}/{oid[2:]}')

def fetch_object_if_missing (oid, remote_git_dir):
    if object_exists (oid):
        return
    remote_git_dir += '/.gitforge'
    os.makedirs (f'{GIT_DIR}/objects/{oid[:2]}', exist_ok=True)
    shutil.copy (f'{remote_git_dir}/objects/{oid[:2]}/{oid[2:]}',
                 f'{GIT_DIR}/objects/{oid[:2]}/{oid[2:]}')

def push_object (oid, remote_git_dir):
    remote_git_dir += '/.gitforge'
    os.makedirs (f'{remote_git_dir}/objects/{oid[:2]}', exist_ok=True)
    shutil.copy (f'{GIT_DIR}/objects/{oid[:2]}/{oid[2:]}',
                 f'{remote_git_dir}/objects/{oid[:2]}/{oid[2:]}')

def get_config ():
    config_path = f'{GIT_DIR}/config'
    config = {}
    if os.path.isfile (config_path):
        with open (config_path) as f:
            config = json.load (f)
    return config

def set_config (key, value):
    config = get_config ()
    keys = key.split ('.')
    current = config
    for k in keys[:-1]:
        current = current.setdefault (k, {})
    current[keys[-1]] = value

    with open (f'{GIT_DIR}/config', 'w') as f:
        json.dump (config, f, indent=2)

def get_user_identity ():
    config = get_config ()
    user = config.get ('user', {})

    name = user.get ('name') or os.environ.get ('GIT_AUTHOR_NAME', 'Unknown')
    email = user.get ('email') or os.environ.get ('GIT_AUTHOR_EMAIL', 'unknown@example.com')

    return name, email

def format_timestamp ():
    timestamp = int (time.time ())
    local_time = time.localtime ()
    if local_time.tm_isdst and time.daylight:
        offset = -time.altzone
    else:
        offset = -time.timezone
    hours, remainder = divmod (abs (offset), 3600)
    minutes = remainder // 60
    sign = '+' if offset >= 0 else '-'
    tz_str = f'{sign}{hours:02d}{minutes:02d}'
    return f'{timestamp} {tz_str}'


# ============================================================================
# REBASE STATE MANAGEMENT
# ============================================================================

def get_rebase_state():
    """Get current rebase state from .gitforge/REBASE_STATE"""
    state_path = f'{GIT_DIR}/REBASE_STATE'
    if os.path.isfile(state_path):
        with open(state_path) as f:
            return json.load(f)
    return None

def save_rebase_state(state):
    """Save rebase state to .gitforge/REBASE_STATE"""
    with open(f'{GIT_DIR}/REBASE_STATE', 'w') as f:
        json.dump(state, f)

def delete_rebase_state():
    """Delete rebase state file"""
    state_path = f'{GIT_DIR}/REBASE_STATE'
    if os.path.isfile(state_path):
        os.remove(state_path)


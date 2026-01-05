import itertools
import operator
import os
import re
import string

from collections import deque, namedtuple

from . import objects
from . import diff_engine

Author = namedtuple ('Author', ['name', 'email', 'timestamp', 'timezone'])

def init ():
    objects.init ()
    objects.update_ref ('HEAD', objects.RefValue (symbolic=True, value='refs/heads/master'))

def write_tree ():
    # Index is flat, we need it as a tree of dicts
    index_as_tree = {}
    with objects.get_index () as index:
        for path, entry in index.items ():
            # Extract oid from new index format
            oid = entry['oid']
            if oid is None:
                # During index with "state": "conflict" and  "type": "delete_modify" / "add_add"
                continue
                
            path_parts = path.split ('/')
            dirpath, filename = path_parts[:-1], path_parts[-1]

            current = index_as_tree
            # Find the dict for the directory of this file
            for dirname in dirpath:
                current = current.setdefault (dirname, {})
            current[filename] = oid

    def write_tree_recursive (tree_dict):
        entries = []
        for name, value in tree_dict.items ():
            if type (value) is dict:
                type_ = 'tree'
                oid = write_tree_recursive (value)
            else:
                type_ = 'blob'
                oid = value
            entries.append ((name, oid, type_))

        tree = ''.join (f'{type_} {oid} {name}\n'
                        for name, oid, type_
                        in sorted (entries))
        return objects.hash_object (tree.encode (), 'tree')

    return write_tree_recursive (index_as_tree)


def _iter_tree_entries (oid):
    if not oid:
        return
    tree = objects.get_object (oid, 'tree')
    for entry in tree.decode ().splitlines ():
        type_, oid, name = entry.split (' ', 2)
        yield type_, oid, name


def get_tree (oid, base_path=''):
    result = {}
    for type_, oid, name in _iter_tree_entries (oid):
        assert '/' not in name
        assert name not in ('..', '.')
        path = base_path + name
        if type_ == 'blob':
            result[path] = oid
        elif type_ == 'tree':
            result.update (get_tree (oid, f'{path}/'))
        else:
            assert False, f'Unknown tree entry {type_}'
    return result

def get_working_tree ():
    result = {}
    for root, _, filenames in os.walk ('.'):
        for filename in filenames:
            path = os.path.relpath (f'{root}/{filename}')
            if is_ignored (path) or not os.path.isfile (path):
                continue
            with open (path, 'rb') as f:
                result[path] = objects.hash_object (f.read ())
    return result

def get_index_tree ():
    """Return index as {path: oid} for clean entries only (for diff comparisons)."""
    with objects.get_index () as index:
        return {path: entry['oid'] for path, entry in index.items ()
                if entry.get ('state') == 'clear'}

def _empty_current_directory ():
    for root, dirnames, filenames in os.walk ('.', topdown=False):
        for filename in filenames:
            path = os.path.relpath (f'{root}/{filename}')
            if is_ignored (path) or not os.path.isfile (path):
                continue
            os.remove (path)
        for dirname in dirnames:
            path = os.path.relpath (f'{root}/{dirname}')
            if is_ignored (path):
                continue
            try:
                os.rmdir (path)
            except (FileNotFoundError, OSError):
                # Deletion might fail if the directory contains ignored files,
                # so it's OK
                pass

def read_tree (tree_oid, update_working=False):
    with objects.get_index () as index:
        index.clear ()
        # Convert plain tree {path: oid} to new index format {path: {state, oid}}
        tree = get_tree (tree_oid)
        for path, oid in tree.items ():
            index[path] = {"state": "clear", "oid": oid}

        if update_working:
            _checkout_index (index)

def read_tree_merged (t_base, t_HEAD, t_other, update_working=False):
    # t_base is the Least Common Ancestor

    tree, conflicts = diff_engine.merge_trees (
        get_tree (t_base),
        get_tree (t_HEAD),
        get_tree (t_other)
    )

    with objects.get_index () as index:
        index.clear ()
        index.update(tree)

        if update_working:
            _checkout_index (index)

    return conflicts

def _checkout_index (index):
    _empty_current_directory ()
    for path, entry in index.items ():
        # Extract oid from new index format
        oid = entry['oid']
        if oid is None:
            # Skip files with no oid (delete_modify, add_add conflicts)
            continue
        os.makedirs (os.path.dirname (f'./{path}'), exist_ok=True)
        with open (path, 'wb') as f:
            f.write (objects.get_object (oid, 'blob'))


def commit (message, author_name=None, author_email=None, author_date=None, allow_merge_parent=True):
    with objects.get_index () as index:
        if objects.has_conflicts (index):
            conflicted_files = objects.get_conflicted_files (index)
            raise objects.ConflictException (
                f"Cannot commit: merge conflicts exist in the following files: {', '.join (conflicted_files)}. "
                "Resolve conflicts and run 'gitforge add' or abort the merge.",
                conflicted_files
            )

    default_name, default_email = objects.get_user_identity ()

    author_name = author_name or default_name
    author_email = author_email or default_email
    author_date = author_date or objects.format_timestamp ()

    committer_name = default_name
    committer_email = default_email
    committer_date = objects.format_timestamp ()

    commit_data = f'tree {write_tree ()}\n'
    HEAD = objects.get_ref ('HEAD').value
    if HEAD:
        commit_data += f'parent {HEAD}\n'

    # Only add MERGE_HEAD as parent if explicitly allowed (disabled for cherry-pick/rebase)
    if allow_merge_parent:
        MERGE_HEAD = objects.get_ref ('MERGE_HEAD').value
        if MERGE_HEAD:
            commit_data += f'parent {MERGE_HEAD}\n'
            objects.delete_ref ('MERGE_HEAD', deref=False)

        ORIG_HEAD = objects.get_ref ('ORIG_HEAD').value
        if ORIG_HEAD:
            objects.delete_ref ('ORIG_HEAD', deref=False)

    commit_data += f'author {author_name} <{author_email}> {author_date}\n'
    commit_data += f'committer {committer_name} <{committer_email}> {committer_date}\n'

    commit_data += '\n'
    commit_data += f'{message}\n'

    oid = objects.hash_object (commit_data.encode (), 'commit')

    objects.update_ref ('HEAD', objects.RefValue (symbolic=False, value=oid))

    return oid

def checkout (name):
    # Check for merge conflicts before checkout
    with objects.get_index () as index:
        if objects.has_conflicts (index):
            conflicted_files = objects.get_conflicted_files (index)
            raise objects.ConflictException (
                f"Cannot checkout: merge conflicts exist in the following files: {', '.join (conflicted_files)}. "
                "Resolve conflicts or abort the merge.",
                conflicted_files
            )

    oid = get_oid (name)
    commit_obj = get_commit (oid)
    read_tree (commit_obj.tree, update_working=True)

    if is_branch (name):    # making HEAD symbolic
        HEAD = objects.RefValue (symbolic=True, value=f'refs/heads/{name}')
    else:                   # making HEAD non-symbolic
        HEAD = objects.RefValue (symbolic=False, value=oid)

    objects.update_ref ('HEAD', HEAD, deref=False)

def reset (oid, soft=False, mixed=False, hard=False):
    # Default to soft if no mode specified
    if not (soft or mixed or hard):
        soft = True

    objects.update_ref ('HEAD', objects.RefValue (symbolic=False, value=oid))

    if mixed or hard:
        # Update index (and working directory if hard) to match the commit's tree
        commit = get_commit (oid)
        read_tree (commit.tree, update_working=hard)

def merge (other):
    # Check if already in a merge state
    existing_merge = objects.get_ref ('MERGE_HEAD').value
    if existing_merge:
        print ('error: You have not concluded your merge (MERGE_HEAD exists).')
        print ('Please commit your changes before you merge, or use "gitforge merge --abort" to abort.')
        return

    HEAD = objects.get_ref ('HEAD').value
    assert HEAD
    merge_base = get_merge_base (other, HEAD)
    c_other = get_commit (other)

    # Handle fast-forward merge
    if merge_base == HEAD:
        read_tree (c_other.tree, update_working=True)
        objects.update_ref ('HEAD', objects.RefValue (symbolic=False, value=other))
        print ('Fast-forward merge, no need to commit')
        return

    # MERGE_HEAD is a intermediate ref created while merging and deleted post merge commit / abort
    objects.update_ref ('MERGE_HEAD', objects.RefValue (symbolic=False, value=other))

    # ORIG_HEAD is a ref to HEAD before merge, to be used during abort command and deleted post merge commit / abort
    objects.update_ref ('ORIG_HEAD', objects.RefValue (symbolic=False, value=HEAD))

    c_base = get_commit (merge_base)
    c_HEAD = get_commit (HEAD)
    conflicts = read_tree_merged (c_base.tree, c_HEAD.tree, c_other.tree, update_working=True)
    if conflicts:
        print('Merge stopped due to conflicts:')
        for p in conflicts:
            print(f'  - {p}')
        print('Resolve the conflict / abort the merge')
    else:
        print ('Merged in working tree\nPlease commit')


def merge_abort ():
    # Check if there's a merge in progress
    MERGE_HEAD = objects.get_ref ('MERGE_HEAD').value
    if not MERGE_HEAD:
        print ('error: There is no merge in progress (MERGE_HEAD missing).')
        return

    # Get ORIG_HEAD to restore to
    ORIG_HEAD = objects.get_ref ('ORIG_HEAD').value
    if not ORIG_HEAD:
        print ('error: Cannot abort merge (ORIG_HEAD missing).')
        return

    # Reset to ORIG_HEAD (hard reset restores HEAD, index, and working tree)
    reset (ORIG_HEAD, hard=True)

    # Clean up merge refs
    objects.delete_ref ('MERGE_HEAD', deref=False)
    objects.delete_ref ('ORIG_HEAD', deref=False)

    print (f'Merge aborted. Restored to {ORIG_HEAD[:10]}')


def get_merge_base(oid1, oid2):
    # Least Common Ancestor - Bidirectional BFS
    if oid1 == oid2:
        return oid1

    visited1, visited2 = {oid1}, {oid2}
    frontier1, frontier2 = deque([oid1]), deque([oid2])

    while frontier1 or frontier2:
        # Expand branch 1
        if frontier1:
            current = frontier1.popleft()
            if current in visited2:
                return current

            for parent in get_commit(current).parents:
                if parent not in visited1:
                    visited1.add(parent)
                    frontier1.append(parent)

        # Expand branch 2
        if frontier2:
            current = frontier2.popleft()
            if current in visited1:
                return current

            for parent in get_commit(current).parents:
                if parent not in visited2:
                    visited2.add(parent)
                    frontier2.append(parent)

    return None



def is_ancestor_of (commit, maybe_ancestor):
    return maybe_ancestor in iter_commits_and_parents ({commit})


def create_tag (name, oid):
    objects.update_ref (f'refs/tags/{name}', objects.RefValue (symbolic=False, value=oid))

def create_branch (name, oid):
    objects.update_ref (f'refs/heads/{name}', objects.RefValue (symbolic=False, value=oid))

def iter_branch_names ():
    for refname, _ in objects.iter_refs ('refs/heads/'):
        yield os.path.relpath (refname, 'refs/heads/')

def is_branch (branch):
    return objects.get_ref (f'refs/heads/{branch}').value is not None

def get_branch_name ():
    HEAD = objects.get_ref ('HEAD', deref=False)
    if not HEAD.symbolic:
        return None
    HEAD = HEAD.value
    assert HEAD.startswith ('refs/heads/')
    return os.path.relpath (HEAD, 'refs/heads')


Commit = namedtuple ('Commit', ['tree', 'parents', 'message', 'author', 'committer'])

def _parse_author_line (value):
    match = re.match (r'(.+) <(.+)> (\d+) ([+-]\d{4})', value)
    if match:
        return Author (
            name=match.group (1),
            email=match.group (2),
            timestamp=int (match.group (3)),
            timezone=match.group (4)
        )
    return None

def get_commit (oid):
    parents = []
    author = None
    committer = None

    commit = objects.get_object (oid, 'commit').decode ()
    lines = iter (commit.splitlines ())
    for line in itertools.takewhile (operator.truth, lines):
        key, value = line.split (' ', 1)
        if key == 'tree':
            tree = value
        elif key == 'parent':
            parents.append (value)
        elif key == 'author':
            author = _parse_author_line (value)
        elif key == 'committer':
            committer = _parse_author_line (value)
        else:
            assert False, f'Unknown field {key}'

    message = '\n'.join (lines)

    if author is None:
        author = Author (name='Unknown', email='unknown', timestamp=0, timezone='+0000')
    if committer is None:
        committer = author

    return Commit (tree=tree, parents=parents, message=message, author=author, committer=committer)

def iter_commits_and_parents (oids):
    # N.B. Must yield the oid before acccessing it (to allow caller to fetch it
    # if needed)
    oids = deque (oids)
    visited = set ()

    while oids:
        oid = oids.popleft ()
        if not oid or oid in visited:
            continue
        visited.add (oid)
        yield oid

        commit = get_commit (oid)
        # Return first parent next
        oids.extendleft (commit.parents[:1])
        # Return other parents later
        oids.extend (commit.parents[1:])

def iter_objects_in_commits (oids):
    # N.B. Must yield the oid before acccessing it (to allow caller to fetch it
    # if needed)

    visited = set ()
    def iter_objects_in_tree (oid):
        visited.add (oid)
        yield oid
        for type_, oid, _ in _iter_tree_entries (oid):
            if oid not in visited:
                if type_ == 'tree':
                    yield from iter_objects_in_tree (oid)
                else:
                    visited.add (oid)
                    yield oid

    for oid in iter_commits_and_parents (oids):
        yield oid
        commit = get_commit (oid)
        if commit.tree not in visited:
            yield from iter_objects_in_tree (commit.tree)

"""
    1. f'{name}' -> Root (.gitforge): This way we can specify refs/tags/mytag
    2. f'refs/{name}' -> .gitforge/refs: This way we can specify tags/mytag
    3. f'refs/tags/{name}' -> .gitforge/refs/tags: This way we can specify mytag
    4. f'refs/heads/{name}' -> .gitforge/refs/heads: ref under refs/heads is a branch
"""
def get_oid (name):
    if name == '@': name = 'HEAD'

    # Name is ref
    refs_to_try = [
        f'{name}',
        f'refs/{name}',
        f'refs/tags/{name}',
        f'refs/heads/{name}',
    ]
    for ref in refs_to_try:
        if objects.get_ref (ref, deref=False).value:
            return objects.get_ref (ref).value

    # Name is SHA1
    is_hex = all (c in string.hexdigits for c in name)
    if len (name) == 40 and is_hex:
        return name

    assert False, f'Unknown name {name}'

def add (filenames):

    def add_file (filename):
        # Normalize path
        filename = os.path.relpath (filename)
        with open (filename, 'rb') as f:
            oid = objects.hash_object (f.read ())
        # Write new index format - adding a file marks it as clear (resolves conflicts)
        index[filename] = {"state": "clear", "oid": oid}

    def add_directory (dirname):
        for root, _, filenames in os.walk (dirname):
            for filename in filenames:
                # Normalize path
                path = os.path.relpath (f'{root}/{filename}')
                if is_ignored (path) or not os.path.isfile (path):
                    continue
                add_file (path)

    with objects.get_index () as index:
        for name in filenames:
            if os.path.isfile (name):
                add_file (name)
            elif os.path.isdir (name):
                add_directory (name)
            else:
                # File doesn't exist - if it's in the index, remove it (stage deletion)
                name = os.path.relpath (name)
                if name in index:
                    del index[name]

def is_ignored (path):
    return '.gitforge' in path.split ('/')


def _check_clean_state():
    """Check that working tree and index are clean."""
    HEAD = objects.get_ref('HEAD').value
    if not HEAD:
        return True, None

    head_tree = get_tree(get_commit(HEAD).tree)
    index_tree = get_index_tree()
    working_tree = get_working_tree()

    # Check index vs HEAD (staged changes)
    for path, o_head, o_index in diff_engine.compare_trees(head_tree, index_tree):
        if o_head != o_index:
            return False, "staged changes exist"

    # Check working tree vs index (unstaged changes)
    for path, o_index, o_work in diff_engine.compare_trees(index_tree, working_tree):
        if o_index != o_work:
            return False, "unstaged changes exist"

    return True, None


def cherry_pick(commit_oid):
    """Apply a single commit onto current HEAD."""
    # Check for in-progress merge
    if objects.get_ref('MERGE_HEAD').value:
        print('error: A merge is in progress (MERGE_HEAD exists).')
        print('Complete the merge with "gitforge commit" or abort with "gitforge merge --abort".')
        return

    # Check for in-progress rebase
    if objects.get_rebase_state():
        print('error: A rebase is in progress.')
        print('Complete the rebase or abort it before cherry-picking.')
        return

    # Check if cherry-pick already in progress
    if objects.get_ref('CHERRY_PICK_HEAD').value:
        print('error: Cherry-pick already in progress.')
        print('Use "gitforge cherry-pick --continue" or "gitforge cherry-pick --abort".')
        return

    # Check for conflicts
    with objects.get_index() as index:
        if objects.has_conflicts(index):
            conflicted = objects.get_conflicted_files(index)
            raise objects.ConflictException(
                f"Cannot cherry-pick: conflicts exist in: {', '.join(conflicted)}",
                conflicted
            )

    # Check for dirty working tree / index
    is_clean, reason = _check_clean_state()
    if not is_clean:
        print(f'error: Cannot cherry-pick: {reason}.')
        print('Please commit or stash them.')
        return

    c = get_commit(commit_oid)

    # Reject root commits
    if not c.parents:
        print('error: Cannot cherry-pick root commit (no parent for base).')
        return

    # Reject merge commits
    if len(c.parents) > 1:
        print(f'error: {commit_oid[:10]} is a merge commit.')
        print('Cherry-picking merge commits is not supported.')
        return

    # Save state for abort
    HEAD = objects.get_ref('HEAD').value
    objects.update_ref('ORIG_HEAD', objects.RefValue(symbolic=False, value=HEAD))

    # Use shared apply logic
    success, new_oid, conflicts = _apply_commit(commit_oid)

    if conflicts:
        # Save cherry-pick state
        objects.update_ref('CHERRY_PICK_HEAD', objects.RefValue(symbolic=False, value=commit_oid))

        print(f'CONFLICT during cherry-pick {commit_oid[:10]}')
        for p in conflicts:
            print(f'  - {p}')
        print('\nResolve conflicts, then run:')
        print('  gitforge add <files>')
        print('  gitforge cherry-pick --continue')
        print('\nOr abort with:')
        print('  gitforge cherry-pick --abort')
        return

    if new_oid is None:
        # Empty commit - already restored by _apply_commit
        print(f'Skipping: {commit_oid[:10]} (empty cherry-pick)')
        _cherry_pick_cleanup()
        return

    _cherry_pick_cleanup()
    print(f'Cherry-picked {commit_oid[:10]} -> {new_oid[:10]}')


def cherry_pick_continue():
    """Continue cherry-pick after conflict resolution."""
    cherry_pick_head = objects.get_ref('CHERRY_PICK_HEAD').value
    if not cherry_pick_head:
        print('error: No cherry-pick in progress.')
        return

    # Verify conflicts resolved
    with objects.get_index() as index:
        if objects.has_conflicts(index):
            conflicted = objects.get_conflicted_files(index)
            print(f'error: Conflicts remain in: {", ".join(conflicted)}')
            print('Run "gitforge add <file>" after resolving.')
            return

    # Use shared finish logic
    new_oid = _finish_apply(cherry_pick_head)

    if new_oid is None:
        print(f'Skipping: {cherry_pick_head[:10]} (empty cherry-pick)')
    else:
        print(f'Cherry-picked {cherry_pick_head[:10]} -> {new_oid[:10]}')

    _cherry_pick_cleanup()


def cherry_pick_abort():
    """Abort cherry-pick and restore original state."""
    cherry_pick_head = objects.get_ref('CHERRY_PICK_HEAD').value
    if not cherry_pick_head:
        print('error: No cherry-pick in progress.')
        return

    orig_head = objects.get_ref('ORIG_HEAD').value
    if not orig_head:
        print('error: Cannot abort (ORIG_HEAD missing).')
        return

    reset(orig_head, hard=True)
    _cherry_pick_cleanup()
    print(f'Cherry-pick aborted. Restored to {orig_head[:10]}')


def _cherry_pick_cleanup():
    """Clean up cherry-pick state."""
    if objects.get_ref('CHERRY_PICK_HEAD').value:
        objects.delete_ref('CHERRY_PICK_HEAD', deref=False)
    if objects.get_ref('ORIG_HEAD').value:
        objects.delete_ref('ORIG_HEAD', deref=False)


def get_commits_to_replay(upstream_oid, head_oid):
    """Get commits from HEAD back to upstream (exclusive) following first-parent only."""
    merge_base = get_merge_base(upstream_oid, head_oid)
    commits = []
    cur = head_oid

    while cur and cur != merge_base:
        commits.append(cur)
        c = get_commit(cur)
        cur = c.parents[0] if c.parents else None

    return list(reversed(commits))


def _finish_apply(commit_oid):
    """
    Finish applying a commit after conflicts are resolved (shared by cherry-pick and rebase --continue).
    
    Checks for empty commit and creates new commit preserving original author.
    
    Returns:
        new_oid: str|None - The new commit OID, or None if empty (skipped)
    """
    c = get_commit(commit_oid)

    # Check for empty commit
    new_tree_oid = write_tree()
    head_commit = get_commit(objects.get_ref('HEAD').value)
    if new_tree_oid == head_commit.tree:
        # Restore working directory to HEAD before skipping
        read_tree(get_commit(objects.get_ref('HEAD').value).tree, update_working=True)
        return None  # Skipped (empty)

    # Create commit preserving author
    new_oid = commit(
        message=c.message,
        author_name=c.author.name,
        author_email=c.author.email,
        author_date=f'{c.author.timestamp} {c.author.timezone}',
        allow_merge_parent=False
    )

    return new_oid


def _apply_commit(commit_oid):
    """
    Apply a single commit onto current HEAD (shared by cherry-pick and rebase).
    
    Returns:
        (success: bool, new_oid: str|None, conflicts: list|None)
        - success=False, conflicts=list  → merge conflicts occurred
        - success=True, new_oid=str      → commit created
        - success=True, new_oid=None     → empty commit, skipped
    """
    c = get_commit(commit_oid)

    # Get trees for 3-way merge
    base_tree = get_commit(c.parents[0]).tree if c.parents else None
    head_tree = get_commit(objects.get_ref('HEAD').value).tree
    other_tree = c.tree

    # Merge trees
    conflicts = read_tree_merged(base_tree, head_tree, other_tree, update_working=True)

    if conflicts:
        return False, None, conflicts

    # Use shared finish logic
    new_oid = _finish_apply(commit_oid)

    return True, new_oid, None


def rebase(upstream):
    """Start rebase onto upstream."""
    # Check for in-progress merge
    if objects.get_ref('MERGE_HEAD').value:
        print('error: A merge is in progress (MERGE_HEAD exists).')
        print('Complete the merge with "gitforge commit" or abort with "gitforge merge --abort".')
        return

    # Check if rebase already in progress
    if objects.get_rebase_state():
        print('error: A rebase is already in progress.')
        print('Use "gitforge rebase --continue" or "gitforge rebase --abort".')
        return

    # Check for in-progress cherry-pick
    if objects.get_ref('CHERRY_PICK_HEAD').value:
        print('error: A cherry-pick is in progress.')
        print('Complete the cherry-pick or abort it before rebasing.')
        return

    # Check for conflicts
    with objects.get_index() as index:
        if objects.has_conflicts(index):
            conflicted = objects.get_conflicted_files(index)
            raise objects.ConflictException(
                f"Cannot rebase: conflicts exist in: {', '.join(conflicted)}",
                conflicted
            )

    # Check for dirty working tree / index
    is_clean, reason = _check_clean_state()
    if not is_clean:
        print(f'error: Cannot rebase: {reason}.')
        print('Please commit or stash them.')
        return

    HEAD = objects.get_ref('HEAD').value
    upstream_oid = get_oid(upstream)

    # Check upstream is ancestor of HEAD
    merge_base = get_merge_base(upstream_oid, HEAD)
    if merge_base is None:
        print('error: upstream has no common history with HEAD.')
        return
    elif merge_base == upstream_oid:
        print('Branch is already up to date')
        return

    # Identify commits to replay (first-parent only)
    commits_to_replay = get_commits_to_replay(upstream_oid, HEAD)

    if not commits_to_replay:
        print('Current branch is up to date.')
        return

    # Check for merge commits
    for commit_oid in commits_to_replay:
        c = get_commit(commit_oid)
        if len(c.parents) > 1:
            print(f'error: Cannot rebase: commit {commit_oid[:10]} is a merge commit.')
            print('Rebase does not support merge commits.')
            return

    # Save rebase state
    state = {
        'orig_head': HEAD,
        'upstream': upstream_oid,
        'commits': commits_to_replay,
        'current_index': 0
    }
    objects.save_rebase_state(state)
    objects.update_ref('ORIG_HEAD', objects.RefValue(symbolic=False, value=HEAD))

    print(f'Rebasing {len(commits_to_replay)} commit(s) onto {upstream_oid[:10]}')

    # Hard reset to upstream
    reset(upstream_oid, hard=True)

    # Start replay loop
    _rebase_replay_loop()


def _rebase_replay_loop():
    """Replay commits one by one using shared _apply_commit()."""
    state = objects.get_rebase_state()
    if not state:
        return

    commits = state['commits']
    idx = state['current_index']

    while idx < len(commits):
        commit_oid = commits[idx]

        # Use shared apply logic
        success, new_oid, conflicts = _apply_commit(commit_oid)

        if conflicts:
            # Save state and stop
            state['current_index'] = idx
            objects.save_rebase_state(state)

            print(f'CONFLICT applying {commit_oid[:10]}')
            for p in conflicts:
                print(f'  - {p}')
            print('\nResolve conflicts, then run "gitforge add <files>"')
            print('and "gitforge rebase --continue"')
            print('Or run "gitforge rebase --abort" to abort.')
            return

        if new_oid:
            print(f'Applied: {commit_oid[:10]} -> {new_oid[:10]}')
        else:
            print(f'Skipping: {commit_oid[:10]} (empty)')

        idx += 1
        state['current_index'] = idx
        objects.save_rebase_state(state)

    # All done - cleanup
    _rebase_cleanup()
    print('\nRebase complete.')


def rebase_continue():
    """Continue rebase after conflict resolution."""
    state = objects.get_rebase_state()
    if not state:
        print('error: No rebase in progress.')
        return

    # Verify conflicts resolved
    with objects.get_index() as index:
        if objects.has_conflicts(index):
            conflicted = objects.get_conflicted_files(index)
            print(f'error: Conflicts remain in: {", ".join(conflicted)}')
            print('Run "gitforge add <file>" after resolving.')
            return

    # Use shared finish logic
    commits = state['commits']
    idx = state['current_index']
    commit_oid = commits[idx]

    new_oid = _finish_apply(commit_oid)

    if new_oid is None:
        print(f'Skipping: {commit_oid[:10]} (empty)')
    else:
        print(f'Applied: {commit_oid[:10]} -> {new_oid[:10]}')

    # Advance and continue
    state['current_index'] = idx + 1
    objects.save_rebase_state(state)
    _rebase_replay_loop()


def rebase_abort():
    """Abort rebase and restore original state."""
    state = objects.get_rebase_state()
    if not state:
        print('error: No rebase in progress.')
        return

    orig_head = state['orig_head']

    # Hard reset to ORIG_HEAD
    reset(orig_head, hard=True)

    _rebase_cleanup()
    print(f'Rebase aborted. Restored to {orig_head[:10]}')


def _rebase_cleanup():
    """Clean up all rebase state."""
    objects.delete_rebase_state()

    if objects.get_ref('ORIG_HEAD').value:
        objects.delete_ref('ORIG_HEAD', deref=False)


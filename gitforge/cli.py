import argparse
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone, timedelta

from . import repository
from . import objects
from . import diff_engine
from . import remotes

def main ():
    with objects.change_git_dir ('.'):
        args = parse_args ()
        args.func (args)

def parse_args ():
    parser = argparse.ArgumentParser ()

    oid = repository.get_oid

    commands = parser.add_subparsers (dest='command')
    commands.required = True

    init_parser = commands.add_parser ('init')
    init_parser.set_defaults (func=init)

    hash_object_parser = commands.add_parser ('hash-object')
    hash_object_parser.set_defaults (func=hash_object)
    hash_object_parser.add_argument ('file')

    cat_file_parser = commands.add_parser ('cat-file')
    cat_file_parser.set_defaults (func=cat_file)
    cat_file_parser.add_argument ('object', type=oid)

    write_tree_parser = commands.add_parser ('write-tree')
    write_tree_parser.set_defaults (func=write_tree)

    read_tree_parser = commands.add_parser ('read-tree')
    read_tree_parser.set_defaults (func=read_tree)
    read_tree_parser.add_argument ('tree', type=oid)

    commit_parser = commands.add_parser ('commit')
    commit_parser.set_defaults (func=commit)
    commit_parser.add_argument ('-m', '--message', required=True)

    log_parser = commands.add_parser ('log')
    log_parser.set_defaults (func=log)
    log_parser.add_argument ('oid', default='@', type=oid, nargs='?')

    show_parser = commands.add_parser ('show')
    show_parser.set_defaults (func=show)
    show_parser.add_argument ('oid', default='@', type=oid, nargs='?')

    diff_parser = commands.add_parser ('diff')
    diff_parser.set_defaults (func=_diff)
    diff_parser.add_argument ('--cached', action='store_true')
    diff_parser.add_argument ('commit', nargs='?')

    checkout_parser = commands.add_parser ('checkout')
    checkout_parser.set_defaults (func=checkout)
    checkout_parser.add_argument ('commit')

    tag_parser = commands.add_parser ('tag')
    tag_parser.set_defaults (func=tag)
    tag_parser.add_argument ('name')
    tag_parser.add_argument ('oid', default='@', type=oid, nargs='?')

    branch_parser = commands.add_parser ('branch')
    branch_parser.set_defaults (func=branch)
    branch_parser.add_argument ('name', nargs='?')
    branch_parser.add_argument ('start_point', default='@', type=oid, nargs='?')

    k_parser = commands.add_parser ('k')
    k_parser.set_defaults (func=k)

    status_parser = commands.add_parser ('status')
    status_parser.set_defaults (func=status)

    reset_parser = commands.add_parser ('reset')
    reset_parser.set_defaults (func=reset)
    reset_parser.add_argument ('commit', type=oid)
    reset_mode = reset_parser.add_mutually_exclusive_group ()
    reset_mode.add_argument ('--soft', action='store_true', help='Only move HEAD (default)')
    reset_mode.add_argument ('--mixed', action='store_true', help='Move HEAD and update index')
    reset_mode.add_argument ('--hard', action='store_true', help='Move HEAD, update index and working directory')

    merge_parser = commands.add_parser ('merge')
    merge_parser.set_defaults (func=merge)
    merge_parser.add_argument ('commit', nargs='?', type=oid)
    merge_parser.add_argument ('--abort', action='store_true', help='Abort the current merge and restore to ORIG_HEAD')

    merge_base_parser = commands.add_parser ('merge-base')
    merge_base_parser.set_defaults (func=merge_base)
    merge_base_parser.add_argument ('commit1', type=oid)
    merge_base_parser.add_argument ('commit2', type=oid)

    cherry_pick_parser = commands.add_parser ('cherry-pick')
    cherry_pick_parser.set_defaults (func=cherry_pick)
    cherry_pick_parser.add_argument ('commit', nargs='?', type=oid)
    cherry_pick_parser.add_argument ('--continue', dest='continue_cherry_pick', action='store_true',
                                     help='Continue after resolving conflicts')
    cherry_pick_parser.add_argument ('--abort', action='store_true',
                                     help='Abort and restore original state')

    rebase_parser = commands.add_parser ('rebase')
    rebase_parser.set_defaults (func=rebase)
    rebase_parser.add_argument ('upstream', nargs='?', type=oid)
    rebase_parser.add_argument ('--continue', dest='continue_rebase', action='store_true',
                                help='Continue after resolving conflicts')
    rebase_parser.add_argument ('--abort', action='store_true',
                                help='Abort and restore original state')

    fetch_parser = commands.add_parser ('fetch')
    fetch_parser.set_defaults (func=fetch)
    fetch_parser.add_argument ('remote')

    push_parser = commands.add_parser ('push')
    push_parser.set_defaults (func=push)
    push_parser.add_argument ('remote')
    push_parser.add_argument ('branch')

    add_parser = commands.add_parser ('add')
    add_parser.set_defaults (func=add)
    add_parser.add_argument ('files', nargs='+')

    config_parser = commands.add_parser ('config')
    config_parser.set_defaults (func=config)
    config_parser.add_argument ('key', nargs='?')
    config_parser.add_argument ('value', nargs='?')

    return parser.parse_args ()


def init (args):
    repository.init ()
    print (f'Initialized empty gitforge repository in {os.getcwd()}/{objects.GIT_DIR}')

"""
    flow of the command `hash-object` is:
    
    Get the path of the file to store.
    Read the file.
    Hash the content of the file using SHA-1.
    Store the file under ".gitforge/objects/{the SHA-1 hash}".
"""
def hash_object (args):
    with open (args.file, 'rb') as f:
        print (objects.hash_object (f.read ()))

def cat_file (args):
    sys.stdout.flush ()
    sys.stdout.buffer.write (objects.get_object (args.object, expected=None))

def write_tree (args):
    print (repository.write_tree ())

def read_tree (args):
    repository.read_tree (args.tree)

def commit (args):
    try:
        print (repository.commit (args.message))
    except objects.ConflictException as e:
        print (f'error: {e}', file=sys.stderr)
        sys.exit (1)

def _format_commit_date (timestamp, tz_str):
    sign = 1 if tz_str[0] == '+' else -1
    hours = int (tz_str[1:3])
    minutes = int (tz_str[3:5])
    offset = timedelta (hours=sign * hours, minutes=sign * minutes)
    tz = timezone (offset)
    dt = datetime.fromtimestamp (timestamp, tz=tz)
    return dt.strftime ('%a %b %d %H:%M:%S %Y %z')

def _print_commit (oid, commit, refs=None):
    refs_str = f' ({", ".join (refs)})' if refs else ''
    print (f'commit {oid}{refs_str}')

    if commit.author:
        print (f'Author:    {commit.author.name} <{commit.author.email}>')
        author_date = _format_commit_date (commit.author.timestamp, commit.author.timezone)
        print (f'AuthorDate: {author_date}')

    if commit.committer:
        print (f'Committer:    {commit.committer.name} <{commit.committer.email}>')
        commit_date = _format_commit_date (commit.committer.timestamp, commit.committer.timezone)
        print (f'CommitDate: {commit_date}')

    print ()
    print (textwrap.indent (commit.message, '    '))
    print ()

def log (args):
    refs = {}
    for refname, ref in objects.iter_refs ():
        refs.setdefault (ref.value, []).append (refname)

    for oid in repository.iter_commits_and_parents ({args.oid}):
        commit = repository.get_commit (oid)
        _print_commit (oid, commit, refs.get (oid))

def show (args):
    if not args.oid:
        return
    commit = repository.get_commit (args.oid)
    parent_tree = None
    if commit.parents:
        parent_tree = repository.get_commit (commit.parents[0]).tree

    _print_commit (args.oid, commit)
    result = diff_engine.diff_trees (
        repository.get_tree (parent_tree), repository.get_tree (commit.tree))
    sys.stdout.flush ()
    sys.stdout.buffer.write (result)

"""
operation of diff :
1. If no arguments are provided, diff from the index to the working directory. This way you can quickly see unstaged changes.
2. If --cached was provided, diff from HEAD to the index. This way you can quickly see which changes are going to be commited.
3. If a specific commit was provided, diff from the commit to the index or working directory (depending on whether --cached was provided).
"""
def _diff (args):
    oid = args.commit and repository.get_oid (args.commit)

    if args.commit:
        # If a commit was provided explicitly, diff from it
        tree_from = repository.get_tree (oid and repository.get_commit (oid).tree)

    if args.cached:
        tree_to = repository.get_index_tree ()
        if not args.commit:
            # If no commit was provided, diff from HEAD
            oid = repository.get_oid ('@')
            tree_from = repository.get_tree (oid and repository.get_commit (oid).tree)
    else:
        tree_to = repository.get_working_tree ()
        if not args.commit:
            # If no commit was provided, diff from index
            tree_from = repository.get_index_tree ()

    result = diff_engine.diff_trees (tree_from, tree_to)
    sys.stdout.flush ()
    sys.stdout.buffer.write (result)


def checkout (args):
    try:
        repository.checkout (args.commit)
    except objects.ConflictException as e:
        print (f'error: {e}', file=sys.stderr)
        sys.exit (1)

def tag (args):
    repository.create_tag (args.name, args.oid)

def branch (args):
    if not args.name:
        current = repository.get_branch_name ()
        for branch in repository.iter_branch_names ():
            prefix = '*' if branch == current else ' '
            print (f'{prefix} {branch}')
    else:
        repository.create_branch (args.name, args.start_point)
        print (f'Branch {args.name} created at {args.start_point[:10]}')

def k (args):
    dot = 'digraph commits {\n'

    oids = set ()
    for refname, ref in objects.iter_refs (deref=False):
        dot += f'"{refname}" [shape=note]\n'
        dot += f'"{refname}" -> "{ref.value}"\n'
        if not ref.symbolic:
            oids.add (ref.value)

    for oid in repository.iter_commits_and_parents (oids):
        commit = repository.get_commit (oid)
        dot += f'"{oid}" [shape=box style=filled label="{oid[:10]}"]\n'
        for parent in commit.parents:
            dot += f'"{oid}" -> "{parent}"\n'

    dot += '}'
    print (dot)

    # Generate PNG and open it
    import tempfile
    with tempfile.NamedTemporaryFile (suffix='.png', delete=False) as f:
        output_path = f.name

    with subprocess.Popen (
            ['dot', '-Tpng', '-o', output_path],
            stdin=subprocess.PIPE) as proc:
        proc.communicate (dot.encode ())

    # Open the image with default viewer
    subprocess.run (['open', output_path])

def status (args):
    HEAD = repository.get_oid ('@')
    branch = repository.get_branch_name ()
    if branch:
        print (f'On branch {branch}')
    else:
        print (f'HEAD detached at {HEAD[:10]}')

    MERGE_HEAD = objects.get_ref ('MERGE_HEAD').value
    if MERGE_HEAD:
        print (f'Merging with {MERGE_HEAD[:10]}')

    # Check for rebase in progress
    rebase_state = objects.get_rebase_state ()
    if rebase_state:
        idx = rebase_state['current_index']
        total = len (rebase_state['commits'])
        print (f'\nRebase in progress onto {rebase_state["upstream"][:10]}')
        if idx < total:
            current = rebase_state['commits'][idx]
            print (f'  Applying: {current[:10]} ({idx + 1}/{total})')
        print ('  (use "gitforge rebase --continue" after resolving conflicts)')
        print ('  (use "gitforge rebase --abort" to abort)')

    # Check for cherry-pick in progress
    CHERRY_PICK_HEAD = objects.get_ref ('CHERRY_PICK_HEAD').value
    if CHERRY_PICK_HEAD:
        print (f'\nCherry-pick in progress: {CHERRY_PICK_HEAD[:10]}')
        print ('  (use "gitforge cherry-pick --continue" after resolving conflicts)')
        print ('  (use "gitforge cherry-pick --abort" to abort)')

    # Check for and display conflicted files
    conflicted_paths = set ()
    with objects.get_index () as index:
        if objects.has_conflicts (index):
            conflicted_paths = set (objects.get_conflicted_files (index))
            print ('\nUnmerged paths (fix conflicts and run "gitforge add"):')
            for path in conflicted_paths:
                conflict_type = index[path].get ('type', 'unknown')
                if conflict_type == "add_add":
                    print (f'    both added:                      {path}')
                elif conflict_type == "current_delete_target_modify":
                    print (f'    current: deleted, target: modified   {path}')
                elif conflict_type == "current_modify_target_delete":
                    print (f'    current: modified, target: deleted   {path}')
                elif conflict_type == "content_conflict":
                    print (f'    both modified:                   {path}')
                else:
                    print (f'    conflict:                        {path} ({conflict_type})')
            print ()

    # To display changed files that are going to be committed, we will compare index to HEAD.
    # Exclude conflicted files as they are already shown in "Unmerged paths"
    print ('\nChanges to be committed:\n')
    HEAD_tree = HEAD and repository.get_commit (HEAD).tree
    for path, action in diff_engine.iter_changed_files (repository.get_tree (HEAD_tree),
                                                 repository.get_index_tree ()):
        if path not in conflicted_paths:
            print (f'{action:>12}: {path}')

    # To display changed files that aren't going to be committed we will compare the index to the working tree.
    # Exclude conflicted files as they are already shown in "Unmerged paths"
    print ('\nChanges not staged for commit:\n')
    for path, action in diff_engine.iter_changed_files (repository.get_index_tree (),
                                                 repository.get_working_tree ()):
        if path not in conflicted_paths:
            print (f'{action:>12}: {path}')


def reset (args):
    repository.reset (args.commit, soft=args.soft, mixed=args.mixed, hard=args.hard)

def merge (args):
    if args.abort:
        repository.merge_abort ()
    elif args.commit:
        repository.merge (args.commit)
    else :
        print ('error: merge requires a commit argument (or --abort)', file=sys.stderr)
        sys.exit (1)

def merge_base (args):
    print (repository.get_merge_base (args.commit1, args.commit2))

def cherry_pick (args):
    if args.abort:
        repository.cherry_pick_abort ()
    elif args.continue_cherry_pick:
        repository.cherry_pick_continue ()
    elif args.commit:
        try:
            repository.cherry_pick (args.commit)
        except objects.ConflictException as e:
            print (f'error: {e}', file=sys.stderr)
            sys.exit (1)
    else:
        print ('error: cherry-pick requires commit (or --continue/--abort)', file=sys.stderr)
        sys.exit (1)

def rebase (args):
    if args.abort:
        repository.rebase_abort ()
    elif args.continue_rebase:
        repository.rebase_continue ()
    elif args.upstream:
        try:
            repository.rebase (args.upstream)
        except objects.ConflictException as e:
            print (f'error: {e}', file=sys.stderr)
            sys.exit (1)
    else:
        print ('error: rebase requires upstream (or --continue/--abort)', file=sys.stderr)
        sys.exit (1)

def fetch (args):
    remotes.fetch (args.remote)

def push (args):
    remotes.push (args.remote, f'refs/heads/{args.branch}')

def add (args):
    repository.add (args.files)

def config (args):
    if args.key and args.value:
        objects.set_config (args.key, args.value)
        print (f'{args.key} = {args.value}')
    elif args.key:
        cfg = objects.get_config ()
        keys = args.key.split ('.')
        value = cfg
        for k in keys:
            if isinstance (value, dict):
                value = value.get (k)
            else:
                value = None
                break
        if value is not None:
            print (value)
        else:
            print (f'{args.key} not set')
    else:
        cfg = objects.get_config ()
        print (json.dumps (cfg, indent=2))

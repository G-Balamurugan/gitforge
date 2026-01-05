import subprocess

from collections import defaultdict
from tempfile import NamedTemporaryFile as Temp

from . import objects


def compare_trees (*trees):
    entries = defaultdict (lambda: [None] * len (trees))
    for i, tree in enumerate (trees):
        for path, oid in tree.items ():
            entries[path][i] = oid

    for path, oids in entries.items ():
        yield (path, *oids)

def iter_changed_files (t_from, t_to):
    for path, o_from, o_to in compare_trees (t_from, t_to):
        if o_from != o_to:
            action = ('new file' if not o_from else
                      'deleted' if not o_to else
                      'modified')
            yield path, action

def diff_trees (t_from, t_to):
    output = b''
    for path, o_from, o_to in compare_trees (t_from, t_to):
        if o_from != o_to:
            # Compute the diff between current and parent file object's content
            output += diff_blobs (o_from, o_to, path)
    return output


def diff_blobs (o_from, o_to, path='blob'):
    with Temp () as f_from, Temp () as f_to:
        for oid, f in ((o_from, f_from), (o_to, f_to)):
            if oid:
                f.write (objects.get_object (oid))
                f.flush ()

        with subprocess.Popen (
                ['diff', '--unified', '--show-c-function',
                 '--label', f'a/{path}', f_from.name,
                 '--label', f'b/{path}', f_to.name],
                stdout=subprocess.PIPE) as proc:
            output, _ = proc.communicate ()

        return output

def merge_trees (t_base, t_HEAD, t_other):
    """
    Perform a 3-way merge of trees.
    
    Returns:
        (tree, conflicts): merged tree dict and list of conflicted paths
        
    Conflict types:
        - content_conflict: Both sides modified the same file differently
        - add_add: Both sides added the same file with different content
        - current_delete_target_modify: Current (HEAD) deleted, target modified
        - current_modify_target_delete: Target deleted, current (HEAD) modified
    """
    tree = {}
    conflicts = []

    for path, o_base, o_HEAD, o_other in compare_trees (t_base, t_HEAD, t_other):
        # ---------- BOTH DELETED ----------
        if o_HEAD is None and o_other is None:
            continue

        # ---------- ONLY ONE SIDE ADDED (no conflict) ----------
        if o_base is None and ((o_HEAD is None) != (o_other is None)):
            tree[path] = {"state": "clear", "oid": o_HEAD or o_other}
            continue

        # ---------- DELETE ACCEPTED (no conflict) ----------
        if o_base and o_HEAD is None and o_other == o_base:
            continue  # HEAD deleted, other unchanged - accept deletion
        if o_base and o_other is None and o_HEAD == o_base:
            continue  # Other deleted, HEAD unchanged - accept deletion

        # ---------- ONLY ONE SIDE MODIFIED (no conflict) ----------
        if o_base and o_HEAD and o_other:
            if o_HEAD == o_base and o_other != o_base:
                # HEAD unchanged, other modified - take other's version
                tree[path] = {"state": "clear", "oid": o_other}
                continue
            elif o_other == o_base and o_HEAD != o_base:
                # Other unchanged, HEAD modified - take HEAD's version
                tree[path] = {"state": "clear", "oid": o_HEAD}
                continue
            elif o_HEAD == o_other:
                # Both made the same change - take either (no conflict)
                tree[path] = {"state": "clear", "oid": o_HEAD}
                continue

        # ---------- ADD/ADD with identical content (no conflict) ----------
        if o_base is None and o_HEAD and o_other and o_HEAD == o_other:
            tree[path] = {"state": "clear", "oid": o_HEAD}
            continue

        # ---------- DETERMINE CONFLICT TYPE ----------
        # At this point, we have a conflict that needs merge_blobs
        if o_base is None and o_HEAD and o_other:
            conflict_type = "add_add"
        elif o_base and o_HEAD is None and o_other:
            # Current (HEAD) deleted, target modified
            conflict_type = "current_delete_target_modify"
        elif o_base and o_HEAD and o_other is None:
            # Current (HEAD) modified, target deleted
            conflict_type = "current_modify_target_delete"
        else:
            conflict_type = "content_conflict"

        # ---------- UNIFIED MERGE (diff3) ----------
        # This handles ALL conflict types: add_add, delete_modify_*, content_conflict
        merged_content, has_conflict = merge_blobs (o_base, o_HEAD, o_other)
        merged_oid = objects.hash_object (merged_content)

        if has_conflict:
            tree[path] = {
                "state": "conflict",
                "type": conflict_type,
                "oid": merged_oid,  # Merged content with conflict markers
                "base": o_base,
                "head": o_HEAD,
                "other": o_other
            }
            conflicts.append(path)
        else:
            tree[path] = {
                "state": "clear",
                "oid": merged_oid
            }

    return tree, conflicts


def merge_blobs (o_base, o_HEAD, o_other):
    with Temp () as f_base, Temp () as f_HEAD, Temp () as f_other:

        # Write blobs to files
        for oid, f in ((o_base, f_base), (o_HEAD, f_HEAD), (o_other, f_other)):
            if oid:
                f.write (objects.get_object (oid))
                f.flush ()

        with subprocess.Popen (
                ['diff3', '-m',
                 '-L', 'HEAD', f_HEAD.name,
                 '-L', 'BASE', f_base.name,
                 '-L', 'MERGE_HEAD', f_other.name,
                 ], stdout=subprocess.PIPE) as proc:
            output, _ = proc.communicate ()
            # diff3 returns 0 for clean merge, 1 for conflicts
            assert proc.returncode in (0, 1)
            has_conflict = (proc.returncode == 1)

        return output, has_conflict


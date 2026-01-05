import os

from . import repository
from . import objects

REMOTE_REFS_BASE = 'refs/heads/'
LOCAL_REFS_BASE = 'refs/remote'

def fetch (remote_path):
    # Get refs from server
    refs = _get_remote_refs (remote_path, REMOTE_REFS_BASE)

    # Fetch missing objects by iterating and fetching on demand
    for oid in repository.iter_objects_in_commits (refs.values ()):
        objects.fetch_object_if_missing (oid, remote_path)

    # Update local refs to match server
    for remote_name, value in refs.items ():
        refname = os.path.relpath (remote_name, REMOTE_REFS_BASE)
        objects.update_ref (f'{LOCAL_REFS_BASE}/{refname}',
                         objects.RefValue (symbolic=False, value=value))

def push (remote_path, refname):
    """
    Inorder to avoid over writing of remote repo, allow push only if :
    1. The ref that we're pushing doesn't exist yet on the remote. 
        It means that it's a new branch and there is no risk of overwriting other's work.
    2. If the remote ref does exist, it must point to a commit that is an ancestor of the pushed ref. 
        This ancestry means that the local commit is based on the remote commit, 
        which means that the remote commit not getting overwritten, since it's part of the history of the newly pushed commit.
    """
    # Get refs data
    remote_refs = _get_remote_refs (remote_path)
    remote_ref = remote_refs.get (refname)
    local_ref = objects.get_ref (refname).value
    if not local_ref:
        raise ValueError (f"Local ref '{refname}' does not exist. Cannot push a branch that doesn't exist locally.")

    # Don't allow force push
    if remote_ref and not repository.is_ancestor_of (local_ref, remote_ref):
        raise ValueError (f"Push rejected: remote ref '{refname}' is not an ancestor of local ref. This would overwrite remote commits.")

    # Compute which objects the server doesn't have
    known_remote_refs = filter (objects.object_exists, remote_refs.values ())
    remote_objects = set (repository.iter_objects_in_commits (known_remote_refs))
    local_objects = set (repository.iter_objects_in_commits ({local_ref}))
    objects_to_push = local_objects - remote_objects

    # Push missing objects
    for oid in objects_to_push:
        objects.push_object (oid, remote_path)

    # Update server ref to our value
    with objects.change_git_dir (remote_path):
        objects.update_ref (refname,
                         objects.RefValue (symbolic=False, value=local_ref))

def _get_remote_refs (remote_path, prefix=''):
    with objects.change_git_dir (remote_path):
        return {refname: ref.value for refname, ref in objects.iter_refs (prefix)}


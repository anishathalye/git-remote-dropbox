from git_remote_dropbox.constants import DEVNULL

import subprocess
import zlib


def command_output(*args, **kwargs):
    """
    Return the result of running a git command.
    """
    args = ('git',) + args
    output = subprocess.check_output(args, stderr=DEVNULL)
    if kwargs.get('decode', True):
        output = output.decode('utf8')
    if kwargs.get('strip', True):
        output = output.strip()
    return output


def command_ok(*args):
    """
    Return whether a git command runs successfully.
    """
    args = ('git',) + args
    return subprocess.call(args, stdout=DEVNULL, stderr=DEVNULL) == 0


def is_ancestor(ancestor, ref):
    """
    Return whether ancestor is an ancestor of ref.

    This returns true when it is possible to fast-forward from ancestor to ref.
    """
    return command_ok('merge-base', '--is-ancestor', ancestor, ref)


def object_exists(sha):
    """
    Return whether the object exists in the repository.
    """
    return command_ok('cat-file', '-t', sha)


def history_exists(sha):
    """
    Return whether the object, along with its history, exists in the
    repository.
    """
    return command_ok('rev-list', '--objects', sha)


def ref_value(ref):
    """
    Return the hash of the ref.
    """
    return command_output('rev-parse', ref)


def symbolic_ref_value(name):
    """
    Return the branch head to which the symbolic ref refers.
    """
    return command_output('symbolic-ref', name)


def object_kind(sha):
    """
    Return the type of the object.
    """
    return command_output('cat-file', '-t', sha)


def object_data(sha, kind=None):
    """
    Return the contents of the object.

    If kind is None, return a pretty-printed representation of the object.
    """
    if kind is not None:
        return command_output('cat-file', kind, sha, decode=False, strip=False)
    else:
        return command_output('cat-file', '-p', sha, decode=False, strip=False)


def encode_object(sha):
    """
    Return the encoded contents of the object.

    The encoding is identical to the encoding git uses for loose objects.

    This operation is the inverse of `decode_object`.
    """
    kind = object_kind(sha)
    size = command_output('cat-file', '-s', sha)
    contents = object_data(sha, kind)
    data = kind.encode('utf8') + b' ' + size.encode('utf8') + b'\0' + contents
    compressed = zlib.compress(data)
    return compressed


def decode_object(data):
    """
    Decode the object, write it, and return the computed hash.

    This operation is the inverse of `encode_object`.
    """
    decompressed = zlib.decompress(data)
    header, contents = decompressed.split(b'\0', 1)
    kind = header.split()[0]
    p = subprocess.Popen(['git', 'hash-object', '-w', '--stdin', '-t', kind.decode('utf8')],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=DEVNULL)
    sha = p.communicate(contents)[0].decode('utf8').strip()
    return sha


def list_objects(ref, exclude):
    """
    Return the objects reachable from ref excluding the objects reachable from
    exclude.
    """
    exclude = ['^%s' % obj for obj in exclude if object_exists(obj)]
    objects = command_output('rev-list', '--objects', ref, *exclude)
    if not objects:
        return []
    return [i.split()[0] for i in objects.split('\n')]


def referenced_objects(sha):
    """
    Return the objects directly referenced by the object.
    """
    kind = object_kind(sha)
    if kind == 'blob':
        # blob objects do not reference any other objects
        return []
    data = object_data(sha).decode('utf8').strip()
    if kind == 'tag':
        # tag objects reference a single object
        obj = data.split('\n')[0].split()[1]
        return [obj]
    elif kind == 'commit':
        # commit objects reference a tree and zero or more parents
        lines = data.split('\n')
        tree = lines[0].split()[1]
        objs = [tree]
        for line in lines[1:]:
            if line.startswith('parent '):
                objs.append(line.split()[1])
            else:
                break
        return objs
    elif kind == 'tree':
        # tree objects reference zero or more trees and blobs, or submodules
        lines = data.split('\n')
        # submodules have the mode '160000' and the kind 'commit', we filter them out because
        # there is nothing to download and this causes errors
        return [line.split()[2] for line in lines if not line.startswith('160000 commit ')]
    else:
        raise Exception('unexpected git object type: %s' % kind)


def get_remote_url(name):
    """
    Return the URL of the given remote.
    """
    return command_output('remote', 'get-url', name)

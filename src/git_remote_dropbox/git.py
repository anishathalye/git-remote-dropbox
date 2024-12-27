import subprocess
import zlib
from typing import List, Optional

from git_remote_dropbox.constants import DEVNULL

EMPTY_TREE_HASH: str = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def command_output_raw(*args: str) -> bytes:
    """
    Return the raw result of running a git command.
    """
    args = ("git", *args)
    return subprocess.check_output(args, stderr=DEVNULL)


def command_output(*args: str) -> str:
    """
    Return the raw result of running a git command.
    """
    return command_output_raw(*args).decode("utf8").strip()


def command_ok(*args: str) -> bool:
    """
    Return whether a git command runs successfully.
    """
    args = ("git", *args)
    return subprocess.call(args, stdout=DEVNULL, stderr=DEVNULL) == 0


def is_ancestor(ancestor: str, ref: str) -> bool:
    """
    Return whether ancestor is an ancestor of ref.

    This returns true when it is possible to fast-forward from ancestor to ref.
    """
    return command_ok("merge-base", "--is-ancestor", ancestor, ref)


def object_exists(sha: str) -> bool:
    """
    Return whether the object exists in the repository.
    """
    return command_ok("cat-file", "-e", sha)


def history_exists(sha: str) -> bool:
    """
    Return whether the object, along with its history, exists in the
    repository.
    """
    return command_ok("rev-list", "--objects", sha)


def ref_value(ref: str) -> str:
    """
    Return the hash of the ref.
    """
    return command_output("rev-parse", ref)


def symbolic_ref_value(name: str) -> str:
    """
    Return the branch head to which the symbolic ref refers.
    """
    return command_output("symbolic-ref", name)


def object_kind(sha: str) -> str:
    """
    Return the type of the object.
    """
    return command_output("cat-file", "-t", sha)


def object_data(sha: str, kind: Optional[str] = None) -> bytes:
    """
    Return the contents of the object.

    If kind is None, return a pretty-printed representation of the object.
    """
    if kind is not None:
        return command_output_raw("cat-file", kind, sha)
    return command_output_raw("cat-file", "-p", sha)


def encode_object(sha: str) -> bytes:
    """
    Return the encoded contents of the object.

    The encoding is identical to the encoding git uses for loose objects.

    This operation is the inverse of `decode_object`.
    """
    kind = object_kind(sha)
    size = command_output("cat-file", "-s", sha)
    contents = object_data(sha, kind)
    data = kind.encode("utf8") + b" " + size.encode("utf8") + b"\0" + contents
    return zlib.compress(data)


def decode_object(data: bytes) -> str:
    """
    Decode the object, write it, and return the computed hash.

    This operation is the inverse of `encode_object`.
    """
    decompressed = zlib.decompress(data)
    header, contents = decompressed.split(b"\0", 1)
    kind = header.split()[0]
    return write_object(kind.decode("utf8"), contents)


def write_object(kind: str, contents: bytes) -> str:
    with subprocess.Popen(
        ["git", "hash-object", "-w", "--stdin", "-t", kind],  # noqa: S607
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=DEVNULL,
    ) as p:
        sha = p.communicate(contents)[0].decode("utf8").strip()
    return sha  # noqa: RET504


def list_objects(ref: str, exclude: List[str]) -> List[str]:
    """
    Return the objects reachable from ref excluding the objects reachable from
    exclude.
    """
    exclude = [f"^{obj}" for obj in exclude if object_exists(obj)]
    objects = command_output("rev-list", "--objects", ref, *exclude)
    if not objects:
        return []
    return [i.split()[0] for i in objects.split("\n")]


def referenced_objects(sha: str) -> List[str]:
    """
    Return the objects directly referenced by the object.
    """
    kind = object_kind(sha)
    if kind == "blob":
        # blob objects do not reference any other objects
        return []
    data = object_data(sha).decode("utf8").strip()
    if kind == "tag":
        # tag objects reference a single object
        obj = data.split("\n", maxsplit=1)[0].split()[1]
        return [obj]
    if kind == "commit":
        # commit objects reference a tree and zero or more parents
        lines = data.split("\n")
        tree = lines[0].split()[1]
        objs = [tree]
        for line in lines[1:]:
            if line.startswith("parent "):
                objs.append(line.split()[1])
            else:
                break
        return objs
    if kind == "tree":
        # tree objects reference zero or more trees and blobs, or submodules
        if not data:
            # empty tree
            return []
        lines = data.split("\n")
        # submodules have the mode '160000' and the kind 'commit', we filter them out because
        # there is nothing to download and this causes errors
        return [line.split()[2] for line in lines if not line.startswith("160000 commit ")]
    msg = f"unexpected git object type: {kind}"
    raise ValueError(msg)


def get_remote_url(name: str) -> str:
    """
    Return the URL of the given remote.
    """
    return command_output("remote", "get-url", name)

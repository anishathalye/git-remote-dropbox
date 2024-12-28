import multiprocessing
import multiprocessing.dummy
import multiprocessing.pool
import posixpath
import sys
import threading
from typing import Dict, List, NoReturn, Optional, Set, Tuple, Union

import dropbox  # type: ignore

from git_remote_dropbox import git
from git_remote_dropbox.constants import (
    CHUNK_SIZE,
    MAX_RETRIES,
    PROCESSES,
)
from git_remote_dropbox.util import (
    Binder,
    Level,
    Poison,
    Token,
    readline,
    stderr,
    stdout,
)

try:
    # Importing synchronize is to detect platforms where
    # multiprocessing does not work (python issue 3770)
    # and cause an ImportError. Otherwise it will happen
    # later when trying to use Queue().
    from multiprocessing import Queue
    from multiprocessing import synchronize as _  # noqa: F401
except ImportError:
    from queue import Queue  # type: ignore


class Helper:
    """
    A git remote helper to communicate with Dropbox.
    """

    def __init__(self, token: Token, path: str, processes: int = PROCESSES) -> None:
        self._token = token
        self._per_thread = threading.local()
        self._path = path
        self._processes = processes
        self._verbosity = Level.INFO  # default verbosity
        self._refs: Dict[str, Tuple[str, str]] = {}  # map from remote ref name => (rev number, sha)
        self._pushed: Dict[str, str] = {}  # map from remote ref name => sha
        self._first_push = False

    @property
    def verbosity(self) -> Level:
        return self._verbosity

    def _trace(self, message: str, level: Level = Level.DEBUG, *, exact: bool = False) -> None:
        """
        Log a message with a given severity level.
        """
        if level > self._verbosity:
            return
        if exact:
            if level == self._verbosity:
                stderr(message)
            return
        if level <= Level.ERROR:
            stderr(f"error: {message}\n")
        elif level == Level.INFO:
            stderr(f"info: {message}\n")
        elif level >= Level.DEBUG:
            stderr(f"debug: {message}\n")

    def _fatal(self, message: str) -> NoReturn:
        """
        Log a fatal error and exit.
        """
        self._trace(message, Level.ERROR)
        sys.exit(1)

    @property
    def _connection(self) -> dropbox.Dropbox:
        """
        Return a Dropbox connection object private to this thread.

        Lazily initialized per-thread.
        """
        if not hasattr(self._per_thread, "connection"):
            self._per_thread.connection = self._token.connect()
        return self._per_thread.connection

    def run(self) -> None:
        """
        Run the helper following the git remote helper communication protocol.
        """
        while True:
            line = readline()
            if line == "capabilities":
                _write("option")
                _write("push")
                _write("fetch")
                _write()
            elif line.startswith("option"):
                self._do_option(line)
            elif line.startswith("list"):
                self._do_list(line)
            elif line.startswith("push"):
                self._do_push(line)
            elif line.startswith("fetch"):
                self._do_fetch(line)
            elif line == "":
                break
            else:
                self._fatal(f"unsupported operation: {line}")

    def _do_option(self, line: str) -> None:
        """
        Handle the option command.
        """
        if line.startswith("option verbosity"):
            self._verbosity = Level(int(line[len("option verbosity ") :]))
            _write("ok")
        else:
            _write("unsupported")

    def _do_list(self, line: str) -> None:
        """
        Handle the list command.
        """
        for_push = "for-push" in line
        refs = self.get_refs(for_push=for_push)
        for sha, ref in refs:
            _write(f"{sha} {ref}")
        if not for_push:
            head = self.read_symbolic_ref("HEAD")
            if head:
                _write(f"@{head[1]} HEAD")
            else:
                self._trace("no default branch on remote", Level.INFO)
        _write()

    def _do_push(self, line: str) -> None:
        """
        Handle the push command.
        """
        remote_head = None
        while True:
            src, dst = line.split(" ")[1].split(":")
            if src == "":
                self._delete(dst)
            else:
                self._push(src, dst)
                if self._first_push and (not remote_head or src == git.symbolic_ref("HEAD")):
                    remote_head = dst
            line = readline()
            if line == "":
                if self._first_push:
                    self._first_push = False
                    if remote_head:
                        if not self.write_symbolic_ref("HEAD", remote_head):
                            self._trace("failed to set default branch on remote", Level.INFO)
                    else:
                        self._trace("first push but no branch to set remote HEAD")
                break
        _write()

    def _do_fetch(self, line: str) -> None:
        """
        Handle the fetch command.
        """
        while True:
            _, sha, value = line.split(" ")
            self._fetch(sha)
            line = readline()
            if line == "":
                break
        _write()

    def _delete(self, ref: str) -> None:
        """
        Delete the ref from the remote.
        """
        self._trace(f"deleting ref {ref}")
        head = self.read_symbolic_ref("HEAD")
        if head and ref == head[1]:
            _write(f"error {ref} refusing to delete the current branch: {head[1]}")
            return
        try:
            self._connection.files_delete(self._ref_path(ref))
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.DeleteError):
                raise
            # someone else might have deleted it first, that's fine
        self._refs.pop(ref, None)  # discard
        self._pushed.pop(ref, None)  # discard
        _write(f"ok {ref}")

    def _push(self, src: str, dst: str) -> None:
        """
        Push src to dst on the remote.
        """
        force = False
        if src.startswith("+"):
            src = src[1:]
            force = True
        present = [self._refs[name][1] for name in self._refs]
        present.extend(self._pushed.values())
        # before updating the ref, write all objects that are referenced
        objects = git.list_objects(src, present)
        try:
            # upload objects in parallel
            pool = multiprocessing.pool.ThreadPool(processes=self._processes)
            res = pool.imap_unordered(Binder(self, "_put_object"), objects)
            # show progress
            total = len(objects)
            self._trace("", level=Level.INFO, exact=True)
            for done, _ in enumerate(res, 1):
                pct = int(float(done) / total * 100)
                message = f"\rWriting objects: {pct:3.0f}% ({done}/{total})"
                if done == total:
                    message = f"{message}, done.\n"
                self._trace(message, level=Level.INFO, exact=True)
        except Exception:
            if self.verbosity >= Level.DEBUG:
                raise  # re-raise exception so it prints out a stack trace
            self._fatal("exception while writing objects (run with -v for details)\n")
        sha = git.ref_value(src)
        error = self._write_ref(sha, dst, force=force)
        if error is None:
            _write(f"ok {dst}")
            self._pushed[dst] = sha
        else:
            _write(f"error {dst} {error}")

    def _ref_path(self, name: str) -> str:
        """
        Return the path to the given ref on the remote.
        """
        if not name.startswith("refs/"):
            msg = f"invalid ref name: {name}"
            raise ValueError(msg)
        return posixpath.join(self._path, name)

    def _ref_name_from_path(self, path: str) -> str:
        """
        Return the ref name given the full path of the remote ref.
        """
        prefix = f"{self._path}/"
        if not path.startswith(prefix):
            msg = f"invalid ref path: {path}"
            raise ValueError(msg)
        return path[len(prefix) :]

    def _object_path(self, name: str) -> str:
        """
        Return the path to the given object on the remote.
        """
        prefix = name[:2]
        suffix = name[2:]
        return posixpath.join(self._path, "objects", prefix, suffix)

    def _get_file(self, path: str) -> Tuple[str, bytes]:
        """
        Return the revision number and content of a given file on the remote.

        Return a tuple (revision, content).
        """
        self._trace(f"fetching: {path}")
        meta, resp = self._connection.files_download(path)
        return (meta.rev, resp.content)

    def _get_files(self, paths: List[str]) -> List[Tuple[str, bytes]]:
        """
        Return a list of (revision number, content) for a given list of files.
        """
        pool = multiprocessing.dummy.Pool(self._processes)
        return pool.map(self._get_file, paths)  # type: ignore

    def _put_object(self, sha: str) -> None:
        """
        Upload an object to the remote.
        """
        data = git.encode_object(sha)
        path = self._object_path(sha)
        self._trace(f"writing: {path}")
        retries = 0
        mode = dropbox.files.WriteMode.overwrite

        if len(data) <= CHUNK_SIZE:
            while True:
                try:
                    self._connection.files_upload(data, path, mode, strict_conflict=True, mute=True)
                except dropbox.exceptions.InternalServerError:
                    self._trace(f"internal server error writing {sha}, retrying")
                    if retries < MAX_RETRIES:
                        retries += 1
                    else:
                        raise
                else:
                    break
        else:
            cursor = dropbox.files.UploadSessionCursor(offset=0)
            done_uploading = False

            while not done_uploading:
                try:
                    end = cursor.offset + CHUNK_SIZE
                    chunk = data[(cursor.offset) : end]

                    if cursor.offset == 0:
                        # upload first chunk
                        result = self._connection.files_upload_session_start(chunk)
                        cursor.session_id = result.session_id
                    elif end < len(data):
                        # upload intermediate chunks
                        self._connection.files_upload_session_append_v2(chunk, cursor)
                    else:
                        # upload the last chunk
                        commit_info = dropbox.files.CommitInfo(path, mode, strict_conflict=True, mute=True)
                        self._connection.files_upload_session_finish(chunk, cursor, commit_info)
                        done_uploading = True

                    # advance cursor to next chunk
                    cursor.offset = end

                except dropbox.files.UploadSessionOffsetError as offset_error:
                    self._trace(f"offset error writing {sha}, retrying")
                    cursor.offset = offset_error.correct_offset
                    if retries < MAX_RETRIES:
                        retries += 1
                    else:
                        raise
                except dropbox.exceptions.InternalServerError:
                    self._trace(f"internal server error writing {sha}, retrying")
                    if retries < MAX_RETRIES:
                        retries += 1
                    else:
                        raise

    def _download(self, input_queue: "Queue[Union[str, Poison]]", output_queue: "Queue[Union[str, Poison]]") -> None:
        """
        Download files given in input_queue and push results to output_queue.
        """
        while True:
            try:
                obj = input_queue.get()
                if isinstance(obj, Poison):
                    return
                _, data = self._get_file(self._object_path(obj))
                computed_sha = git.decode_object(data)
                if computed_sha != obj:
                    output_queue.put(Poison(f"hash mismatch {computed_sha} != {obj}"))
                output_queue.put(obj)
            except Exception as e:  # noqa: BLE001
                output_queue.put(Poison(f"exception while downloading: {e}"))

    def _fetch(self, sha: str) -> None:
        """
        Recursively fetch the given object and the objects it references.
        """
        # have multiple threads downloading in parallel
        queue = [sha]
        pending: Set[str] = set()
        downloaded: Set[str] = set()
        input_queue: Queue[Union[str, Poison]] = Queue()  # requesting downloads
        output_queue: Queue[Union[str, Poison]] = Queue()  # completed downloads
        procs = []
        for _ in range(self._processes):
            target = Binder(self, "_download")
            args = (input_queue, output_queue)
            # use multiprocessing.dummy to use threads instead of processes
            proc = multiprocessing.dummy.Process(target=target, args=args)
            proc.daemon = True
            proc.start()
            procs.append(proc)
        self._trace("", level=Level.INFO, exact=True)  # for showing progress
        done = total = 0
        while queue or pending:
            if queue:
                # if possible, queue up download
                sha = queue.pop()
                if sha in downloaded or sha in pending:
                    continue
                if git.object_exists(sha):
                    if sha == git.EMPTY_TREE_HASH:
                        # git.object_exists() returns True for the empty
                        # tree hash even if it's not present in the object
                        # store. Everything will work fine in this situation,
                        # but `git fsck` will complain if it's not present, so
                        # we explicitly add it to avoid that.
                        git.write_object("tree", b"")
                    if not git.history_exists(sha):
                        # this can only happen in the case of aborted fetches
                        # that are resumed later
                        self._trace(f"missing part of history from {sha}")
                        queue.extend(git.referenced_objects(sha))
                    else:
                        self._trace(f"{sha} already downloaded")
                else:
                    pending.add(sha)
                    input_queue.put(sha)
            else:
                # process completed download
                res = output_queue.get()
                if isinstance(res, Poison):
                    # _download never puts Poison with an empty message in the output_queue
                    if res.message is None:
                        msg = "invalid Poison with no message"
                        raise ValueError(msg)
                    self._fatal(res.message)
                pending.remove(res)
                downloaded.add(res)
                queue.extend(git.referenced_objects(res))
                # show progress
                done = len(downloaded)
                total = done + len(pending)
                pct = int(float(done) / total * 100)
                message = f"\rReceiving objects: {pct:3.0f}% ({done}/{total})"
                self._trace(message, level=Level.INFO, exact=True)
        if total:
            self._trace(
                f"\rReceiving objects: 100% ({done}/{total}), done.\n",
                level=Level.INFO,
                exact=True,
            )
        for _ in procs:
            input_queue.put(Poison())
        for proc in procs:
            proc.join()

    def _write_ref(self, new_sha: str, dst: str, *, force: bool = False) -> Optional[str]:
        """
        Atomically update the given reference to point to the given object.

        Return None if there is no error, otherwise return a description of the
        error.
        """
        path = self._ref_path(dst)
        if force:
            # overwrite regardless of what is there before
            mode = dropbox.files.WriteMode.overwrite
        else:
            info = self._refs.get(dst, None)
            if info:
                rev, sha = info
                if not git.object_exists(sha):
                    return "fetch first"
                is_fast_forward = git.is_ancestor(sha, new_sha)
                if not is_fast_forward and not force:
                    return "non-fast forward"
                # perform an atomic compare-and-swap
                mode = dropbox.files.WriteMode.update(rev)
            else:
                # perform an atomic add, which fails if a concurrent writer
                # writes before this does
                mode = dropbox.files.WriteMode.add
        self._trace(f"writing ref {dst} with mode {mode}")
        data = f"{new_sha}\n".encode()
        try:
            self._connection.files_upload(data, path, mode, strict_conflict=True, mute=True)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.UploadError):
                raise
            return "fetch first"
        else:
            return None

    def get_refs(self, *, for_push: bool) -> List[Tuple[str, str]]:
        """
        Return the refs present on the remote.

        Return a list of tuples of (sha, name).
        """
        try:
            loc = posixpath.join(self._path, "refs")
            res = self._connection.files_list_folder(loc, recursive=True)
            files = res.entries
            while res.has_more:
                res = self._connection.files_list_folder_continue(res.cursor)
                files.extend(res.entries)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.ListFolderError):
                raise
            if not for_push:
                # if we're pushing, it's okay if nothing exists beforehand,
                # but it's good to notify the user just in case
                self._trace("repository is empty", Level.INFO)
            else:
                self._first_push = True
            return []
        files = [i for i in files if isinstance(i, dropbox.files.FileMetadata)]
        paths = [i.path_lower for i in files]
        if not paths:
            return []
        revs: List[str] = []
        data: List[bytes] = []
        for rev, datum in self._get_files(paths):
            revs.append(rev)
            data.append(datum)
        refs = []
        for path, rev, datum in zip(paths, revs, data):
            name = self._ref_name_from_path(path)
            sha = datum.decode("utf8").strip()
            self._refs[name] = (rev, sha)
            refs.append((sha, name))
        return refs

    def write_symbolic_ref(self, path: str, ref: str, rev: Optional[str] = None) -> bool:
        """
        Write the given symbolic ref to the remote.

        Perform a compare-and-swap (using previous revision rev) if specified,
        otherwise perform a regular write.

        Return a boolean indicating whether the write was successful.
        """
        path = posixpath.join(self._path, path)
        # choose between atomic compare-and-swap and atomic add
        mode = dropbox.files.WriteMode.update(rev) if rev else dropbox.files.WriteMode.add
        data = f"ref: {ref}\n".encode()
        self._trace(f"writing symbolic ref {path} with mode {mode}")
        try:
            self._connection.files_upload(data, path, mode, strict_conflict=True, mute=True)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.UploadError):
                raise
            return False
        return True

    def read_symbolic_ref(self, path: str) -> Optional[Tuple[str, str]]:
        """
        Return the revision number and content of a given symbolic ref on the remote.

        Return a tuple (revision, content), or None if the symbolic ref does not exist.
        """
        path = posixpath.join(self._path, path)
        self._trace(f"fetching symbolic ref: {path}")
        try:
            meta, resp = self._connection.files_download(path)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.DownloadError):
                raise
            return None
        ref = resp.content.decode("utf8")
        ref = ref[len("ref: ") :].rstrip()
        rev = meta.rev
        return (rev, ref)


def _write(message: Optional[str] = None) -> None:
    """
    Write a message to standard output.
    """
    if message is not None:
        stdout(f"{message}\n")
    else:
        stdout("\n")

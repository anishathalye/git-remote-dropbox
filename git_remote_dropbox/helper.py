from git_remote_dropbox.constants import (
    PROCESSES,
    CHUNK_SIZE,
    MAX_RETRIES,
)
from git_remote_dropbox.util import (
    readline,
    Level,
    stdout,
    stderr,
    Binder,
    Poison,
)
import git_remote_dropbox.git as git

import dropbox

import multiprocessing
import multiprocessing.dummy
import multiprocessing.pool
import posixpath


class Helper(object):
    """
    A git remote helper to communicate with Dropbox.
    """

    def __init__(self, token, path, processes=PROCESSES):
        self._token = token
        self._path = path
        self._processes = processes
        self._verbosity = Level.INFO  # default verbosity
        self._refs = {}  # map from remote ref name => (rev number, sha)
        self._pushed = {}  # map from remote ref name => sha
        self._first_push = False

    @property
    def verbosity(self):
        return self._verbosity

    def _write(self, message=None):
        """
        Write a message to standard output.
        """
        if message is not None:
            stdout('%s\n' % message)
        else:
            stdout('\n')

    def _trace(self, message, level=Level.DEBUG, exact=False):
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
            stderr('error: %s\n' % message)
        elif level == Level.INFO:
            stderr('info: %s\n' % message)
        elif level >= Level.DEBUG:
            stderr('debug: %s\n' % message)

    def _fatal(self, message):
        """
        Log a fatal error and exit.
        """
        self._trace(message, Level.ERROR)
        exit(1)

    def _connection(self):
        """
        Return a Dropbox connection object.
        """
        # we use fresh connection objects for every use so that multiple
        # threads can have connections simultaneously
        return dropbox.Dropbox(self._token)

    def run(self):
        """
        Run the helper following the git remote helper communication protocol.
        """
        while True:
            line = readline()
            if line == 'capabilities':
                self._write('option')
                self._write('push')
                self._write('fetch')
                self._write()
            elif line.startswith('option'):
                self._do_option(line)
            elif line.startswith('list'):
                self._do_list(line)
            elif line.startswith('push'):
                self._do_push(line)
            elif line.startswith('fetch'):
                self._do_fetch(line)
            elif line == '':
                break
            else:
                self._fatal('unsupported operation: %s' % line)

    def _do_option(self, line):
        """
        Handle the option command.
        """
        if line.startswith('option verbosity'):
            self._verbosity = int(line[len('option verbosity '):])
            self._write('ok')
        else:
            self._write('unsupported')

    def _do_list(self, line):
        """
        Handle the list command.
        """
        for_push = 'for-push' in line
        refs = self.get_refs(for_push=for_push)
        for sha, ref in refs:
            self._write('%s %s' % (sha, ref))
        if not for_push:
            head = self.read_symbolic_ref('HEAD')
            if head:
                self._write('@%s HEAD' % head[1])
            else:
                self._trace('no default branch on remote', Level.INFO)
        self._write()

    def _do_push(self, line):
        """
        Handle the push command.
        """
        remote_head = None
        while True:
            src, dst = line.split(' ')[1].split(':')
            if src == '':
                self._delete(dst)
            else:
                self._push(src, dst)
                if self._first_push:
                    if not remote_head or src == git.symbolic_ref('HEAD'):
                        remote_head = dst
            line = readline()
            if line == '':
                if self._first_push:
                    self._first_push = False
                    if not self.write_symbolic_ref('HEAD', remote_head):
                        self._trace('failed to set default branch on remote', Level.INFO)
                break
        self._write()

    def _do_fetch(self, line):
        """
        Handle the fetch command.
        """
        while True:
            _, sha, value = line.split(' ')
            self._fetch(sha)
            line = readline()
            if line == '':
                break
        self._write()

    def _delete(self, ref):
        """
        Delete the ref from the remote.
        """
        self._trace('deleting ref %s' % ref)
        head = self.read_symbolic_ref('HEAD')
        if head and ref == head[1]:
            self._write('error %s refusing to delete the current branch: %s' % (ref, head))
            return
        try:
            self._connection().files_delete(self._ref_path(ref))
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.DeleteError):
                raise
            # someone else might have deleted it first, that's fine
        self._refs.pop(ref, None)  # discard
        self._pushed.pop(ref, None)  # discard
        self._write('ok %s' % ref)

    def _push(self, src, dst):
        """
        Push src to dst on the remote.
        """
        force = False
        if src.startswith('+'):
            src = src[1:]
            force = True
        present = [self._refs[name][1] for name in self._refs]
        present.extend(self._pushed.values())
        # before updating the ref, write all objects that are referenced
        objects = git.list_objects(src, present)
        try:
            # upload objects in parallel
            pool = multiprocessing.pool.ThreadPool(processes=self._processes)
            res = pool.imap_unordered(Binder(self, '_put_object'), objects)
            # show progress
            total = len(objects)
            self._trace('', level=Level.INFO, exact=True)
            for done, _ in enumerate(res, 1):
                pct = int(float(done) / total * 100)
                message = '\rWriting objects: {:3.0f}% ({}/{})'.format(pct, done, total)
                if done == total:
                    message = '%s, done.\n' % message
                self._trace(message, level=Level.INFO, exact=True)
        except Exception:
            if self.verbosity >= Level.DEBUG:
                raise  # re-raise exception so it prints out a stack trace
            else:
                self._fatal('exception while writing objects (run with -v for details)\n')
        sha = git.ref_value(src)
        error = self._write_ref(sha, dst, force)
        if error is None:
            self._write('ok %s' % dst)
            self._pushed[dst] = sha
        else:
            self._write('error %s %s' % (dst, error))

    def _ref_path(self, name):
        """
        Return the path to the given ref on the remote.
        """
        assert name.startswith('refs/')
        return posixpath.join(self._path, name)

    def _ref_name_from_path(self, path):
        """
        Return the ref name given the full path of the remote ref.
        """
        prefix = '%s/' % self._path
        assert path.startswith(prefix)
        return path[len(prefix):]

    def _object_path(self, name):
        """
        Return the path to the given object on the remote.
        """
        prefix = name[:2]
        suffix = name[2:]
        return posixpath.join(self._path, 'objects', prefix, suffix)

    def _get_file(self, path):
        """
        Return the revision number and content of a given file on the remote.

        Return a tuple (revision, content).
        """
        self._trace('fetching: %s' % path)
        meta, resp = self._connection().files_download(path)
        return (meta.rev, resp.content)

    def _get_files(self, paths):
        """
        Return a list of (revision number, content) for a given list of files.
        """
        pool = multiprocessing.dummy.Pool(self._processes)
        return pool.map(self._get_file, paths)

    def _put_object(self, sha):
        """
        Upload an object to the remote.
        """
        data = git.encode_object(sha)
        path = self._object_path(sha)
        self._trace('writing: %s' % path)
        retries = 0
        mode = dropbox.files.WriteMode('overwrite')

        if len(data) <= CHUNK_SIZE:
            while True:
                try:
                    self._connection().files_upload(data, path, mode, mute=True)
                except dropbox.exceptions.InternalServerError:
                    self._trace('internal server error writing %s, retrying' % sha)
                    if retries < MAX_RETRIES:
                        retries += 1
                    else:
                        raise
                else:
                    break
        else:
            conn = self._connection()
            cursor = dropbox.files.UploadSessionCursor(offset=0)
            done_uploading = False

            while not done_uploading:
                try:
                    end = cursor.offset + CHUNK_SIZE
                    chunk = data[(cursor.offset):end]

                    if cursor.offset == 0:
                        # upload first chunk
                        result = conn.files_upload_session_start(chunk)
                        cursor.session_id = result.session_id
                    elif end < len(data):
                        # upload intermediate chunks
                        conn.files_upload_session_append_v2(chunk, cursor)
                    else:
                        # upload the last chunk
                        commit_info = dropbox.files.CommitInfo(path, mode, mute=True)
                        conn.files_upload_session_finish(chunk, cursor, commit_info)
                        done_uploading = True

                    # advance cursor to next chunk
                    cursor.offset = end

                except dropbox.files.UploadSessionOffsetError as offset_error:
                    self._trace('offset error writing %s, retrying' % sha)
                    cursor.offset = offset_error.correct_offset
                    if retries < MAX_RETRIES:
                        retries += 1
                    else:
                        raise
                except dropbox.exceptions.InternalServerError:
                    self._trace('internal server error writing %s, retrying' % sha)
                    if retries < MAX_RETRIES:
                        retries += 1
                    else:
                        raise

    def _download(self, input_queue, output_queue):
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
                    output_queue.put(
                        Poison('hash mismatch %s != %s' % (computed_sha, obj)))
                output_queue.put(obj)
            except Exception as e:
                output_queue.put(Poison('exception while downloading: %s' % e))

    def _fetch(self, sha):
        """
        Recursively fetch the given object and the objects it references.
        """
        # have multiple threads downloading in parallel
        queue = [sha]
        pending = set()
        downloaded = set()
        input_queue = multiprocessing.Queue()  # requesting downloads
        output_queue = multiprocessing.Queue()  # completed downloads
        procs = []
        for _ in range(self._processes):
            target = Binder(self, '_download')
            args = (input_queue, output_queue)
            # use multiprocessing.dummy to use threads instead of processes
            proc = multiprocessing.dummy.Process(target=target, args=args)
            proc.daemon = True
            proc.start()
            procs.append(proc)
        self._trace('', level=Level.INFO, exact=True)  # for showing progress
        done = total = 0
        while queue or pending:
            if queue:
                # if possible, queue up download
                sha = queue.pop()
                if sha in downloaded or sha in pending:
                    continue
                if git.object_exists(sha):
                    if not git.history_exists(sha):
                        # this can only happen in the case of aborted fetches
                        # that are resumed later
                        self._trace('missing part of history from %s' % sha)
                        queue.extend(git.referenced_objects(sha))
                    else:
                        self._trace('%s already downloaded' % sha)
                else:
                    pending.add(sha)
                    input_queue.put(sha)
            else:
                # process completed download
                res = output_queue.get()
                if isinstance(res, Poison):
                    self._fatal(res.message)
                pending.remove(res)
                downloaded.add(res)
                queue.extend(git.referenced_objects(res))
                # show progress
                done = len(downloaded)
                total = done + len(pending)
                pct = int(float(done) / total * 100)
                message = '\rReceiving objects: {:3.0f}% ({}/{})'.format(pct, done, total)
                self._trace(message, level=Level.INFO, exact=True)
        if total:
            self._trace('\rReceiving objects: 100% ({}/{}), done.\n'.format(done, total),
                        level=Level.INFO, exact=True)
        for proc in procs:
            input_queue.put(Poison())
        for proc in procs:
            proc.join()

    def _write_ref(self, new_sha, dst, force=False):
        """
        Atomically update the given reference to point to the given object.

        Return None if there is no error, otherwise return a description of the
        error.
        """
        path = self._ref_path(dst)
        if force:
            # overwrite regardless of what is there before
            mode = dropbox.files.WriteMode('overwrite')
        else:
            info = self._refs.get(dst, None)
            if info:
                rev, sha = info
                if not git.object_exists(sha):
                    return 'fetch first'
                is_fast_forward = git.is_ancestor(sha, new_sha)
                if not is_fast_forward and not force:
                    return 'non-fast forward'
                # perform an atomic compare-and-swap
                mode = dropbox.files.WriteMode.update(rev)
            else:
                # perform an atomic add, which fails if a concurrent writer
                # writes before this does
                mode = dropbox.files.WriteMode('add')
        self._trace('writing ref %s with mode %s' % (dst, mode))
        data = ('%s\n' % new_sha).encode('utf8')
        try:
            self._connection().files_upload(data, path, mode, mute=True)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.UploadError):
                raise
            return 'fetch first'
        else:
            return None

    def get_refs(self, for_push):
        """
        Return the refs present on the remote.

        Return a list of tuples of (sha, name).
        """
        try:
            loc = posixpath.join(self._path, 'refs')
            res = self._connection().files_list_folder(loc, recursive=True)
            files = res.entries
            while res.has_more:
                res = self._connection().files_list_folder_continue(res.cursor)
                files.extend(res.entries)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.ListFolderError):
                raise
            if not for_push:
                # if we're pushing, it's okay if nothing exists beforehand,
                # but it's good to notify the user just in case
                self._trace('repository is empty', Level.INFO)
            else:
                self._first_push = True
            return []
        files = [i for i in files if isinstance(i, dropbox.files.FileMetadata)]
        paths = [i.path_lower for i in files]
        if not paths:
            return []
        revs, data = zip(*self._get_files(paths))
        refs = []
        for path, rev, data in zip(paths, revs, data):
            name = self._ref_name_from_path(path)
            sha = data.decode('utf8').strip()
            self._refs[name] = (rev, sha)
            refs.append((sha, name))
        return refs

    def write_symbolic_ref(self, path, ref, rev=None):
        """
        Write the given symbolic ref to the remote.

        Perform a compare-and-swap (using previous revision rev) if specified,
        otherwise perform a regular write.

        Return a boolean indicating whether the write was successful.
        """
        path = posixpath.join(self._path, path)
        if rev:
            # atomic compare-and-swap
            mode = dropbox.files.WriteMode.update(rev)
        else:
            # atomic add
            mode = dropbox.files.WriteMode('add')
        data = ('ref: %s\n' % ref).encode('utf8')
        self._trace('writing symbolic ref %s with mode %s' % (path, mode))
        try:
            self._connection().files_upload(data, path, mode, mute=True)
            return True
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.UploadError):
                raise
            return False
        return True

    def read_symbolic_ref(self, path):
        """
        Return the revision number and content of a given symbolic ref on the remote.

        Return a tuple (revision, content), or None if the symbolic ref does not exist.
        """
        path = posixpath.join(self._path, path)
        self._trace('fetching symbolic ref: %s' % path)
        try:
            meta, resp = self._connection().files_download(path)
            ref = resp.content.decode('utf8')
            ref = ref[len('ref: '):].rstrip()
            rev = meta.rev
            return (rev, ref)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.DownloadError):
                raise
            return None

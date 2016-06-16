#!/usr/bin/env python

# Copyright (c) 2015-2016 Anish Athalye (me@anishathalye.com)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import dropbox

import json
import multiprocessing
import multiprocessing.dummy
import multiprocessing.pool
import os
import posixpath
import subprocess
import sys
import zlib


__version__ = '0.2.0'


CONFIG_FILE = '~/.git-remote-dropbox.json'
DEVNULL = open(os.devnull, 'w')
PROCESSES = 20
MAX_RETRIES = 3


def stdout(line):
    """
    Write line to standard output.
    """
    sys.stdout.write(line)
    sys.stdout.flush()


def stderr(line):
    """
    Write line to standard error.
    """
    sys.stderr.write(line)
    sys.stderr.flush()


def readline():
    """
    Read a line from standard input.
    """
    return sys.stdin.readline().strip()  # remove trailing newline


def git_command_output(*args, **kwargs):
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


def git_command_ok(*args):
    """
    Return whether a git command runs successfully.
    """
    args = ('git',) + args
    return subprocess.call(args, stdout=DEVNULL, stderr=DEVNULL) == 0


def git_is_ancestor(ancestor, ref):
    """
    Return whether ancestor is an ancestor of ref.

    This returns true when it is possible to fast-forward from ancestor to ref.
    """
    return git_command_ok('merge-base', '--is-ancestor', ancestor, ref)


def git_object_exists(sha):
    """
    Return whether the object exists in the repository.
    """
    return git_command_ok('cat-file', '-t', sha)


def git_history_exists(sha):
    """
    Return whether the object, along with its history, exists in the
    repository.
    """
    return git_command_ok('rev-list', '--objects', sha)


def git_ref_value(ref):
    """
    Return the hash of the ref.
    """
    return git_command_output('rev-parse', ref)


def git_object_kind(sha):
    """
    Return the type of the object.
    """
    return git_command_output('cat-file', '-t', sha)


def git_object_data(sha, kind=None):
    """
    Return the contents of the object.

    If kind is None, return a pretty-printed representation of the object.
    """
    if kind is not None:
        return git_command_output('cat-file', kind, sha, decode=False, strip=False)
    else:
        return git_command_output('cat-file', '-p', sha, decode=False, strip=False)


def git_encode_object(sha):
    """
    Return the encoded contents of the object.

    The encoding is identical to the encoding git uses for loose objects.

    This operation is the inverse of `git_decode_object`.
    """
    kind = git_object_kind(sha)
    size = git_command_output('cat-file', '-s', sha)
    contents = git_object_data(sha, kind)
    data = kind.encode('utf8') + b' ' + size.encode('utf8') + b'\0' + contents
    compressed = zlib.compress(data)
    return compressed


def git_decode_object(data):
    """
    Decode the object, write it, and return the computed hash.

    This operation is the inverse of `git_encode_object`.
    """
    decompressed = zlib.decompress(data)
    header, contents = decompressed.split(b'\0', 1)
    kind = header.split()[0]
    p = subprocess.Popen(['git', 'hash-object', '-w', '--stdin', '-t', kind],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=DEVNULL)
    sha = p.communicate(contents)[0].decode('utf8').strip()
    return sha


def git_list_objects(ref, exclude):
    """
    Return the objects reachable from ref excluding the objects reachable from
    exclude.
    """
    exclude = ['^%s' % obj for obj in exclude if git_object_exists(obj)]
    objects = git_command_output('rev-list', '--objects', ref, *exclude)
    if not objects:
        return []
    return [i.split()[0] for i in objects.split('\n')]


def git_referenced_objects(sha):
    """
    Return the objects directly referenced by the object.
    """
    kind = git_object_kind(sha)
    if kind == 'blob':
        # blob objects do not reference any other objects
        return []
    data = git_object_data(sha).decode('utf8').strip()
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


class Level(object):
    """
    A class for severity levels.
    """

    ERROR = 0
    INFO = 1
    DEBUG = 2


class Poison(object):
    """
    A poison pill.

    Instances of this class can be used as sentinel objects to communicate
    termination requests to processes.
    """

    def __init__(self, message=None):
        self.message = message


class Binder(object):
    """
    A class to bind a method to an object.

    Python's built-in pickling does not work on bound methods or lambdas. This
    class is designed to work around that restriction. In addition, it provides
    the ability to partially apply a function.

    For example, Binder can be used as follows:

        >>> class A(object):
        ...   def __init__(self, x):
        ...     self.x = x
        ...   def add(self, y, z):
        ...     return self.x + y + z
        ...
        >>> b = Binder(A(1), 'add', 2)
        >>> b(3)
        6

    In the above example, it is possible to pickle the `b` object.
    """

    def __init__(self, obj, func_name, *args):
        """
        Initialize a Binder with an object and a function by its name.

        Partially apply the function with args.
        """
        self._obj = obj
        self._func_name = func_name
        self._args = args

    def __call__(self, *args):
        """
        Call the function bound to the object, passing args if given.
        """
        # we cannot pickle an instance method, but we can pickle the instance
        # itself along with the method name, and then we can dynamically
        # retrieve the unbound method and call it with the instance and
        # arguments
        method = getattr(type(self._obj), self._func_name)
        args = self._args + args
        return method(self._obj, *args)


class Helper(object):
    """
    A git remote helper to communicate with Dropbox.
    """

    def __init__(self, token, url, processes=PROCESSES):
        self._token = token
        self._url = url
        self._processes = processes
        self._verbosity = Level.INFO  # default verbosity
        self._refs = {}  # map from remote ref name => (rev number, sha)
        self._pushed = {}  # map from remote ref name => sha

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
        refs = self._get_refs(for_push=for_push)
        for ref in refs:
            self._write(ref)
        self._write()

    def _do_push(self, line):
        """
        Handle the push command.
        """
        while True:
            src, dst = line.split(' ')[1].split(':')
            if src == '':
                self._delete(dst)
            else:
                self._push(src, dst)
            line = readline()
            if line == '':
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
        objects = git_list_objects(src, present)
        try:
            # upload objects in parallel
            pool = multiprocessing.pool.ThreadPool(processes=self._processes)
            res = pool.imap_unordered(Binder(self, '_put_object'), objects)
            # show progress
            total = len(objects)
            self._trace('', level=Level.INFO, exact=True)
            for done, _ in enumerate(res, 1):
                pct = float(done) / total
                message = '\rWriting objects: {:4.0%} ({}/{})'.format(pct, done, total)
                if done == total:
                    message = '%s, done.\n' % message
                self._trace(message, level=Level.INFO, exact=True)
        except Exception:
            self._fatal('exception while writing objects')
        sha = git_ref_value(src)
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
        return posixpath.join(self._url, name)

    def _ref_name_from_path(self, path):
        """
        Return the ref name given the full path of the remote ref.
        """
        prefix = '%s/' % self._url
        assert path.startswith(prefix)
        return path[len(prefix):]

    def _object_path(self, name):
        """
        Return the path to the given object on the remote.
        """
        prefix = name[:2]
        suffix = name[2:]
        return posixpath.join(self._url, 'objects', prefix, suffix)

    def _get_file(self, path):
        """
        Return the revision number and content of a given file on the remote.

        Return a tuple (revision, content).
        """
        self._trace('fetching: %s' % path)
        meta, resp = self._connection().files_download(path)
        return (meta.rev, resp.content)

    def _put_object(self, sha):
        """
        Upload an object to the remote.
        """
        data = git_encode_object(sha)
        path = self._object_path(sha)
        self._trace('writing: %s' % path)
        retries = 0
        while True:
            try:
                mode = dropbox.files.WriteMode('overwrite')
                self._connection().files_upload(data, path, mode, mute=True)
            except dropbox.exceptions.InternalServerError:
                self._trace('internal server error writing %s, retrying' % sha)
                if retries < MAX_RETRIES:
                    retries += 1
                else:
                    raise
            else:
                break

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
                computed_sha = git_decode_object(data)
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
        self._trace('', level=Level.INFO, exact=True) # for showing progress
        while queue or pending:
            if queue:
                # if possible, queue up download
                sha = queue.pop()
                if sha in downloaded or sha in pending:
                    continue
                if git_object_exists(sha):
                    if not git_history_exists(sha):
                        # this can only happen in the case of aborted fetches
                        # that are resumed later
                        self._trace('missing part of history from %s' % sha)
                        queue.extend(git_referenced_objects(sha))
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
                queue.extend(git_referenced_objects(res))
                # show progress
                done = len(downloaded)
                total = done + len(pending)
                pct = float(done) / total
                message = '\rReceiving objects: {:4.0%} ({}/{})'.format(pct, done, total)
                self._trace(message, level=Level.INFO, exact=True)
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
                is_fast_forward = git_is_ancestor(sha, new_sha)
                if not is_fast_forward and not force:
                    return 'non-fast-forward'
                # perform an atomic compare-and-swap
                mode = dropbox.files.WriteMode.update(rev)
            else:
                # perform an atomic add, which fails if a concurrent writer
                # writes before this does
                mode = dropbox.files.WriteMode('add')
        self._trace('writing ref %s with mode %s' % (dst, mode))
        data = '%s\n' % new_sha
        try:
            self._connection().files_upload(data, path, mode, mute=True)
        except dropbox.exceptions.ApiError as e:
            if not isinstance(e.error, dropbox.files.UploadError):
                raise
            return 'fetch first'
        else:
            return None

    def _get_refs(self, for_push):
        """
        Return the refs present on the remote.
        """
        try:
            loc = posixpath.join(self._url, 'refs')
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
            return []
        refs = []
        for ref_file in files:
            if not isinstance(ref_file, dropbox.files.FileMetadata):
                continue
            path = ref_file.path_lower
            name = self._ref_name_from_path(path)
            rev, data = self._get_file(path)
            sha = data.decode('utf8').strip()
            self._refs[name] = (rev, sha)
            refs.append('%s %s' % (sha, name))
        return refs


class Config(object):
    """
    A class to manage configuration data.
    """

    def __init__(self, filename):
        with open(filename) as f:
            self._settings = json.load(f)

    def __getitem__(self, key):
        """
        Return the setting corresponding to key.

        Raises KeyError if the config file is missing the key.
        """
        return self._settings[key]


def main():
    name, url = sys.argv[1:3]
    url = url.lower()
    if url.startswith('dropbox://'):
        url = url[len('dropbox:/'):]  # keep single leading slash
    if not url.startswith('/') or url.endswith('/'):
        stderr('error: URL must have leading slash and no trailing slash\n')
        exit(1)

    config_files = [
        os.path.join(os.environ.get('XDG_CONFIG_HOME',
                                    os.path.expanduser('~/.config')),
                     'git',
                     'git-remote-dropbox.json'),
        os.path.expanduser('~/.git-remote-dropbox.json'),
    ]
    config = None
    for config_file in config_files:
        try:
            config = Config(config_file)
        except ValueError:
            stderr('error: malformed config file: %s\n' % config_file)
            exit(1)
        except IOError:
            continue
        else:
            break
    if not config:
        stderr('error: missing config file: %s\n' % config_files[0])
        exit(1)
    try:
        token = config['token']
    except KeyError:
        stderr('error: config file missing token\n')
        exit(1)

    helper = Helper(token, url)
    try:
        helper.run()
    except Exception:
        stderr('error: unexpected exception\n')
    except KeyboardInterrupt:
        # exit silently with an error code
        exit(1)


if __name__ == '__main__':
    if sys.platform == 'win32':
        import msvcrt
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    main()

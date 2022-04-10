import json
import os
import sys
import tempfile
from typing import Optional, Any, Dict, List


def stdout(line: str) -> None:
    """
    Write line to standard output.
    """
    sys.stdout.write(line)
    sys.stdout.flush()


def stderr(line: str) -> None:
    """
    Write line to standard error.
    """
    sys.stderr.write(line)
    sys.stderr.flush()


def readline() -> str:
    """
    Read a line from standard input.
    """
    return sys.stdin.readline().strip()  # remove trailing newline


def stdout_to_binary() -> None:
    """
    Ensure that stdout is in binary mode on windows
    """
    if sys.platform == "win32":
        import msvcrt

        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


class Level:
    """
    A class for severity levels.
    """

    ERROR = 0
    INFO = 1
    DEBUG = 2


class Poison:
    """
    A poison pill.

    Instances of this class can be used as sentinel objects to communicate
    termination requests to processes.
    """

    def __init__(self, message: Optional[str] = None) -> None:
        self.message = message


class Binder:
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

    def __init__(self, obj: Any, func_name: str, *args: Any) -> None:
        """
        Initialize a Binder with an object and a function by its name.

        Partially apply the function with args.
        """
        self._obj = obj
        self._func_name = func_name
        self._args = args

    def __call__(self, *args: Any) -> Any:
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


class Config:
    """
    A class to manage configuration data.
    """

    VERSION = 2
    INITIAL_CONFIG: Dict[str, Any] = {
        "version": VERSION,
        "tokens": {
            "default": None,
            "named": {},
        },
    }
    """
    tokens are stored as descriptors of the form
        [tag, token]
    where tag is one of ['long-lived', 'refresh']

    "default" stores the default account, while explicitly named usernames are
    stored in "named"
    """

    def __init__(self, filename: str, create: bool = False) -> None:
        self._filename = filename
        if create:
            self._settings = self.INITIAL_CONFIG
            self.save()
        with open(filename) as f:
            self._settings = json.load(f)
        version = self._settings.get("version")
        # try to migrate
        if version is None:
            # v1 style config, before we had versions
            self._settings = _migrate_config_v1_to_v2(self._settings)
            self.save()
        elif version != self.VERSION:
            raise ValueError(
                'expected config version %d, got %s; delete the config file "%s" to re-initialize'
                % (self.VERSION, version, filename)
            )

    def get(self, key: str, value: Any = None) -> Any:
        return self._settings.get(key, value)

    def __getitem__(self, key: str) -> Any:
        """
        Return the setting corresponding to key.

        Raises KeyError if the config file is missing the key.
        """
        return self._settings[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._settings[key] = value

    def save(self) -> None:
        contents = json.dumps(self._settings, indent=2).encode("utf8")
        atomic_write(contents, self._filename)


def _migrate_config_v1_to_v2(obj: Dict[str, str]) -> Dict[str, Any]:
    """
    Migrate a git-remote-dropbox v1 configuration type to a v2-style configuration.

    The v1 configuration mapped strings (usernames) to long-term tokens, and
    used the string "default" to represent the default account.
    """
    named: Dict[str, List[str]] = {}
    default_token = None
    for username, token in obj.items():
        token_rep = ["long-lived", token]
        if username == "default":
            default_token = token_rep
        else:
            named[username] = token_rep
    return {
        "version": 2,
        "tokens": {
            "default": default_token,
            "named": named,
        },
    }


def atomic_write(contents: bytes, path: str) -> None:
    # same directory as path to avoid being on a different filesystem
    try:
        temp_file = tempfile.NamedTemporaryFile(dir=os.path.dirname(path), delete=False)
        temp_file.write(contents)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()  # necessary on Windows because we can't move an open file
        os.replace(temp_file.name, path)
    finally:
        try:
            os.unlink(temp_file.name)
        except:
            pass

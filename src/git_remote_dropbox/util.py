import contextlib
import json
import os
import sys
import tempfile
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Dict, Optional

import dropbox  # type: ignore

from git_remote_dropbox.constants import APP_KEY


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


class Level(IntEnum):
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
        ...     def __init__(self, x):
        ...         self.x = x
        ...
        ...     def add(self, y, z):
        ...         return self.x + y + z
        >>> b = Binder(A(1), "add", 2)
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


class Token(ABC):
    @abstractmethod
    def connect(self) -> dropbox.Dropbox:
        raise NotImplementedError

    @abstractmethod
    def serialize(self) -> Any:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse(cls, rep: Any) -> "Token":
        raise NotImplementedError


class RefreshToken(Token):
    _value: str

    def __init__(self, value: str) -> None:
        self._value = value

    def serialize(self) -> Any:
        return ["refresh", self._value]

    @classmethod
    def parse(cls, rep: Any) -> "RefreshToken":
        if (
            not isinstance(rep, list)
            or len(rep) != 2  # noqa: PLR2004
            or rep[0] != "refresh"
            or not isinstance(rep[1], str)
        ):
            msg = "cannot parse as RefreshToken"
            raise ValueError(msg)
        return RefreshToken(rep[1])

    def connect(self) -> dropbox.Dropbox:
        return dropbox.Dropbox(oauth2_refresh_token=self._value, app_key=APP_KEY)


class LongLivedToken(Token):
    _value: str

    def __init__(self, value: str) -> None:
        self._value = value

    def serialize(self) -> Any:
        return ["long-lived", self._value]

    @classmethod
    def parse(cls, rep: Any) -> "LongLivedToken":
        if (
            not isinstance(rep, list)
            or len(rep) != 2  # noqa: PLR2004
            or rep[0] != "long-lived"
            or not isinstance(rep[1], str)
        ):
            msg = "cannot parse as LongLivedToken"
            raise ValueError(msg)
        return LongLivedToken(rep[1])

    def connect(self) -> dropbox.Dropbox:
        return dropbox.Dropbox(self._value)


def parse_token(rep: Any) -> Token:
    for token_type in [RefreshToken, LongLivedToken]:
        try:
            return token_type.parse(rep)
        except ValueError:
            continue
    msg = f'cannot parse "{rep}" as a token'
    raise ValueError(msg)


class Config:
    """
    A class to manage configuration data.
    """

    _VERSION: int = 2

    _filename: str
    _default_token: Optional[Token]
    _named_tokens: Dict[str, Token]

    def __init__(self, filename: str, *, create: bool = False) -> None:
        self._filename = filename
        self._default_token = None
        self._named_tokens = {}
        if create:
            self.save()
        else:
            self.load()

    def save(self) -> None:
        rep: Dict[str, Any] = {}
        rep["version"] = self._VERSION
        named_tokens = {name: token.serialize() for name, token in self._named_tokens.items()}
        default_token = self._default_token.serialize() if self._default_token else None
        rep["tokens"] = {"default": default_token, "named": named_tokens}
        contents = json.dumps(rep, indent=2).encode("utf8")
        atomic_write(contents, self._filename)

    def load(self) -> None:
        with open(self._filename) as f:
            rep = json.load(f)
        version = rep.get("version")
        # try to migrate if necessary
        if version is None:
            # v1 style config, before we had versions
            for username, token_rep in rep.items():
                token = LongLivedToken(token_rep)
                if username == "default":
                    self._default_token = token
                else:
                    self._named_tokens[username] = token
            self.save()
        elif version != self._VERSION:
            raise ValueError(
                'expected config version %d, got %s; delete the config file "%s" to re-initialize'
                % (self._VERSION, version, self._filename)
            )
        else:
            # version is correct, parse
            default_token_rep = rep["tokens"]["default"]
            if default_token_rep:
                self._default_token = parse_token(default_token_rep)
            for username, token_rep in rep["tokens"]["named"].items():
                self._named_tokens[username] = parse_token(token_rep)

    def get_default_token(self) -> Optional[Token]:
        return self._default_token

    def set_default_token(self, token: Token) -> None:
        self._default_token = token

    def delete_default_token(self) -> None:
        self._default_token = None

    def named_tokens(self) -> Dict[str, Token]:
        return self._named_tokens

    def get_named_token(self, name: str) -> Optional[Token]:
        return self._named_tokens.get(name)

    def set_named_token(self, name: str, token: Token) -> None:
        self._named_tokens[name] = token

    def delete_named_token(self, name: str) -> None:
        self._named_tokens.pop(name, None)  # ignore nonexistent


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
        with contextlib.suppress(Exception):
            os.unlink(temp_file.name)

import json
import os
import sys


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


def stdout_to_binary():
    """
    Ensure that stdout is in binary mode on windows
    """
    if sys.platform == 'win32':
        import msvcrt
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


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

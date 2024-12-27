import sys

from git_remote_dropbox.cli.common import (
    error,
    get_helper,
)
from git_remote_dropbox.util import (
    Level,
    stdout_to_binary,
)


def main() -> None:
    """
    Main entry point for git-remote-dropbox Git remote helper.
    """
    # configure system
    stdout_to_binary()

    url = sys.argv[2]
    helper = get_helper(url)
    try:
        helper.run()
    except Exception:
        if helper.verbosity >= Level.DEBUG:
            raise  # re-raise exception so it prints out a stack trace
        error("unexpected exception (run with -v for details)")
    except KeyboardInterrupt:
        # exit silently with an error code
        sys.exit(1)

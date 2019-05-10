from git_remote_dropbox.util import (
    Config,
    Level,
    stderr,
    stdout_to_binary,
)
from git_remote_dropbox.helper import Helper

import os
import sys
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse


def main():
    """
    Main entry point for git-remote-dropbox Git remote helper.
    """
    # configure system
    stdout_to_binary()

    url = sys.argv[2]
    # urls are one of:
    # dropbox:///path/to/repo
    # dropbox://username@/path/to/repo
    # dropbox://:token@/path/to/repo
    url = urlparse(url)
    if url.scheme != 'dropbox':
        stderr('error: URL must start with the "dropbox://" scheme\n')
        exit(1)
    if url.netloc:
        if not url.username and not url.password:
            # user probably put in something like "dropbox://path/to/repo"
            # missing the third "/"
            stderr('error: URL with no username or token must start with "dropbox:///"\n')
            exit(1)
        if url.username and url.password:
            # user supplied both username and token
            stderr('error: URL must not specify both username and token\n')
            exit(1)
    path = url.path.lower()  # dropbox is case insensitive, so we must canonicalize
    if path.endswith('/'):
        stderr('error: URL path must not have trailing slash\n')
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
    if not config and not url.password:
        stderr('error: missing config file: %s\n' % config_files[0])
        exit(1)
    try:
        if url.password:
            token = url.password
        elif not url.username:
            token = config['default']
        else:
            token = config[url.username]
    except KeyError:
        token_name = url.username or 'default'
        stderr('error: config file missing token for key "%s"\n' % token_name)
        exit(1)

    helper = Helper(token, path)
    try:
        helper.run()
    except Exception:
        if helper.verbosity >= Level.DEBUG:
            raise  # re-raise exception so it prints out a stack trace
        else:
            stderr('error: unexpected exception (run with -v for details)\n')
            exit(1)
    except KeyboardInterrupt:
        # exit silently with an error code
        exit(1)

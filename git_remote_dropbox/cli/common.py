from git_remote_dropbox.util import (
    Config,
    stderr,
)
from git_remote_dropbox.helper import Helper

import os
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse


def error(msg):
    stderr('error: %s\n' % msg)
    exit(1)


def get_helper(url):
    """
    Return a Helper configured to point at the given URL.

    URLs are one of:
        dropbox:///path/to/repo
        dropbox://username@/path/to/repo
        dropbox://:token@/path/to/repo
    """
    url = urlparse(url)
    if url.scheme != 'dropbox':
        error('URL must start with the "dropbox://" scheme')
    if url.netloc:
        if not url.username and not url.password:
            # user probably put in something like "dropbox://path/to/repo"
            # missing the third "/"
            error('URL with no username or token must start with "dropbox:///"')
        if url.username and url.password:
            # user supplied both username and token
            error('URL must not specify both username and token')
    path = url.path.lower()  # dropbox is case insensitive, so we must canonicalize
    if path.endswith('/'):
        error('URL path must not have trailing slash')

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
            error('malformed config file: %s' % config_file)
        except IOError:
            continue
        else:
            break
    if not config and not url.password:
        error('missing config file: %s' % config_files[0])
    try:
        if url.password:
            token = url.password
        elif not url.username:
            token = config['default']
        else:
            token = config[url.username]
    except KeyError:
        token_name = url.username or 'default'
        error('config file missing token for key "%s"' % token_name)

    return Helper(token, path)

import os
import sys
from typing import NoReturn
from urllib.parse import urlparse

import dropbox  # type: ignore

from git_remote_dropbox.helper import Helper
from git_remote_dropbox.util import (
    Config,
    LongLivedToken,
    Token,
    stderr,
)


def error(msg: str) -> NoReturn:
    stderr(f"error: {msg}\n")
    sys.exit(1)


def get_config() -> Config:
    config_files = [
        os.path.join(
            os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
            "git",
            "git-remote-dropbox.json",
        ),
        os.path.expanduser("~/.git-remote-dropbox.json"),
    ]
    for path in config_files:
        if os.path.exists(path):
            return Config(path)
    path = config_files[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return Config(path, create=True)


def check_connection(dbx: dropbox.Dropbox) -> None:
    dbx.users_get_current_account()


def get_helper(url: str) -> Helper:
    """
    Return a Helper configured to point at the given URL.

    URLs must be formatted as:
        dropbox:///path/to/repo
        dropbox://username@/path/to/repo
        dropbox://:token@/path/to/repo
    """
    parsed = urlparse(url)
    if parsed.scheme != "dropbox":
        error('URL must start with the "dropbox://" scheme')
    if parsed.netloc:
        if not parsed.username and not parsed.password:
            # user probably put in something like "dropbox://path/to/repo"
            # missing the third "/"
            error('URL with no username or token must start with "dropbox:///"')
        if parsed.username and parsed.password:
            # user supplied both username and token
            error("URL must not specify both username and token")
    path = parsed.path.lower()  # dropbox is case insensitive, so we must canonicalize
    if path.endswith("/"):
        error("URL path must not have trailing slash")

    config = get_config()
    token: Token
    if parsed.password:
        token = LongLivedToken(parsed.password)
    elif parsed.username:
        t = config.get_named_token(parsed.username)
        if not t:
            error(f"you must log in first with 'git dropbox login {parsed.username}'")
        token = t
    else:
        t = config.get_default_token()
        if not t:
            error("you must log in first with 'git dropbox login'")
        token = t
    try:
        check_connection(token.connect())
    except dropbox.exceptions.DropboxException:
        if parsed.password:
            error(
                "invalid inline legacy access token, try switching to short-lived access tokens with 'git dropbox login'"
            )
        elif parsed.username:
            error(f"invalid access token, try logging in again with 'git dropbox login {parsed.username}'")
        else:
            error("invalid access token, try logging in again with 'git dropbox login'")

    return Helper(token, path)

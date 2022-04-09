from git_remote_dropbox.util import (
    Config,
    stderr,
)
from git_remote_dropbox.helper import Helper
from git_remote_dropbox.constants import APP_KEY

import dropbox  # type: ignore

import os
from typing import Callable, NoReturn
from urllib.parse import urlparse


def error(msg: str) -> NoReturn:
    stderr("error: %s\n" % msg)
    exit(1)


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


def make_connector(token_type: str, token: str) -> Callable[[], dropbox.Dropbox]:
    if token_type == "long-lived":
        return lambda: dropbox.Dropbox(token)
    elif token_type == "refresh":
        return lambda: dropbox.Dropbox(oauth2_refresh_token=token, app_key=APP_KEY)
    else:
        raise ValueError("cannot handle token type: %s" % token_type)


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
    if parsed.password:
        token_type = "long-lived"
        token = parsed.password
    elif parsed.username:
        token_rep = config["tokens"]["named"].get(parsed.username)
        if not token_rep:
            error("you must log in first with 'git dropbox login %s'" % parsed.username)
        token_type, token = token_rep
    else:
        token_rep = config["tokens"]["default"]
        if not token_rep:
            error("you must log in first with 'git dropbox login'")
        token_type, token = token_rep
    connector = make_connector(token_type, token)
    try:
        check_connection(connector())
    except dropbox.exceptions.DropboxException:
        if parsed.password:
            error(
                "invalid inline legacy access token, try switching to short-lived access tokens with 'git dropbox login'"
            )
        elif parsed.username:
            error(
                "invalid access token, try logging in again with 'git dropbox login %s'"
                % parsed.username
            )
        else:
            error("invalid access token, try logging in again with 'git dropbox login'")

    return Helper(connector, path)

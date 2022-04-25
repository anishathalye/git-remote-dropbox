import git_remote_dropbox
from git_remote_dropbox import constants
from git_remote_dropbox import git
from git_remote_dropbox.util import RefreshToken, LongLivedToken
from git_remote_dropbox.cli.common import (
    error,
    get_helper,
    get_config,
)

import dropbox  # type: ignore

import argparse
import subprocess
import sys
from typing import Optional


def main() -> None:
    """
    Main entry point for git-dropbox program.
    """
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparsers.required = True
    subparsers.dest = "command"

    parser_set_head = subparsers.add_parser("set-head", help="set the default branch on the remote")
    parser_set_head.add_argument("remote", type=str, help="name of the remote")
    parser_set_head.add_argument("branch", type=str, help="name of the branch on the remote")

    parser_version = subparsers.add_parser(
        "version", help="print the version of git-remote-dropbox"
    )

    parser_login = subparsers.add_parser("login", help="log in to Dropbox")
    parser_login.add_argument("username", type=str, help="username/tag", nargs="?", default=None)

    parser_logout = subparsers.add_parser("logout", help="log out from Dropbox")
    parser_logout.add_argument("username", type=str, help="username/tag", nargs="?", default=None)

    parser_show_logins = subparsers.add_parser(
        "show-logins", help="show logged-in accounts and their usernames/tags"
    )

    args = parser.parse_args()

    if args.command == "set-head":
        set_head(args.remote, args.branch)
    elif args.command == "version":
        version()
    elif args.command == "login":
        login(args.username)
    elif args.command == "logout":
        logout(args.username)
    elif args.command == "show-logins":
        show_logins()


def set_head(remote: str, branch: str) -> None:
    """
    Set the default branch on the remote to point to branch.

    While almost all git-remote-dropbox functionality is fully safe under
    concurrent operation, this particular functionality is not safe under a
    particular kind of concurrent modification. In particular, if set-head is
    called with a branch that is concurrently deleted, then the operation fails
    (and notifies the user).
    """
    try:
        url = git.get_remote_url(remote)
    except subprocess.CalledProcessError:
        error("no such remote '%s'" % remote)
        sys.exit(1)
    helper = get_helper(url)

    remote_ref = "refs/heads/%s" % branch

    def branch_exists() -> bool:
        refs = helper.get_refs(False)
        for _, name in refs:
            if name == remote_ref:
                return True
        return False

    # check if target branch exists
    if not branch_exists():
        error("remote has no such ref '%s'" % remote_ref)
    # get current head
    old_head = helper.read_symbolic_ref("HEAD")
    if old_head and old_head[1] == remote_ref:
        error("remote HEAD is already '%s'" % remote_ref)
    rev = old_head[0] if old_head else None
    # write new head
    ok = helper.write_symbolic_ref("HEAD", remote_ref, rev=rev)
    if not ok:
        error("concurrent modification of remote HEAD detected (try again)")
    # ensure that target branch still exists
    if not branch_exists():
        # this should be a really rare occurrence: have the user fix it up if
        # it happens
        error("remote ref '%s' was concurrently deleted: remote HEAD needs to be fixed (try again)")
    print("Updated remote HEAD to '%s'." % remote_ref)


def login(username: Optional[str]) -> None:
    auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
        constants.APP_KEY, use_pkce=True, token_access_type="offline"
    )
    authorize_url = auth_flow.start()
    print("Logging in to Dropbox using OAuth...")
    print("1. Go to: %s" % authorize_url)
    print('2. Click "Allow" (you might have to log in first)')
    print("3. Copy the authorization code")
    auth_code = input("Enter authorization code: ").strip()
    try:
        oauth_result = auth_flow.finish(auth_code)
        token = RefreshToken(oauth_result.refresh_token)
    except Exception:
        error("failed to log in; did you copy the code correctly?")

    config = get_config()
    if username is None:
        config.set_default_token(token)
    else:
        config.set_named_token(username, token)
    config.save()

    if username is None:
        example = "dropbox:///path/to/repo"
    else:
        example = "dropbox://%s@/path/to/repo" % username
    print("Successfully logged in! You can now add Dropbox remotes like '%s'" % example)


def logout(username: Optional[str]) -> None:
    config = get_config()
    if username is None:
        config.delete_default_token()
        config.save()
        print("Logged out!")
    else:
        config.delete_named_token(username)
        config.save()
        print("Logged out %s!" % username)


def show_logins() -> None:
    config = get_config()
    token = config.get_default_token()
    if token is not None:
        deprecated = ""
        if isinstance(token, LongLivedToken):
            deprecated = " [deprecated long-lived token]"
        print("(default user)%s" % deprecated)
    for username, token in config.named_tokens().items():
        deprecated = ""
        if isinstance(token, LongLivedToken):
            deprecated = " [deprecated long-lived token]"
        print("%s%s" % (username, deprecated))


def version() -> None:
    print("git-remote-dropbox %s" % git_remote_dropbox.__version__)

import argparse
import subprocess
import sys
from typing import Optional

import dropbox  # type: ignore

import git_remote_dropbox
from git_remote_dropbox import constants, git
from git_remote_dropbox.cli.common import (
    error,
    get_config,
    get_helper,
)
from git_remote_dropbox.util import LongLivedToken, RefreshToken


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

    parser_version = subparsers.add_parser(  # noqa: F841
        "version", help="print the version of git-remote-dropbox"
    )

    parser_login = subparsers.add_parser("login", help="log in to Dropbox")
    parser_login.add_argument("username", type=str, help="username/tag", nargs="?", default=None)

    parser_logout = subparsers.add_parser("logout", help="log out from Dropbox")
    parser_logout.add_argument("username", type=str, help="username/tag", nargs="?", default=None)

    parser_show_logins = subparsers.add_parser(  # noqa: F841
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
        error(f"no such remote '{remote}'")
        sys.exit(1)
    helper = get_helper(url)

    remote_ref = f"refs/heads/{branch}"

    def branch_exists() -> bool:
        refs = helper.get_refs(for_push=False)
        return any(name == remote_ref for _, name in refs)

    # check if target branch exists
    if not branch_exists():
        error(f"remote has no such ref '{remote_ref}'")
    # get current head
    old_head = helper.read_symbolic_ref("HEAD")
    if old_head and old_head[1] == remote_ref:
        error(f"remote HEAD is already '{remote_ref}'")
    rev = old_head[0] if old_head else None
    # write new head
    ok = helper.write_symbolic_ref("HEAD", remote_ref, rev=rev)
    if not ok:
        error("concurrent modification of remote HEAD detected (try again)")
    # ensure that target branch still exists
    if not branch_exists():
        # this should be a really rare occurrence: have the user fix it up if
        # it happens
        error(f"remote ref '{remote_ref}' was concurrently deleted: remote HEAD needs to be fixed (try again)")
    print(f"Updated remote HEAD to '{remote_ref}'.")


def login(username: Optional[str]) -> None:
    auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
        constants.APP_KEY,
        use_pkce=True,
        token_access_type="offline",  # noqa: S106
    )
    authorize_url = auth_flow.start()
    print("Logging in to Dropbox using OAuth...")
    print(f"1. Go to: {authorize_url}")
    print('2. Click "Allow" (you might have to log in first)')
    print("3. Copy the authorization code")
    auth_code = input("Enter authorization code: ").strip()
    try:
        oauth_result = auth_flow.finish(auth_code)
        token = RefreshToken(oauth_result.refresh_token)
    except Exception:  # noqa: BLE001
        error("failed to log in; did you copy the code correctly?")

    config = get_config()
    if username is None:
        config.set_default_token(token)
    else:
        config.set_named_token(username, token)
    config.save()

    example = "dropbox:///path/to/repo" if username is None else f"dropbox://{username}@/path/to/repo"
    print(f"Successfully logged in! You can now add Dropbox remotes like '{example}'")


def logout(username: Optional[str]) -> None:
    config = get_config()
    if username is None:
        config.delete_default_token()
        config.save()
        print("Logged out!")
    else:
        config.delete_named_token(username)
        config.save()
        print(f"Logged out {username}!")


def show_logins() -> None:
    config = get_config()
    token = config.get_default_token()
    if token is not None:
        deprecated = ""
        if isinstance(token, LongLivedToken):
            deprecated = " [deprecated long-lived token]"
        print(f"(default user){deprecated}")
    for username, token in config.named_tokens().items():
        deprecated = ""
        if isinstance(token, LongLivedToken):
            deprecated = " [deprecated long-lived token]"
        print(f"{username}{deprecated}")


def version() -> None:
    print(f"git-remote-dropbox {git_remote_dropbox.__version__}")

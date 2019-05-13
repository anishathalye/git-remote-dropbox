import git_remote_dropbox.git as git
from git_remote_dropbox.cli.common import (
    error,
    get_helper,
)

import argparse
import subprocess


def main():
    """
    Main entry point for git-dropbox-manage program.
    """
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparsers.required = True
    subparsers.dest = 'command'

    parser_set_head = subparsers.add_parser('set-head', help='set the default branch on the remote')
    parser_set_head.add_argument('remote', type=str, help='name of the remote')
    parser_set_head.add_argument('branch', type=str, help='name of the branch on the remote')

    args = parser.parse_args()

    if args.command == 'set-head':
        set_head(args.remote, args.branch)


def set_head(remote, branch):
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
        error('no such remote \'%s\'' % remote)
        exit(1)
    helper = get_helper(url)

    remote_ref = 'refs/heads/%s' % branch

    def branch_exists():
        refs = helper.get_refs(False)
        for _, name in refs:
            if name == remote_ref:
                return True
        return False

    # check if target branch exists
    if not branch_exists():
        error('remote has no such ref \'%s\'' % remote_ref)
    # get current head
    old_head = helper.read_symbolic_ref('HEAD')
    if old_head and old_head[1] == remote_ref:
        error('remote HEAD is already \'%s\'' % remote_ref)
    rev = old_head[0] if old_head else None
    # write new head
    ok = helper.write_symbolic_ref('HEAD', remote_ref, rev=rev)
    if not ok:
        error('concurrent modification of remote HEAD detected (try again)')
    # ensure that target branch still exists
    if not branch_exists():
        # this should be a really rare occurrence: have the user fix it up if
        # it happens
        error('remote ref \'%s\' was concurrently deleted: remote HEAD needs to be fixed (try again)')
    print('Updated remote HEAD to \'%s\'.' % remote_ref)

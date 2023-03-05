# git-remote-dropbox [![Build Status](https://github.com/anishathalye/git-remote-dropbox/workflows/CI/badge.svg)](https://github.com/anishathalye/git-remote-dropbox/actions?query=workflow%3ACI) [![pypi](https://img.shields.io/pypi/v/git-remote-dropbox.svg)](https://pypi.org/pypi/git-remote-dropbox/)

git-remote-dropbox is a transparent bidirectional bridge between Git and
Dropbox. It lets you use a Dropbox folder or a shared folder as a Git remote!

---

This Git remote helper makes Dropbox act like a _true Git remote_. It maintains
_all guarantees_ that are provided by a traditional Git remote while using
Dropbox as a backing store. This means that it works correctly even when there
are multiple people operating on the repository at once, making it possible to
use a Dropbox shared folder as a Git remote for collaboration.

Once the helper is installed, using it is as simple as adding a remote like
`dropbox:///path/to/repo`.

To clone repositories in folders or shared folders mounted in your Dropbox, you
can run:

```bash
git clone "dropbox:///path/to/repo"
```

To add a remote to an existing local repository, you can run:

```bash
git remote add origin "dropbox:///path/to/repo"
```

The repository directory will be created automatically the first time you push.

After adding the remote, you can treat it just like a regular Git remote. The
Dropbox-backed remote supports all operations that regular remotes support, and
it provides identical guarantees in terms of atomicity even when there are
concurrent operations, even when using a shared folder.

## Setup

### Install git-remote-dropbox

1. Prerequisites:
   1. `python` and matching `pip`
   2. `git`
2. Install this package with `pip install git-remote-dropbox`. Use `which git-remote-dropbox` to make sure it's available via `$PATH`. If not, edit `$PATH` appropriately.

### Log in to Dropbox

Run `git dropbox login` and follow the instructions to authenticate with OAuth
and log in to your Dropbox account.

## Sharing

The above gives you a way to create a Git repository on Dropbox and use it from multiple machines that you own. In other words, it's a convenient way to share a remote with your laptop and your desktop.

If you want to share with other people, you should explicitly share (e.g. via the Dropbox website) the root folder of the repo with your collaborators. Then they should also install git-remote-dropbox and log in *with their own account*.

## Multiple Accounts

git-remote-dropbox supports using multiple Dropbox accounts. You can have named
accounts with `git dropbox login <username>`. **These usernames are unrelated
to your Dropbox login; you can choose whatever names you want to organize your
accounts, e.g. "work".**

You can tell git-remote-dropbox to use a particular account by setting the git
remote URL appropriately, specifying a username like:
`dropbox://username@/path/to/repo`.

## Repository Manager

In addition to the git remote helper, git-remote-dropbox comes with an
additional tool to manage your logins and repositories on Dropbox. This tool
can be invoked as `git dropbox`.

The tool supports the following commands:

- `git dropbox login [username]`: log in, either with the default account (no
  need to specify a username in remote), or with an alias (for multi-account
  support)
- `git dropbox logout [username]`: log out
- `git dropbox show-logins`: list logged-in accounts
- `git dropbox set-head <remote> <branch>`: set default branch on the remote
- `git dropbox version`: show version

## Notes

- Do not directly interact with Git repositories in your Dropbox folder -always
  use git-remote-dropbox. If you're using the Dropbox client to sync files,
  it's a good idea to use [selective
  sync](https://help.dropbox.com/installs-integrations/sync-uploads/selective-sync-overview)
  and disable syncing of the folder containing the repository to avoid any
  unexpected conflicts, just in case.

- git-remote-dropbox does not use the Dropbox desktop client - it uses the API
  directly. It does not require that the desktop client is installed.

- The remote helper does not support shallow cloning.

- Cloning a repository or fetching a lot of objects produces lots of loose
  objects. To save space in the local repository, run `git gc --aggressive`.

- If the remote HEAD (default branch on the remote) is not set, after cloning a
  repository from Dropbox, Git will not automatically check out a branch. To
  check out a branch, run `git checkout <branch>`. To set the default branch on
  the remote, use the [`git dropbox`](#repository-manager) command.

## FAQ

**Why shouldn't I keep my Git repository in Dropbox and let the client sync
it?**

There seem to be a lot of articles on the Internet recommending this as a good
workflow. However, this is *not a good idea*! The desktop client is not aware
of how Git manages it's on-disk format, so if there are concurrent changes or
delays in syncing, it's possible to have conflicts that result in a corrupted
Git repository. This may be uncommon with the way the timing works out in the
single user case, but it's still not safe!

**Why shouldn't I keep a bare Git repository in a Dropbox shared folder, use it
as a folder-based Git remote, and sync it with the desktop client?**

There seem to be some articles on the Internet suggesting that this is a good
idea. It's not. Using the desktop client to sync a bare Git repository is not
safe. Concurrent changes or delays in syncing can result in a corrupted Git
repository.

**How can I access / recover my repository from Dropbox without using the
git-remote-dropbox helper?**

Because git-remote-dropbox uses an on-disk format that's compatible with Git,
accessing your repository without using the helper is easy:

1. Download the repository data (a directory containing the `objects` and
   `refs` directories) from Dropbox.
2. Make a new directory and initialize an empty Git repository in the
   directory.
3. Overwrite `.git/refs` and `.git/objects` in your newly initialized
   repository with the data downloaded from Dropbox (using a command like `rm
   -rf .git/{refs,objects} && cp -r /path/to/data/{refs,objects} .git/`).
4. Check out a branch (using a command like `git checkout -f master`).
5. Optionally, run `git gc --aggressive` to save disk space in your local
   repository.

**How do I use git-remote-dropbox from behind a proxy server?**

You can use git-remote-dropbox from behind a proxy server by setting the
`HTTP_PROXY` and `HTTPS_PROXY` environment variables. See
[here](http://docs.python-requests.org/en/latest/user/advanced/#proxies) for
more details.

**How do I use git-remote-dropbox with submodules?**

You can allow this by setting
[`protocol.dropbox.allow`](https://git-scm.com/docs/git-config#Documentation/git-config.txt-protocolltnamegtallow)
to `always`:

```bash
git config --global --add protocol.dropbox.allow always
```

## Design

To read about the design of git-remote-dropbox, see [DESIGN.md](DESIGN.md).
This could be especially useful if you're thinking about contributing to the
project.

## Contributing

Do you have ideas on how to improve git-remote-dropbox? Have a feature request,
bug report, or patch? Great! See [CONTRIBUTING.md](CONTRIBUTING.md) for
information on what you can do about that.

## License

Copyright (c) Anish Athalye. Released under the MIT License. See
[LICENSE.md](LICENSE.md) for details.

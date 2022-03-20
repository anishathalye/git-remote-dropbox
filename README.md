# git-remote-dropbox [![Build Status](https://github.com/anishathalye/git-remote-dropbox/workflows/CI/badge.svg)](https://github.com/anishathalye/git-remote-dropbox/actions?query=workflow%3ACI)

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

### A. Get access token from Dropbox

1. Go to the Dropbox [app console](https://www.dropbox.com/developers/apps) (may require login).

2. Click "Create app".

3. Select "Scoped access" (you don't have a choice).

4. Select "Full Dropbox".

5. Name your app (e.g. "Git Remote"; you need a unique name, but it doesn't matter what name you choose).

6. Click "Create app". You will now see a configuration page. Make sure you are on the "Settings" tab.

7. Scroll down to the "OAuth 2" section, and change the "Access token expiration" to "No expiration".

8. On the "Permissions" tab, under "Files and folders" select `files.metadata.write` (which also selects `files.metadata.read`), `files.content.write`, and `files.content.read`. Click "Submit" at the bottom. (You must make sure to do this _before_ the next step, because changing permissions does not affect existing access tokens.)

9. Back on the "Settings" tab, click "Generate" under the "Generated access token" heading. Copy the generated token token. Note that it is longer than the display, so exercise care in copying _all_ of it. Save the token in either `~/.config/git/git-remote-dropbox.json` or `~/.git-remote-dropbox.json`. The file looks like:
   ```json
   {
      "default": "xxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   }
   ```

### B. Local software installation

1. Prerequisites:
   1. `python` and matching `pip`
   2. `git`
2. Install this package with `pip install git-remote-dropbox`. Use `which git-remote-dropbox` to make sure it's available via `$PATH`. If not, edit `$PATH` appropriately.

### __Note about access tokens__

1. The access token you have will now enable access to your entire Dropbox, from any machine. It is valid until you either delete the app or regenerate the access token. Keep this token a secret. In particular, you should **NOT** share this for making a shared repo (see [Sharing](#sharing) below for the right way to do that).

2. If you have multiple Dropbox accounts, this token will access only the one that was logged in when you created the Dropbox app. You can specify alternate ones in the config file and reference them via the pathname (see [Multiple Accounts](#multiple-accounts) below).

## Sharing

The above gives you a way to create a Git repository on Dropbox and use it from multiple machines that you own (that have the access token). In other words, it's a convenient way to share a remote with your laptop and your desktop.

If you want to share with other people, you should explicitly share (e.g. via the Dropbox website) the root folder of the repo with your collaborators. Then they should follow steps (A) and (B) above to generate their own access token to use `git-remote-dropbox`. **Collaborators do not need _your_ access token.**

## Multiple Accounts

`git-remote-dropbox` supports using multiple Dropbox accounts. You can create
OAuth tokens for different accounts and add them all to the config file, using
a user-defined username as the key:

```json
{
    "alice": "xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx",
    "ben": "xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx",
    "charlie": "xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx"
}
```

You can tell `git-remote-dropbox` to use the token corresponding to `username` by
specifying a URL like `dropbox://username@/path/to/repo`.

You can also specify the token inline by using a URL like
`dropbox://:token@/path/to/repo`.

## Repository Manager

In addition to the git remote helper, `git-remote-dropbox` comes with an
additional tool to manage repositories on Dropbox. This tool can be invoked as
`git dropbox`. You can also create an alias for it with the following:

Currently the tool supports a single subcommand, `git dropbox set-head <remote>
<branch>`, that can be used to set the default branch on the remote.

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

## Design

To read about the design of git-remote-dropbox, see [DESIGN.md](DESIGN.md).
This could be especially useful if you're thinking about contributing to the
project.

## Contributing

Do you have ideas on how to improve git-remote-dropbox? Have a feature request,
bug report, or patch? Great! See [CONTRIBUTING.md](CONTRIBUTING.md) for
information on what you can do about that.

## License

Copyright (c) 2015-2021 Anish Athalye. Released under the MIT License. See
[LICENSE.md](LICENSE.md) for details.

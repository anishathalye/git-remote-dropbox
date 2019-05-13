git-remote-dropbox
==================

git-remote-dropbox is a transparent bidirectional bridge between Git and
Dropbox. It lets you use a Dropbox folder or a shared folder as a Git remote!

.. image:: https://travis-ci.org/anishathalye/git-remote-dropbox.svg?branch=master
   :target: https://travis-ci.org/anishathalye/git-remote-dropbox

----

This Git remote helper makes Dropbox act like a *true Git remote*. It maintains
*all guarantees* that are provided by a traditional Git remote while using
Dropbox as a backing store. This means that it works correctly even when there
are multiple people operating on the repository at once, making it possible to
use a Dropbox shared folder as a Git remote for collaboration.

Once the helper is installed, using it is as simple as adding a remote like
``dropbox:///path/to/repo``.

To clone repositories in folders or shared folders mounted in your Dropbox, you
can run:

.. code:: bash

    git clone "dropbox:///path/to/repo"

To add a remote to an existing local repository, you can run:

.. code:: bash

    git remote add origin "dropbox:///path/to/repo"

The repository directory will be created automatically the first time you push.

After adding the remote, you can treat it just like a regular Git remote. The
Dropbox-backed remote supports all operations that regular remotes support, and
it provides identical guarantees in terms of atomicity even when there are
concurrent operations, even when using a shared folder.

Setup
-----

1. Install the helper with ``pip install git-remote-dropbox``.

2. Generate an OAuth 2 token by going to the `app console
   <https://www.dropbox.com/developers/apps>`__, creating a Dropbox API app
   with "Full Dropbox" access (or "App folder" access if you prefer, if you're
   not going to be using Dropbox's sharing features to use git-remote-dropbox
   in a multi-user setup), and generating an access token for yourself.

3. Save your OAuth token in ``~/.config/git/git-remote-dropbox.json`` or
   ``~/.git-remote-dropbox.json``. The file should look something like this:

   .. code:: json

       {
           "default": "xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx"
       }

Multiple Accounts
-----------------

git-remote-dropbox supports using multiple Dropbox accounts. You can create
OAuth tokens for different accounts and add them all to the config file, using
a user-defined username as the key:

.. code:: json

    {
        "alice": "xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx",
        "ben": "xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx",
        "charlie": "xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx"
    }

You can tell git-remote-dropbox to use the token corresponding to ``username``
by specifying a URL like ``dropbox://username@/path/to/repo``.

You can also specify the token inline by using a URL like
``dropbox://:token@/path/to/repo``.

Repository Manager
------------------

In addition to the git remote helper, git-remote-dropbox comes with an
additional tool to manage repositories on Dropbox. This tool can be invoked as
``git-dropbox-manager``. You can also create an alias for it with the
following:

.. code:: bash

    git config --global alias.dropbox '!git-dropbox-manage'

With this configuration, the tool can be invoked as ``git dropbox``.

Currently the tool supports a single subcommand, ``git dropbox set-head
<remote> <branch>``, that can be used to set the default branch on the remote.

Notes
-----

- Do not directly interact with Git repositories in your Dropbox folder -
  always use git-remote-dropbox. If you're using the Dropbox client to sync
  files, it's a good idea to use `selective sync
  <https://www.dropbox.com/en/help/175#select>`__ and disable syncing of the
  folder containing the repository to avoid any unexpected conflicts, just in
  case.

- git-remote-dropbox does not use the Dropbox desktop client - it uses the API
  directly. It does not require that the desktop client is installed.

- The remote helper does not support shallow cloning.

- Cloning a repository or fetching a lot of objects produces lots of loose
  objects. To save space in the local repository, run ``git gc --aggressive``.

- After cloning a repository from Dropbox, Git will not automatically check out
  a branch. To check out a branch, run ``git checkout <branch>``.

FAQ
---

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

1. Download the repository data (a directory containing the ``objects`` and
   ``refs`` directories) from Dropbox.

2. Make a new directory and initialize an empty Git repository in the
   directory.

3. Overwrite ``.git/refs`` and ``.git/objects`` in your newly initialized
   repository with the data downloaded from Dropbox (using a command like ``rm
   -rf .git/{refs,objects} && cp -r /path/to/data/{refs,objects} .git/``).

4. Check out a branch (using a command like ``git checkout -f master``).

5. Optionally, run ``git gc --aggressive`` to save disk space in your local
   repository.

**How do I use git-remote-dropbox from behind a proxy server?**

You can use git-remote-dropbox from behind a proxy server by setting the
``HTTP_PROXY`` and ``HTTPS_PROXY`` environment variables. See `here
<http://docs.python-requests.org/en/latest/user/advanced/#proxies>`__ for more
details.

Design
------

To read about the design of git-remote-dropbox, see `DESIGN.rst <DESIGN.rst>`__.
This could be especially useful if you're thinking about contributing to the
project.

Contributing
------------

Do you have ideas on how to improve git-remote-dropbox? Have a feature request,
bug report, or patch? Great! See `CONTRIBUTING.md <CONTRIBUTING.md>`__ for
information on what you can do about that.

Packaging
---------

1. Update version information.

2. Build the package using ``python setup.py sdist bdist_wheel``.

3. Sign and upload the package using ``twine upload -s dist/*``.

License
-------

Copyright (c) 2015-2019 Anish Athalye. Released under the MIT License. See
`LICENSE.rst <LICENSE.rst>`__ for details.

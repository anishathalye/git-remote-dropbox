# Design

Many things are designed the way they are in order to have the same semantics
and guarantees as a regular Git remote *without running any special code on the
server side*.

git-remote-dropbox is a [Git remote helper][gitremote-helper].

To support all Git operations, we need to support one capability for pushing
and one capability for fetching. For our use case, the best way to do this is
to implement the `push` and `fetch` capabilities. Alternatives are better
suited for interacting with foreign version control systems.

## Repository Layout

We store repository data on Dropbox in a similar way to how Git stores data on
disk. In particular, we store [references][git-references] and [loose
objects][git-objects], which make up all information that needs to be stored on
the server. The repository folder layout looks almost identical to a bare Git
repository.

### References

References are stored in `refs` (relative to the repository root). The format
of references is identical to how Git stores references in the `.git`
directory. For example, the `master` ref would be stored in
`refs/heads/master`, and the file would contain the SHA1 hash corresponding to
the commit that the master branch points to.

### Symbolic References

Symbolic references are stored in the repository root. The format of the
symbolic refs is identical to how Git stores symbolic refs in the `.git`
directory. For example, `HEAD` would be stored in `HEAD`, and if it is pointing
to `refs/heads/master`, the file would contain `ref: refs/heads/master`.

### Objects

Objects are stored in `objects` (relative to the repository root). The path and
file name of objects is identical to how Git stores loose objects in the `.git`
directory. For example, an object with the hash
`5f1594aa9545fab32ae35276cb03002f29ce9b79` would be stored in
`objects/5f/1594aa9545fab32ae35276cb03002f29ce9b79`.

The files may not actually be identical on disk due to differences in DEFLATE
compression, but in fact, if the files are copied as-is into a local Git
repository, Git will recognize the files as valid.

git-remote-dropbox stores all objects as loose objects - it does not pack
objects. This means that we do not perform delta compression. In addition, we
do not perform garbage collection of dangling objects.

## Push

To push a ref, we need to ensure that the server has all objects reachable from
the ref, and we need to update the ref in a safe way such that concurrent
operations don't cause problems.

### Objects

We can use the `git rev-list --objects <ref>` command to get all the objects
reachable from `ref`. We could just upload all of these, but that would be a
lot of unnecessary work, equivalent to uploading the entire repository for
every push.

Instead, we can figure out exactly what objects the server is missing, and then
we can upload only those objects. We can get a list of refs present on the
server, and then we can compute which objects the server is missing by using
`git rev-list --objects <ref> ^<exclude>`, where `exclude` is a ref present on
the server. We can do this with multiple exclusions too.

Once we have the list of objects that the server is missing, we can upload them
all. Because objects are content-addressed, we don't need to worry about
conflicts.

### Refs

Pushing the ref itself is slightly more complicated. Once all the objects are
present, we need to update the remote ref atomically. First, we check if we're
performing a fast-forward, and then we perform a compare-and-swap operation. If
there are any concurrent changes, we require the user to fetch before
continuing, maintaining safety.

We can perform a compare-and-swap operation in Dropbox by using the "update"
write mode with a specific revision number.

If we're doing a force push, the process is simpler - we can just overwrite the
ref with the new value.

If we're deleting a branch, we make sure that we're not deleting the default
branch before deleting the ref.

### Symbolic refs

The symbolic ref `HEAD` is set upon repository creation.

## Fetch

For fetching remote refs, we could just fetch everything from the `objects`
directory. However, that would be really slow because of all the unnecessary
work involved, especially when fetching small changes.

Instead, we fetch refs by recursively downloading all of the objects reachable
from the object pointed to by the ref, terminating branches of the recursion
when we reach objects that we already have locally, provided that we have the
full history from that point on.

[gitremote-helper]: https://www.kernel.org/pub/software/scm/git/docs/gitremote-helpers.html
[git-objects]: https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
[git-references]: https://git-scm.com/book/en/v2/Git-Internals-Git-References

# Development

git-remote-dropbox uses the [Hatch] project manager ([installation instructions][hatch-install]).

Hatch automatically manages dependencies and runs type checking, formatting/linting, and other operations in isolated [environments][hatch-environments].

[Hatch]: https://hatch.pypa.io/
[hatch-install]: https://hatch.pypa.io/latest/install/
[hatch-environments]: https://hatch.pypa.io/latest/environment/

## Testing

git-remote-dropbox has integration tests written in shell scripts. The tests exercise git-remote-dropbox via git operations, so the tests interact with the filesystem. For this reason, it is recommended that tests are run inside a Docker container (or in CI).

To run the tests, first start a Docker container:

```bash
docker run -it --rm -v "${PWD}:/git-remote-dropbox" -w /git-remote-dropbox python:3.13-bookworm /bin/bash
```

Now, inside the Docker container, install the git-remote-dropbox package:

```bash
pip install -e .
```

Next, set the `DROPBOX_TOKEN` environment variable (to your long-lived access token). This is required because the tests actually interact with the real Dropbox API.

```bash
export DROPBOX_TOKEN='...'
```

Finally, run the tests:

```bash
tests/test.sh
```

## Type checking

You can run the [mypy static type checker][mypy] with:

```bash
hatch run types:check
```

[mypy]: https://mypy-lang.org/

## Formatting and linting

You can run the [Ruff][ruff] formatter and linter with:

```bash
hatch fmt
```

This will automatically make [safe fixes][fix-safety] to your code. If you want to only check your files without making modifications, run `hatch fmt --check`.

[ruff]: https://github.com/astral-sh/ruff
[fix-safety]: https://docs.astral.sh/ruff/linter/#fix-safety

## Packaging

You can use [`hatch build`][hatch-build] to create build artifacts, a [source distribution ("sdist")][sdist] and a [built distribution ("wheel")][bdist].

You can use [`hatch publish`][hatch-publish] to publish build artifacts to [PyPI][pypi].

[hatch-build]: https://hatch.pypa.io/latest/build/
[sdist]: https://packaging.python.org/en/latest/glossary/#term-Source-Distribution-or-sdist
[bdist]: https://packaging.python.org/en/latest/glossary/#term-Built-Distribution
[hatch-publish]: https://hatch.pypa.io/latest/publish/
[pypi]: https://pypi.org/

## Continuous integration

Testing, type checking, and formatting/linting is [checked in CI][ci].

[ci]: .github/workflows/ci.yml

# Prepare a release

Create a GitHub release after the version, documentation, tests, and package have been checked.
This project creates a release from a Git tag. It does not publish to PyPI.

## Check the release candidate

From the repository root, install the locked development and documentation dependencies. Then run
the same checks used by the release workflow:

```console
$ uv sync --all-extras --group docs --locked --no-editable
$ uv run --no-sync ruff check .
$ uv run --no-sync ruff format --check .
$ uv run --no-sync ty check
$ uv run --no-sync pytest
$ uv run --no-sync zensical build --clean --strict
```

Pytest imports the checked-out `src/` tree. This catches source changes even when the environment
is non-editable. The release workflow separately installs the built wheel in a new environment to
check the package that users would receive.

## Create the tag

Set the version in `pyproject.toml`, update any user-facing release notes, and commit those changes.
The tag must use the exact same version with a leading `v`. For example, package version `0.1.3`
requires tag `v0.1.3`:

```console
$ git tag -a v0.1.3 -m "Release v0.1.3"
$ git push origin v0.1.3
```

Protect version tags with a repository ruleset for `v*`. Prevent updates and deletions after a tag
is created. A version tag identifies one source revision and must never be moved to another commit.

The tag starts the release workflow. It checks the tag and package version, runs quality checks,
tests, and a strict documentation build, builds a wheel and source archive, and installs the wheel
in a clean environment for a command-line smoke test. It also creates a GitHub artifact attestation
before creating the GitHub release.

## Check the result

Open the workflow run from the tag. The GitHub release contains the wheel and source archive.
Published releases and their assets are immutable: if a release already exists for the tag, the
workflow stops with a clear error and changes nothing. It never uploads anything to PyPI.

If an attempt fails before a GitHub release exists, keep the tag unchanged. Use **Re-run failed
jobs** for a temporary service failure. If the fix changes source, configuration, or package
contents, commit it with the next version and create a new protected tag. Do not delete, force-push,
or move the failed tag; the workflow performs no destructive recovery automatically.

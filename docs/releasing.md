# Releasing

Run the test suite and review the source for credentials/private data. Keep `pyproject.toml`,
`__init__.py`, `install.sh`, Docker/Compose tags and README installer URLs on the same version.

```bash
python -m pip install '.[mcp,dev]'
ruff check src tests
pytest -q
python -m build
git tag v1.0.1
git push origin HEAD --tags
```

The tag workflow runs CI before creating a release. It includes wheel, sdist, source zip and
SHA256SUMS, then builds the GHCR image. The repository's Actions token needs `contents: write` and
`packages: write`, declared in the workflow. No PyPI credentials are needed: the installer uses the
GitHub Release wheel. GHCR packages may need their visibility changed to public in GitHub settings;
the source-build Docker route always remains available.

To publish manually after tests (requires GitHub CLI login):

```bash
python scripts/package_release.py
gh repo create Ancientshi/GeneralAgentOS --public --source=. --remote=origin --push
git tag v1.0.1
git push origin v1.0.1
```

Inspect the Actions run and release assets before advertising the online installer. To retry a
failed packaging job, re-run that Actions job; do not move an existing release tag.

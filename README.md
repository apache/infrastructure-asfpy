# asfpy - ASF Infrastructure Common Library for Python functions
<a href="https://pypi.org/project/asfpy"><img alt="PyPI" src="https://img.shields.io/pypi/v/asfpy.svg?color=blue&maxAge=600" /></a>
<a href="https://pypi.org/project/asfpy"><img alt="PyPI - Python Versions" src="https://img.shields.io/pypi/pyversions/asfpy.svg?maxAge=600" /></a>
<a href="https://github.com/apache/infrastructure-asfpy/actions/workflows/unittest.yml?query=branch%3Amain"><img alt="Unit Tests" src="https://github.com/apache/infrastructure-asfpy/actions/workflows/unittest.yml/badge.svg?branch=main" /></a>
<a href="https://github.com/apache/infrastructure-asfpy/blob/main/LICENSE"><img alt="Apache License" src="https://img.shields.io/github/license/apache/infrastructure-asfpy" /></a>

This Python library contains features commonly used at the Apache Software Foundation.

(For asfpy 0.37 and below, look at our old [Subversion repository](https://svn.apache.org/repos/infra/infrastructure/trunk/projects/asfpy/))

## Package Documention
- `aioldap`: asynchronous LDAP client (_documentation TBD_)
- `clitools`: LDAP work via command line tooling (_documentation TBD_)
- `crypto`: helper for ED25519 work (_documentation TBD_)
- `db`: high performance simplified SQLite client (_documentation TBD_)
- `justone`: helper to ensure only one long-running process is operating (_documentation TBD_)
- `messaging`: helpers to send email (_documentation TBD_)
- `pubsub`: client for subscribing to the ASF pubsub service (_documentation TBD_)
- `sqlite`: document-based CRUD using SQLite (_documentation TBD_)
- `stopwatch`: debug/logging timing for Python code. See [documentation](stopwatch.md)
- `syslog`: redirect `print()` to syslog (_documentation TBD_)
- `twatcher`: watch EZT emplates for edits, then reload (_documentation TBD_)
- `whoami`: fetch hostname of box (_documentation TBD_)

--
- `daemon`: **DEPRECATED** old code to spawn a daemon (obsoleted by pipservice)
- `ldapadmin`: **DEPRECATED** internal ASF infra tooling (moved to internal infra)

----

## Building asfpy package

Prerequisites:

- `poetry`: install e.g. with pipx `pipx install poetry`

Building the package:

```console
$ poetry build
```

Running the tests:

```console
$ poetry run pytest
```

## Installation

Create and activate a virtual environment and then install `asfpy` using [pip](https://pip.pypa.io):

```console
$ pip install "asfpy"
```

Note: Adding `[ldap]` or `[aioldap]` extras will install optional dependencies for LDAP support that will 
require additional [system dependencies](https://github.com/noirello/bonsai?tab=readme-ov-file#requirements-for-building):

```console
$ pip install "asfpy[aioldap]"
```

## Publishing a new asfpy package

Create an account on https://pypi.org/, then add a token with an "all projects" scope.

Configure your credentials for the `pypi` repository:

```console
$ poetry config pypi-token.pypi <your-token>
```

Finally publish to `pypi.org`:

```console
$ make publish
```

See [this guide](https://realpython.com/pypi-publish-python-package/#publish-your-package-to-pypi) for more details on working with PyPi.

Please also create a tag for the release.

### Publishing to test.pypi.org

Create an account on https://test.pypi.org/, then add a token with an
"all projects" scope.

Add a `testpypi` repository to your poetry config:

```console
$ poetry config repositories.testpypi https://test.pypi.org/legacy/
```

Configure your credentials for the `testpypi` repository:

```console
$ poetry config pypi-token.testpypi <your-token>
```

Finally publish to `test.pypi.org`:

```console
$ make publish-test
```

The package should upload to the test.pypi.org service.

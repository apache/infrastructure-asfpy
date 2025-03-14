# asfpy - ASF Infrastructure Common Library for Python functions
<a href="https://pypi.org/project/asfpy"><img alt="PyPI" src="https://img.shields.io/pypi/v/asfpy.svg?color=blue&maxAge=600" /></a>
<a href="https://pypi.org/project/asfpy"><img alt="PyPI - Python Versions" src="https://img.shields.io/pypi/pyversions/asfpy.svg?maxAge=600" /></a>
<a href="https://github.com/apache/infrastructure-asfpy/actions/workflows/unittest.yml?query=branch%3Amain"><img alt="Unit Tests" src="https://github.com/apache/infrastructure-asfpy/actions/workflows/unittest.yml/badge.svg?branch=main" /></a>
<a href="https://github.com/apache/infrastructure-asfpy/blob/main/LICENSE"><img alt="Apache License" src="https://img.shields.io/github/license/apache/infrastructure-asfpy" /></a>

This Python library contains features commonly used at the Apache Software Foundation.

(For asfpy 0.37 and below, look at our old [Subversion repository](https://svn.apache.org/repos/infra/infrastructure/trunk/projects/asfpy/))


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

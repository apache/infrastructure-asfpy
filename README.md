# asfpy - ASF Infrastructure Common Library for Python functions
<a href="https://pypi.org/project/asfpy"><img alt="PyPI" src="https://img.shields.io/pypi/v/asfpy.svg?color=blue&maxAge=600" /></a>
<a href="https://pypi.org/project/asfpy"><img alt="PyPI - Python Versions" src="https://img.shields.io/pypi/pyversions/asfpy.svg?maxAge=600" /></a>
<a href="https://github.com/apache/infrastructure-asfpy/actions/workflows/unittest.yml?query=branch%3Amain"><img alt="Unit Tests" src="https://github.com/apache/infrastructure-asfpy/actions/workflows/unittest.yml/badge.svg?branch=main" /></a>
<a href="https://github.com/apache/infrastructure-asfpy/blob/main/LICENSE"><img alt="Apache License" src="https://img.shields.io/github/license/apache/infrastructure-asfpy" /></a>

This Python library contains features commonly used at the Apache Software Foundation.

(For asfpy 0.37 and below, look at our old [Subversion repository](https://svn.apache.org/repos/infra/infrastructure/trunk/projects/asfpy/))


## Building asfpy package

Preparation

* `apt install python3.10-venv`
* `pip3 install build twine`

Bump the version number in `setup.py` and run:
`python3 -m build`


## Publishing a new asfpy package

After building the asfpy package, run the following command, where $version is the new version to publish:

`python3 -m twine upload dist/asfpy-$version*`  (for instance `dist/asfpy-0.38*`)

The above command will upload the `.whl` and the `.tar.gz` (the glob-asterisk is important!)

See [this guide](https://realpython.com/pypi-publish-python-package/#publish-your-package-to-pypi) for more details on working with PyPi.

Please also create a tag for the release.

### for testing

Create an account on https://test.pypi.org/, then add a token with an
"all projects" scope. Place that into your `.pypirc` like so:

```
[testpypi]
  repository = https://test.pypi.org/legacy/
  username = __token__
  password = pypi-tokenstringgoeshere
```

Then you can test an upload with:
`python3 -m twine upload -r testpypi dist/asf-py$version*`

The package should upload to the test.pypi.org service.

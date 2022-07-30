# asfpy - ASF Infrastructure Common Library for Python functions

This Python library contains features commonly used at the Apache Software Foundation.

(For asfpy 0.37 and below, look at our old [Subversion repository](https://svn.apache.org/repos/infra/infrastructure/trunk/projects/asfpy/))


## Building asfpy package
Make sure you have the `build` and `twine` packages installed first ( `pip3 install build twine`)

Bump the version number in `setup.py` and run:
`python3 setup.py sdist bdist_wheel`

## Publishing a new asfpy package
After building the asfpy package, run the following command, where $version is the new version to publish:

`python3 -m twine upload dist/asfpy-$version*`  (for instance `dist/asfpy-0.38*`)

See [this guide](https://realpython.com/pypi-publish-python-package/#publish-your-package-to-pypi) for more details on working with PyPi.

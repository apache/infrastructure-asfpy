.PHONY: build check publish publish-test

SHELL := /bin/bash

PYTHON ?= $(which python3)
SCRIPTS ?= scripts/poetry

build:
	@echo "Building module"
	@echo "==============="

	@poetry build

check:
	@echo "Checking for a dirty workspace"
	@echo "=============================="

	@git status -s -uno | grep '.' && echo "Workspace contains uncommitted changes, aborting publishing" && exit 1
	@git status -s -unormal | grep -E "asfpy|tests" | grep "?" && echo "Workspace contains untracked source files, aborting publishing" && exit 1

publish: check build
	$(eval VERSION=$(shell poetry version -s))

	@echo "Releasing version ${VERSION}"

	@if [[ "$(VERSION)" =~ "dev" ]]; then \
		echo "Detected development version, abort publishing"; \
		exit 1; \
	fi

	@poetry publish && echo "\nPublished version $(VERSION) to pypi.org, do not forget to tag the repo with v$(VERSION)."

publish-test: build
	$(eval REPO=$(shell poetry config repositories.testpypi | grep -o 'test.pypi.org'))
	@if [ "$(REPO)" != "test.pypi.org" ]; then \
		echo "\nSetting up testpypi repository"; \
		poetry config repositories.testpypi https://test.pypi.org/legacy/; \
		echo "Dont forget to configure your token for test.pypi.org using:"; \
		echo "  poetry config pypi-token.testpypi <your-token>\n"; \
	fi

	$(eval VERSION=$(shell poetry version -s))

	@poetry publish -r testpypi && echo "\nPublished version $(VERSION) to test.pypi.org."

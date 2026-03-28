.PHONY: build check publish publish-test

SHELL := /bin/bash

build:
	@echo "Building module"
	@echo "==============="

	@uv build

check:
	@echo "Checking for a dirty workspace"
	@echo "=============================="

	@if git status -s -uno | grep -q .; then \
		echo "Workspace contains uncommitted changes, aborting publishing"; \
		exit 1; \
	fi
	@if git status -s -unormal | grep -E "asfpy|tests" | grep -q "?"; then \
		echo "Workspace contains untracked source files, aborting publishing"; \
		exit 1; \
	fi
	@uv lock --locked

publish: check build
	$(eval VERSION=$(shell uv version --short))

	@echo "Releasing version ${VERSION}"

	@if [[ "$(VERSION)" =~ "dev" ]]; then \
		echo "Detected development version, abort publishing"; \
		exit 1; \
	fi

	@uv publish || exit 1
	@echo ""
	@echo "Published version $(VERSION) to pypi.org, do not forget to tag the repo with v$(VERSION)."
	@echo "$ git tag v${VERSION}"
	@echo "$ git push origin v${VERSION}"
	@echo "Also: bump the version in pyproject.toml"

publish-test: build
	$(eval VERSION=$(shell uv version --short))

	@uv publish --publish-url https://test.pypi.org/legacy/ && echo -e "\nPublished version $(VERSION) to test.pypi.org."

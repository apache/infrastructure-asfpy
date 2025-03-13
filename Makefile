.PHONY: build check publish publish-test

PYTHON ?= $(which python3)
SCRIPTS ?= scripts/poetry

build:
	@echo "Building module"
	@echo "==============="

	poetry build

check:
	@echo "Checking for a dirty workspace"
	@echo "=============================="

	git status -s -uno | grep '.' && echo "Workspace contains uncommitted changes" && exit 1
	git status -s -unormal | grep -E "asfpy|tests" | grep "?" && echo "Workspace contains untracked source files" && exit 1

publish: check build
	poetry publish

publish-test: build
	poetry publish -r testpypi

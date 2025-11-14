.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
    match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
    if match:
        target, help = match.groups()
        print("%-40s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

TEST_REGION="us-west-2"
TEST_ROLE="arn:aws:iam::303467602807:role/update-dns-tester"
TEST_SELECTOR="update-dns-test-1 and aws-6"

help: install-hooks
	@python -c "$$PRINT_HELP_PYSCRIPT" < Makefile

.PHONY: install-hooks
install-hooks:  ## Install repo hooks
	@echo "Checking and installing hooks"
	@test -d .git/hooks || (echo "Looks like you are not in a Git repo" ; exit 1)
	@test -L .git/hooks/pre-commit || ln -fs ../../hooks/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit


.PHONY: lint
lint:  ## Run code style checks
	terraform fmt --check -recursive

.PHONY: test
test:  ## Run tests on the module
	pytest -xvvs tests/

.PHONY: test-keep
test-keep:  ## Run a test and keep resources
	pytest -xvvs \
		--aws-region=${TEST_REGION} \
		--test-role-arn=${TEST_ROLE} \
		--keep-after \
		-k ${TEST_SELECTOR} \
		tests/test_module.py \
		2>&1 | tee pytest-`date +%Y%m%d-%H%M%S`-output.log

.PHONY: test-clean
test-clean:  ## Run a test and destroy resources
	pytest -xvvs \
		--aws-region=${TEST_REGION} \
		--test-role-arn=${TEST_ROLE} \
		-k ${TEST_SELECTOR} \
		tests/test_module.py \
		2>&1 | tee pytest-`date +%Y%m%d-%H%M%S`-output.log


.PHONY: bootstrap
bootstrap: ## bootstrap the development environment
	pip install -U "pip ~= 25.2"
	pip install -U "setuptools ~= 80.9"
	pip install -r requirements.txt

.PHONY: clean
clean: ## clean the repo from cruft
	rm -rf .pytest_cache
	find . -name '.terraform' -exec rm -fr {} +
	rm -f pytest-*-output.log

# Internal target for creating releases - do not call directly
.PHONY: _release
_release:
	@test -n "$(BUMP)" || (echo "Error: BUMP variable must be set" && exit 1)
	@echo "Checking if git-cliff is installed..."
	@command -v git-cliff >/dev/null 2>&1 || { \
		echo ""; \
		echo "Error: git-cliff is not installed."; \
		echo ""; \
		echo "Please install it using one of the following methods:"; \
		echo ""; \
		echo "  Cargo (Rust):"; \
		echo "    cargo install git-cliff"; \
		echo ""; \
		echo "  Arch Linux:"; \
		echo "    pacman -S git-cliff"; \
		echo ""; \
		echo "  Homebrew (macOS/Linux):"; \
		echo "    brew install git-cliff"; \
		echo ""; \
		echo "  From binary (Linux/macOS/Windows):"; \
		echo "    https://github.com/orhun/git-cliff/releases"; \
		echo ""; \
		echo "For more installation options, see: https://git-cliff.org/docs/installation"; \
		echo ""; \
		exit 1; \
	}
	@echo "Checking if on main branch..."
	@git branch --show-current | grep -q "^main$$" || (echo "Error: Must be on main branch to release" && exit 1)
	@echo "Calculating version..."
	$(eval NEW_VERSION := $(shell git cliff --bumped-version --bump $(BUMP)))
	@echo "New version will be: $(NEW_VERSION)"
	@echo "Updating CHANGELOG.md..."
	@git cliff --unreleased --tag $(NEW_VERSION) --prepend CHANGELOG.md
	@echo "Committing CHANGELOG..."
	@git add CHANGELOG.md
	@git commit -m "Update CHANGELOG for $(NEW_VERSION)"
	@echo "Creating tag $(NEW_VERSION)..."
	@git tag $(NEW_VERSION)
	@echo "Release $(NEW_VERSION) created. Push with: git push && git push --tags"

.PHONY: release-patch
release-patch: ## Release a patch version (x.x.PATCH)
	@$(MAKE) _release BUMP=patch

.PHONY: release-minor
release-minor: ## Release a minor version (x.MINOR.0)
	@$(MAKE) _release BUMP=minor

.PHONY: release-major
release-major: ## Release a major version (MAJOR.0.0)
	@$(MAKE) _release BUMP=major

.PHONY: fmt
fmt: format

.PHONY: format
format:  ## Use terraform fmt to format all files in the repo
	@echo "Formatting terraform files"
	terraform fmt -recursive
	black tests update_dns/main.py

define BROWSER_PYSCRIPT
import os, webbrowser, sys

from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

BROWSER := python -c "$$BROWSER_PYSCRIPT"

.PHONY: docs
docs: ## generate Sphinx HTML documentation, including API docs
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html
.PHONY: venv

venv: ## Create local python virtual environment
	python3 -m venv .venv
	@echo "To activate run"
	@echo ""
	@echo ". .venv/bin/activate"

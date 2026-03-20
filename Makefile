.PHONY: help pre-commit build test coverage clean lint format install bump-patch bump-fix bump-minor bump-feat bump-major bump bump-check \
	security-trivy security-trivy-detail security-trufflehog ci-security

PACKAGES := isvctl isvreporter isvtest
BUMP_SCRIPT := scripts/bump-version.py

# Align with .github/workflows/ci.yaml security-trivy-scan (filesystem scan). Requires Docker.
TRIVY_IMAGE ?= aquasec/trivy:latest
TRUFFLEHOG_IMAGE ?= trufflesecurity/trufflehog:latest
SECURITY_SKIP_DIRS := .git,dist,htmlcov,.pytest_cache,.ruff_cache,.venv,node_modules,vendor,.terraform
# SARIF path written by CI dsx trivy-scan / aquasecurity/trivy-action (default filename).
TRIVY_SARIF ?= vulnerability-scan-results.sarif

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

pre-commit: ## Run pre-commit on all packages
	@echo "Running pre-commit on all packages..."
	@for pkg in $(PACKAGES); do \
		echo ""; \
		echo "=========================================="; \
		echo "Running pre-commit in $$pkg"; \
		echo "=========================================="; \
		if [ -n "$$GITLAB_CI" ]; then \
			(cd $$pkg && uvx pre-commit run -a --show-diff-on-failure) || exit 1; \
		else \
			(cd $$pkg && uvx pre-commit run -a) || exit 1; \
		fi; \
	done
	@echo ""
	@echo "✅ All pre-commit checks passed!"

lint: ## Run ruff linting on all packages
	@for pkg in $(PACKAGES); do \
		echo "Linting $$pkg..."; \
		(cd $$pkg && uvx ruff check src/) || exit 1; \
	done

format: ## Format code with ruff on all packages
	@for pkg in $(PACKAGES); do \
		echo "Formatting $$pkg..."; \
		(cd $$pkg && uvx ruff format src/) || exit 1; \
	done

security-trivy: ## Trivy fs scan (HIGH/CRITICAL; Docker). Writes $(TRIVY_SARIF), prints per-finding summary; --exit-code 0 (like CI fail-on-findings false)
	@command -v docker >/dev/null 2>&1 || { echo "docker not found; install Docker to run local security scans"; exit 1; }
	docker run --rm -v "$(CURDIR):/repo" -w /repo $(TRIVY_IMAGE) fs \
		--severity HIGH,CRITICAL \
		--ignore-unfixed \
		--skip-dirs "$(SECURITY_SKIP_DIRS)" \
		--scanners vuln,secret,misconfig,license \
		--exit-code 0 \
		--format sarif \
		--output "/repo/$(TRIVY_SARIF)" \
		/repo
	@echo ""
	@echo "=== Per-finding summary (same as: make security-trivy-detail) ==="
	@$(MAKE) security-trivy-detail

security-trivy-detail: ## List each finding from $(TRIVY_SARIF) (jq). Run after security-trivy or CI; GITHUB_STEP_SUMMARY appends in Actions
	@./scripts/trivy-sarif-summary.sh "$(TRIVY_SARIF)"

security-trufflehog: ## Run TruffleHog secret scan (Docker; verified/unknown, --only-verified). Exits non-zero if verified secrets are found
	@command -v docker >/dev/null 2>&1 || { echo "docker not found; install Docker to run local security scans"; exit 1; }
	docker run --rm -v "$(CURDIR):/work" -w /work $(TRUFFLEHOG_IMAGE) filesystem /work \
		--results=verified,unknown --only-verified --fail

ci-security: security-trivy security-trufflehog ## Run local equivalents of CI Trivy + TruffleHog (not CodeQL; use GitHub Actions or install CodeQL CLI)

test: ## Run tests for all packages
	@for pkg in $(PACKAGES); do \
		echo "Testing $$pkg..."; \
		if [ "$$pkg" = "isvtest" ]; then \
			(cd $$pkg && uv run pytest -m unit) || exit 1; \
		else \
			(cd $$pkg && uv run pytest) || exit 1; \
		fi; \
	done
	@echo ""
	@echo "✅ All tests passed!"

coverage: ## Run tests with coverage and generate combined report
	@echo "Running tests with coverage..."
	@for pkg in $(PACKAGES); do \
		echo "Testing $$pkg with coverage..."; \
		if [ "$$pkg" = "isvtest" ]; then \
			(cd $$pkg && uv run pytest -m unit --cov=src --cov-report=) || exit 1; \
		else \
			(cd $$pkg && uv run pytest --cov=src --cov-report=) || exit 1; \
		fi; \
	done
	@echo ""
	@echo "Combining coverage reports..."
	@uv run coverage combine $(foreach pkg,$(PACKAGES),$(pkg)/.coverage)
	@uv run coverage xml -o coverage-combined.xml
	@uv run coverage report
	@echo ""
	@echo "✅ Coverage report generated: coverage-combined.xml"

build: ## Build all packages (wheels output to dist/)
	@echo "Building wheel packages..."
	@mkdir -p dist
	@for pkg in $(PACKAGES); do \
		echo "Building $$pkg..."; \
		uv build $$pkg/ --out-dir dist/ --no-build-logs || exit 1; \
	done
	@echo ""
	@echo "✅ All packages built successfully!"
	@echo "Wheels available in dist/"

install: ## Install all packages in development mode
	uv sync
	@echo ""
	@echo "✅ Installation complete!"

bump-patch: ## Bump patch version (e.g. 0.4.2 -> 0.4.3)
	uv run python $(BUMP_SCRIPT) patch

bump-fix: bump-patch ## Alias for bump-patch

bump-minor: ## Bump minor version (e.g. 0.4.2 -> 0.5.0)
	uv run python $(BUMP_SCRIPT) minor

bump-feat: bump-minor ## Alias for bump-minor

bump-major: ## Bump major version (e.g. 0.4.2 -> 1.0.0)
	uv run python $(BUMP_SCRIPT) major

bump: ## Bump to explicit version (e.g. make bump VERSION=1.2.3)
	@if [ -z "$(VERSION)" ]; then echo "Usage: make bump VERSION=x.y.z"; exit 1; fi
	uv run python $(BUMP_SCRIPT) $(VERSION)

bump-check: ## Verify versions match (CI; e.g. make bump-check VERSION=1.2.3)
	@if [ -z "$(VERSION)" ]; then echo "Usage: make bump-check VERSION=x.y.z"; exit 1; fi
	uv run python $(BUMP_SCRIPT) --check $(VERSION)

clean: ## Clean build artifacts and test outputs
	@echo "Cleaning build artifacts and test outputs..."
	@rm -rf dist/
	@rm -f coverage-combined.xml .coverage
	@for pkg in $(PACKAGES); do \
		echo "Cleaning $$pkg..."; \
		rm -rf $$pkg/dist/ $$pkg/.pytest_cache/ $$pkg/__pycache__/; \
		rm -f $$pkg/junit.xml $$pkg/coverage.xml $$pkg/.coverage; \
		find $$pkg -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true; \
		find $$pkg -type f -name "*.pyc" -delete 2>/dev/null || true; \
	done
	@echo "✅ Clean complete!"

update-spdx-headers: ## Update SPDX headers in all packages
	@echo "Updating SPDX headers in all packages..."
	@uv run python scripts/add_spdx_headers.py
	@echo "✅ SPDX headers updated!"

.PHONY: help pre-commit build test coverage clean lint format install

PACKAGES := isvctl isvreporter isvtest

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

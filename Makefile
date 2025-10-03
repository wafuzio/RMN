.PHONY: docs docs-check clean help

help:
	@echo "Available targets:"
	@echo "  docs        - Update auto-generated documentation (README taxonomy)"
	@echo "  docs-check  - Verify documentation is up to date (CI mode)"
	@echo "  clean       - Remove Python cache files"

docs:
	@echo "Updating auto-generated documentation..."
	@python3 scripts/docs/update_docs.py

docs-check:
	@echo "Checking documentation is up to date..."
	@python3 scripts/docs/update_docs.py --check

clean:
	@echo "Cleaning Python cache files..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Clean complete"

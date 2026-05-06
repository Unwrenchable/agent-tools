#!/usr/bin/env bash
# tools/sandbox_runner/run_tests.sh
#
# Entrypoint for the realai-sandbox Docker image.
# Runs pytest against the mounted /workspace directory.
#
# Exit codes:
#   0 — all tests passed
#   2 — tests failed (pytest convention for collection/test errors)

set -euo pipefail

cd /workspace

echo "=== Running tests in sandbox ==="
echo "Python: $(python --version)"
echo "pytest: $(python -m pytest --version)"
echo "Working directory: $(pwd)"
echo ""

# Install the package in editable mode if setup files exist.
if [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
    pip install --quiet -e ".[dev]" 2>/dev/null || pip install --quiet -e . 2>/dev/null || true
fi

python -m pytest -q "$@"

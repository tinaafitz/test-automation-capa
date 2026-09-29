# run-tests

Execute the test-automation-capa test suite.

## What this skill does

Runs pytest against the test suite:
- Executes all tests or specific test patterns
- Captures test results, coverage, and output
- Works from any directory (auto-detects repo)
- Supports filtering by test name, file, or marker

## Prerequisites

- `podman` installed and in PATH
- Container image `test-automation-capa:latest` built (or will build automatically)
- 4+ GB RAM available

## Run all tests

```bash
# Auto-detect repo path
REPO_PATH=$(git -C /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa rev-parse --show-toplevel 2>/dev/null || echo /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa)

# Run all tests with coverage (bypass entrypoint to skip app startup)
podman run --rm \
  -v test-automation-data:/data \
  -v "$REPO_PATH:/workspace" \
  --entrypoint bash \
  test-automation-capa:latest \
  -c "cd /app && pytest -v --cov --cov-report=term-missing"
```

## Run specific test file

```bash
REPO_PATH=$(git -C /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa rev-parse --show-toplevel 2>/dev/null || echo /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa)

podman run --rm \
  -v test-automation-data:/data \
  -v "$REPO_PATH:/workspace" \
  test-automation-capa:latest \
  bash -c "cd /app && pytest -v ui/backend/test_app.py"
```

## Run tests matching pattern

```bash
# Run only tests with "rosa" in the name
podman run --rm \
  -v test-automation-data:/data \
  test-automation-capa:latest \
  bash -c "cd /app && pytest -v -k rosa"
```

## Run with markers

```bash
# Run only unit tests (skip integration tests)
podman run --rm \
  -v test-automation-data:/data \
  test-automation-capa:latest \
  bash -c "cd /app && pytest -v -m unit"
```

## Options

- `-v` — Verbose output
- `--cov` — Calculate coverage
- `--cov-report=term-missing` — Show which lines weren't covered
- `-k PATTERN` — Run tests matching pattern
- `-m MARKER` — Run tests with specific marker
- `--tb=short` — Shorter traceback format
- `-x` — Stop on first failure
- `-s` — Show print statements

## Example: Run tests with short output

```bash
REPO_PATH=$(git -C /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa rev-parse --show-toplevel 2>/dev/null || echo /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa)

podman run --rm \
  -v test-automation-data:/data \
  test-automation-capa:latest \
  bash -c "cd /app && pytest --tb=short -q"
```

## Environment

Tests run in ephemeral container (removed after completion). Data volume mounted for persistent test artifacts.

## Related skills

- `run-ui` — Start the application
- `stop-ui` — Stop the application
- `logs` — View container logs

## Notes

- Uses `--rm` flag so container is cleaned up after tests complete
- Data volume preserved for next run
- Tests execute in `/app` directory with full dependencies available
- Coverage reports printed to terminal

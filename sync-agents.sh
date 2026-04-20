#!/usr/bin/env bash
#
# Sync AI agent framework from upstream rosa-hcp-e2e-test repo
#
# Usage:
#   ./sync-agents.sh                    # sync from default upstream path
#   ./sync-agents.sh /path/to/upstream  # sync from custom path
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="${1:-$(dirname "$SCRIPT_DIR")/rosa-hcp-e2e-test-fresh-upstream}"

if [ ! -d "$UPSTREAM/agents" ]; then
    echo "Error: upstream repo not found at $UPSTREAM"
    echo "Usage: $0 /path/to/rosa-hcp-e2e-test"
    exit 1
fi

echo "Syncing agent framework from: $UPSTREAM"

# Base agent files
for f in __init__.py base_agent.py monitoring_agent.py diagnostic_agent.py remediation_agent.py learning_agent.py; do
    cp "$UPSTREAM/agents/$f" "$SCRIPT_DIR/agents/$f"
    echo "  agents/$f"
done

# Domain plugins
rsync -a --delete "$UPSTREAM/agents/domains/" "$SCRIPT_DIR/agents/domains/"
echo "  agents/domains/ (recursive)"

# Knowledge base template
cp "$UPSTREAM/agents/knowledge_base/known_issues.json" "$SCRIPT_DIR/agents/knowledge_base/known_issues.json"
echo "  agents/knowledge_base/known_issues.json"

# Test runner
cp "$UPSTREAM/run-test-suite.py" "$SCRIPT_DIR/run-test-suite.py"
echo "  run-test-suite.py"

echo ""
echo "Done. Synced $(find "$SCRIPT_DIR/agents" -name "*.py" | wc -l | tr -d ' ') Python files."

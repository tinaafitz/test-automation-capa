"""Knowledge base search and remediation history tools."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
KB_DIR = PROJECT_ROOT / "agents" / "knowledge_base"


def register_tools(mcp):

    @mcp.tool()
    def capa_search_known_issues(query: str = "", issue_type: str = "") -> str:
        """Search the CAPA knowledge base for known cluster issues and their remediation strategies.

        Args:
            query: Free-text search across issue descriptions, symptoms, and causes
            issue_type: Filter by exact issue type (e.g., 'cloudformation_deletion_failure')
        """
        try:
            with open(KB_DIR / "known_issues.json") as f:
                issues = json.load(f)
        except Exception as e:
            return json.dumps({"error": f"Failed to load knowledge base: {e}"})

        results = []
        for issue in issues:
            if issue_type and issue.get("type") != issue_type:
                continue
            if query:
                searchable = json.dumps(issue).lower()
                if query.lower() not in searchable:
                    continue
            results.append(issue)

        return json.dumps({"matches": results, "count": len(results), "total_known_issues": len(issues)}, indent=2)

    @mcp.tool()
    def capa_remediation_history(issue_type: str = "", limit: int = 20) -> str:
        """View past remediation outcomes — what fixes were tried, whether they succeeded, and details.

        Args:
            issue_type: Filter by issue type (optional)
            limit: Max results to return (default: 20)
        """
        try:
            with open(KB_DIR / "remediation_outcomes.json") as f:
                outcomes = json.load(f)
        except Exception as e:
            return json.dumps({"error": f"Failed to load remediation outcomes: {e}"})

        if issue_type:
            outcomes = [o for o in outcomes if o.get("issue_type") == issue_type]

        # Compute summary stats
        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.get("success"))
        failures = total - successes

        # Return most recent
        recent = outcomes[-limit:] if limit else outcomes
        recent.reverse()

        return json.dumps({
            "total_outcomes": total,
            "successes": successes,
            "failures": failures,
            "success_rate": f"{(successes / total * 100):.1f}%" if total else "N/A",
            "recent": recent,
        }, indent=2, default=str)

    @mcp.tool()
    def capa_learning_stats() -> str:
        """Get AI agent learning statistics — success rates by fix type, confidence trends,
        and pending patterns awaiting human review."""
        stats = {}

        # Remediation outcome stats by fix type
        try:
            with open(KB_DIR / "remediation_outcomes.json") as f:
                outcomes = json.load(f)

            by_fix = {}
            for o in outcomes:
                fix = o.get("recommended_fix", "unknown")
                by_fix.setdefault(fix, {"total": 0, "successes": 0})
                by_fix[fix]["total"] += 1
                if o.get("success"):
                    by_fix[fix]["successes"] += 1

            for fix, data in by_fix.items():
                data["success_rate"] = f"{(data['successes'] / data['total'] * 100):.1f}%" if data["total"] else "N/A"

            stats["by_fix_type"] = by_fix
            stats["total_outcomes"] = len(outcomes)
        except Exception as e:
            stats["outcomes_error"] = str(e)

        # Pending learnings (new patterns awaiting review)
        try:
            pending_path = KB_DIR / "pending_learnings.json"
            if pending_path.exists():
                with open(pending_path) as f:
                    pending = json.load(f)
                stats["pending_review"] = len(pending)
                stats["pending_patterns"] = pending
            else:
                stats["pending_review"] = 0
        except Exception:
            stats["pending_review"] = 0

        return json.dumps(stats, indent=2, default=str)

"""Enforce complete line and branch coverage for every integration module."""
import json
from pathlib import Path


def main() -> None:
    report = json.loads(Path("coverage.json").read_text())
    failures = []
    if not report["meta"].get("branch_coverage"):
        failures.append("Coverage report must include branch coverage")
    expected = {path.as_posix() for path in Path("custom_components/ha_pocketsmith").rglob("*.py")}
    missing = expected - report["files"].keys()
    failures.extend(f"{filename}: missing coverage data" for filename in sorted(missing))
    for filename, data in report["files"].items():
        if not filename.startswith("custom_components/ha_pocketsmith/"):
            continue
        summary = data["summary"]
        if summary["missing_lines"] or summary.get("missing_branches", 0):
            failures.append(
                f"{filename}: {summary['missing_lines']} uncovered lines, "
                f"{summary.get('missing_branches', 0)} uncovered branches"
            )
    if failures:
        raise SystemExit("\n".join(failures))
    print("Every integration module has 100% line and branch coverage.")


if __name__ == "__main__":
    main()

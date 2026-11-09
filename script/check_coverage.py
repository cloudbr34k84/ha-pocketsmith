"""Enforce Silver per-module coverage and Bronze's complete flow coverage."""
import json
from pathlib import Path


def main() -> None:
    report = json.loads(Path("coverage.json").read_text())
    failures = []
    expected = {path.as_posix() for path in Path("custom_components/ha_pocketsmith").rglob("*.py")}
    missing = expected - report["files"].keys()
    failures.extend(f"{filename}: missing coverage data" for filename in sorted(missing))
    for filename, data in report["files"].items():
        if not filename.startswith("custom_components/ha_pocketsmith/"):
            continue
        percent = data["summary"]["percent_covered"]
        required = 100 if filename.endswith("/config_flow.py") else 95
        if percent < required or (required == 95 and percent == 95):
            failures.append(f"{filename}: {percent:.2f}% (required {'100%' if required == 100 else '>95%'})")
    if failures:
        raise SystemExit("\n".join(failures))
    print("All integration modules exceed 95%; config flow has 100% coverage.")


if __name__ == "__main__":
    main()

"""The CI gate rejects incomplete or missing integration coverage."""
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "script" / "check_coverage.py"


@pytest.mark.parametrize(
    ("branch_coverage", "missing_lines", "missing_branches", "include_file", "expected"),
    [
        (True, 0, 0, True, True),
        (False, 0, 0, True, False),
        (True, 1, 0, True, False),
        (True, 0, 1, True, False),
        (True, 0, 0, False, False),
    ],
)
def test_coverage_gate(tmp_path, branch_coverage, missing_lines, missing_branches, include_file, expected):
    integration = tmp_path / "custom_components" / "ha_pocketsmith"
    integration.mkdir(parents=True)
    (integration / "example.py").write_text("pass\n")
    filename = "custom_components/ha_pocketsmith/example.py"
    report = {
        "meta": {"branch_coverage": branch_coverage},
        "files": {
            filename: {"summary": {"missing_lines": missing_lines, "missing_branches": missing_branches}}
        } if include_file else {},
    }
    (tmp_path / "coverage.json").write_text(json.dumps(report))
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert (result.returncode == 0) is expected

"""Verify protected original files and the mechanically relocated upstream modules."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    ".gitattributes",
    "pyproject.toml",
    "api.py",
    "Dockerfile",
    "README.md",
    "src/container_runtime.py",
    "src/day_forecast_publication.py",
    "deploy/forecast-dispatch/.env.example",
    "deploy/forecast-dispatch/compose.yaml",
    "deploy/forecast-dispatch/vendor-day-release.json",
    "scripts/check_combined_lifecycle.py",
    "scripts/check_forecast_bridge_live.py",
    "scripts/package_forecast_dispatch.py",
    "tests/test_day_forecast_publication.py",
    "tests/test_api.py",  # The public route inventory now includes day-only backfill.
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(root=ROOT):
    evidence = json.loads(
        (root / "deploy/forecast-dispatch/integration-source.json").read_text("utf-8")
    )
    changed = [
        name
        for name, expected in evidence["original_files"].items()
        if not (root / name).is_file() or sha(root / name) != expected
    ]
    forbidden = sorted(set(changed) - ALLOWED)
    if forbidden:
        raise ValueError(f"Changes outside integration scope: {forbidden}")
    vendor = root / "src/vendor/dayahead"
    for name, expected in evidence["vendor_original_sha256"].items():
        # Only these two imports were relocated; compare the exact upstream bytes.
        data = (vendor / name).read_bytes()
        if name in {"contract.py", "storage.py"}:
            data = data.replace(b"from .result_contract import", b"from app.result_contract import")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Vendor logic changed: {name}")
    return {
        "passed": True,
        "protected_original_files": len(evidence["original_files"]) - len(ALLOWED),
        "modified_original_files": sorted(changed),
        "vendor_commit": evidence["vendor_commit"],
        "vendor_logic_unchanged": True,
    }


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, indent=2))

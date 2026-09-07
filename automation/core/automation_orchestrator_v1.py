from pathlib import Path
import json
import subprocess
import sys

BASE = Path(__file__).resolve().parents[2]

REGISTRY_FILE = (
    BASE
    / "automation"
    / "config"
    / "source_permission_registry.json"
)

STAGES = [
    ("automation_runner_v1", BASE / "automation" / "core" / "automation_runner_v1.py"),
    ("bulk_official_collector_v1", BASE / "automation" / "core" / "bulk_official_collector_v1.py"),
    ("bulk_manifest_builder_v1", BASE / "automation" / "core" / "bulk_manifest_builder_v1.py"),
    ("bulk_official_intake_v1", BASE / "automation" / "core" / "bulk_official_intake_v1.py"),
    ("unified_importer_v1_5", BASE / "automation" / "core" / "unified_importer_v1_5.py"),

    ("region_registry_builder_v1", BASE / "automation" / "core" / "region_registry_builder_v1.py"),
    ("branch_master_v2_builder", BASE / "automation" / "core" / "branch_master_v2_builder.py"),
    ("branch_region_mapper_v1", BASE / "automation" / "core" / "branch_region_mapper_v1.py"),
    ("regional_data_loader_driver_v1", BASE / "automation" / "core" / "regional_data_loader_driver_v1.py"),
    ("regional_package_index_builder_v1", BASE / "automation" / "core" / "regional_package_index_builder_v1.py"),
    ("regional_cache_sync_v1", BASE / "automation" / "core" / "regional_cache_sync_v1.py"),

    ("unified_pre_cutover_validator_v1", BASE / "automation" / "core" / "unified_pre_cutover_validator_v1.py"),
]


def load_registry():
    if not REGISTRY_FILE.exists():
        print(f"BLOCKED: permission registry not found: {REGISTRY_FILE}")
        return None

    try:
        with REGISTRY_FILE.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"BLOCKED: permission registry invalid: {exc}")
        return None

    if not isinstance(data, dict):
        print("BLOCKED: permission registry root is not an object")
        return None

    return data


def permission_gate():
    registry = load_registry()

    if registry is None:
        return False

    markets = registry.get("markets")

    if not isinstance(markets, list):
        print("BLOCKED: permission registry markets invalid")
        return False

    approved_markets = []

    for market in markets:
        if not isinstance(market, dict):
            continue

        market_id = str(market.get("marketId", "")).strip()
        permissions = market.get("permissions", {})

        if not market_id or not isinstance(permissions, dict):
            continue

        automated = permissions.get("automatedCollection", {})

        if not isinstance(automated, dict):
            continue

        status = str(automated.get("status", "")).strip().lower()
        allowed = automated.get("allowed") is True

        if status == "approved" and allowed:
            approved_markets.append(market_id)

    print()
    print("PERMISSION HARD GATE")
    print(f"Approved automatedCollection markets : {len(approved_markets)}")

    if approved_markets:
        print("Approved markets:")
        for market_id in approved_markets:
            print(f"  - {market_id}")
        print("PERMISSION HARD GATE : PASS")
        return True

    print("PERMISSION HARD GATE : BLOCKED")
    print("Reason: no approved automatedCollection permission.")
    return False


def run_stage(name, path):
    print(f"\n=== {name} ===")

    if not path.exists():
        print(f"BLOCKED: stage file not found: {path}")
        return False

    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(BASE),
    )

    if result.returncode != 0:
        print(f"FAILED: {name} exit={result.returncode}")
        return False

    print(f"PASS: {name}")
    return True


def main():
    print("INDIRIMLI CLOUD ORCHESTRATOR V1")
    print("FAIL-CLOSED MODE : ENABLED")
    print("PRODUCTION WRITE : DISABLED")

    if not permission_gate():
        print("\nORCHESTRATOR V1 : BLOCKED")
        print("No collector or later stage executed.")
        return 1

    for name, path in STAGES:
        if not run_stage(name, path):
            print("\nORCHESTRATOR V1 : BLOCKED")
            print("No later stage executed.")
            return 1

    print("\nORCHESTRATOR V1 : PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


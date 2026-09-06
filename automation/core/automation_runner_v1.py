import importlib.util
import json
from pathlib import Path
import os

BASE = Path(__file__).resolve().parent.parent
ADAPTERS_DIR = BASE / "adapters"
REGISTRY_NAME = os.environ.get("INDIRIMLI_PERMISSION_REGISTRY", "source_permission_registry.json")
REGISTRY_FILE = BASE / "config" / REGISTRY_NAME


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def permission_allowed(registry, market_id, module_name):
    market = next(
        (
            row
            for row in registry.get("markets", [])
            if isinstance(row, dict)
            and str(row.get("marketId") or "").strip() == market_id
        ),
        None,
    )

    if market is None:
        return False

    rule = (
        market.get("permissions", {})
        .get(module_name, {})
    )

    return (
        rule.get("allowed") is True
        and str(rule.get("status") or "").strip().lower()
        == "approved"
    )


def load_adapter(market_id):
    adapter_file = ADAPTERS_DIR / f"{market_id}_adapter_v1.py"

    if not adapter_file.exists():
        return None

    spec = importlib.util.spec_from_file_location(
        f"{market_id}_adapter_v1",
        adapter_file,
    )

    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    registry = load_json(REGISTRY_FILE)

    markets = registry.get("markets", [])

    print("=" * 70)
    print("INDIRIMLI CLOUD AUTOMATION RUNNER V1")
    print("=" * 70)

    for market in markets:
        if not isinstance(market, dict):
            continue

        market_id = str(
            market.get("marketId") or ""
        ).strip()

        if not market_id:
            continue

        print()
        print("MARKET:", market_id)

        if not permission_allowed(
            registry,
            market_id,
            "automatedCollection",
        ):
            print("AUTOMATED COLLECTION: BLOCKED")
            print("REASON: permission not approved")
            continue

        adapter = load_adapter(market_id)

        if adapter is None:
            print("ADAPTER: MISSING")
            continue

        result = adapter.collect(
            market_id,
            {
                key: permission_allowed(
                    registry,
                    market_id,
                    key,
                )
                for key in (
                    "prices",
                    "images",
                    "catalogs",
                    "branches",
                )
            },
        )

        print(
            "ADAPTER:",
            result.get("adapterName"),
        )
        print(
            "MODE:",
            result.get("metadata", {}).get("mode"),
        )
        print(
            "NETWORK REQUEST:",
            result.get("metadata", {}).get("networkRequest"),
        )

    print()
    print("=" * 70)
    print("AUTOMATION RUNNER V1 PASS")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())






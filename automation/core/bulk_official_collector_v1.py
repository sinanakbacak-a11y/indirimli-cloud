import json
import sys
import importlib.util
from datetime import datetime
from pathlib import Path

from adapter_contract_v1 import (
    normalize_adapter_result,
    validate_adapter_result,
)
# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parents[2]

BULK_ROOT = BASE / "bulk_official"

PERMISSION_REGISTRY_FILE = (
    BULK_ROOT
    / "source_permission_registry.json"
)

MARKET_MASTER_FILE = (
    BASE
    / "unified_data_platform"
    / "inputs"
    / "markets"
    / "cloud_market_master.json"
)

INPUT_DIR = BULK_ROOT / "inputs"

OUTPUT_BATCH_FILE = (
    INPUT_DIR
    / "bulk_official_batch_001.json"
)

REPORT_DIR = BULK_ROOT / "reports"

COLLECTOR_REPORT_FILE = (
    REPORT_DIR
    / "bulk_official_collector_v1_report.json"
)

SIMULATION_MODE = False

# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.now().isoformat(
        timespec="seconds"
    )


def read_json(path):
    with Path(path).open(
        "r",
        encoding="utf-8-sig",
    ) as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


# ============================================================
# PERMISSION REGISTRY
# ============================================================

def load_permission_registry():
    if not PERMISSION_REGISTRY_FILE.exists():
        return {
            "defaultPolicy":
                "deny_unless_approved",
            "markets": {},
        }

    data = read_json(
        PERMISSION_REGISTRY_FILE
    )

    markets = {}

    for row in data.get(
        "markets",
        [],
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        market_id = str(
            row.get("marketId")
            or ""
        ).strip()

        if not market_id:
            continue

        markets[
            market_id
        ] = row

    return {
        "defaultPolicy":
            data.get(
                "defaultPolicy",
                "deny_unless_approved",
            ),
        "markets":
            markets,
    }


def permission_allowed(
    registry,
    market_id,
    module_name,
):
    market = (
        registry
        .get("markets", {})
        .get(market_id)
    )

    if market is None:
        return False

    permissions = market.get(
        "permissions",
        {}
    )

    rule = permissions.get(
        module_name,
        {}
    )

    return (
        rule.get("allowed") is True
        and str(
            rule.get("status")
            or ""
        ).strip().lower()
        == "approved"
    )


# ============================================================
# DYNAMIC MARKET DISCOVERY
# ============================================================

def discover_markets():
    if not MARKET_MASTER_FILE.exists():
        return {}

    data = read_json(
        MARKET_MASTER_FILE
    )

    markets = {}

    for row in data.get(
        "markets",
        [],
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        market_id = str(
            row.get("marketId")
            or ""
        ).strip()

        if not market_id:
            continue

        markets[
            market_id
        ] = row

    return markets


# ============================================================
# ADAPTER REGISTRY
# ============================================================
#
# ÅÄ°MDÄ°LÄ°K ADAPTER YOK.
#
# Ä°zin geldikÃ§e ilgili market adapterÄ±
# buraya kaydedilecek.
#
# Collector'Ä±n ana motoru deÄŸiÅŸmeyecek.
#
# ============================================================
ADAPTER_REGISTRY = {}


def discover_adapters():
    adapters_dir = (
        BASE
        / "adapters"
    )

    registry = {}

    if not adapters_dir.exists():
        return registry

    for path in sorted(
        adapters_dir.glob("*_adapter_v*.py")
    ):
        if path.name == "__init__.py":
            continue

        module_name = (
            "dynamic_adapter_"
            + path.stem
        )

        spec = importlib.util.spec_from_file_location(
            module_name,
            path,
        )

        if (
            spec is None
            or spec.loader is None
        ):
            continue

        module = importlib.util.module_from_spec(
            spec
        )

        spec.loader.exec_module(
            module
        )

        market_id = str(
            getattr(
                module,
                "MARKET_ID",
                "",
            )
            or ""
        ).strip()

        collect_fn = getattr(
            module,
            "collect",
            None,
        )

        if (
            not market_id
            or not callable(
                collect_fn
            )
        ):
            continue

        registry[
            market_id
        ] = collect_fn

    return registry


def refresh_adapter_registry():
    global ADAPTER_REGISTRY

    ADAPTER_REGISTRY = (
        discover_adapters()
    )

    return ADAPTER_REGISTRY


def get_adapter(market_id):
    return ADAPTER_REGISTRY.get(
        market_id
    )


# ============================================================
# EMPTY NORMALIZED RESULT
# ============================================================

def empty_collection():
    return {
        "products": [],
        "prices": [],
        "images": [],
        "catalogs": [],
        "branches": [],
    }

def permission_allowed_for_run(
    registry,
    market_id,
    module_name,
):
    if SIMULATION_MODE:
        # Sadece simÃ¼lasyon testi.
        # GerÃ§ek permission registry deÄŸiÅŸmez.
        if market_id == "bim":
            return module_name in {
                "automatedCollection",
                "prices",
                "images",
                "catalogs",
                "branches",
            }

    return permission_allowed(
        registry,
        market_id,
        module_name,
    )


# ============================================================
# COLLECT MARKET
# ============================================================

def collect_market(
    market_id,
    registry,
):
    result = empty_collection()

    # Ana otomatik toplama vanasÄ±.
    if not permission_allowed_for_run(
    registry,
    market_id,
    "automatedCollection",
):
        return {
            "status":
                "automatic_collection_closed",
            "marketId":
                market_id,
            "collection":
                result,
        }

    adapter = get_adapter(
        market_id
    )

    # Ä°zin var ama henÃ¼z adapter yoksa
    # hiÃ§bir aÄŸ isteÄŸi yapma.
    if adapter is None:
        return {
            "status":
                "adapter_not_configured",
            "marketId":
                market_id,
            "collection":
                result,
        }

    module_permissions = {
        "prices":
     permission_allowed_for_run(
                registry,
                market_id,
                "prices",
            ),

        "images":
          permission_allowed_for_run(
                registry,
                market_id,
                "images",
            ),

        "catalogs":
           permission_allowed_for_run(
                registry,
                market_id,
                "catalogs",
            ),

        "branches":
        permission_allowed_for_run(
                registry,
                market_id,
                "branches",
            ),
    }

    raw_collected = adapter(
        market_id=market_id,
        permissions=module_permissions,
    )

    collected = normalize_adapter_result(
        raw_collected,
        market_id=market_id,
        adapter_name=getattr(
            adapter,
            "__name__",
            "unknown_adapter",
        ),
    )

    contract_errors = validate_adapter_result(
        collected
    )

    if contract_errors:
        return {
            "status":
                "adapter_contract_invalid",

            "marketId":
                market_id,

            "contractErrors":
                contract_errors,

            "collection":
                result,
        }

    # Ä°kinci collector-side gÃ¼venlik filtresi.
    if module_permissions[
        "prices"
    ]:
        result["prices"] = (
            collected.get(
                "prices",
                [],
            )
        )

        result["products"] = (
            collected.get(
                "products",
                [],
            )
        )

    if module_permissions[
        "images"
    ]:
        result["images"] = (
            collected.get(
                "images",
                [],
            )
        )

    if module_permissions[
        "catalogs"
    ]:
        result["catalogs"] = (
            collected.get(
                "catalogs",
                [],
            )
        )

    if module_permissions[
        "branches"
    ]:
        result["branches"] = (
            collected.get(
                "branches",
                [],
            )
        )

    return {
        "status": "collected",
        "marketId": market_id,
        "collection": result,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 80)
    print(
        "INDIRIMLI BULK OFFICIAL COLLECTOR V1"
    )
    print("=" * 80)

    INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry = (
        load_permission_registry()
    )
    refresh_adapter_registry()

    markets = discover_markets()

    batch = {
        "schemaVersion": 1,
        "batchId":
            "bulk_official_batch_001",
        "source":
            "official_multi_market",
        "createdAt":
            now(),
        "products": [],
        "prices": [],
        "images": [],
        "catalogs": [],
        "branches": [],
    }

    report_rows = []

    for market_id in sorted(
        markets.keys()
    ):
        result = collect_market(
            market_id,
            registry,
        )

        report_rows.append({
            "marketId":
                market_id,
            "status":
                result["status"],
        })

        collected = result[
            "collection"
        ]

        batch["products"].extend(
            collected["products"]
        )

        batch["prices"].extend(
            collected["prices"]
        )

        batch["images"].extend(
            collected["images"]
        )

        batch["catalogs"].extend(
            collected["catalogs"]
        )

        batch["branches"].extend(
            collected["branches"]
        )

    write_json(
        OUTPUT_BATCH_FILE,
        batch,
    )

    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "collector":
            "bulk_official_collector_v1",

        "marketCount":
            len(markets),

        "markets":
            report_rows,

        "counts": {
            "products":
                len(batch["products"]),

            "prices":
                len(batch["prices"]),

            "images":
                len(batch["images"]),

            "catalogs":
                len(batch["catalogs"]),

            "branches":
                len(batch["branches"]),
        },

        "batchFile":
            str(
                OUTPUT_BATCH_FILE
            ),
    }

    write_json(
        COLLECTOR_REPORT_FILE,
        report,
    )

    print(
        "Discovered markets :",
        len(markets),
    )

    for row in report_rows:
        print(
            row["marketId"],
            "->",
            row["status"],
        )

    print()
    print(
        "Products :",
        len(batch["products"]),
    )
    print(
        "Prices   :",
        len(batch["prices"]),
    )
    print(
        "Images   :",
        len(batch["images"]),
    )
    print(
        "Catalogs :",
        len(batch["catalogs"]),
    )
    print(
        "Branches :",
        len(batch["branches"]),
    )

    print("=" * 80)

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()

    except Exception as exc:
        print()
        print(
            "BULK OFFICIAL COLLECTOR V1 ERROR"
        )
        print(
            repr(exc)
        )

        exit_code = 1

    sys.exit(exit_code)

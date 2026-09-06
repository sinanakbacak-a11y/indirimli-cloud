from dataclasses import dataclass, field
from typing import Any, Dict, List


# ============================================================
# ADAPTER CONTRACT V1
# ============================================================

ADAPTER_CONTRACT_VERSION = 1


@dataclass
class AdapterContext:
    market_id: str

    permissions: Dict[str, bool]

    simulation_mode: bool = False

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class AdapterResult:
    schema_version: int = (
        ADAPTER_CONTRACT_VERSION
    )

    market_id: str = ""

    adapter_name: str = ""

    adapter_version: str = "1"

    products: List[Dict[str, Any]] = field(
        default_factory=list
    )

    prices: List[Dict[str, Any]] = field(
        default_factory=list
    )

    images: List[Dict[str, Any]] = field(
        default_factory=list
    )

    catalogs: List[Dict[str, Any]] = field(
        default_factory=list
    )

    branches: List[Dict[str, Any]] = field(
        default_factory=list
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    errors: List[Dict[str, Any]] = field(
        default_factory=list
    )

    warnings: List[Dict[str, Any]] = field(
        default_factory=list
    )

    def to_dict(self):
        return {
            "schemaVersion":
                self.schema_version,

            "marketId":
                self.market_id,

            "adapterName":
                self.adapter_name,

            "adapterVersion":
                self.adapter_version,

            "products":
                self.products,

            "prices":
                self.prices,

            "images":
                self.images,

            "catalogs":
                self.catalogs,

            "branches":
                self.branches,

            "metadata":
                self.metadata,

            "errors":
                self.errors,

            "warnings":
                self.warnings,
        }


# ============================================================
# VALIDATION
# ============================================================

def validate_adapter_result(
    result: Dict[str, Any],
):
    errors = []

    if not isinstance(
        result,
        dict,
    ):
        return [
            "adapter_result_not_dict"
        ]

    required_lists = (
        "products",
        "prices",
        "images",
        "catalogs",
        "branches",
        "errors",
        "warnings",
    )

    for key in required_lists:
        if key not in result:
            errors.append(
                f"missing_{key}"
            )

            continue

        if not isinstance(
            result[key],
            list,
        ):
            errors.append(
                f"{key}_not_list"
            )

    market_id = str(
        result.get("marketId")
        or ""
    ).strip()

    if not market_id:
        errors.append(
            "market_id_missing"
        )

    adapter_name = str(
        result.get("adapterName")
        or ""
    ).strip()

    if not adapter_name:
        errors.append(
            "adapter_name_missing"
        )

    return errors


# ============================================================
# NORMALIZER
# ============================================================

def normalize_adapter_result(
    raw_result,
    market_id,
    adapter_name,
    adapter_version="1",
):
    if isinstance(
        raw_result,
        AdapterResult,
    ):
        result = raw_result.to_dict()

    elif isinstance(
        raw_result,
        dict,
    ):
        result = dict(
            raw_result
        )

    else:
        result = {}

    result.setdefault(
        "schemaVersion",
        ADAPTER_CONTRACT_VERSION,
    )

    result["marketId"] = str(
        result.get("marketId")
        or market_id
        or ""
    ).strip()

    result["adapterName"] = str(
        result.get("adapterName")
        or adapter_name
        or ""
    ).strip()

    result["adapterVersion"] = str(
        result.get("adapterVersion")
        or adapter_version
        or "1"
    ).strip()

    for key in (
        "products",
        "prices",
        "images",
        "catalogs",
        "branches",
        "errors",
        "warnings",
    ):
        value = result.get(
            key
        )

        if not isinstance(
            value,
            list,
        ):
            result[key] = []

    if not isinstance(
        result.get("metadata"),
        dict,
    ):
        result["metadata"] = {}

    return result
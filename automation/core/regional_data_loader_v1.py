import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
PLATFORM_DIR = BASE_DIR / "unified_data_platform"

BRANCH_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "branches"
    / "branch_master_v2_mapped.json"
)

PRICE_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "prices"
    / "legacy_prices_import.json"
)

OUTPUT_DIR = (
    PLATFORM_DIR
    / "regional_packages"
)

REPORT_FILE = (
    PLATFORM_DIR
    / "reports"
    / "regional_data_loader_v1_report.json"
)

QUARANTINE_FILE = (
    PLATFORM_DIR
    / "quarantine"
    / "regional_data_loader_v1_quarantine.json"
)


def read_json(path: Path, default=None):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def write_json(path: Path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def main():
    parser = argparse.ArgumentParser(
        description="Indirimli Regional Data Loader V1"
    )

    parser.add_argument(
        "--il-id",
        required=True,
        help="Yuklenecek ilin ilId degeri.",
    )

    parser.add_argument(
        "--ilce-id",
        required=True,
        help="Yuklenecek ilcenin ilceId degeri.",
    )

    args = parser.parse_args()

    il_id = clean_text(args.il_id)
    ilce_id = clean_text(args.ilce_id)

    print("=" * 60)
    print("INDIRIMLI REGIONAL DATA LOADER V1")
    print("=" * 60)
    print(f"ilId   : {il_id}")
    print(f"ilceId : {ilce_id}")
    print()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    quarantine = []

    if not BRANCH_FILE.exists():
        print(
            f"ERROR: Branch mapped dosyasi bulunamadi: {BRANCH_FILE}"
        )
        return 1

    try:
        branch_data = read_json(
            BRANCH_FILE,
            {},
        )
    except Exception as exc:
        print(
            f"ERROR: Branch JSON okunamadi: {exc}"
        )
        return 1

    branches = branch_data.get(
        "branches",
        [],
    )

    if not isinstance(branches, list):
        print("ERROR: branches liste olmali.")
        return 1

    regional_branches = []

    for branch in branches:
        if not isinstance(branch, dict):
            quarantine.append(
                {
                    "reason": "invalid_branch_record",
                    "record": branch,
                }
            )
            continue

        if (
            clean_text(branch.get("ilId")) == il_id
            and clean_text(branch.get("ilceId")) == ilce_id
            and clean_text(
                branch.get("regionMappingStatus")
            ) == "mapped"
        ):
            regional_branches.append(branch)

    regional_sube_ids = {
        clean_text(branch.get("subeId"))
        for branch in regional_branches
        if clean_text(branch.get("subeId"))
    }

    prices = []

    if PRICE_FILE.exists():
        try:
            price_data = read_json(
                PRICE_FILE,
                {},
            )

            raw_prices = price_data.get(
                "prices",
                [],
            )

            if isinstance(raw_prices, list):
                for price in raw_prices:
                    if not isinstance(price, dict):
                        quarantine.append(
                            {
                                "reason": "invalid_price_record",
                                "record": price,
                            }
                        )
                        continue

                    sube_id = clean_text(
                        price.get("subeId")
                    )

                    if sube_id in regional_sube_ids:
                        prices.append(price)

        except Exception as exc:
            quarantine.append(
                {
                    "reason": "price_file_read_error",
                    "error": str(exc),
                }
            )

    package_id = (
        f"tr_{il_id}_{ilce_id}"
        .replace(" ", "_")
        .lower()
    )

    output_file = (
        OUTPUT_DIR
        / il_id
        / ilce_id
        / "regional_package.json"
    )

    package = {
        "schemaVersion": 1,
        "packageId": package_id,
        "generatedAt": now,
        "region": {
            "ulkeId": "tr",
            "ilId": il_id,
            "ilceId": ilce_id,
        },
        "counts": {
            "branchCount": len(
                regional_branches
            ),
            "priceCount": len(prices),
        },
        "branches": regional_branches,
        "prices": prices,
    }

    report = {
        "schemaVersion": 1,
        "generatedAt": now,
        "region": {
            "ilId": il_id,
            "ilceId": ilce_id,
        },
        "inputBranchCount": len(
            branches
        ),
        "regionalBranchCount": len(
            regional_branches
        ),
        "regionalPriceCount": len(
            prices
        ),
        "quarantineCount": len(
            quarantine
        ),
        "packageFile": str(
            output_file
        ),
        "productionModified": False,
        "flutterModified": False,
        "cloudModified": False,
    }

    if quarantine:
        write_json(
            QUARANTINE_FILE,
            {
                "schemaVersion": 1,
                "generatedAt": now,
                "records": quarantine,
            },
        )

        write_json(
            REPORT_FILE,
            report,
        )

        print(
            "PACKAGE WRITE BLOCKED - quarantine mevcut."
        )
        return 3

    write_json(
        output_file,
        package,
    )

    write_json(
        QUARANTINE_FILE,
        {
            "schemaVersion": 1,
            "generatedAt": now,
            "records": [],
        },
    )

    write_json(
        REPORT_FILE,
        report,
    )

    print(
        f"Regional branches : {len(regional_branches)}"
    )
    print(
        f"Regional prices   : {len(prices)}"
    )
    print(
        "Quarantine        : 0"
    )
    print()
    print(
        "Production modified : NO"
    )
    print(
        "Flutter modified    : NO"
    )
    print(
        "Cloud modified      : NO"
    )
    print()
    print(
        "REGIONAL DATA LOADER V1 COMPLETED"
    )
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

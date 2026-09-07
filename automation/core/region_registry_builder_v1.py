import json
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
PLATFORM_DIR = BASE_DIR / "unified_data_platform"

SEED_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "regions"
    / "region_seed.json"
)

REGISTRY_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "regions"
    / "region_registry.json"
)

REPORT_FILE = (
    PLATFORM_DIR
    / "reports"
    / "region_registry_builder_v1_report.json"
)

QUARANTINE_FILE = (
    PLATFORM_DIR
    / "quarantine"
    / "region_registry_builder_v1_quarantine.json"
)


def read_json(path: Path, default=None):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

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
    print("=" * 60)
    print("INDIRIMLI REGION REGISTRY BUILDER V1")
    print("=" * 60)

    now = datetime.now().isoformat(timespec="seconds")

    if not SEED_FILE.exists():
        print(f"ERROR: region_seed.json bulunamadi: {SEED_FILE}")
        return 1

    try:
        seed = read_json(SEED_FILE, {})
    except Exception as exc:
        print(f"ERROR: Seed JSON okunamadi: {exc}")
        return 1

    country = seed.get("country", {})
    iller = seed.get("iller", [])

    if not isinstance(country, dict):
        print("ERROR: country object olmali.")
        return 1

    if not isinstance(iller, list):
        print("ERROR: iller liste olmali.")
        return 1

    ulke_id = clean_text(country.get("ulkeId"))
    ulke_adi = clean_text(country.get("ad"))

    if not ulke_id or not ulke_adi:
        print("ERROR: country.ulkeId ve country.ad zorunlu.")
        return 1

    quarantine = []
    valid_iller = []

    seen_il_ids = set()
    seen_il_names = set()

    total_ilce_count = 0

    for il_index, il in enumerate(iller):
        if not isinstance(il, dict):
            quarantine.append(
                {
                    "reason": "invalid_il_record",
                    "index": il_index,
                    "record": il,
                }
            )
            continue

        il_id = clean_text(il.get("ilId"))
        il_adi = clean_text(il.get("ad"))
        ilceler = il.get("ilceler", [])

        if not il_id or not il_adi:
            quarantine.append(
                {
                    "reason": "missing_il_identity",
                    "index": il_index,
                    "record": il,
                }
            )
            continue

        normalized_il_name = il_adi.casefold()

        if il_id in seen_il_ids:
            quarantine.append(
                {
                    "reason": "duplicate_il_id",
                    "ilId": il_id,
                }
            )
            continue

        if normalized_il_name in seen_il_names:
            quarantine.append(
                {
                    "reason": "duplicate_il_name",
                    "ad": il_adi,
                }
            )
            continue

        if not isinstance(ilceler, list):
            quarantine.append(
                {
                    "reason": "ilceler_not_list",
                    "ilId": il_id,
                }
            )
            continue

        seen_il_ids.add(il_id)
        seen_il_names.add(normalized_il_name)

        valid_ilceler = []
        seen_ilce_ids = set()
        seen_ilce_names = set()

        for ilce_index, ilce in enumerate(ilceler):
            if not isinstance(ilce, dict):
                quarantine.append(
                    {
                        "reason": "invalid_ilce_record",
                        "ilId": il_id,
                        "index": ilce_index,
                        "record": ilce,
                    }
                )
                continue

            ilce_id = clean_text(ilce.get("ilceId"))
            ilce_adi = clean_text(ilce.get("ad"))

            if not ilce_id or not ilce_adi:
                quarantine.append(
                    {
                        "reason": "missing_ilce_identity",
                        "ilId": il_id,
                        "index": ilce_index,
                        "record": ilce,
                    }
                )
                continue

            normalized_ilce_name = ilce_adi.casefold()

            if ilce_id in seen_ilce_ids:
                quarantine.append(
                    {
                        "reason": "duplicate_ilce_id",
                        "ilId": il_id,
                        "ilceId": ilce_id,
                    }
                )
                continue

            if normalized_ilce_name in seen_ilce_names:
                quarantine.append(
                    {
                        "reason": "duplicate_ilce_name",
                        "ilId": il_id,
                        "ad": ilce_adi,
                    }
                )
                continue

            seen_ilce_ids.add(ilce_id)
            seen_ilce_names.add(normalized_ilce_name)

            valid_ilceler.append(
                {
                    "ilceId": ilce_id,
                    "ad": ilce_adi,
                    "status": clean_text(
                        ilce.get("status")
                    ) or "active",
                }
            )

        total_ilce_count += len(valid_ilceler)

        valid_iller.append(
            {
                "ilId": il_id,
                "ad": il_adi,
                "status": clean_text(
                    il.get("status")
                ) or "active",
                "ilceler": valid_ilceler,
            }
        )

    registry = {
        "schemaVersion": 1,
        "updatedAt": now,
        "country": {
            "ulkeId": ulke_id,
            "ad": ulke_adi,
        },
        "iller": valid_iller,
    }

    report = {
        "schemaVersion": 1,
        "generatedAt": now,
        "inputIlCount": len(iller),
        "validIlCount": len(valid_iller),
        "validIlceCount": total_ilce_count,
        "quarantineCount": len(quarantine),
        "flutterModified": False,
        "cloudModified": False,
        "productionModified": False,
    }

    write_json(REGISTRY_FILE, registry)

    write_json(
        REPORT_FILE,
        report,
    )

    write_json(
        QUARANTINE_FILE,
        {
            "schemaVersion": 1,
            "generatedAt": now,
            "records": quarantine,
        },
    )

    print()
    print(f"Input il          : {len(iller)}")
    print(f"Valid il          : {len(valid_iller)}")
    print(f"Valid ilce        : {total_ilce_count}")
    print(f"Quarantine        : {len(quarantine)}")
    print()
    print("Flutter modified   : NO")
    print("Cloud modified     : NO")
    print("Production modified: NO")
    print()
    print("REGION REGISTRY BUILDER V1 COMPLETED")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

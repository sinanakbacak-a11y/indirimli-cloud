import json
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
PLATFORM_DIR = BASE_DIR / "unified_data_platform"

REGISTRY_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "regions"
    / "region_registry.json"
)

LOADER_FILE = (
    BASE_DIR
    / "automation"
    / "core"
    / "regional_data_loader_v1.py"
)


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def main():
    print("=" * 60)
    print("INDIRIMLI REGIONAL DATA LOADER DRIVER V1")
    print("=" * 60)
    print("FAIL-CLOSED MODE : ENABLED")
    print("PRODUCTION WRITE : DISABLED")
    print()

    if not REGISTRY_FILE.exists():
        print(f"BLOCKED: region registry not found: {REGISTRY_FILE}")
        return 1

    if not LOADER_FILE.exists():
        print(f"BLOCKED: regional loader not found: {LOADER_FILE}")
        return 1

    try:
        registry = read_json(REGISTRY_FILE)
    except Exception as exc:
        print(f"BLOCKED: region registry invalid: {exc}")
        return 1

    if not isinstance(registry, dict):
        print("BLOCKED: region registry root is not an object")
        return 1

    iller = registry.get("iller")

    if not isinstance(iller, list):
        print("BLOCKED: region registry iller must be a list")
        return 1

    regions = []

    for il in iller:
        if not isinstance(il, dict):
            print("BLOCKED: invalid il record in region registry")
            return 1

        il_id = clean_text(il.get("ilId"))
        ilceler = il.get("ilceler")

        if not il_id:
            print("BLOCKED: ilId missing in region registry")
            return 1

        if not isinstance(ilceler, list):
            print(f"BLOCKED: ilceler invalid for ilId={il_id}")
            return 1

        for ilce in ilceler:
            if not isinstance(ilce, dict):
                print(f"BLOCKED: invalid ilce record for ilId={il_id}")
                return 1

            ilce_id = clean_text(ilce.get("ilceId"))

            if not ilce_id:
                print(f"BLOCKED: ilceId missing for ilId={il_id}")
                return 1

            regions.append((il_id, ilce_id))

    print(f"Registry il count      : {len(iller)}")
    print(f"Registry region count  : {len(regions)}")
    print()

    if not regions:
        print("NO REGIONS AVAILABLE")
        print("Regional loader execution skipped.")
        print()
        print("Production modified : NO")
        print("Flutter modified    : NO")
        print("Cloud modified      : NO")
        print()
        print("REGIONAL DATA LOADER DRIVER V1 PASS")
        print("=" * 60)
        return 0

    for index, (il_id, ilce_id) in enumerate(regions, start=1):
        print()
        print(f"[{index}/{len(regions)}] ilId={il_id} ilceId={ilce_id}")

        result = subprocess.run(
            [
                sys.executable,
                str(LOADER_FILE),
                "--il-id",
                il_id,
                "--ilce-id",
                ilce_id,
            ],
            cwd=str(BASE_DIR),
        )

        if result.returncode != 0:
            print(
                f"BLOCKED: regional loader failed "
                f"ilId={il_id} ilceId={ilce_id} "
                f"exit={result.returncode}"
            )
            print("No later region will be executed.")
            return 1

    print()
    print("All registered regions processed.")
    print("Production modified : NO")
    print("Flutter modified    : NO")
    print("Cloud modified      : NO")
    print()
    print("REGIONAL DATA LOADER DRIVER V1 PASS")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

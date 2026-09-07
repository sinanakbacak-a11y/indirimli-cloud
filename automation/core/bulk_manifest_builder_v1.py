import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]

BULK_ROOT = BASE / "bulk_official"
BATCH_FILE = BULK_ROOT / "outputs" / "bulk_official_batch.json"
REPORT_FILE = BULK_ROOT / "reports" / "bulk_official_collector_report.json"
MANIFEST_FILE = BULK_ROOT / "bulk_manifest.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")

    with tmp.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    tmp.replace(path)


def main():
    print("=" * 80)
    print("INDIRIMLI BULK MANIFEST BUILDER V1")
    print("=" * 80)

    if not BATCH_FILE.exists():
        print("ERROR: collector batch yok.")
        return 2

    if not REPORT_FILE.exists():
        print("ERROR: collector report yok.")
        return 2

    batch = read_json(BATCH_FILE)
    report = read_json(REPORT_FILE)

    if not isinstance(batch, dict):
        print("ERROR: collector batch gecersiz.")
        return 2

    if not isinstance(report, dict):
        print("ERROR: collector report gecersiz.")
        return 2

    markets = []

    for row in report.get("markets", []):
        if not isinstance(row, dict):
            continue

        market_id = str(
            row.get("marketId", "")
        ).strip()

        if market_id:
            markets.append(market_id)

    markets = sorted(set(markets))

    manifest = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "batchId": str(
            batch.get("batchId", "")
        ).strip(),
        "source": str(
            batch.get("source", "")
        ).strip(),

        "markets": markets,

        "categories": [],

        "modules": {
            "prices": {
                "verifiedOnly": True
            }
        },

        "safety": {
            "rejectAutomaticTestPrices": True,
            "requireOfficialSourceForProduction": True
        }
    }

    write_json(
        MANIFEST_FILE,
        manifest,
    )

    print(
        "Markets  :",
        len(markets),
    )

    print(
        "Categories:",
        len(manifest["categories"]),
    )

    print(
        "Manifest :",
        MANIFEST_FILE,
    )

    print(
        "MANIFEST BUILDER V1 PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

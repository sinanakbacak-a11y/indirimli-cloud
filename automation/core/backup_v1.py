import json
import sys
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]

LIVE_POINTER = BASE / "live" / "latest.json"
BACKUP_ROOT = BASE / "backup"
SNAPSHOT_ROOT = BACKUP_ROOT / "snapshots"


def now():
    return datetime.now().isoformat(timespec="seconds")


def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    print("=" * 80)
    print("INDIRIMLI BACKUP V1")
    print("=" * 80)

    if not LIVE_POINTER.exists():
        print("BACKUP V1 : BLOCKED")
        print("Reason    : live/latest.json bulunamadi.")
        return 2

    try:
        live = read_json(LIVE_POINTER)
    except Exception as exc:
        print("BACKUP V1 : BLOCKED")
        print(f"Reason    : live/latest.json okunamadi: {exc}")
        return 2

    package_id = str(live.get("packageId") or "").strip()
    manifest_path = str(live.get("manifestPath") or "").strip()
    manifest_sha256 = str(live.get("manifestSha256") or "").strip()
    mode = str(live.get("mode") or "").strip()

    if not package_id or not manifest_path or not manifest_sha256:
        print("BACKUP V1 : BLOCKED")
        print("Reason    : live pointer eksik alan iceriyor.")
        return 2

    existing_snapshots = sorted(SNAPSHOT_ROOT.glob("snapshot_*.json"))

    for existing_snapshot_path in reversed(existing_snapshots):
        try:
            existing_snapshot = read_json(existing_snapshot_path)
        except Exception:
            continue

        if (
            existing_snapshot.get("packageId") == package_id
            and existing_snapshot.get("manifestSha256") == manifest_sha256
            and existing_snapshot.get("restoreEligible") is True
        ):
            print("BACKUP V1 : ALREADY BACKED UP")
            print(f"Existing Snapshot : {existing_snapshot_path}")
            return 0

    snapshot_id = "snapshot_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = SNAPSHOT_ROOT / f"{snapshot_id}.json"

    snapshot = {
        "schemaVersion": 1,
        "backupVersion": 1,
        "snapshotId": snapshot_id,
        "createdAt": now(),
        "source": "live/latest.json",
        "packageId": package_id,
        "manifestPath": manifest_path,
        "manifestSha256": manifest_sha256,
        "mode": mode,
        "active": live.get("active") is True,
        "restoreEligible": True,
    }

    try:
        write_json(snapshot_path, snapshot)
    except Exception as exc:
        print("BACKUP V1 : FAILED")
        print(f"Reason    : snapshot yazilamadi: {exc}")
        return 1

    print("Package ID      :", package_id)
    print("Manifest SHA256 :", manifest_sha256)
    print("Snapshot        :", snapshot_path)
    print("-" * 80)
    print("LIVE POINTER    : READ ONLY")
    print("BACKUP V1       : PASS")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]

LIVE_POINTER = BASE / "live" / "latest.json"
BACKUP_ROOT = BASE / "backup"
LATEST_BACKUP = BACKUP_ROOT / "latest_backup.json"


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
    print("INDIRIMLI RESTORE V1")
    print("=" * 80)

    if not LATEST_BACKUP.exists():
        print("RESTORE V1 : BLOCKED")
        print("Reason     : backup/latest_backup.json bulunamadi.")
        return 2

    if not LIVE_POINTER.exists():
        print("RESTORE V1 : BLOCKED")
        print("Reason     : live/latest.json bulunamadi.")
        return 2

    try:
        backup = read_json(LATEST_BACKUP)
    except Exception as exc:
        print("RESTORE V1 : BLOCKED")
        print(f"Reason     : backup okunamadi: {exc}")
        return 2

    if backup.get("restoreEligible") is not True:
        print("RESTORE V1 : BLOCKED")
        print("Reason     : backup restore icin uygun degil.")
        return 2

    package_id = str(backup.get("packageId") or "").strip()
    manifest_path = str(backup.get("manifestPath") or "").strip()
    manifest_sha256 = str(backup.get("manifestSha256") or "").strip()
    mode = str(backup.get("mode") or "").strip()

    if not package_id or not manifest_path or not manifest_sha256:
        print("RESTORE V1 : BLOCKED")
        print("Reason     : backup gerekli alanlari icermiyor.")
        return 2

    restored_pointer = {
        "schemaVersion": 1,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "packageId": package_id,
        "manifestPath": manifest_path,
        "manifestSha256": manifest_sha256,
        "mode": mode,
        "active": True,
    }

    try:
        write_json(LIVE_POINTER, restored_pointer)
    except Exception as exc:
        print("RESTORE V1 : FAILED")
        print(f"Reason     : live pointer yazilamadi: {exc}")
        return 1

    print("Restored Package :", package_id)
    print("Manifest SHA256  :", manifest_sha256)
    print("Source Snapshot  :", LATEST_BACKUP)
    print("-" * 80)
    print("LIVE POINTER     : RESTORED")
    print("RESTORE V1       : PASS")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
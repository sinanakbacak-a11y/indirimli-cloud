import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
PLATFORM_DIR = BASE_DIR / "unified_data_platform"

INDEX_FILE = (
    PLATFORM_DIR
    / "indexes"
    / "regional_package_index.json"
)

CACHE_MANIFEST_FILE = (
    PLATFORM_DIR
    / "regional_cache"
    / "cache_manifest.json"
)

SYNC_PLAN_FILE = (
    PLATFORM_DIR
    / "regional_cache"
    / "regional_cache_sync_plan.json"
)

REPORT_FILE = (
    PLATFORM_DIR
    / "reports"
    / "regional_cache_sync_v1_report.json"
)

QUARANTINE_FILE = (
    PLATFORM_DIR
    / "quarantine"
    / "regional_cache_sync_v1_quarantine.json"
)


def read_json(path: Path, default=None):
    if not path.exists():
        return default

    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as file:
        return json.load(file)


def write_json(path: Path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
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

def file_sha256(path: Path):
    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha256.update(chunk)

    return sha256.hexdigest()

def main():
    print("=" * 60)
    print("INDIRIMLI REGIONAL CACHE SYNC V1")
    print("=" * 60)
    print()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    quarantine = []

    if not INDEX_FILE.exists():
        print(
            "ERROR: regional_package_index.json bulunamadi."
        )
        return 1

    try:
        index_data = read_json(
            INDEX_FILE,
            {},
        )
    except Exception as exc:
        print(
            f"ERROR: Index JSON okunamadi: {exc}"
        )
        return 1

    remote_packages = index_data.get(
        "packages",
        [],
    )

    if not isinstance(remote_packages, list):
        print(
            "ERROR: Index packages liste olmali."
        )
        return 1

    cache_manifest = read_json(
        CACHE_MANIFEST_FILE,
        {
            "schemaVersion": 1,
            "updatedAt": "",
            "packages": [],
        },
    )

    if not isinstance(cache_manifest, dict):
        print(
            "ERROR: Cache manifest root object olmali."
        )
        return 1

    cached_packages = cache_manifest.get(
        "packages",
        [],
    )

    if not isinstance(cached_packages, list):
        print(
            "ERROR: Cache packages liste olmali."
        )
        return 1

    remote_by_id = {}
    cached_by_id = {}

    for package in remote_packages:
        if not isinstance(package, dict):
            quarantine.append(
                {
                    "reason": "invalid_remote_package",
                    "record": package,
                }
            )
            continue

        package_id = clean_text(
            package.get("packageId")
        )

        checksum = clean_text(
            package.get("checksum")
        )

        checksum_algorithm = clean_text(
            package.get("checksumAlgorithm")
        )

        package_path = clean_text(
            package.get("packagePath")
        )

        if (
            not package_id
            or not checksum
            or checksum_algorithm != "sha256"
            or not package_path
        ):
            quarantine.append(
                {
                    "reason": (
                        "invalid_remote_package_metadata"
                    ),
                    "packageId": package_id,
                }
            )
            continue

        if package_id in remote_by_id:
            quarantine.append(
                {
                    "reason": (
                        "duplicate_remote_package_id"
                    ),
                    "packageId": package_id,
                }
            )
            continue

        remote_by_id[package_id] = package

    for package in cached_packages:
        if not isinstance(package, dict):
            quarantine.append(
                {
                    "reason": "invalid_cached_package",
                    "record": package,
                }
            )
            continue

        package_id = clean_text(
            package.get("packageId")
        )

        if not package_id:
            quarantine.append(
                {
                    "reason": (
                        "cached_package_missing_id"
                    ),
                    "record": package,
                }
            )
            continue

        if package_id in cached_by_id:
            quarantine.append(
                {
                    "reason": (
                        "duplicate_cached_package_id"
                    ),
                    "packageId": package_id,
                }
            )
            continue

        cached_by_id[package_id] = package

    sync_items = []

    cache_valid_count = 0
    cache_missing_count = 0
    checksum_changed_count = 0

    for package_id in sorted(
        remote_by_id.keys()
    ):
        remote = remote_by_id[
            package_id
        ]

        cached = cached_by_id.get(
            package_id
        )

        remote_checksum = clean_text(
            remote.get("checksum")
        )

        cached_checksum = ""

        if cached is not None:
            cached_checksum = clean_text(
                cached.get("checksum")
            )
        cached_package_exists = False

        if cached is not None:
            cached_package_path = clean_text(
                cached.get("packagePath")
            )

            if cached_package_path:
                cached_package_file = (
                    PLATFORM_DIR
                    / cached_package_path
                )

                cached_package_exists = (
                    cached_package_file.exists()
                    and cached_package_file.is_file()
                )

                if cached_package_exists:
                    cached_checksum = file_sha256(
                        cached_package_file
                    )
        if (
            not cached_checksum
            or not cached_package_exists
        ):
            state = "cache_missing"
            decision = "download_required"
            cache_missing_count += 1
        elif (
            cached_checksum
            == remote_checksum
        ):
            state = "cache_valid"
            decision = "no_download"
            cache_valid_count += 1

        else:
            state = "checksum_changed"
            decision = "download_required"
            checksum_changed_count += 1

        sync_items.append(
            {
                "packageId": package_id,
                "ulkeId": clean_text(
                    remote.get("ulkeId")
                ),
                "ilId": clean_text(
                    remote.get("ilId")
                ),
                "ilceId": clean_text(
                    remote.get("ilceId")
                ),
                "state": state,
                "decision": decision,
                "packagePath": clean_text(
                    remote.get("packagePath")
                ),

                "downloadUrl": clean_text(
    remote.get("downloadUrl")
),

                "remoteChecksum": (
                    remote_checksum
                ),
                "cachedChecksum": (
                    cached_checksum
                ),
                "sizeBytes": remote.get(
                    "sizeBytes",
                    0,
                ),
            }
        )

    orphaned_cache = []

    for package_id in sorted(
        cached_by_id.keys()
    ):
        if package_id not in remote_by_id:
            orphaned_cache.append(
                {
                    "packageId": package_id,
                    "reason": (
                        "not_present_in_current_index"
                    ),
                }
            )

    download_required_count = (
        cache_missing_count
        + checksum_changed_count
    )

    sync_plan = {
        "schemaVersion": 1,
        "generatedAt": now,
        "country": clean_text(
            index_data.get("country")
        ) or "tr",
        "summary": {
            "totalRemotePackages": len(
                remote_by_id
            ),
            "cacheValid": (
                cache_valid_count
            ),
            "downloadRequired": (
                download_required_count
            ),
            "cacheMissing": (
                cache_missing_count
            ),
            "checksumChanged": (
                checksum_changed_count
            ),
            "orphanedCache": len(
                orphaned_cache
            ),
        },
        "packages": sync_items,
        "orphanedCache": orphaned_cache,
    }

    report = {
        "schemaVersion": 1,
        "generatedAt": now,
        "remotePackageCount": len(
            remote_by_id
        ),
        "cachedPackageCount": len(
            cached_by_id
        ),
        "cacheValidCount": (
            cache_valid_count
        ),
        "downloadRequiredCount": (
            download_required_count
        ),
        "cacheMissingCount": (
            cache_missing_count
        ),
        "checksumChangedCount": (
            checksum_changed_count
        ),
        "orphanedCacheCount": len(
            orphaned_cache
        ),
        "quarantineCount": len(
            quarantine
        ),
        "productionActivationPerformed": False,
        "flutterModified": False,
        "cloudModified": False,
        "cacheManifestModified": False,
        "packageDownloadPerformed": False,
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
            f"Remote packages    : {len(remote_by_id)}"
        )
        print(
            f"Cached packages    : {len(cached_by_id)}"
        )
        print(
            f"Quarantine         : {len(quarantine)}"
        )
        print()
        print(
            "SYNC PLAN WRITE BLOCKED - quarantine mevcut."
        )
        print()
        print(
            "Production activation : NO"
        )
        print(
            "Flutter modified      : NO"
        )
        print(
            "Cloud modified        : NO"
        )
        print(
            "Cache manifest changed: NO"
        )
        print(
            "Package download      : NO"
        )

        return 3

    write_json(
        SYNC_PLAN_FILE,
        sync_plan,
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
        f"Total packages     : {len(remote_by_id)}"
    )
    print(
        f"Cache valid        : {cache_valid_count}"
    )
    print(
        f"Download required  : {download_required_count}"
    )
    print(
        f"Cache missing      : {cache_missing_count}"
    )
    print(
        f"Checksum changed   : {checksum_changed_count}"
    )
    print(
        f"Orphaned cache     : {len(orphaned_cache)}"
    )
    print(
        "Quarantine         : 0"
    )
    print()
    print(
        "Production activation : NO"
    )
    print(
        "Flutter modified      : NO"
    )
    print(
        "Cloud modified        : NO"
    )
    print(
        "Cache manifest changed: NO"
    )
    print(
        "Package download      : NO"
    )
    print()
    print(
        "REGIONAL CACHE SYNC V1 COMPLETED"
    )
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

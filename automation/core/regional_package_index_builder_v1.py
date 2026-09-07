import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

PLATFORM_DIR = (
    BASE_DIR
    / "unified_data_platform"
)

CONFIG_FILE = (
    PLATFORM_DIR
    / "config"
    / "regional_download_config.json"
)

PACKAGES_DIR = (
    PLATFORM_DIR
    / "regional_packages"
)

INDEXES_DIR = (
    PLATFORM_DIR
    / "indexes"
)

OUTPUT_FILE = (
    INDEXES_DIR
    / "regional_package_index.json"
)

REPORT_FILE = (
    PLATFORM_DIR
    / "reports"
    / "regional_package_index_builder_v1_report.json"
)

QUARANTINE_FILE = (
    PLATFORM_DIR
    / "quarantine"
    / "regional_package_index_builder_v1_quarantine.json"
)


def read_json(path: Path):
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

def load_download_base_url():
    config = read_json(
        CONFIG_FILE
    )

    if not isinstance(config, dict):
        return ""

    return clean_text(
        config.get("downloadBaseUrl")
    )


def calculate_sha256(path: Path):
    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            block = file.read(
                1024 * 1024
            )

            if not block:
                break

            sha256.update(block)

    return sha256.hexdigest()


def get_relative_package_path(
    package_file: Path,
):
    return package_file.relative_to(
        PLATFORM_DIR
    ).as_posix()

def build_download_url(
    package_path: str,
):
    base_url = load_download_base_url()

    if not base_url:
        return ""

    return (
        base_url.rstrip("/")
        + "/"
        + package_path.lstrip("/")
    )

def main():
    print("=" * 60)
    print(
        "INDIRIMLI REGIONAL PACKAGE INDEX BUILDER V1"
    )
    print("=" * 60)
    print()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    quarantine = []
    packages = []

    if not PACKAGES_DIR.exists():
        print(
            "ERROR: regional_packages klasoru bulunamadi."
        )
        return 1

    package_files = sorted(
        PACKAGES_DIR.rglob(
            "regional_package.json"
        )
    )

    for package_file in package_files:
        try:
            data = read_json(
                package_file
            )
        except Exception as exc:
            quarantine.append(
                {
                    "reason": "package_read_error",
                    "file": str(
                        package_file
                    ),
                    "error": str(exc),
                }
            )
            continue

        if not isinstance(data, dict):
            quarantine.append(
                {
                    "reason": "invalid_package_root",
                    "file": str(
                        package_file
                    ),
                }
            )
            continue

        package_id = clean_text(
            data.get("packageId")
        )

        region = data.get(
            "region",
            {},
        )

        counts = data.get(
            "counts",
            {},
        )

        if not isinstance(region, dict):
            region = {}

        if not isinstance(counts, dict):
            counts = {}

        ulke_id = clean_text(
            region.get("ulkeId")
        )

        il_id = clean_text(
            region.get("ilId")
        )

        ilce_id = clean_text(
            region.get("ilceId")
        )

        if (
            not package_id
            or not ulke_id
            or not il_id
            or not ilce_id
        ):
            quarantine.append(
                {
                    "reason": (
                        "missing_required_region_identity"
                    ),
                    "file": str(
                        package_file
                    ),
                    "packageId": package_id,
                    "ulkeId": ulke_id,
                    "ilId": il_id,
                    "ilceId": ilce_id,
                }
            )
            continue

        try:
            branch_count = int(
                counts.get(
                    "branchCount",
                    0,
                )
            )

            price_count = int(
                counts.get(
                    "priceCount",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            quarantine.append(
                {
                    "reason": "invalid_counts",
                    "file": str(
                        package_file
                    ),
                }
            )
            continue

        if (
            branch_count < 0
            or price_count < 0
        ):
            quarantine.append(
                {
                    "reason": "negative_counts",
                    "file": str(
                        package_file
                    ),
                }
            )
            continue

        generated_at = clean_text(
            data.get("generatedAt")
        )

        checksum = calculate_sha256(
            package_file
        )

        package_size = (
            package_file.stat().st_size
        )

        package_path = get_relative_package_path(
            package_file
        )

        packages.append(
            {
                "packageId": package_id,
                "ulkeId": ulke_id,
                "ilId": il_id,
                "ilceId": ilce_id,

                "schemaVersion": data.get(
                    "schemaVersion",
                    1,
                ),

                "updatedAt": generated_at,

                "branchCount": (
                    branch_count
                ),

                "priceCount": (
                    price_count
                ),

                "packagePath": package_path,

                "downloadUrl": build_download_url(
                    package_path
                ),

                "sizeBytes": (
                    package_size
                ),

                "checksumAlgorithm": (
                    "sha256"
                ),

                "checksum": checksum,

                "status": "candidate",
            }
        )

    # Ayni packageId iki farkli dosyada
    # bulunursa otomatik yayinlamiyoruz.
    package_ids = {}

    for package in packages:
        package_id = package[
            "packageId"
        ]

        package_ids.setdefault(
            package_id,
            0,
        )

        package_ids[
            package_id
        ] += 1

    duplicate_ids = {
        package_id
        for package_id, count
        in package_ids.items()
        if count > 1
    }

    if duplicate_ids:
        quarantine.append(
            {
                "reason": (
                    "duplicate_package_ids"
                ),
                "packageIds": sorted(
                    duplicate_ids
                ),
            }
        )

    packages = sorted(
        packages,
        key=lambda item: (
            item["ulkeId"],
            item["ilId"],
            item["ilceId"],
            item["packageId"],
        ),
    )

    total_branch_count = sum(
        item["branchCount"]
        for item in packages
    )

    total_price_count = sum(
        item["priceCount"]
        for item in packages
    )

    index = {
        "schemaVersion": 1,
        "generatedAt": now,

        "country": "tr",

        "packageCount": len(
            packages
        ),

        "totals": {
            "branchCount": (
                total_branch_count
            ),
            "priceCount": (
                total_price_count
            ),
        },

        "packages": packages,
    }

    report = {
        "schemaVersion": 1,
        "generatedAt": now,

        "packageFilesFound": len(
            package_files
        ),

        "validPackageCount": len(
            packages
        ),

        "quarantineCount": len(
            quarantine
        ),

        "duplicatePackageIds": sorted(
            duplicate_ids
        ),

        "totalBranchCount": (
            total_branch_count
        ),

        "totalPriceCount": (
            total_price_count
        ),

        "indexFile": str(
            OUTPUT_FILE
        ),

        "productionActivationPerformed": False,
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
            f"Package files      : {len(package_files)}"
        )
        print(
            f"Valid packages     : {len(packages)}"
        )
        print(
            f"Quarantine         : {len(quarantine)}"
        )
        print()
        print(
            "INDEX WRITE BLOCKED - quarantine mevcut."
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
        print()

        return 3

    write_json(
        OUTPUT_FILE,
        index,
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
        f"Package files      : {len(package_files)}"
    )
    print(
        f"Indexed packages   : {len(packages)}"
    )
    print(
        f"Total branches     : {total_branch_count}"
    )
    print(
        f"Total prices       : {total_price_count}"
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
    print()
    print(
        "REGIONAL PACKAGE INDEX BUILDER V1 COMPLETED"
    )
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

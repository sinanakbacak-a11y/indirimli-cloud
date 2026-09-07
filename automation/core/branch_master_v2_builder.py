import json
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
PLATFORM_DIR = BASE_DIR / "unified_data_platform"

BRANCHES_DIR = (
    PLATFORM_DIR
    / "inputs"
    / "branches"
)

SOURCE_FILE = (
    BRANCHES_DIR
    / "cloud_branch_master.json"
)

OUTPUT_FILE = (
    BRANCHES_DIR
    / "branch_master_v2.json"
)

REPORT_FILE = (
    PLATFORM_DIR
    / "reports"
    / "branch_master_v2_builder_report.json"
)

QUARANTINE_FILE = (
    PLATFORM_DIR
    / "quarantine"
    / "branch_master_v2_builder_quarantine.json"
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


def to_float(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    print("=" * 60)
    print("INDIRIMLI BRANCH MASTER V2 BUILDER")
    print("=" * 60)

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    if not SOURCE_FILE.exists():
        print(
            f"ERROR: Kaynak dosya bulunamadi: {SOURCE_FILE}"
        )
        return 1

    try:
        source = read_json(
            SOURCE_FILE,
            {},
        )
    except Exception as exc:
        print(
            f"ERROR: Kaynak JSON okunamadi: {exc}"
        )
        return 1

    branches = source.get(
        "branches",
        [],
    )

    if not isinstance(branches, list):
        print(
            "ERROR: branches liste olmali."
        )
        return 1

    output_branches = []
    quarantine = []

    seen_sube_ids = set()

    for index, branch in enumerate(branches):
        if not isinstance(branch, dict):
            quarantine.append(
                {
                    "reason": "invalid_branch_record",
                    "index": index,
                    "record": branch,
                }
            )
            continue

        sube_id = clean_text(
            branch.get("subeId")
        )

        market_id = clean_text(
            branch.get("marketId")
        )

        if not sube_id or not market_id:
            quarantine.append(
                {
                    "reason": "missing_branch_identity",
                    "index": index,
                    "record": branch,
                }
            )
            continue

        if sube_id in seen_sube_ids:
            quarantine.append(
                {
                    "reason": "duplicate_sube_id",
                    "subeId": sube_id,
                }
            )
            continue

        seen_sube_ids.add(
            sube_id
        )

        enlem = to_float(
            branch.get("enlem")
        )

        boylam = to_float(
            branch.get("boylam")
        )

        if enlem is None or boylam is None:
            quarantine.append(
                {
                    "reason": "invalid_coordinates",
                    "subeId": sube_id,
                    "record": branch,
                }
            )
            continue

        veri_durumu = clean_text(
            branch.get("veriDurumu")
        ) or "unknown"

        existing_status = clean_text(
            branch.get("status")
        ) or "candidate"

        il_id = clean_text(
            branch.get("ilId")
        )

        il = clean_text(
            branch.get("il")
        )

        ilce_id = clean_text(
            branch.get("ilceId")
        )

        ilce = clean_text(
            branch.get("ilce")
        )

        mahalle = clean_text(
            branch.get("mahalle")
        )

        region_mapping_status = (
            "mapped"
            if il_id and ilce_id
            else "pending_region_mapping"
        )

        # Test/candidate veriyi asla otomatik
        # production durumuna yÃ¼kseltmiyoruz.
        if veri_durumu.lower() == "test":
            status = "candidate"
        else:
            status = existing_status

        output_branches.append(
            {
                "subeId": sube_id,
                "marketId": market_id,
                "ulkeId": "tr",
                "ilId": il_id,
                "il": il,
                "ilceId": ilce_id,
                "ilce": ilce,
                "mahalle": mahalle,
                "ad": clean_text(
                    branch.get("ad")
                ),
                "sube": clean_text(
                    branch.get("sube")
                ),
                "adres": clean_text(
                    branch.get("adres")
                ),
                "enlem": enlem,
                "boylam": boylam,
                "veriDurumu": veri_durumu,
                "status": status,
                "regionMappingStatus": (
                    region_mapping_status
                ),
                "source": clean_text(
                    branch.get("source")
                ) or "cloud_branch_master",
                "sonGuncelleme": clean_text(
                    branch.get(
                        "sonGuncelleme"
                    )
                ) or now,
            }
        )

    mapped_count = sum(
        1
        for branch in output_branches
        if branch["regionMappingStatus"]
        == "mapped"
    )

    pending_mapping_count = sum(
        1
        for branch in output_branches
        if branch["regionMappingStatus"]
        == "pending_region_mapping"
    )

    test_count = sum(
        1
        for branch in output_branches
        if branch["veriDurumu"].lower()
        == "test"
    )

    output = {
        "schemaVersion": 2,
        "updatedAt": now,
        "branches": output_branches,
    }

    report = {
        "schemaVersion": 1,
        "generatedAt": now,
        "inputBranchCount": len(
            branches
        ),
        "validBranchCount": len(
            output_branches
        ),
        "mappedRegionCount": (
            mapped_count
        ),
        "pendingRegionMappingCount": (
            pending_mapping_count
        ),
        "testBranchCount": test_count,
        "quarantineCount": len(
            quarantine
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

        print()
        print(
            f"Input branches     : {len(branches)}"
        )
        print(
            f"Valid branches     : {len(output_branches)}"
        )
        print(
            f"Quarantine         : {len(quarantine)}"
        )
        print()
        print(
            "OUTPUT WRITE BLOCKED - quarantine mevcut."
        )
        print(
            "Mevcut branch_master_v2.json korunuyor."
        )

        return 3

    write_json(
        OUTPUT_FILE,
        output,
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

    print()
    print(
        f"Input branches          : {len(branches)}"
    )
    print(
        f"Valid branches          : {len(output_branches)}"
    )
    print(
        f"Mapped regions          : {mapped_count}"
    )
    print(
        f"Pending region mappings : {pending_mapping_count}"
    )
    print(
        f"Test branches           : {test_count}"
    )
    print(
        "Quarantine              : 0"
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
        "BRANCH MASTER V2 BUILDER COMPLETED"
    )
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

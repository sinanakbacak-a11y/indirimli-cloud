import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
PLATFORM_DIR = BASE_DIR / "unified_data_platform"

BRANCH_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "branches"
    / "branch_master_v2.json"
)

REGION_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "regions"
    / "region_registry.json"
)

OUTPUT_FILE = (
    PLATFORM_DIR
    / "inputs"
    / "branches"
    / "branch_master_v2_mapped.json"
)

REPORT_FILE = (
    PLATFORM_DIR
    / "reports"
    / "branch_region_mapper_v1_report.json"
)

QUARANTINE_FILE = (
    PLATFORM_DIR
    / "quarantine"
    / "branch_region_mapper_v1_quarantine.json"
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


def normalize(value):
    text = clean_text(value).casefold()

    text = text.replace("Ä±", "i")
    text = text.replace("ÅŸ", "s")
    text = text.replace("ÄŸ", "g")
    text = text.replace("Ã¼", "u")
    text = text.replace("Ã¶", "o")
    text = text.replace("Ã§", "c")

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return " ".join(
        text.split()
    )


def build_region_index(region_data):
    by_ilce_name = {}

    for il in region_data.get(
        "iller",
        [],
    ):
        if not isinstance(il, dict):
            continue

        il_id = clean_text(
            il.get("ilId")
        )

        il_adi = clean_text(
            il.get("ad")
        )

        for ilce in il.get(
            "ilceler",
            [],
        ):
            if not isinstance(ilce, dict):
                continue

            ilce_id = clean_text(
                ilce.get("ilceId")
            )

            ilce_adi = clean_text(
                ilce.get("ad")
            )

            key = normalize(
                ilce_adi
            )

            if not key:
                continue

            by_ilce_name.setdefault(
                key,
                [],
            ).append(
                {
                    "ilId": il_id,
                    "il": il_adi,
                    "ilceId": ilce_id,
                    "ilce": ilce_adi,
                }
            )

    return by_ilce_name


def score_candidate(branch, candidate):
    score = 0
    reasons = []

    adres = normalize(
        branch.get("adres")
    )

    sube = normalize(
        branch.get("sube")
    )

    il_adi = normalize(
        candidate["il"]
    )

    ilce_adi = normalize(
        candidate["ilce"]
    )

    if ilce_adi and ilce_adi in adres:
        score += 60
        reasons.append(
            "district_in_address"
        )

    if il_adi and il_adi in adres:
        score += 25
        reasons.append(
            "province_in_address"
        )

    if ilce_adi and ilce_adi in sube:
        score += 15
        reasons.append(
            "district_in_branch_name"
        )

    return score, reasons


def main():
    print("=" * 60)
    print("INDIRIMLI BRANCH REGION MAPPER V1")
    print("=" * 60)

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    if not BRANCH_FILE.exists():
        print(
            f"ERROR: branch_master_v2.json bulunamadi: {BRANCH_FILE}"
        )
        return 1

    if not REGION_FILE.exists():
        print(
            f"ERROR: region_registry.json bulunamadi: {REGION_FILE}"
        )
        return 1

    try:
        branch_data = read_json(
            BRANCH_FILE,
            {},
        )

        region_data = read_json(
            REGION_FILE,
            {},
        )
    except Exception as exc:
        print(
            f"ERROR: JSON okunamadi: {exc}"
        )
        return 1

    branches = branch_data.get(
        "branches",
        [],
    )

    if not isinstance(
        branches,
        list,
    ):
        print(
            "ERROR: branches liste olmali."
        )
        return 1

    region_index = build_region_index(
        region_data
    )

    mapped_branches = []
    quarantine = []

    mapped_count = 0
    review_count = 0
    unresolved_count = 0

    for branch in branches:
        if not isinstance(
            branch,
            dict,
        ):
            quarantine.append(
                {
                    "reason": "invalid_branch_record",
                    "record": branch,
                }
            )
            continue

        updated = deepcopy(
            branch
        )

        # Zaten doÄŸrulanmÄ±ÅŸ bÃ¶lge eÅŸlemesi varsa koru.
        if (
            clean_text(
                branch.get("ilId")
            )
            and clean_text(
                branch.get("ilceId")
            )
        ):
            updated[
                "regionMappingStatus"
            ] = "mapped"

            updated[
                "regionMappingConfidence"
            ] = 100

            updated[
                "regionMappingMethod"
            ] = "existing_verified_mapping"

            mapped_count += 1

            mapped_branches.append(
                updated
            )

            continue

        scored_candidates = []

        for candidate_list in region_index.values():
            for candidate in candidate_list:
                score, reasons = score_candidate(
                    branch,
                    candidate,
                )

                if score > 0:
                    scored_candidates.append(
                        {
                            "candidate": candidate,
                            "score": score,
                            "reasons": reasons,
                        }
                    )

        scored_candidates.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        if not scored_candidates:
            updated[
                "regionMappingStatus"
            ] = "unresolved"

            updated[
                "regionMappingConfidence"
            ] = 0

            updated[
                "regionMappingMethod"
            ] = "no_candidate"

            unresolved_count += 1

            mapped_branches.append(
                updated
            )

            continue

        best = scored_candidates[0]

        second_score = (
            scored_candidates[1]["score"]
            if len(scored_candidates) > 1
            else 0
        )

        best_score = best["score"]
        best_candidate = best["candidate"]

        # YÃ¼ksek gÃ¼ven:
        # adres iÃ§inde hem ilÃ§e hem il varsa
        # genellikle 85 puan gelir.
        if (
            best_score >= 80
            and best_score - second_score >= 20
        ):
            updated["ilId"] = (
                best_candidate["ilId"]
            )

            updated["il"] = (
                best_candidate["il"]
            )

            updated["ilceId"] = (
                best_candidate["ilceId"]
            )

            updated["ilce"] = (
                best_candidate["ilce"]
            )

            updated[
                "regionMappingStatus"
            ] = "mapped"

            updated[
                "regionMappingConfidence"
            ] = best_score

            updated[
                "regionMappingMethod"
            ] = "address_text_high_confidence"

            updated[
                "regionMappingReasons"
            ] = best["reasons"]

            mapped_count += 1

        elif best_score >= 60:
            updated[
                "regionMappingStatus"
            ] = "review_required"

            updated[
                "regionMappingConfidence"
            ] = best_score

            updated[
                "regionMappingCandidate"
            ] = best_candidate

            updated[
                "regionMappingMethod"
            ] = "address_text_medium_confidence"

            updated[
                "regionMappingReasons"
            ] = best["reasons"]

            review_count += 1

        else:
            updated[
                "regionMappingStatus"
            ] = "unresolved"

            updated[
                "regionMappingConfidence"
            ] = best_score

            updated[
                "regionMappingMethod"
            ] = "low_confidence"

            unresolved_count += 1

        mapped_branches.append(
            updated
        )

    output = {
        "schemaVersion": 2,
        "updatedAt": now,
        "branches": mapped_branches,
    }

    report = {
        "schemaVersion": 1,
        "generatedAt": now,
        "inputBranchCount": len(
            branches
        ),
        "mappedBranchCount": (
            mapped_count
        ),
        "reviewRequiredCount": (
            review_count
        ),
        "unresolvedCount": (
            unresolved_count
        ),
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
            "OUTPUT WRITE BLOCKED - quarantine mevcut."
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
        f"Input branches    : {len(branches)}"
    )
    print(
        f"Mapped branches   : {mapped_count}"
    )
    print(
        f"Review required   : {review_count}"
    )
    print(
        f"Unresolved        : {unresolved_count}"
    )
    print(
        "Quarantine        : 0"
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
        "BRANCH REGION MAPPER V1 COMPLETED"
    )
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

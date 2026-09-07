import json
import sys
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]

PLATFORM = BASE / "unified_data_platform"
CONFIG = PLATFORM / "config"
INPUTS = PLATFORM / "inputs"
REPORTS = PLATFORM / "reports"
QUARANTINE = PLATFORM / "quarantine"

ACTIVE_POINTER = CONFIG / "active_platform.json"

MARKETS_INPUT = INPUTS / "markets" / "cloud_market_master.json"
BRANCHES_INPUT = INPUTS / "branches" / "cloud_branch_master.json"
PRODUCTS_INPUT = INPUTS / "products" / "legacy_products_import.json"
PRICES_INPUT = INPUTS / "prices" / "legacy_prices_import.json"

IMPORTER_REPORT = REPORTS / "unified_importer_v1_5_report.json"
IMPORTER_QUARANTINE = QUARANTINE / "unified_importer_v1_5_quarantine.json"

OUTPUT_REPORT = REPORTS / "unified_pre_cutover_validator_v1_report.json"


def now():
    return datetime.now().isoformat(timespec="seconds")


def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")

    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tmp.replace(path)


def rows(data, key):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            return value

    return []


def failure(code, message, details=None):
    item = {
        "code": code,
        "message": message,
    }

    if details is not None:
        item["details"] = details

    return item


def main():
    print("=" * 80)
    print("INDIRIMLI UNIFIED PRE-CUTOVER VALIDATOR V1")
    print("=" * 80)

    failures = []
    warnings = []

    required_files = [
        ACTIVE_POINTER,
        MARKETS_INPUT,
        BRANCHES_INPUT,
        PRODUCTS_INPUT,
        PRICES_INPUT,
        IMPORTER_REPORT,
        IMPORTER_QUARANTINE,
    ]

    missing = [
        str(path)
        for path in required_files
        if not path.exists()
    ]

    if missing:
        failures.append(
            failure(
                "REQUIRED_FILE_MISSING",
                "Pre-cutover doğrulaması için gerekli dosyalar eksik.",
                missing,
            )
        )

    if not failures:
        try:
            pointer = read_json(ACTIVE_POINTER)
            markets = rows(read_json(MARKETS_INPUT), "markets")
            branches = rows(read_json(BRANCHES_INPUT), "branches")
            products = rows(read_json(PRODUCTS_INPUT), "products")
            prices = rows(read_json(PRICES_INPUT), "prices")
            importer_report = read_json(IMPORTER_REPORT)
            quarantine_data = read_json(IMPORTER_QUARANTINE)
        except Exception as exc:
            failures.append(
                failure(
                    "JSON_READ_ERROR",
                    "Candidate platform dosyaları okunamadı.",
                    repr(exc),
                )
            )

    if not failures:
        print("1/6 Required files       : PASS")

        relation_errors = importer_report.get("relationErrors", 0)

        if relation_errors != 0:
            failures.append(
                failure(
                    "RELATION_ERRORS",
                    "Importer relationErrors sıfır değil.",
                    relation_errors,
                )
            )

        print(
            "2/6 Relation integrity   :",
            "PASS" if relation_errors == 0 else "FAIL",
        )

        if not markets:
            failures.append(
                failure(
                    "NO_MARKETS",
                    "Candidate platform içinde market bulunmuyor.",
                )
            )

        if not branches:
            failures.append(
                failure(
                    "NO_BRANCHES",
                    "Candidate platform içinde şube bulunmuyor.",
                )
            )

        if not products:
            failures.append(
                failure(
                    "NO_PRODUCTS",
                    "Candidate platform içinde ürün bulunmuyor.",
                )
            )

        print(
            "3/6 Candidate contents   :",
            "PASS"
            if markets and branches and products
            else "FAIL",
        )

        candidate_valid = bool(pointer.get("candidateValidated"))
        cutover_approved = bool(pointer.get("cutoverApproved"))
        automatic_fallback = bool(pointer.get("automaticFallback"))

        if not candidate_valid:
            failures.append(
                failure(
                    "CANDIDATE_NOT_VALIDATED",
                    "Importer candidateValidated=true değil.",
                )
            )

        if cutover_approved:
            failures.append(
                failure(
                    "CUTOVER_ALREADY_APPROVED",
                    "Pre-cutover aşamasında cutoverApproved true olamaz.",
                )
            )

        if automatic_fallback:
            failures.append(
                failure(
                    "AUTOMATIC_FALLBACK_ENABLED",
                    "Automatic fallback pre-cutover aşamasında açık olamaz.",
                )
            )

        print(
            "4/6 Cutover gate        :",
            "PASS"
            if candidate_valid
            and not cutover_approved
            and not automatic_fallback
            else "FAIL",
        )

        quarantine_rows = rows(
            quarantine_data,
            "kayitlar",
        )

        unexpected = [
            item
            for item in quarantine_rows
            if not isinstance(item, dict)
        ]

        if unexpected:
            failures.append(
                failure(
                    "INVALID_QUARANTINE",
                    "Quarantine içinde geçersiz kayıt yapısı var.",
                    len(unexpected),
                )
            )

        print(
            "5/6 Quarantine structure:",
            "PASS" if not unexpected else "FAIL",
        )

        report_candidate_valid = bool(
            importer_report.get("candidateValidated")
        )

        if not report_candidate_valid:
            failures.append(
                failure(
                    "IMPORTER_REPORT_NOT_VALIDATED",
                    "Importer raporunda candidateValidated=true değil.",
                )
            )

        if importer_report.get("cutoverApproved") is True:
            failures.append(
                failure(
                    "IMPORTER_REPORT_CUTOVER",
                    "Importer raporunda cutoverApproved true.",
                )
            )

        print(
            "6/6 Importer report     :",
            "PASS"
            if report_candidate_valid
            and importer_report.get("cutoverApproved") is not True
            else "FAIL",
        )

    passed = not failures

    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "validator": "unified_pre_cutover_validator_v1",
        "passed": passed,
        "failures": failures,
        "warnings": warnings,
    }

    write_json(OUTPUT_REPORT, report)

    print("-" * 80)
    print("PRE-CUTOVER VALIDATION :", "PASS" if passed else "FAIL")
    print("Failures               :", len(failures))
    print("Cutover                : NOT PERFORMED")
    print("Automatic fallback     : DISABLED")
    print("=" * 80)

    return 0 if passed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("PRE-CUTOVER VALIDATOR ERROR:", repr(exc))
        sys.exit(2)

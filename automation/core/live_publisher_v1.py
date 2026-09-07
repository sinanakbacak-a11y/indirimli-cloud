import json
import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLATFORM = BASE / "unified_data_platform"

EXPORT_ROOT = PLATFORM / "exports" / "flutter_live"
PUBLISH_ROOT = PLATFORM / "publish_ready" / "flutter_live"
REPORTS = PLATFORM / "reports"

LATEST_EXPORT = EXPORT_ROOT / "latest_live_export.json"
PUBLISH_REPORT = REPORTS / "live_publisher_v1_report.json"


def now():
    return datetime.now().isoformat(timespec="seconds")


def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_rel(path_str):
    return str(path_str).replace("\\", "/")


def fail(code, message, details=None):
    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "status": "BLOCKED",
        "code": code,
        "message": message,
        "details": details,
        "published": False,
    }
    atomic_write_json(PUBLISH_REPORT, report)

    print("=" * 80)
    print("INDIRIMLI SHADOW PUBLISHER V1")
    print("=" * 80)
    print("PUBLISH BLOCKED")
    print("Code   :", code)
    print("Reason :", message)
    if details is not None:
        print("Details:", details)
    print("=" * 80)
    return 1


def validate_manifest(package_dir, manifest):
    problems = []

    if manifest.get("mode") != "UNIFIED_LIVE":
        problems.append("manifest mode UNIFIED_LIVE degil")
    policy = manifest.get("flutterPolicy") or {}

    required_false = [
        "mayWriteFavorites",
        "mayWritePriceAlerts",
        "mayActivateLegacy",
    ]

    if policy.get("shadowOnly") is not False:
        problems.append("shadowOnly false degil")

    if policy.get("mayMutateAppState") is not True:
        problems.append("mayMutateAppState true degil")

    if policy.get("mayCallSetState") is not True:
        problems.append("mayCallSetState true degil")

    for key in required_false:
        if policy.get(key) is not False:
            problems.append(f"{key} false degil")

    validation = manifest.get("validation") or {}

    if validation.get("postCutoverPassed") is not True:
        problems.append("postCutoverPassed true degil")

    if "testBranchesInProduction" not in validation:
        problems.append(
            "testBranchesInProduction validation alani eksik"
        )
    elif int(
        validation.get("testBranchesInProduction") or 0
    ) != 0:
        problems.append(
            "testBranchesInProduction sifir degil"
        )


    if int(
        validation.get("testPricesInProduction") or 0
    ) != 0:
        problems.append(
            "testPricesInProduction sifir degil"
        )

    if int(
        validation.get("unexpectedQuarantine") or 0
    ) != 0:
        problems.append(
            "unexpectedQuarantine sifir degil"
        )

    if int(
        validation.get("productionRelationErrors") or 0
    ) != 0:
        problems.append(
            "productionRelationErrors sifir degil"
        )

    file_entries = []

    files = manifest.get("files") or {}
    for value in files.values():
        if isinstance(value, dict):
            file_entries.append(value)

    for value in manifest.get("productChunks") or []:
        if isinstance(value, dict):
            file_entries.append(value)

    for value in manifest.get("priceChunks") or []:
        if isinstance(value, dict):
            file_entries.append(value)

    for entry in file_entries:
        rel = normalize_rel(entry.get("path") or "")
        expected = str(entry.get("sha256") or "").strip().lower()

        if not rel:
            problems.append("bos file path")
            continue

        path = package_dir / Path(rel)

        if not path.exists():
            problems.append(f"eksik dosya: {rel}")
            continue

        actual = sha256_file(path).lower()

        if actual != expected:
            problems.append(f"checksum uyusmazligi: {rel}")

        expected_bytes = entry.get("bytes")
        if expected_bytes is not None:
            try:
                if path.stat().st_size != int(expected_bytes):
                    problems.append(f"boyut uyusmazligi: {rel}")
            except Exception:
                problems.append(f"boyut kontrol hatasi: {rel}")

    return problems


def main():
    print("=" * 80)
    print("INDIRIMLI SHADOW PUBLISHER V1")
    print("=" * 80)

    if not LATEST_EXPORT.exists():
        return fail(
            "LATEST_EXPORT_MISSING",
            f"latest shadow export bulunamadi: {LATEST_EXPORT}",
        )

    latest = read_json(LATEST_EXPORT)

    package_id = str(latest.get("packageId") or "").strip()
    manifest_rel = str(latest.get("manifestRelativePath") or "").strip()
    expected_manifest_sha = str(latest.get("manifestSha256") or "").strip().lower()

    if not package_id or not manifest_rel or not expected_manifest_sha:
        return fail(
            "LATEST_EXPORT_INVALID",
            "latest_live_export.json eksik alan iceriyor.",
            latest,
        )

    package_dir = EXPORT_ROOT / package_id
    manifest_path = EXPORT_ROOT / Path(manifest_rel)

    if not package_dir.exists():
        return fail(
            "PACKAGE_MISSING",
            f"Shadow package bulunamadi: {package_dir}",
        )

    if not manifest_path.exists():
        return fail(
            "MANIFEST_MISSING",
            f"Manifest bulunamadi: {manifest_path}",
        )

    actual_manifest_sha = sha256_file(manifest_path).lower()

    if actual_manifest_sha != expected_manifest_sha:
        return fail(
            "MANIFEST_CHECKSUM_MISMATCH",
            "Manifest SHA256 latest pointer ile uyusmuyor.",
            {
                "expected": expected_manifest_sha,
                "actual": actual_manifest_sha,
            },
        )

    manifest = read_json(manifest_path)

    if manifest.get("packageId") != package_id:
        return fail(
            "PACKAGE_ID_MISMATCH",
            "Manifest packageId latest pointer ile uyusmuyor.",
            {
                "latest": package_id,
                "manifest": manifest.get("packageId"),
            },
        )

    problems = validate_manifest(package_dir, manifest)

    if problems:
        return fail(
            "PACKAGE_VALIDATION_FAILED",
            "Shadow package dogrulamadan gecemedi.",
            problems[:50],
        )

    target_dir = PUBLISH_ROOT / package_id

    if target_dir.exists():
        shutil.rmtree(target_dir)

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_dir, target_dir)

    # Re-validate after copy.
    copied_manifest = target_dir / "manifest.json"

    if sha256_file(copied_manifest).lower() != actual_manifest_sha:
        shutil.rmtree(target_dir, ignore_errors=True)
        return fail(
            "COPY_VERIFY_FAILED",
            "Publish-ready kopya manifest checksum dogrulamasi basarisiz.",
        )

    latest_public = {
        "schemaVersion": 1,
        "updatedAt": now(),
        "packageId": package_id,
        "manifestPath": f"packages/{package_id}/manifest.json",
        "manifestSha256": actual_manifest_sha,
        "mode": "UNIFIED_LIVE",
        "active": True,
    }

    # Build clean GitHub-ready structure:
    # publish_ready/flutter_live/
    #   latest.json
    #   packages/<packageId>/...
    packages_dir = PUBLISH_ROOT / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    final_package_dir = packages_dir / package_id

    if final_package_dir.exists():
        shutil.rmtree(final_package_dir)

    shutil.move(str(target_dir), str(final_package_dir))

    atomic_write_json(
        PUBLISH_ROOT / "latest.json",
        latest_public,
    )

    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "status": "SUCCESS",
        "published": False,
        "publishReady": True,
        "packageId": package_id,
        "sourcePackage": str(package_dir),
        "publishReadyRoot": str(PUBLISH_ROOT),
        "publishPackage": str(final_package_dir),
        "latestFile": str(PUBLISH_ROOT / "latest.json"),
        "manifestSha256": actual_manifest_sha,
        "validatedFiles": (
            len(manifest.get("files") or {})
            + len(manifest.get("productChunks") or [])
            + len(manifest.get("priceChunks") or [])
        ),
        "note": (
            "Bu script GitHub'a otomatik yukleme yapmaz. "
            "Sadece checksum dogrulanmis publish-ready paketi hazirlar."
        ),
    }

    atomic_write_json(PUBLISH_REPORT, report)

    print("Package ID          :", package_id)
    print("Manifest SHA256     :", actual_manifest_sha)
    print("Publish-ready root  :", PUBLISH_ROOT)
    print("Latest pointer      :", PUBLISH_ROOT / "latest.json")
    print("-" * 80)
    print("PACKAGE VALIDATION  : PASS")
    print("PUBLISH READY       : YES")
    print("GITHUB UPLOAD       : NOT PERFORMED")
    print("SHADOW ONLY         : YES")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as exc:
        print()
        print("SHADOW PUBLISHER ERROR")
        print(repr(exc))
        exit_code = 2

    sys.exit(exit_code)


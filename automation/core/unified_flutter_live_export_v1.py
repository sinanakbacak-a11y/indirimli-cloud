import json
import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLATFORM = BASE / "unified_data_platform"

CONFIG = PLATFORM / "config"
INDEXES = PLATFORM / "indexes"
INPUTS = PLATFORM / "inputs"
REPORTS = PLATFORM / "reports"
EXPORT_ROOT = PLATFORM / "exports" / "flutter_live"

ACTIVE_POINTER = CONFIG / "active_platform.json"
POST_CUTOVER_REPORT = REPORTS / "unified_post_cutover_validator_v1_report.json"

MARKETS_INDEX = INDEXES / "markets_index.json"
BRANCHES_INDEX = INDEXES / "branches_index.json"
CATEGORIES_INDEX = INDEXES / "categories_index.json"
PRODUCTS_INDEX = INDEXES / "products_index.json"
PRICES_INPUT = INPUTS / "prices" / "legacy_prices_import.json"

PRODUCT_CHUNK_SIZE = 1000
PRICE_CHUNK_SIZE = 2000


def now():
    return datetime.now().isoformat(timespec="seconds")


def stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
    temp.replace(path)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows(data, key):
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    return []


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def export_single_json(package_dir, relative_path, key, items):
    path = package_dir / relative_path
    atomic_write_json(
        path,
        {
            "schemaVersion": 1,
            "generatedAt": now(),
            "count": len(items),
            key: items,
        },
    )
    return {
        "path": str(relative_path).replace("\\", "/"),
        "count": len(items),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def export_chunks(package_dir, folder_name, key, items, chunk_size):
    folder = package_dir / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    chunks = []

    for index, chunk in enumerate(chunked(items, chunk_size), start=1):
        filename = f"{folder_name}_{index:04d}.json"
        path = folder / filename

        atomic_write_json(
            path,
            {
                "schemaVersion": 1,
                "generatedAt": now(),
                "chunkIndex": index,
                "count": len(chunk),
                key: chunk,
            },
        )

        chunks.append({
            "path": f"{folder_name}/{filename}",
            "count": len(chunk),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        })

    return chunks


def fail(message):
    print("=" * 80)
    print("INDIRIMLI UNIFIED FLUTTER EXPORT V1")
    print("=" * 80)
    print("EXPORT BLOCKED")
    print(message)
    print("=" * 80)
    return 1


def main():
    print("=" * 80)
    print("INDIRIMLI UNIFIED FLUTTER EXPORT V1")
    print("=" * 80)

    required = [
        ACTIVE_POINTER,
        POST_CUTOVER_REPORT,
        MARKETS_INDEX,
        BRANCHES_INDEX,
        CATEGORIES_INDEX,
        PRODUCTS_INDEX,
        PRICES_INPUT,
    ]

    for path in required:
        if not path.exists():
            return fail(f"Required file missing: {path}")

    pointer = read_json(ACTIVE_POINTER)
    post = read_json(POST_CUTOVER_REPORT)

    # Hard gates: export only from validated unified platform.
    if pointer.get("activePlatform") != "unified_v1":
        return fail(
            f"activePlatform must be unified_v1, found: "
            f"{pointer.get('activePlatform')}"
        )

    if pointer.get("automaticFallback") is not False:
        return fail("automaticFallback must be false")

    if pointer.get("legacyReadAllowed") is not False:
        return fail("legacyReadAllowed must be false")

    if post.get("passed") is not True:
        return fail("post-cutover validation is not PASS")

    post_counts = post.get("counts") or {}

    if int(
        post_counts.get("testPricesInProduction") or 0
    ) != 0:
        return fail(
            "testPricesInProduction must be 0"
        )

    if int(
        post_counts.get("unexpectedQuarantine") or 0
    ) != 0:
        return fail(
            "unexpectedQuarantine must be 0"
        )

    if int(
        post_counts.get("productionRelationErrors") or 0
    ) != 0:
        return fail(
            "productionRelationErrors must be 0"
        )

    markets = rows(read_json(MARKETS_INDEX), "markets")
    branches = rows(read_json(BRANCHES_INDEX), "branches")
    categories = rows(read_json(CATEGORIES_INDEX), "categories")
    products = rows(read_json(PRODUCTS_INDEX), "products")
    prices = rows(read_json(PRICES_INPUT), "prices")

    package_id = f"unified_v1_{stamp()}"
    package_dir = EXPORT_ROOT / package_id
    package_dir.mkdir(parents=True, exist_ok=False)

    try:
        files = {}

        files["markets"] = export_single_json(
            package_dir,
            Path("masters") / "markets.json",
            "markets",
            markets,
        )

        files["branches"] = export_single_json(
            package_dir,
            Path("masters") / "branches.json",
            "branches",
            branches,
        )

        files["categories"] = export_single_json(
            package_dir,
            Path("masters") / "categories.json",
            "categories",
            categories,
        )

        product_chunks = export_chunks(
            package_dir,
            "products",
            "products",
            products,
            PRODUCT_CHUNK_SIZE,
        )

        price_chunks = export_chunks(
            package_dir,
            "prices",
            "prices",
            prices,
            PRICE_CHUNK_SIZE,
        )

        manifest = {
            "schemaVersion": 1,
            "exportVersion": 1,
            "packageId": package_id,
            "generatedAt": now(),
            "mode": "UNIFIED_LIVE",
            "platform": {
                "activePlatform": pointer.get("activePlatform"),
                "previousPlatform": pointer.get("previousPlatform"),
                "automaticFallback": pointer.get("automaticFallback"),
                "legacyReadAllowed": pointer.get("legacyReadAllowed"),
            },
                      "validation": {
                "postCutoverPassed": post.get("passed"),
                "testBranchesInProduction":
                    post_counts.get("testBranchesInProduction"),
                "testPricesInProduction":
                    post_counts.get("testPricesInProduction"),
                "unexpectedQuarantine":
                    post_counts.get("unexpectedQuarantine"),
                "productionRelationErrors":
                    post_counts.get("productionRelationErrors"),
            },
            "counts": {
                "markets": len(markets),
                "branches": len(branches),
                "categories": len(categories),
                "products": len(products),
                "prices": len(prices),
            },
            "chunking": {
                "productChunkSize": PRODUCT_CHUNK_SIZE,
                "priceChunkSize": PRICE_CHUNK_SIZE,
                "productChunkCount": len(product_chunks),
                "priceChunkCount": len(price_chunks),
            },
            "files": files,
            "productChunks": product_chunks,
            "priceChunks": price_chunks,
            "flutterPolicy": {
                "shadowOnly": False,
                "mayMutateAppState": True,
                "mayCallSetState": True,
                "mayWriteFavorites": False,
                "mayWritePriceAlerts": False,
                "mayActivateLegacy": False,
            },
        }

        manifest_path = package_dir / "manifest.json"
        atomic_write_json(manifest_path, manifest)

        # Package-wide manifest checksum written separately so manifest
        # does not checksum itself recursively.
        checksum_path = package_dir / "manifest.sha256"
        checksum_path.write_text(
            sha256_file(manifest_path) + "\n",
            encoding="utf-8",
        )

        latest_pointer = {
            "schemaVersion": 1,
            "updatedAt": now(),
            "packageId": package_id,
            "manifestRelativePath": f"{package_id}/manifest.json",
            "manifestSha256": sha256_file(manifest_path),
            "mode": "UNIFIED_LIVE",
        }
        atomic_write_json(
            EXPORT_ROOT / "latest_live_export.json",
            latest_pointer,
        )

        report = {
            "schemaVersion": 1,
            "generatedAt": now(),
            "status": "SUCCESS",
            "packageId": package_id,
            "packageDir": str(package_dir),
            "manifest": str(manifest_path),
            "counts": manifest["counts"],
            "chunking": manifest["chunking"],
            "shadowPolicy": manifest["flutterPolicy"],
        }
        atomic_write_json(
            REPORTS / "unified_flutter_live_export_v1_report.json",
            report,
        )

    except Exception:
        # Never leave a half-built package visible as a valid export.
        shutil.rmtree(package_dir, ignore_errors=True)
        raise

    print("Package ID          :", package_id)
    print("Markets             :", len(markets))
    print("Branches            :", len(branches))
    print("Categories          :", len(categories))
    print("Products            :", len(products))
    print("Prices              :", len(prices))
    print("Product chunks      :", len(product_chunks))
    print("Price chunks        :", len(price_chunks))
    print("Manifest SHA256     :", sha256_file(manifest_path))
    print("-" * 80)
    print("SHADOW EXPORT       : SUCCESS")
    print("APP STATE MUTATION  : DISABLED")
    print("LEGACY ACTIVATION   : DISABLED")
    print("FLUTTER CUTOVER     : NOT PERFORMED")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as exc:
        print()
        print("UNIFIED FLUTTER EXPORT ERROR")
        print(repr(exc))
        exit_code = 2

    sys.exit(exit_code)


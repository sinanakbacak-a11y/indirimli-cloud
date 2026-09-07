import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parents[2]

BULK_ROOT = BASE / "bulk_official"
MANIFEST_FILE = BULK_ROOT / "bulk_manifest.json"
INPUT_DIR = BULK_ROOT / "inputs"
REPORT_DIR = BULK_ROOT / "reports"
QUARANTINE_DIR = BULK_ROOT / "quarantine"


PERMISSION_REGISTRY_FILE = (
    BULK_ROOT
    / "source_permission_registry.json"
)
OUTPUT_DIR = BULK_ROOT / "outputs"

CATEGORY_PACKS = BASE / "category_packs"

PRODUCTION_PRICE_FILE = (
    BASE
    / "gercek_pilot"
    / "cloud_export"
    / "production_fiyatlar.json"
)

PRICE_HISTORY_FILE = (
    BASE
    / "unified_data_platform"
    / "history"
    / "price_history.json"
)

MASTER_MARKET_FILE = (
    BASE
    / "unified_data_platform"
    / "inputs"
    / "markets"
    / "cloud_market_master.json"
)

MASTER_BRANCH_FILE = (
    BASE
    / "unified_data_platform"
    / "inputs"
    / "branches"
    / "cloud_branch_master.json"
)

CATEGORY_INDEX_FILE = (
    BASE
    / "unified_data_platform"
    / "indexes"
    / "categories_index.json"
)

# ============================================================
# BASIC HELPERS
# ============================================================

def now():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return datetime.now().date().isoformat()


def read_json(path):
    with Path(path).open(
        "r",
        encoding="utf-8-sig",
    ) as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def backup_file(path):
    path = Path(path)

    if not path.exists():
        return ""

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        BULK_ROOT
        / "backups"
        / stamp
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup = backup_dir / path.name

    shutil.copy2(
        path,
        backup,
    )

    return str(backup)


def normalize_text(value):
    value = str(
        value or ""
    ).strip().casefold()

    table = str.maketrans({
        "Ä±": "i",
        "ÄŸ": "g",
        "Ã¼": "u",
        "ÅŸ": "s",
        "Ã¶": "o",
        "Ã§": "c",
        "Ä°": "i",
        "Ä": "g",
        "Ãœ": "u",
        "Å": "s",
        "Ã–": "o",
        "Ã‡": "c",
    })

    value = value.translate(table)

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    )

    return value.strip("_")


def extract_weight(name):
    text = str(
        name or ""
    )

    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return "", ""

    amount = (
        match.group(1)
        .replace(",", ".")
    )

    unit = (
        match.group(2)
        .lower()
    )

    return amount, unit


def make_master_id(name, brand):
    clean_name = normalize_text(name)
    clean_brand = normalize_text(brand)

    if (
        clean_brand
        and clean_name.startswith(
            clean_brand + "_"
        )
    ):
        clean_name = clean_name[
            len(clean_brand) + 1:
        ]

    return clean_name
def discover_platform_contract():
    contract = {
        "markets": {},
        "branches": {},
        "categories": {},
    }

    # MARKET DISCOVERY
    if MASTER_MARKET_FILE.exists():
        market_data = read_json(
            MASTER_MARKET_FILE
        )

        for row in market_data.get(
            "markets",
            [],
        ):
            if not isinstance(
                row,
                dict,
            ):
                continue

            market_id = str(
                row.get("marketId")
                or ""
            ).strip()

            if not market_id:
                continue

            contract["markets"][
                market_id
            ] = row

    # BRANCH DISCOVERY
    if MASTER_BRANCH_FILE.exists():
        branch_data = read_json(
            MASTER_BRANCH_FILE
        )

        for row in branch_data.get(
            "branches",
            [],
        ):
            if not isinstance(
                row,
                dict,
            ):
                continue

            branch_id = str(
                row.get("subeId")
                or ""
            ).strip()

            if not branch_id:
                continue

            contract["branches"][
                branch_id
            ] = row

    # CATEGORY DISCOVERY
    if CATEGORY_INDEX_FILE.exists():
        category_data = read_json(
            CATEGORY_INDEX_FILE
        )

        for row in category_data.get(
            "categories",
            [],
        ):
            if not isinstance(
                row,
                dict,
            ):
                continue

            category_id = str(
                row.get("kategoriId")
                or ""
            ).strip()

            if not category_id:
                continue

            contract["categories"][
                category_id
            ] = row

    return contract


def load_permission_registry():
    if not PERMISSION_REGISTRY_FILE.exists():
        return {
            "defaultPolicy": "deny_unless_approved",
            "markets": {},
        }

    data = read_json(
        PERMISSION_REGISTRY_FILE
    )

    markets = {}

    for row in data.get(
        "markets",
        [],
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        market_id = str(
            row.get("marketId")
            or ""
        ).strip()

        if not market_id:
            continue

        markets[
            market_id
        ] = row

    return {
        "defaultPolicy":
            data.get(
                "defaultPolicy",
                "deny_unless_approved",
            ),
        "markets":
            markets,
    }


def permission_allowed(
    permission_registry,
    market_id,
    module_name,
):
    market = (
        permission_registry
        .get("markets", {})
        .get(market_id)
    )

    if market is None:
        return False

    permissions = market.get(
        "permissions",
        {}
    )

    rule = permissions.get(
        module_name,
        {}
    )

    return (
        rule.get("allowed") is True
        and str(
            rule.get("status")
            or ""
        ).strip().lower()
        == "approved"
    )


def branch_matches_market(
    branch_id,
    market_id,
    contract,
):
    branch = contract[
        "branches"
    ].get(branch_id)

    if branch is None:
        return False

    return (
        str(
            branch.get("marketId")
            or ""
        ).strip()
        == market_id
    )


def is_branch_production_ready(
    branch_id,
    contract,
):
    branch = contract[
        "branches"
    ].get(branch_id)

    if branch is None:
        return False

    status = str(
        branch.get("status")
        or ""
    ).strip().lower()

    data_status = str(
        branch.get("veriDurumu")
        or ""
    ).strip().lower()

    return (
        status in {
            "active",
            "production",
            "production_ready",
        }
        and data_status not in {
            "test",
            "otomatik_test",
        }
    )

def load_permission_registry():
    if not PERMISSION_REGISTRY_FILE.exists():
        return {
            "defaultPolicy": "deny_unless_approved",
            "markets": {},
        }

    data = read_json(
        PERMISSION_REGISTRY_FILE
    )

    markets = {}

    for row in data.get(
        "markets",
        [],
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        market_id = str(
            row.get("marketId")
            or ""
        ).strip()

        if not market_id:
            continue

        markets[
            market_id
        ] = row

    return {
        "defaultPolicy":
            data.get(
                "defaultPolicy",
                "deny_unless_approved",
            ),
        "markets":
            markets,
    }


def permission_allowed(
    permission_registry,
    market_id,
    module_name,
):
    market = (
        permission_registry
        .get("markets", {})
        .get(market_id)
    )

    if market is None:
        return False

    permissions = market.get(
        "permissions",
        {}
    )

    rule = permissions.get(
        module_name,
        {}
    )

    return (
        rule.get("allowed") is True
        and str(
            rule.get("status")
            or ""
        ).strip().lower()
        == "approved"
    )
# ============================================================
# INPUT EXTRACTION
# ============================================================

def get_list(data, keys):
    if not isinstance(
        data,
        dict,
    ):
        return []

    for key in keys:
        value = data.get(key)

        if isinstance(
            value,
            list,
        ):
            return value

    return []


def load_bulk_inputs():
    INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = []

    for path in sorted(
        INPUT_DIR.glob("*.json")
    ):
        try:
            data = read_json(path)

            result.append({
                "path": path,
                "data": data,
            })

        except Exception as exc:
            result.append({
                "path": path,
                "error": repr(exc),
            })

    return result


# ============================================================
# CATEGORY PACK MANAGEMENT
# ============================================================

def load_category_pack(category_id):
    path = (
        CATEGORY_PACKS
        / f"{category_id}.json"
    )

    if path.exists():
        data = read_json(path)

        if not isinstance(
            data.get("urunler"),
            list,
        ):
            data["urunler"] = []

        return path, data

    data = {
        "version": 1,
        "sonGuncelleme": today(),
        "kategoriId": category_id,
        "kategoriAdi": category_id,
        "toplamUrun": 0,
        "urunler": [],
    }

    return path, data


def build_existing_product_indexes():
    by_id = {}
    by_exact = {}

    if not CATEGORY_PACKS.exists():
        return by_id, by_exact

    for path in CATEGORY_PACKS.glob(
        "*.json"
    ):
        try:
            data = read_json(path)
        except Exception:
            continue

        rows = data.get(
            "urunler",
            [],
        )

        if not isinstance(
            rows,
            list,
        ):
            continue

        for row in rows:
            if not isinstance(
                row,
                dict,
            ):
                continue

            product_id = str(
                row.get("id")
                or ""
            ).strip()

            if product_id:
                by_id[
                    product_id
                ] = row

            key = (
                str(
                    row.get("marketId")
                    or ""
                ).strip(),

                normalize_text(
                    row.get("marka")
                ),

                normalize_text(
                    row.get("ad")
                ),

                str(
                    row.get("kategoriId")
                    or ""
                ).strip(),
            )

            by_exact.setdefault(
                key,
                [],
            ).append(row)

    return by_id, by_exact


# ============================================================
# PRICE MANAGEMENT
# ============================================================

def load_production_prices():
    if PRODUCTION_PRICE_FILE.exists():
        data = read_json(
            PRODUCTION_PRICE_FILE
        )
    else:
        data = {
            "version": 1,
            "sonGuncelleme": today(),
            "veriTipi":
                "panel_dogrulanmis_fiyatlar",
            "toplamFiyatKaydi": 0,
            "fiyatlar": [],
        }

    if not isinstance(
        data.get("fiyatlar"),
        list,
    ):
        data["fiyatlar"] = []

    return data


# ============================================================
# SAFETY
# ============================================================

def is_verified(row):
    value = str(
        row.get(
            "dogrulamaDurumu"
        )
        or ""
    ).strip().lower()

    return value in {
        "dogrulandi",
        "verified",
        "production_verified",
    }


def is_active(row):
    return (
        row.get("aktif")
        is True
    )


def is_test_record(row):
    source = str(
        row.get("kaynak")
        or row.get("source")
        or ""
    ).strip().lower()

    status = str(
        row.get("veriDurumu")
        or ""
    ).strip().lower()

    return (
        status
        in {
            "otomatik_test",
            "test",
        }
        or "generator" in source
        or "automatic_test" in source
    )


def has_official_source(
    row,
    parent_data,
):
    source = str(
        row.get("kaynak")
        or row.get("source")
        or parent_data.get("source")
        or ""
    ).strip().lower()

    url = str(
        row.get("kaynakUrl")
        or row.get("sourceUrl")
        or ""
    ).strip()

    official_markers = (
        "official",
        "resmi",
        "resmÃ®",
    )

    source_ok = any(
        marker in source
        for marker
        in official_markers
    )

    return (
        source_ok
        and bool(url)
    )


# ============================================================
# PRODUCT RESOLVER
# ============================================================

def resolve_existing_product(
    row,
    by_id,
    by_exact,
):
    requested_id = str(
        row.get("productId")
        or row.get("id")
        or ""
    ).strip()

    if requested_id:
        existing = by_id.get(
            requested_id
        )

        if existing:
            return (
                existing,
                "exact_product_id",
            )

    market_id = str(
        row.get("marketId")
        or ""
    ).strip()

    category_id = str(
        row.get("kategoriId")
        or ""
    ).strip()

    name = normalize_text(
        row.get("urunAdi")
        or row.get("ad")
    )

    brand = normalize_text(
        row.get("marka")
    )

    key = (
        market_id,
        brand,
        name,
        category_id,
    )

    matches = by_exact.get(
        key,
        [],
    )

    if len(matches) == 1:
        return (
            matches[0],
            "exact_market_brand_name_category",
        )

    return (
        None,
        "not_resolved",
    )


# ============================================================
# NEW PRODUCT CREATION
# ============================================================

def create_product(
    row,
    category_id,
):
    market_id = str(
        row.get("marketId")
        or ""
    ).strip()

    market_name = str(
        row.get("market")
        or market_id.upper()
    ).strip()

    branch_id = str(
        row.get("subeId")
        or ""
    ).strip()

    name = str(
        row.get("urunAdi")
        or row.get("ad")
        or ""
    ).strip()

    brand = str(
        row.get("marka")
        or ""
    ).strip()

    master_id = str(
        row.get("masterProductId")
        or ""
    ).strip()

    if not master_id:
        master_id = make_master_id(
            name,
            brand,
        )

    product_id = str(
        row.get("productId")
        or row.get("id")
        or ""
    ).strip()

    if not product_id:
        product_id = (
            f"{market_id}_"
            f"{normalize_text(brand)}_"
            f"{master_id}"
        )

    gramaj, birim = extract_weight(
        name
    )

    return {
        "id": product_id,
        "masterProductId": master_id,
        "karsilastirmaId": master_id,
        "karsilastirmaAnahtari":
            master_id,

        "ad": name,

        "urunGrubu":
            str(
                row.get("urunGrubu")
                or name
            ).strip(),

        "market": market_name,
        "marketId": market_id,
        "subeId": branch_id,

        "kategori":
            str(
                row.get("kategori")
                or category_id
            ).strip(),

        "kategoriId":
            category_id,

        # PRICE AYRI LAYER'DA
        "fiyat": 0,
        "eskiFiyat": 0,

        "mesafe": 0,

        "indirimli":
            row.get("indirimli")
            is True,

        "stok":
            row.get("stok")
            is not False,

        "resim":
            str(
                row.get("resim")
                or ""
            ).strip(),

        "imageUrl":
            str(
                row.get("imageUrl")
                or row.get("gorselUrl")
                or ""
            ).strip(),

        "kampanya":
            str(
                row.get("kampanya")
                or ""
            ).strip(),

        "sonGuncelleme":
            str(
                row.get(
                    "sonGuncelleme"
                )
                or today()
            ).strip(),

        "barkod":
            str(
                row.get("barkod")
                or ""
            ).strip(),

        "gramaj":
            str(
                row.get("gramaj")
                or gramaj
            ).strip(),

        "birim":
            str(
                row.get("birim")
                or birim
            ).strip(),

        "marka": brand,

        "fiyatBaslangic":
            str(
                row.get(
                    "fiyatBaslangic"
                )
                or ""
            ).strip(),

        "fiyatBitis":
            str(
                row.get(
                    "fiyatBitis"
                )
                or ""
            ).strip(),

        "kaynak":
            str(
                row.get("kaynak")
                or "resmi_market_sitesi"
            ).strip(),

        "kaynakUrl":
            str(
                row.get("kaynakUrl")
                or ""
            ).strip(),

        "veriDurumu":
            "production_verified",

        "fiyatTipi":
            "official_verified",

        # FUTURE INTEGRATION
        "catalogId":
            str(
                row.get("catalogId")
                or ""
            ).strip(),

        "imageStatus":
            (
                "available"
                if (
                    row.get("imageUrl")
                    or row.get("gorselUrl")
                )
                else "missing"
            ),
    }


# ============================================================
# PRICE CREATION
# ============================================================

def create_price(
    row,
    product,
):
    try:
        price_value = float(
            row.get("fiyat")
        )
    except Exception:
        price_value = 0

    master_id = str(
        product.get(
            "masterProductId"
        )
        or ""
    ).strip()

    market_id = str(
        product.get("marketId")
        or ""
    ).strip()

    branch_id = str(
        row.get("subeId")
        or product.get("subeId")
        or ""
    ).strip()

    return {
        "sira": 0,

        "fiyatId":
            f"{market_id}_"
            f"{branch_id}_"
            f"{master_id}",

        "masterProductId":
            master_id,

        "urunAdi":
            product.get("ad")
            or "",

        "marka":
            product.get("marka")
            or "",

        "kategori":
            product.get("kategori")
            or "",

        "birim":
            product.get("birim")
            or "",

        "marketId":
            market_id,

        "market":
            product.get("market")
            or "",

        "subeId":
            branch_id,

        "fiyat":
            price_value,

        "eskiFiyat":
            float(
                row.get(
                    "eskiFiyat"
                )
                or 0
            ),

        "indirimli":
            row.get("indirimli")
            is True,

        "stok":
            row.get("stok")
            is not False,

        "fiyatBaslangic":
            str(
                row.get(
                    "fiyatBaslangic"
                )
                or today()
            ).strip(),

        "fiyatBitis":
            str(
                row.get(
                    "fiyatBitis"
                )
                or ""
            ).strip(),

        "sonGuncelleme":
            str(
                row.get(
                    "sonGuncelleme"
                )
                or today()
            ).strip(),

        "kaynak":
            str(
                row.get("kaynak")
                or "resmi_market_sitesi"
            ).strip(),

        "kaynakUrl":
            str(
                row.get("kaynakUrl")
                or ""
            ).strip(),

        "kaynakNotu":
            "Bulk Official Intake V1",

        "dogrulamaDurumu":
            "dogrulandi",

        "aktif":
            True,

        "priceResolver":
            "bulk_official_intake_v1",
    }


# ============================================================
# FUTURE MODULE STAGING
# ============================================================

def stage_optional_module(
    module_name,
    rows,
):
    if not rows:
        return

    output = (
        OUTPUT_DIR
        / f"{module_name}.json"
    )

    current = []

    if output.exists():
        try:
            data = read_json(output)

            current = data.get(
                module_name,
                [],
            )

        except Exception:
            current = []

    current.extend(rows)

    write_json(
        output,
        {
            "schemaVersion": 1,
            "updatedAt": now(),
            module_name: current,
        },
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 80)
    print(
        "INDIRIMLI BULK OFFICIAL INTAKE V1"
    )
    print("=" * 80)

    BULK_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    QUARANTINE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    if not MANIFEST_FILE.exists():
        print(
            "ERROR: bulk_manifest.json yok."
        )
        return 2

    manifest = read_json(
        MANIFEST_FILE
    )

    permission_registry = (
        load_permission_registry()
    )

    contract = discover_platform_contract()

    discovered_markets = set(
        contract["markets"].keys()
    )

    discovered_categories = set(
        contract["categories"].keys()
    )

    manifest_markets = set(
        manifest.get(
            "markets",
            [],
        )
    )

    manifest_categories = set(
        manifest.get(
            "categories",
            [],
        )
    )

    allowed_markets = (
        discovered_markets
        if discovered_markets
        else manifest_markets
    )

    allowed_categories = (
        discovered_categories
        if discovered_categories
        else manifest_categories
    )

    print(
        "Discovered markets   :",
        len(discovered_markets),
    )

    print(
        "Discovered branches  :",
        len(contract["branches"]),
    )

    print(
        "Discovered categories:",
        len(discovered_categories),
    )

    print(
        "Allowed markets      :",
        len(allowed_markets),
    )

    print(
        "Allowed categories   :",
        len(allowed_categories),
    )

    modules = manifest.get(
        "modules",
        {},
    )

    safety = manifest.get(
        "safety",
        {},
    )

    inputs = load_bulk_inputs()

    print(
        "Input JSON sayisi :",
        len(inputs),
    )

    by_id, by_exact = (
        build_existing_product_indexes()
    )

    price_data = (
        load_production_prices()
    )

    prices = price_data[
        "fiyatlar"
    ]

    existing_price_keys = {
        (
            str(
                row.get(
                    "masterProductId"
                )
                or ""
            ).strip(),

            str(
                row.get("marketId")
                or ""
            ).strip(),

            str(
                row.get("subeId")
                or ""
            ).strip(),
        )
        for row in prices
        if isinstance(row, dict)
    }

    existing_price_map = {
        (
            str(
                row.get("masterProductId")
                or ""
            ).strip(),

            str(
                row.get("marketId")
                or ""
            ).strip(),

            str(
                row.get("subeId")
                or ""
            ).strip(),
        ): row
        for row in prices
        if isinstance(row, dict)
    }
    if PRICE_HISTORY_FILE.exists():
        history_data = read_json(
            PRICE_HISTORY_FILE
        )

        price_history = history_data.get(
            "history",
            [],
        )

        if not isinstance(
            price_history,
            list,
        ):
            price_history = []

    else:
        price_history = []

    category_cache = {}
    category_backups = {}

    price_backup = backup_file(
        PRODUCTION_PRICE_FILE
    )

    quarantine = []
    stats = {
        "rawRecords": 0,
        "existingProductsMatched": 0,
        "newProductsCreated": 0,
        "newVerifiedPrices": 0,
        "updatedPrices": 0,
        "unchangedPrices": 0,
        "priceHistoryAdded": 0,
        "duplicatePrices": 0,
        "rejected": 0,
        "imagesStaged": 0,
        "catalogsStaged": 0,
        "branchesStaged": 0,
    }

    staged_images = []
    staged_catalogs = []
    staged_branches = []

    for source in inputs:
        path = source["path"]

        if "error" in source:
            quarantine.append({
                "type":
                    "input_read_error",
                "file":
                    str(path),
                "error":
                    source["error"],
            })

            stats["rejected"] += 1
            continue

        data = source["data"]

        # ----------------------------------------------------
        # PRODUCT / PRICE INPUTS
        # ----------------------------------------------------

        product_rows = get_list(
            data,
            (
                "records",
                "fiyatlar",
                "products",
                "urunler",
            ),
        )

        for row in product_rows:
            if not isinstance(
                row,
                dict,
            ):
                continue

            stats[
                "rawRecords"
            ] += 1

            market_id = str(
                row.get("marketId")
                or data.get("marketId")
                or ""
            ).strip()

            category_id = str(
                row.get("kategoriId")
                or data.get("kategoriId")
                or ""
            ).strip()

            # inherit root source
            if not row.get(
                "kaynak"
            ):
                row["kaynak"] = (
                    data.get("source")
                    or ""
                )

            if (
                market_id
                not in allowed_markets
            ):
                quarantine.append({
                    "type":
                        "market_not_allowed",
                    "file":
                        str(path),
                    "row":
                        row,
                })

                stats["rejected"] += 1
                continue
            if (
                category_id
                not in allowed_categories
            ):
                quarantine.append({
                    "type":
                        "category_not_allowed",
                    "file":
                        str(path),
                    "row":
                        row,
                })

                stats["rejected"] += 1
                continue

            if not permission_allowed(
                permission_registry,
                market_id,
                "prices",
            ):
                quarantine.append({
                    "type": "price_permission_denied",
                    "file": str(path),
                    "marketId": market_id,
                    "row": row,
                })

                stats["rejected"] += 1
                continue

            branch_id = str(
                row.get("subeId")
                or ""
            ).strip()

            if branch_id:
                if not branch_matches_market(
                    branch_id,
                    market_id,
                    contract,
                ):
                    quarantine.append({
                        "type": "branch_market_mismatch",
                        "file": str(path),
                        "marketId": market_id,
                        "subeId": branch_id,
                        "row": row,
                    })

                    stats["rejected"] += 1
                    continue
        
            row["marketId"] = (
                market_id
            )

            row["kategoriId"] = (
                category_id
            )

            if (
                safety.get(
                    "rejectAutomaticTestPrices",
                    True,
                )
                and is_test_record(row)
            ):
                quarantine.append({
                    "type":
                        "automatic_test_rejected",
                    "file":
                        str(path),
                    "row":
                        row,
                })

                stats["rejected"] += 1
                continue

            if (
                modules
                .get(
                    "prices",
                    {},
                )
                .get(
                    "verifiedOnly",
                    True,
                )
                and not is_verified(row)
            ):
                quarantine.append({
                    "type":
                        "not_verified",
                    "file":
                        str(path),
                    "row":
                        row,
                })

                stats["rejected"] += 1
                continue

            if not is_active(row):
                quarantine.append({
                    "type":
                        "not_active",
                    "file":
                        str(path),
                    "row":
                        row,
                })

                stats["rejected"] += 1
                continue

            if (
                safety.get(
                    "requireOfficialSourceForProduction",
                    True,
                )
                and not has_official_source(
                    row,
                    data,
                )
            ):
                quarantine.append({
                    "type":
                        "official_source_required",
                    "file":
                        str(path),
                    "row":
                        row,
                })

                stats["rejected"] += 1
                continue

            try:
                price_value = float(
                    row.get("fiyat")
                    or 0
                )
            except Exception:
                price_value = 0

            if price_value <= 0:
                quarantine.append({
                    "type":
                        "invalid_price",
                    "file":
                        str(path),
                    "row":
                        row,
                })

                stats["rejected"] += 1
                continue

            product, method = (
                resolve_existing_product(
                    row,
                    by_id,
                    by_exact,
                )
            )

            if product is not None:
                stats[
                    "existingProductsMatched"
                ] += 1

            else:
                create_missing = (
                    modules
                    .get(
                        "products",
                        {},
                    )
                    .get(
                        "createMissingProducts",
                        True,
                    )
                )

                if not create_missing:
                    quarantine.append({
                        "type":
                            "product_not_resolved",
                        "file":
                            str(path),
                        "row":
                            row,
                    })

                    stats["rejected"] += 1
                    continue

                product = create_product(
                    row,
                    category_id,
                )

                product_id = (
                    product["id"]
                )

                if product_id in by_id:
                    product = by_id[
                        product_id
                    ]

                else:
                    if (
                        category_id
                        not in category_cache
                    ):
                        cat_path, cat_data = (
                            load_category_pack(
                                category_id
                            )
                        )

                        category_cache[
                            category_id
                        ] = (
                            cat_path,
                            cat_data,
                        )

                        if cat_path.exists():
                            category_backups[
                                category_id
                            ] = backup_file(
                                cat_path
                            )

                    _, cat_data = (
                        category_cache[
                            category_id
                        ]
                    )

                    cat_data[
                        "urunler"
                    ].append(
                        product
                    )

                    by_id[
                        product_id
                    ] = product

                    exact_key = (
                        product[
                            "marketId"
                        ],

                        normalize_text(
                            product[
                                "marka"
                            ]
                        ),

                        normalize_text(
                            product[
                                "ad"
                            ]
                        ),

                        product[
                            "kategoriId"
                        ],
                    )

                    by_exact.setdefault(
                        exact_key,
                        [],
                    ).append(
                        product
                    )

                    stats[
                        "newProductsCreated"
                    ] += 1

            price_row = (
                create_price(
                    row,
                    product,
                )
            )

            price_key = (
                price_row[
                    "masterProductId"
                ],
                price_row[
                    "marketId"
                ],
                price_row[
                    "subeId"
                ],
            )

            if (
                price_key
                in existing_price_keys
            ):
                existing_price = (
                    existing_price_map[
                        price_key
                    ]
                )

                try:
                    old_price = float(
                        existing_price.get(
                            "fiyat"
                        )
                        or 0
                    )
                except Exception:
                    old_price = 0

                try:
                    new_price = float(
                        price_row.get(
                            "fiyat"
                        )
                        or 0
                    )
                except Exception:
                    new_price = 0

                if old_price == new_price:
                    stats[
                        "unchangedPrices"
                    ] += 1

                    continue

                price_history.append({
                    "masterProductId":
                        existing_price.get(
                            "masterProductId"
                        )
                        or "",

                    "marketId":
                        existing_price.get(
                            "marketId"
                        )
                        or "",

                    "subeId":
                        existing_price.get(
                            "subeId"
                        )
                        or "",

                    "urunAdi":
                        existing_price.get(
                            "urunAdi"
                        )
                        or "",

                    "eskiFiyat":
                        old_price,

                    "yeniFiyat":
                        new_price,

                    "degisimTarihi":
                        today(),

                    "kaynak":
                        price_row.get(
                            "kaynak"
                        )
                        or "",

                    "kaynakUrl":
                        price_row.get(
                            "kaynakUrl"
                        )
                        or "",

                    "historySource":
                        "bulk_official_intake_v1",
                })

                existing_price.update(
                    price_row
                )

                stats[
                    "updatedPrices"
                ] += 1

                stats[
                    "priceHistoryAdded"
                ] += 1

                continue

            prices.append(
                price_row
            )

            existing_price_keys.add(
                price_key
            )

            existing_price_map[
                price_key
            ] = price_row

            stats[
                "newVerifiedPrices"
            ] += 1

        # ----------------------------------------------------
        # IMAGES
        # ----------------------------------------------------

        images = get_list(
            data,
            (
                "images",
                "gorseller",
            ),
        )
        allowed_images = []

        for image_row in images:
            if not isinstance(
                image_row,
                dict,
            ):
                continue

            image_market_id = str(
                image_row.get("marketId")
                or data.get("marketId")
                or ""
            ).strip()

            if permission_allowed(
                permission_registry,
                image_market_id,
                "images",
            ):
                allowed_images.append(
                    image_row
                )

            else:
                quarantine.append({
                    "type":
                        "image_permission_denied",
                    "file":
                        str(path),
                    "marketId":
                        image_market_id,
                    "row":
                        image_row,
                })

        staged_images.extend(
            allowed_images
        )

        stats[
            "imagesStaged"
        ] += len(
            allowed_images
        )

        # ----------------------------------------------------
        # CATALOGS
        # ----------------------------------------------------

        catalogs = get_list(
            data,
            (
                "catalogs",
                "kataloglar",
                "aktueller",
            ),
        )

        allowed_catalogs = []

        for catalog_row in catalogs:
            if not isinstance(
                catalog_row,
                dict,
            ):
                continue

            catalog_market_id = str(
                catalog_row.get("marketId")
                or data.get("marketId")
                or ""
            ).strip()

            if permission_allowed(
                permission_registry,
                catalog_market_id,
                "catalogs",
            ):
                allowed_catalogs.append(
                    catalog_row
                )

            else:
                quarantine.append({
                    "type":
                        "catalog_permission_denied",
                    "file":
                        str(path),
                    "marketId":
                        catalog_market_id,
                    "row":
                        catalog_row,
                })

        staged_catalogs.extend(
            allowed_catalogs
        )

        stats[
            "catalogsStaged"
        ] += len(
            allowed_catalogs
        )

        # ----------------------------------------------------
        # BRANCHES
        # ----------------------------------------------------

        branches = get_list(
            data,
            (
                "branches",
                "subeler",
            ),
        )

        allowed_branches = []

        for branch_row in branches:
            if not isinstance(
                branch_row,
                dict,
            ):
                continue

            branch_market_id = str(
                branch_row.get("marketId")
                or data.get("marketId")
                or ""
            ).strip()

            if permission_allowed(
                permission_registry,
                branch_market_id,
                "branches",
            ):
                allowed_branches.append(
                    branch_row
                )

            else:
                quarantine.append({
                    "type":
                        "branch_permission_denied",
                    "file":
                        str(path),
                    "marketId":
                        branch_market_id,
                    "row":
                        branch_row,
                })

        staged_branches.extend(
            allowed_branches
        )

        stats[
            "branchesStaged"
        ] += len(
            allowed_branches
        )

    # ========================================================
    # SAVE CATEGORY PACKS
    # ========================================================

    for (
        category_id,
        (
            path,
            data,
        ),
    ) in category_cache.items():

        rows = data.get(
            "urunler",
            [],
        )

        data[
            "toplamUrun"
        ] = len(rows)

        data[
            "sonGuncelleme"
        ] = today()

        write_json(
            path,
            data,
        )

    # ========================================================
    # SAVE PRICES
    # ========================================================

    for index, row in enumerate(
        prices,
        start=1,
    ):
        row["sira"] = index

    price_data[
        "fiyatlar"
    ] = prices

    price_data[
        "toplamFiyatKaydi"
    ] = len(prices)

    price_data[
        "sonGuncelleme"
    ] = today()

    write_json(
        PRODUCTION_PRICE_FILE,
        price_data,
    )

    write_json(
        PRICE_HISTORY_FILE,
        {
            "schemaVersion": 1,
            "updatedAt": now(),
            "count": len(
                price_history
            ),
            "history": price_history,
        },
    )
    # ========================================================
    # STAGE OPTIONAL MODULES
    # ========================================================

    if (
        modules
        .get(
            "images",
            {},
        )
        .get(
            "enabled",
            False,
        )
    ):
        stage_optional_module(
            "images",
            staged_images,
        )

    if (
        modules
        .get(
            "catalogs",
            {},
        )
        .get(
            "enabled",
            False,
        )
    ):
        stage_optional_module(
            "catalogs",
            staged_catalogs,
        )

    if (
        modules
        .get(
            "branches",
            {},
        )
        .get(
            "enabled",
            False,
        )
    ):
        stage_optional_module(
            "branches",
            staged_branches,
        )

    # ========================================================
    # QUARANTINE
    # ========================================================

    quarantine_file = (
        QUARANTINE_DIR
        / "bulk_official_intake_v1_quarantine.json"
    )

    write_json(
        quarantine_file,
        {
            "schemaVersion": 1,
            "generatedAt": now(),
            "count": len(
                quarantine
            ),
            "records": quarantine,
        },
    )

    # ========================================================
    # REPORT
    # ========================================================

    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "pipeline":
            "bulk_official_intake_v1",

        "stats": stats,

        "production": {
            "productCategoriesTouched":
                len(category_cache),

            "productionPriceCount":
                len(prices),
        },

        "backups": {
            "productionPrices":
                price_backup,

            "categories":
                category_backups,
        },

        "outputs": {
            "productionPrices":
                str(
                    PRODUCTION_PRICE_FILE
                ),

            "quarantine":
                str(
                    quarantine_file
                ),

            "images":
                str(
                    OUTPUT_DIR
                    / "images.json"
                ),

            "catalogs":
                str(
                    OUTPUT_DIR
                    / "catalogs.json"
                ),

            "branches":
                str(
                    OUTPUT_DIR
                    / "branches.json"
                ),
        },
    }

    report_file = (
        REPORT_DIR
        / "bulk_official_intake_v1_report.json"
    )

    write_json(
        report_file,
        report,
    )

    print()
    print(
        "RAW kayÄ±t             :",
        stats["rawRecords"],
    )

    print(
        "Mevcut Ã¼rÃ¼n eÅŸleÅŸti   :",
        stats[
            "existingProductsMatched"
        ],
    )

    print(
        "Yeni Ã¼rÃ¼n oluÅŸturuldu :",
        stats[
            "newProductsCreated"
        ],
    )

    print(
        "Yeni verified fiyat   :",
        stats[
            "newVerifiedPrices"
        ],
    )

    print(
        "Duplicate fiyat       :",
        stats[
            "duplicatePrices"
        ],
    )

    print(
        "Rejected / quarantine :",
        stats["rejected"],
    )

    print(
        "GÃ¶rsel staged         :",
        stats["imagesStaged"],
    )

    print(
        "Katalog staged        :",
        stats["catalogsStaged"],
    )

    print(
        "Åube staged           :",
        stats["branchesStaged"],
    )

    print(
        "Production fiyat      :",
        len(prices),
    )

    print(
        "Rapor                  :",
        report_file,
    )

    print("=" * 80)

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()

    except Exception as exc:
        print()
        print(
            "BULK OFFICIAL INTAKE V1 ERROR"
        )

        print(
            repr(exc)
        )

        exit_code = 1

    sys.exit(exit_code)

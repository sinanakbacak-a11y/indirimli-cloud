import json
import sys
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[2]
PLATFORM = BASE / "unified_data_platform"
CONFIG = PLATFORM / "config"
INPUTS = PLATFORM / "inputs"
INDEXES = PLATFORM / "indexes"
REPORTS = PLATFORM / "reports"
QUARANTINE = PLATFORM / "quarantine"
ACTIVE_POINTER = CONFIG / "active_platform.json"

MARKET_MASTER_URL = "https://raw.githubusercontent.com/sinanakbacak-a11y/indirimli-cloud/main/marketler.json"

BRANCH_ALIASES = {
    "carrefoursa_uskudar_test_001": "carrefoursa_umraniye_test_001",
}

def now():
    return datetime.now().isoformat(timespec="seconds")

def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def fetch_json(url):
    req = Request(url + f"?v={int(datetime.now().timestamp())}",
                  headers={"User-Agent":"IndirimliUnifiedImporter/1.3"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))

def extract_rows(data, *keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []

def ensure_pointer():
    if ACTIVE_POINTER.exists():
        pointer = read_json(ACTIVE_POINTER)
    else:
        pointer = {
            "schemaVersion": 1,
            "activePlatform": "legacy_v17",
            "candidatePlatform": "unified_v1",
            "automaticFallback": False,
            "rollbackRequiresApproval": True,
            "candidateValidated": False,
            "cutoverApproved": False,
            "updatedAt": now(),
        }
    pointer["automaticFallback"] = False
    pointer["cutoverApproved"] = False
    pointer["updatedAt"] = now()
    write_json(ACTIVE_POINTER, pointer)
    return pointer

def normalize_text(value):
    value = str(value or "").strip().casefold()
    table = str.maketrans({
        "ı":"i","ğ":"g","ü":"u","ş":"s","ö":"o","ç":"c",
        "İ":"i","Ğ":"g","Ü":"u","Ş":"s","Ö":"o","Ç":"c"
    })
    return value.translate(table)


def normalize_product_name(name, brand):
    name = str(name or "").strip()
    brand = str(brand or "").strip()

    if not name:
        return ""

    if not brand:
        return name

    normalized_name = normalize_text(name)
    normalized_brand = normalize_text(brand)

    repeated_prefix = f"{normalized_brand} {normalized_brand} "

    if normalized_name.startswith(repeated_prefix):
        parts = name.split()

        if len(parts) >= 2:
            return " ".join(parts[1:]).strip()

    return name


def build_market_name_index(markets):
    index = {}
    for market_id, row in markets.items():
        for raw in (market_id, row.get("ad")):
            key = normalize_text(raw)
            if key:
                index.setdefault(key, set()).add(market_id)
    return index

def build_branches_by_market(branches):
    result = {}
    for branch_id, row in branches.items():
        market_id = str(row.get("marketId") or "").strip()
        if market_id:
            result.setdefault(market_id, []).append(branch_id)
    return result

def auto_repair_market_branch(row, markets, branches, market_name_index, branches_by_market):
    """
    Conservative repair only:
    - known branch alias
    - branch -> market inference
    - exact market name/id -> marketId
    - market with exactly one known branch -> subeId
    Never guesses when multiple candidates exist.
    """
    changes = []
    market_id = str(row.get("marketId") or "").strip()
    branch_id = str(row.get("subeId") or "").strip()
    market_name = str(row.get("market") or "").strip()

    if branch_id in BRANCH_ALIASES:
        old = branch_id
        branch_id = BRANCH_ALIASES[branch_id]
        changes.append(("branch_alias", "subeId", old, branch_id))

    branch = branches.get(branch_id)
    if not market_id and branch is not None:
        market_id = str(branch.get("marketId") or "").strip()
        if market_id:
            changes.append(("branch_to_market", "marketId", "", market_id))

    if not market_id and market_name:
        candidates = set()
        for key in (normalize_text(market_name),):
            candidates.update(market_name_index.get(key, set()))
        if len(candidates) == 1:
            market_id = next(iter(candidates))
            changes.append(("market_name_to_id", "marketId", "", market_id))

    if market_id and not branch_id:
        candidates = branches_by_market.get(market_id, [])
        if len(candidates) == 1:
            branch_id = candidates[0]
            changes.append(("single_branch_for_market", "subeId", "", branch_id))

    row["marketId"] = market_id
    row["subeId"] = branch_id
    return changes


def is_canonical_category_file(path):
    """
    Accept only canonical category JSON files.
    Reject backups, copies, reports and generated helper files.
    """
    name = path.name
    stem = path.stem.lower()

    if name == "index_adayi.json":
        return False

    rejected_tokens = [
        "rapor",
        "report",
        "backup",
        "yedek",
        "copy",
        "kopya",
        "extract",
    ]

    if any(token in stem for token in rejected_tokens):
        return False

    # Windows/browser duplicate pattern: "sut (2).json"
    if re.search(r"\s\(\d+\)$", path.stem):
        return False

    return True

def main():
    print("=" * 80)
    print("INDIRIMLI UNIFIED IMPORTER V1.5")
    print("=" * 80)

    if not PLATFORM.exists():
        print("ERROR: unified_data_platform not found.")
        return 2

    pointer = ensure_pointer()
    print("Active platform    :", pointer.get("activePlatform"))
    print("Candidate platform :", pointer.get("candidatePlatform"))
    print("Automatic fallback :", pointer.get("automaticFallback"))
    print("-" * 80)

    quarantine = []
    corrections = []

    print("1/4 Loading Market Master from locked cloud source...")
    print("Market Master URL  :", MARKET_MASTER_URL)
    try:
        market_data = fetch_json(MARKET_MASTER_URL)
    except Exception as exc:
        print("ERROR: Market Master could not be downloaded.")
        print(repr(exc))
        return 3

    market_rows = extract_rows(market_data, "marketler", "subeler", "data")
    markets = {}
    branches = {}

    for row in market_rows:
        if not isinstance(row, dict):
            quarantine.append({"type":"market_row_not_object"})
            continue
        market_id = str(row.get("marketId") or "").strip()
        branch_id = str(row.get("subeId") or "").strip()
        name = str(row.get("ad") or "").strip()
        if not market_id or not branch_id or not name:
            quarantine.append({
                "type":"market_branch_missing_field",
                "marketId":market_id,"subeId":branch_id,"ad":name
            })
            continue
        markets.setdefault(market_id,{
            "marketId":market_id,"ad":name,
            "status":"candidate","source":"cloud_market_master"
        })
        branches[branch_id]={
            "subeId":branch_id,"marketId":market_id,"ad":name,
            "sube":str(row.get("sube") or "").strip(),
            "adres":str(row.get("adres") or "").strip(),
            "enlem":row.get("enlem"),"boylam":row.get("boylam"),
            "veriDurumu":str(row.get("veriDurumu") or "").strip(),
            "status":"candidate","source":"cloud_market_master"
        }

    print("Market Master      :", len(markets))
    print("Branch Master      :", len(branches))

    market_name_index = build_market_name_index(markets)
    branches_by_market = build_branches_by_market(branches)

    print("2/4 Loading category packs...")
    category_dir = BASE / "category_packs"
    categories = {}
    products = {}
    prices = []

    if not category_dir.exists():
        print("ERROR: category_packs not found:", category_dir)
        return 4

    all_json_files = list(sorted(category_dir.glob("*.json")))
    category_files = [p for p in all_json_files if is_canonical_category_file(p)]
    ignored_files = [p.name for p in all_json_files if p not in category_files]

    print("Category files     :", len(category_files))
    print("Ignored JSON files :", len(ignored_files))
    for ignored in ignored_files:
        print("  IGNORE           :", ignored)

    for path in category_files:
        try:
            data = read_json(path)
        except Exception as exc:
            quarantine.append({"type":"category_file_read_error","file":str(path),"error":repr(exc)})
            continue

        rows = extract_rows(data, "urunler")
        category_id = str(data.get("kategoriId") or path.stem).strip()
        category_name = str(data.get("kategoriAdi") or data.get("ad") or category_id).strip()

        categories[category_id]={
            "kategoriId":category_id,"ad":category_name,
            "status":"candidate","source":"legacy_import"
        }

        for row in rows:
            if not isinstance(row, dict):
                continue
            product_id = str(row.get("id") or "").strip()
            master_id = str(row.get("masterProductId") or row.get("karsilastirmaId") or "").strip()
            if not product_id or not master_id:
                quarantine.append({
                    "type":"product_missing_identity","file":str(path),
                    "id":product_id,"masterProductId":master_id
                })
                continue

            relation_row = {
                "market": str(row.get("market") or "").strip(),
                "marketId": str(row.get("marketId") or "").strip(),
                "subeId": str(row.get("subeId") or "").strip(),
            }
            repairs = auto_repair_market_branch(
                relation_row, markets, branches, market_name_index, branches_by_market
            )
            market_id = relation_row["marketId"]
            branch_id = relation_row["subeId"]
            for repair_type, field, old_value, new_value in repairs:
                corrections.append({
                    "type": repair_type,
                    "productId": product_id,
                    "field": field,
                    "oldValue": old_value,
                    "newValue": new_value,
                })

            products[product_id] = {
                "id": product_id,
                "masterProductId": master_id,
                "karsilastirmaId": str(row.get("karsilastirmaId") or "").strip(),
                "ad": normalize_product_name(
    row.get("ad"),
    row.get("marka"),
),
                "marka": str(row.get("marka") or "").strip(),
                "kategoriId": str(row.get("kategoriId") or category_id).strip(),
                "kategori": str(row.get("kategori") or category_name).strip(),
                "gramaj": str(row.get("gramaj") or "").strip(),
                "birim": str(row.get("birim") or "").strip(),
                "barkod": str(row.get("barkod") or "").strip(),
                "market": relation_row["market"],
                "marketId": market_id,
                "subeId": branch_id,
                "status": "candidate",
                "source": "legacy_import",
            }

            try:
                price_value = float(row.get("fiyat"))
            except Exception:
                price_value = None

            # ============================================================
            # UNIFIED PRICE RESOLVER V1
            # Otomatik test fiyatlarini production price katmanina gecirmez.
            # Urun kaydi korunur, test fiyati quarantine'e alinir.
            # ============================================================

            price_source = str(row.get("kaynak") or "").strip()
            price_data_status = str(row.get("veriDurumu") or "").strip()
            branch_id_lower = str(branch_id or "").strip().lower()

            is_test_price = (
                price_source.lower() in {
                    "market_variant_generator_v1",
                    "csv_otomatik_test",
                    "regional_integrity_test",
                }
                or price_data_status.lower() in {
                    "otomatik_test",
                    "test",
                }
                or "_test_" in branch_id_lower
            )

            quarantine.append({
                "type": "price_excluded_by_production_gate",
                "resolver": "unified_price_resolver_v1",
                "reason": (
                    "test_price_not_allowed_in_production"
                    if is_test_price
                    else "unverified_legacy_price_not_allowed_in_production"
                ),
                "productId": product_id,
                "masterProductId": master_id,
                "marketId": market_id,
                "subeId": branch_id,
                "fiyat": price_value,
                "kaynak": price_source,
                "veriDurumu": price_data_status,
                "sourceFile": str(path),
            })

    # ============================================================
    # VERIFIED PRODUCTION PRICE IMPORT V1
    # Dogrulanmis production fiyatlarini Unified Price Layer'a ekler.
    # ============================================================

    verified_price_path = (
        BASE
        / "gercek_pilot"
        / "cloud_export"
        / "production_fiyatlar.json"
    )

    verified_added = 0
    verified_quarantine = 0

    if verified_price_path.exists():
        verified_data = read_json(verified_price_path)
        verified_rows = extract_rows(
            verified_data,
            "fiyatlar",
        )

        def comparable_name(name, brand):
            value = normalize_text(name)
            brand_value = normalize_text(brand)

            if brand_value:
                while value.startswith(brand_value + " "):
                    value = value[len(brand_value):].strip()

            value = re.sub(r"\s+", " ", value).strip()
            return value

        def comparable_master(master_id, brand):
            value = normalize_text(master_id)
            brand_value = normalize_text(brand)

            if brand_value:
                prefix = brand_value + "_"
                while value.startswith(prefix):
                    value = value[len(prefix):]

            return value.strip("_")

        for row in verified_rows:
            if not isinstance(row, dict):
                continue

            if row.get("aktif") is not True:
                continue

            if str(
                row.get("dogrulamaDurumu") or ""
            ).strip().lower() != "dogrulandi":
                continue

            try:
                verified_price = float(row.get("fiyat"))
            except Exception:
                verified_price = 0

            if verified_price <= 0:
                continue

            verified_market_id = str(
                row.get("marketId") or ""
            ).strip()

            verified_branch_id = str(
                row.get("subeId") or ""
            ).strip()

            verified_master = str(
                row.get("masterProductId") or ""
            ).strip()

            verified_name = str(
                row.get("urunAdi") or ""
            ).strip()

            verified_brand = str(
                row.get("marka") or ""
            ).strip()

            resolved_product = None

            # 1) Birebir masterProductId + market
            for product in products.values():
                if (
                    product.get("masterProductId") == verified_master
                    and product.get("marketId") == verified_market_id
                ):
                    resolved_product = product
                    break

            # 2) Marka temizlenmis masterProductId + market
            if resolved_product is None:
                verified_master_cmp = comparable_master(
                    verified_master,
                    verified_brand,
                )

                for product in products.values():
                    product_master_cmp = comparable_master(
                        product.get("masterProductId"),
                        verified_brand,
                    )

                    if (
                        product_master_cmp == verified_master_cmp
                        and product.get("marketId") == verified_market_id
                    ):
                        resolved_product = product
                        break

            # 3) Marka temizlenmis urun adi + market
            if resolved_product is None:
                verified_name_cmp = comparable_name(
                    verified_name,
                    verified_brand,
                )

                for product in products.values():
                    product_name_cmp = comparable_name(
                        product.get("ad"),
                        verified_brand,
                    )

                    if (
                        product_name_cmp == verified_name_cmp
                        and product.get("marketId") == verified_market_id
                    ):
                        resolved_product = product
                        break

            if resolved_product is None:
                verified_quarantine += 1

                quarantine.append({
                    "type": "verified_price_product_not_resolved",
                    "masterProductId": verified_master,
                    "urunAdi": verified_name,
                    "marketId": verified_market_id,
                    "subeId": verified_branch_id,
                    "fiyat": verified_price,
                    "sourceFile": str(verified_price_path),
                })

                continue

            resolved_product_id = resolved_product["id"]
            resolved_master_id = resolved_product["masterProductId"]

            # Ayni urun/market/sube icin eski candidate fiyat varsa
            # dogrulanmis production fiyati onun yerine gecer.
            prices[:] = [
                price
                for price in prices
                if not (
                    price.get("productId") == resolved_product_id
                    and price.get("marketId") == verified_market_id
                    and price.get("subeId") == verified_branch_id
                )
            ]

            prices.append({
                "productId": resolved_product_id,
                "masterProductId": resolved_master_id,
                "market": str(
                    row.get("market") or ""
                ).strip(),
                "marketId": verified_market_id,
                "subeId": verified_branch_id,
                "fiyat": verified_price,
                "fiyatBaslangic": str(
                    row.get("fiyatBaslangic") or ""
                ).strip(),
                "fiyatBitis": str(
                    row.get("fiyatBitis") or ""
                ).strip(),
                "kaynak": str(
                    row.get("kaynak") or ""
                ).strip(),
                "kaynakUrl": str(
                    row.get("kaynakUrl") or ""
                ).strip(),
                "veriDurumu": "production_verified",
                "status": "candidate",
                "source": "verified_production_import",
                "priceResolver": "verified_production_price_resolver_v1",
            })

            verified_added += 1

        print(
            "Verified prices added:",
            verified_added,
        )
        print(
            "Verified price quarantine:",
            verified_quarantine,
        )
    else:
        print(
            "Verified production price file not found:",
            verified_price_path,
        )

    print("3/4 Validating relations...")
    relation_errors = 0
    market_ids = set(markets.keys())
    category_ids = set(categories.keys())
    product_ids = set(products.keys())

    for product in products.values():
        if product["kategoriId"] not in category_ids:
            relation_errors += 1
            quarantine.append({"type":"product_category_relation_error","id":product["id"],
                               "kategoriId":product["kategoriId"]})

    for price in prices:
        if price["productId"] not in product_ids:
            relation_errors += 1
            quarantine.append({"type":"price_product_relation_error","productId":price["productId"]})

        if price["marketId"] not in market_ids:
            relation_errors += 1
            quarantine.append({"type":"unresolved_price_market_relation","productId":price["productId"],
                               "marketId":price["marketId"]})

        branch = branches.get(price["subeId"])
        if branch is None:
            relation_errors += 1
            quarantine.append({"type":"unresolved_price_branch_relation","productId":price["productId"],
                               "subeId":price["subeId"]})
        elif branch["marketId"] != price["marketId"]:
            relation_errors += 1
            quarantine.append({"type":"price_branch_market_mismatch","productId":price["productId"],
                               "marketId":price["marketId"],"subeId":price["subeId"],
                               "branchMarketId":branch["marketId"]})

    print("4/4 Writing candidate platform files...")
    write_json(INPUTS/"markets"/"cloud_market_master.json",
               {"schemaVersion":1,"importedAt":now(),"sourceUrl":MARKET_MASTER_URL,
                "markets":list(markets.values())})
    write_json(INPUTS/"branches"/"cloud_branch_master.json",
               {"schemaVersion":1,"importedAt":now(),"sourceUrl":MARKET_MASTER_URL,
                "branches":list(branches.values())})
    write_json(INPUTS/"categories"/"legacy_categories_import.json",
               {"schemaVersion":1,"importedAt":now(),"categories":list(categories.values())})
    write_json(INPUTS/"products"/"legacy_products_import.json",
               {"schemaVersion":1,"importedAt":now(),"products":list(products.values())})
    write_json(INPUTS/"prices"/"legacy_prices_import.json",
               {"schemaVersion":1,"importedAt":now(),"prices":prices})

    write_json(INDEXES/"markets_index.json",
               {"schemaVersion":1,"updatedAt":now(),"markets":list(markets.values())})
    write_json(INDEXES/"branches_index.json",
               {"schemaVersion":1,"updatedAt":now(),"branches":list(branches.values())})
    write_json(INDEXES/"categories_index.json",
               {"schemaVersion":1,"updatedAt":now(),"categories":list(categories.values())})
    write_json(INDEXES/"products_index.json",
               {"schemaVersion":1,"updatedAt":now(),"products":list(products.values())})

    write_json(QUARANTINE/"unified_importer_v1_5_quarantine.json",
               {"schemaVersion":1,"generatedAt":now(),"toplam":len(quarantine),"kayitlar":quarantine})
    write_json(REPORTS/"unified_importer_v1_5_corrections.json",
               {"schemaVersion":1,"generatedAt":now(),"toplam":len(corrections),"duzeltmeler":corrections})

    candidate_valid = (relation_errors == 0 and len(markets)>0 and len(branches)>0 and len(products)>0)

    pointer["candidateValidated"] = candidate_valid
    pointer["cutoverApproved"] = False
    pointer["automaticFallback"] = False
    pointer["updatedAt"] = now()
    write_json(ACTIVE_POINTER, pointer)

    report = {
        "schemaVersion":1,"generatedAt":now(),"mode":"IMPORT_AND_VALIDATE_ONLY",
        "marketMasterSource":MARKET_MASTER_URL,
        "counts":{"markets":len(markets),"branches":len(branches),
                  "categories":len(categories),"products":len(products),"prices":len(prices)},
        "automaticCorrections":len(corrections),
        "autoRepairEngine":"SAFE_EXACT_MATCH_ONLY",
        "canonicalFileGuard":True,
        "ignoredFiles":ignored_files,
        "relationErrors":relation_errors,
        "quarantineCount":len(quarantine),
        "candidateValidated":candidate_valid,
        "activePlatform":pointer.get("activePlatform"),
        "candidatePlatform":pointer.get("candidatePlatform"),
        "automaticFallback":False,
        "cutoverApproved":False,
    }
    write_json(REPORTS/"unified_importer_v1_5_report.json", report)

    print("-"*80)
    print("Markets            :",len(markets))
    print("Branches           :",len(branches))
    print("Categories         :",len(categories))
    print("Products           :",len(products))
    print("Price rows         :",len(prices))
    print("Auto corrections   :",len(corrections))
    print("Repair policy       : SAFE_EXACT_MATCH_ONLY")
    print("Canonical guard     : ON")
    print("Relation errors    :",relation_errors)
    print("Quarantine         :",len(quarantine))
    print("-"*80)
    print("Candidate valid    :",candidate_valid)
    print("CUTOVER NOT PERFORMED.")
    print("Legacy active platform unchanged.")
    print("Automatic fallback disabled.")
    print("="*80)
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as exc:
        print()
        print("UNIFIED IMPORTER V1.3 ERROR")
        print(repr(exc))
        exit_code = 1
    sys.exit(exit_code)



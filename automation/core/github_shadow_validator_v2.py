import json
import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin

BASE = Path(__file__).resolve().parent
PLATFORM = BASE / "unified_data_platform"
LOCAL_ROOT = PLATFORM / "publish_ready" / "flutter_shadow"

BASE_RAW = "https://raw.githubusercontent.com/sinanakbacak-a11y/indirimli-cloud/main/shadow/"
LATEST_URL = urljoin(BASE_RAW, "latest.json")

def fetch_bytes(url):
    req = Request(url, headers={"User-Agent":"IndirimliGithubShadowValidator/2.0"})
    with urlopen(req, timeout=30) as r:
        return r.read()

def fetch_json(url):
    raw = fetch_bytes(url)
    return json.loads(raw.decode("utf-8")), raw

def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)

def canonical_bytes(obj):
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

def canonical_sha(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()

def fail(msg, detail=None):
    print("="*80)
    print("INDIRIMLI GITHUB SHADOW VALIDATOR V2")
    print("="*80)
    print("VALIDATION: FAIL")
    print("Reason:", msg)
    if detail is not None:
        print("Details:", detail)
    print("="*80)
    return 1

def compare_json(local_path, remote_url, label):
    if not local_path.exists():
        raise FileNotFoundError(str(local_path))
    local_obj = read_json(local_path)
    remote_obj, _ = fetch_json(remote_url)

    if local_obj != remote_obj:
        return False, {
            "label": label,
            "localCanonicalSha256": canonical_sha(local_obj),
            "remoteCanonicalSha256": canonical_sha(remote_obj),
        }

    return True, {
        "label": label,
        "canonicalSha256": canonical_sha(local_obj),
    }

def main():
    print("="*80)
    print("INDIRIMLI GITHUB SHADOW VALIDATOR V2")
    print("="*80)

    print("1/5 latest.json semantic kontrol...")
    try:
        remote_latest, _ = fetch_json(LATEST_URL)
    except Exception as e:
        return fail("remote latest.json okunamadi", repr(e))

    local_latest_path = LOCAL_ROOT / "latest.json"
    if not local_latest_path.exists():
        return fail("local latest.json bulunamadi", str(local_latest_path))

    local_latest = read_json(local_latest_path)

    if local_latest != remote_latest:
        return fail("latest.json semantic olarak farkli", {
            "localCanonicalSha256": canonical_sha(local_latest),
            "remoteCanonicalSha256": canonical_sha(remote_latest),
        })

    pid = str(remote_latest.get("packageId") or "").strip()
    manifest_rel = str(remote_latest.get("manifestPath") or "").strip()

    if not pid or not manifest_rel:
        return fail("latest.json zorunlu alanlari eksik")

    local_package = LOCAL_ROOT / "packages" / pid
    local_manifest = local_package / "manifest.json"
    remote_manifest_url = urljoin(BASE_RAW, manifest_rel)

    print("2/5 manifest semantic kontrol...")
    ok, info = compare_json(local_manifest, remote_manifest_url, "manifest.json")
    if not ok:
        return fail("manifest semantic olarak farkli", info)

    manifest = read_json(local_manifest)

    if manifest.get("mode") != "SHADOW_READ_ONLY":
        return fail("manifest mode gecersiz")

    validation = manifest.get("validation") or {}
    if validation.get("preCutoverPassed") is not True:
        return fail("preCutoverPassed true degil")
    if int(validation.get("relationErrorCount") or 0) != 0:
        return fail("relationErrorCount sifir degil")
    if int(validation.get("quarantineCount") or 0) != 0:
        return fail("quarantineCount sifir degil")

    policy = manifest.get("flutterPolicy") or {}
    if policy.get("shadowOnly") is not True:
        return fail("shadowOnly true degil")
    for key in [
        "mayMutateAppState",
        "mayCallSetState",
        "mayWriteFavorites",
        "mayWritePriceAlerts",
        "mayActivateLegacy",
    ]:
        if policy.get(key) is not False:
            return fail(f"{key} false degil")

    package_base = urljoin(BASE_RAW, f"packages/{pid}/")

    entries = []
    for name, e in (manifest.get("files") or {}).items():
        if isinstance(e, dict):
            entries.append((e["path"], f"master:{name}"))
    for i, e in enumerate(manifest.get("productChunks") or [], 1):
        entries.append((e["path"], f"product:{i}"))
    for i, e in enumerate(manifest.get("priceChunks") or [], 1):
        entries.append((e["path"], f"price:{i}"))

    print("3/5 master dosyalari semantic kontrol...")
    print("4/5 product chunk semantic kontrol...")
    print("5/5 price chunk semantic kontrol...")

    verified = []
    for rel, label in entries:
        local_path = local_package / Path(rel)
        remote_url = urljoin(package_base, rel)
        try:
            ok, info = compare_json(local_path, remote_url, label)
        except Exception as e:
            return fail("dosya okunamadi", {"path": rel, "error": repr(e)})
        if not ok:
            return fail("remote dosya local publish-ready ile farkli", {
                "path": rel,
                **info
            })
        verified.append({"path": rel, **info})

    counts = manifest.get("counts") or {}

    print("-"*80)
    print("Package ID          :", pid)
    print("Markets             :", counts.get("markets"))
    print("Branches            :", counts.get("branches"))
    print("Categories          :", counts.get("categories"))
    print("Products            :", counts.get("products"))
    print("Prices              :", counts.get("prices"))
    print("Validated files     :", len(verified))
    print("-"*80)
    print("GITHUB SHADOW VALIDATION V2: PASS")
    print("SEMANTIC JSON MATCH       : PASS")
    print("ACCESSIBILITY             : PASS")
    print("SHADOW POLICY             : PASS")
    print("RAW BYTE DIFFERENCE       : IGNORED BY DESIGN")
    print("FLUTTER CUTOVER           : NOT PERFORMED")
    print("="*80)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("GITHUB SHADOW VALIDATOR V2 ERROR")
        print(repr(e))
        sys.exit(2)

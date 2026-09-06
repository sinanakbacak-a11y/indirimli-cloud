MARKET_ID = "bim"


def collect(
    market_id,
    permissions,
):
    return {
        "schemaVersion": 1,
        "marketId": market_id,
        "adapterName": "bim_adapter_v1",
        "adapterVersion": "1",

        "products": [],
        "prices": [],
        "images": [],
        "catalogs": [],
        "branches": [],

        "metadata": {
            "mode": "dry_run",
            "networkRequest": False,
            "permissions": permissions,
        },

        "errors": [],
        "warnings": [],
    }
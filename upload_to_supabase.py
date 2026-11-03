"""Carga data/ a Supabase (base chilena, ver schema.sql).

Lee data/retailer_stores.json + data/prices.csv.gz y hace upsert via
PostgREST. Requiere la service_role key solo para escribir; la app usa la
publishable key de solo lectura.

Uso:
    export SUPABASE_URL="https://<ref>.supabase.co"
    export SUPABASE_SERVICE_ROLE_KEY="<service_role, nunca commitear>"
    python upload_to_supabase.py --dry-run   # valida sin escribir
    python upload_to_supabase.py
"""
import argparse
import csv
import gzip
import json
import os
import sys
import time

import requests

PRICE_COLUMNS = [
    "ean", "country_code", "region_id", "city_id", "store_id", "chain_id",
    "price", "promo_price", "currency", "stock", "stock_quantity",
    "last_updated", "source", "product_name", "description", "brand",
    "image_url", "category_path", "measurement_unit", "unit_multiplier",
    "promotion_names",
]


def _client():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        sys.exit("faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY en el entorno")
    session = requests.Session()
    session.headers.update({
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    })
    return session, url


def _upsert(session, url, table, rows, on_conflict, batch=500):
    total = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        resp = session.post(
            f"{url}/rest/v1/{table}?on_conflict={on_conflict}",
            data=json.dumps(chunk),
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            sys.exit(f"upsert {table} fallo: HTTP {resp.status_code} {resp.text[:300]}")
        total += len(chunk)
        print(f"  {table}: {total}/{len(rows)}")
        time.sleep(0.2)
    return total


def _open_csv(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")


def _clean_price_row(row):
    out = {col: (row.get(col) or None) for col in PRICE_COLUMNS}
    for col in ("price", "promo_price", "stock_quantity", "unit_multiplier"):
        if out[col] in ("", None):
            out[col] = None
    for col in ("brand", "image_url", "category_path", "description",
                "measurement_unit", "promotion_names"):
        if not out[col]:
            out[col] = None
    out["stock"] = str(row.get("stock", "")).lower() == "true"
    return out


def main():
    parser = argparse.ArgumentParser(description="Carga dataset a Supabase")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-stores", action="store_true")
    parser.add_argument("--skip-prices", action="store_true")
    args = parser.parse_args()

    stores_path = os.path.join(args.data_dir, "retailer_stores.json")
    with open(stores_path, encoding="utf-8") as fh:
        stores = json.load(fh)
    print(f"locales: {len(stores)} (ej: {stores[0]['id']} / {stores[0]['name']})")

    prices_path = os.path.join(args.data_dir, "prices.csv.gz")
    if not os.path.exists(prices_path):
        prices_path = os.path.join(args.data_dir, "prices.csv")
    if not os.path.exists(prices_path):
        sys.exit(f"sin prices.csv(.gz) en {args.data_dir}")

    if args.dry_run:
        with _open_csv(prices_path) as fh:
            reader = csv.DictReader(fh)
            first = next(reader)
            n = 1 + sum(1 for _ in reader)
        print(f"  {os.path.basename(prices_path)}: {n} filas, ej: "
              f"{first['ean']} | {first['product_name'][:50]} | "
              f"${first['price']} | {first['store_id']}")
        print("dry-run OK, nada escrito")
        return

    session, url = _client()
    if not args.skip_stores:
        print("subiendo locales...")
        _upsert(session, url, "retailer_stores", stores, "id", args.batch)
    if not args.skip_prices:
        print(f"subiendo {os.path.basename(prices_path)}...")
        rows = []
        with _open_csv(prices_path) as fh:
            for row in csv.DictReader(fh):
                rows.append(_clean_price_row(row))
        _upsert(session, url, "product_prices", rows, "ean,store_id", args.batch)
    print("carga completa")


if __name__ == "__main__":
    main()

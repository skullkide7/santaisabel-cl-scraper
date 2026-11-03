"""Catalogo Santa Isabel Chile -> data/prices.csv.gz + data/retailer_stores.json.

Uso:
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python scrape_catalog.py [--limit-products N]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vtex import scrape_chain

CONFIG = {
    "chain_id": "santaisabel",
    "chain_name": "Santa Isabel",
    "account": "santaisabel",
    "storefront": "https://www.santaisabel.cl",
    "image_host": "santaisabel.vtexassets.com",
}


def main():
    parser = argparse.ArgumentParser(description="Scraper catalogo Santa Isabel Chile")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--limit-categories", type=int, default=None)
    parser.add_argument("--limit-products", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.35)
    args = parser.parse_args()
    scrape_chain(
        CONFIG,
        args.out_dir,
        limit_categories=args.limit_categories,
        limit_products=args.limit_products,
        max_pages=args.max_pages,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()

"""Pruebas del scraper (stdlib unittest, sin dependencias extra).

Uso: python -m unittest
"""
import csv
import gzip
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtex

CONFIG = {
    "chain_id": "test",
    "chain_name": "Test",
    "account": "test",
    "storefront": "https://example.cl",
    "image_host": "img",
}

LOCALES_HTML = (
    '\\"id\\":\\"loc-1\\",\\"name\\":\\"Centro\\",'
    '\\"address\\":\\"Av 1\\",\\"manager\\":\\"M\\",'
    '\\"region\\":\\"Región Metropolitana\\",\\"city\\":\\"Santiago\\",'
    '\\"coordinates\\":{\\"lat\\":-33.45,\\"lng\\":-70.66}'
)

TREE = [
    {"id": 1, "name": "A", "children": [
        {"id": 2, "name": "B", "children": []},
        {"id": 3, "name": "C", "children": []},
    ]}
]

PRODUCT = {
    "productId": "9",
    "description": "<p>Una rica <b>leche</b></p>",
    "brand": "Marca",
    "categories": ["/A/C/"],
    "clusterHighlights": {"7": "7 Promo X", "8": "Promo Y"},
    "items": [{
        "ean": "780000000001",
        "name": "Leche 1L",
        "nameComplete": "Leche Entera 1L",
        "measurementUnit": "un",
        "unitMultiplier": 1,
        "images": [{"imageUrl": "https://img/p.jpg"}],
        "sellers": [{"commertialOffer": {
            "Price": 100.0, "ListPrice": 150.0, "AvailableQuantity": 5,
        }}],
    }],
}


class ScraperTests(unittest.TestCase):
    def test_leaf_categories_use_full_path_filter(self):
        self.assertEqual(
            vtex.leaf_categories(TREE),
            [("C:/1/2/", "A > B"), ("C:/1/3/", "A > C")],
        )

    def test_parse_product_price_and_promo(self):
        rows, _ = vtex.parse_product(PRODUCT, "img")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["ean"], "780000000001")
        self.assertEqual(row["price"], 150.0)
        self.assertEqual(row["promo_price"], 100.0)
        self.assertTrue(row["stock"])
        self.assertEqual(row["description"], "Una rica leche")
        self.assertEqual(row["measurement_unit"], "un")
        self.assertIn("Promo X", row["promotion_names"])
        self.assertIn("Promo Y", row["promotion_names"])

    def test_failed_category_does_not_abort_run(self):
        def search(fq, start, end):
            if fq == "C:/1/2/":
                raise RuntimeError("HTTP 500")
            return [PRODUCT] if start == 0 else []

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(vtex.VTEXClient, "fetch_page",
                              return_value=LOCALES_HTML), \
                 patch.object(vtex.VTEXClient, "category_tree",
                              return_value=TREE), \
                 patch.object(vtex.VTEXClient, "search_category",
                              side_effect=search):
                n_stores, n_skus, n_rows = vtex.scrape_chain(
                    CONFIG, tmp, delay=0)
        self.assertEqual((n_stores, n_skus, n_rows), (1, 1, 1))
        with gzip.open(os.path.join(tmp, "prices.csv.gz"), "rt") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ean"], "780000000001")
        self.assertEqual(rows[0]["price"], "150.0")
        self.assertEqual(rows[0]["promo_price"], "100.0")


if __name__ == "__main__":
    unittest.main()

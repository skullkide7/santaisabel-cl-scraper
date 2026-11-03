"""Cliente para el catalogo VTEX de Cencosud Chile (Jumbo / Santa Isabel).

Ambas cadenas usan la misma plataforma: storefront Next.js sobre un backend
VTEX cuya API de catalogo responde sin autenticacion. Este modulo concentra
toda la logica para generar siempre el mismo formato fila-por-(ean, tienda).

Fuentes por cadena:
  - Arbol de categorias + busqueda paginada por categoria:
      https://<account>.vtexcommercestable.com.br/api/catalog_system/...
    Entrega ean, nombre, descripcion, precio, precio lista, stock, marca,
    imagen y categoria.
  - Locales fisicos (ciudad, direccion, coordenadas): pagina /locales del
    storefront, que trae un arreglo `localities` embebido.

Aproximacion documentada (v1): VTEX expone un unico precio online por SKU
(un solo seller), no el precio de gondola de cada local. El scraper asigna
ese precio online a todos los locales fisicos, en el mismo formato
una-fila-por-(ean, tienda) que NZ, para que la app funcione (tienda mas
cercana + alternativas <=5 km). Si Cencosud publica precios por local, se
agrega como una pasada extra sin cambiar el formato.
"""

import csv
import gzip
import html
import json
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36 EANShopper-scraper/1.0"
)
COUNTRY_CODE = "CL"
COUNTRY_NAME = "Chile"
CURRENCY = "CLP"
PAGE_SIZE = 50  # maximo que acepta VTEX por pagina (_to - _from)


class VTEXClient:
    """Llamadas GET con reintentos y pausa entre requests."""

    def __init__(self, account, delay=0.35, timeout=30):
        self.base = f"https://{account}.vtexcommercestable.com.br"
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _get(self, path, params=None, tries=4):
        last = None
        for attempt in range(tries):
            try:
                resp = self.session.get(
                    self.base + path, params=params, timeout=self.timeout
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    last = f"HTTP {resp.status_code}"
                else:
                    resp.raise_for_status()
                    time.sleep(self.delay)
                    return resp
            except requests.RequestException as exc:  # red incluida
                last = str(exc)
            time.sleep(self.delay * (2 ** attempt) + 0.5)
        raise RuntimeError(f"GET {path} fallo tras {tries} intentos: {last}")

    def category_tree(self, depth=10):
        return self._get(f"/api/catalog_system/pub/category/tree/{depth}").json()

    def search_category(self, category_fq, start, end):
        return self._get(
            "/api/catalog_system/pub/products/search",
            params={"fq": category_fq, "_from": start, "_to": end},
        ).json()

    def fetch_page(self, url):
        last = None
        for attempt in range(4):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                time.sleep(self.delay)
                return resp.text
            except requests.RequestException as exc:
                last = str(exc)
            time.sleep(self.delay * (2 ** attempt) + 0.5)
        raise RuntimeError(f"GET {url} fallo tras 4 intentos: {last}")


def leaf_categories(tree, prefix="", ids=""):
    """Aplana el arbol a hojas: [(fq, 'A > B > C')].

    fq es el filtro VTEX con ruta completa (C:/1/3/549/): el id solo no
    filtra en hojas, verificado en vivo.
    """
    leaves = []
    for node in tree or []:
        path = f"{prefix} > {node['name']}" if prefix else node["name"]
        id_path = f"{ids}/{node['id']}"
        children = node.get("children") or []
        if children:
            leaves.extend(leaf_categories(children, path, id_path))
        else:
            leaves.append((f"C:{id_path}/", path))
    return leaves


def slugify(text):
    norm = unicodedata.normalize("NFKD", (text or "").lower())
    ascii_text = "".join(c for c in norm if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug or "sin-ciudad"


def strip_html(text):
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", no_tags)).strip()


# El HTML de /locales trae el arreglo `localities` con comillas escapadas
# (\" o \\\" segun el nivel); se acepta uno o mas backslashes.
_LOCALITY_RE = re.compile(
    r'\\+"id\\+":\\+"(?P<id>[^"\\]+)\\+",'
    r'\\+"name\\+":\\+"(?P<name>[^"\\]*)\\+",'
    r'\\+"address\\+":\\+"(?P<address>[^"\\]*)\\+",'
    r'\\+"manager\\+":\\+"(?P<manager>[^"\\]*)\\+",'
    r'\\+"region\\+":\\+"(?P<region>[^"\\]*)\\+",'
    r'\\+"city\\+":\\+"(?P<city>[^"\\]*)\\+",'
    r'\\+"coordinates\\+":\{\\+"lat\\+":(?P<lat>-?[\d.]+),'
    r'\\+"lng\\+":(?P<lng>-?[\d.]+)\}'
)


def parse_localities(html_text, chain_id, chain_name):
    """Extrae tiendas de /locales al esquema vivo de retailer_stores."""
    stores = []
    seen = set()
    for match in _LOCALITY_RE.finditer(html_text):
        loc_id = match.group("id")
        if loc_id in seen:
            continue
        seen.add(loc_id)
        name = match.group("name").strip()
        if not name.lower().startswith(chain_name.lower().split()[0]):
            name = f"{chain_name} {name}"
        region = match.group("region").strip()
        city = match.group("city").strip()
        stores.append(
            {
                "id": f"CL_{chain_id}_{loc_id}",
                "chain_id": chain_id,
                "chain_name": chain_name,
                "country_code": COUNTRY_CODE,
                "region_id": f"CL-{slugify(region)}",
                "city_id": slugify(city),
                "country_name": COUNTRY_NAME,
                "region_name": region,
                "city_name": city,
                "name": name,
                "address": match.group("address").strip(),
                "lat": float(match.group("lat")),
                "lon": float(match.group("lng")),
                "category": "supermarket",
                "is_active": True,
            }
        )
    stores.sort(key=lambda s: s["id"])
    return stores


def online_store(config):
    """Tienda virtual para el modelo slim.

    El precio VTEX es unico por cadena, asi que en modo slim las filas de
    precios referencian esta tienda y los locales fisicos se usan solo
    para proximidad (misma info, ~1/100 de las filas).
    """
    chain_id = config["chain_id"]
    chain_name = config["chain_name"]
    return {
        "id": f"CL_{chain_id}_online",
        "chain_id": chain_id,
        "chain_name": chain_name,
        "country_code": COUNTRY_CODE,
        "region_id": None,
        "city_id": None,
        "country_name": COUNTRY_NAME,
        "region_name": None,
        "city_name": None,
        "name": f"{chain_name} Online",
        "address": "Tienda online",
        "lat": None,
        "lon": None,
        "category": "online",
        "is_active": True,
    }


def _sku_offer(item):
    sellers = item.get("sellers") or []
    if not sellers:
        return None
    return sellers[0].get("commertialOffer") or {}


def parse_product(product, image_host):
    """Normaliza un producto VTEX a una o mas filas por SKU con EAN.

    Devuelve (rows, category_path). Cada row trae ean, nombre, descripcion,
    precio, promo, stock, marca e imagen; la tienda se agrega despues.
    """
    description = strip_html(product.get("description"))
    brand = (product.get("brand") or "").strip() or None
    categories = product.get("categories") or []
    category_path = categories[0].strip().strip("/") if categories else None
    promos = []
    for value in (product.get("clusterHighlights") or {}).values():
        label = re.sub(r"^\d+[\s_]+", "", str(value)).strip()
        if label and label not in promos:
            promos.append(label)
    promotion_names = " | ".join(promos) or None
    rows = []
    for item in product.get("items") or []:
        ean = (item.get("ean") or "").strip()
        if not ean:
            continue
        offer = _sku_offer(item)
        try:
            price = float(offer.get("Price")) if offer.get("Price") else None
        except (TypeError, ValueError):
            price = None
        try:
            list_price = (
                float(offer.get("ListPrice")) if offer.get("ListPrice") else None
            )
        except (TypeError, ValueError):
            list_price = None
        if price is None:
            continue  # sin precio no sirve para la app
        base = list_price or price
        promo = price if price < base else None
        try:
            available = int(offer.get("AvailableQuantity") or 0)
        except (TypeError, ValueError):
            available = 0
        images = item.get("images") or []
        image_url = images[0].get("imageUrl") if images else None
        if image_url and image_url.startswith("/"):
            image_url = f"https://{image_host}{image_url}"
        rows.append(
            {
                "ean": ean,
                "product_name": (
                    item.get("nameComplete") or item.get("name") or ""
                ).strip(),
                "description": description,
                "price": base,
                "promo_price": promo,
                "stock": available > 0,
                "stock_quantity": available,
                "brand": brand,
                "image_url": image_url,
                "category_path": category_path,
                "measurement_unit": (
                    (item.get("measurementUnit") or "").strip() or None
                ),
                "unit_multiplier": item.get("unitMultiplier"),
                "promotion_names": promotion_names,
            }
        )
    return rows, category_path


PRICE_COLUMNS = [
    "ean",
    "country_code",
    "region_id",
    "city_id",
    "store_id",
    "chain_id",
    "price",
    "promo_price",
    "currency",
    "stock",
    "stock_quantity",
    "last_updated",
    "source",
    "product_name",
    "description",
    "brand",
    "image_url",
    "category_path",
    "measurement_unit",
    "unit_multiplier",
    "promotion_names",
]


def scrape_chain(config, out_dir, limit_categories=None, limit_products=None,
                 max_pages=None, delay=0.35, slim=False):
    """Barrido completo de la cadena. Devuelve (n_stores, n_skus, n_rows).

    Escribe data/retailer_stores.json y data/prices.csv.gz con una fila
    por (ean, tienda); con slim=True, una fila por ean contra la tienda
    virtual CL_<cadena>_online (mismo precio, sin cartesiano).
    """
    import os

    os.makedirs(out_dir, exist_ok=True)
    source = "scrape_" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stamped = datetime.now(timezone.utc).isoformat()
    client = VTEXClient(config["account"], delay=delay)

    print(f"[{config['chain_id']}] locales desde {config['storefront']}/locales")
    html_text = client.fetch_page(config["storefront"] + "/locales")
    stores = parse_localities(html_text, config["chain_id"], config["chain_name"])
    if not stores:
        raise RuntimeError("no se encontraron locales en /locales")
    price_stores = stores
    if slim:
        price_stores = [online_store(config)]
        stores = stores + price_stores
    stores_path = os.path.join(out_dir, "retailer_stores.json")
    with open(stores_path, "w", encoding="utf-8") as fh:
        json.dump(stores, fh, ensure_ascii=False, indent=1)
    print(f"[{config['chain_id']}] {len(stores)} locales -> {stores_path}")

    print(f"[{config['chain_id']}] arbol de categorias")
    leaves = leaf_categories(client.category_tree())
    if limit_categories:
        leaves = leaves[:limit_categories]
    print(f"[{config['chain_id']}] {len(leaves)} categorias hoja")

    prices_path = os.path.join(out_dir, "prices.csv.gz")
    seen_products = set()
    seen_eans = set()
    n_skus = n_rows = 0
    with gzip.open(prices_path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PRICE_COLUMNS)
        writer.writeheader()
        failed = []
        for cat_fq, cat_path in leaves:
            start, pages = 0, 0
            try:
                while True:
                    # VTEX rechaza _to >= 50: paginas de 0-49, 50-99, ...
                    products = client.search_category(
                        cat_fq, start, start + PAGE_SIZE - 1)
                    if not products:
                        break
                    for product in products:
                        pid = str(product.get("productId"))
                        if pid in seen_products:
                            continue
                        seen_products.add(pid)
                        rows, _ = parse_product(product, config["image_host"])
                        for row in rows:
                            if row["ean"] in seen_eans:
                                continue
                            seen_eans.add(row["ean"])
                            n_skus += 1
                            if limit_products and n_skus > limit_products:
                                break
                            for store in price_stores:
                                writer.writerow(
                                    {
                                        "ean": row["ean"],
                                        "country_code": COUNTRY_CODE,
                                        "region_id": store["region_id"],
                                        "city_id": store["city_id"],
                                        "store_id": store["id"],
                                        "chain_id": config["chain_id"],
                                        "price": row["price"],
                                        "promo_price": row["promo_price"] or "",
                                        "currency": CURRENCY,
                                        "stock": str(row["stock"]).lower(),
                                        "stock_quantity": row["stock_quantity"],
                                        "last_updated": stamped,
                                        "source": source,
                                        "product_name": row["product_name"],
                                        "description": row["description"],
                                        "brand": row["brand"] or "",
                                        "image_url": row["image_url"] or "",
                                        "category_path": (
                                            row["category_path"] or ""
                                        ),
                                        "measurement_unit": (
                                            row["measurement_unit"] or ""
                                        ),
                                        "unit_multiplier": (
                                            row["unit_multiplier"]
                                            if row["unit_multiplier"] not in
                                            (None, "") else ""
                                        ),
                                        "promotion_names": (
                                            row["promotion_names"] or ""
                                        ),
                                    }
                                )
                                n_rows += 1
                        if limit_products and n_skus >= limit_products:
                            break
                    if limit_products and n_skus >= limit_products:
                        break
                    pages += 1
                    if max_pages and pages >= max_pages:
                        break
                    if len(products) < PAGE_SIZE:
                        break
                    start += PAGE_SIZE
            except RuntimeError as exc:
                # Una categoria con error (ej. HTTP 500 de VTEX) se omite
                # y la corrida sigue con las demas.
                failed.append(cat_path)
                print(f"[{config['chain_id']}] AVISO: categoria omitida "
                      f"{cat_path}: {exc}")
                continue
            if limit_products and n_skus >= limit_products:
                break
    print(f"[{config['chain_id']}] {n_skus} SKUs x {len(price_stores)} "
          f"tiendas = {n_rows} filas -> {prices_path}")
    if failed:
        print(f"[{config['chain_id']}] AVISO: {len(failed)} categorias "
              f"omitidas por error: {', '.join(failed[:10])}")
    return len(stores), n_skus, n_rows

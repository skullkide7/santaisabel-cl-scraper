# Scraper Santa Isabel Chile — EAN, precios y locales

Scraper público del catálogo de **Santa Isabel Chile** (Cencosud). Extrae
ciudad, país, EAN, precio, descripción, promociones y locales físicos, y
genera un dataset listo para cargar a Supabase con el esquema de
`schema.sql`.

Repo hermano: `jumbo-cl-scraper` (misma plataforma VTEX, mismo formato).

## Fuente de datos

- Catálogo: API VTEX pública de Cencosud
  (`santaisabel.vtexcommercestable.com.br/api/catalog_system/...`): árbol
  de categorías + búsqueda paginada por categoría. Entrega EAN, nombre,
  descripción, precio, precio lista, stock, marca, imagen, unidad de medida
  y clusters de promoción.
- Locales: página `/locales` de santaisabel.cl (id, nombre, dirección,
  región, ciudad y coordenadas).

No usa navegador ni credenciales.

## Uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Prueba acotada
python scrape_catalog.py --limit-categories 2 --max-pages 1

# Corrida completa (~1-2 h, escribe data/*.gz)
python scrape_catalog.py

# Cargar a Supabase (proyecto nuevo con schema.sql aplicado)
python upload_to_supabase.py --dry-run
export SUPABASE_URL="https://<ref>.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="<service_role>"
python upload_to_supabase.py
```

## Salidas (`data/`, no se commitean)

- `retailer_stores.json`: un objeto por local (`id` =
  `CL_santaisabel_<local>`, `chain_id`, `chain_name`, `country_code` =
  `CL`, `region_id`, `city_id`, `country_name` = Chile, `region_name`,
  `city_name`, `name`, `address`, `lat`, `lon`, ...).
- `prices.csv.gz`: una fila por (ean, tienda): `ean, country_code,
  region_id, city_id, store_id, chain_id, price, promo_price, currency
  (CLP), stock, stock_quantity, last_updated, source, product_name,
  description, brand, image_url, category_path, measurement_unit,
  unit_multiplier, promotion_names`.

## Limitaciones

- VTEX expone un único precio online nacional por SKU (un solo seller);
  el scraper lo asigna a todos los locales para mantener el formato
  fila-por-(ean, tienda). No son precios de góndola por local: Cencosud no
  los publica.
- Solo se conservan SKUs con EAN y precio.
- Uso responsable: respeta los términos de santaisabel.cl y no abuses del
  `--delay` (pausa entre requests, 0,35 s por defecto).

## Licencia

MIT.

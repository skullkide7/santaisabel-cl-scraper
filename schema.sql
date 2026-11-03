-- Esquema Supabase para la base chilena (Jumbo + Santa Isabel).
-- Base distinta a la de Nueva Zelanda; mismo contrato que consume la app
-- (lookup por EAN + busqueda por nombre) con columnas extra para Chile.
--
-- Uso: crear un proyecto nuevo en https://supabase.com/dashboard, abrir el
-- SQL Editor, pegar este archivo completo y ejecutar. Luego cargar con:
--   python upload_to_supabase.py   (en cada repo scraper)

create extension if not exists pg_trgm;

create table if not exists retailer_stores (
  id text primary key,
  chain_id text not null,
  chain_name text not null,
  country_code text not null default 'CL',
  region_id text,
  city_id text,
  country_name text not null default 'Chile',
  region_name text,
  city_name text,
  name text not null,
  address text,
  lat double precision,
  lon double precision,
  category text not null default 'supermarket',
  is_active boolean not null default true
);

create table if not exists product_prices (
  ean text not null,
  country_code text not null default 'CL',
  region_id text,
  city_id text,
  store_id text not null references retailer_stores (id) on delete cascade,
  chain_id text not null,
  price numeric not null,
  promo_price numeric,
  currency text not null default 'CLP',
  stock boolean not null default true,
  stock_quantity integer,
  last_updated timestamptz not null default now(),
  last_updated_local timestamptz,
  source text,
  scrapper_run_id text,
  product_name text,
  description text,
  brand text,
  image_url text,
  category_path text,
  measurement_unit text,
  unit_multiplier numeric,
  promotion_names text,
  primary key (ean, store_id)
);

create index if not exists product_prices_ean_idx on product_prices (ean);
create index if not exists product_prices_store_idx on product_prices (store_id);
-- La busqueda por nombre usa ilike con comodines; sin trigram da timeout.
create index if not exists product_prices_name_trgm
  on product_prices using gin (product_name gin_trgm_ops);

alter table retailer_stores enable row level security;
alter table product_prices enable row level security;

drop policy if exists "public read" on retailer_stores;
create policy "public read" on retailer_stores
  for select to anon, authenticated using (true);

drop policy if exists "public read" on product_prices;
create policy "public read" on product_prices
  for select to anon, authenticated using (true);

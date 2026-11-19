"""Recambios V0.2.8 independiente. Backend de catálogo y listas.
La aplicación Windows fija los datos bajo LOCALAPPDATA/Recambios/Datos.
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
import base64
import binascii
import hashlib
from datetime import datetime
from contextlib import contextmanager, closing
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import mimetypes
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import urljoin, urlsplit, unquote, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

VERSION = 'V0.2.8'
ON_DESKTOP_EXIT = None  # Instalador WebView2: cierre nativo si se solicita /api/salir.
HERE = Path(__file__).resolve().parent
DATA = Path(os.environ['INVENTARIO_PRO10_DATA_DIR']).expanduser().resolve() if os.environ.get('INVENTARIO_PRO10_DATA_DIR') else HERE / 'Datos'
DB = DATA / 'inventario.sqlite3'
PHOTOS = DATA / 'Fotos'
WEB = HERE / 'web'
TOKEN = secrets.token_urlsafe(32)
DB_LOCK = threading.RLock()
MAX_JSON = 8 * 1024 * 1024
MAX_PHOTO = 4 * 1024 * 1024
MAX_HTML = 2 * 1024 * 1024
MAX_BACKUP_ZIP = 60 * 1024 * 1024
MAX_UNCOMPRESSED_BACKUP = 250 * 1024 * 1024


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


@contextmanager
def connect():
    with closing(sqlite3.connect(DB, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        with db:
            yield db


def setup():
    DATA.mkdir(parents=True, exist_ok=True)
    PHOTOS.mkdir(parents=True, exist_ok=True)
    with DB_LOCK, connect() as db:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS inventarios (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            creado TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS articulos (
            id INTEGER PRIMARY KEY,
            inventario_id INTEGER NOT NULL REFERENCES inventarios(id),
            titulo TEXT NOT NULL,
            descripcion TEXT NOT NULL DEFAULT '',
            referencia TEXT NOT NULL DEFAULT '',
            referencia_tienda TEXT NOT NULL DEFAULT '',
            marca TEXT NOT NULL DEFAULT '',
            categoria TEXT NOT NULL DEFAULT '',
            observaciones TEXT NOT NULL DEFAULT '',
            foto TEXT NOT NULL DEFAULT '',
            controlar_stock INTEGER NOT NULL DEFAULT 0,
            cantidad INTEGER,
            creado TEXT NOT NULL,
            modificado TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_articulos_inventario ON articulos(inventario_id);
          CREATE TABLE IF NOT EXISTS enlaces (
            id INTEGER PRIMARY KEY,
            articulo_id INTEGER NOT NULL REFERENCES articulos(id) ON DELETE CASCADE,
            tienda TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL,
            principal INTEGER NOT NULL DEFAULT 0
          );
          CREATE TABLE IF NOT EXISTS listas_compra (
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL UNIQUE, creado TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS lista_lineas (
            id INTEGER PRIMARY KEY,
            lista_id INTEGER NOT NULL REFERENCES listas_compra(id) ON DELETE CASCADE,
            origen_inventario TEXT NOT NULL DEFAULT '',
            origen_inventario_id INTEGER,
            origen_articulo_id INTEGER,
            titulo TEXT NOT NULL,
            descripcion TEXT NOT NULL DEFAULT '',
            referencia TEXT NOT NULL DEFAULT '',
            referencia_tienda TEXT NOT NULL DEFAULT '',
            marca TEXT NOT NULL DEFAULT '',
            categoria TEXT NOT NULL DEFAULT '',
            observaciones TEXT NOT NULL DEFAULT '',
            foto TEXT NOT NULL DEFAULT '',
            enlaces_json TEXT NOT NULL DEFAULT '[]',
            cantidad INTEGER NOT NULL CHECK(cantidad >= 1 AND cantidad <= 100000),
            creado TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_lineas_lista ON lista_lineas(lista_id);
          CREATE TABLE IF NOT EXISTS ajustes (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
          );
        ''')
        # Una instalación nueva comienza sin ningún inventario.
        # Las instalaciones existentes conservan sus inventarios y artículos.
        # La selección se repara bajo demanda en get_active_inventory_id().
        db.commit()


def safe_photo_bytes(blob):
    if len(blob) > MAX_PHOTO or len(blob) < 12:
        raise ValueError('Fotografía vacía o demasiado grande (máximo 4 MB).')
    if blob.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if blob.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if blob.startswith(b'RIFF') and blob[8:12] == b'WEBP':
        return 'webp'
    raise ValueError('Formato de fotografía no admitido. Usa JPG, PNG o WebP.')


def decode_photo(value):
    if not value:
        return None
    if not isinstance(value, str) or not value.startswith('data:image/') or ',' not in value:
        raise ValueError('Fotografía incorrecta.')
    try:
        blob = base64.b64decode(value.split(',', 1)[1], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Fotografía dañada.')
    return blob, safe_photo_bytes(blob)


def check_external_url(url):
    if not isinstance(url, str) or len(url) > 2000:
        raise ValueError('URL demasiado larga o incorrecta.')
    p = urlsplit(url.strip())
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Utiliza una dirección HTTPS pública de una tienda.')
    if not re.fullmatch(r'[A-Za-z0-9.-]+', p.hostname) or '.' not in p.hostname:
        raise ValueError('Dominio de tienda no válido.')
    if len(p.hostname) > 253:
        raise ValueError('Dominio de tienda no válido.')
    return p.geturl()


def public_external_url(url):
    url = check_external_url(url)
    p = urlsplit(url)
    if p.hostname.endswith(('.local', '.internal', '.localhost', '.test', '.invalid', '.example')):
        raise ValueError('No se admiten direcciones de redes privadas.')
    try:
        addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError('No se pudo resolver la tienda. Comprueba Internet y la URL.')
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('No se permiten direcciones IP privadas o locales.')
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_external_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_external(url, limit=MAX_HTML):
    url = public_external_url(url)
    opener = build_opener(SafeRedirect)
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; Recambios/0.2)',
        'Accept': 'text/html,image/avif,image/webp,image/png,image/jpeg,*/*'
    })
    with opener.open(req, timeout=10) as res:
        mime = res.headers.get('Content-Type', '').lower()
        if not (mime.startswith('text/html') or mime.startswith('image/')):
            raise ValueError('La tienda ha devuelto un tipo de contenido no admitido.')
        chunk = res.read(limit + 1)
        if len(chunk) > limit:
            raise ValueError('El contenido de la tienda supera el tamaño permitido.')
        return chunk, mime, res.geturl()


class ProductParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = ''
        self.h1 = ''
        self.img = ''
        self.jsonld = []
        self.capture = None
        self.capture_text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            k = (a.get('property') or a.get('name') or a.get('itemprop') or '').lower()
            if k:
                self.meta.setdefault(k, a.get('content', ''))
        elif tag == 'script' and a.get('type') == 'application/ld+json':
            self.capture = 'jsonld'
            self.capture_text = []
        elif tag in ('title', 'h1') and not self.capture:
            self.capture = tag
            self.capture_text = []
        elif tag == 'img' and not self.img:
            source = a.get('data-src') or a.get('src') or ''
            if source and not source.startswith('data:'):
                if 'produkt' in str(a.get('class', '')).lower() or 'product' in str(a.get('class', '')).lower() or a.get('itemprop') == 'image':
                    self.img = source

    def handle_data(self, data):
        if self.capture:
            self.capture_text.append(data)

    def handle_endtag(self, tag):
        if tag == self.capture or (tag == 'script' and self.capture == 'jsonld'):
            text = ''.join(self.capture_text).strip()
            if self.capture == 'jsonld':
                self.jsonld.append(text)
            elif text:
                setattr(self, self.capture, text)
            self.capture = None
            self.capture_text = []


def find_product_json(d):
    if isinstance(d, list):
        for x in d:
            found = find_product_json(x)
            if found:
                return found
    if isinstance(d, dict):
        typ = d.get('@type', '')
        if typ == 'Product' or (isinstance(typ, list) and 'Product' in typ):
            return d
        if '@graph' in d:
            return find_product_json(d['@graph'])
    return {}


def import_product(url):
    html_data, ctype, actual = fetch_external(url)
    if not ctype.startswith('text/html'):
        raise ValueError('El enlace no es una página de producto.')
    html = html_data.decode('utf-8', 'replace')
    p = ProductParser()
    p.feed(html)
    product = {}
    for block in p.jsonld:
        try:
            product = find_product_json(json.loads(block))
        except (ValueError, TypeError):
            continue
        if product:
            break
    title = unescape(str(product.get('name') or p.meta.get('og:title') or p.h1 or p.title or '')).strip()
    title = re.sub(r'\s*[|]\s*RC.KleinKram.*$', '', title, flags=re.I)
    description = unescape(str(product.get('description') or p.meta.get('description') or '')).strip()
    description = re.sub('<[^>]+>', ' ', description)
    description = re.sub(r'\s+', ' ', description)[:1200]
    brand = product.get('brand', '')
    if isinstance(brand, dict):
        brand = brand.get('name', '')
    sku = str(product.get('sku') or p.meta.get('product:retailer_item_id') or '')
    if not sku:
        match = re.search(r'(?:Artikel-Nr\.?|Número de artículo|Art(?:í|i)culo Nº)\s*:?\s*</?[^>]*>?\s*([A-Za-z0-9_-]+)', html, re.I)
        if match:
            sku = match.group(1)
    if not sku:
        tail = unquote(urlsplit(actual).path.rstrip('/').split('/')[-1])
        if re.fullmatch('[a-zA-Z0-9_-]{3,40}', tail):
            sku = tail
    if not brand and title:
        brand = title.split()[0]
    reference = ''
    if str(brand).lower() == 'serpent':
        m = re.search(r'\bSerpent\s+(\d{5,7})\b', title, re.I)
        if m:
            reference = m.group(1)
    img = product.get('image') or p.meta.get('og:image') or p.meta.get('twitter:image') or p.meta.get('image') or p.img
    if isinstance(img, list):
        img = img[0] if img else ''
    if isinstance(img, dict):
        img = img.get('url', '')
    image_data = ''
    warning = ''
    if img:
        try:
            img_url = urljoin(actual, str(img))
            raw, _, _ = fetch_external(img_url, MAX_PHOTO)
            fmt = safe_photo_bytes(raw)
            image_data = f'data:image/{"jpeg" if fmt == "jpg" else fmt};base64,' + base64.b64encode(raw).decode('ascii')
        except (ValueError, OSError) as exc:
            warning = f'No se pudo descargar la fotografía automáticamente: {exc}'
    else:
        warning = 'No se encontró una fotografía en la ficha.'
    if not title:
        raise ValueError('No se encontró el nombre del producto. Puedes introducirlo manualmente.')
    return {
        'titulo': title[:200],
        'descripcion': description,
        'referencia': reference,
        'referencia_tienda': sku[:80],
        'marca': str(brand)[:80],
        'tienda': urlsplit(actual).hostname.removeprefix('www.'),
        'url': check_external_url(actual),
        'foto_data': image_data,
        'aviso': warning,
    }


def row_to_item(db, row):
    result = dict(row)
    result['foto_url'] = '/api/foto/' + row['foto'] if row['foto'] else ''
    result.pop('foto', None)
    result.pop('cantidad', None)
    result.pop('controlar_stock', None)
    result['enlaces'] = [dict(x) for x in db.execute(
        'SELECT id,tienda,url,principal FROM enlaces WHERE articulo_id=? ORDER BY principal DESC,id', (row['id'],))]
    return result


def str_field(x, key, maxsize=300):
    val = x.get(key, '')
    if not isinstance(val, str):
        raise ValueError(f'Campo incorrecto: {key}')
    return val.strip()[:maxsize]


def validate_inventory_name(name):
    if not isinstance(name, str):
        raise ValueError('Nombre de inventario incorrecto.')
    clean = re.sub(r'\s+', ' ', name).strip()
    if len(clean) < 1:
        raise ValueError('El nombre del inventario es obligatorio.')
    if len(clean) > 60:
        raise ValueError('El nombre del inventario es demasiado largo (máximo 60 caracteres).')
    return clean


def list_inventories(db=None):
    own = db is None
    if own:
        ctx = connect()
        db = ctx.__enter__()
    try:
        rows = db.execute('SELECT id,nombre,creado FROM inventarios ORDER BY lower(nombre), id').fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            ctx.__exit__(None, None, None)


def get_active_inventory_id(db):
    """Devuelve el inventario abierto o None cuando todavía no hay ninguno."""
    row = db.execute('SELECT valor FROM ajustes WHERE clave="inventario_activo"').fetchone()
    try:
        active = int(row['valor']) if row else None
    except (TypeError, ValueError):
        active = None
    if active is not None and db.execute('SELECT 1 FROM inventarios WHERE id=?', (active,)).fetchone():
        return active
    first = db.execute('SELECT id FROM inventarios ORDER BY lower(nombre), id LIMIT 1').fetchone()
    if first is None:
        db.execute('DELETE FROM ajustes WHERE clave="inventario_activo"')
        return None
    active = first['id']
    db.execute('INSERT OR REPLACE INTO ajustes(clave,valor) VALUES ("inventario_activo", ?)', (str(active),))
    return active


def set_active_inventory(db, inventory_id):
    if not db.execute('SELECT 1 FROM inventarios WHERE id=?', (inventory_id,)).fetchone():
        raise ValueError('El inventario ya no existe.')
    db.execute('INSERT OR REPLACE INTO ajustes(clave,valor) VALUES ("inventario_activo", ?)', (str(inventory_id),))


def get_inventory(db, inventory_id):
    row = db.execute('SELECT id,nombre,creado FROM inventarios WHERE id=?', (inventory_id,)).fetchone()
    if row is None:
        raise ValueError('El inventario ya no existe.')
    return dict(row)


def create_inventory(name):
    clean = validate_inventory_name(name)
    with DB_LOCK, connect() as db:
        try:
            cur = db.execute('INSERT INTO inventarios(nombre,creado) VALUES (?,?)', (clean, now()))
        except sqlite3.IntegrityError:
            raise ValueError('Ya existe un inventario con ese nombre.')
        set_active_inventory(db, cur.lastrowid)
        db.commit()
        return {'inventario': get_inventory(db, cur.lastrowid), 'inventarios': list_inventories(db), 'activo_id': cur.lastrowid}


def rename_inventory(inventory_id, name):
    clean = validate_inventory_name(name)
    with DB_LOCK, connect() as db:
        if not db.execute('SELECT 1 FROM inventarios WHERE id=?', (inventory_id,)).fetchone():
            raise ValueError('El inventario ya no existe.')
        try:
            db.execute('UPDATE inventarios SET nombre=? WHERE id=?', (clean, inventory_id))
        except sqlite3.IntegrityError:
            raise ValueError('Ya existe un inventario con ese nombre.')
        db.commit()
        return {'inventario': get_inventory(db, inventory_id), 'inventarios': list_inventories(db), 'activo_id': get_active_inventory_id(db)}


def delete_inventory(inventory_id):
    with DB_LOCK, connect() as db:
        all_ids = [r['id'] for r in db.execute('SELECT id FROM inventarios ORDER BY lower(nombre), id')]
        if inventory_id not in all_ids:
            raise ValueError('El inventario ya no existe.')
        photos = [r['foto'] for r in db.execute('SELECT foto FROM articulos WHERE inventario_id=? AND foto<>""', (inventory_id,))]
        article_ids = [r['id'] for r in db.execute('SELECT id FROM articulos WHERE inventario_id=?', (inventory_id,))]
        if article_ids:
            marks = ','.join('?' * len(article_ids))
            db.execute(f'DELETE FROM enlaces WHERE articulo_id IN ({marks})', article_ids)
        db.execute('DELETE FROM articulos WHERE inventario_id=?', (inventory_id,))
        db.execute('DELETE FROM inventarios WHERE id=?', (inventory_id,))
        # Si era el último, queda el catálogo vacío. Si había otros,
        # get_active_inventory_id selecciona uno de los supervivientes.
        get_active_inventory_id(db)
        db.commit()
    for name in photos:
        if name:
            (PHOTOS / name).unlink(missing_ok=True)
    with DB_LOCK, connect() as db:
        return {'inventarios': list_inventories(db), 'activo_id': get_active_inventory_id(db)}


def list_items(inventory_id):
    with DB_LOCK, connect() as db:
        inventory = get_inventory(db, inventory_id)
        rows = db.execute('SELECT * FROM articulos WHERE inventario_id=? ORDER BY id DESC', (inventory_id,)).fetchall()
        return {'inventario': inventory, 'articulos': [row_to_item(db, row) for row in rows]}


def save_item(inventory_id, data, item_id=None):
    if not isinstance(data, dict):
        raise ValueError('Datos de artículo incorrectos.')
    title = str_field(data, 'titulo', 200)
    if not title:
        raise ValueError('La descripción breve de la pieza es obligatoria.')
    fields = {x: str_field(data, x, cap) for x, cap in (
        ('descripcion', 2000), ('referencia', 80), ('referencia_tienda', 80), ('marca', 80),
        ('categoria', 100), ('observaciones', 2000))}
    links = data.get('enlaces', [])
    if not isinstance(links, list) or len(links) > 8:
        raise ValueError('Máximo ocho tiendas por artículo.')
    validated = []
    for link in links:
        if not isinstance(link, dict):
            raise ValueError('Enlace incorrecto.')
        url = str_field(link, 'url', 2000)
        if not url:
            continue
        validated.append((str_field(link, 'tienda', 100), check_external_url(url)))
    photo = decode_photo(data.get('foto_data'))
    remove_photo = data.get('quitar_foto') is True
    new_photo = ''
    if photo:
        blob, fmt = photo
        new_photo = f'{secrets.token_hex(16)}.{fmt}'
        (PHOTOS / new_photo).write_bytes(blob)
    old_photo = ''
    try:
        with DB_LOCK, connect() as db:
            get_inventory(db, inventory_id)
            if item_id is not None:
                row = db.execute('SELECT foto FROM articulos WHERE id=? AND inventario_id=?', (item_id, inventory_id)).fetchone()
                if row is None:
                    raise ValueError('El artículo ya no existe.')
                old_photo = row['foto']
                img = new_photo or ('' if remove_photo else old_photo)
                db.execute('''UPDATE articulos SET titulo=?,descripcion=?,referencia=?,referencia_tienda=?,
                    marca=?,categoria=?,observaciones=?,foto=?,modificado=? WHERE id=? AND inventario_id=?''',
                    (title, *fields.values(), img, now(), item_id, inventory_id))
            else:
                cur = db.execute('''INSERT INTO articulos(inventario_id,titulo,descripcion,referencia,
                    referencia_tienda,marca,categoria,observaciones,foto,creado,modificado)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                    (inventory_id, title, *fields.values(), new_photo, now(), now()))
                item_id = cur.lastrowid
            db.execute('DELETE FROM enlaces WHERE articulo_id=?', (item_id,))
            for j, (shop, url) in enumerate(validated):
                db.execute('INSERT INTO enlaces(articulo_id,tienda,url,principal) VALUES (?,?,?,?)',
                           (item_id, shop, url, int(j == 0)))
            db.commit()
            row = db.execute('SELECT * FROM articulos WHERE id=?', (item_id,)).fetchone()
            result = row_to_item(db, row)
    except Exception:
        if new_photo:
            (PHOTOS / new_photo).unlink(missing_ok=True)
        raise
    if old_photo and old_photo != result['foto_url'].removeprefix('/api/foto/'):
        (PHOTOS / old_photo).unlink(missing_ok=True)
    return result


def delete_item(inventory_id, item_id):
    with DB_LOCK, connect() as db:
        row = db.execute('SELECT foto FROM articulos WHERE id=? AND inventario_id=?', (item_id, inventory_id)).fetchone()
        if row is None:
            raise ValueError('El artículo ya no existe.')
        db.execute('DELETE FROM articulos WHERE id=? AND inventario_id=?', (item_id, inventory_id))
        db.commit()
    if row['foto']:
        (PHOTOS / row['foto']).unlink(missing_ok=True)



def validar_id(value, nombre='Identificador'):
    if type(value) is not int or value < 1:
        raise ValueError(f'{nombre} incorrecto.')
    return value


def validar_cantidad(value):
    if type(value) is not int or not (1 <= value <= 100000):
        raise ValueError('La cantidad de compra debe estar entre 1 y 100000.')
    return value


def list_shopping_lists():
    with DB_LOCK, connect() as db:
        return {'listas': [dict(r) for r in db.execute('''
            SELECT l.id,l.nombre,l.creado,COUNT(x.id) AS articulos,
                   COALESCE(SUM(x.cantidad),0) AS unidades
              FROM listas_compra l LEFT JOIN lista_lineas x ON x.lista_id=l.id
             GROUP BY l.id ORDER BY l.creado DESC,l.id DESC''')]}


def create_shopping_list(name):
    name = validate_inventory_name(name)
    with DB_LOCK, connect() as db:
        if db.execute('SELECT 1 FROM listas_compra WHERE lower(nombre)=lower(?)', (name,)).fetchone():
            raise ValueError('Ya existe una lista con ese nombre.')
        cur = db.execute('INSERT INTO listas_compra(nombre,creado) VALUES (?,?)', (name, now()))
        return {'id': cur.lastrowid, 'nombre': name}


def rename_shopping_list(lista_id, name):
    validar_id(lista_id, 'Lista')
    name = validate_inventory_name(name)
    with DB_LOCK, connect() as db:
        if not db.execute('SELECT 1 FROM listas_compra WHERE id=?', (lista_id,)).fetchone():
            raise ValueError('La lista ya no existe.')
        if db.execute('SELECT 1 FROM listas_compra WHERE lower(nombre)=lower(?) AND id<>?', (name, lista_id)).fetchone():
            raise ValueError('Ya existe una lista con ese nombre.')
        db.execute('UPDATE listas_compra SET nombre=? WHERE id=?', (name, lista_id))
        return {'ok': True}


def delete_shopping_list(lista_id):
    validar_id(lista_id, 'Lista')
    with DB_LOCK, connect() as db:
        photos = [r['foto'] for r in db.execute('SELECT foto FROM lista_lineas WHERE lista_id=? AND foto<>""', (lista_id,))]
        cur = db.execute('DELETE FROM listas_compra WHERE id=?', (lista_id,))
        if not cur.rowcount:
            raise ValueError('La lista ya no existe.')
    for photo in photos:
        (PHOTOS / photo).unlink(missing_ok=True)
    return {'ok': True}


def shopping_list_detail(lista_id):
    validar_id(lista_id, 'Lista')
    with DB_LOCK, connect() as db:
        lista = db.execute('SELECT * FROM listas_compra WHERE id=?', (lista_id,)).fetchone()
        if lista is None:
            raise ValueError('La lista ya no existe.')
        rows = []
        for row in db.execute('SELECT * FROM lista_lineas WHERE lista_id=? ORDER BY id DESC', (lista_id,)):
            entry = dict(row)
            entry['enlaces'] = json.loads(entry.pop('enlaces_json'))
            entry['foto_url'] = '/api/foto/' + entry.pop('foto') if row['foto'] else ''
            rows.append(entry)
        return {'lista': dict(lista), 'lineas': rows}


def add_shopping_line(lista_id, inventario_id, articulo_id, cantidad, url_compra=None):
    validar_id(lista_id, 'Lista')
    validar_id(inventario_id, 'Inventario')
    validar_id(articulo_id, 'Artículo')
    validar_cantidad(cantidad)
    photo_new = ''
    with DB_LOCK, connect() as db:
        if not db.execute('SELECT 1 FROM listas_compra WHERE id=?', (lista_id,)).fetchone():
            raise ValueError('La lista ya no existe.')
        inv = get_inventory(db, inventario_id)
        row = db.execute('SELECT * FROM articulos WHERE id=? AND inventario_id=?', (articulo_id, inventario_id)).fetchone()
        if row is None:
            raise ValueError('El artículo no existe en ese inventario.')
        links = [dict(tienda=r['tienda'], url=r['url']) for r in db.execute(
            'SELECT tienda,url FROM enlaces WHERE articulo_id=? ORDER BY principal DESC,id', (articulo_id,))]
        # Sólo se puede seleccionar una URL que pertenezca al artículo real.
        if url_compra is not None and not isinstance(url_compra, str):
            raise ValueError('La tienda seleccionada no es válida.')
        selected_url = url_compra if url_compra is not None else (links[0]['url'] if links else '')
        if selected_url and not any(link['url'] == selected_url for link in links):
            raise ValueError('La página elegida ya no pertenece a este recambio. Revisa las tiendas.')
        if links and not selected_url:
            raise ValueError('Elige la página web en la que quieres comprar este recambio.')
        # Dos tiendas distintas generan dos entradas independientes en una misma lista.
        # Una misma pieza y tienda suman cantidad, sin tocar el catálogo.
        for prior in db.execute('''SELECT id,cantidad,enlaces_json FROM lista_lineas WHERE lista_id=?
            AND origen_inventario_id=? AND origen_articulo_id=?''', (lista_id, inventario_id, articulo_id)):
            previous_links = json.loads(prior['enlaces_json'])
            previous_choice = next((link['url'] for link in previous_links if link.get('seleccionada')),
                                   previous_links[0]['url'] if previous_links else '')
            if previous_choice == selected_url:
                nueva = validar_cantidad(prior['cantidad'] + cantidad)
                db.execute('UPDATE lista_lineas SET cantidad=? WHERE id=?', (nueva, prior['id']))
                return {'ok': True, 'id': prior['id'], 'cantidad': nueva}
        for link in links:
            link['seleccionada'] = link['url'] == selected_url
        if row['foto']:
            source = PHOTOS / row['foto']
            if source.is_file():
                photo_new = secrets.token_hex(16) + source.suffix
                shutil.copyfile(source, PHOTOS / photo_new)
        try:
            cur = db.execute('''INSERT INTO lista_lineas(
                lista_id,origen_inventario,origen_inventario_id,origen_articulo_id,
                titulo,descripcion,referencia,referencia_tienda,marca,categoria,
                observaciones,foto,enlaces_json,cantidad,creado)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                lista_id, inv['nombre'], inventario_id, articulo_id,
                row['titulo'], row['descripcion'], row['referencia'], row['referencia_tienda'],
                row['marca'], row['categoria'], row['observaciones'], photo_new,
                json.dumps(links,ensure_ascii=False), cantidad, now()))
        except Exception:
            if photo_new:
                (PHOTOS / photo_new).unlink(missing_ok=True)
            raise
    return {'ok': True, 'id': cur.lastrowid, 'cantidad': cantidad}


def set_shopping_quantity(lista_id, linea_id, cantidad):
    validar_id(lista_id, 'Lista')
    validar_id(linea_id, 'Pieza')
    validar_cantidad(cantidad)
    with DB_LOCK, connect() as db:
        cur = db.execute('UPDATE lista_lineas SET cantidad=? WHERE id=? AND lista_id=?', (cantidad, linea_id, lista_id))
        if not cur.rowcount:
            raise ValueError('La pieza ya no está en esta lista.')
    return {'ok': True}


def remove_shopping_line(lista_id, linea_id):
    validar_id(lista_id, 'Lista')
    validar_id(linea_id, 'Pieza')
    with DB_LOCK, connect() as db:
        row = db.execute('SELECT foto FROM lista_lineas WHERE id=? AND lista_id=?', (linea_id, lista_id)).fetchone()
        if not row:
            raise ValueError('La pieza ya no está en esta lista.')
        db.execute('DELETE FROM lista_lineas WHERE id=? AND lista_id=?', (linea_id, lista_id))
    if row['foto']:
        (PHOTOS / row['foto']).unlink(missing_ok=True)
    return {'ok': True}


def archive_backup():
    memory = BytesIO()
    with DB_LOCK:
        snapshot = sqlite3.connect(':memory:')
        snapshot.row_factory = sqlite3.Row
        try:
            with connect() as db:
                db.backup(snapshot)
            items = [dict(r) for r in snapshot.execute('SELECT * FROM articulos ORDER BY id')]
            links = [dict(r) for r in snapshot.execute('SELECT * FROM enlaces ORDER BY id')]
            inventories = [dict(r) for r in snapshot.execute('SELECT * FROM inventarios ORDER BY id')]
            settings = [dict(r) for r in snapshot.execute('SELECT * FROM ajustes ORDER BY clave')]
            listas = [dict(r) for r in snapshot.execute('SELECT * FROM listas_compra ORDER BY id')]
            lista_lineas = [dict(r) for r in snapshot.execute('SELECT * FROM lista_lineas ORDER BY id')]
            sqlite_bytes = snapshot.serialize()
        finally:
            snapshot.close()
        with ZipFile(memory, 'w', ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr('inventario.sqlite3', sqlite_bytes)
            z.writestr('inventario.json', json.dumps({
                'formato': 3,
                'inventarios': inventories,
                'ajustes': settings,
                'articulos': items,
                'enlaces': links,
                'listas': listas,
                'lista_lineas': lista_lineas,
            }, ensure_ascii=False, indent=2))
            for img in sorted({r['foto'] for r in items if r['foto']} | {r['foto'] for r in lista_lineas if r['foto']}):
                f = PHOTOS / img
                if f.is_file():
                    z.write(f, 'Fotos/' + img)
    return memory.getvalue()



def inspect_backup(archive_bytes):
    """Validar ZIP sin alterar datos; usado tanto en vista previa como al aplicar."""
    if len(archive_bytes) > MAX_BACKUP_ZIP:
        raise ValueError('La copia es demasiado grande (máximo 60 MB).')
    photo_blobs = {}
    try:
        with ZipFile(BytesIO(archive_bytes)) as z:
            entries = z.infolist()
            if len(entries) > 15000 or sum(i.file_size for i in entries) > MAX_UNCOMPRESSED_BACKUP:
                raise ValueError('La copia contiene demasiados archivos o datos.')
            names = {i.filename for i in entries}
            if 'inventario.json' not in names:
                raise ValueError('Este ZIP no parece una copia de seguridad de Recambios.')
            if z.getinfo('inventario.json').file_size > 20 * 1024 * 1024:
                raise ValueError('La lista de recambios de esta copia es demasiado grande.')
            source = json.loads(z.read('inventario.json').decode('utf-8'))
            if not isinstance(source, dict) or source.get('formato') not in (1, 2, 3):
                raise ValueError('Formato de copia de seguridad no admitido.')
            inventories = source.get('inventarios')
            items = source.get('articulos')
            links = source.get('enlaces')
            if not (isinstance(inventories, list) and isinstance(items, list) and isinstance(links, list)):
                raise ValueError('La copia no contiene inventarios válidos.')
            if len(inventories) > 100 or len(items) > 10000 or len(links) > 80000:
                raise ValueError('La copia supera los límites admitidos.')
            # Una copia moderna puede incluir solo listas, sin inventarios.
            old_names = {}
            for inv in inventories:
                if not isinstance(inv, dict) or type(inv.get('id')) is not int or inv['id'] < 1 or inv['id'] in old_names:
                    raise ValueError('Los identificadores de inventario de la copia no son válidos.')
                old_names[inv['id']] = validate_inventory_name(inv.get('nombre'))
            source_items = {}
            for item in items:
                if not isinstance(item, dict) or type(item.get('id')) is not int or item['id'] < 1 or item['id'] in source_items:
                    raise ValueError('Hay artículos duplicados o incorrectos en la copia.')
                if item.get('inventario_id') not in old_names:
                    raise ValueError('Hay artículos sin inventario en la copia.')
                if not isinstance(item.get('titulo'), str) or not item['titulo'].strip():
                    raise ValueError('Hay artículos sin descripción en la copia.')
                source_items[item['id']] = item
            links_by_item = {}
            for link in links:
                if not isinstance(link, dict) or link.get('articulo_id') not in source_items:
                    raise ValueError('Hay enlaces sin artículo en la copia.')
                raw_url = link.get('url', '')
                if not isinstance(raw_url, str):
                    raise ValueError('Enlace incorrecto en la copia.')
                links_by_item.setdefault(link['articulo_id'], []).append((
                    str(link.get('tienda') or '')[:100], check_external_url(raw_url)))
                if len(links_by_item[link['articulo_id']]) > 8:
                    raise ValueError('Hay demasiados enlaces en un artículo de la copia.')
            if not isinstance(source.get('listas', []), list) or not isinstance(source.get('lista_lineas', []), list):
                raise ValueError('Las listas de la copia no son válidas.')
            source_lists = {}
            source_lines = {}
            for lst in source.get('listas', []):
                if not isinstance(lst, dict) or type(lst.get('id')) is not int or lst['id'] < 1 or lst['id'] in source_lists:
                    raise ValueError('La copia contiene listas incorrectas.')
                source_lists[lst['id']] = validate_inventory_name(lst.get('nombre'))
            if len(source_lists) > 300 or len({n.casefold() for n in source_lists.values()}) != len(source_lists):
                raise ValueError('La copia contiene demasiadas listas o nombres repetidos.')
            for line in source.get('lista_lineas', []):
                if not isinstance(line, dict) or type(line.get('id')) is not int or line['id'] < 1 or line['id'] in source_lines:
                    raise ValueError('La copia contiene piezas de lista incorrectas.')
                if line.get('lista_id') not in source_lists:
                    raise ValueError('Hay piezas de listas sin lista válida.')
                validar_cantidad(line.get('cantidad'))
                if not isinstance(line.get('titulo'), str) or not line['titulo'].strip():
                    raise ValueError('Hay una pieza de lista sin descripción.')
                for field in ('origen_inventario', 'descripcion', 'referencia', 'referencia_tienda',
                              'marca', 'categoria', 'observaciones', 'foto'):
                    if not isinstance(line.get(field, ''), str):
                        raise ValueError('Campo incorrecto en una lista.')
                links_raw = line.get('enlaces_json', '[]')
                if not isinstance(links_raw, str) or len(links_raw) > 20000:
                    raise ValueError('Enlaces de lista incorrectos.')
                try:
                    list_links = json.loads(links_raw)
                except (ValueError, TypeError):
                    raise ValueError('Enlaces de lista incorrectos.')
                if not isinstance(list_links, list) or len(list_links) > 8:
                    raise ValueError('La lista tiene demasiados enlaces.')
                for link in list_links:
                    if not isinstance(link, dict) or not isinstance(link.get('tienda'), str):
                        raise ValueError('Enlace de lista incorrecto.')
                    check_external_url(link.get('url', ''))
                source_lines[line['id']] = line
            if len(source_lines) > 20000:
                raise ValueError('Hay demasiadas piezas en las listas de la copia.')
            images = {item.get('foto', '') for item in items if item.get('foto', '')} | {line.get('foto', '') for line in source_lines.values() if line.get('foto', '')}
            for photo in images:
                if not isinstance(photo, str) or not re.fullmatch(r'[0-9a-f]{32}\.(?:jpg|png|webp)', photo):
                    raise ValueError('Hay una fotografía con nombre incorrecto en la copia.')
                zip_name = 'Fotos/' + photo
                if zip_name not in names:
                    raise ValueError('Falta la fotografía ' + photo + ' en la copia.')
                if z.getinfo(zip_name).file_size > MAX_PHOTO:
                    raise ValueError('Hay una fotografía demasiado grande en la copia.')
                blob = z.read(zip_name)
                actual_ext = safe_photo_bytes(blob)
                if actual_ext != photo.rsplit('.', 1)[1]:
                    raise ValueError('El formato de una fotografía no coincide con su extensión.')
                photo_blobs[photo] = blob
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise ValueError('El ZIP no es una copia válida o está dañado.') from exc

    if len({name.casefold() for name in old_names.values()}) != len(old_names):
        raise ValueError("La copia contiene inventarios con nombres repetidos.")
    return old_names, source_items, links_by_item, photo_blobs, source_lists, source_lines


def preview_backup(archive_bytes):
    old_names, source_items, _, _, source_lists, source_lines = inspect_backup(archive_bytes)
    with DB_LOCK, connect() as db:
        existing = {r['nombre'].casefold(): dict(r) for r in db.execute('SELECT id,nombre FROM inventarios')}
        counts = {r['inventario_id']: r['n'] for r in db.execute('SELECT inventario_id, COUNT(*) n FROM articulos GROUP BY inventario_id')}
        existing_lists = {r['nombre'].casefold(): dict(r) for r in db.execute('SELECT id,nombre FROM listas_compra')}
        preview = []
        for old_id, name in old_names.items():
            match = existing.get(name.casefold())
            preview.append({
                'id_origen': old_id,
                'nombre': name,
                'recambios': sum(1 for i in source_items.values() if i['inventario_id'] == old_id),
                'coincidencia': {'id': match['id'], 'nombre': match['nombre'],
                                'recambios': counts.get(match['id'], 0)} if match else None,
            })
    preview_lists = [{'id_origen': old_id, 'nombre': name,
                      'articulos': sum(1 for ln in source_lines.values() if ln['lista_id'] == old_id),
                      'coincidencia': existing_lists.get(name.casefold())}
                     for old_id, name in source_lists.items()]
    return {'ok': True, 'huella': hashlib.sha256(archive_bytes).hexdigest(),
            'inventarios': preview, 'listas': preview_lists}


def restore_backup(archive_bytes, options=None, huella=None):
    """Restaura con nombres exactos; los conflictos exigen decisión explícita.

    Los reemplazos son transaccionales. Se hace copia de seguridad automática de
    los inventarios previos si hay sustituciones y las fotos antiguas se borran
    únicamente después de confirmar la base de datos.
    """
    if not huella or hashlib.sha256(archive_bytes).hexdigest() != huella:
        raise ValueError('La copia ha cambiado; vuelve a seleccionarla.')
    old_names, source_items, links_by_item, photo_blobs, source_lists, source_lines = inspect_backup(archive_bytes)
    if not isinstance(options, dict):
        raise ValueError('Debes confirmar cómo recuperar los inventarios.')
    written = []
    old_photos_to_remove = set()
    overwritten = 0
    safety_copy = None
    with DB_LOCK:
        with connect() as db:
            existing = {r['nombre'].casefold(): dict(r) for r in db.execute('SELECT id,nombre FROM inventarios')}
            planned = {}
            reserved = set(existing)
            overwritten_targets = set()
            for source_id, original_name in old_names.items():
                conflict = existing.get(original_name.casefold())
                choice = options.get(str(source_id), {})
                if not isinstance(choice, dict):
                    raise ValueError('Hay una elección de restauración incorrecta.')
                mode = choice.get('accion', 'crear')
                if conflict:
                    if mode == 'sobrescribir':
                        if type(choice.get('destino_id')) is not int or choice['destino_id'] != conflict['id']:
                            raise ValueError('El inventario ha cambiado. Vuelve a cargar la copia.')
                        if conflict['id'] in overwritten_targets:
                            raise ValueError('No se puede sobrescribir dos veces el mismo inventario.')
                        overwritten_targets.add(conflict['id'])
                        planned[source_id] = (mode, conflict['nombre'], conflict['id'])
                    elif mode == 'renombrar':
                        new_name = validate_inventory_name(choice.get('nombre', ''))
                        if new_name.casefold() in reserved:
                            raise ValueError(f'El nombre «{new_name}» ya existe. Elige uno diferente.')
                        reserved.add(new_name.casefold())
                        planned[source_id] = ('crear', new_name, None)
                    else:
                        raise ValueError(f'El inventario «{original_name}» ya existe. Elige sobrescribir o cambiar nombre.')
                else:
                    if mode != 'crear':
                        raise ValueError('La lista de inventarios ha cambiado. Vuelve a cargar la copia.')
                    if original_name.casefold() in reserved:
                        raise ValueError(f'El nombre «{original_name}» ya está ocupado.')
                    reserved.add(original_name.casefold())
                    planned[source_id] = ('crear', original_name, None)
            existing_lists = {r['nombre'].casefold(): dict(r) for r in db.execute('SELECT id,nombre FROM listas_compra')}
            planned_lists = {}
            reserved_lists = set(existing_lists)
            for source_id, original_name in source_lists.items():
                conflict = existing_lists.get(original_name.casefold())
                choice = options.get('lista:' + str(source_id), {})
                if not isinstance(choice, dict):
                    raise ValueError('Elección de recuperación de lista incorrecta.')
                mode = choice.get('accion', 'crear')
                if conflict:
                    if mode == 'sobrescribir' and type(choice.get('destino_id')) is int and choice['destino_id'] == conflict['id']:
                        planned_lists[source_id] = ('sobrescribir', conflict['nombre'], conflict['id'])
                        overwritten_targets.add(('lista', conflict['id']))
                    elif mode == 'renombrar':
                        new_name = validate_inventory_name(choice.get('nombre'))
                        if new_name.casefold() in reserved_lists:
                            raise ValueError(f'La lista «{new_name}» ya existe.')
                        reserved_lists.add(new_name.casefold())
                        planned_lists[source_id] = ('crear', new_name, None)
                    else:
                        raise ValueError(f'La lista «{original_name}» ya existe. Elige sobrescribir o cambiar nombre.')
                else:
                    if mode != 'crear' or original_name.casefold() in reserved_lists:
                        raise ValueError('El nombre de una lista ha cambiado. Vuelve a cargar la copia.')
                    reserved_lists.add(original_name.casefold())
                    planned_lists[source_id] = ('crear', original_name, None)
            # La copia se genera antes de borrar ningún artículo previo.
            if overwritten_targets:
                backup_dir = DATA / 'Copias_antes_de_sobrescribir'
                backup_dir.mkdir(parents=True, exist_ok=True)
                safety_copy = backup_dir / ('Recambios_antes_de_sobrescribir_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.zip')
                backup_bytes = archive_backup()
                safety_copy.write_bytes(backup_bytes)
            try:
                mapping = {}
                for source_id, (mode, name, target) in planned.items():
                    if mode == 'sobrescribir':
                        rows = db.execute('SELECT id,foto FROM articulos WHERE inventario_id=?', (target,)).fetchall()
                        old_photos_to_remove.update(r['foto'] for r in rows if r['foto'])
                        # Enlaces se borran por FK CASCADE al eliminar artículos.
                        db.execute('DELETE FROM articulos WHERE inventario_id=?', (target,))
                        mapping[source_id] = target
                        overwritten += 1
                    else:
                        cur = db.execute('INSERT INTO inventarios(nombre,creado) VALUES (?,?)', (name, now()))
                        mapping[source_id] = cur.lastrowid
                list_mapping = {}
                for source_id, (mode, name, target) in planned_lists.items():
                    if mode == 'sobrescribir':
                        rows = db.execute('SELECT foto FROM lista_lineas WHERE lista_id=?', (target,)).fetchall()
                        old_photos_to_remove.update(r['foto'] for r in rows if r['foto'])
                        db.execute('DELETE FROM lista_lineas WHERE lista_id=?', (target,))
                        list_mapping[source_id] = target
                    else:
                        cur = db.execute('INSERT INTO listas_compra(nombre,creado) VALUES (?,?)', (name, now()))
                        list_mapping[source_id] = cur.lastrowid
                new_photos = {}
                for original_photo, content in photo_blobs.items():
                    ext = original_photo.rsplit('.', 1)[1]
                    generated = secrets.token_hex(16) + '.' + ext
                    (PHOTOS / generated).write_bytes(content)
                    written.append(generated)
                    new_photos[original_photo] = generated
                for old_item_id, item in source_items.items():
                    fields = [item.get(key, '') for key in (
                        'titulo', 'descripcion', 'referencia', 'referencia_tienda', 'marca', 'categoria', 'observaciones')]
                    if any(not isinstance(v, str) for v in fields):
                        raise ValueError('Hay datos de artículo incorrectos en la copia.')
                    title, description, ref, shop_ref, brand, cat, notes = fields
                    stamp = now()
                    cur = db.execute("""INSERT INTO articulos(inventario_id,titulo,descripcion,referencia,
                        referencia_tienda,marca,categoria,observaciones,foto,creado,modificado)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                        mapping[item['inventario_id']], title[:200], description[:2000], ref[:80],
                        shop_ref[:80], brand[:80], cat[:100], notes[:2000],
                        new_photos.get(item.get('foto', ''), ''), stamp, stamp))
                    for j, (shop, url) in enumerate(links_by_item.get(old_item_id, [])):
                        db.execute('INSERT INTO enlaces(articulo_id,tienda,url,principal) VALUES (?,?,?,?)',
                                   (cur.lastrowid, shop, url, int(j == 0)))
                for line in source_lines.values():
                    keys = ('titulo', 'descripcion', 'referencia', 'referencia_tienda',
                            'marca', 'categoria', 'observaciones', 'origen_inventario')
                    fields = [line.get(k, '') for k in keys]
                    if any(not isinstance(field, str) for field in fields):
                        raise ValueError('Hay campos incorrectos en una lista de la copia.')
                    db.execute('''INSERT INTO lista_lineas(lista_id, origen_inventario,
                        origen_inventario_id, origen_articulo_id, titulo, descripcion, referencia,
                        referencia_tienda, marca, categoria, observaciones, foto,
                        enlaces_json, cantidad, creado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                        list_mapping[line['lista_id']], fields[7][:60], None, None,
                        fields[0][:200], fields[1][:2000], fields[2][:80], fields[3][:80],
                        fields[4][:80], fields[5][:100], fields[6][:2000],
                        new_photos.get(line.get('foto', ''), ''), line.get('enlaces_json', '[]'),
                        line['cantidad'], now()))
                if mapping:
                    set_active_inventory(db, next(iter(mapping.values())))
                db.commit()
            except Exception:
                db.rollback()
                for photo in written:
                    (PHOTOS / photo).unlink(missing_ok=True)
                raise
            # Borrar fotos antiguas solo después del COMMIT; si falla el borrado
            # se dejarán archivos huérfanos, pero los datos seguirán intactos.
            for photo in old_photos_to_remove:
                try:
                    (PHOTOS / photo).unlink(missing_ok=True)
                except OSError:
                    pass
            return {
                'ok': True, 'inventarios_importados': len(old_names),
                'inventarios_sobrescritos': overwritten,
                'articulos_importados': len(source_items),
                'listas_importadas': len(source_lists),
                'piezas_lista_importadas': len(source_lines),
                'copia_previa': str(safety_copy) if safety_copy else '',
                'activo_id': get_active_inventory_id(db),
                'inventarios': list_inventories(db),
            }


class Handler(BaseHTTPRequestHandler):
    server_version = 'Recambios/0.2.8'

    def log_message(self, fmt, *args):
        pass

    def respond(self, payload, status=200, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                         "connect-src 'self'; frame-ancestors http://127.0.0.1:*; object-src 'none'; base-uri 'none'")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def route(self):
        return urlsplit(self.path).path

    def query(self):
        return parse_qs(urlsplit(self.path).query)

    def int_query(self, key):
        values = self.query().get(key)
        if not values:
            return None
        try:
            value = int(values[0])
        except Exception:
            raise ValueError('Parámetro incorrecto.')
        if value < 1:
            raise ValueError('Parámetro incorrecto.')
        return value

    def do_GET(self):
        if not self.authorized_host():
            return self.respond({'error': 'Host no permitido'}, 403)
        route = self.route()
        try:
            if route == '/api/health':
                return self.respond({'ok': True, 'version': VERSION})
            if route == '/api/inventarios':
                with DB_LOCK, connect() as db:
                    return self.respond({'inventarios': list_inventories(db), 'activo_id': get_active_inventory_id(db)})
            if route == '/api/listas':
                return self.respond(list_shopping_lists())
            if route == '/api/listas/detalle':
                return self.respond(shopping_list_detail(self.int_query('id')))
            if route == '/api/articulos':
                inventory_id = self.int_query('inventario_id')
                with DB_LOCK, connect() as db:
                    if inventory_id is None:
                        inventory_id = get_active_inventory_id(db)
                if inventory_id is None:
                    return self.respond({'inventario': None, 'articulos': []})
                return self.respond(list_items(inventory_id))
            if route == '/api/copia':
                filename = 'Recambios_' + datetime.now().strftime('%Y%m%d_%H%M') + '.zip'
                return self.respond(archive_backup(), ctype='application/zip', extra={
                    'Content-Disposition': f'attachment; filename="{filename}"'})
            if route.startswith('/api/foto/'):
                name = route.split('/')[-1]
                if not re.fullmatch(r'[0-9a-f]{32}\.(?:jpg|png|webp)', name):
                    return self.respond({'error': 'Foto no encontrada'}, 404)
                path = PHOTOS / name
                if not path.is_file():
                    return self.respond({'error': 'Foto no encontrada'}, 404)
                return self.respond(path.read_bytes(), ctype=mimetypes.guess_type(path.name)[0] or 'image/jpeg')
            files = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}
            if route not in files:
                return self.respond({'error': 'No encontrado'}, 404)
            path = WEB / files[route]
            raw = path.read_bytes()
            if route in ('/', '/index.html'):
                raw = raw.replace(b'__INV_TOKEN__', TOKEN.encode())
            content = {
                'index.html': 'text/html; charset=utf-8',
                'app.js': 'application/javascript; charset=utf-8',
                'styles.css': 'text/css; charset=utf-8'}[files[route]]
            return self.respond(raw, ctype=content)
        except (ValueError, UnicodeError) as exc:
            return self.respond({'error': str(exc)}, 400)

    def do_POST(self):
        if not self.authorized_host():
            return self.respond({'error': 'Host no permitido'}, 403)
        if self.headers.get('Origin') != f'http://{self.headers.get("Host", "")}' or self.headers.get('X-Inventario-Token') != TOKEN:
            return self.respond({'error': 'Acceso no autorizado'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > MAX_BACKUP_ZIP:
                raise ValueError('Solicitud demasiado grande.')
            route = self.route()
            if route in ('/api/previsualizar-copia', '/api/cargar-copia'):
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('No se ha recibido el archivo completo.')
                if route == '/api/previsualizar-copia':
                    return self.respond(preview_backup(raw))
                query = self.query()
                try:
                    options = json.loads(query.get('opciones', [''])[0])
                    huella = query.get('huella', [''])[0]
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ValueError('Decisiones de restauración incorrectas.') from exc
                return self.respond(restore_backup(raw, options, huella))
            if length > MAX_JSON:
                raise ValueError('Solicitud demasiado grande.')
            data = json.loads(self.rfile.read(length))
            if route == '/api/salir':
                self.respond({'ok': True, 'mensaje': 'Programa cerrado.'})
                if ON_DESKTOP_EXIT is not None:
                    # En escritorio hay que cerrar también la ventana WebView2.
                    threading.Timer(0.3, ON_DESKTOP_EXIT).start()
                else:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if route == '/api/listas/nueva':
                result = create_shopping_list(str_field(data, 'nombre', 60))
            elif route == '/api/listas/renombrar':
                result = rename_shopping_list(data.get('id'), str_field(data, 'nombre', 60))
            elif route == '/api/listas/eliminar':
                result = delete_shopping_list(data.get('id'))
            elif route == '/api/listas/anadir':
                result = add_shopping_line(data.get('lista_id'), data.get('inventario_id'),
                                           data.get('articulo_id'), data.get('cantidad'), data.get('url_compra'))
            elif route == '/api/listas/cantidad':
                result = set_shopping_quantity(data.get('lista_id'), data.get('linea_id'), data.get('cantidad'))
            elif route == '/api/listas/quitar':
                result = remove_shopping_line(data.get('lista_id'), data.get('linea_id'))
            elif route == '/api/importar':
                result = import_product(str_field(data, 'url', 2000))
            elif route == '/api/guardar':
                ident = data.get('id')
                inventory_id = data.get('inventario_id')
                if not isinstance(inventory_id, int) or inventory_id < 1:
                    raise ValueError('Inventario incorrecto.')
                if ident is not None and (not isinstance(ident, int) or ident < 1):
                    raise ValueError('ID incorrecto.')
                result = {'articulo': save_item(inventory_id, data, ident)}
            elif route == '/api/eliminar':
                ident = data.get('id')
                inventory_id = data.get('inventario_id')
                if not isinstance(inventory_id, int) or inventory_id < 1:
                    raise ValueError('Inventario incorrecto.')
                if not isinstance(ident, int) or ident < 1:
                    raise ValueError('ID incorrecto.')
                delete_item(inventory_id, ident)
                result = {'ok': True}
            elif route == '/api/inventarios/activar':
                inventory_id = data.get('id')
                if not isinstance(inventory_id, int) or inventory_id < 1:
                    raise ValueError('Inventario incorrecto.')
                with DB_LOCK, connect() as db:
                    set_active_inventory(db, inventory_id)
                    db.commit()
                    result = {'activo_id': get_active_inventory_id(db), 'inventarios': list_inventories(db)}
            elif route == '/api/inventarios/nuevo':
                result = create_inventory(str_field(data, 'nombre', 60))
            elif route == '/api/inventarios/renombrar':
                inventory_id = data.get('id')
                if not isinstance(inventory_id, int) or inventory_id < 1:
                    raise ValueError('Inventario incorrecto.')
                result = rename_inventory(inventory_id, str_field(data, 'nombre', 60))
            elif route == '/api/inventarios/eliminar':
                inventory_id = data.get('id')
                if not isinstance(inventory_id, int) or inventory_id < 1:
                    raise ValueError('Inventario incorrecto.')
                result = delete_inventory(inventory_id)
            else:
                return self.respond({'error': 'Ruta desconocida'}, 404)
            return self.respond(result)
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            return self.respond({'error': str(exc)}, 400)
        except (OSError, TimeoutError) as exc:
            return self.respond({'error': f'No se pudo contactar con la tienda: {exc}'}, 502)
        except Exception as exc:
            print('Recambios: error en petición:', type(exc).__name__, str(exc), flush=True)
            return self.respond({'error': 'Error interno. Consulta la ventana del programa.'}, 500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--open-browser', action='store_true', help='Abrir la interfaz al iniciar')
    args = parser.parse_args()
    if args.host != '127.0.0.1':
        parser.error('Solo se admite el servidor local.')
    if sys.version_info < (3, 11):
        parser.error('Se necesita Python 3.11 o posterior para ejecutar Recambios.')
    setup()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Recambios {VERSION} en {url}', flush=True)
    print('Para cerrar: botón «Cerrar programa» de la interfaz o Ctrl+C en esta ventana.', flush=True)
    if args.open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

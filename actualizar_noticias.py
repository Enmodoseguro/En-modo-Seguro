#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 EN MODO SEGURO — EL MOTOR (actualizador de noticias)
============================================================
Este programa se ejecuta TODOS LOS DÍAS, junta las novedades del
mercado asegurador y escribe el archivo `noticias.json`, que la web
(index.html) lee para mostrar las noticias.

Fuentes:
  1) Feeds RSS de portales del seguro  -> lo más confiable.
  2) Páginas de la SSN y la SRT        -> scraping "best-effort"
                                          (selectores ajustables).
  3) Boletín Oficial                   -> ver NOTA al final del archivo.

Uso:
    pip install -r requirements.txt
    python actualizar_noticias.py

Resultado:
    noticias.json  (en la misma carpeta)
"""

import json
import re
import sys
import html
import datetime
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# ------------------------------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------------------------------
SALIDA = "noticias.json"          # archivo que lee la web
MAX_NOTICIAS = 24                 # cuántas noticias guardar
TIMEOUT = 20                      # segundos máximos por pedido
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "application/rss+xml, application/xml, text/xml, application/atom+xml, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

# --- 1) Portales del seguro con RSS -------------------------------
# En sitios WordPress el feed suele estar en <dominio>/feed/.
# Agregá o quitá fuentes libremente.
FEEDS_RSS = [
    {"nombre": "Mercado y Seguros",   "url": "https://mercadosyseguros.com/feed/"},
    {"nombre": "100% Seguro",         "url": "https://100seguro.com.ar/feed/"},
    {"nombre": "El Seguro en Acción", "url": "https://elseguroenaccion.com.ar/feed/"},
    {"nombre": "Tiempo de Seguros",   "url": "https://www.tiempodeseguros.com.ar/feed/"},
    {"nombre": "Informe Operadores",  "url": "https://www.informeoperadores.com.ar/feed/"},
    {"nombre": "NBS",                 "url": "https://nbs.ar/feed/"},
    {"nombre": "Onda Seguro",         "url": "https://www.ondaseguro.com.ar/feed/"},
    # {"nombre": "Todo Riesgo",       "url": "https://www.todoriesgo.com.ar/feed/"},
]

# --- 2) Páginas de organismos para scrapear -----------------------
# "best-effort": si el sitio cambia su HTML, ajustá los selectores CSS.
# Dejalo vacío [] para usar solo RSS, o descomentá los ejemplos y
# ajustá la URL del listado de noticias y los selectores.
PAGINAS_HTML = [
    # {
    #     "nombre": "SSN",
    #     "url": "https://www.argentina.gob.ar/superintendencia-de-seguros/noticias",
    #     "item": "article a, .listado-noticias li a",   # cada noticia
    #     "titulo_attr": "text",                          # 'text' o un atributo
    # },
    # {
    #     "nombre": "SRT",
    #     "url": "https://www.argentina.gob.ar/srt/prensa",
    #     "item": "article a, .views-row a",
    #     "titulo_attr": "text",
    # },
]

# --- Clasificación por palabras clave -----------------------------
CATEGORIAS = [
    ("Regulación", ["ssn", "srt", "resol", "superintendencia", "normativa",
                    "reglament", "boletín oficial", "riesgos del trabajo"]),
    ("Innovación", ["insurtech", "tecnolog", "digital", "innova",
                    "datos abiertos", "inteligencia artificial", "siep"]),
    ("Mercado",    ["compañ", "aseguradora", " art ", "ceo", "fusión",
                    "ranking", "primaje", "productor", "nombramiento"]),
]


def categorizar(texto: str) -> str:
    t = (texto or "").lower()
    for categoria, claves in CATEGORIAS:
        if any(k in t for k in claves):
            return categoria
    return "Mercado"


def limpiar(texto: str, n: int = 220) -> str:
    """Quita HTML, normaliza espacios y recorta."""
    if not texto:
        return ""
    txt = BeautifulSoup(texto, "html.parser").get_text(" ")
    txt = re.sub(r"\s+", " ", html.unescape(txt)).strip()
    if len(txt) > n:
        txt = txt[:n].rsplit(" ", 1)[0] + "…"
    return txt


def a_iso(valor: str) -> str:
    """Convierte cualquier fecha a 'AAAA-MM-DD' (o '' si no se puede)."""
    if not valor:
        return ""
    try:
        return dateparser.parse(valor).date().isoformat()
    except Exception:
        return ""


def extraer_imagen(entry) -> str:
    """Busca la imagen (miniatura) de una noticia dentro del feed."""
    # 1) media:thumbnail
    thumbs = entry.get("media_thumbnail") or []
    if thumbs and thumbs[0].get("url"):
        return thumbs[0]["url"]
    # 2) media:content
    for m in entry.get("media_content") or []:
        url = m.get("url", "")
        tipo = (str(m.get("type", "")) + str(m.get("medium", ""))).lower()
        if url and ("image" in tipo or url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp"))):
            return url
    # 3) enclosures (archivos adjuntos)
    for enc in entry.get("enclosures") or []:
        if "image" in str(enc.get("type", "")).lower() and enc.get("href"):
            return enc["href"]
    # 4) primera imagen dentro del contenido o el resumen
    blob = ""
    if entry.get("content"):
        blob = entry["content"][0].get("value", "")
    blob = blob or entry.get("summary", "") or entry.get("description", "")
    if blob:
        img = BeautifulSoup(blob, "html.parser").find("img")
        if img and img.get("src"):
            return img["src"]
    return ""


def _bajar(url: str) -> bytes:
    """Descarga una URL con reintentos y headers de navegador. Devuelve bytes o lanza excepción."""
    ultimo = "sin respuesta"
    for intento in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            print(f"        GET {url} -> HTTP {r.status_code} ({len(r.content)} bytes)")
            if r.status_code == 200 and r.content:
                return r.content
            ultimo = f"HTTP {r.status_code}"
        except Exception as ex:
            ultimo = str(ex)
            print(f"        intento {intento + 1} de {url} falló: {ex}")
    raise RuntimeError(ultimo)


def _variantes(url: str) -> list:
    """Devuelve la URL dada y algunas variantes típicas de feed, por si /feed/ no es la correcta."""
    base = url.rstrip("/")
    raiz = base[:-5] if base.endswith("/feed") else base
    candidatas = [url, raiz + "/feed/", raiz + "/?feed=rss2", raiz + "/feed/rss/", raiz + "/rss"]
    out = []
    for v in candidatas:
        if v not in out:
            out.append(v)
    return out


def desde_rss(fuente: dict) -> list:
    """Lee un feed RSS (probando variantes) y devuelve una lista de noticias normalizadas."""
    d = None
    for u in _variantes(fuente["url"]):
        try:
            contenido = _bajar(u)
        except Exception as ex:
            print(f"        {u}: {ex}")
            continue
        parsed = feedparser.parse(contenido)
        if parsed.entries:
            d = parsed
            break
    if d is None:
        # Último recurso: que feedparser lo intente por su cuenta.
        d = feedparser.parse(fuente["url"], request_headers=HEADERS)

    items = []
    for e in d.entries:
        titulo = (e.get("title") or "").strip()
        if not titulo:
            continue
        resumen = limpiar(e.get("summary") or e.get("description") or "")
        fecha = a_iso(e.get("published") or e.get("updated") or "")
        items.append({
            "titulo": titulo,
            "resumen": resumen,
            "fuente": fuente["nombre"],
            "categoria": categorizar(titulo + " " + resumen),
            "fecha": fecha,
            "url": e.get("link") or "",
            "imagen": extraer_imagen(e),
        })
    return items


def desde_html(pagina: dict) -> list:
    """Scrapea un listado de noticias de una página (best-effort)."""
    items = []
    r = requests.get(pagina["url"], headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for el in soup.select(pagina["item"])[:15]:
        titulo = el.get_text(" ").strip()
        if not titulo or len(titulo) < 10:
            continue
        href = el.get("href", "")
        link = urljoin(pagina["url"], href) if href else ""
        items.append({
            "titulo": titulo,
            "resumen": "",
            "fuente": pagina["nombre"],
            "categoria": categorizar(titulo + " " + pagina["nombre"]),
            "fecha": "",
            "url": link,
            "imagen": "",
        })
    return items


def main():
    todas = []

    # 1) RSS (la base confiable)
    for fuente in FEEDS_RSS:
        try:
            nuevas = desde_rss(fuente)
            todas += nuevas
            print(f"[OK]    {fuente['nombre']}: {len(nuevas)} noticias")
        except Exception as ex:
            print(f"[ERROR] {fuente['nombre']}: {ex}", file=sys.stderr)

    # 2) Scraping de organismos (best-effort)
    for pagina in PAGINAS_HTML:
        try:
            nuevas = desde_html(pagina)
            todas += nuevas
            print(f"[OK]    {pagina['nombre']}: {len(nuevas)} noticias")
        except Exception as ex:
            print(f"[ERROR] {pagina['nombre']}: {ex}", file=sys.stderr)

    # Quitar duplicados por título
    vistas, unicas = set(), []
    for it in todas:
        clave = it["titulo"].lower()
        if clave in vistas:
            continue
        vistas.add(clave)
        unicas.append(it)

    # Ordenar por fecha (más nuevas primero; las sin fecha al final)
    unicas.sort(key=lambda x: x["fecha"] or "0000-00-00", reverse=True)
    unicas = unicas[:MAX_NOTICIAS]

    # Hora de Argentina (UTC-3), aunque el robot corra en un servidor de otra zona
    ar = datetime.timezone(datetime.timedelta(hours=-3))
    salida = {
        "actualizado": datetime.datetime.now(ar).isoformat(timespec="minutes"),
        "total": len(unicas),
        "noticias": unicas,
    }
    with open(SALIDA, "w", encoding="utf-8") as fp:
        json.dump(salida, fp, ensure_ascii=False, indent=2)

    print(f"\n✓ {len(unicas)} noticias guardadas en '{SALIDA}'")
    if not unicas:
        print("  (Sin resultados: revisá conexión o las URLs de las fuentes.)")


if __name__ == "__main__":
    main()

# ==================================================================
# NOTA sobre el BOLETÍN OFICIAL y la SSN/SRT
# ------------------------------------------------------------------
# - Los feeds RSS de los portales del seguro ya traen, en la práctica,
#   gran parte de las resoluciones y noticias de la SSN y la SRT,
#   porque esos medios las cubren.
# - Scrapear directamente argentina.gob.ar (SSN/SRT) es posible pero
#   FRÁGIL: si cambian el HTML, hay que actualizar los selectores de
#   PAGINAS_HTML. Por eso vienen como ejemplo comentado.
# - El Boletín Oficial (boletinoficial.gob.ar) carga el contenido con
#   JavaScript y conviene usar su API/servicio de avisos, lo cual es un
#   paso más avanzado. Si querés, lo armamos aparte.
# ==================================================================

"""
Conector de barrido TrendTrack (trendtrack.io) para la biblioteca de referentes:
anuncios de Meta (Facebook/Instagram) espiados por TrendTrack, con el mismo
contrato que `atria.py` y `apify_adlibrary.py` (`estimar`, `probar`, `traer`).

Lo que SÍ está confirmado por la documentación pública de la API
(docs.trendtrack.io, leída el 2026-09-30 a través de sus resúmenes: desde
este entorno el dominio está bloqueado, así que nunca vimos una respuesta real):

- Base `https://api.trendtrack.io`; autenticación `Authorization: Bearer <llave>`
  (no existe `x-api-key`). Hace falta el plan Pro o superior.
- `GET /v1/me` no consume créditos: sirve para probar la llave.
- `GET /v1/ads` exige `search`; paginación `limit` + `offset`; respuesta
  `{data, requestId}` más un bloque de paginación. `/v1/ads` es solo Meta.
  Filtros avanzados (estado, tipo de medio, orden) viven en `POST /v1/ads/query`,
  cuyo cuerpo no conocemos: por eso aquí NO se usa, y el formato y «solo
  activos» se filtran en local sobre lo que llega.
- Cada fila devuelta cuesta 1 crédito (US$ 1 = 1 000 créditos); el plan Pro
  incluye 20 000 al mes. La cabecera `X-Credits-Remaining` trae el saldo.
- Errores: 401 (llave ausente, inválida, revocada o vencida), 402
  `insufficient_credits`, 429 `rate_limited` con `Retry-After`.
  Pro: 20 peticiones por segundo y 1 200 por hora.

Lo que NO está verificado: los nombres de los campos de cada anuncio.
`_normalizar` los lee con una tabla de alias (`_CLAVES`) y el resto del módulo
no depende de ellos. Como cada fila devuelta se cobra, la primera página es
chica (`PAGINA_PRUEBA`): si ninguna fila se reconoce, el barrido se detiene ahí
con un error que lista los campos recibidos (solo sus nombres, nunca los
valores) y se ajusta la tabla con UNA corrección.

Créditos: como en Atria, el costo es el cupo del plan (`usd_fuente` 0). El uso
del mes se cuenta aquí (`creditos_este_mes`) y el saldo que informa TrendTrack
se guarda al vuelo (`creditos_restantes`); ambos se ven en el panel admin.
`_pedir` es la costura de pruebas.
"""
import json
import math
import os
import re
import time
from datetime import date

import requests
import sqlalchemy as sa
from flask_babel import gettext, ngettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
from referentes.fuentes.base import AVISO_CUOTA_AGOTADA, ErrorFuente

BASE_URL = "https://api.trendtrack.io"
# Modos de búsqueda que esta fuente admite (las demás admiten palabra y marca).
MODOS = ("palabra",)
PAGINA = 50
# Primera página chica: si la forma de los anuncios no se reconoce, solo se
# pagan estas filas (10 créditos = US$ 0,01) antes de detenerse.
PAGINA_PRUEBA = 10
# El formato (imagen/video) y «solo activos» se filtran aquí, después de pagar
# la fila; este factor acota cuántas filas se miran por cada anuncio pedido.
FACTOR_ESCANEO = 3
USD_POR_CREDITO = 0.001
ESPERA_ENTRE_LLAMADAS = 0.2
ESPERA_LIMITE_MAX = 60
TIMEOUT = 25
MAX_CAMPOS_EN_ERROR = 25

# Tabla de alias por campo (forma SUPUESTA, sin verificar; ver la cabecera).
# Se prueba en orden y gana el primer valor no vacío. `id_meta`: ids que son
# los de la Ad Library de Meta (se guardan tal cual y se deduplican contra
# Atria/Apify); `id_propio`: el id interno de TrendTrack (se guarda con `tt:`).
_CLAVES = {
    "id_meta": ("adArchiveId", "ad_archive_id", "libraryId", "library_id", "metaAdId", "meta_ad_id"),
    "id_propio": ("id", "adId", "ad_id"),
    "pagina_id": ("pageId", "page_id", "advertiserId", "advertiser_id"),
    "marca": ("pageName", "page_name", "advertiserName", "advertiser_name", "brandName", "brand_name", "advertiser"),
    "titular": ("title", "headline", "adTitle"),
    "cuerpo": ("body", "text", "primaryText", "primary_text", "adText", "copy", "caption"),
    "tipo": ("mediaType", "media_type", "displayFormat", "display_format", "format", "type"),
    "imagen": ("imageUrl", "image_url", "thumbnailUrl", "thumbnail_url", "thumbnail", "previewUrl", "preview_url",
               "previewImageUrl", "images", "image"),
    "video": ("videoUrl", "video_url", "videos", "video"),
    "inicio": ("startDate", "start_date", "firstSeen", "first_seen", "startedAt", "createdAt"),
    "ultima_vez": ("lastSeen", "last_seen", "lastSeenDate", "endDate", "end_date", "updatedAt"),
    "estado": ("status", "adStatus", "ad_status"),
    "activo": ("isActive", "is_active", "active"),
    "dias": ("daysRunning", "days_running", "runningDays", "days"),
    "variantes": ("creativeDuplicates", "creative_duplicates", "duplicates", "variants", "variantsCount"),
    "idioma": ("language", "lang"),
}


class _LimiteExcedido(RuntimeError):
    """429 dos veces seguidas: se agotó la cuota por segundo/hora del plan."""


class _SinCreditos(RuntimeError):
    """402 `insufficient_credits`: los créditos del plan y de recarga se acabaron."""


def _api_key():
    return (os.environ.get("TRENDTRACK_API_KEY") or "").strip()


# --------------------------------------------------------------- contadores ---

def _clave_mes():
    return f"trendtrack_creditos:{date.today().strftime('%Y-%m')}"


_CLAVE_SALDO = "trendtrack_saldo"


def creditos_este_mes():
    """Créditos que ESTA plataforma ha gastado en TrendTrack este mes."""
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _clave_mes())).scalar()
    try:
        return int(crudo or 0)
    except (TypeError, ValueError):
        return 0


def _sumar_creditos(n):
    if n <= 0:
        return
    clave = _clave_mes()
    with db.conectar() as con:
        # Lock de escritura antes de leer (mismo truco que atria y cuentas.limite_ok).
        con.execute(db.kv.update().where(db.kv.c.clave == clave).values(valor=db.kv.c.valor))
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave)).scalar()
        try:
            total = int(crudo or 0) + int(n)
        except (TypeError, ValueError):
            total = int(n)
        con.execute(insert_sqlite(db.kv).values(clave=clave, valor=str(total), actualizado_en=db.ahora())
                    .on_conflict_do_update(index_elements=["clave"],
                                           set_={"valor": str(total), "actualizado_en": db.ahora()}))


def _guardar_saldo(cabeceras):
    """Guarda el saldo que informa TrendTrack (`X-Credits-Remaining`), si vino."""
    try:
        restantes = int(float((cabeceras or {}).get("X-Credits-Remaining")))
    except (TypeError, ValueError):
        return
    valor = json.dumps({"restantes": restantes, "fecha": date.today().isoformat()})
    with db.conectar() as con:
        con.execute(insert_sqlite(db.kv).values(clave=_CLAVE_SALDO, valor=valor, actualizado_en=db.ahora())
                    .on_conflict_do_update(index_elements=["clave"],
                                           set_={"valor": valor, "actualizado_en": db.ahora()}))


def creditos_restantes():
    """`{"restantes": int, "fecha": "AAAA-MM-DD"}` del último saldo visto, o None."""
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _CLAVE_SALDO)).scalar()
    try:
        d = json.loads(crudo or "")
        return {"restantes": int(d["restantes"]), "fecha": str(d.get("fecha") or "")}
    except (TypeError, ValueError, KeyError):
        return None


# ------------------------------------------------------------------- HTTP ---

def _sesion():
    return requests.Session()


def _get(sesion, ruta, params, llave):
    """Una petición GET real. Un `requests.RequestException` (timeout, error de
    conexión) se envuelve como `ErrorFuente`; la llave nunca llega a un mensaje."""
    try:
        return sesion.get(f"{BASE_URL}{ruta}", params=params, timeout=TIMEOUT,
                          headers={"Authorization": f"Bearer {llave}", "Accept": "application/json"})
    except requests.RequestException as e:
        raise ErrorFuente(gettext("No se pudo conectar con TrendTrack: %(tipo)s.", tipo=type(e).__name__)) from e


def _espera_de(respuesta):
    try:
        return min(max(float((respuesta.headers or {}).get("Retry-After")), 1.0), ESPERA_LIMITE_MAX)
    except (TypeError, ValueError):
        return 10.0


def _pedir(sesion, ruta, params, medido=True):
    """Una llamada real a TrendTrack, espaciada. Ante 429 espera `Retry-After`
    y reintenta una vez (`_LimiteExcedido` si vuelve a fallar); 402 es
    `_SinCreditos`; 401 y el resto son `ErrorFuente`. Devuelve el cuerpo JSON."""
    llave = _api_key()
    if not llave:
        raise ErrorFuente(gettext("TrendTrack no está configurado (falta TRENDTRACK_API_KEY)."))
    time.sleep(ESPERA_ENTRE_LLAMADAS)
    r = _get(sesion, ruta, params, llave)
    if r.status_code == 429:
        time.sleep(_espera_de(r))
        r = _get(sesion, ruta, params, llave)
        if r.status_code == 429:
            raise _LimiteExcedido()
    if r.status_code == 401:
        raise ErrorFuente(gettext("TrendTrack no aceptó la llave (TRENDTRACK_API_KEY): revísala o genera otra."))
    if r.status_code == 402:
        raise _SinCreditos()
    if r.status_code == 403:
        raise ErrorFuente(gettext("Tu plan de TrendTrack no incluye la API (hace falta el plan Pro o superior)."))
    if r.status_code >= 400:
        raise ErrorFuente(gettext("TrendTrack respondió con un error (HTTP %(codigo)s).", codigo=r.status_code))
    try:
        sobre = r.json()
    except ValueError:
        raise ErrorFuente(gettext("TrendTrack respondió algo inesperado (HTTP %(codigo)s).", codigo=r.status_code)) from None
    if medido:
        _guardar_saldo(getattr(r, "headers", None))
    return sobre if isinstance(sobre, dict) else {"data": sobre}


# ------------------------------------------------------------ contrato común ---

def probar():
    """`GET /v1/me` no consume créditos: solo confirma que la llave vale."""
    _pedir(_sesion(), "/v1/me", {}, medido=False)
    return None


def estimar(consulta, tope):
    """Hasta `tope × FACTOR_ESCANEO` filas se miran (la primera página se paga
    aunque no sirva); cada una es 1 crédito del plan. Sin costo propio en USD:
    como Atria, el cupo va incluido en el plan."""
    tope = max(1, int(tope or 0))
    creditos = tope * FACTOR_ESCANEO
    llamadas = max(1, math.ceil(creditos / PAGINA))
    usd = round(creditos * USD_POR_CREDITO, 2)
    return {"usd_fuente": 0.0, "llamadas": llamadas,
            "detalle": ngettext("hasta %(num)d crédito de TrendTrack (del plan; US$ %(usd)s si fueran de recarga)",
                                "hasta %(num)d créditos de TrendTrack (del plan; US$ %(usd)s si fueran de recarga)",
                                creditos, usd=f"{usd:.2f}")}


# ------------------------------------------------------------ normalización ---

def _v(item, clave):
    """Primer valor no vacío de la tabla de alias `_CLAVES[clave]`."""
    for k in _CLAVES[clave]:
        v = item.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _texto(v):
    if isinstance(v, dict):
        v = v.get("name") or v.get("title") or v.get("text")
    return v.strip() if isinstance(v, str) else ""


def _url(v):
    """Una URL http(s) desde un texto, un dict `{url|src}` o una lista de ellos."""
    if isinstance(v, (list, tuple)):
        for x in v:
            u = _url(x)
            if u:
                return u
        return None
    if isinstance(v, dict):
        v = v.get("url") or v.get("src") or v.get("imageUrl") or v.get("image_url")
    return v.strip() if isinstance(v, str) and v.strip().startswith(("http://", "https://")) else None


def _entero(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _fecha(v):
    return v[:10] if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v) else None


def _tipo(v):
    t = (v or "")
    t = t.lower() if isinstance(t, str) else ""
    if "video" in t:
        return "video"
    if "carousel" in t or "carrusel" in t or t == "dco":
        return "carrusel"
    return "imagen"


def _activo(item):
    a = _v(item, "activo")
    if isinstance(a, bool):
        return a
    estado = _v(item, "estado")
    if isinstance(estado, str):
        return estado.strip().lower() in ("active", "activo", "running", "live")
    return True  # sin señal, no se descarta por «inactivo»


def _normalizar(item):
    """Un anuncio de TrendTrack → el dict que consume `guardar_referente`, o
    None si no trae un id o ninguna imagen utilizable."""
    if not isinstance(item, dict):
        return None
    id_meta = _v(item, "id_meta")
    id_propio = _v(item, "id_propio")
    if id_meta is not None:
        anuncio_id = str(id_meta)
    elif id_propio is not None:
        anuncio_id = f"tt:{id_propio}"[:40]       # id interno: no se cruza con el de la Ad Library
    else:
        return None
    video = _url(_v(item, "video"))
    imagen = _url(_v(item, "imagen"))
    tipo = _tipo(_v(item, "tipo"))
    if tipo == "imagen" and video and not imagen:
        tipo = "video"
    if not imagen:
        return None
    pagina_id = _v(item, "pagina_id")
    pagina_id = str(pagina_id) if pagina_id is not None else None
    inicio = _fecha(_v(item, "inicio"))
    es_meta = id_meta is not None
    return {
        "anuncio_id": anuncio_id,
        "pagina_id": pagina_id,
        "marca": _texto(_v(item, "marca")),
        "titular": _texto(_v(item, "titular")),
        "cuerpo": _texto(_v(item, "cuerpo")),
        "idioma": _texto(_v(item, "idioma")) or None,
        "pais": None,
        "tipo": tipo,
        "imagen_origen": imagen,
        "dias": _entero(_v(item, "dias")),
        "variantes": _entero(_v(item, "variantes")),
        "primera_vez": inicio,
        "ultima_vez": _fecha(_v(item, "ultima_vez")) or inicio,
        "activo": _activo(item),
        "url_anuncio": f"https://www.facebook.com/ads/library/?id={id_meta}" if es_meta else None,
        "url_marca": (f"https://www.facebook.com/ads/library/?view_all_page_id={pagina_id}" if pagina_id else None),
        "etiquetas_fuente": {},
        "extra": {"video_url": video} if video else {},
    }


def _cumple(anuncio, consulta):
    """Filtros que TrendTrack no recibe (ver la cabecera): formato y «solo activos»."""
    formato = consulta.get("formato") or "imagen"
    if formato == "video" and anuncio["tipo"] != "video":
        return False
    if formato == "imagen" and anuncio["tipo"] not in ("imagen", "carrusel"):
        return False
    if consulta.get("solo_activos", True) and not anuncio["activo"]:
        return False
    return True


def _filas(sobre):
    """La lista de anuncios del sobre `{data, ...}`. `data` puede ser la lista
    misma o un dict que la trae bajo `items`/`ads`/`rows`/`results`."""
    data = sobre.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "ads", "rows", "results"):
            if isinstance(data.get(k), list):
                return data[k]
    if data is None:
        return []
    raise ErrorFuente(gettext("TrendTrack devolvió la lista de anuncios en una forma que Creatv no reconoce todavía."))


def _campos_de(filas):
    primera = next((f for f in filas if isinstance(f, dict)), {})
    nombres = sorted(k for k in primera if isinstance(k, str) and re.fullmatch(r"[A-Za-z0-9_]{1,40}", k))
    return ", ".join(nombres[:MAX_CAMPOS_EN_ERROR]) or "—"


def traer(consulta, tope, avanzar, cursor=None):
    """Itera páginas de anuncios normalizados y ya filtrados por formato y
    estado. `cursor` es el `offset` (texto) desde el que retomar; cada página se
    entrega como `(anuncios, cursor_siguiente, {})` y `cursor_siguiente` es None
    al agotarse la búsqueda o el tope de filas a mirar. Solo busca por palabra
    clave: `/v1/ads` exige `search` y el filtro por página no está confirmado.
    Sin créditos (402) o con el límite de ritmo agotado: entrega parcial
    (`AVISO_CUOTA_AGOTADA`) si ya trajo algo en esta llamada; si no, `ErrorFuente`."""
    if consulta.get("modo") == "marca":
        raise ErrorFuente(gettext("TrendTrack solo busca por palabra clave; para los anuncios de una marca usa Atria o Apify."))
    palabra = (consulta.get("palabra") or "").strip()
    if not palabra:
        raise ErrorFuente(gettext("Escribe una palabra clave."))
    sesion = _sesion()
    tope = int(tope or 0)
    maximo_filas = max(tope, 1) * FACTOR_ESCANEO
    offset = _entero(cursor) or 0
    escaneadas = 0
    aceptados = 0
    validada = False
    while aceptados < tope and escaneadas < maximo_filas:
        limite = min(PAGINA if validada else PAGINA_PRUEBA, maximo_filas - escaneadas)
        try:
            sobre = _pedir(sesion, "/v1/ads", {"search": palabra, "limit": limite, "offset": offset})
        except (_SinCreditos, _LimiteExcedido) as e:
            if escaneadas == 0:
                raise ErrorFuente(gettext("TrendTrack: se acabaron los créditos del plan.") if isinstance(e, _SinCreditos)
                                  else gettext("TrendTrack: se alcanzó el límite de peticiones del plan; intenta en un rato.")) from None
            avanzar(detalle=AVISO_CUOTA_AGOTADA)
            yield [], None, {}
            return
        filas = _filas(sobre)
        _sumar_creditos(len(filas))
        if not filas:
            yield [], None, {}
            return
        escaneadas += len(filas)
        offset += len(filas)
        normalizados = [_normalizar(f) for f in filas]
        if not validada:
            if not any(normalizados):
                raise ErrorFuente(gettext(
                    "TrendTrack devolvió anuncios con campos que Creatv no reconoce todavía (recibidos: %(campos)s). "
                    "Avisa al equipo para ajustar el conector; se detuvo para no gastar más créditos.",
                    campos=_campos_de(filas)))
            validada = True
        pagina = [a for a in normalizados if a and _cumple(a, consulta)][:max(0, tope - aceptados)]
        aceptados += len(pagina)
        # Sigue solo si la página vino llena (regla de la documentación: una
        # página corta es la última) y aún hay presupuesto de filas.
        hay_mas = len(filas) >= limite and escaneadas < maximo_filas
        avanzar(detalle=f"{min(aceptados, tope)}/{tope}")
        yield pagina, (str(offset) if hay_mas else None), {}
        if not hay_mas:
            return

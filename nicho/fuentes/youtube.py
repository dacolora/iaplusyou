"""
Fuente `youtube` (spec §3.4): YouTube Data API v3 con llave simple
(YOUTUBE_API_KEY): los comentarios públicos no necesitan OAuth. Cuota
verificada 2026-09-20 en developers.google.com/youtube/v3/determine_quota_cost:
`search.list` tiene su PROPIO cupo de 100 llamadas por día por proyecto;
`commentThreads.list` y `videos.list` cuestan 1 unidad de las 10 000 diarias.
Por eso una recolección hace UNA búsqueda (max_videos ≤ MAX_VIDEOS) y pagina
los comentarios de a POR_PAGINA. Links de videos (`watch?v=`, `youtu.be/`,
`/shorts/`, `/live/`, `/embed/`) no gastan búsqueda: se resuelven con
`videos.list`.

Parámetros: palabras_clave, links, max_videos, max_comentarios_por_video,
idioma (relevanceLanguage) y region (regionCode). Un video con comentarios
cerrados (`commentsDisabled`) se salta; cuota agotada (`quotaExceeded`,
`rateLimitExceeded`, `dailyLimitExceeded`) entrega lo leído con `aviso`;
llave inválida o API no habilitada -> ErrorFuente. Nunca se guarda el autor.
"""
import json
import os
import re

from googleapiclient.errors import HttpError

from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

MAX_VIDEOS = 10
MAX_COMENTARIOS_POR_VIDEO = 500
POR_PAGINA = 100
URL_VIDEO = "https://www.youtube.com/watch?v="
_RE_VIDEO = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")
_RE_IDIOMA = re.compile(r"^[a-z]{2,5}$")
_RE_REGION = re.compile(r"^[A-Z]{2}$")
_CUOTA = ("quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded")


def id_video_desde_link(url):
    m = _RE_VIDEO.search(url or "")
    return m.group(1) if m else None


def _entero(v, defecto, tope):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = defecto
    return max(1, min(tope, n if n else defecto))


def normalizar_params(params):
    p = dict(params or {})
    palabras = (p.get("palabras_clave") or "").strip()
    links = [i for i in (id_video_desde_link(x) for x in (p.get("links") or [])) if i]
    if not palabras and not links:
        raise ErrorFuente("YouTube necesita palabras clave o links de videos.")
    idioma = (p.get("idioma") or "").strip().lower()
    region = (p.get("region") or "").strip().upper()
    return {"palabras_clave": palabras, "links": links[:MAX_VIDEOS],
            "max_videos": _entero(p.get("max_videos"), 5, MAX_VIDEOS),
            "max_comentarios_por_video": _entero(p.get("max_comentarios_por_video"), 100, MAX_COMENTARIOS_POR_VIDEO),
            "idioma": idioma if _RE_IDIOMA.match(idioma) else "es",
            "region": region if _RE_REGION.match(region) else None}


def cliente_api():
    """Cliente de la Data API v3 con la llave del .env. Las pruebas lo reemplazan."""
    llave = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not llave:
        raise ErrorFuente("Falta YOUTUBE_API_KEY en el .env del servidor.")
    from googleapiclient.discovery import build
    return build("youtube", "v3", developerKey=llave, cache_discovery=False)


def razon(e):
    """Motivo de un HttpError de Google (`errors[0].reason`), o cadena vacía."""
    try:
        data = json.loads(getattr(e, "content", b"") or b"{}")
        return str(((data.get("error") or {}).get("errors") or [{}])[0].get("reason") or "")
    except (ValueError, AttributeError, TypeError, IndexError):
        return ""


# --------------------------------------------------------------- parsers ---

def parsear_busqueda(resp):
    salida = []
    for item in (resp or {}).get("items") or []:
        vid = ((item.get("id") or {}).get("videoId"))
        if vid:
            salida.append({"id": vid, "titulo": ((item.get("snippet") or {}).get("title") or "")})
    return salida


def parsear_videos(resp):
    return [{"id": item.get("id"), "titulo": ((item.get("snippet") or {}).get("title") or "")}
            for item in ((resp or {}).get("items") or []) if item.get("id")]


def parsear_hilos(resp, video):
    salida = []
    for item in (resp or {}).get("items") or []:
        arriba = ((item.get("snippet") or {}).get("topLevelComment") or {})
        s = arriba.get("snippet") or {}
        cid = item.get("id") or arriba.get("id")
        if not cid:
            continue
        salida.append({"fuente_id": cid, "texto": s.get("textOriginal") or s.get("textDisplay") or "",
                       "url": f"{URL_VIDEO}{video['id']}&lc={cid}", "contexto": video.get("titulo") or "",
                       "puntuacion": s.get("likeCount"), "fecha": s.get("publishedAt"), "extra": {"video_id": video["id"]}})
    return salida


# --------------------------------------------------------------- cliente ---

def _error_llave(e):
    return ErrorFuente(f"Google rechazó la llamada ({razon(e) or 'error'}): revisa YOUTUBE_API_KEY y que la YouTube Data API v3 esté habilitada.")


def buscar_videos(yt, p):
    consulta = {"part": "id,snippet", "q": p["palabras_clave"], "type": "video", "maxResults": p["max_videos"],
                "relevanceLanguage": p["idioma"], "safeSearch": "none"}
    if p["region"]:
        consulta["regionCode"] = p["region"]
    return parsear_busqueda(yt.search().list(**consulta).execute())


def videos_por_id(yt, ids):
    if not ids:
        return []
    return parsear_videos(yt.videos().list(part="snippet", id=",".join(ids)).execute())


def comentarios_video(yt, video, max_n):
    """Páginas de commentThreads hasta max_n. Lanza HttpError tal cual (la fuente decide)."""
    salida, token = [], None
    while len(salida) < max_n:
        consulta = {"part": "snippet", "videoId": video["id"], "maxResults": min(POR_PAGINA, max_n - len(salida)),
                    "order": "relevance", "textFormat": "plainText"}
        if token:
            consulta["pageToken"] = token
        resp = yt.commentThreads().list(**consulta).execute()
        salida += parsear_hilos(resp, video)
        token = (resp or {}).get("nextPageToken")
        if not token:
            break
    return salida[:max_n]


class FuenteYouTube(Fuente):
    tipo = "youtube"

    def probar(self):
        try:
            yt = cliente_api()
            yt.videos().list(part="id", id="dQw4w9WgXcQ").execute()      # 1 unidad
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}
        except HttpError as e:
            return {"ok": False, "detalle": _error_llave(e).usuario}
        return {"ok": True, "detalle": "YouTube aceptó la llave."}

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.aviso = ""
        yt = cliente_api()
        avanzar("Buscando")
        try:
            videos = videos_por_id(yt, p["links"])
        except HttpError as e:
            if razon(e) in _CUOTA:
                self.aviso = "YouTube agotó la cuota diaria del proyecto de Google; vuelve a intentar mañana."
                return
            raise _error_llave(e)
        if p["palabras_clave"]:
            try:
                videos += buscar_videos(yt, p)
            except HttpError as e:
                if razon(e) not in _CUOTA:
                    raise _error_llave(e)
                self.aviso = ("YouTube agotó las búsquedas del día (100 por proyecto de Google); se leyeron solo los videos de los links. "
                              "Vuelve a buscar mañana.")
        if not videos:
            return
        vistos, pendientes = set(), []
        for v in videos:
            if v["id"] not in vistos:
                vistos.add(v["id"])
                pendientes.append(v)
        pendientes = pendientes[:MAX_VIDEOS]
        for n, video in enumerate(pendientes, start=1):
            avanzar("Leyendo comentarios", f"video {n} de {len(pendientes)}")
            try:
                hilos = comentarios_video(yt, video, p["max_comentarios_por_video"])
            except HttpError as e:
                motivo = razon(e)
                if motivo == "commentsDisabled":
                    continue
                if motivo in _CUOTA:
                    self.aviso = (f"YouTube agotó la cuota diaria; se guardó lo leído hasta el video {n - 1} de {len(pendientes)}. "
                                  "Vuelve a recolectar mañana.")
                    return
                raise _error_llave(e)
            for crudo in hilos:
                c = normalizar_comentario(crudo)
                if c:
                    yield c

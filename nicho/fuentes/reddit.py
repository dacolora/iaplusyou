"""
Fuente `reddit` (spec §3.3): API oficial de Reddit con token de solo lectura.
Verificado 2026-09-20 en la wiki OAuth2 de Reddit: una app tipo *script* o
*web app* obtiene un token sin usuario con `grant_type=client_credentials` en
https://www.reddit.com/api/v1/access_token (autenticación básica
client_id:client_secret; el token no trae refresh y dura ~24 h) y llama a
https://oauth.reddit.com con `Authorization: bearer …` y un User-Agent que
describa la app. Límite: 100 llamadas por minuto por cliente OAuth (PAUSA de
1 s entre llamadas deja margen); gratis solo para uso no comercial — si el
producto se vende, hay que pedir acceso comercial a Reddit (SETUP.md).

Llaves en el .env raíz: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
REDDIT_USER_AGENT. Parámetros: palabras_clave, subreddits (≤ MAX_SUBREDDITS),
links de posts, max_posts (≤ MAX_POSTS), max_comentarios_por_post
(≤ MAX_COMENTARIOS_POR_POST), periodo. El texto del post entra como
comentario (fuente_id = id del post); cada comentario `t1` con su id, hasta
dos niveles (`depth=2`), ordenados por votos; se saltan `[deleted]`,
`[removed]`, `more` y los de AutoModerator. Nunca se guarda el autor. Ante
429 persistente la fuente entrega lo leído y deja `aviso`.
"""
import os
import re

from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

URL_TOKEN = "https://www.reddit.com/api/v1/access_token"
URL_API = "https://oauth.reddit.com"
URL_PUBLICA = "https://www.reddit.com"
MAX_POSTS = 25
MAX_COMENTARIOS_POR_POST = 200
MAX_SUBREDDITS = 5
PERIODOS = ("week", "month", "year", "all")
PAUSA = 1.0
VARIABLES = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
_RE_POST = re.compile(r"reddit\.com/r/[^/]+/comments/([a-z0-9]+)", re.IGNORECASE)
_RE_POST_CORTO = re.compile(r"redd\.it/([a-z0-9]+)", re.IGNORECASE)
_SIN_TEXTO = ("", "[deleted]", "[removed]")
_BOTS = ("AutoModerator",)


def id_post_desde_link(url):
    m = _RE_POST.search(url or "") or _RE_POST_CORTO.search(url or "")
    return m.group(1).lower() if m else None


def _entero(v, defecto, tope):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = defecto
    return max(1, min(tope, n if n else defecto))


def normalizar_params(params):
    p = dict(params or {})
    palabras = (p.get("palabras_clave") or "").strip()
    links = [i for i in (id_post_desde_link(x) for x in (p.get("links") or [])) if i]
    if not palabras and not links:
        raise ErrorFuente("Reddit necesita palabras clave o links de posts.")
    subreddits = []
    for s in p.get("subreddits") or []:
        s = (s or "").strip().strip("/")
        if s.lower().startswith("r/"):
            s = s[2:]
        if s:
            subreddits.append(s)
    return {"palabras_clave": palabras, "subreddits": subreddits[:MAX_SUBREDDITS], "links": links[:MAX_POSTS],
            "max_posts": _entero(p.get("max_posts"), 10, MAX_POSTS),
            "max_comentarios_por_post": _entero(p.get("max_comentarios_por_post"), 50, MAX_COMENTARIOS_POR_POST),
            "periodo": p.get("periodo") if p.get("periodo") in PERIODOS else "year"}


def _llaves():
    ll = {k: (os.environ.get(k) or "").strip() for k in VARIABLES}
    faltan = [k for k, v in ll.items() if not v]
    if faltan:
        raise ErrorFuente(f"Falta {', '.join(faltan)} en el .env del servidor.")
    return ll


# --------------------------------------------------------------- parsers ---

def _post(d):
    return {"id": d.get("id") or "", "titulo": d.get("title") or "", "permalink": d.get("permalink") or "",
            "texto": d.get("selftext") or "", "puntuacion": d.get("score"), "fecha": d.get("created_utc"),
            "subreddit": d.get("subreddit") or ""}


def parsear_busqueda(data):
    """JSON de /search -> posts {id, titulo, permalink, texto, puntuacion, fecha, subreddit}."""
    salida = []
    for hijo in (((data or {}).get("data") or {}).get("children") or []):
        d = hijo.get("data") or {}
        if hijo.get("kind") == "t3" and d.get("id"):
            salida.append(_post(d))
    return salida


def _comentario(post, d):
    return {"fuente_id": d["id"], "texto": d.get("body") or "", "url": URL_PUBLICA + (d.get("permalink") or ""),
            "contexto": post["titulo"], "puntuacion": d.get("score"), "fecha": d.get("created_utc"),
            "extra": {"subreddit": post["subreddit"], "post_id": post["id"]}}


def _recorrer(hijos, post, salida, max_n):
    for hijo in hijos or []:
        if len(salida) >= max_n:
            return
        if hijo.get("kind") != "t1":
            continue
        d = hijo.get("data") or {}
        if d.get("id") and (d.get("body") or "").strip() not in _SIN_TEXTO and d.get("author") not in _BOTS:
            salida.append(_comentario(post, d))
        respuestas = d.get("replies")
        if isinstance(respuestas, dict):
            _recorrer(((respuestas.get("data") or {}).get("children")), post, salida, max_n)


def parsear_comentarios(data, max_n):
    """JSON de /comments/<id> (dos Listings: el post y sus comentarios) -> el
    texto del post como comentario (si tiene) + comentarios hasta max_n."""
    if not isinstance(data, list) or len(data) < 2:
        return []
    hijos_post = ((data[0].get("data") or {}).get("children") or [])
    post = _post((hijos_post[0].get("data") or {}) if hijos_post else {})
    salida = []
    if post["id"] and post["texto"].strip() not in _SIN_TEXTO:
        salida.append({"fuente_id": post["id"], "texto": post["texto"], "url": URL_PUBLICA + post["permalink"],
                       "contexto": post["titulo"], "puntuacion": post["puntuacion"], "fecha": post["fecha"],
                       "extra": {"subreddit": post["subreddit"], "post_id": post["id"]}})
    _recorrer(((data[1].get("data") or {}).get("children") or []), post, salida, max_n)
    return salida[:max_n]


# --------------------------------------------------------------- cliente ---

def _token(sesion, ll):
    r = _http.pedir(sesion, "POST", URL_TOKEN, "Reddit", auth=(ll["REDDIT_CLIENT_ID"], ll["REDDIT_CLIENT_SECRET"]),
                    data={"grant_type": "client_credentials"}, headers={"User-Agent": ll["REDDIT_USER_AGENT"]})
    if r.status_code in (401, 403):
        raise ErrorFuente("Reddit no aceptó las llaves (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET).")
    if r.status_code != 200:
        raise ErrorFuente(f"Reddit no dio token ({r.status_code}).")
    token = (r.json() or {}).get("access_token")
    if not token:
        raise ErrorFuente("Reddit no devolvió un token.")
    return token


def _get(sesion, token, ll, ruta, params):
    """GET a oauth.reddit.com. None si 404; ErrorFuente en 401/403 u otro código."""
    r = _http.pedir(sesion, "GET", URL_API + ruta, "Reddit", params={**params, "raw_json": 1},
                    headers={"Authorization": f"bearer {token}", "User-Agent": ll["REDDIT_USER_AGENT"]})
    if r.status_code == 404:
        return None
    if r.status_code in (401, 403):
        raise ErrorFuente("Reddit rechazó la llamada (¿la app perdió permisos o el user agent no describe la app?).")
    if r.status_code != 200:
        raise ErrorFuente(f"Reddit respondió {r.status_code}.")
    return r.json()


def buscar_posts(sesion, token, ll, p):
    """Una búsqueda global o una por subreddit; devuelve (posts, limitado).
    `limitado` es True si Reddit cortó con 429 a mitad de las búsquedas;
    se devuelven los posts ya encontrados."""
    consulta = {"q": p["palabras_clave"], "sort": "relevance", "t": p["periodo"], "limit": p["max_posts"], "type": "link"}
    rutas = [f"/r/{s}/search" for s in p["subreddits"]] or ["/search"]
    vistos, posts = set(), []
    for i, ruta in enumerate(rutas):
        if i:
            _http.dormir(PAUSA)
        params = dict(consulta, restrict_sr=1) if ruta != "/search" else consulta
        try:
            for post in parsear_busqueda(_get(sesion, token, ll, ruta, params) or {}):
                if post["id"] not in vistos:
                    vistos.add(post["id"])
                    posts.append(post)
        except _http.Error429:
            return posts[:p["max_posts"]], True
    return posts[:p["max_posts"]], False


class FuenteReddit(Fuente):
    tipo = "reddit"

    def probar(self):
        try:
            _token(_http.sesion(), _llaves())
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}
        return {"ok": True, "detalle": "Reddit aceptó las llaves (solo lectura)."}

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        ll = _llaves()
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.aviso = ""
        sesion = _http.sesion()
        try:
            token = _token(sesion, ll)
        except _http.Error429 as e:
            self.aviso = f"Reddit limitó las llamadas al pedir el token; intenta en unos minutos. ({e.usuario})"
            return
        avanzar("Buscando")
        ids = list(p["links"])
        if p["palabras_clave"]:
            posts, limitado = buscar_posts(sesion, token, ll, p)
            ids += [post["id"] for post in posts]
            if limitado:
                self.aviso = "Reddit limitó las llamadas durante la búsqueda; se leyeron los posts encontrados hasta ahí y los links. Vuelve a buscar en unos minutos."
        vistos, pendientes = set(), []
        for i in ids:
            if i not in vistos:
                vistos.add(i)
                pendientes.append(i)
        for n, post_id in enumerate(pendientes, start=1):
            avanzar("Leyendo comentarios", f"post {n} de {len(pendientes)}")
            _http.dormir(PAUSA)
            try:
                data = _get(sesion, token, ll, f"/comments/{post_id}", {"sort": "top", "limit": p["max_comentarios_por_post"], "depth": 2})
            except _http.Error429:
                self.aviso = (f"Reddit limitó las llamadas; se guardó lo leído hasta el post {n - 1} de {len(pendientes)}. "
                              "Vuelve a recolectar en unos minutos.")
                return
            if data is None:
                continue
            for crudo in parsear_comentarios(data, p["max_comentarios_por_post"]):
                c = normalizar_comentario(crudo)
                if c:
                    yield c

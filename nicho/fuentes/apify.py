"""
Fuente `apify` (spec §3.5): reseñas de Amazon y comentarios de TikTok a través
de los actores de `apify_actores` (de pago, por resultado). Llave APIFY_TOKEN
SIEMPRE como cabecera `Authorization: Bearer …`, nunca en la URL (los logs de
gunicorn y del worker guardan URLs). API v2 verificada 2026-09-20:
  POST /v2/actors/<usuario~actor>/runs (entrada JSON; ?timeout= segundos)
       -> data.id, data.status, data.defaultDatasetId
  GET  /v2/actor-runs/<id> -> data.status (READY, RUNNING, SUCCEEDED, FAILED,
       TIMING-OUT, TIMED-OUT, ABORTING, ABORTED)
  GET  /v2/datasets/<id>/items?clean=true&format=json&limit=N -> lista de ítems
Se sondea cada PAUSA_SONDEO s hasta MAX_ESPERA_S. Corrida FAILED / TIMED-OUT /
ABORTED -> ErrorFuente con el estado. `resultados` cuenta los ítems entregados:
el worker anota el gasto como resultados × precio del actor ("aprox.").
"""
import os

from nicho.fuentes import _http, apify_actores
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

URL_API = "https://api.apify.com/v2"
PAUSA_SONDEO = 10.0
MAX_ESPERA_S = 1200
TERMINALES = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")


def normalizar_params(params):
    p = dict(params or {})
    clave = p.get("actor") or ""
    est = apify_actores.estimar(clave, p.get("max_resultados") or 1)        # valida el actor y el tope
    return {"actor": clave, "links": apify_actores.validar_links(clave, p.get("links") or []), "max_resultados": est["max_resultados"]}


def _token():
    t = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not t:
        raise ErrorFuente("Falta APIFY_TOKEN en el .env del servidor.")
    return t


def _cabeceras(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _mensaje_apify(r):
    try:
        return str(((r.json() or {}).get("error") or {}).get("message") or "")[:200]
    except (ValueError, AttributeError):
        return ""


class FuenteApify(Fuente):
    tipo = "apify"
    de_pago = True

    def __init__(self):
        self.resultados = 0
        self.aviso = ""

    def estimar(self, params):
        p = normalizar_params(params)
        return apify_actores.estimar(p["actor"], p["max_resultados"])

    def probar(self):
        try:
            r = _http.pedir(_http.sesion(), "GET", URL_API + "/users/me", "Apify", headers=_cabeceras(_token()))
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}
        if r.status_code != 200:
            return {"ok": False, "detalle": f"Apify no aceptó el token ({r.status_code})."}
        return {"ok": True, "detalle": "Apify aceptó el token."}

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        token = _token()
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.resultados, self.aviso = 0, ""
        actor = apify_actores.ACTORES[p["actor"]]
        sesion = _http.sesion()
        avanzar("Buscando", actor["nombre"])
        r = _http.pedir(sesion, "POST", f"{URL_API}/actors/{actor['actor']}/runs", "Apify", headers=_cabeceras(token),
                        params={"timeout": MAX_ESPERA_S}, json=apify_actores.entrada(p["actor"], p["links"], p["max_resultados"]))
        if r.status_code in (401, 403):
            raise ErrorFuente("Apify no aceptó el token (APIFY_TOKEN).")
        if r.status_code == 400:
            raise ErrorFuente(f"Apify rechazó la entrada del actor: {_mensaje_apify(r) or 'entrada inválida'}")
        if r.status_code not in (200, 201):
            raise ErrorFuente(f"Apify no arrancó la corrida ({r.status_code}).")
        corrida = (r.json() or {}).get("data") or {}
        run_id, dataset_id = corrida.get("id"), corrida.get("defaultDatasetId")
        if not run_id or not dataset_id:
            raise ErrorFuente("Apify no devolvió el id de la corrida.")
        estado = corrida.get("status") or "READY"
        esperado = 0.0
        while estado not in TERMINALES:
            if esperado >= MAX_ESPERA_S:
                raise ErrorFuente(f"La corrida de Apify no terminó en {int(MAX_ESPERA_S / 60)} min (id {run_id}); revísala en console.apify.com.")
            _http.dormir(PAUSA_SONDEO)
            esperado += PAUSA_SONDEO
            r = _http.pedir(sesion, "GET", f"{URL_API}/actor-runs/{run_id}", "Apify", headers=_cabeceras(token))
            if r.status_code != 200:
                raise ErrorFuente(f"Apify no respondió el estado de la corrida ({r.status_code}).")
            estado = ((r.json() or {}).get("data") or {}).get("status") or estado
            avanzar("Leyendo comentarios", f"Apify: {estado}")
        if estado != "SUCCEEDED":
            raise ErrorFuente(f"La corrida de Apify terminó en {estado} (id {run_id}); revísala en console.apify.com.")
        r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{dataset_id}/items", "Apify", headers=_cabeceras(token),
                        params={"clean": "true", "format": "json", "limit": p["max_resultados"]})
        if r.status_code != 200:
            raise ErrorFuente(f"Apify no entregó los resultados ({r.status_code}).")
        for item in (r.json() or []):
            crudo = apify_actores.leer_item(p["actor"], item if isinstance(item, dict) else {})
            c = normalizar_comentario(crudo) if crudo else None
            if c:
                self.resultados += 1
                yield c

"""
Fuente `apify` (spec §3.5): reseñas de Amazon y comentarios de TikTok a través
de los actores de `apify_actores` (de pago, por resultado). Llave APIFY_TOKEN
SIEMPRE como cabecera `Authorization: Bearer …`, nunca en la URL (los logs de
gunicorn y del worker guardan URLs). API v2 verificada 2026-09-20:
  POST /v2/actors/<usuario~actor>/runs (entrada JSON; ?timeout= segundos,
       ?maxItems= ítems cobrados, ?maxTotalChargeUsd= tope de cobro)
       -> data.id, data.status, data.defaultDatasetId
  GET  /v2/actor-runs/<id> -> data.status (READY, RUNNING, SUCCEEDED, FAILED,
       TIMING-OUT, TIMED-OUT, ABORTING, ABORTED)
  GET  /v2/datasets/<id>/items?clean=true&format=json&limit=N -> lista de ítems
  GET  /v2/datasets/<id> -> data.itemCount
Una corrida se paga aunque termine mal, así que después del POST nada se
abandona: se sondea cada PAUSA_SONDEO s hasta MAX_ESPERA_S tolerando hasta
MAX_FALLOS_SONDEO lecturas malas seguidas, y al llegar a CUALQUIER estado
terminal (o al vencer el reloj local) se lee el dataset igual, hasta
INTENTOS_DATASET veces. `resultados` es el número de ítems CRUDOS que devolvió
el dataset (no solo los que traen texto): el worker anota el gasto como
resultados × precio del actor ("aprox."). Si el dataset no se puede leer,
`resultados` cae al `itemCount` del dataset y, en último caso, al tope
aprobado — registrar de más es mejor que perder el registro de un cobro.
`run_id`/`dataset_id` quedan en la fuente y en todo mensaje posterior al POST
para poder rastrear la corrida en console.apify.com.
"""
import os

from nicho.fuentes import _http, apify_actores
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

URL_API = "https://api.apify.com/v2"
PAUSA_SONDEO = 10.0
MAX_ESPERA_S = 1200
TERMINALES = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")
MAX_FALLOS_SONDEO = 6          # lecturas de estado malas SEGUIDAS antes de rendirse
INTENTOS_DATASET = 3           # lecturas del dataset antes de caer al itemCount
ESTADO_SIN_TERMINAR = "sin terminar"   # estado ficticio: venció el reloj local


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


def _frase_estado(estado):
    """«terminó en FAILED» / «no terminó en 20 min»: el sujeto de los mensajes
    del final, con el estado terminal real o el reloj local vencido."""
    if estado == ESTADO_SIN_TERMINAR:
        return f"no terminó en {int(MAX_ESPERA_S / 60)} min"
    return f"terminó en {estado}"


class FuenteApify(Fuente):
    tipo = "apify"
    de_pago = True

    def __init__(self):
        self.resultados = 0
        self.aviso = ""
        self.run_id = None
        self.dataset_id = None

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

    def _arrancar(self, sesion, token, p, avanzar):
        """POST de la corrida. Deja `run_id`/`dataset_id` fijados: desde acá
        cualquier error tiene que decir cuál corrida se pagó."""
        actor = apify_actores.ACTORES[p["actor"]]
        estimado = apify_actores.estimar(p["actor"], p["max_resultados"])
        avanzar("Buscando", actor["nombre"])
        # maxItems (actores por resultado) y maxTotalChargeUsd (por evento) son
        # el tope de cobro del lado de Apify: lo que la puerta mostró y nada más.
        r = _http.pedir(sesion, "POST", f"{URL_API}/actors/{actor['actor']}/runs", "Apify", headers=_cabeceras(token),
                        params={"timeout": MAX_ESPERA_S, "maxItems": p["max_resultados"], "maxTotalChargeUsd": estimado["usd"]},
                        json=apify_actores.entrada(p["actor"], p["links"], p["max_resultados"]))
        if r.status_code in (401, 403):
            raise ErrorFuente("Apify no aceptó el token (APIFY_TOKEN).")
        if r.status_code == 400:
            raise ErrorFuente(f"Apify rechazó la entrada del actor: {_mensaje_apify(r) or 'entrada inválida'}")
        if r.status_code not in (200, 201):
            raise ErrorFuente(f"Apify no arrancó la corrida ({r.status_code}).")
        corrida = (r.json() or {}).get("data") or {}
        self.run_id, self.dataset_id = corrida.get("id") or None, corrida.get("defaultDatasetId") or None
        if not self.run_id or not self.dataset_id:
            # Si el id sí vino, queda guardado igual: la corrida pudo arrancar (y cobrar).
            raise ErrorFuente(f"Apify no devolvió los ids de la corrida (corrida {self.run_id or '?'}, "
                              f"dataset {self.dataset_id or '?'}); revísala en console.apify.com.")
        return corrida.get("status") or "READY"

    def _sondear(self, sesion, token, estado, avanzar):
        """Sondea hasta un estado terminal y lo devuelve, o ESTADO_SIN_TERMINAR
        si venció MAX_ESPERA_S. Un fallo pasajero no abandona la corrida: se
        toleran MAX_FALLOS_SONDEO lecturas malas SEGUIDAS (una buena reinicia el
        contador) y la espera total sigue acotada."""
        esperado, fallos, ultimo = 0.0, 0, ""
        while estado not in TERMINALES:
            if esperado >= MAX_ESPERA_S:
                return ESTADO_SIN_TERMINAR
            _http.dormir(PAUSA_SONDEO)
            esperado += PAUSA_SONDEO
            try:
                r = _http.pedir(sesion, "GET", f"{URL_API}/actor-runs/{self.run_id}", "Apify", headers=_cabeceras(token))
                malo = "" if r.status_code == 200 else f"HTTP {r.status_code}"
            except ErrorFuente as e:                            # sin URL ni cabeceras: nunca lleva el token
                r, malo = None, e.usuario or "sin respuesta"
            if malo:
                fallos, ultimo = fallos + 1, malo
                if fallos >= MAX_FALLOS_SONDEO:
                    raise ErrorFuente(f"Apify no respondió el estado {MAX_FALLOS_SONDEO} veces seguidas ({ultimo}); "
                                      f"corrida {self.run_id}: revísala en console.apify.com.")
                continue
            fallos = 0
            estado = ((r.json() or {}).get("data") or {}).get("status") or estado
            avanzar("Leyendo comentarios", f"Apify: {estado} · corrida {self.run_id}")
        return estado

    def _leer_dataset(self, sesion, token, limite):
        """Ítems crudos del dataset, hasta INTENTOS_DATASET intentos. Devuelve
        `(lista, "")` cuando se pudo leer (la lista puede venir vacía) y
        `(None, motivo)` cuando no."""
        motivo = ""
        for intento in range(INTENTOS_DATASET):
            if intento:
                _http.dormir(PAUSA_SONDEO)
            try:
                r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{self.dataset_id}/items", "Apify", headers=_cabeceras(token),
                                params={"clean": "true", "format": "json", "limit": limite})
            except ErrorFuente as e:
                motivo = e.usuario
                continue
            if r.status_code != 200:
                motivo = f"HTTP {r.status_code}"
                continue
            datos = r.json()
            return (datos if isinstance(datos, list) else []), ""
        return None, motivo

    def _contar_dataset(self, sesion, token):
        """`itemCount` del dataset cuando no se pudieron leer los ítems: sirve
        para registrar el gasto de todos modos. None si tampoco se puede."""
        try:
            r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{self.dataset_id}", "Apify", headers=_cabeceras(token))
        except ErrorFuente:
            return None
        if r.status_code != 200:
            return None
        try:
            return max(0, int(((r.json() or {}).get("data") or {}).get("itemCount")))
        except (AttributeError, TypeError, ValueError):
            return None

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        token = _token()
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.resultados, self.aviso = 0, ""
        self.run_id, self.dataset_id = None, None
        sesion = _http.sesion()
        estado = self._arrancar(sesion, token, p, avanzar)
        estado = self._sondear(sesion, token, estado, avanzar)
        crudos, motivo = self._leer_dataset(sesion, token, p["max_resultados"])   # la corrida ya se pagó: se lee pase lo que pase
        if crudos is None:
            contados = self._contar_dataset(sesion, token)
            self.resultados = p["max_resultados"] if contados is None else contados
            raise ErrorFuente(f"Apify no entregó los resultados ({motivo}); corrida {self.run_id}, "
                              f"dataset {self.dataset_id}: revísalos en console.apify.com.")
        self.resultados = len(crudos)                            # ítems CRUDOS: es lo que Apify cobra
        for item in crudos:
            crudo = apify_actores.leer_item(p["actor"], item if isinstance(item, dict) else {})
            c = normalizar_comentario(crudo) if crudo else None
            if c:
                yield c
        if estado != "SUCCEEDED":
            if not self.resultados:
                raise ErrorFuente(f"La corrida de Apify {_frase_estado(estado)} sin resultados (corrida {self.run_id}); "
                                  "revísala en console.apify.com.")
            self.aviso = f"Apify {_frase_estado(estado)} (corrida {self.run_id}); se guardaron {self.resultados} resultados."

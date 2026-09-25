"""
Fuente `apify` (spec §3.5): reseñas de Amazon y comentarios de TikTok a través
de los actores de `apify_actores` (de pago, por resultado). Llave APIFY_TOKEN
SIEMPRE como cabecera `Authorization: Bearer …`, nunca en la URL (los logs de
gunicorn y del worker guardan URLs). La mecánica de arrancar/sondear/leer el
dataset vive en `providers/apify.py` (compartida con
`referentes/fuentes/apify_adlibrary.py`, spec bloque 5) — este módulo solo
sabe qué actor llamar y cómo convertir sus ítems crudos en comentarios.
`resultados` es el número de ítems CRUDOS que devolvió el dataset (no solo
los que traen texto): el worker anota el gasto como resultados × precio del
actor ("aprox."). Si el dataset no se puede leer, `resultados` cae al
`itemCount` del dataset y, en último caso, al tope aprobado — registrar de
más es mejor que perder el registro de un cobro. `run_id`/`dataset_id`
quedan en la fuente y en todo mensaje posterior al arranque para poder
rastrear la corrida en console.apify.com.
"""
import os

import providers.apify as apify_api
from nicho.fuentes import _http, apify_actores
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

URL_API = apify_api.URL_API
PAUSA_SONDEO = apify_api.PAUSA_SONDEO
MAX_ESPERA_S = apify_api.MAX_ESPERA_S
TERMINALES = apify_api.TERMINALES
MAX_FALLOS_SONDEO = apify_api.MAX_FALLOS_SONDEO
INTENTOS_DATASET = apify_api.INTENTOS_DATASET
ESTADO_SIN_TERMINAR = apify_api.ESTADO_SIN_TERMINAR


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
            return apify_api.probar_token(_http.sesion(), _token())
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        token = _token()
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.resultados, self.aviso = 0, ""
        self.run_id, self.dataset_id = None, None
        sesion = _http.sesion()
        actor = apify_actores.ACTORES[p["actor"]]
        estimado = apify_actores.estimar(p["actor"], p["max_resultados"])
        avanzar("Buscando", actor["nombre"])
        entrada = apify_actores.entrada(p["actor"], p["links"], p["max_resultados"])

        def _guardar_ids(run_id, dataset_id):
            # Se llama aunque `arrancar` termine lanzando: si Apify devolvió un id de
            # corrida (pudo cobrar) queda guardado en la fuente antes del error.
            self.run_id, self.dataset_id = run_id, dataset_id

        _, _, estado = apify_api.arrancar(
            sesion, token, actor["actor"], entrada, p["max_resultados"], estimado["usd"], on_ids=_guardar_ids)
        estado = apify_api.sondear(sesion, token, self.run_id, estado, "Leyendo comentarios", avanzar)
        crudos, motivo = apify_api.leer_dataset(sesion, token, self.dataset_id, p["max_resultados"])   # la corrida ya se pagó: se lee pase lo que pase
        if crudos is None:
            contados = apify_api.contar_dataset(sesion, token, self.dataset_id)
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
                raise ErrorFuente(f"La corrida de Apify {apify_api.frase_estado(estado)} sin resultados (corrida {self.run_id}); "
                                  "revísala en console.apify.com.")
            self.aviso = f"Apify {apify_api.frase_estado(estado)} (corrida {self.run_id}); se guardaron {self.resultados} resultados."

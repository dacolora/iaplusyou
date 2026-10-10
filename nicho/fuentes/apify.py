"""
Fuente `apify` (spec §3.5): reseñas de Amazon y comentarios de TikTok a través
de los actores de `apify_actores` (de pago, por resultado). Llave APIFY_TOKEN
SIEMPRE como cabecera `Authorization: Bearer …`, nunca en la URL (los logs de
gunicorn y del worker guardan URLs). `recolectar` arma la lista de corridas
con `apify_actores.corridas()` (una por link para junglee -- reseñas de
Amazon en el plan FREE --, una sola para los demás) y las corre con
`providers.apify.correr_lote` (compartido con `nicho/fuentes/plataforma.py`
y `referentes/fuentes/apify_adlibrary.py`, spec bloque 5) — este módulo solo
sabe qué actor llamar y cómo convertir sus ítems crudos en comentarios.
`resultados` es el número de ítems CRUDOS que devolvieron los datasets (no
solo los que traen texto): el worker anota el gasto como resultados × precio
del actor ("aprox."). Si un dataset no se puede leer, su cuota de
`resultados` cae al `itemCount` del dataset y, en último caso, al tope
aprobado de esa corrida — registrar de más es mejor que perder el registro
de un cobro. `run_id`/`dataset_id` (de la primera corrida lanzada) y
`corridas` (los registros de `correr_lote`, que `tareas.nicho._gasto_recoleccion`
ya lee) quedan en la fuente para poder rastrear cualquier cobro en
console.apify.com.
"""
import os

from flask_babel import gettext

import providers.apify as apify_api
from idiomas import N_
from nicho.fuentes import _http, apify_actores
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

# Copias de solo lectura, re-exportadas para quien ya importaba estos nombres
# desde este módulo. OJO: son copias tomadas una vez al importar — parchear un
# atributo de ESTE módulo (p.ej. `apify.PAUSA_SONDEO` en un test) NO cambia el
# comportamiento real, que lee las variables propias de `providers.apify`
# (`apify_api.PAUSA_SONDEO`, etc.); para eso hay que parchear `apify_api`.
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
        raise ErrorFuente(gettext("Falta APIFY_TOKEN en el .env del servidor."))
    return t


class FuenteApify(Fuente):
    tipo = "apify"
    de_pago = True

    def __init__(self):
        self.resultados = 0
        self.aviso = ""
        self.run_id = None
        self.dataset_id = None
        self.corridas = []

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
        self.resultados, self.aviso, self.corridas = 0, "", []
        self.run_id, self.dataset_id = None, None
        sesion = _http.sesion()
        actor = apify_actores.ACTORES[p["actor"]]
        avanzar(N_("Buscando"), actor["nombre"])
        corridas = apify_actores.corridas(p["actor"], p["links"], p["max_resultados"])
        res = apify_api.correr_lote(sesion, token, actor["actor"], corridas, N_("Leyendo comentarios"), avanzar, on_ids=self._anotar_corridas)
        self.resultados, self.aviso, self.corridas = res["resultados"], res["aviso"], res["corridas"]
        # La primera corrida lanzada (pudo cobrar aunque las demás no arrancaran o el lote
        # termine en error): queda en la fuente para poder rastrearla en console.apify.com.
        lanzadas = [c for c in res["corridas"] if c["run_id"]]
        if lanzadas:
            self.run_id, self.dataset_id = lanzadas[0]["run_id"], lanzadas[0]["dataset_id"]
        # `correr_lote` levanta ErrorFuente si no identifica ninguna corrida; un arranque incierto pudo cobrar. Acá
        # además: sin ítems que guardar y con alguna corrida que no terminó en SUCCEEDED o cuyo
        # dataset no se pudo leer (`motivo`), es el mismo "sin resultados" de siempre.
        if not res["items"] and any(c["estado"] != "SUCCEEDED" or c["motivo"] for c in res["corridas"]):
            raise ErrorFuente(gettext("Apify no entregó resultados (%(aviso)s); revísalos en console.apify.com.",
                                      aviso=res["aviso"]))
        for _, item in res["items"]:
            crudo = apify_actores.leer_item(p["actor"], item if isinstance(item, dict) else {})
            c = normalizar_comentario(crudo) if crudo else None
            if c:
                yield c

"""
Fuente genérica de una plataforma del registro (spec Parte 3 §4): busca
productos por palabra clave y trae reseñas de productos elegidos con los
actores de `nicho/fuentes/plataformas.py`, corriendo varias corridas de Apify
a la vez con `providers.apify.correr_lote`. `tipo` es la clave de la
plataforma (`amazon`, `meli`, `tiktok_shop`): los comentarios entran a la
base con esa `fuente`, `contexto` = título del producto y `extra.producto` =
su id, para que la página cuente reseñas por plataforma y los avatares citen
el producto. `resultados` son ítems crudos (lo que Apify cobra); `corridas`
y `run_id` sirven para rastrear un cobro en console.apify.com;
`conteo_por_producto` alimenta `producto_nicho.resenas_traidas` (no se
vuelve a pagar un producto ya traído). `aviso` queda con lo que no terminó
en SUCCEEDED; solo es error cuando no se entregó NADA y algo salió mal.
"""
import functools
import os

from flask_babel import gettext

import providers.apify as apify_api
from idiomas import N_
from nicho.fuentes import _http, plataformas
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario


def _token():
    t = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not t:
        raise ErrorFuente(gettext("Falta APIFY_TOKEN en el .env del servidor."))
    return t


class FuentePlataforma(Fuente):
    de_pago = True

    def __init__(self, clave):
        plataformas.nombre(clave)                       # ErrorFuente si la clave no existe
        self.tipo = self.clave = clave
        self.resultados = 0
        self.aviso = ""
        self.run_id = None
        self.dataset_id = None
        self.corridas = []
        self.conteo_por_producto = {}

    def tarifa(self, params=None):
        """Lo que cobra una recolección (reseñas): `_gasto_recoleccion` lo usa."""
        return plataformas.actor_resenas(self.clave)

    def tarifa_busqueda(self):
        return plataformas.actor_busqueda(self.clave)

    def probar(self):
        try:
            return apify_api.probar_token(_http.sesion(), _token())
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}

    def _correr(self, actor, corridas, etapa, avanzar):
        self.resultados, self.aviso, self.corridas, self.run_id, self.dataset_id = 0, "", [], None, None
        res = apify_api.correr_lote(_http.sesion(), _token(), actor, corridas, etapa, avanzar)
        self.resultados, self.aviso, self.corridas = res["resultados"], res["aviso"], res["corridas"]
        lanzadas = [c for c in res["corridas"] if c["run_id"]]
        if lanzadas:
            self.run_id, self.dataset_id = lanzadas[0]["run_id"], lanzadas[0]["dataset_id"]
        if not res["items"] and any(c["estado"] != "SUCCEEDED" for c in res["corridas"]):
            raise ErrorFuente(gettext("%(nombre)s no entregó nada: %(aviso)s", nombre=plataformas.nombre(self.clave), aviso=res["aviso"]))
        return res

    def buscar(self, consultas, pais, productos_por_consulta, avanzar=None):
        """Itera productos normalizados (con `consulta`), sin repetir ids."""
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        corridas = plataformas.entradas_busqueda(self.clave, consultas, pais, productos_por_consulta)
        avanzar(N_("Buscando"), plataformas.actor_busqueda(self.clave)["nombre"])
        res = self._correr(plataformas.actor_busqueda(self.clave)["actor"], corridas, N_("Buscando"), avanzar)
        conjunta = " | ".join(c for c in consultas if c)[:200]
        vistos = set()
        for indice, item in res["items"]:
            p = plataformas.leer_producto(self.clave, item, (pais or "").upper() or None)
            if not p or p["fuente_id"] in vistos:
                continue
            vistos.add(p["fuente_id"])
            etiqueta = corridas[indice].get("etiqueta") if indice < len(corridas) else None
            p["consulta"] = (etiqueta if etiqueta and etiqueta != "búsqueda" else conjunta)[:200]
            yield p

    def recolectar(self, params, avanzar=None):
        """`params = {"productos": [{fuente_id, url, titulo}], "resenas_por_producto": n, "pais": "SE"}`."""
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        p = dict(params or {})
        productos = [dict(x) for x in (p.get("productos") or []) if (x or {}).get("fuente_id")]
        corridas = plataformas.entradas_resenas(self.clave, productos, p.get("pais") or "", int(p.get("resenas_por_producto") or 100))
        por_id = {x["fuente_id"]: x for x in productos}
        por_producto = plataformas.PLATAFORMAS[self.clave]["resenas"]["por_producto"]
        self.conteo_por_producto = {}
        avanzar(N_("Buscando"), plataformas.actor_resenas(self.clave)["nombre"])
        res = self._correr(plataformas.actor_resenas(self.clave)["actor"], corridas, N_("Leyendo comentarios"), avanzar)
        for indice, item in res["items"]:
            r = plataformas.leer_resena(self.clave, item)
            if not r:
                continue
            producto = por_id.get(r.get("producto") or "")
            if producto is None and por_producto and indice < len(corridas):
                producto = por_id.get(corridas[indice].get("etiqueta") or "")
            if producto is None and len(productos) == 1:
                producto = productos[0]
            pid = producto["fuente_id"] if producto else (r.get("producto") or None)
            c = normalizar_comentario({"fuente_id": r["fuente_id"], "texto": r["texto"], "url": r.get("url") or (producto or {}).get("url"),
                                       "contexto": (producto or {}).get("titulo"), "puntuacion": r.get("puntuacion"), "fecha": r.get("fecha"),
                                       "extra": {"producto": pid, "plataforma": self.clave}})
            if c:
                if pid:
                    self.conteo_por_producto[pid] = self.conteo_por_producto.get(pid, 0) + 1
                yield c


def fabrica(clave):
    """Lo que `nicho.fuentes.por_tipo` devuelve para una plataforma: se llama
    sin argumentos, como las clases de las otras fuentes."""
    return functools.partial(FuentePlataforma, clave)

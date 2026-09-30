"""La investigación de punta a punta con todo falso (spec Parte 3): consultas → buscar → seleccionar →
reseñas → redes → avatares, corriendo las tareas encoladas en orden como lo haría el worker."""
import json
import re

import pytest

FRASE = "las pantuflas me quitaron el dolor del talón"


class PlatFalsa:
    """Fuente de plataforma falsa: 3 productos por búsqueda y 10 reseñas por producto."""
    de_pago = True
    fallar_busqueda = set()
    llamadas = []

    def __init__(self, clave):
        self.tipo = self.clave = clave
        self.resultados, self.aviso, self.run_id, self.corridas, self.conteo_por_producto = 0, "", None, [], {}

    def tarifa_busqueda(self):
        return {"actor": f"x~{self.clave}-buscar", "nombre": f"Búsqueda {self.clave}", "usd_por_resultado": 0.003}

    def tarifa(self, params=None):
        return {"actor": f"x~{self.clave}-resenas", "nombre": f"Reseñas {self.clave}", "usd_por_resultado": 0.001}

    def buscar(self, consultas, pais, n, avanzar=None):
        PlatFalsa.llamadas.append(("buscar", self.clave))
        from nicho.fuentes.base import ErrorFuente
        if self.clave in PlatFalsa.fallar_busqueda:
            raise ErrorFuente(f"{self.clave} se cayó")
        self.run_id, self.corridas = f"rb-{self.clave}", [{"run_id": f"rb-{self.clave}"}]
        for k in range(3):
            self.resultados += 1
            yield {"fuente_id": f"{self.clave}-{k}", "titulo": f"Pantufla {self.clave} {k}", "marca": None, "precio": 10.0, "moneda": "MXN",
                   "estrellas": 4.5, "n_resenas": 100 - k, "url": f"https://x/{self.clave}/{k}", "imagen": None, "consulta": consultas[0], "extra": {}}

    def recolectar(self, params, avanzar=None):
        PlatFalsa.llamadas.append(("resenas", self.clave))
        self.run_id, self.corridas = f"rr-{self.clave}", [{"run_id": f"rr-{self.clave}"}]
        for p in params["productos"]:
            for k in range(10):
                self.resultados += 1
                self.conteo_por_producto[p["fuente_id"]] = self.conteo_por_producto.get(p["fuente_id"], 0) + 1
                yield {"fuente_id": f"{p['fuente_id']}-r{k}", "texto": f"Reseña {k} de {p['fuente_id']}: {FRASE}.", "url": p["url"],
                       "contexto": p["titulo"], "puntuacion": 5, "fecha": None, "extra": {"producto": p["fuente_id"], "plataforma": self.clave}}


class RedFalsa:
    tipo = "youtube"
    de_pago = False

    def __init__(self):
        self.resultados, self.aviso, self.run_id = 0, "", None

    def recolectar(self, params, avanzar=None):
        for k in range(10):
            yield {"fuente_id": f"yt{k}", "texto": f"Video {k}: {FRASE}, lo recomiendo.", "url": None, "contexto": "Review", "puntuacion": 3,
                   "fecha": None, "extra": {}}


def _claude(texto, max_tokens):
    """Claude falso: responde según qué prompt le llega."""
    from nicho import avatares
    if avatares.MARCA_COMPLETAR in texto:
        return '{"sub_avatares": []}', 10, 2
    if "búsquedas cortas" in texto:
        return '{"consultas": ["pantuflas dolor talón", "pantuflas ortopédicas"]}', 300, 30
    if "de verdad del nicho" in texto:
        ids = [int(x) for x in re.findall(r"(?m)^(\d+) · ", texto)]
        return json.dumps({"productos": [{"id": i, "relevante": True, "motivo": "del nicho"} for i in ids]}), 900, 80
    ids = [int(x) for x in re.findall(r"\[(\d+)\]", texto)]
    if "Agrúpalos por el DESEO" in texto:
        return json.dumps({"nucleos": [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r", "comentarios": ids}]}), 2000, 200
    sub = {"base": "emocion", "nombre": "Carla / La del turno largo", "deseo": "Quiero llegar a la noche sin dolor", "demografia": "Mujer 40-50 (inferido)",
           "edad_rango": "40-50", "emocion": "Agotamiento", "identidad": {"quiere_que_vean": "fuerte", "cree_de_si": "aguanta", "quiere_lograr": "cuidar"},
           "soluciones_previas": [{"que": "Plantillas", "por_que_fallo": ["duras"]}], "situaciones": ["Turno largo", "Al llegar a casa"],
           "comportamiento": "Se quita los zapatos", "conciencia": {"nivel": "consciente_de_la_solucion", "detalle": "busca"},
           "encaje_producto": "Alivio del talón", "tono": "Práctico", "palabras_clave": ["talón", "turno", "alivio"],
           "evidencia": [{"comentario_id": ids[0], "cita": FRASE}, {"comentario_id": ids[1], "cita": FRASE}]}
    return json.dumps({"sub_avatares": [sub]}), 1500, 600


@pytest.fixture()
def mundo(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from nicho import avatares, fuentes
    from tareas import investigacion, nicho  # noqa: F401  (registra las tareas)
    cola_mem = []

    def _encolar(job_id, tipo, payload, **kw):
        if any(t["job_id"] == job_id and not t.get("hecha") for t in cola_mem):
            return False
        cola_mem.append({"id": len(cola_mem) + 1, "job_id": job_id, "tipo": tipo, "payload": payload, "intentos": 1,
                         "max_intentos": kw.get("max_intentos", 1)})
        return True

    def _por_tipo(tipo):
        if tipo in ("amazon", "meli", "tiktok_shop"):
            return lambda: PlatFalsa(tipo)
        if tipo == "youtube":
            return RedFalsa
        raise KeyError(tipo)

    monkeypatch.setattr(trabajos, "encolar", _encolar)
    monkeypatch.setattr(fuentes, "por_tipo", _por_tipo)
    monkeypatch.setattr(avatares, "_llamar", _claude)
    monkeypatch.setenv("APIFY_TOKEN", "t")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    PlatFalsa.fallar_busqueda, PlatFalsa.llamadas = set(), []

    def correr(detener_en=None):
        corridas = []
        while True:
            pendientes = [t for t in cola_mem if not t.get("hecha")]
            if not pendientes:
                return corridas
            t = pendientes[0]
            etiqueta = t["tipo"] + ":" + str(t["payload"].get("plataforma") or t["payload"].get("fuente") or "")
            if detener_en and etiqueta == detener_en:
                return corridas
            t["hecha"] = True
            corridas.append(etiqueta)
            try:
                tareas.REGISTRO[t["tipo"]](t)
            except Exception as e:  # noqa: BLE001 — como el worker: la tarea falla y la cola sigue
                t["error"] = str(e)

    return {"cola": cola_mem, "correr": correr}


def _arrancar(plataformas=("amazon", "meli"), redes=("youtube",)):
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = datos.crear_estudio("acme", "Pantuflas", producto="HappyFlops", tema="pantuflas para dolor de pies", pais="MX")
    est = inv.estimar({}, "MX", list(plataformas), list(redes), inv.TOPES_DEFECTO)
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial("pantuflas para dolor de pies", "MX", list(plataformas), list(redes),
                                                               inv.TOPES_DEFECTO, estimado=est))
    ti.avanzar("acme", eid)
    return eid


def test_investigacion_de_punta_a_punta(mundo):
    import gastos
    from nicho import calidad, datos
    eid = _arrancar()
    assert mundo["correr"]() == ["nicho_inv_consultas:", "nicho_inv_buscar:amazon", "nicho_inv_buscar:meli", "nicho_inv_seleccionar:",
                                 "nicho_recolectar:amazon", "nicho_recolectar:meli", "nicho_recolectar:youtube", "nicho_generar_avatares:"]
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "lista" and all(i["pasos"][p]["estado"] == "hecho" for p in i["orden"]), i
    assert i["consultas"] == ["pantuflas dolor talón", "pantuflas ortopédicas"] and i["elegidos"] == {"amazon": ["amazon-0", "amazon-1", "amazon-2"], "meli": ["meli-0", "meli-1", "meli-2"]}
    conteos = datos.contar_por_fuente("acme", eid)
    assert conteos["amazon"]["total"] == 30 and conteos["meli"]["total"] == 30 and conteos["youtube"]["total"] == 10
    assert all(p["resenas_traidas"] == 10 for p in datos.productos_nicho("acme", eid))
    nuevos = datos.lista_avatares("acme")["nuevos"]
    assert [x["avatar"]["nombre"] for x in nuevos] == ["Carla / La del turno largo"] and calidad.faltantes(nuevos[0]["avatar"]) == []
    total_gasto = round(sum(g["usd"] for g in gastos.historial("acme")), 4)
    assert total_gasto == round(i["gastado_usd"], 4) and 0 < i["gastado_usd"] <= i["aprobado_usd"]


def test_una_tienda_caida_no_frena_la_investigacion(mundo):
    from nicho import datos
    PlatFalsa.fallar_busqueda = {"meli"}
    eid = _arrancar()
    corridas = mundo["correr"]()
    assert "nicho_recolectar:meli" not in corridas and corridas[-1] == "nicho_generar_avatares:"
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["buscar:meli"]["estado"] == "error" and "se cayó" in i["pasos"]["buscar:meli"]["aviso"]
    assert i["pasos"]["resenas:meli"]["estado"] == "vacio" and i["estado"] == "lista"


def test_reanudar_despues_de_un_reinicio_no_repite_lo_pagado(mundo):
    import tareas
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = _arrancar()
    antes = mundo["correr"](detener_en="nicho_recolectar:meli")
    assert antes[-1] == "nicho_recolectar:amazon"
    viva = [t for t in mundo["cola"] if not t.get("hecha")][0]
    viva["hecha"] = True                                              # el worker se reinició con esta tarea en curso
    tareas.AL_INTERRUMPIR["nicho_recolectar"](viva, "reinicio del worker")
    assert datos.investigacion("acme", eid)["estado"] == "interrumpida"
    datos.actualizar_investigacion("acme", eid, inv.reanudar)
    assert ti.avanzar("acme", eid) == "resenas:meli"
    despues = mundo["correr"]()
    assert despues == ["nicho_recolectar:meli", "nicho_recolectar:youtube", "nicho_generar_avatares:"]
    assert PlatFalsa.llamadas.count(("buscar", "amazon")) == 1 and PlatFalsa.llamadas.count(("resenas", "amazon")) == 1
    assert datos.investigacion("acme", eid)["estado"] == "lista"

"""Nicho Parte 4 de punta a punta (spec 2026-09-30 §5): un estudio en Colombia con Mercado Libre (local),
Walmart (otro mercado: EE. UU.) y AliExpress (compradores de todo el mundo), con FuentePlataforma de verdad
sobre un Apify falso que entrega la salida real recortada de la verificación, y Claude falso."""
import json
import os
import re

import pytest

_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "nicho", "plataformas")
POR_PRODUCTO = 6
PROMPTS = []
FRASE = "se me quitó el dolor en los talones"


def _fixture(nombre):
    with open(os.path.join(_DIR, nombre), encoding="utf-8") as f:
        return json.load(f)


def _multiplicar(base, urls, id_de_url, campo_id, campo_producto):
    """POR_PRODUCTO reseñas por link pedido, cada una con id propio y el id del producto pedido."""
    salida = []
    for url in urls:
        pid = id_de_url(url)
        for k in range(POR_PRODUCTO):
            r = dict(base[k % len(base)])
            r[campo_id], r[campo_producto] = f"{r[campo_id]}-{pid}-{k}", pid
            salida.append(r)
    return salida


class ApifyFalso:
    """Reemplaza `providers.apify.correr_lote`: anota cada entrada y responde según el actor."""

    def __init__(self):
        self.entradas = []

    def __call__(self, sesion, token, actor, corridas, etapa, avanzar=None, max_simultaneas=5, on_ids=None):
        items, registros = [], []
        for indice, c in enumerate(corridas):
            self.entradas.append((actor, c["entrada"]))
            propios = self._items(actor, c["entrada"])
            items += [(indice, it) for it in propios]
            registros.append({"indice": indice, "etiqueta": c.get("etiqueta"), "run_id": f"run-{len(self.entradas)}",
                              "dataset_id": f"ds-{len(self.entradas)}", "estado": "SUCCEEDED", "resultados": len(propios), "motivo": ""})
        return {"items": items, "resultados": len(items), "corridas": registros, "aviso": ""}

    @staticmethod
    def _items(actor, entrada):
        if actor == "karamelo~mercado-libre-listings-scraper":
            return _fixture("meli_busqueda.json")
        if actor == "s-r~walmart-scraper":
            return _fixture("walmart_busqueda.json")
        if actor == "dami_studio~aliexpress-products-scraper":
            return _fixture("aliexpress_busqueda.json")
        if actor == "karamelo~mercadolibre-review-scraper":
            return _multiplicar(_fixture("meli_resenas.json")[:2], entrada["productUrls"],
                                lambda u: re.search(r"MCO-?\d+", u).group(0).replace("-", ""), "reviewId", "productId")
        if actor == "apt_marble~walmart-reviews-scraper":
            return _multiplicar(_fixture("walmart_resenas.json")[:2], entrada["products"], lambda u: u.rsplit("/", 1)[-1], "reviewId", "productId")
        if actor == "axlymxp~aliexpress-reviews-scraper":
            return _multiplicar(_fixture("aliexpress_resenas.json")[:2], entrada["productUrls"],
                                lambda u: re.search(r"(\d+)\.html", u).group(1), "review_id", "product_id")
        raise AssertionError(f"actor inesperado: {actor}")


def _claude(texto, max_tokens):
    """Claude falso: responde según qué prompt le llega y guarda cada prompt."""
    from nicho import avatares
    PROMPTS.append(texto)
    if avatares.MARCA_COMPLETAR in texto:
        return '{"sub_avatares": []}', 10, 2
    if "búsquedas cortas" in texto:
        return json.dumps({"consultas": {"es": ["botella con marcador de tiempo", "botella motivacional"],
                                         "en": ["water bottle time marker", "motivational water bottle"]}}), 300, 40
    if "de verdad del nicho" in texto:
        ids = [int(x) for x in re.findall(r"(?m)^(\d+) · ", texto)]
        return json.dumps({"productos": [{"id": i, "relevante": True, "motivo": "del nicho"} for i in ids]}), 900, 80
    ids = [int(x) for x in re.findall(r"\[(\d+)\]", texto)]
    if "Agrúpalos por el DESEO" in texto:
        return json.dumps({"nucleos": [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r", "comentarios": ids}]}), 2000, 200
    con_frase = [int(x) for x in re.findall(r"(?m)^\[(\d+)\] \(meli .*" + FRASE, texto)]
    sub = {"base": "emocion", "nombre": "Carla / La del turno largo", "deseo": "Quiero llegar a la noche sin dolor",
           "demografia": "Mujer 40-50 (inferido)", "edad_rango": "40-50", "emocion": "Agotamiento",
           "identidad": {"quiere_que_vean": "fuerte", "cree_de_si": "aguanta", "quiere_lograr": "cuidar"},
           "soluciones_previas": [{"que": "Plantillas", "por_que_fallo": ["duras"]}], "situaciones": ["Turno largo", "Al llegar a casa"],
           "comportamiento": "Se quita los zapatos", "conciencia": {"nivel": "consciente_de_la_solucion", "detalle": "busca"},
           "encaje_producto": "Alivio del talón", "tono": "Práctico", "palabras_clave": ["talón", "turno", "alivio"],
           "evidencia": [{"comentario_id": i, "cita": FRASE} for i in con_frase[:2]]}
    return json.dumps({"sub_avatares": [sub]}), 1500, 600


@pytest.fixture()
def cadena(base_temporal, monkeypatch):
    import providers.apify as apify_api
    import tareas
    import trabajos
    from nicho import avatares
    from tareas import investigacion, nicho  # noqa: F401  (registra las tareas)
    cola_mem, apify = [], ApifyFalso()

    def _encolar(job_id, tipo, payload, **kw):
        if any(t["job_id"] == job_id and not t.get("hecha") for t in cola_mem):
            return False
        cola_mem.append({"id": len(cola_mem) + 1, "job_id": job_id, "tipo": tipo, "payload": payload, "intentos": 1,
                         "max_intentos": kw.get("max_intentos", 1)})
        return True

    monkeypatch.setattr(trabajos, "encolar", _encolar)
    monkeypatch.setattr(apify_api, "correr_lote", apify)
    monkeypatch.setattr(avatares, "_llamar", _claude)
    monkeypatch.setenv("APIFY_TOKEN", "t")
    PROMPTS.clear()

    def correr():
        corridas = []
        while True:
            pendientes = [t for t in cola_mem if not t.get("hecha")]
            if not pendientes:
                return corridas
            t = pendientes[0]
            t["hecha"] = True
            corridas.append(t["tipo"] + ":" + str(t["payload"].get("plataforma") or t["payload"].get("fuente") or ""))
            try:
                tareas.REGISTRO[t["tipo"]](t)
            except Exception as e:  # noqa: BLE001 — como el worker: la tarea falla y la cola sigue
                t["error"] = str(e)

    return {"cola": cola_mem, "apify": apify, "correr": correr}


def test_otro_mercado_de_punta_a_punta(cadena):
    import gastos
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    tema = "botellas de agua con marcador de tiempo"
    eid = datos.crear_estudio("acme", "Botellas", producto="Botella con horario", tema=tema, pais="CO")
    plats = ["meli", "walmart", "aliexpress"]
    est = inv.estimar({}, "CO", plats, [], inv.TOPES_DEFECTO)
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial(tema, "CO", plats, [], inv.TOPES_DEFECTO, estimado=est))
    ti.avanzar("acme", eid)
    assert cadena["correr"]() == ["nicho_inv_consultas:", "nicho_inv_buscar:meli", "nicho_inv_buscar:walmart", "nicho_inv_buscar:aliexpress",
                                  "nicho_inv_seleccionar:", "nicho_recolectar:meli", "nicho_recolectar:walmart", "nicho_recolectar:aliexpress",
                                  "nicho_generar_avatares:"]
    assert not [t for t in cadena["cola"] if t.get("error")]
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "lista", i
    assert i["consultas"] == ["botella con marcador de tiempo", "botella motivacional"]
    assert i["consultas_por_idioma"]["en"] == ["water bottle time marker", "motivational water bottle"]
    # cada tienda buscó en su idioma y en su sitio
    entradas = cadena["apify"].entradas
    meli = [e for a, e in entradas if a == "karamelo~mercado-libre-listings-scraper"]
    assert [e["keyword"] for e in meli] == ["botella con marcador de tiempo", "botella motivacional"]
    assert all(e["country"] == "https://listado.mercadolibre.com.co/" for e in meli)
    assert [e["query"] for a, e in entradas if a == "s-r~walmart-scraper"] == ["water bottle time marker", "motivational water bottle"]
    assert [e["searchQueries"] for a, e in entradas if a == "dami_studio~aliexpress-products-scraper"] == [["water bottle time marker"],
                                                                                                         ["motivational water bottle"]]
    # cada reseña quedó marcada con su país y su mercado
    marcas = {}
    for c in datos.comentarios_para_generar("acme", eid):
        marcas.setdefault(c["fuente"], set()).add((c["extra"]["pais"], c["extra"]["mercado"]))
    assert marcas == {"meli": {("CO", "local")}, "walmart": {("US", "otro")}, "aliexpress": {("BR", "otro"), ("ES", "otro")}}
    # Claude vio la marca y la regla, con lo local primero
    nucleos = next(p for p in PROMPTS if "Agrúpalos por el DESEO" in p)
    assert "otro mercado: Estados Unidos" in nucleos and "otro mercado: Brasil" in nucleos and "Mercado del estudio: Colombia." in nucleos
    assert re.match(r"\[\d+\] \(meli ", nucleos.split("COMENTARIOS:\n", 1)[1].splitlines()[0])
    # el gasto de las reseñas de AliExpress cuenta su arranque y todo cabe en lo aprobado
    ali = [g for g in gastos.historial("acme") if (g["extra"] or {}).get("actor") == "axlymxp~aliexpress-reviews-scraper"]
    assert len(ali) == 1 and ali[0]["usd"] == 0.05                                 # 12 reseñas × 0.003 + 1 corrida × 0.01
    total = round(sum(g["usd"] for g in gastos.historial("acme")), 4)
    assert total == round(i["gastado_usd"], 4) and 0 < i["gastado_usd"] <= i["aprobado_usd"]
    assert datos.lista_avatares("acme")["nuevos"]                                    # los avatares se generaron

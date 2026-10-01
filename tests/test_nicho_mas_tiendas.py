"""Nicho Parte 4 (spec 2026-09-30): Walmart y AliExpress, otro mercado, búsquedas por idioma y reseñas marcadas, sin red."""
import pytest  # noqa: F401  (las tareas siguientes agregan pruebas que lo usan)


def test_estimar_no_rechaza_otro_mercado(monkeypatch):
    from nicho import avatares, investigacion as inv
    monkeypatch.setattr(avatares, "estimar_costo_maximo", lambda: {"usd": 0.4})
    e = inv.estimar({}, "CO", ["meli", "amazon", "walmart", "aliexpress"], [], inv.TOPES_DEFECTO)
    assert [(f["clave"], f["mercado"], f["sitio"]) for f in e["filas"]] == [("meli", "local", "CO"), ("amazon", "otro", "US"),
                                                                            ("walmart", "otro", "US"), ("aliexpress", "local", "CO")]
    assert [(f["busqueda_usd"], f["resenas_usd"]) for f in e["filas"]] == [(0.12, 1.05), (0.18, 1.35), (0.09, 1.5), (0.03, 4.51)]
    assert e["total_usd"] == round(0.12 + 1.05 + 0.18 + 1.35 + 0.09 + 1.5 + 0.03 + 4.51 + e["claude_usd"] + 0.4, 2)


def test_mas_resenados_desempatan_por_vendidos(monkeypatch):
    """AliExpress no trae número de reseñas: entre empates mandan sus pedidos (spec Parte 4 §1.1)."""
    from nicho import avatares, investigacion as inv
    productos = [{"id": 1, "plataforma": "aliexpress", "fuente_id": "A", "titulo": "Poco vendida", "n_resenas": None, "extra": {"vendidos": 10}},
                 {"id": 2, "plataforma": "aliexpress", "fuente_id": "B", "titulo": "Muy vendida", "n_resenas": None, "extra": {"vendidos": 4025}},
                 {"id": 3, "plataforma": "aliexpress", "fuente_id": "C", "titulo": "Sin dato", "n_resenas": None, "extra": {}},
                 {"id": 4, "plataforma": "aliexpress", "fuente_id": "D", "titulo": "Con reseñas", "n_resenas": 3, "extra": {"vendidos": "x"}}]
    assert inv.elegir(productos, {p["id"]: {"relevante": True} for p in productos}, 3) == {"aliexpress": ["D", "B", "A"]}
    vistos = []
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: vistos.append(t) or ('{"productos": [{"id": 1, "relevante": true}]}', 10, 5))
    inv.seleccion_con_claude({"tema": "t"}, productos)
    assert vistos[0].index("Con reseñas") < vistos[0].index("Muy vendida") < vistos[0].index("Poco vendida") < vistos[0].index("Sin dato")


def test_gasto_cuenta_el_arranque_de_cada_corrida(base_temporal):
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    from tareas import nicho as tn
    tarifa = {"actor": "axlymxp~aliexpress-reviews-scraper", "nombre": "Reseñas de AliExpress", "usd_por_resultado": 0.003, "usd_por_corrida": 0.01}

    class Fuente:
        def __init__(self, n):
            self.resultados, self.corridas, self.run_id = n, [{"run_id": "r1"}], "r1"

        def tarifa(self, params=None):
            return tarifa
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    assert ti._gasto_apify("acme", eid, {"id": 7}, "buscar:aliexpress", Fuente(0), tarifa) == 0.01      # sin resultados igual cobró el arranque
    assert tn._gasto_recoleccion("acme", eid, {"id": 8}, Fuente(5), {}) == 0.03                        # 5 × 0.003 + 0.01
    assert ti._gasto_apify("acme", eid, {"id": 9}, "buscar:aliexpress", Fuente(0), {**tarifa, "usd_por_corrida": 0.0}) == 0.0
    filas = {g["referencia"]: g for g in gastos.historial("acme")}
    assert filas[f"recoleccion:{eid}:buscar:aliexpress:t7"]["usd"] == 0.01 and filas[f"recoleccion:{eid}:t8"]["usd"] == 0.03
    assert filas[f"recoleccion:{eid}:t8"]["extra"]["usd_por_corrida"] == 0.01 and f"recoleccion:{eid}:buscar:aliexpress:t9" not in filas

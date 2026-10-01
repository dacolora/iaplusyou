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


def test_consultas_por_idioma_en_una_llamada(monkeypatch):
    from nicho import avatares, investigacion as inv
    llamadas = []

    def _llamar(texto, max_tokens):
        llamadas.append((texto, max_tokens))
        return ('{"consultas": {"es": ["botella con horario", "botella motivacional", "botella con horario"], '
                '"en": ["water bottle time marker", "motivational bottle"]}}'), 400, 60
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    est = {"tema": "botellas con marcador de tiempo", "producto": ""}
    por_idioma, te, ts = inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])
    assert por_idioma == {"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker", "motivational bottle"]}
    assert (te, ts) == (400, 60) and len(llamadas) == 1
    texto, max_tokens = llamadas[0]
    assert "español (es)" in texto and "inglés (en)" in texto and '"en": ["...", "..."]' in texto and "de 2 a 3" in texto
    assert max_tokens == inv.MAX_TOKENS_CONSULTAS >= 1000
    # un idioma de más que no llega queda fuera (su tienda usará las del país); el del país es obligatorio
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": {"es": ["a uno", "b dos"]}}', 10, 5))
    assert inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])[0] == {"es": ["a uno", "b dos"]}
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": {"en": ["a uno", "b dos"]}}', 10, 5))
    with pytest.raises(avatares.AnalisisInvalido) as e:
        inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])
    assert e.value.tokens_entrada == 10
    # la lista suelta (la forma de la Parte 3) cuenta como la del primer idioma
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": ["a uno", "b dos"]}', 10, 5))
    assert inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])[0] == {"es": ["a uno", "b dos"]}
    assert inv.consultas_con_claude(est, "CO", 3)[0] == ["a uno", "b dos"]


def test_idiomas_necesarios_y_estimado_por_idioma(monkeypatch):
    from nicho import avatares, investigacion as inv
    assert inv.idiomas_necesarios("CO", ["meli", "amazon", "walmart", "aliexpress", "tiktok_shop"]) == ["es", "en"]
    assert inv.idiomas_necesarios("SE", ["amazon", "meli"]) == ["sv", "es"] and inv.idiomas_necesarios("BR", []) == ["pt"]
    assert inv.idiomas_necesarios("US", ["amazon", "walmart", "aliexpress"]) == ["en"]
    un_idioma, dos = inv._tokens_claude(2, inv.TOPES_DEFECTO, 1), inv._tokens_claude(2, inv.TOPES_DEFECTO, 2)
    assert dos[0] > un_idioma[0] and dos[1] > un_idioma[1] and inv._tokens_claude(2, inv.TOPES_DEFECTO) == un_idioma
    monkeypatch.setattr(avatares, "estimar_costo_maximo", lambda: {"usd": 0.4})
    vistos, real = [], inv._tokens_claude
    monkeypatch.setattr(inv, "_tokens_claude", lambda n, topes, n_idiomas=1: vistos.append((n, n_idiomas)) or real(n, topes, n_idiomas))
    inv.estimar({}, "CO", ["meli", "walmart"], [], inv.TOPES_DEFECTO)
    assert vistos == [(2, 2)]


def test_ejecutar_consultas_guarda_las_de_cada_idioma(base_temporal, monkeypatch):
    from nicho import avatares, datos, investigacion as inv
    from tareas import investigacion as ti
    pedidos = []

    def _llamar(texto, max_tokens):
        pedidos.append(texto)
        return ('{"consultas": {"es": ["botella con horario", "botella motivacional"], '
                '"en": ["water bottle time marker", "motivational bottle"]}}'), 300, 40
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    monkeypatch.setattr(ti.trabajos, "encolar", lambda *a, **k: True)
    eid = datos.crear_estudio("acme", "X", tema="botellas con marcador de tiempo", pais="CO")
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial("botellas", "CO", ["meli", "walmart"], [], inv.TOPES_DEFECTO,
                                                               estimado={"total_usd": 5.0}))
    ti.ejecutar_consultas({"id": 3, "payload": {"cliente": "acme", "estudio_id": eid}, "intentos": 1, "max_intentos": 2})
    i = datos.investigacion("acme", eid)
    assert i["consultas"] == ["botella con horario", "botella motivacional"] and i["pasos"]["consultas"]["estado"] == "hecho"
    assert i["consultas_por_idioma"] == {"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker", "motivational bottle"]}
    assert "español (es)" in pedidos[0] and "inglés (en)" in pedidos[0]


def test_cada_tienda_busca_en_su_idioma(base_temporal, monkeypatch):
    from nicho import datos, fuentes, investigacion as inv
    from tareas import investigacion as ti
    vistas = {}

    class Falsa:
        de_pago, resultados, aviso, corridas, run_id = True, 0, "", [], None

        def __init__(self, clave):
            self.clave = clave

        def tarifa_busqueda(self):
            return {"actor": "x", "nombre": "x", "usd_por_resultado": 0.001}

        def buscar(self, consultas, pais, n, avanzar=None):
            vistas[self.clave] = list(consultas)
            return iter(())
    monkeypatch.setattr(fuentes, "por_tipo", lambda tipo: (lambda: Falsa(tipo)))
    monkeypatch.setattr(ti.trabajos, "encolar", lambda *a, **k: True)
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    i = inv.crear_inicial("t", "CO", ["meli", "walmart", "amazon"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 5.0})
    i = inv.marcar_paso({**i, "consultas": ["botella con horario", "botella motivacional"],
                         "consultas_por_idioma": {"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker"]}},
                        "consultas", "hecho")
    datos.iniciar_investigacion("acme", eid, i)
    for k, plat in enumerate(("meli", "walmart")):
        ti.ejecutar_buscar({"id": 10 + k, "payload": {"cliente": "acme", "estudio_id": eid, "plataforma": plat}, "intentos": 1, "max_intentos": 1})
    assert vistas == {"meli": ["botella con horario", "botella motivacional"], "walmart": ["water bottle time marker"]}
    assert not datos.investigacion("acme", eid)["pasos"]["buscar:walmart"].get("aviso")
    # sin las de su idioma, la tienda usa las del país y el paso lo dice
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas_por_idioma": {"es": x["consultas"]}})
    ti.ejecutar_buscar({"id": 12, "payload": {"cliente": "acme", "estudio_id": eid, "plataforma": "amazon"}, "intentos": 1, "max_intentos": 1})
    assert vistas["amazon"] == ["botella con horario", "botella motivacional"]
    assert datos.investigacion("acme", eid)["pasos"]["buscar:amazon"]["aviso"] == ti.NOTA_IDIOMA


def test_seleccion_pone_primero_el_mercado_local():
    from nicho import avatares

    def c(i, fuente, mercado=None):
        extra = {"mercado": mercado, "pais": "US" if mercado == "otro" else "CO"} if mercado else {}
        return {"id": i, "fuente": fuente, "texto": "x" * 30, "puntuacion": 5, "fecha": None, "extra": extra}
    comentarios = [c(1, "aliexpress", "otro"), c(2, "aliexpress", "local"), c(3, "walmart", "otro"), c(4, "meli", "local"), c(5, "youtube")]
    assert [x["id"] for x in avatares.seleccionar(comentarios)] == [2, 4, 5, 1, 3]
    assert [x["id"] for x in avatares.seleccionar(comentarios, max_n=3)] == [2, 4, 5]


def test_prompts_marcan_el_otro_mercado_y_llevan_la_regla():
    from nicho import avatares
    est = {"producto": "Botella", "tema": "botellas", "idioma": "es", "pais": "CO"}
    comentarios = [{"id": 1, "fuente": "meli", "texto": "Me encanta la botella", "puntuacion": 5, "contexto": "Botella 1L",
                    "extra": {"mercado": "local", "pais": "CO"}},
                   {"id": 2, "fuente": "walmart", "texto": "Love this bottle", "puntuacion": 4, "contexto": None,
                    "extra": {"mercado": "otro", "pais": "US"}},
                   {"id": 3, "fuente": "aliexpress", "texto": "Muito boa", "puntuacion": 5, "contexto": None,
                    "extra": {"mercado": "otro", "pais": "PL"}}]
    p = avatares.armar_prompt_nucleos(est, comentarios)
    assert "[1] (meli · 5 · Botella 1L) Me encanta" in p and "[2] (walmart · 4 · otro mercado: Estados Unidos) Love this bottle" in p
    assert "[3] (aliexpress · 5 · otro mercado: PL) Muito boa" in p
    assert "Mercado del estudio: Colombia." in p and "el tono" in p and p.index("Mercado del estudio") < p.index("COMENTARIOS:")
    nucleo = {"nombre": "N", "deseo": "Quiero", "resumen": "r"}
    assert "Mercado del estudio: Colombia." in avatares.armar_prompt_subs(est, nucleo, comentarios)
    assert "Mercado del estudio: Colombia." in avatares.armar_prompt_completar(est, nucleo, comentarios, [(0, {}, ["deseo"])])
    solo_locales = [comentarios[0], {"id": 4, "fuente": "texto", "texto": "Otro comentario", "puntuacion": None, "contexto": None}]
    assert "Mercado del estudio" not in avatares.armar_prompt_nucleos(est, solo_locales)
    assert "otro mercado" not in avatares.armar_prompt_subs(est, nucleo, solo_locales)
    assert "otro mercado" not in avatares.armar_prompt_completar(est, nucleo, solo_locales, [(0, {}, ["deseo"])])

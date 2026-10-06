"""Nicho Parte 4 (spec 2026-09-30): Walmart y AliExpress, otro mercado, búsquedas por idioma y reseñas marcadas, sin red."""
import pytest  # noqa: F401  (las tareas siguientes agregan pruebas que lo usan)


def test_estimar_no_rechaza_otro_mercado(monkeypatch):
    from nicho import avatares, investigacion as inv
    monkeypatch.setattr(avatares, "estimar_costo_maximo", lambda: {"usd": 0.4})
    e = inv.estimar({}, "CO", ["meli", "amazon", "walmart", "aliexpress"], [], inv.TOPES_DEFECTO)
    assert [(f["clave"], f["mercado"], f["sitio"]) for f in e["filas"]] == [("meli", "local", "CO"), ("amazon", "otro", "US"),
                                                                            ("walmart", "otro", "US"), ("aliexpress", "local", "CO")]
    # precios del plan FREE de Apify, verificados 2026-10-01: meli reseñas 1500 × 0.0015 = 2.25; amazon búsqueda 60 × 0.005 = 0.3;
    # amazon reseñas (junglee, fix 3 2026-10-01): una corrida por producto, 10 reseñas por corrida (tope real
    # del plan FREE) -- 15 × (10 × 0.006) = 0.9, el peor caso REAL, sin el mínimo de US$ 0,50 de la corrida
    assert [(f["busqueda_usd"], f["resenas_usd"]) for f in e["filas"]] == [(0.12, 2.25), (0.3, 0.9), (0.09, 1.5), (0.03, 4.51)]
    assert e["total_usd"] == round(0.12 + 2.25 + 0.3 + 0.9 + 0.09 + 1.5 + 0.03 + 4.51 + e["claude_usd"] + 0.4, 2)


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
    # la salida es siempre el tope de las dos llamadas (el pensamiento adaptativo se cobra como
    # salida y nunca lo pasa, medido en la prueba real del 2026-10-01): un idioma de más solo sube
    # la entrada, nunca la salida
    assert dos[0] > un_idioma[0] and dos[1] == un_idioma[1] == inv.MAX_TOKENS_CONSULTAS + inv.MAX_TOKENS_SELECCION
    assert inv._tokens_claude(2, inv.TOPES_DEFECTO) == un_idioma
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


def test_topes_de_salida_de_claude_alcanzan_con_varias_tiendas():
    """Ola final F1/F2: el pensamiento adaptativo gasta del mismo tope; 300 productos × ~25 tokens ya pasan
    de 6 000, y el tope sigue bajo el límite del SDK sin streaming (≈ 21 333)."""
    from nicho import investigacion as inv
    assert inv.MAX_TOKENS_SELECCION >= 25 * inv.MAX_FILAS_SELECCION + 4000 and inv.MAX_TOKENS_SELECCION <= 21000
    assert inv.MAX_TOKENS_CONSULTAS >= 4000


def test_topes_de_salida_de_avatares_no_se_cortan_por_el_pensamiento():
    """Segunda prueba de centavos en producción (2026-10-01, estudio 3 de colorado_forja): núcleos se
    cortó con el tope viejo (4 000) para apenas 94 comentarios porque el pensamiento adaptativo de
    claude-sonnet-5 gasta del mismo tope (`_llamar` no manda `thinking`); mismo remedio que arriba."""
    from nicho import avatares
    for tope in (avatares.MAX_TOKENS_NUCLEOS, avatares.MAX_TOKENS_SUBS, avatares.MAX_TOKENS_COMPLETAR):
        assert 12000 <= tope <= 21000


def test_seleccion_toma_por_turnos_entre_tiendas(monkeypatch):
    """Ola final F3: AliExpress no trae número de reseñas; con el corte de filas lleno no queda fuera: las
    tiendas se turnan y cada una conserva su orden de más reseñadas."""
    from nicho import avatares, investigacion as inv
    amazon = [{"id": i, "plataforma": "amazon", "fuente_id": f"A{i}", "titulo": f"Amazon {i}", "n_resenas": 100 * i, "extra": {}}
              for i in (1, 2, 3)]
    ali = [{"id": 10 + i, "plataforma": "aliexpress", "fuente_id": f"X{i}", "titulo": f"Ali {i}", "n_resenas": None,
            "extra": {"vendidos": i}} for i in (1, 2, 3)]
    r = inv._repartir_por_plataforma(amazon + ali, 4)
    assert [p["id"] for p in r] == [13, 3, 12, 2]                     # aliexpress y amazon (orden de clave), dos de cada una
    assert [p["id"] for p in inv._repartir_por_plataforma(amazon, 2)] == [3, 2]
    assert inv._repartir_por_plataforma(ali, 10) == sorted(ali, key=inv._mas_resenado) and inv._repartir_por_plataforma([], 5) == []
    vistos = []
    monkeypatch.setattr(inv, "MAX_FILAS_SELECCION", 4)
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: vistos.append(t) or ('{"productos": [{"id": 3, "relevante": true}]}', 10, 5))
    inv.seleccion_con_claude({"tema": "t"}, amazon + ali)
    lista = vistos[0].split("reseñas):\n", 1)[1]
    assert "Ali 3" in lista and "Ali 2" in lista and "Amazon 3" in lista and "Amazon 2" in lista
    assert "Ali 1" not in lista and "Amazon 1" not in lista


def test_cambiar_el_pais_del_estudio_remarca_el_mercado(base_temporal, monkeypatch):
    """Ola final F4: `mercado` es relativo al país del estudio; si el estudio cambia de país se recalcula en la
    misma escritura (solo las filas que cambian)."""
    import db
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    datos.agregar_comentarios("acme", eid, "walmart", [{"fuente_id": "w1", "texto": "Love this bottle",
                                                        "extra": {"producto": "1", "plataforma": "walmart", "pais": "US", "mercado": "otro"}}])
    datos.agregar_comentarios("acme", eid, "meli", [{"fuente_id": "m1", "texto": "Me encanta", "extra": {"pais": "CO", "mercado": "local"}}])
    datos.agregar_comentarios("acme", eid, "aliexpress", [{"fuente_id": "a1", "texto": "Great", "extra": {"pais": "US", "mercado": "local"}}])
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": "t1", "texto": "Sin país"}])
    otro = datos.crear_estudio("acme", "Y", tema="t", pais="CO")
    datos.agregar_comentarios("acme", otro, "walmart", [{"fuente_id": "w1", "texto": "Love it", "extra": {"pais": "US", "mercado": "otro"}}])
    antes = {c["fuente_id"]: c for c in datos.comentarios_para_generar("acme", eid)}
    monkeypatch.setattr(db, "ahora", lambda: "2099-01-01T00:00:00")
    assert datos.actualizar_estudio("acme", eid, pais="us")
    despues = {c["fuente_id"]: c for c in datos.comentarios_para_generar("acme", eid)}
    assert despues["w1"]["extra"] == {"producto": "1", "plataforma": "walmart", "pais": "US", "mercado": "local"}
    assert despues["m1"]["extra"] == {"pais": "CO", "mercado": "otro"}
    assert despues["w1"]["actualizado_en"] == despues["m1"]["actualizado_en"] == "2099-01-01T00:00:00"
    for clave in ("a1", "t1"):                                         # ya estaba bien / sin país: no se escribe
        assert despues[clave]["extra"] == antes[clave]["extra"] and despues[clave]["actualizado_en"] == antes[clave]["actualizado_en"]
    assert datos.comentarios_para_generar("acme", otro)[0]["extra"]["mercado"] == "otro"          # otro estudio: intacto
    assert datos.estudio("acme", eid)["pais"] == "US"


def test_consultas_por_idioma_toleran_la_forma_de_la_respuesta(monkeypatch):
    """Ola final F7: respuesta sin «consultas», claves con mayúsculas o región y un idioma de más con una sola búsqueda."""
    from nicho import avatares, investigacion as inv
    est = {"tema": "botellas", "producto": ""}

    def responde(texto):
        monkeypatch.setattr(avatares, "_llamar", lambda t, m: (texto, 10, 5))
    responde('{"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker", "motivational bottle"]}')
    assert inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])[0] == {
        "es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker", "motivational bottle"]}
    responde('{"consultas": {"ES": ["botella con horario", "botella motivacional"], "en-US": ["water bottle time marker", "motivational bottle"]}}')
    assert inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])[0] == {
        "es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker", "motivational bottle"]}
    responde('{"consultas": {"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker"]}}')
    assert inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])[0]["en"] == ["water bottle time marker"]
    responde('{"consultas": {"es": ["botella con horario"], "en": ["water bottle time marker", "motivational bottle"]}}')
    with pytest.raises(avatares.AnalisisInvalido):                       # el del país sigue pidiendo min(2, n)
        inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])


def test_estimado_de_avatares_cuenta_lo_que_se_manda():
    """Ola final F9: el prompt manda la línea entera de cada comentario (`_linea`) y, con algún comentario de otro
    mercado, la regla en cada llamada; el estimado cuenta las dos cosas."""
    from nicho import avatares

    def c(i, mercado):
        return {"id": i, "fuente": "walmart", "texto": "x" * 400, "puntuacion": 4, "fecha": None, "contexto": "Botella de vidrio 1L",
                "extra": {"mercado": mercado, "pais": "US" if mercado == "otro" else "CO"}}
    llamadas = 1 + 2 * avatares.MAX_NUCLEOS
    fijo = avatares.TOKENS_SUB_JSON * avatares.MAX_NUCLEOS * avatares.MAX_SUBS_POR_NUCLEO
    locales = [c(i, "local") for i in range(1, 26)]
    lineas = int(sum(len(avatares._linea(x)) for x in locales) * avatares.TOKENS_POR_CARACTER)
    assert lineas > int(400 * 25 * avatares.TOKENS_POR_CARACTER)
    assert avatares.estimar_costo(locales)["tokens_entrada"] == lineas * 3 + avatares.TOKENS_PROMPT * llamadas + fijo
    mezcla = locales[:-1] + [c(99, "otro")]
    lineas = int(sum(len(avatares._linea(x)) for x in mezcla) * avatares.TOKENS_POR_CARACTER)
    regla = avatares.TOKENS_REGLA_OTRO_MERCADO
    assert regla >= len(avatares.REGLA_OTRO_MERCADO) * avatares.TOKENS_POR_CARACTER
    assert avatares.estimar_costo(mezcla)["tokens_entrada"] == lineas * 3 + (avatares.TOKENS_PROMPT + regla) * llamadas + fijo
    # el peor caso de la investigación lleva la línea más larga y la regla: nunca queda corto frente a uno real
    peor = avatares.comentarios_peor_caso()
    assert len(avatares.seleccionar(peor)) == avatares.MAX_COMENTARIOS and all(x["extra"]["mercado"] == "otro" for x in peor)
    assert avatares.estimar_costo_maximo()["tokens_entrada"] >= avatares.estimar_costo(mezcla * 30)["tokens_entrada"]

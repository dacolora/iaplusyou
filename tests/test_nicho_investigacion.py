"""Pure tests for nicho/investigacion.py state machine."""
import pytest
from nicho import investigacion as inv
from nicho.fuentes import plataformas as plat


class TestSiguientePaso:
    """Tests para siguiente_paso()"""

    def test_siguiente_paso_consultas_pendiente(self):
        """First step is always consultas."""
        i = {"version": 1, "estado": "consultas", "pasos": {}}
        assert inv.siguiente_paso(i) == "consultas"

    def test_siguiente_paso_lista_no_avanza(self):
        """When done, siguiente_paso returns None."""
        i = {"version": 1, "estado": "lista", "pasos": {}}
        assert inv.siguiente_paso(i) is None

    def test_siguiente_paso_detenida_no_avanza(self):
        """When stopped, siguiente_paso returns None."""
        i = {"version": 1, "estado": "detenida", "pasos": {}}
        assert inv.siguiente_paso(i) is None

    def test_siguiente_paso_interrumpida_no_avanza(self):
        """When interrupted, siguiente_paso returns None."""
        i = {"version": 1, "estado": "interrumpida", "pasos": {}}
        assert inv.siguiente_paso(i) is None

    def test_siguiente_paso_sigue_orden(self):
        """Steps follow PASOS_CADENA order."""
        i = {
            "version": 1, "estado": "buscando",
            "pasos": {"consultas": {"estado": "hecho"}}
        }
        # Debe devolver el próximo paso sin hacer
        paso = inv.siguiente_paso(i)
        assert paso == "buscar:amazon"

    def test_siguiente_paso_retoma_en_curso(self):
        """If a step is en_curso, return it for resumption."""
        i = {
            "version": 1, "estado": "buscando",
            "pasos": {
                "consultas": {"estado": "hecho"},
                "buscar:amazon": {"estado": "en_curso"}
            }
        }
        assert inv.siguiente_paso(i) == "buscar:amazon"

    def test_siguiente_paso_salta_vacios(self):
        """Pasos with vacio estado are skipped."""
        i = {
            "version": 1, "estado": "buscando",
            "pasos": {
                "consultas": {"estado": "hecho"},
                "buscar:amazon": {"estado": "vacio"},
                "buscar:meli": {"estado": None}
            }
        }
        # Debe devolver buscar:meli que está None
        assert inv.siguiente_paso(i) == "buscar:meli"


class TestMarcarPaso:
    """Tests para marcar_paso()"""

    def test_marcar_paso_nuevo(self):
        """Mark a new step."""
        i = {"version": 1, "estado": "consultas", "pasos": {}}
        i2 = inv.marcar_paso(i, "consultas", "hecho", usd=0.01, productos=25)

        assert i2["pasos"]["consultas"]["estado"] == "hecho"
        assert i2["pasos"]["consultas"]["usd"] == 0.01
        assert i2["pasos"]["consultas"]["productos"] == 25

    def test_marcar_paso_no_modifica_original(self):
        """marcar_paso returns new dict, doesn't modify original."""
        i = {"version": 1, "pasos": {}}
        i2 = inv.marcar_paso(i, "consultas", "hecho", usd=0.01)

        assert "consultas" not in i["pasos"]
        assert "consultas" in i2["pasos"]

    def test_marcar_paso_actualiza_existente(self):
        """Update an existing step."""
        i = {"pasos": {"consultas": {"estado": "en_curso", "usd": 0.0}}}
        i2 = inv.marcar_paso(i, "consultas", "hecho", usd=0.02)

        assert i2["pasos"]["consultas"]["estado"] == "hecho"
        assert i2["pasos"]["consultas"]["usd"] == 0.02


class TestResumen:
    """Tests para resumen()"""

    def test_resumen_basico(self):
        """Build summary dict for UI."""
        i = {
            "estado": "resenas",
            "consultas": ["skincare", "facial"],
            "pasos": {
                "consultas": {"estado": "hecho", "usd": 0.01},
                "buscar:amazon": {"estado": "hecho", "productos": 57},
                "seleccionar": {"estado": "hecho", "relevantes": 15},
            },
            "gastado_usd": 1.25, "aprobado_usd": 5.00
        }
        r = inv.resumen(i)

        assert r["consultas"] == ["skincare", "facial"]
        assert r["productos"] == 57
        assert r["relevantes"] == 15
        assert r["gastado"] == 1.25
        assert r["aprobado"] == 5.00
        assert r["estado"] == "resenas"

    def test_resumen_vacio(self):
        """Resumen on empty investigacion."""
        i = {}
        r = inv.resumen(i)

        assert r["consultas"] == []
        assert r["productos"] == 0
        assert r["relevantes"] == 0


class TestPuedeReanudar:
    """Tests para puede_reanudar()"""

    def test_puede_reanudar_detenida(self):
        """detenida state allows resumption."""
        assert inv.puede_reanudar("detenida") is True

    def test_puede_reanudar_interrumpida(self):
        """interrumpida state allows resumption."""
        assert inv.puede_reanudar("interrumpida") is True

    def test_puede_reanudar_lista(self):
        """lista state does not allow resumption."""
        assert inv.puede_reanudar("lista") is False

    def test_puede_reanudar_en_curso(self):
        """en_curso state does not allow resumption."""
        assert inv.puede_reanudar("generando") is False


class TestEstimar:
    """Tests para estimar()"""

    def test_estimar_sin_plataformas(self):
        """Estimate with no platforms costs only Claude + avatares."""
        result = inv.estimar(
            {}, pais="SE",
            plataformas_elegidas=[],
            redes_elegidas=[],
            topes=inv.TOPES_DEFECTO
        )
        # Solo Claude + avatares
        assert "total_usd" in result
        assert result["total_usd"] > 0
        assert result["claude_usd"] > 0
        assert result["avatares_usd"] > 0

    def test_estimar_una_plataforma(self):
        """Estimate includes search + reviews for one platform."""
        result = inv.estimar(
            {}, pais="SE",
            plataformas_elegidas=["amazon"],
            redes_elegidas=[],
            topes=inv.TOPES_DEFECTO
        )
        assert len(result["filas"]) == 1
        assert result["filas"][0]["clave"] == "amazon"
        assert result["filas"][0]["busqueda_usd"] > 0
        assert result["filas"][0]["resenas_usd"] > 0
        assert result["total_usd"] > 0


class TestCrearInicial:
    """Tests para crear_inicial()"""

    def test_crear_inicial_estructura(self):
        """crear_inicial returns valid structure."""
        # MX (no SE): la investigación real valida cobertura por país (R8) y
        # meli no tiene tienda en Suecia -- MX tiene tanto Amazon como MELI.
        inv_data = inv.crear_inicial(
            tema="skincare",
            pais="MX",
            plataformas_elegidas=["amazon", "meli"],
            redes_elegidas=["reddit"],
            topes=inv.TOPES_DEFECTO
        )

        assert inv_data["version"] == 1
        assert inv_data["estado"] == "consultas"
        assert inv_data["tema"] == "skincare"
        assert inv_data["pais"] == "MX"
        assert inv_data["plataformas"] == ["amazon", "meli"]
        assert inv_data["redes"] == ["reddit"]
        # pasos ya no nace vacío: viene prellenado "pendiente" para cada paso del orden.
        assert set(inv_data["pasos"]) == set(inv_data["orden"])
        assert all(p["estado"] == "pendiente" for p in inv_data["pasos"].values())
        assert inv_data["gastado_usd"] == 0.0
        assert inv_data["aprobado_usd"] > 0


class TestPlataformas:
    """Tests para nicho/fuentes/plataformas.py"""

    def test_disponibles_amazon_se(self):
        """Amazon is available in SE."""
        assert "amazon" in plat.disponibles("SE")

    def test_disponibles_meli_se(self):
        """MELI is not available in SE."""
        assert "meli" not in plat.disponibles("SE")

    def test_disponibles_meli_co(self):
        """MELI is available in CO."""
        assert "meli" in plat.disponibles("CO")

    def test_disponibles_tiktok_shop_ubiquo(self):
        """TikTok Shop is available everywhere."""
        assert "tiktok_shop" in plat.disponibles("SE")
        assert "tiktok_shop" in plat.disponibles("CO")
        assert "tiktok_shop" in plat.disponibles("US")

    def test_dominio_amazon_se(self):
        """Amazon domain for SE is se."""
        assert plat.dominio("amazon", "SE") == "se"

    def test_dominio_amazon_co(self):
        """Amazon has no store in Colombia (ruling R8): dominio is None."""
        assert plat.dominio("amazon", "CO") is None

    def test_idioma_se(self):
        """Language for SE is Swedish."""
        assert plat.idioma("SE") == "sv"

    def test_idioma_co(self):
        """Language for CO is Spanish."""
        assert plat.idioma("CO") == "es"

    def test_estimar_busqueda_amazon(self):
        """Estimate search cost for Amazon."""
        costo = plat.estimar_busqueda("amazon", 2, 20)
        # 2 × 20 = 40 resultados × $0.005 = $0.20 (plan FREE de Apify, verificado 2026-10-01)
        assert costo > 0
        assert isinstance(costo, float)

    def test_estimar_resenas_amazon(self):
        """Estimate review cost for Amazon (junglee~amazon-reviews-scraper, por_producto=false: una corrida)."""
        costo = plat.estimar_resenas("amazon", 15, 100)
        # 15 × 40 (tope por producto) = 600 resultados × $0.006 = $3.6
        assert costo > 0
        assert isinstance(costo, float)

    def test_entradas_busqueda_amazon(self):
        """Build Apify input for Amazon search."""
        entradas = plat.entradas_busqueda("amazon", ["skincare", "facial"], "SE", 20)
        assert len(entradas) == 1
        assert "categoryOrProductUrls" in entradas[0]["entrada"]

    def test_entradas_busqueda_meli(self):
        """Build Apify input for MELI search."""
        entradas = plat.entradas_busqueda("meli", ["skincare"], "CO", 20)
        assert len(entradas) == 1
        assert "keyword" in entradas[0]["entrada"]

    def test_leer_producto_amazon(self):
        """Normalize Amazon product item."""
        item = {
            "asin": "B01234567",
            "title": "Skincare Set",
            "brand": "FakeBrand",
            "price": 29.99,
            "stars": 4.5,
            "reviewsCount": 123,
            "url": "https://amazon.se/...",
            "image": "https://..."
        }
        prod = plat.leer_producto("amazon", item)

        assert prod is not None
        assert prod["fuente_id"] == "B01234567"
        assert prod["titulo"] == "Skincare Set"
        assert prod["precio"] == 29.99
        assert prod["estrellas"] == 4.5
        assert prod["n_resenas"] == 123

    def test_leer_producto_incompleto(self):
        """leer_producto returns None for incomplete item."""
        item = {"asin": "B01234567"}  # Missing title
        prod = plat.leer_producto("amazon", item)
        assert prod is None

    def test_entradas_resenas_amazon(self):
        """Build Apify input for Amazon reviews: junglee~amazon-reviews-scraper (FREE plan) runs
        ONE run PER PRODUCT (never joins several productUrls: the FREE plan only reads the first
        link of a run), capped at 10 reviews per product (the plan's real per-run limit)."""
        productos = [
            {"fuente_id": "B0000TEST1", "url": "https://www.amazon.com/dp/B0000TEST1", "titulo": "P1"},
            {"fuente_id": "B0000TEST2", "url": "https://www.amazon.com/dp/B0000TEST2", "titulo": "P2"}
        ]
        entradas = plat.entradas_resenas("amazon", productos, "US", 30)      # 30 pedidas, recortadas al tope de 10

        assert len(entradas) == 2
        assert entradas[0]["entrada"]["productUrls"] == [{"url": "https://www.amazon.com/dp/B0000TEST1"}]
        assert entradas[1]["entrada"]["productUrls"] == [{"url": "https://www.amazon.com/dp/B0000TEST2"}]
        assert entradas[0]["entrada"]["maxReviews"] == 10 and entradas[0]["max_items"] == 10

    def test_leer_resena_amazon(self):
        """Normalize Amazon review (junglee~amazon-reviews-scraper, 2026-10-01): reviewTitle/reviewDescription/
        ratingScore, never userId/userProfileLink even when the actor sends them."""
        item = {
            "reviewId": "R123",
            "reviewTitle": "Great",
            "reviewDescription": "Great product!",
            "ratingScore": 5,
            "date": "2026-09-22",
            "productAsin": "B0TEST1234",
            "productOriginalAsin": "B0TEST1234",
            "input": "https://www.amazon.com/dp/B0TEST1234",
            "userId": "secret-buyer-id",
            "userProfileLink": "https://www.amazon.com/gp/profile/secret-buyer-id",
        }
        resena = plat.leer_resena("amazon", item)

        assert resena is not None
        assert resena["fuente_id"] == "R123"
        assert resena["texto"] == "Great. Great product!"
        assert resena["puntuacion"] == 5
        assert resena["producto"] == "B0TEST1234" and resena["producto_pedido"] == "B0TEST1234"
        assert "userId" not in resena and "userProfileLink" not in resena


class TestConstantes:
    """Tests para constantes exportadas"""

    def test_estados_cadena_validos(self):
        """ESTADOS_CADENA contains expected states."""
        assert "consultas" in inv.ESTADOS_CADENA
        assert "lista" in inv.ESTADOS_CADENA
        assert "detenida" in inv.ESTADOS_CADENA

    def test_pasos_cadena_validos(self):
        """PASOS_CADENA contains expected steps."""
        assert "consultas" in inv.PASOS_CADENA
        assert "buscar:amazon" in inv.PASOS_CADENA
        assert "seleccionar" in inv.PASOS_CADENA
        assert "generar" in inv.PASOS_CADENA

    def test_topes_defecto(self):
        """TOPES_DEFECTO has required keys."""
        assert "consultas" in inv.TOPES_DEFECTO
        assert "productos_por_consulta" in inv.TOPES_DEFECTO
        assert "productos_elegidos" in inv.TOPES_DEFECTO
        assert "resenas_por_producto" in inv.TOPES_DEFECTO

    def test_idiomas_cobertura(self):
        """IDIOMAS has reasonable country coverage."""
        assert len(inv.IDIOMAS) > 10
        assert inv.IDIOMAS.get("CO") == "es"
        assert inv.IDIOMAS.get("SE") == "sv"


def _inv(plataformas=("amazon", "meli"), redes=("reddit",), **pasos):
    from nicho import investigacion as inv
    i = inv.crear_inicial("tofflor", "SE", list(plataformas), list(redes), inv.TOPES_DEFECTO, estimado={"total_usd": 5.0})
    for paso, estado in pasos.items():
        i = inv.marcar_paso(i, paso, estado)
    return i


def test_orden_y_crear_inicial_prellenado():
    from nicho import investigacion as inv
    assert inv.orden_pasos(["amazon", "meli"], ["reddit"]) == ["consultas", "buscar:amazon", "buscar:meli", "seleccionar", "resenas:amazon", "resenas:meli", "redes:reddit", "generar"]
    i = _inv()
    assert i["orden"] == inv.orden_pasos(["amazon", "meli"], ["reddit"]) and i["aprobado_usd"] == 5.0 and i["gastado_usd"] == 0.0
    assert all(i["pasos"][p] == {"estado": "pendiente"} for p in i["orden"]) and i["estado"] == "consultas" and i["elegidos"] == {}
    assert i["iniciada_en"] and i["terminada_en"] is None and i["detenida_por"] is None
    assert inv.normalizar_topes({"consultas": "9", "productos_por_consulta": 1, "productos_elegidos": None, "resenas_por_producto": 1000}) == \
        {"consultas": 4, "productos_por_consulta": 5, "productos_elegidos": 15, "resenas_por_producto": 200}
    with pytest.raises(ValueError):
        inv.normalizar_topes({"consultas": "muchas"})


def test_siguiente_paso_por_orden_y_estados():
    from nicho import investigacion as inv
    i = _inv()
    assert inv.siguiente_paso(i) == "consultas"
    i = inv.marcar_paso(i, "consultas", "en_curso")
    assert inv.siguiente_paso(i) == "consultas" and i["estado"] == "consultas"
    i = inv.marcar_paso(i, "consultas", "hecho", usd=0.01)
    assert i["estado"] == "buscando"                                                     # avanzar() encola buscar:amazon con este estado, sin marcarlo todavía
    i = inv.marcar_paso(i, "buscar:amazon", "error", aviso="x")
    assert inv.siguiente_paso(i) == "buscar:meli" and i["estado"] == "buscando" and i["gastado_usd"] == 0.01
    for paso, estado in (("buscar:meli", "vacio"), ("seleccionar", "hecho"), ("resenas:amazon", "hecho"), ("resenas:meli", "saltado"), ("redes:reddit", "saltado")):
        i = inv.marcar_paso(i, paso, estado, usd=0.5 if estado == "hecho" else 0)
    # el próximo a correr es "generar" (redes:reddit ya quedó "saltado"): avanzar() lo encola enseguida.
    assert inv.siguiente_paso(i) == "generar" and i["estado"] == "generando" and i["gastado_usd"] == 1.01
    i = inv.marcar_paso(i, "generar", "hecho", usd=0.3)
    assert inv.terminada(i) and i["estado"] == "lista" and i["terminada_en"] and inv.siguiente_paso(i) is None
    d = inv.detener(_inv(), "sin tema")
    assert d["estado"] == "detenida" and d["detenida_por"] == "sin tema" and inv.siguiente_paso(d) is None and inv.puede_reanudar(d["estado"])
    assert inv.estado_por_paso("resenas:meli") == "resenas" and inv.estado_por_paso("generar") == "generando"
    viejo = {"estado": "consultas", "pasos": {"consultas": {"estado": "hecho"}}, "plataformas": ["meli"], "redes": []}
    assert inv.siguiente_paso(viejo) == "buscar:meli"                                    # sin `orden`: se deriva de plataformas/redes


def test_estimar_suma_plataformas_claude_y_avatares(monkeypatch):
    from nicho import avatares, investigacion as inv
    monkeypatch.setattr(avatares, "estimar_costo_maximo", lambda: {"usd": 0.4})
    e = inv.estimar({}, "SE", ["amazon", "tiktok_shop"], ["reddit"], inv.TOPES_DEFECTO)
    # amazon búsqueda 60 × 0.005 = 0.3 (plan FREE de Apify, verificado 2026-10-01); amazon reseñas
    # (junglee, fix 3 2026-10-01): una corrida por producto, 10 reseñas por corrida (el tope real
    # del plan FREE) -- 15 productos × (10 × 0.006) = 0.9, el peor caso REAL, sin el mínimo
    assert [f["clave"] for f in e["filas"]] == ["amazon", "tiktok_shop"] and e["filas"][0]["busqueda_usd"] == 0.3 and e["filas"][0]["resenas_usd"] == 0.9
    # claude_usd sale de _tokens_claude (amazon + tiktok_shop buscan las dos en sueco: un idioma)
    entrada_cl, salida_cl = inv._tokens_claude(2, inv.TOPES_DEFECTO, 1)
    assert e["avatares_usd"] == 0.4 and e["claude_usd"] == inv._centavos(inv.costo_claude(entrada_cl, salida_cl)) > 0
    assert e["total_usd"] == round(0.3 + 0.9 + 0.27 + 6.75 + e["claude_usd"] + 0.4, 2) and e["texto"]
    otro = inv.estimar({}, "SE", ["meli"], [], inv.TOPES_DEFECTO)["filas"][0]           # MELI no está en Suecia: busca en México
    assert (otro["mercado"], otro["sitio"]) == ("otro", "MX")


def test_elegir_y_params_redes():
    from nicho import investigacion as inv
    productos = [{"id": 1, "plataforma": "amazon", "fuente_id": "A", "n_resenas": 10}, {"id": 2, "plataforma": "amazon", "fuente_id": "B", "n_resenas": 500},
                 {"id": 3, "plataforma": "amazon", "fuente_id": "C", "n_resenas": None}, {"id": 4, "plataforma": "meli", "fuente_id": "M", "n_resenas": 3}]
    decisiones = {1: {"relevante": True, "motivo": "sí"}, 2: {"relevante": True, "motivo": "sí"}, 3: {"relevante": True, "motivo": "sí"}, 4: {"relevante": False, "motivo": "no"}}
    assert inv.elegir(productos, decisiones, 2) == {"amazon": ["B", "A"]}
    assert inv.elegir(productos, {}, 2) == {}
    i = {**_inv(), "consultas": ["tofflor mot fotsmärta", "ortopediska tofflor"]}
    assert inv.params_redes("reddit", i) == {"palabras_clave": "tofflor mot fotsmärta OR ortopediska tofflor", "subreddits": [], "links": [],
                                             "max_posts": 25, "max_comentarios_por_post": 50, "periodo": "year"}
    assert inv.params_redes("youtube", i) == {"palabras_clave": "tofflor mot fotsmärta | ortopediska tofflor", "links": [], "max_videos": 10,
                                              "max_comentarios_por_video": 100, "idioma": "sv", "region": "SE"}


def test_consultas_y_seleccion_con_claude(monkeypatch):
    from nicho import avatares, investigacion as inv
    llamadas = []

    def _llamar(texto, max_tokens):
        llamadas.append(texto)
        if "consultas" in texto.split("Responde")[-1]:
            # Nota: el quinto elemento del brief original era "x"*90 escrito
            # DENTRO de un literal de una sola comilla -- Python no evalúa esa
            # multiplicación ahí (queda como texto crudo `"x"*90`), lo que
            # rompe el JSON. Se quita: los otros 4 elementos ya cubren trim,
            # deduplicado y exclusión de vacíos.
            return '```json\n{"consultas": ["tofflor mot fotsmärta", " ortopediska tofflor ", "tofflor mot fotsmärta", ""]}\n```', 700, 40
        return '{"productos": [{"id": 1, "relevante": true, "motivo": "pantufla del nicho"}, {"id": 2, "relevante": false, "motivo": "es un calcetín"}, {"id": 99, "relevante": true}]}', 900, 60
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    est = {"tema": "pantuflas para dolor de pies", "producto": "HappyFlops", "idioma": "sv"}
    consultas, te, ts = inv.consultas_con_claude(est, "SE")
    assert consultas == ["tofflor mot fotsmärta", "ortopediska tofflor"] and (te, ts) == (700, 40)
    assert "sv" in llamadas[0] or "sueco" in llamadas[0]
    productos = [{"id": 1, "plataforma": "amazon", "titulo": "Tofflor", "marca": "A", "precio": 10, "moneda": "SEK", "estrellas": 4.5, "n_resenas": 100},
                 {"id": 2, "plataforma": "amazon", "titulo": "Strumpor", "marca": None, "precio": None, "moneda": None, "estrellas": None, "n_resenas": None}]
    decisiones, te, ts = inv.seleccion_con_claude(est, productos)
    assert decisiones == {1: {"relevante": True, "motivo": "pantufla del nicho"}, 2: {"relevante": False, "motivo": "es un calcetín"}}
    assert (te, ts) == (900, 60) and "Strumpor" in llamadas[1]
    assert inv.costo_claude(1000, 100) == avatares.costo_real(1000, 100)
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ("no es json", 10, 5))
    with pytest.raises(avatares.AnalisisInvalido) as e:
        inv.consultas_con_claude(est, "SE")
    assert e.value.tokens_entrada == 10 and e.value.tokens_salida == 5
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": ["solo una"]}', 10, 5))
    with pytest.raises(avatares.AnalisisInvalido):
        inv.consultas_con_claude(est, "SE")                                               # menos de 2 consultas no sirve


def test_tokens_claude_salida_es_siempre_el_tope_de_las_dos_llamadas():
    """El pensamiento adaptativo de claude-sonnet-5 se cobra como salida y nunca pasa `max_tokens`
    (medido en la prueba real del 2026-10-01): la salida del estimado es siempre la suma de los
    dos topes, sin importar cuántas plataformas o idiomas entren."""
    from nicho import investigacion as inv
    for n in (0, 1, 2, 5):
        for k in (1, 2, 3):
            assert inv._tokens_claude(n, inv.TOPES_DEFECTO, k)[1] == inv.MAX_TOKENS_CONSULTAS + inv.MAX_TOKENS_SELECCION


def test_estimar_costo_maximo():
    from nicho import avatares
    e = avatares.estimar_costo_maximo()
    assert e["comentarios"] == avatares.MAX_COMENTARIOS and e["usd"] > 0 and e["suficientes"]
    # Peor caso real: los DOS topes de seleccionar() llenos a la vez (una reseña
    # real llega a 2 000 caracteres, así que MAX_COMENTARIOS puede sumar
    # MAX_CARACTERES completo) -- no solo MAX_COMENTARIOS × 250 --, contado con la
    # línea entera que va al prompt (`_linea`) y la regla de otro mercado en cada llamada.
    falsos = avatares.comentarios_peor_caso()
    assert len(falsos) == avatares.MAX_COMENTARIOS and sum(len(c["texto"]) for c in falsos) == avatares.MAX_CARACTERES
    tokens_texto = int(sum(len(avatares._linea(c)) for c in falsos) * avatares.TOKENS_POR_CARACTER)
    assert tokens_texto > int(avatares.MAX_CARACTERES * avatares.TOKENS_POR_CARACTER)
    assert e["tokens_entrada"] == (tokens_texto * 3
                                   + (avatares.TOKENS_PROMPT + avatares.TOKENS_REGLA_OTRO_MERCADO) * (1 + 2 * avatares.MAX_NUCLEOS)
                                   + avatares.TOKENS_SUB_JSON * avatares.MAX_NUCLEOS * avatares.MAX_SUBS_POR_NUCLEO)


def test_reanudar_y_job_de_paso():
    from nicho import investigacion as inv
    i = inv.crear_inicial("t", "CO", ["amazon", "meli"], ["reddit"], inv.TOPES_DEFECTO, estimado={"total_usd": 3.0})
    for paso, estado in (("consultas", "hecho"), ("buscar:amazon", "error"), ("buscar:meli", "en_curso")):
        i = inv.marcar_paso(i, paso, estado)
    i = {**inv.detener(i, "x"), "ultimo_error": "boom"}
    r = inv.reanudar(i)
    assert r["pasos"]["buscar:meli"]["estado"] == "pendiente" and r["pasos"]["buscar:amazon"]["estado"] == "error"   # lo que cobró no se repite solo
    assert r["estado"] == "buscando" and r["detenida_por"] is None and r["ultimo_error"] is None and r["terminada_en"] is None
    j = inv.detener(inv.marcar_paso(inv.marcar_paso(i, "buscar:meli", "hecho"), "seleccionar", "error"), "Claude")
    assert inv.reanudar(j)["pasos"]["seleccionar"]["estado"] == "pendiente"                                      # Claude sí se reintenta
    assert inv.job_de_paso("acme", 3, "buscar:meli") == "nicho:acme:3:inv:buscar:meli"
    assert inv.job_de_paso("acme", 3, "resenas:meli") == "nicho:acme:3:recolectar:meli"
    assert inv.job_de_paso("acme", 3, "redes:youtube") == "nicho:acme:3:recolectar:youtube"
    assert inv.job_de_paso("acme", 3, "generar") == "nicho:acme:3:generar"


def test_consultas_respetan_el_tope_aprobado(monkeypatch):
    """La búsqueda nunca gasta más que su línea del estimado: Claude recibe el
    tope aprobado y lo que sobra se recorta (ola final, F3)."""
    from nicho import avatares
    llamadas = []

    def _llamar(texto, max_tokens):
        llamadas.append(texto)
        return '{"consultas": ["a uno", "b dos", "c tres", "d cuatro"]}', 50, 10
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    est = {"tema": "pantuflas", "producto": ""}
    consultas, _, _ = inv.consultas_con_claude(est, "SE", 1)
    assert consultas == ["a uno"] and "de 1 a 1" in llamadas[-1]
    consultas, _, _ = inv.consultas_con_claude(est, "SE", 3)
    assert consultas == ["a uno", "b dos", "c tres"] and "de 2 a 3" in llamadas[-1]
    assert len(inv.consultas_con_claude(est, "SE", 99)[0]) == inv.LIMITES["consultas"][1]          # nunca más que el límite
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": ["sola"]}', 10, 5))
    assert inv.consultas_con_claude(est, "SE", 1)[0] == ["sola"]                                   # con tope 1, una sirve


def test_pasos_y_etiquetas_de_las_tiendas_nuevas():
    from nicho import investigacion as inv
    assert inv.PASOS_CADENA == ("consultas", "buscar:amazon", "buscar:meli", "buscar:tiktok_shop", "buscar:walmart", "buscar:aliexpress",
                                "seleccionar", "resenas:amazon", "resenas:meli", "resenas:tiktok_shop", "resenas:walmart", "resenas:aliexpress",
                                "redes:reddit", "redes:youtube", "generar")
    assert set(inv.ETIQUETAS_PASO) == set(inv.PASOS_CADENA)
    assert inv.orden_pasos(["walmart", "aliexpress"], []) == ["consultas", "buscar:walmart", "buscar:aliexpress", "seleccionar",
                                                             "resenas:walmart", "resenas:aliexpress", "generar"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

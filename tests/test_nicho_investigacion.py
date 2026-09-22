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
            plataformas=[],
            redes=[],
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
            plataformas=["amazon"],
            redes=[],
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
        inv_data = inv.crear_inicial(
            tema="skincare",
            pais="SE",
            plataformas=["amazon", "meli"],
            redes=["reddit"],
            topes=inv.TOPES_DEFECTO
        )

        assert inv_data["version"] == 1
        assert inv_data["estado"] == "consultas"
        assert inv_data["tema"] == "skincare"
        assert inv_data["pais"] == "SE"
        assert inv_data["plataformas"] == ["amazon", "meli"]
        assert inv_data["redes"] == ["reddit"]
        assert inv_data["pasos"] == {}
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
        """Amazon domain for CO is com.mx (proxy) or custom."""
        # CO might not be in the dict, should return default "com"
        dom = plat.dominio("amazon", "CO")
        assert isinstance(dom, str)

    def test_idioma_se(self):
        """Language for SE is Swedish."""
        assert plat.idioma("SE") == "sv"

    def test_idioma_co(self):
        """Language for CO is Spanish."""
        assert plat.idioma("CO") == "es"

    def test_estimar_busqueda_amazon(self):
        """Estimate search cost for Amazon."""
        costo = plat.estimar_busqueda("amazon", 2, 20)
        # 2 × 20 = 40 resultados × $0.003 = $0.12
        assert costo > 0
        assert isinstance(costo, float)

    def test_estimar_resenas_amazon(self):
        """Estimate review cost for Amazon (por_producto=true)."""
        costo = plat.estimar_resenas("amazon", 15, 100)
        # 15 × 100 = 1500 resultados × $0.0009 = $1.35
        assert costo > 0
        assert isinstance(costo, float)

    def test_entradas_busqueda_amazon(self):
        """Build Apify input for Amazon search."""
        entradas = plat.entradas_busqueda("amazon", ["skincare", "facial"], "SE", 20)
        assert len(entradas) == 1
        assert "categoryOrProductUrls" in entradas[0]

    def test_entradas_busqueda_meli(self):
        """Build Apify input for MELI search."""
        entradas = plat.entradas_busqueda("meli", ["skincare"], "CO", 20)
        assert len(entradas) == 1
        assert "keyword" in entradas[0]

    def test_leer_producto_amazon(self):
        """Normalize Amazon product item."""
        item = {
            "asin": "B01234567",
            "title": "Skincare Set",
            "brand": "FakeBrand",
            "price": "USD 29.99",
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
        """Build Apify input for Amazon reviews."""
        productos = [
            {"fuente_id": "B001", "url": "https://...", "titulo": "P1"},
            {"fuente_id": "B002", "url": "https://...", "titulo": "P2"}
        ]
        entradas = plat.entradas_resenas("amazon", productos, 50)

        assert len(entradas) == 2
        assert all("asin" in e for e in entradas)

    def test_leer_resena_amazon(self):
        """Normalize Amazon review."""
        item = {
            "reviewId": "R123",
            "text": "Great product!",
            "rating": 5,
            "date": "2026-09-22",
            "verified": True
        }
        resena = plat.leer_resena("amazon", item)

        assert resena is not None
        assert resena["fuente_id"] == "R123"
        assert resena["texto"] == "Great product!"
        assert resena["puntuacion"] == 5


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

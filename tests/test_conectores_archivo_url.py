"""Conectores de catálogo sin API: contrato normalizado, CSV/Excel y URL."""
import io
import os

import pytest

import conectores
from conectores import base, csv_excel, url as conector_url
from conectores.base import ErrorConector, normalizar_pedido, normalizar_producto, parsear_precio

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


# --- base ------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("89.900,00", 89900.0),
    ("$ 12,50", 12.5),
    ("1,234", 1234.0),
    ("1234.5", 1234.5),
    ("1.234.567", 1234567.0),
    ("1,234.56", 1234.56),
    ("COP 45.000", 45000.0),
    ("12,5", 12.5),
    ("0.999", 0.999),
    ("-45,50", -45.5),
    ("", None),
    (None, None),
    ("gratis", None),
    (45000, 45000.0),
    (12.5, 12.5),
])
def test_parsear_precio(texto, esperado):
    assert parsear_precio(texto) == esperado


def test_normalizar_producto_completa_claves_y_castea():
    p = normalizar_producto({
        "nombre": "  Espejo  ", "precio": "89.900,00", "moneda": " cop ",
        "fotos": ["https://x/a.jpg", "https://x/a.jpg", "ftp://no", " https://x/b.jpg "],
    })
    assert tuple(p.keys()) == base.CLAVES_PRODUCTO
    assert p["nombre"] == "Espejo"
    assert p["fuente_id"] == "espejo"
    assert p["precio"] == 89900.0
    assert p["moneda"] == "COP"
    assert p["fotos"] == ["https://x/a.jpg", "https://x/b.jpg"]
    assert p["url_imagen_principal"] == "https://x/a.jpg"
    assert p["descripcion"] == ""
    assert p["url_compra"] is None and p["categoria"] is None
    assert p["extra"] == {}


def test_normalizar_producto_sin_nombre_es_error():
    with pytest.raises(ErrorConector) as ei:
        normalizar_producto({"nombre": "  ", "precio": 1})
    assert str(ei.value) == ei.value.usuario
    assert "nombre" in ei.value.usuario


def test_normalizar_producto_moneda_invalida_y_fuente_id_numerico():
    p = normalizar_producto({"nombre": "X", "moneda": "pesos", "fuente_id": 123, "fotos": "https://x/a.jpg"})
    assert p["moneda"] is None
    assert p["fuente_id"] == "123"
    assert p["fotos"] == ["https://x/a.jpg"]


@pytest.mark.parametrize("fecha, esperado", [
    ("2026-09-16T10:20:30Z", "2026-09-16T10:20:30"),
    ("2026-09-16T10:20:30-05:00", "2026-09-16T10:20:30"),
    ("2026-09-16T10:20:30.123456+00:00", "2026-09-16T10:20:30"),
    ("2026-09-16", "2026-09-16T00:00:00"),
    ("2026-09-16 10:20:30", "2026-09-16T10:20:30"),
])
def test_normalizar_pedido_fechas(fecha, esperado):
    ped = normalizar_pedido({"fuente_id": 55, "fecha": fecha, "total": "12,50", "moneda": "usd",
                             "items": [{"sku": "A", "nombre": "a", "cantidad": "2", "precio": "6,25"}],
                             "utm_content": " pieza-9 "})
    assert tuple(ped.keys()) == base.CLAVES_PEDIDO
    assert ped["fecha"] == esperado
    assert ped["fuente_id"] == "55"
    assert ped["total"] == 12.5
    assert ped["moneda"] == "USD"
    assert ped["items"] == [{"sku": "A", "nombre": "a", "cantidad": 2, "precio": 6.25}]
    assert ped["utm_content"] == "pieza-9"


def test_normalizar_pedido_fecha_invalida_y_utm_vacio():
    with pytest.raises(ErrorConector):
        normalizar_pedido({"fuente_id": "1", "fecha": "ayer", "total": 1})
    ped = normalizar_pedido({"fuente_id": "1", "fecha": "2026-01-01", "total": None, "utm_content": ""})
    assert ped["total"] == 0.0 and ped["utm_content"] is None and ped["items"] == []


def test_conector_base_contrato():
    c = base.Conector({"token": "abc"})
    assert c.credenciales == {"token": "abc"}
    assert base.Conector.tipo is None and not c.tiene_pedidos and not c.soporta_utm
    assert c.pedidos_desde("2026-01-01") == []
    r = c.probar()
    assert r["ok"] is True and set(r) == {"ok", "nombre", "detalle"}
    with pytest.raises(NotImplementedError):
        c.listar_productos()


def test_registro_por_tipo():
    @conectores.registrar
    class Falso(base.Conector):
        tipo = "falso_test"
    try:
        assert conectores.por_tipo("falso_test") is Falso
        assert "falso_test" in conectores.tipos()
    finally:
        conectores.REGISTRO.pop("falso_test", None)
    with pytest.raises(ValueError) as ei:
        conectores.por_tipo("nada")
    assert "Tipo de tienda no soportado" in str(ei.value)


# --- csv / excel -----------------------------------------------------------

def test_csv_punto_y_coma_con_acentos():
    productos = csv_excel.leer(os.path.join(FIXTURES, "productos.csv"), "productos.csv")
    assert len(productos) == 3  # la fila vacía se salta
    espejo, vidrio, repisa = productos
    assert espejo["nombre"] == "Espejo redondo 60cm"
    assert espejo["fuente_id"] == "ESP-60"
    assert espejo["precio"] == 89900.0
    assert espejo["moneda"] == "COP"
    assert espejo["fotos"] == ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"]
    assert espejo["url_imagen_principal"] == "https://cdn.test/a.jpg"
    assert espejo["descripcion"] == "Espejo de pared con marco dorado"
    assert espejo["categoria"] == "Espejos"
    assert espejo["url_compra"] == "https://tienda.test/espejo-redondo"
    assert vidrio["fuente_id"] == "vidrio-templado-6mm"  # sin sku → slug
    assert vidrio["precio"] == 45000.0
    assert repisa["precio"] == 12.5 and repisa["moneda"] == "USD" and repisa["fotos"] == []
    assert repisa["url_imagen_principal"] is None


def test_csv_desde_bytes_con_alias_y_latin1():
    contenido = "name,price,image,link,category\nSillón,1234.5,https://x/1.jpg,https://t/1,Muebles\n".encode("latin-1")
    productos = csv_excel.leer(contenido, "lista.CSV")
    assert len(productos) == 1
    p = productos[0]
    assert p["nombre"] == "Sillón" and p["precio"] == 1234.5
    assert p["fotos"] == ["https://x/1.jpg"] and p["url_compra"] == "https://t/1" and p["categoria"] == "Muebles"


def test_csv_fotos_separadas_por_coma():
    contenido = 'nombre,imagenes\nMesa,"https://x/1.jpg, https://x/2.jpg"\n'.encode("utf-8")
    p = csv_excel.leer(contenido, "m.csv")[0]
    assert p["fotos"] == ["https://x/1.jpg", "https://x/2.jpg"]


def test_xlsx_generado_con_openpyxl():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Producto", "Price", "Imagen", "Referencia"])
    ws.append(["Taza", 12000, "https://x/taza.jpg", "TZ-1"])
    ws.append([None, None, None, None])
    ws.append(["Plato", "8.500,00", None, None])
    wb.create_sheet("Otra").append(["nombre"])
    buf = io.BytesIO()
    wb.save(buf)
    productos = csv_excel.leer(buf.getvalue(), "catalogo.xlsx")
    assert [p["nombre"] for p in productos] == ["Taza", "Plato"]
    assert productos[0]["precio"] == 12000.0 and productos[0]["fuente_id"] == "TZ-1"
    assert productos[1]["precio"] == 8500.0 and productos[1]["fuente_id"] == "plato"


def test_csv_sin_columna_nombre():
    with pytest.raises(ErrorConector) as ei:
        csv_excel.leer(b"precio,sku\n10,A\n", "x.csv")
    assert "nombre" in ei.value.usuario


def test_csv_vacio_y_extension_desconocida():
    with pytest.raises(ErrorConector):
        csv_excel.leer(b"", "vacio.csv")
    with pytest.raises(ErrorConector):
        csv_excel.leer(b"nombre,precio\n", "solo_cabecera.csv")
    with pytest.raises(ErrorConector):
        csv_excel.leer(b"nombre\n", "x.pdf")


def test_columnas_ayuda():
    assert "nombre" in csv_excel.COLUMNAS_AYUDA and "|" in csv_excel.COLUMNAS_AYUDA


# --- url -------------------------------------------------------------------

class _Respuesta:
    def __init__(self, texto, status=200):
        self._bytes = texto.encode("utf-8") if isinstance(texto, str) else texto
        self.status_code = status
        self.headers = {}
        self.encoding = "utf-8"

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._bytes), chunk_size):
            yield self._bytes[i:i + chunk_size]

    @property
    def text(self):
        return self._bytes.decode("utf-8", errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("no debería usarse")

    def close(self):
        pass


def _fingir(monkeypatch, respuesta, capturado=None):
    def falso_get(url, **kw):
        if capturado is not None:
            capturado.update(kw, url=url)
        return respuesta
    monkeypatch.setattr(conector_url.requests, "get", falso_get)


def test_url_jsonld_gana_a_og(monkeypatch):
    with open(os.path.join(FIXTURES, "producto_og.html"), encoding="utf-8") as f:
        html = f.read()
    capturado = {}
    _fingir(monkeypatch, _Respuesta(html), capturado)
    p = conector_url.leer("https://tienda.test/lampara?x=1")
    assert p["nombre"] == "Lámpara de mesa & escritorio"
    assert p["descripcion"] == 'Lámpara LED regulable "nordic"'
    assert p["fuente_id"] == conector_url.hashlib.sha1(b"https://tienda.test/lampara?x=1").hexdigest()[:16]
    assert p["url_compra"] == "https://tienda.test/lampara?x=1"
    assert p["fotos"] == ["https://cdn.test/lamp1.jpg", "https://cdn.test/lamp2.jpg"]
    assert p["precio"] == 89900.0 and p["moneda"] == "COP"
    assert p["extra"]["metodo"] == "jsonld"
    assert p["extra"]["sku"] == "LAMP-01"
    assert "Chrome" in capturado["headers"]["User-Agent"]
    assert capturado["headers"]["Accept-Language"] == "es,en"
    assert capturado["timeout"] == 20 and capturado["stream"] is True


def test_url_solo_open_graph(monkeypatch):
    html = """<html><head><title>Titulo HTML</title>
    <meta content="Silla &amp; mesa" property="og:title" />
    <meta property="og:description" content="Muy c&oacute;moda">
    <meta property="og:image" content="https://cdn.test/s1.jpg">
    <meta property="og:image" content="https://cdn.test/s2.jpg">
    <meta property="product:price:amount" content="199.99">
    <meta property="product:price:currency" content="usd">
    </head><body></body></html>"""
    _fingir(monkeypatch, _Respuesta(html))
    p = conector_url.leer("https://tienda.test/silla")
    assert p["nombre"] == "Silla & mesa"
    assert p["descripcion"] == "Muy cómoda"
    assert p["fotos"] == ["https://cdn.test/s1.jpg", "https://cdn.test/s2.jpg"]
    assert p["precio"] == 199.99 and p["moneda"] == "USD"
    assert p["extra"]["metodo"] == "og"


def test_url_solo_title(monkeypatch):
    _fingir(monkeypatch, _Respuesta("<html><head><title> Solo t&iacute;tulo </title></head><body>hola</body></html>"))
    p = conector_url.leer("https://tienda.test/x")
    assert p["nombre"] == "Solo título"
    assert p["precio"] is None and p["fotos"] == [] and p["extra"]["metodo"] == "title"


def test_url_sin_titulo_es_error(monkeypatch):
    _fingir(monkeypatch, _Respuesta("<html><body><p>nada</p></body></html>"))
    with pytest.raises(ErrorConector) as ei:
        conector_url.leer("https://tienda.test/x")
    assert "<p>" not in ei.value.usuario


def test_url_mas_de_3mb_aborta(monkeypatch):
    grande = "<html><head><title>x</title></head><body>" + ("a" * (3 * 1024 * 1024 + 10)) + "</body></html>"
    _fingir(monkeypatch, _Respuesta(grande))
    with pytest.raises(ErrorConector) as ei:
        conector_url.leer("https://tienda.test/grande")
    assert "3 MB" in ei.value.usuario


def test_url_404_sin_html_en_mensaje(monkeypatch):
    _fingir(monkeypatch, _Respuesta("<html><body>Not Found <b>ugly</b></body></html>", status=404))
    with pytest.raises(ErrorConector) as ei:
        conector_url.leer("https://tienda.test/no-existe")
    assert "404" in ei.value.usuario
    assert "<html>" not in ei.value.usuario and "ugly" not in ei.value.usuario


def test_url_error_de_red(monkeypatch):
    def falla(url, **kw):
        raise conector_url.requests.ConnectionError("dns")
    monkeypatch.setattr(conector_url.requests, "get", falla)
    with pytest.raises(ErrorConector) as ei:
        conector_url.leer("https://tienda.test/x")
    assert ei.value.usuario


def test_url_jsonld_offers_dict_y_lista_de_bloques(monkeypatch):
    html = """<html><head><title>t</title>
    <script type="application/ld+json">[{"@type":"BreadcrumbList"},
      {"@type":"Product","name":"Bolso","image":{"@type":"ImageObject","url":"https://cdn.test/b.jpg"},
       "offers":{"@type":"Offer","price":45000,"priceCurrency":"COP"}}]</script>
    </head></html>"""
    _fingir(monkeypatch, _Respuesta(html))
    p = conector_url.leer("https://tienda.test/bolso")
    assert p["nombre"] == "Bolso" and p["precio"] == 45000.0 and p["fotos"] == ["https://cdn.test/b.jpg"]


def test_url_jsonld_roto_cae_a_og(monkeypatch):
    html = """<html><head><title>t</title>
    <script type="application/ld+json">{no es json</script>
    <meta property="og:title" content="Desde OG"></head></html>"""
    _fingir(monkeypatch, _Respuesta(html))
    p = conector_url.leer("https://tienda.test/roto")
    assert p["nombre"] == "Desde OG" and p["extra"]["metodo"] == "og"

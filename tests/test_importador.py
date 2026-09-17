"""importador.py: producto normalizado → fila `producto` → activo del catálogo
de Crear (fotos descargadas + regla de Claude), sin tocar red ni clientes/."""
import os

import pytest

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class _Respuesta:
    def __init__(self, cuerpo=PNG, status=200, content_type="image/png", largo=None):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        if largo is not None:
            self.headers["Content-Length"] = str(largo)
        self._cuerpo = cuerpo
        self.cerrada = False

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._cuerpo), chunk_size):
            yield self._cuerpo[i:i + chunk_size]

    def close(self):
        self.cerrada = True


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    """Catálogo en tmp_path, requests.get falso (cuenta descargas), regla
    falsa (cuenta llamadas), hosts siempre permitidos."""
    import catalogo_productos
    import importador
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    descargas = []
    respuestas = {}

    def _get(url, headers=None, timeout=None, stream=None, allow_redirects=True):
        assert allow_redirects is False  # las redirecciones se siguen a mano (SSRF)
        descargas.append(url)
        r = respuestas.get(url)
        if callable(r):
            return r()
        return r or _Respuesta()
    monkeypatch.setattr(importador.requests, "get", _get)
    monkeypatch.setattr(importador, "host_permitido", lambda u: True)
    reglas = []

    def _regla(nombre, descripcion="", categoria=""):
        reglas.append(nombre)
        return f"Regla de {nombre}: mismo color y logo."
    monkeypatch.setattr(importador.generador_prompts, "regla_fidelidad", _regla)
    return {"descargas": descargas, "respuestas": respuestas, "reglas": reglas, "tmp": tmp_path}


def _prod(nombre="Cojín Azul", fuente_id="p1", fotos=("https://cdn.test/a.jpg", "https://cdn.test/b.png"), **extra):
    from conectores.base import normalizar_producto
    d = {"fuente_id": fuente_id, "nombre": nombre, "descripcion": "Cojín de lino azul 45x45", "precio": 10,
         "moneda": "USD", "url_compra": "https://tienda.test/p1", "fotos": list(fotos), "categoria": "Hogar"}
    d.update(extra)
    return normalizar_producto(d)


def test_importar_lista_crea_producto_y_activo_con_fotos_y_regla(entorno):
    import catalogo_productos
    import importador
    import tiendas
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(content_type="image/jpeg")
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res == {"nuevos": 1, "actualizados": 0, "activos": 1, "errores": []}
    prod = tiendas.productos("acme")[0]
    assert prod["activo_catalogo_id"] == "cojin_azul"
    activo = catalogo_productos.encontrar("acme", "cojin_azul", "producto")
    assert activo is not None
    assert activo["imagenes"] == ["01.jpg", "02.png"]
    assert activo["regla_propia"] == "Regla de Cojín Azul: mismo color y logo."
    assert activo["tipo"] == "textil_hogar"
    assert activo["nombre"] == "Cojín Azul" and activo["descripcion"] == "Cojín de lino azul 45x45"
    assert entorno["descargas"] == ["https://cdn.test/a.jpg", "https://cdn.test/b.png"]
    assert entorno["reglas"] == ["Cojín Azul"]
    # nada se escribió en el clientes/ real del repo
    assert not os.path.exists(os.path.join(os.path.dirname(FIXTURES), "..", "clientes", "acme", "productos", "cojin_azul"))


def test_segunda_importacion_no_redescarga_ni_pisa_regla_editada(entorno):
    import catalogo_productos
    import importador
    importador.importar_lista("acme", "shopify", [_prod()])
    catalogo_productos.actualizar("acme", "cojin_azul", regla="Editada a mano.")
    entorno["descargas"].clear()
    entorno["reglas"].clear()
    res = importador.importar_lista("acme", "shopify", [_prod(nombre="Cojín Azul Marino", descripcion="Nueva desc")])
    assert res == {"nuevos": 0, "actualizados": 1, "activos": 1, "errores": []}
    assert entorno["descargas"] == [] and entorno["reglas"] == []
    activo = catalogo_productos.encontrar("acme", "cojin_azul", "producto")
    assert activo["regla_propia"] == "Editada a mano."
    assert activo["nombre"] == "Cojín Azul Marino" and activo["descripcion"] == "Nueva desc"
    assert activo["imagenes"] == ["01.png", "02.png"]


def test_producto_sin_fotos_no_crea_activo_y_lo_avisa(entorno):
    import catalogo_productos
    import importador
    import tiendas
    res = importador.importar_lista("acme", "csv", [_prod(nombre="Repisa", fuente_id="r1", fotos=())])
    assert res["nuevos"] == 1 and res["activos"] == 0
    assert len(res["errores"]) == 1 and "Repisa" in res["errores"][0] and "sin fotos" in res["errores"][0]
    assert tiendas.productos("acme")[0]["activo_catalogo_id"] is None
    assert catalogo_productos.listar("acme", "producto") == []
    assert not os.path.isdir(os.path.join(str(entorno["tmp"]), "clientes", "acme", "productos", "repisa"))
    assert entorno["reglas"] == []  # sin fotos no se gasta la llamada a Claude


def test_fotos_que_fallan_no_crean_activo_ni_carpeta_fantasma(entorno):
    import catalogo_productos
    import importador
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(status=404)
    entorno["respuestas"]["https://cdn.test/b.png"] = _Respuesta(content_type="text/html")
    res = importador.importar_lista("acme", "csv", [_prod()])
    assert res["activos"] == 0 and any("ninguna foto" in e for e in res["errores"])
    assert not catalogo_productos.existe("acme", "cojin_azul")
    assert entorno["reglas"] == []


def test_foto_demasiado_grande_se_salta_pero_el_activo_sale_con_las_demas(entorno):
    import catalogo_productos
    import importador
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(largo=importador.MAX_BYTES_FOTO + 1)
    res = importador.importar_lista("acme", "csv", [_prod()])
    assert res["activos"] == 1 and any("1 foto(s)" in e for e in res["errores"])
    assert catalogo_productos.encontrar("acme", "cojin_azul", "producto")["imagenes"] == ["02.png"]


def test_host_privado_se_rechaza(entorno, monkeypatch):
    import importador
    from conectores.base import ErrorConector

    def _host(u):
        if "b.png" in u:
            raise ErrorConector("No se pudo resolver el dominio.")
        return False
    monkeypatch.setattr(importador, "host_permitido", _host)
    res = importador.importar_lista("acme", "csv", [_prod()])
    assert res["activos"] == 0 and entorno["descargas"] == []


def test_redireccion_se_sigue_revalidando_host(entorno, monkeypatch):
    import catalogo_productos
    import importador
    r = _Respuesta(status=302)
    r.headers["Location"] = "/real/a.jpg"
    entorno["respuestas"]["https://cdn.test/a.jpg"] = r
    entorno["respuestas"]["https://cdn.test/real/a.jpg"] = _Respuesta(content_type="image/jpeg")
    interno = _Respuesta(status=302)
    interno.headers["Location"] = "http://10.0.0.5/b.png"
    entorno["respuestas"]["https://cdn.test/b.png"] = interno
    monkeypatch.setattr(importador, "host_permitido", lambda u: "10.0.0.5" not in u)
    res = importador.importar_lista("acme", "csv", [_prod()])
    assert res["activos"] == 1
    assert catalogo_productos.encontrar("acme", "cojin_azul", "producto")["imagenes"] == ["01.jpg"]
    assert "http://10.0.0.5/b.png" not in entorno["descargas"] and r.cerrada


def test_maximo_seis_fotos(entorno):
    import catalogo_productos
    import importador
    fotos = [f"https://cdn.test/{i}.png" for i in range(9)]
    importador.importar_lista("acme", "csv", [_prod(fotos=fotos)])
    assert len(entorno["descargas"]) == 6
    assert catalogo_productos.encontrar("acme", "cojin_azul", "producto")["imagenes"] == [f"0{i}.png" for i in range(1, 7)]


def test_adopta_activo_existente_con_el_mismo_nombre(entorno):
    import catalogo_productos
    import importador
    import tiendas
    catalogo_productos.crear("acme", "Cojín Azul", "subido a mano", tipo="otro", regla="Mi regla.")
    carpeta = catalogo_productos.carpeta_de("acme", "cojin_azul")
    with open(os.path.join(carpeta, "manual.jpg"), "wb") as f:
        f.write(PNG)
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["activos"] == 1 and res["errores"] == []
    assert tiendas.productos("acme")[0]["activo_catalogo_id"] == "cojin_azul"
    activo = catalogo_productos.encontrar("acme", "cojin_azul", "producto")
    assert activo["regla_propia"] == "Mi regla." and activo["imagenes"] == ["manual.jpg"]
    assert entorno["descargas"] == [] and entorno["reglas"] == []
    assert len(catalogo_productos.listar("acme", "producto")) == 1


def test_activo_borrado_se_vuelve_a_crear(entorno):
    import catalogo_productos
    import importador
    importador.importar_lista("acme", "shopify", [_prod()])
    catalogo_productos.eliminar("acme", "cojin_azul")
    entorno["descargas"].clear()
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["actualizados"] == 1 and res["activos"] == 1
    assert len(entorno["descargas"]) == 2 and catalogo_productos.existe("acme", "cojin_azul")


def test_vincular_activo_forzar_fotos(entorno):
    import catalogo_productos
    import importador
    import tiendas
    importador.importar_lista("acme", "shopify", [_prod()])
    pid = tiendas.productos("acme")[0]["id"]
    entorno["descargas"].clear()
    assert importador.vincular_activo("acme", pid) == "cojin_azul" and entorno["descargas"] == []
    assert importador.vincular_activo("acme", pid, forzar_fotos=True) == "cojin_azul"
    assert len(entorno["descargas"]) == 2
    assert catalogo_productos.encontrar("acme", "cojin_azul", "producto")["imagenes"] == ["01.png", "02.png"]


def test_un_producto_malo_no_frena_a_los_demas(entorno):
    import importador
    res = importador.importar_lista("acme", "csv", [
        {"fuente_id": "", "nombre": "", "fotos": []},
        _prod(nombre="Bueno", fuente_id="b1"),
    ])
    assert res["nuevos"] == 1 and res["activos"] == 1 and len(res["errores"]) == 1


def test_on_progreso_recibe_etapas(entorno):
    import importador
    etapas = []
    importador.importar_lista("acme", "csv", [_prod(), _prod(nombre="Otro", fuente_id="p2")],
                              on_progreso=lambda e, d: etapas.append((e, d)))
    assert etapas[0] == ("Guardando productos", "2 producto(s)")
    assert ("Creando activos", "1 de 2") in etapas and ("Creando activos", "2 de 2") in etapas


@pytest.mark.parametrize("nombre,descripcion,categoria,esperado", [
    ("Tenis Runner Blanco", "", "", "calzado"),
    ("Sandalias de cuero", "", "Zapatos", "calzado"),
    ("Chanclas slide HappyFlops", "goma acanalada", "", "calzado"),
    ("Camiseta oversize", "", "", "prenda"),
    ("Hoodie negro", "algodón", "Ropa", "prenda"),
    ("Pantalón cargo", "", "", "prenda"),
    ("Mochila urbana", "", "", "bolso"),
    ("Riñonera reflectiva", "", "", "bolso"),
    ("Cobija de polar", "", "", "textil_hogar"),
    ("Cojín Azul", "lino", "Hogar", "textil_hogar"),
    ("Espejo redondo 60cm", "Espejo de pared con marco dorado", "Espejos", "otro"),
    ("Vidrio templado 6mm", "", "", "otro"),
    ("Kit", "sábanas y toallas", "", "textil_hogar"),
    ("Bolso para tenis", "", "", "bolso"),   # el nombre manda sobre la descripción
    ("Set regalo", "", "Calzado", "calzado"),
    ("Raqueta de tenis", "", "", "otro"),   # "tenis" no es calzado con una raqueta al lado
    ("", "", "", "otro"),
])
def test_inferir_tipo(nombre, descripcion, categoria, esperado):
    import importador
    import prompt_swap
    tipo = importador.inferir_tipo(nombre, descripcion, categoria)
    assert tipo == esperado and tipo in prompt_swap.TIPOS


def test_desde_archivo_con_fixture_csv(entorno):
    import catalogo_productos
    import importador
    import tiendas
    etapas = []
    res = importador.desde_archivo("acme", os.path.join(FIXTURES, "productos.csv"), "productos.csv",
                                   on_progreso=lambda e, d: etapas.append(e))
    assert res["nuevos"] == 3 and res["actualizados"] == 0
    assert res["activos"] == 2   # la repisa viene sin fotos
    assert any("Repisa" in e and "sin fotos" in e for e in res["errores"])
    assert etapas[0] == "Leyendo" and "Guardando productos" in etapas and "Creando activos" in etapas
    prods = {p["fuente_id"]: p for p in tiendas.productos("acme")}
    assert set(prods) == {"ESP-60", "vidrio-templado-6mm", "REP-01"}
    assert all(p["fuente"] == "csv" for p in prods.values())
    assert prods["ESP-60"]["activo_catalogo_id"] == "espejo_redondo_60cm"
    assert catalogo_productos.encontrar("acme", "espejo_redondo_60cm", "producto")["tipo"] == "otro"
    assert sorted(entorno["descargas"]) == ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg", "https://cdn.test/c.jpg"]


def test_desde_archivo_ilegible_lanza_error_conector(entorno, tmp_path):
    import importador
    from conectores.base import ErrorConector
    ruta = tmp_path / "x.csv"
    ruta.write_text("precio;foto\n1;2\n", encoding="utf-8")
    with pytest.raises(ErrorConector):
        importador.desde_archivo("acme", str(ruta), "x.csv")


def test_desde_url(entorno, monkeypatch):
    import importador
    import tiendas
    monkeypatch.setattr(importador.conector_url, "leer",
                        lambda url: _prod(nombre="Espejo web", fuente_id="abc123", url_compra=url))
    res = importador.desde_url("acme", "https://tienda.test/espejo")
    assert res["nuevos"] == 1 and res["activos"] == 1
    p = tiendas.productos("acme")[0]
    assert p["fuente"] == "url" and p["url_compra"] == "https://tienda.test/espejo"


def test_resumen_texto_en_espanol():
    import importador
    texto = importador.resumen_texto({"nuevos": 2, "actualizados": 1, "activos": 2,
                                      "errores": ["a", "b", "c", "d"]})
    assert "2 producto(s) nuevo(s)" in texto and "1 actualizado(s)" in texto and "2 con activo" in texto
    assert "4 aviso(s)" in texto and "y 1 más" in texto


def test_regla_fidelidad_nunca_lanza(monkeypatch):
    import generador_prompts
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert generador_prompts.regla_fidelidad("X", "desc", "cat") == ""

    class _Cliente:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            assert kw["max_tokens"] <= 300 and "X" in kw["messages"][0]["content"]
            return type("R", (), {"content": [type("B", (), {"type": "text", "text": ' "Regla lista." '})()]})()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(generador_prompts.anthropic, "Anthropic", _Cliente)
    assert generador_prompts.regla_fidelidad("X", "desc", "cat") == "Regla lista."


def test_dos_productos_con_mismo_nombre_no_colapsan_en_un_activo(entorno):
    import catalogo_productos
    import importador
    import tiendas
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(content_type="image/jpeg")
    entorno["respuestas"]["https://cdn.test/z.jpg"] = _Respuesta(content_type="image/jpeg")
    res1 = importador.importar_lista("acme", "shopify", [
        _prod(nombre="Gorra", fuente_id="g1", descripcion="Gorra roja", fotos=("https://cdn.test/a.jpg",))])
    assert res1["activos"] == 1
    res2 = importador.importar_lista("acme", "shopify", [
        _prod(nombre="Gorra", fuente_id="g2", descripcion="Gorra negra", fotos=("https://cdn.test/z.jpg",))])
    assert res2["activos"] == 1 and res2["errores"] == []

    prods = {p["fuente_id"]: p for p in tiendas.productos("acme")}
    assert prods["g1"]["activo_catalogo_id"] == "gorra"
    assert prods["g2"]["activo_catalogo_id"] == "gorra-2"  # no pisa al primero

    activo1 = catalogo_productos.encontrar("acme", "gorra", "producto")
    activo2 = catalogo_productos.encontrar("acme", "gorra-2", "producto")
    assert activo1["descripcion"] == "Gorra roja" and activo2["descripcion"] == "Gorra negra"
    assert activo1["imagenes"] and activo2["imagenes"]  # cada uno con su propia foto
    assert len(catalogo_productos.listar("acme", "producto")) == 2

    # una nueva sync de g1 (ya ligado) sigue actualizando SU activo, no el del otro
    importador.importar_lista("acme", "shopify", [
        _prod(nombre="Gorra", fuente_id="g1", descripcion="Gorra roja v2", fotos=("https://cdn.test/a.jpg",))])
    prods = {p["fuente_id"]: p for p in tiendas.productos("acme")}
    assert prods["g1"]["activo_catalogo_id"] == "gorra"
    assert catalogo_productos.encontrar("acme", "gorra", "producto")["descripcion"] == "Gorra roja v2"
    assert catalogo_productos.encontrar("acme", "gorra-2", "producto")["descripcion"] == "Gorra negra"


def test_adopta_carpeta_vacia_sin_fotos_no_vincula_ni_avisa_activo(entorno):
    import catalogo_productos
    import importador
    import tiendas
    catalogo_productos.crear("acme", "Cojín Azul", "", tipo="otro")  # carpeta subida a mano, sin imágenes
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(status=500)
    entorno["respuestas"]["https://cdn.test/b.png"] = _Respuesta(status=500)
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["activos"] == 0
    assert any("sin fotos" in e for e in res["errores"])
    assert tiendas.productos("acme")[0]["activo_catalogo_id"] is None
    # la carpeta sigue existiendo (no la creamos en esta llamada) pero invisible en listar()
    assert catalogo_productos.existe("acme", "cojin_azul")
    assert catalogo_productos.listar("acme", "producto") == []


def test_adopta_carpeta_vacia_y_descarga_fotos_como_forzar_fotos(entorno):
    import catalogo_productos
    import importador
    import tiendas
    catalogo_productos.crear("acme", "Cojín Azul", "", tipo="otro")  # carpeta subida a mano, sin imágenes
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(content_type="image/jpeg")
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["activos"] == 1 and res["errores"] == []
    assert tiendas.productos("acme")[0]["activo_catalogo_id"] == "cojin_azul"
    assert catalogo_productos.encontrar("acme", "cojin_azul", "producto")["imagenes"]


def test_descripcion_vacia_no_borra_la_escrita_a_mano(entorno):
    import catalogo_productos
    import importador
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(content_type="image/jpeg")
    importador.importar_lista("acme", "shopify", [_prod()])
    catalogo_productos.actualizar("acme", "cojin_azul", descripcion="Escrita a mano.")
    importador.importar_lista("acme", "shopify", [_prod(descripcion="")])
    activo = catalogo_productos.encontrar("acme", "cojin_azul", "producto")
    assert activo["descripcion"] == "Escrita a mano."


def test_catalogo_existe_y_producto_por_fuente(entorno):
    import catalogo_productos
    import tiendas
    assert catalogo_productos.existe("acme", "nada") is False
    assert catalogo_productos.existe("acme", "../../etc") is False
    assert catalogo_productos.existe("acme", None) is False
    catalogo_productos.crear("acme", "Algo")
    assert catalogo_productos.existe("acme", "algo") is True
    assert tiendas.producto_por_fuente("acme", "csv", "x") is None
    pid = tiendas.upsert_producto("acme", "csv", "x", {"nombre": "X"})
    assert tiendas.producto_por_fuente("acme", "csv", "x")["id"] == pid
    assert tiendas.producto_por_fuente("otro", "csv", "x") is None

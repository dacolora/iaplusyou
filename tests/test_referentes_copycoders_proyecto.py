"""Incidente 2026-09-28: la página del proyecto se quedaba cargando. La
biblioteca global de copycoders nace apagada en cada proyecto (la persona la
trae con un botón) y la página ya no pide de entrada los medios de las
pestañas ocultas."""
import glob
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _anuncio(aid, **extra):
    base = {"anuncio_id": aid, "pagina_id": "1", "fuente": "copycoders", "marca": "Lulutox Tea",
            "url_anuncio": f"https://www.facebook.com/ads/library/?id={aid}", "titular": f"Titular {aid}", "idioma": "en",
            "tipo": "imagen", "imagen_origen": "https://cdn/x.jpg", "dias": 10, "variantes": 2, "activo": True,
            "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
            "firma": "Firma en español", "clasificacion": "fuente", "extra": {}}
    base.update(extra)
    return base


def _sembrar():
    """Uno global de copycoders, uno global de Atria y uno propio de acme."""
    from referentes import datos
    ids = {}
    for clave, anuncio, cliente in (
            ("copycoders", _anuncio("1", dolor="hinchazón"), None),
            ("atria", _anuncio("2", fuente="atria", dolor="fatiga"), None),
            ("propio", _anuncio("3", fuente="atria", dolor="insomnio"), "acme")):
        rid, _ = datos.guardar_referente(anuncio, cliente=cliente)
        datos.marcar_imagen(rid, "ok", f"https://r2/referentes/{rid}.jpg")
        ids[clave] = rid
    return ids


@pytest.fixture()
def proyecto(base_temporal, monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return proyectos


def test_nace_apagada_y_no_lista_copycoders(proyecto):
    from referentes import datos
    ids = _sembrar()
    assert proyecto.referentes_copycoders("acme") is False
    vistos = {r["id"] for r in datos.listar("acme")["items"]}
    assert vistos == {ids["atria"], ids["propio"]}
    op = datos.opciones("acme")
    assert op["total"] == 2 and "hinchazón" not in dict(op["dolores"])
    assert dict(op["fuentes"]) == {"atria": 2}


def test_apagada_igual_abre_un_referente_por_id(proyecto):
    """Uno ya usado en un sprint o en Recrear se sigue abriendo."""
    from referentes import datos
    ids = _sembrar()
    assert datos.referente("acme", ids["copycoders"])["fuente"] == "copycoders"


def test_encendida_lista_todo(proyecto):
    from referentes import datos
    ids = _sembrar()
    proyecto.guardar_referentes_copycoders("acme", True)
    assert {r["id"] for r in datos.listar("acme")["items"]} == set(ids.values())
    assert datos.opciones("acme")["total"] == 3
    assert datos.total_copycoders() == 1


def test_el_admin_global_sigue_viendo_copycoders(proyecto):
    from referentes import datos
    _sembrar()
    assert datos.opciones(None)["total"] == 2          # los dos globales, con copycoders


def test_el_buscador_tambien_mira_el_dolor(proyecto):
    from referentes import datos
    ids = _sembrar()
    assert [r["id"] for r in datos.listar("acme", {"q": "insom"})["items"]] == [ids["propio"]]


@pytest.fixture()
def app(proyecto, monkeypatch):
    import dashboard
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


def test_boton_trae_y_quita_la_biblioteca(app, proyecto):
    _sembrar()
    html = app.get("/cliente/acme").data.decode()
    assert "Traer la biblioteca de copycoders" in html and "hinchazón" not in html
    r = app.post("/cliente/acme/referentes/copycoders", data={"activa": "1"},
                 headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#referentes")
    assert proyecto.referentes_copycoders("acme") is True
    html = app.get("/cliente/acme").data.decode()
    assert "Quitar la biblioteca" in html and "hinchazón" in html
    app.post("/cliente/acme/referentes/copycoders", data={"activa": "0"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert proyecto.referentes_copycoders("acme") is False


def test_sin_copycoders_en_la_base_no_hay_boton(app):
    assert "Traer la biblioteca de copycoders" not in app.get("/cliente/acme").data.decode()


def test_el_filtro_de_dolor_muestra_solo_los_mas_frecuentes(app, proyecto):
    from referentes import datos, rutas
    proyecto.guardar_referentes_copycoders("acme", True)
    for i in range(rutas.MAX_DOLORES_FILTRO + 20):
        rid, _ = datos.guardar_referente(_anuncio(str(1000 + i), dolor=f"dolor {i:03d}"))
        datos.marcar_imagen(rid, "ok", "https://r2/x.jpg")
    html = app.get("/cliente/acme").data.decode()
    select = re.search(r'<select data-filtro="dolor">(.*?)</select>', html, re.S).group(1)
    assert select.count("<option") == rutas.MAX_DOLORES_FILTRO + 1          # + «Cualquier dolor»


def test_ninguna_lista_pide_videos_de_entrada():
    """Las tarjetas nacen con preload="none" + data-precarga y base.html las
    pide al entrar en pantalla (una pestaña oculta nunca entra)."""
    malos = []
    for ruta in glob.glob(os.path.join(RAIZ, "templates", "*.html")):
        texto = open(ruta, encoding="utf-8").read()
        for video in re.findall(r"<video\b[^>]*>", texto):
            if 'preload="metadata"' in video or 'preload="auto"' in video:
                malos.append(f"{os.path.basename(ruta)}: {video[:90]}")
    assert not malos, "\n".join(malos)
    base = open(os.path.join(RAIZ, "templates", "base.html"), encoding="utf-8").read()
    assert "video[data-precarga]" in base and "IntersectionObserver" in base


def test_fotos_del_selector_de_productos_son_diferidas():
    texto = open(os.path.join(RAIZ, "templates", "_selector_productos.html"), encoding="utf-8").read()
    imgs = re.findall(r"<img\b[^>]*>", texto)
    assert imgs and all('loading="lazy"' in i for i in imgs)

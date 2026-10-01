"""catalogo_vista: puro (spec 2026-09-28 §10.2)."""
import catalogo_vista as cv


def _entrada(pid, nombre, colores=(), n_fotos=1):
    return {"id": pid, "categoria": "producto", "nombre": nombre, "n_fotos": n_fotos,
            "colores": [{"id": f"{pid}/{c.lower()}", "color_id": c.lower(), "nombre": f"{nombre} — {c}", "sin_fotos": False,
                         "disponible": True} for c in colores]}


def _fila(pid, **kw):
    base = {"id": pid, "precio": None, "moneda": None, "url_compra": None, "fuente": "manual", "en_prueba": False,
            "prioridad": 0, "archivado": False, "nombre": "x", "n_experimentos": 0, "activo_catalogo_id": None, "fotos": []}
    base.update(kw)
    return base


def test_tarjetas_activo_y_fila():
    prods = [_entrada("original", "Original", ("Pink", "Beige"), n_fotos=3), _entrada("cojin", "Cojín")]
    filas = {"original": _fila(1, precio=34.95, moneda="EUR", url_compra="https://t/o", fuente="shopify", en_prueba=True, prioridad=40)}
    usos = {"original": {"total": 5}}
    sin_activo = [_fila(9, nombre="Lámpara", fuente="csv", n_experimentos=1)]
    t = cv.tarjetas(prods, filas, usos, sin_activo)
    assert [x["tipo"] for x in t] == ["activo", "activo", "fila"]
    o = t[0]
    assert o["id"] == "original" and o["n_colores"] == 2 and o["colores"][0]["id"] == "original/pink"
    assert o["precio"] == 34.95 and o["fuente"] == "shopify" and o["en_prueba"] and o["prioridad"] == 40 and o["usos"] == 5
    assert "pink" in o["busqueda"] and "original" in o["busqueda"] and not o["sin_fotos"]
    assert t[1]["precio"] is None and t[1]["fuente"] is None and t[1]["fila"] is None
    assert t[1]["n_colores"] == 0 and t[1]["colores"] == []
    lam = t[2]
    assert lam["id"] == "fila-9" and lam["sin_fotos"] and lam["usos"] == 1 and lam["nombre"] == "Lámpara"


def _lista():
    prods = [_entrada("a", "Alfa"), _entrada("b", "Beta"), _entrada("c", "Gamma")]
    filas = {"a": _fila(1, precio=10, url_compra="https://x", prioridad=1),
             "b": _fila(2, en_prueba=True, prioridad=9), "c": _fila(3, archivado=True, precio=5)}
    return cv.tarjetas(prods, filas, {}, [_fila(4, nombre="Delta"), _fila(5, nombre="Épsilon", archivado=True)])


def test_contadores_filtrar_ordenar():
    lista = _lista()
    assert cv.contadores(lista) == {"todos": 3, "en_prueba": 1, "sin_precio": 1, "sin_url": 1, "sin_fotos": 1, "archivados": 2}
    assert [t["nombre"] for t in cv.filtrar(lista)] == ["Alfa", "Beta", "Delta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="en_prueba")] == ["Beta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="sin_precio")] == ["Beta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="sin_url")] == ["Beta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="sin_fotos")] == ["Delta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="archivados")] == ["Gamma", "Épsilon"]
    assert [t["nombre"] for t in cv.filtrar(lista, q="ALF")] == ["Alfa"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="lo-que-sea")] == ["Alfa", "Beta", "Delta"]
    visibles = cv.filtrar(lista)
    assert [t["nombre"] for t in cv.ordenar(visibles)] == ["Beta", "Alfa", "Delta"]            # prioridad desc, sin fotos al final
    assert [t["nombre"] for t in cv.ordenar(visibles, "nombre")] == ["Alfa", "Beta", "Delta"]


def test_paginar():
    lista = list(range(130))
    trozo, mas = cv.paginar(lista, 1, 60)
    assert trozo == list(range(60)) and mas
    trozo, mas = cv.paginar(lista, 3, 60)
    assert trozo == list(range(120, 130)) and not mas
    assert cv.paginar(lista, 0, 60)[0] == list(range(60)) and cv.paginar([], 1)[1] is False


def test_contar_usos():
    claves = {"ids": {"original", "original/pink"}, "nombres": {"original — pink"}}
    sesiones = [{"original — pink"}, {"otro"}, {"original/pink", "x"}]
    por_clave = {"original — pink": {1, 2}, "original": {2}}
    campanas = {"original/pink": 3, "cojin": 1}
    assert cv.contar_usos(claves, sesiones, por_clave, campanas) == {"piezas": 2, "experimentos": 2, "campanas": 3, "total": 7}

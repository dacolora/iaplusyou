"""
Catálogo › galería (spec 2026-09-28 §10.2): funciones puras sobre lo que ya
leyeron las rutas — entradas de `catalogo_productos.listar_productos()`,
filas `producto` (`tiendas.por_activo`), filas sin activo y usos — para armar
las tarjetas, filtrarlas, ordenarlas y paginarlas. Sin Flask ni base de
datos: se prueba con dicts (tests/test_catalogo_vista.py).
"""
FILTROS = ("todos", "en_prueba", "sin_precio", "sin_url", "sin_fotos", "archivados")
ORDENES = ("prioridad", "nombre")
POR_PAGINA = 60


def _texto(v):
    return str(v or "").casefold()


def tarjeta_activo(entrada, fila=None, usos=0):
    """Tarjeta de un producto/personaje/entorno del catálogo (con su fila comercial si es producto)."""
    fila = fila or {}
    colores = [{"id": c["id"], "color_id": c["color_id"], "nombre": c["nombre"], "sin_fotos": bool(c.get("sin_fotos")),
                "disponible": c.get("disponible", True) is not False} for c in entrada.get("colores") or []]
    return {
        "tipo": "activo", "id": entrada["id"], "cat": entrada["categoria"], "nombre": entrada["nombre"],
        "busqueda": " ".join([_texto(entrada["nombre"])] + [_texto(c["nombre"]) for c in colores]),
        "n_fotos": int(entrada.get("n_fotos") or 0), "n_colores": len(colores), "colores": colores,
        "precio": fila.get("precio"), "moneda": fila.get("moneda"), "url_compra": fila.get("url_compra"),
        "fuente": fila.get("fuente"), "en_prueba": bool(fila.get("en_prueba")), "prioridad": int(fila.get("prioridad") or 0),
        "archivado": bool(fila.get("archivado")), "usos": int(usos or 0), "sin_fotos": False, "fila": fila or None,
    }


def tarjeta_fila(fila):
    """Tarjeta de una fila importada que todavía no tiene activo (sin fotos en el catálogo)."""
    return {
        "tipo": "fila", "id": f"fila-{fila['id']}", "cat": "producto", "nombre": fila.get("nombre") or "",
        "busqueda": _texto(fila.get("nombre")), "n_fotos": 0, "n_colores": 0, "colores": [],
        "precio": fila.get("precio"), "moneda": fila.get("moneda"), "url_compra": fila.get("url_compra"),
        "fuente": fila.get("fuente"), "en_prueba": bool(fila.get("en_prueba")), "prioridad": int(fila.get("prioridad") or 0),
        "archivado": bool(fila.get("archivado")), "usos": int(fila.get("n_experimentos") or 0), "sin_fotos": True, "fila": fila,
    }


def tarjetas(productos, filas_por_activo=None, usos_por_pid=None, sin_activo=()):
    filas_por_activo = filas_por_activo or {}
    usos_por_pid = usos_por_pid or {}
    salida = [tarjeta_activo(p, filas_por_activo.get(p["id"]), (usos_por_pid.get(p["id"]) or {}).get("total", 0))
              for p in productos]
    salida += [tarjeta_fila(f) for f in sin_activo]
    return salida


def contadores(lista):
    vivas = [t for t in lista if not t["archivado"]]
    return {"todos": len(vivas),
            "en_prueba": sum(1 for t in vivas if t["en_prueba"]),
            "sin_precio": sum(1 for t in vivas if t["tipo"] == "activo" and t["precio"] is None),
            "sin_url": sum(1 for t in vivas if t["tipo"] == "activo" and not t["url_compra"]),
            "sin_fotos": sum(1 for t in vivas if t["sin_fotos"]),
            "archivados": sum(1 for t in lista if t["archivado"])}


def filtrar(lista, q="", filtro="todos"):
    q = _texto(q).strip()
    if filtro not in FILTROS:
        filtro = "todos"

    def pasa(t):
        if q and q not in t["busqueda"]:
            return False
        if filtro == "archivados":
            return t["archivado"]
        if t["archivado"]:
            return False
        if filtro == "en_prueba":
            return t["en_prueba"]
        if filtro == "sin_precio":
            return t["tipo"] == "activo" and t["precio"] is None
        if filtro == "sin_url":
            return t["tipo"] == "activo" and not t["url_compra"]
        if filtro == "sin_fotos":
            return t["sin_fotos"]
        return True
    return [t for t in lista if pasa(t)]


def ordenar(lista, orden="prioridad"):
    """Las filas sin fotos van siempre al final; luego prioridad desc + nombre, o solo nombre."""
    if orden == "nombre":
        return sorted(lista, key=lambda t: (t["sin_fotos"], _texto(t["nombre"])))
    return sorted(lista, key=lambda t: (t["sin_fotos"], -t["prioridad"], _texto(t["nombre"])))


def paginar(lista, pagina=1, por_pagina=POR_PAGINA):
    try:
        pagina = max(1, int(pagina or 1))
    except (TypeError, ValueError):
        pagina = 1
    inicio = (pagina - 1) * por_pagina
    trozo = list(lista[inicio:inicio + por_pagina])
    return trozo, (inicio + por_pagina) < len(lista)


def contar_usos(claves, sesiones, por_clave_exp, campanas_por_catalogo):
    """{"piezas", "experimentos", "campanas", "total"} de un producto.
    `claves` = catalogo_productos.claves_de(); `sesiones` = un set casefold de
    `productos_ids` por sesión de Crear; `por_clave_exp` = {clave casefold:
    {experimento_id}} (dashboard._experimentos_por_activo);
    `campanas_por_catalogo` = {catalogo_id casefold: n campañas}."""
    ids, nombres = set(claves.get("ids") or ()), set(claves.get("nombres") or ())
    todas = ids | nombres
    piezas = sum(1 for s in sesiones if s & todas)
    exps = set()
    for k in todas:
        exps |= set(por_clave_exp.get(k, ()))
    camps = sum(n for k, n in campanas_por_catalogo.items() if k in ids)
    return {"piezas": piezas, "experimentos": len(exps), "campanas": camps, "total": piezas + len(exps) + camps}

"""Las entradas del selector de «Rendimiento» y la fuente de cada una (spec 2026-10-09 R2–R5). Puro: recibe las
tiendas de Triple Whale, las cuentas de Meta y qué cuentas llegan dentro de cada tienda
(`triple_whale.datos.cuentas_meta_de_tiendas`); no lee la base ni conoce Flask.

Una entrada es un país (su tienda y sus cuentas con ese país) o una tienda o cuenta sin país. Su fuente es Triple
Whale si tiene tienda y Meta si no (R3). Una sola tienda sin país es la fuente de todo el proyecto (R4). Una cuenta
de Meta cuyos anuncios llegan en la copia de una tienda está «dentro» de esa tienda: «Todas» no suma su gasto aparte
(R5), aunque vista sola su entrada siga mostrando Meta."""

TW, META = "tw", "meta"


def _clave_tienda(t):
    return t["pais"] if t.get("pais") else f"tienda:{t['id']}"


def _clave_cuenta(c):
    return c["pais"] if c.get("pais") else f"cuenta:{c['ad_account_id']}"


def _nueva(clave, pais, tienda, fuente):
    return {"clave": clave, "pais": pais, "tienda": tienda, "cuentas": [], "fuente": fuente, "cuentas_suma": [],
            "cubierta": False}


def _orden(e):
    # Primero los países (por código), al final lo que no tiene país, en el orden en que llegó.
    return (e["pais"] is None, e["pais"] or "")


def armar(tiendas, cuentas, cubiertas=None):
    """Las entradas en el orden del selector (ver el docstring del módulo)."""
    cubiertas_todas = set().union(*(cubiertas or {}).values()) if cubiertas else set()
    if len(tiendas) == 1 and not tiendas[0].get("pais"):
        unica = _nueva(_clave_tienda(tiendas[0]), None, tiendas[0], TW)
        unica["cuentas"] = list(cuentas)
        return [unica]
    por_clave = {}
    for t in tiendas:
        por_clave[_clave_tienda(t)] = _nueva(_clave_tienda(t), t.get("pais"), t, TW)
    for c in cuentas:
        k = _clave_cuenta(c)
        e = por_clave.setdefault(k, _nueva(k, c.get("pais"), None, META))
        e["cuentas"].append(c)
        if e["fuente"] == META:
            if c["ad_account_id"] in cubiertas_todas:
                e["cubierta"] = True
            else:
                e["cuentas_suma"].append(c["ad_account_id"])
    # «cubierta» de una entrada Meta = todas sus cuentas llegan dentro de una tienda.
    for e in por_clave.values():
        if e["fuente"] == META:
            e["cubierta"] = bool(e["cuentas"]) and not e["cuentas_suma"]
    return sorted(por_clave.values(), key=_orden)


def elegir(entradas, valor):
    """La entrada pedida, o None = «Todas». Con una sola entrada, siempre esa. Un valor que no es la clave de una
    entrada (de otro proyecto, texto raro) es «Todas»."""
    if len(entradas) == 1:
        return entradas[0]
    v = str(valor or "").strip()
    return next((e for e in entradas if v and e["clave"] == v), None)


def de_legado(entradas, tienda=None, cuenta=None):
    """La clave de la entrada que contiene esa tienda (id) o esa cuenta («act_…»), para los `?tienda=`/`?cuenta=` de
    las pestañas viejas. None si no hay."""
    if tienda not in (None, ""):
        try:
            tid = int(tienda)
        except (TypeError, ValueError):
            return None
        return next((e["clave"] for e in entradas if e["tienda"] and e["tienda"]["id"] == tid), None)
    if cuenta:
        act = str(cuenta).strip()
        return next((e["clave"] for e in entradas for c in e["cuentas"] if c["ad_account_id"] == act), None)
    return None


def alcance(entradas, actual):
    """Lo que lee cada fuente para el alcance elegido (`actual` None = «Todas»):

    - "tw": None sin Triple Whale; si no {"tienda_id": la de la entrada, o None = todas las tiendas}.
    - "meta_fuente": cuentas cuyas ventas salen de Meta (sus anuncios y sus sumas). En «Todas», solo las no
      cubiertas (R5); vista sola, todas las de la entrada (R3).
    - "meta_estructura": todas las cuentas de Meta del alcance (campañas y conjuntos: sirven siempre).
    - "cubiertas_tw": cuentas del alcance cuyas campañas llevan las ventas de Triple Whale (las de entradas Triple
      Whale y, en «Todas», las cubiertas).
    - "fuente": "tw", "meta", "mixta" o None (nada conectado)."""
    elegidas = [actual] if actual else list(entradas)
    tiendas = [e for e in elegidas if e["fuente"] == TW]
    tw = {"tienda_id": tiendas[0]["tienda"]["id"] if actual else None} if tiendas else None
    meta_fuente, cubiertas_tw, estructura = [], [], []
    for e in elegidas:
        ids = [c["ad_account_id"] for c in e["cuentas"]]
        estructura.extend(ids)
        if e["fuente"] == TW:
            if not actual:
                cubiertas_tw.extend(ids)
        elif actual:
            meta_fuente.extend(ids)
        else:
            meta_fuente.extend(e["cuentas_suma"])
            cubiertas_tw.extend(a for a in ids if a not in e["cuentas_suma"])
    fuente = "mixta" if tw and meta_fuente else ("tw" if tw else ("meta" if meta_fuente else None))
    return {"tw": tw, "meta_fuente": meta_fuente, "meta_estructura": estructura, "cubiertas_tw": cubiertas_tw,
            "fuente": fuente}

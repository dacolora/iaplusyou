"""«01 Resultados» y «02 Por país» de Rendimiento cuando el alcance trae Meta o mezcla fuentes (spec 2026-10-09
R5–R8 y A2). Solo lee la base y las tasas ya guardadas (`meta_rendimiento.tasas.mapa`): nunca llama a Triple Whale,
a Meta, al BCE ni a Claude, y cada lectura va agrupada (nada de una consulta por día ni por fila).

Reglas, cada una con su motivo:

1. Series por fuente. La parte Triple Whale es la tienda (`serie_tienda`) y, si todavía no trae los totales de la
   tienda, lo que el Pixel de Triple Whale atribuye a anuncios pagados (`serie_anuncios`). La parte Meta es el
   Pixel de cada cuenta que suma (`valor` es la venta, `compras` el pedido), en la moneda de esa cuenta. Cada fuente
   cuenta lo suyo: una cuenta que ya llega dentro de la tienda (R5) no está en `alc["meta_fuente"]` y no se suma
   aparte, así «Todas» no cuenta dos veces el mismo gasto.
2. Moneda (R6). Si todas las partes comparten moneda, esa; si no, USD convertido día por día con la tasa de ESE
   día. Un día con gasto o ventas y sin tasa deja `usd_ok` en falso y «Resultados» en None: nunca una tasa
   inventada, y nunca una suma a medias.
3. Inicio común (R7, A2). Sumar tres meses de una tienda con trece días de una cuenta daría un total que no es de
   nadie, así que «Desde el inicio» arranca el día en que TODAS las fuentes del alcance ya tienen datos (el más
   tardío de sus primeros días). Una fuente sin ningún día copiado todavía no atrasa a las demás. Con un periodo
   fijo no hay inicio común: es el periodo que pidió la persona.
4. Resultados (R8). Es la misma sección de «Resultados de tu tienda» (`triple_whale.resultados.armar`) con la
   fuente «meta» o «mixta» y sin detalle del día. No recibe antigüedad de anuncios ni cohortes (`inicio_copia`
   None): sin ellas la sección no dibuja una serie «A anuncios nuevos 0 %» que no sería cierta.
5. Por país (R5). Una fila por entrada, cada una con su fuente, su moneda y su equivalente en USD; las entradas
   cuyas cuentas llegan dentro de una tienda salen marcadas (`fuera_de_todas`) para que la nota explique por qué
   «Todas» no es la suma de las filas.
"""
from datetime import date, timedelta

import idiomas
from meta_rendimiento import datos as mdatos
from meta_rendimiento import tasas
from triple_whale import datos as twdatos
from triple_whale import paises, resultados
from triple_whale.panel import PERIODOS, periodo


def _flotante(v):
    return float(v or 0)


def _moneda_de(texto):
    return (texto or "").upper()


def _fila(fecha, moneda, gasto, ingresos, pedidos, act=None):
    return {"fecha": str(fecha)[:10], "moneda": moneda, "act": act, "gasto": _flotante(gasto),
            "ingresos": _flotante(ingresos), "pedidos": _flotante(pedidos)}


def _filas_tw(filas, moneda):
    return [_fila(f["fecha"], moneda, f["gasto"], f["ingresos"], f["pedidos"]) for f in filas]


def _filas_meta(filas, cuentas_por_id):
    return [_fila(f["fecha"], _moneda_de(cuentas_por_id.get(f["ad_account_id"], {}).get("moneda")), f["gasto"],
                  f["valor"], f["compras"], act=f["ad_account_id"]) for f in filas]


class _Tasas:
    """Una lectura de `tasa_cambio` por moneda, la primera vez que se pide. Una moneda desconocida no tiene tasa."""

    def __init__(self, desde, hasta):
        self.desde, self.hasta, self._mapas = desde, hasta, {}

    def factor(self, moneda, fecha):
        if moneda not in self._mapas:
            self._mapas[moneda] = tasas.mapa(moneda, self.desde, self.hasta) if moneda else {}
        return self._mapas[moneda].get(fecha)


def _a_usd(filas, tasa):
    """(gasto, ventas) en USD de unas filas diarias, o None si un día con gasto o ventas no tiene tasa."""
    gasto = ventas = 0.0
    for f in filas:
        factor = tasa.factor(f["moneda"], f["fecha"])
        if factor is None:
            if f["gasto"] or f["ingresos"]:
                return None
            continue
        gasto += f["gasto"] * factor
        ventas += f["ingresos"] * factor
    return gasto, ventas


def _unir_por_dia(filas, convertir, tasa):
    """({fecha: {fecha, gasto, ingresos, pedidos}}, usd_ok): las filas de todas las partes sumadas por día, en USD
    día por día si `convertir`. Un día con montos y sin tasa no se suma y `usd_ok` queda en falso."""
    por_dia, usd_ok = {}, True
    for f in filas:
        dia = por_dia.setdefault(f["fecha"], {"fecha": f["fecha"], "gasto": 0.0, "ingresos": 0.0, "pedidos": 0.0})
        gasto, ingresos = f["gasto"], f["ingresos"]
        if convertir:
            factor = tasa.factor(f["moneda"], f["fecha"])
            if factor is None:
                usd_ok = usd_ok and not (gasto or ingresos)
                continue
            gasto, ingresos = gasto * factor, ingresos * factor
        dia["gasto"] += gasto
        dia["ingresos"] += ingresos
        dia["pedidos"] += f["pedidos"]
    return por_dia, usd_ok


def _nombre(entrada):
    """«Noruega» en el idioma de quien mira; sin país, el dominio de la tienda o el nombre de la cuenta."""
    if entrada.get("nombre"):
        return entrada["nombre"]
    if entrada["pais"]:
        return paises.nombre_pais(entrada["pais"], idiomas.activo())
    if entrada["tienda"]:
        return entrada["tienda"].get("dominio") or ""
    cuenta = entrada["cuentas"][0] if entrada["cuentas"] else {}
    return cuenta.get("nombre") or cuenta.get("ad_account_id") or ""


def _origen(entradas_, actual, origen_tw):
    """R8: de dónde sale la venta de cada entrada que suma. En «Todas» una entrada de Meta cuyas cuentas ya llegan
    dentro de una tienda no aparece (no suma)."""
    salida = []
    for e in [actual] if actual else entradas_:
        if e["fuente"] == "tw":
            origen = origen_tw
        elif actual or e["cuentas_suma"]:
            origen = "pixel_meta"
        else:
            continue
        salida.append({"nombre": _nombre(e), "origen": origen})
    return salida


def _tiendas_del_alcance(entradas_, alc):
    if not alc["tw"]:
        return []
    tienda_id = alc["tw"]["tienda_id"]
    tiendas = [e["tienda"] for e in entradas_ if e["fuente"] == "tw" and e["tienda"]]
    return [t for t in tiendas if tienda_id is None or t["id"] == tienda_id]


def _ultima_copia(tiendas, ids_meta, cuentas_por_id):
    """La copia más vieja de las fuentes que suman; None si alguna todavía no tiene (como la pestaña de Triple
    Whale con sus tiendas)."""
    copias = ([t.get("ultima_sincronizacion") for t in tiendas]
              + [cuentas_por_id.get(a, {}).get("ultima_copia") for a in ids_meta])
    hay = [c for c in copias if c]
    return min(hay) if hay and len(hay) == len(copias) else None


def _resultados(cliente, alc, dias, hoy, desde, hasta, ancho, inicio_real, moneda, convertir, origen_tw, moneda_tw,
                tiendas, cuentas_por_id, tasa):
    """({"resultados", "usd_ok"}): la sección con las series de las fuentes que suman, o None sin una tasa."""
    # Antes del primer día en que todas las fuentes tienen datos la serie traería sumas a medias: no se lee.
    lee = max(ancho.isoformat(), min(inicio_real, hasta)) if inicio_real else ancho.isoformat()
    filas = []
    if alc["tw"]:
        leer = twdatos.serie_tienda if origen_tw == "tienda" else twdatos.serie_anuncios
        filas += _filas_tw(leer(cliente, alc["tw"]["tienda_id"], lee, hasta), moneda_tw)
    if alc["meta_fuente"]:
        filas += _filas_meta(mdatos.cuenta_por_dia(cliente, alc["meta_fuente"], lee, hasta), cuentas_por_id)
    por_dia, usd_ok = _unir_por_dia(filas, convertir, tasa)
    if not usd_ok:
        return {"resultados": None, "usd_ok": False}
    d_desde = date.fromisoformat(desde)
    serie = resultados.por_dia(ancho, date.fromisoformat(hasta), list(por_dia.values()))
    r = resultados.armar(
        dias, serie, (d_desde - ancho).days, hoy, alc["fuente"], moneda, {}, {}, None, None, None, None, "",
        _ultima_copia(tiendas, alc["meta_fuente"], cuentas_por_id),
        inicio_datos=inicio_real, fin_datos=max(por_dia, default=None), con_detalle=False)
    return {"resultados": r, "usd_ok": True}


def _fila_pais(entrada, origen, moneda, gasto, ventas, pedidos, usd):
    gasto_usd, ventas_usd = usd if usd else (None, None)
    return {"entrada": entrada, "fuente": entrada["fuente"], "origen": origen, "moneda": moneda, "gasto": gasto,
            "ventas": ventas, "pedidos": pedidos, "retorno": ventas / gasto if gasto and ventas is not None else None,
            "gasto_usd": gasto_usd, "ventas_usd": ventas_usd, "fuera_de_todas": bool(entrada["cubierta"])}


def _filas_pais_tw(cliente, entradas_tw, desde, hasta, origen_tw, moneda_tw, tasa):
    """Las filas de las entradas con tienda: los totales de todas las tiendas en UNA consulta (`por_tienda`); solo
    sin totales de tienda (Pixel de anuncios pagados) o con la tienda en otra moneda hace falta su serie diaria, que
    es lo único que se puede convertir día por día."""
    por_tienda = ({x["tienda_id"]: x["actual"] for x in twdatos.por_tienda(cliente, desde, hasta, desde, hasta)}
                  if origen_tw == "tienda" and entradas_tw else {})
    filas = []
    for e in entradas_tw:
        tienda_id = e["tienda"]["id"]
        diarias = None
        if origen_tw == "tienda":
            a = por_tienda.get(tienda_id) or {}
            gasto, ventas, pedidos = (_flotante(a.get(k)) for k in ("gasto", "ingresos", "pedidos"))
        else:
            diarias = _filas_tw(twdatos.serie_anuncios(cliente, tienda_id, desde, hasta), moneda_tw)
            gasto, ventas, pedidos = (sum(f[k] for f in diarias) for k in ("gasto", "ingresos", "pedidos"))
        if moneda_tw == "USD":
            usd = (gasto, ventas)
        else:
            if diarias is None:
                diarias = _filas_tw(twdatos.serie_tienda(cliente, tienda_id, desde, hasta), moneda_tw)
            usd = _a_usd(diarias, tasa)
        filas.append(_fila_pais(e, origen_tw, moneda_tw, gasto, ventas, pedidos, usd))
    return filas


def _filas_pais_meta(cliente, entradas_meta, desde, hasta, cuentas_por_id, tasa):
    """Las filas de las entradas de Meta: una sola lectura diaria de todas sus cuentas, agrupada en Python. Una
    entrada cuyas cuentas tienen monedas distintas se muestra en USD (no hay una moneda propia que sumar)."""
    ids = [c["ad_account_id"] for e in entradas_meta for c in e["cuentas"]]
    por_cuenta = {}
    for f in _filas_meta(mdatos.cuenta_por_dia(cliente, ids, desde, hasta), cuentas_por_id):
        por_cuenta.setdefault(f["act"], []).append(f)
    filas = []
    for e in entradas_meta:
        propias = [f for c in e["cuentas"] for f in por_cuenta.get(c["ad_account_id"], [])]
        monedas = {_moneda_de(c.get("moneda")) for c in e["cuentas"]}
        gasto, ventas, pedidos = (sum(f[k] for f in propias) for k in ("gasto", "ingresos", "pedidos"))
        usd = _a_usd(propias, tasa)
        moneda = next(iter(monedas), "")
        if len(monedas) > 1:
            moneda = "USD"
            gasto, ventas = usd if usd else (None, None)
        filas.append(_fila_pais(e, "pixel_meta", moneda, gasto, ventas, pedidos, usd))
    return filas


def _por_pais(cliente, entradas_, desde, hasta, origen_tw, moneda_tw, cuentas_por_id, tasa):
    filas = {f["entrada"]["clave"]: f for f in
             _filas_pais_tw(cliente, [e for e in entradas_ if e["fuente"] == "tw"], desde, hasta, origen_tw, moneda_tw,
                            tasa)
             + _filas_pais_meta(cliente, [e for e in entradas_ if e["fuente"] == "meta"], desde, hasta, cuentas_por_id,
                                tasa)}
    return [filas[e["clave"]] for e in entradas_]


def contexto(cliente, entradas_, actual, alc, dias, hoy, moneda_tw):
    """Lo que pintan «01 Resultados» (con Meta o mezcla) y «02 Por país» para el alcance `alc` de la entrada
    `actual` (None = «Todas») de `pestana_rendimiento.entradas`:

    - "resultados": la sección de `resultados.armar`, o None con fuente Triple Whale (la pestaña usa la suya, que
      trae el detalle del día), sin nada conectado o sin una tasa para convertir (`usd_ok` falso).
    - "usd_ok", "moneda": la moneda de las cifras de arriba ("USD" si las partes no comparten moneda).
    - "inicio_comun": el día desde el que todas las fuentes tienen datos, solo con «Desde el inicio» y fuentes con
      primeros días distintos (R7); "desde" y "hasta": el periodo que se leyó.
    - "origen": [{"nombre", "origen": "tienda"|"pixel_tw"|"pixel_meta"}] de las entradas que suman (R8).
    - "por_pais": las filas de «Por país» (solo «Todas» con dos entradas o más); "fuera_de_todas" marca las
      entradas cuyas cuentas llegan dentro de una tienda (R5)."""
    dias = dias if dias in PERIODOS else 0
    moneda_tw = _moneda_de(moneda_tw)
    cuentas_por_id = {c["ad_account_id"]: c for e in entradas_ for c in e["cuentas"]}
    tiendas = _tiendas_del_alcance(entradas_, alc)
    monedas = ({moneda_tw} if alc["tw"] else set()) | {
        _moneda_de(cuentas_por_id.get(a, {}).get("moneda")) for a in alc["meta_fuente"]}
    convertir = len(monedas) > 1
    moneda = "USD" if convertir else next(iter(monedas), moneda_tw)

    primeros = [p for p in (twdatos.primer_dia_copia(cliente, t["id"]) for t in tiendas) if p]
    primeros += list(mdatos.primeras_fechas(cliente, alc["meta_fuente"]).values())
    inicio_real = max(primeros) if primeros else None
    desde, hasta = periodo(dias, hoy, inicio_real if dias == 0 else None)[:2]
    d_desde = date.fromisoformat(desde)
    ancho = d_desde - timedelta(days=max((date.fromisoformat(hasta) - d_desde).days if dias else 0,
                                         resultados.SEMANAS_EXTRA))
    tasa = _Tasas(ancho.isoformat(), hasta)
    origen_tw = ("tienda" if twdatos.hay_tienda(cliente, alc["tw"]["tienda_id"]) else "pixel_tw") if alc["tw"] else None

    salida = {"resultados": None, "usd_ok": True, "moneda": moneda, "desde": desde, "hasta": hasta,
              "inicio_comun": inicio_real if dias == 0 and len(set(primeros)) > 1 else None,
              "origen": _origen(entradas_, actual, origen_tw), "por_pais": []}
    if alc["fuente"] in ("meta", "mixta"):
        salida.update(_resultados(cliente, alc, dias, hoy, desde, hasta, ancho, inicio_real, moneda, convertir,
                                  origen_tw, moneda_tw, tiendas, cuentas_por_id, tasa))
    if actual is None and len(entradas_) >= 2:
        salida["por_pais"] = _por_pais(cliente, entradas_, desde, hasta, origen_tw, moneda_tw, cuentas_por_id, tasa)
    return salida

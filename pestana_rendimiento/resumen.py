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
   fijo no hay inicio común: es el periodo que pidió la persona. Con fuente solo Triple Whale (enmienda A7, revisión
   final de E1, 2026-10-10) no hay inicio común: «Desde el inicio» es el de Triple Whale (`triple_whale.panel.
   _primer_dia`, cada tienda desde su primer día), el mismo de sus Resultados y de la galería que cobra, así «Por
   país» suma lo que dicen los Resultados de arriba.
4. Resultados (R8). Es la misma sección de «Resultados de tu tienda» (`triple_whale.resultados.armar`) con la
   fuente «meta» o «mixta». No recibe antigüedad de anuncios ni cohortes (`inicio_copia` None): sin ellas la sección
   no dibuja una serie «A anuncios nuevos 0 %» que no sería cierta. Desde E2 tarea 7 (2026-10-10, spec A3) trae el
   detalle del día (`con_detalle=True`; `rutas.ver_panel` le pone la URL de `rendimiento.ver_dia`).
5. Por país (R5). Una fila por entrada, cada una con su fuente, su moneda y su equivalente en USD; las entradas
   cuyas cuentas llegan dentro de una tienda salen marcadas (`fuera_de_todas`) para que la nota explique por qué
   «Todas» no es la suma de las filas.
6. Moneda de «Por país» (R6, revisión final de E1). La cifra principal va en la moneda común de todas las filas
   (`moneda_pais`; entonces no se convierte nada ni se piden tasas) o, si no la hay, en USD; una fila sin USD
   (`sin_usd`) lo dice y la página avisa (`por_pais_sin_usd`): nunca «—» callado ni una tasa inventada.
7. El detalle de un día (`dia`, E2 tarea 7, 2026-10-10; spec A3: con alcance solo Triple Whale sigue siendo
   `triple_whale.panel.contexto_dia`). Un día del inicio común de la regla 3 a ayer (hoy va a medias) y no después
   del último día que todas las fuentes ya traen (`_fin_datos`: la gráfica no abre esos días); fuera, un motivo en
   palabras para un 400. Las cifras van en la moneda de los Resultados (regla 2): en USD con la tasa de ESE día y,
   sin ella, «USD no disponible ese día», nunca una inventada; el mismo día de la semana anterior sin tasa no se
   compara. Los anuncios: los 5 que más vendieron entre las dos fuentes por ventas en USD (Triple Whale: lo que el
   Pixel atribuye a anuncios con gasto ese día; Meta: el valor de compras), cada uno mostrado en su moneda; «nuevo» es
   hasta su primer día con gasto en SU copia + 13, y solo pasados 14 días del inicio de esa copia. Una fuente con
   gasto ese día y sin ningún anuncio copiado (la copia de anuncios de Meta guarda 90 días) lo dice
   (`anuncios_fuera`) en vez de «ningún anuncio tuvo gasto». Consultas fijas: una por lectura, nunca por anuncio.
"""
from datetime import date, timedelta

from flask_babel import gettext

import idiomas
from meta_rendimiento import datos as mdatos
from meta_rendimiento import tasas
from triple_whale import datos as twdatos
from triple_whale import paises, resultados
from triple_whale.panel import PERIODOS, _primer_dia, periodo


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


def _monedas(alc, cuentas_por_id, moneda_tw):
    """(convertir, moneda) de las cifras del alcance (regla 2): la moneda que comparten todas las partes que suman, o
    "USD" convertido día por día si no la comparten. Una cuenta sin moneda conocida no comparte la de nadie."""
    monedas = ({moneda_tw} if alc["tw"] else set()) | {
        _moneda_de(cuentas_por_id.get(a, {}).get("moneda")) for a in alc["meta_fuente"]}
    convertir = len(monedas) > 1
    return convertir, "USD" if convertir else next(iter(monedas), moneda_tw)


def _primeros(cliente, alc, tiendas):
    """(primeros días de las tiendas del alcance, {act: primer día} de sus cuentas de Meta que suman): de aquí sale el
    inicio común de R7 (regla 3). Una fuente sin ningún día copiado no aparece."""
    primeros_tw = [p for p in (twdatos.primer_dia_copia(cliente, t["id"]) for t in tiendas) if p]
    return primeros_tw, mdatos.primeras_fechas(cliente, alc["meta_fuente"])


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


def _dia(valor):
    return str(valor)[:10] if valor else None


def _fin_datos(filas, lee, origen_tw, con_datos, tiendas, cuentas_por_id):
    """El último día que TODAS las fuentes con datos ya traen: el más temprano de los finales de cada fuente. Si una
    copia va atrasada, esos días no son ventas en cero de esa fuente: salen «sin copia» y no entran en cifras ni
    comparaciones (sumar solo a la fuente que sí llegó daría una caída que no existe).

    `con_datos` son las fuentes que ya copiaron algún día (None = la parte Triple Whale, o el id de una cuenta de
    Meta): una fuente que todavía no copió nada no atrasa a las demás, pero una que dejó de copiarse sí, aunque no
    tenga ninguna fila dentro del periodo.
    - Una fuente con una fila diaria para cada día (la tienda de Triple Whale) termina en su última fila: es lo que
      también atrapa una sincronización que dejó la fecha de copia al día pero no trajo los totales de la tienda.
      Sin ninguna fila desde `lee`, terminó antes de que empiece lo que se lee.
    - Una fuente que no tiene filas los días sin actividad (una cuenta de Meta en pausa; los anuncios pagados de
      Triple Whale) termina en el día de su última copia o en su última fila, el que sea más tarde: una cuenta
      pausada y al día no atrasa a las demás. Sin filas ni fecha de copia no se sabe y no cuenta."""
    ultima_fila = {}
    for f in filas:
        ultima_fila[f["act"]] = max(ultima_fila.get(f["act"], ""), f["fecha"])
    antes = (date.fromisoformat(lee) - timedelta(days=1)).isoformat()
    fines = []
    for clave in con_datos:
        ultima = ultima_fila.get(clave)
        if clave is None:
            if origen_tw == "tienda":
                fines.append(ultima or antes)
                continue
            copias = [c for c in (_dia(t.get("ultima_sincronizacion")) for t in tiendas) if c]
            copia = min(copias) if copias else None
        else:
            copia = _dia(cuentas_por_id.get(clave, {}).get("ultima_copia"))
        conocidos = [x for x in (ultima, copia) if x]
        if conocidos:
            fines.append(max(conocidos))
    return min(fines, default=None)


def _resultados(cliente, alc, dias, hoy, desde, hasta, ancho, inicio_real, moneda, convertir, origen_tw, moneda_tw,
                tiendas, cuentas_por_id, con_datos, tasa):
    """({"resultados", "usd_ok"}): la sección con las series de las fuentes que suman, o None sin una tasa."""
    # «Desde el inicio» arranca el día en que todas las fuentes tienen datos (R7): antes la serie traería sumas a
    # medias. Un periodo fijo lee desde `ancho`, como la pestaña de Triple Whale: lo que cae dentro del periodo
    # cuenta entero (así «Todas» cuadra con las filas de «Por país») y la comparación con el periodo anterior y los
    # días raros se protegen con `inicio_datos`.
    lee = desde if dias == 0 else ancho.isoformat()
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
        inicio_datos=inicio_real, fin_datos=_fin_datos(filas, lee, origen_tw, con_datos, tiendas, cuentas_por_id),
        con_detalle=True,
        # `dia` rechaza lo anterior a este mismo inicio común (`_primeros`): esos días no se ofrecen (PND-294).
        inicio_detalle=inicio_real or resultados.NINGUN_DIA,
        # Más de una fuente con copia (la tienda y cuentas de Meta, o varias cuentas): lo anterior al inicio común es
        # «todavía no estaban todas tus fuentes», no «antes de la primera copia» (una fuente sí tenía).
        varias_fuentes=len(con_datos) > 1)
    return {"resultados": r, "usd_ok": True}


def _fila_pais(entrada, origen, moneda, gasto, ventas, pedidos, usd):
    gasto_usd, ventas_usd = usd if usd else (None, None)
    return {"entrada": entrada, "fuente": entrada["fuente"], "origen": origen, "moneda": moneda, "gasto": gasto,
            "ventas": ventas, "pedidos": pedidos, "retorno": ventas / gasto if gasto and ventas is not None else None,
            "gasto_usd": gasto_usd, "ventas_usd": ventas_usd, "fuera_de_todas": bool(entrada["cubierta"])}


def _moneda_pais(entradas_, moneda_tw):
    """La moneda de la cifra principal de «Por país» (regla 6): la que comparten TODAS las filas, o "USD". Se sabe
    antes de leer nada: una entrada con tienda va en la moneda del proyecto en Triple Whale, una de Meta en la de sus
    cuentas (con varias, en USD). Una cuenta sin moneda conocida no comparte la de nadie."""
    monedas = set()
    for e in entradas_:
        if e["fuente"] == "tw":
            monedas.add(moneda_tw)
        else:
            propias = {_moneda_de(c.get("moneda")) for c in e["cuentas"]}
            monedas.add(next(iter(propias)) if len(propias) == 1 else "USD")
    return next(iter(monedas)) if len(monedas) == 1 and "" not in monedas else "USD"


def _en_moneda_pais(fila, moneda_pais):
    """La cifra principal de la fila en `moneda_pais` (`gasto_vista`, `ventas_vista`) y `sin_usd` si hacía falta USD
    y no hay tasa."""
    if fila["moneda"] == moneda_pais:
        fila.update(gasto_vista=fila["gasto"], ventas_vista=fila["ventas"], sin_usd=False)
    else:
        fila.update(gasto_vista=fila["gasto_usd"], ventas_vista=fila["ventas_usd"], sin_usd=fila["gasto_usd"] is None)
    return fila


def _filas_pais_tw(cliente, entradas_tw, desde, hasta, origen_tw, moneda_tw, tasa, con_usd=True):
    """Las filas de las entradas con tienda: los totales de todas las tiendas en UNA consulta (`por_tienda`); solo
    sin totales de tienda (Pixel de anuncios pagados) o con la tienda en otra moneda hace falta su serie diaria, que
    es lo único que se puede convertir día por día. Sin `con_usd` (todas las filas comparten una moneda que no es USD)
    no se convierte nada: `gasto_usd` queda en None."""
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
        elif not con_usd:
            usd = None
        else:
            if diarias is None:
                diarias = _filas_tw(twdatos.serie_tienda(cliente, tienda_id, desde, hasta), moneda_tw)
            usd = _a_usd(diarias, tasa)
        filas.append(_fila_pais(e, origen_tw, moneda_tw, gasto, ventas, pedidos, usd))
    return filas


def _filas_pais_meta(cliente, entradas_meta, desde, hasta, cuentas_por_id, tasa, con_usd=True):
    """Las filas de las entradas de Meta: una sola lectura diaria de todas sus cuentas, agrupada en Python. Una
    entrada cuyas cuentas tienen monedas distintas se muestra en USD (no hay una moneda propia que sumar). Sin
    `con_usd`, como en `_filas_pais_tw`."""
    ids = [c["ad_account_id"] for e in entradas_meta for c in e["cuentas"]]
    por_cuenta = {}
    for f in _filas_meta(mdatos.cuenta_por_dia(cliente, ids, desde, hasta), cuentas_por_id):
        por_cuenta.setdefault(f["act"], []).append(f)
    filas = []
    for e in entradas_meta:
        propias = [f for c in e["cuentas"] for f in por_cuenta.get(c["ad_account_id"], [])]
        monedas = {_moneda_de(c.get("moneda")) for c in e["cuentas"]}
        gasto, ventas, pedidos = (sum(f[k] for f in propias) for k in ("gasto", "ingresos", "pedidos"))
        usd = _a_usd(propias, tasa) if con_usd else None
        moneda = next(iter(monedas), "")
        if len(monedas) > 1:
            moneda = "USD"
            gasto, ventas = usd if usd else (None, None)
        filas.append(_fila_pais(e, "pixel_meta", moneda, gasto, ventas, pedidos, usd))
    return filas


def _por_pais(cliente, entradas_, desde, hasta, origen_tw, moneda_tw, cuentas_por_id, tasa):
    """(filas, moneda_pais): las filas de «Por país» en el orden del selector, cada una con su cifra principal en
    `moneda_pais` (regla 6)."""
    moneda_pais = _moneda_pais(entradas_, moneda_tw)
    con_usd = moneda_pais == "USD"
    filas = {f["entrada"]["clave"]: f for f in
             _filas_pais_tw(cliente, [e for e in entradas_ if e["fuente"] == "tw"], desde, hasta, origen_tw, moneda_tw,
                            tasa, con_usd)
             + _filas_pais_meta(cliente, [e for e in entradas_ if e["fuente"] == "meta"], desde, hasta, cuentas_por_id,
                                tasa, con_usd)}
    return [_en_moneda_pais(filas[e["clave"]], moneda_pais) for e in entradas_], moneda_pais


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
      entradas cuyas cuentas llegan dentro de una tienda (R5); "gasto_vista"/"ventas_vista", su cifra en
      "moneda_pais" (regla 6), y "sin_usd" si hacía falta USD y no hay tasa ("por_pais_sin_usd": alguna)."""
    dias = dias if dias in PERIODOS else 0
    moneda_tw = _moneda_de(moneda_tw)
    cuentas_por_id = {c["ad_account_id"]: c for e in entradas_ for c in e["cuentas"]}
    tiendas = _tiendas_del_alcance(entradas_, alc)
    convertir, moneda = _monedas(alc, cuentas_por_id, moneda_tw)

    solo_tw = alc["fuente"] == "tw"
    if solo_tw:
        # A7: con solo Triple Whale, su propio «Desde el inicio» (cada tienda desde su primer día), el de sus
        # Resultados y el de la galería que cobra; el inicio común de R7 es para mezclas (regla 3).
        primeros_tw, primeros_meta, primeros = [], {}, []
        inicio_real = _primer_dia(cliente, alc["tw"]["tienda_id"])
    else:
        primeros_tw, primeros_meta = _primeros(cliente, alc, tiendas)
        primeros = primeros_tw + list(primeros_meta.values())
        inicio_real = max(primeros) if primeros else None
    desde, hasta = periodo(dias, hoy, inicio_real if dias == 0 else None)[:2]
    d_desde = date.fromisoformat(desde)
    ancho = d_desde - timedelta(days=max((date.fromisoformat(hasta) - d_desde).days if dias else 0,
                                         resultados.SEMANAS_EXTRA))
    tasa = _Tasas(ancho.isoformat(), hasta)
    origen_tw = ("tienda" if twdatos.hay_tienda(cliente, alc["tw"]["tienda_id"]) else "pixel_tw") if alc["tw"] else None

    salida = {"resultados": None, "usd_ok": True, "moneda": moneda, "desde": desde, "hasta": hasta,
              "inicio_comun": inicio_real if dias == 0 and len(set(primeros)) > 1 else None,
              "origen": _origen(entradas_, actual, origen_tw), "por_pais": [], "moneda_pais": moneda,
              "por_pais_sin_usd": False}
    if alc["fuente"] in ("meta", "mixta"):
        salida.update(_resultados(cliente, alc, dias, hoy, desde, hasta, ancho, inicio_real, moneda, convertir,
                                  origen_tw, moneda_tw, tiendas, cuentas_por_id,
                                  ([None] if primeros_tw else []) + list(primeros_meta), tasa))
    if actual is None and len(entradas_) >= 2:
        salida["por_pais"], salida["moneda_pais"] = _por_pais(cliente, entradas_, desde, hasta, origen_tw, moneda_tw,
                                                              cuentas_por_id, tasa)
        salida["por_pais_sin_usd"] = any(f["sin_usd"] for f in salida["por_pais"])
    return salida


# --------------------------------------------------------------------- el detalle de un día (regla 7) ---

LIMITE_ANUNCIOS_DIA = 5


def _totales_dia(filas, fecha, convertir, tasa):
    """({"ing", "gas", "ped"} de ese día o None si ninguna fuente tiene fila ese día, usd_ok)."""
    por_dia, usd_ok = _unir_por_dia([f for f in filas if f["fecha"] == fecha], convertir, tasa)
    d = por_dia.get(fecha)
    return ({"ing": d["ingresos"], "gas": d["gasto"], "ped": d["pedidos"]} if d else None), usd_ok


def _edad_conocida(inicio, fecha):
    """True si la antigüedad de un anuncio de esa copia se conoce ese día: 14 días después de su primer día copiado."""
    return bool(inicio) and fecha >= date.fromisoformat(str(inicio)[:10]) + timedelta(days=resultados.DIAS_NUEVO)


def dia(cliente, entradas_, alc, fecha, hoy, moneda_tw):
    """«Qué pasó el …» con Meta o con fuentes mezcladas (regla 7): (detalle, None) con el contexto de
    `triple_whale.resultados.detalle_dia` más `anuncios_fuera` ("tw" | "meta" | "ambas" | "") e `ir_a` (el bloque que abre «Ver todos los anuncios →»),
    o (None, motivo en palabras) para un 400. `alc` es el de `pestana_rendimiento.entradas.alcance` con fuente "meta" o
    "mixta"; con solo Triple Whale el detalle es `triple_whale.panel.contexto_dia`."""
    moneda_tw = _moneda_de(moneda_tw)
    cuentas_por_id = {c["ad_account_id"]: c for e in entradas_ for c in e["cuentas"]}
    tiendas = _tiendas_del_alcance(entradas_, alc)
    convertir, moneda = _monedas(alc, cuentas_por_id, moneda_tw)
    primeros_tw, primeros_meta = _primeros(cliente, alc, tiendas)
    primeros = primeros_tw + list(primeros_meta.values())
    inicio = max(primeros) if primeros else None
    f = fecha.isoformat()
    if not inicio or f < inicio or fecha >= hoy:
        return None, gettext("Ese día no tiene datos completos.")
    # Después del chequeo del rango: una fecha absurda (0001-01-02) haría que restar 7 días reventara (OverflowError, un
    # 500 en vez del 400 de las demás; revisión de la tarea 7).
    f_antes = (fecha - timedelta(days=7)).isoformat()

    # Las cifras del día y del mismo día de la semana anterior: una lectura por fuente, como los Resultados.
    tienda_id = alc["tw"]["tienda_id"] if alc["tw"] else None
    origen_tw = ("tienda" if twdatos.hay_tienda(cliente, tienda_id) else "pixel_tw") if alc["tw"] else None
    filas = []
    if alc["tw"]:
        leer = twdatos.serie_tienda if origen_tw == "tienda" else twdatos.serie_anuncios
        filas += _filas_tw(leer(cliente, tienda_id, f_antes, f), moneda_tw)
    if alc["meta_fuente"]:
        filas += _filas_meta(mdatos.cuenta_por_dia(cliente, alc["meta_fuente"], f_antes, f), cuentas_por_id)
    con_datos = ([None] if primeros_tw else []) + list(primeros_meta)
    fin = _fin_datos(filas, f_antes, origen_tw, con_datos, tiendas, cuentas_por_id)
    if fin and f > fin:
        # La gráfica no abre los días que una fuente todavía no trae (van «sin copia»): sumar solo la que llegó daría
        # una caída que no existe.
        return None, gettext("Ese día todavía no está en la copia de todas tus fuentes.")
    tasa = _Tasas(f_antes, f)
    del_dia, usd_ok = _totales_dia(filas, f, convertir, tasa)
    if not usd_ok:
        return None, gettext("USD no disponible ese día: falta la tasa de cambio de una de tus monedas.")
    antes, antes_ok = _totales_dia(filas, f_antes, convertir, tasa) if f_antes >= inicio else (None, True)
    if not antes_ok:
        antes = None                       # sin tasa ese día no se compara (nunca una tasa inventada)

    # Los anuncios de cada fuente: una lectura por fuente (Triple Whale en la moneda del proyecto; Meta, los mejores de
    # cada cuenta) y el orden final por ventas en USD.
    anuncios, arranques, fuera = [], [], []
    gasto_tw = sum(x["gasto"] for x in filas if x["fecha"] == f and x["act"] is None)
    gasto_meta = sum(x["gasto"] for x in filas if x["fecha"] == f and x["act"] is not None)
    if alc["tw"]:
        conocida = _edad_conocida(twdatos.inicio_para_antiguedad(cliente, tienda_id), fecha)
        propios = twdatos.anuncios_del_dia(cliente, tienda_id, f, limite=LIMITE_ANUNCIOS_DIA)
        anuncios += [dict(a, fuente="tw", moneda=moneda_tw, edad_conocida=conocida) for a in propios]
        arranques.append(twdatos.arrancaron_el(cliente, tienda_id, f) if conocida else None)
        if gasto_tw > 0 and not propios:
            fuera.append("tw")
    if alc["meta_fuente"]:
        conocida = _edad_conocida(mdatos.inicio_para_antiguedad(cliente, alc["meta_fuente"]), fecha)
        propios = mdatos.anuncios_del_dia(cliente, alc["meta_fuente"], f, limite=LIMITE_ANUNCIOS_DIA)
        anuncios += [dict(a, canal=resultados.CANAL_META, fuente="meta", edad_conocida=conocida,
                          moneda=_moneda_de(cuentas_por_id.get(a["ad_account_id"], {}).get("moneda")))
                     for a in propios]
        arranques.append(mdatos.arrancaron_el(cliente, alc["meta_fuente"], f) if conocida else None)
        if gasto_meta > 0 and not propios:
            fuera.append("meta")

    def en_usd(a, clave):
        if not convertir:
            return a[clave]
        factor = tasa.factor(a["moneda"], f)
        return None if factor is None else a[clave] * factor

    # Sin tasa (una cuenta sin moneda conocida: su gasto ya habría frenado el día) al final, nunca convertida a ojo.
    anuncios.sort(key=lambda a: (en_usd(a, "ingresos") is None, -(en_usd(a, "ingresos") or 0),
                                 -(en_usd(a, "gasto") or 0), a["ad_id"]))
    anuncios = anuncios[:LIMITE_ANUNCIOS_DIA]
    creatv = twdatos.piezas_creatv(cliente, [a["ad_id"] for a in anuncios if a["canal"] == resultados.CANAL_META])
    anterior, siguiente = fecha - timedelta(days=1), fecha + timedelta(days=1)
    detalle = resultados.detalle_dia(
        fecha, del_dia or {"ing": 0.0, "gas": 0.0, "ped": 0.0}, antes, {}, anuncios,
        None if None in arranques else sum(arranques), creatv, moneda, alc["fuente"],
        anterior.isoformat() if anterior.isoformat() >= inicio else None,
        siguiente.isoformat() if siguiente < hoy and not (fin and siguiente.isoformat() > fin) else None)
    # `anuncios_fuera`: qué fuente tuvo gasto ese día y no trae sus anuncios ("tw", "meta" o "ambas"; "" si ninguna).
    # El aviso culpa a la que falta: antes siempre culpaba a la copia de 90 días de Meta (revisión de la tarea 7).
    detalle.update(anuncios_fuera="ambas" if len(fuera) > 1 else (fuera[0] if fuera else ""), ir_a="tw-galeria")
    return detalle, None

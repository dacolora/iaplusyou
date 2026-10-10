"""El alcance de las cuentas de Meta con la forma del de Triple Whale (Rendimiento E2, tarea 3, 2026-10-10).

Por qué existe: «Cómo mejorarlo», el lote y «Evaluar con IA» (`triple_whale/pedidos.py`) y la galería
(`triple_whale.panel.galeria`) leen un «alcance» con la forma de `triple_whale.panel.alcance` (`config`, `tienda`,
`tienda_id`, `canal`, `dias`, `ev`, `desde`, `hasta`, `params`). Los anuncios de las cuentas de Meta que no cubre ninguna
tienda (fuente "meta") reusan ese flujo entero, con sus garantías de precio y de no cobrar dos veces, si les armamos
el mismo dict. Este módulo no cobra, no llama a Meta ni a Claude: solo lee la copia local (`meta_rendimiento.panel`),
con un número fijo de consultas que no depende de cuántos anuncios ni cuántas cuentas haya.

Lo que cambia respecto del de Triple Whale, cada cosa con su motivo:

1. `fuente = "meta"` (clave nueva; el de Triple Whale no la trae y se lee como "triple_whale"). Quien pide el análisis
   la pasa a la foto (`mejorar.foto(..., fuente=)`), y el prompt dice «de Meta» en vez de «de Triple Whale».
2. `config = {"moneda", "modelo_atribucion", "ventana_atribucion"}`: el modelo y la ventana son nombres propios de lo
   que mide Meta («Pixel de Meta», «Meta»), no se traducen. `moneda` es la de las cuentas si todas comparten una;
   si difieren, o alguna no tiene moneda conocida, es None (jamás una inventada: ni sumar SEK con EUR ni «USD» por
   defecto, regla R6) y cada anuncio guarda la suya en `moneda`: el pedido pagado usa la del anuncio.
3. Canal. La copia de Meta llama a sus anuncios `canal = "meta"`; el flujo pagado (llaves `(canal, ad_id)` de
   `tw_analisis`, `ganadores_del_canal`, `medios_meta`, la tarjeta) conoce el de Triple Whale, `facebook-ads`
   (`triple_whale.CANAL_META`): todos los anuncios lo llevan. Se cambia DESPUÉS de evaluar (los anillos y los
   veredictos se calculan por cuenta y por canal, y todos son del mismo).
4. Veredicto, diagnóstico y anillos de cada anuncio son contra SU cuenta (lo decide `meta_panel.evaluar_anuncios`, una
   evaluación por cuenta). Lo que el prompt pagado lee de `ev` NO puede ser por anuncio (`pedidos.pedir_analisis` toma
   `benchmarks_canal`, `meta_roas` y el costo por venta de todo el alcance), así que recibe las medianas de TODOS los
   anuncios del alcance: con una cuenta (lo habitual: una entrada del selector), las de esa cuenta, igual que en Triple
   Whale; con varias, las de su unión. Quien necesite el contexto exacto de la cuenta de un anuncio pide el alcance de
   esa cuenta sola (`alcance(cliente, [su_cuenta], …)`).
5. Con monedas mezcladas se quitan las dos cifras en dinero que saldrían de mezclarlas: la mediana del costo por mil
   impresiones (`benchmarks["cpm"]` queda None; CTR, gancho, retención, conversión y ROAS son cocientes y valen) y el
   costo por venta del canal (`ev["cuenta"]["canales"]` queda vacío: `pedidos` y la tarjeta lo leen como «sin dato»).
6. `meta_roas`: la meta de ROAS del proyecto; apagada, cada cuenta se mide con su mediana y el alcance de varias da
   UNA, la de todos sus anuncios.
"""
from datetime import date

import decisor
import proyectos
import triple_whale
from meta_rendimiento import panel as meta_panel
from triple_whale import evaluacion

FUENTE = "meta"
MODELO_ATRIBUCION = "Pixel de Meta"     # nombres propios de lo que mide Meta: no pasan por el catálogo
VENTANA_ATRIBUCION = "Meta"


def _ids_del_proyecto(ids, cuentas_por_id):
    """Los ids que son cuentas de este proyecto, sin repetir y en su orden: lo demás (un id de otro proyecto, uno
    inventado) se ignora, porque los ids llegan de la pestaña y quien lee una cuenta ajena lee a otro cliente."""
    salida = []
    for a in ids or ():
        if isinstance(a, str) and a in cuentas_por_id and a not in salida:
            salida.append(a)
    return salida


def _moneda_comun(cuentas):
    """La moneda que comparten TODAS esas cuentas; None si hay más de una o si alguna no tiene moneda conocida."""
    monedas = {(c.get("moneda") or "").upper() for c in cuentas}
    return next(iter(monedas)) if len(monedas) == 1 and "" not in monedas else None


def alcance(cliente, ids, dias, hoy, params, cuentas_por_id=None):
    """El alcance de esas cuentas de Meta con la forma de `triple_whale.panel.alcance` (ver el módulo), o None si
    ninguno de `ids` es una cuenta del proyecto. `dias`: 0 = desde el inicio, 7, 14, 30 o 90; otro cae en 0. `hoy`, el
    día de referencia (como en Triple Whale). `params`, los de la pestaña (`entrada`, `dias`), se copian. Quien ya leyó
    las cuentas del proyecto (`meta_panel.lista`, el panel) las pasa en `cuentas_por_id` y se ahorra la lectura."""
    if cuentas_por_id is None:
        cuentas_por_id = {c["ad_account_id"]: c for c in meta_panel.lista(cliente)}
    ids = _ids_del_proyecto(ids, cuentas_por_id)
    if not ids:
        return None
    hoy = hoy or date.today()
    dias = dias if not isinstance(dias, bool) and dias in meta_panel.PERIODOS_RENDIMIENTO else 0
    desde, hasta, _, _ = meta_panel.rango_fechas(cliente, ids, dias, hoy)
    r = meta_panel.anuncios_evaluados(cliente, ids, desde, hasta, hoy, cuentas_por_id)
    anuncios = r["ev"]["anuncios"]
    for a in anuncios:
        a["canal"] = triple_whale.CANAL_META
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    moneda = _moneda_comun(cuentas_por_id[a] for a in ids)
    bench = evaluacion.benchmarks([a["m"] for a in anuncios],
                                  reglas.get("impresiones_min", evaluacion.IMPRESIONES_MIN_DEFECTO))
    cuenta = evaluacion.resumen_cuenta(anuncios)
    if moneda is None:                    # SEK con EUR: ni un costo por mil ni un costo por venta que no es de nadie
        bench["cpm"] = None
        cuenta["canales"] = []
    meta_roas = r["meta_roas"] if r["meta_roas"] is not None else evaluacion.meta_roas(reglas, bench)
    ev = {"anuncios": anuncios, "benchmarks": bench, "cuenta": cuenta, "conteo": r["conteo"],
          "hay_ventas": r["ev"]["hay_ventas"], "meta_roas": meta_roas,
          "benchmarks_canal": {triple_whale.CANAL_META: dict(bench)}}
    return {"config": {"moneda": moneda, "modelo_atribucion": MODELO_ATRIBUCION,
                       "ventana_atribucion": VENTANA_ATRIBUCION},
            "tienda": None, "tienda_id": None, "dias": dias, "canal": None, "ev": ev, "desde": desde, "hasta": hasta,
            "params": dict(params or {}), "fuente": FUENTE}

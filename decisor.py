"""
Decisor (spec §5): función pura sobre snapshots + reglas + contexto. Tráfico
filtra (puerta 1), ventas decide (puerta 2, solo con atribución). Nunca toca
la base ni Meta: quien la llama (tareas/experimentos.exp_decidir) arma el
contexto y ejecuta/propone la acción según el modo.

`decidir` sigue pura: el `motivo` sale de `gettext`, que fuera de una llamada
dentro de `idiomas.en_idioma(...)` devuelve el español tal cual (locale por
defecto), así que la función no gana ningún efecto de red ni de app.
"""
from flask_babel import gettext

from idiomas import N_

REGLAS_DEFECTO = {
    "ventana_horas": 48, "impresiones_min": 1000, "gasto_min_x_presupuesto": 2.0,
    "cpc_max": None, "ctr_min": 1.0, "thruplay_min": 0.15,
    "ventana_ventas_horas": 72, "cpa_max": None, "roas_min": 2.0,
    "n_reediciones": 3, "n_regeneraciones": 2, "escalar_pct_dia": 20, "escalar_tope_dia": None,
}
_ENTEROS = {"ventana_horas", "impresiones_min", "ventana_ventas_horas", "n_reediciones", "n_regeneraciones", "escalar_pct_dia"}
# Umbrales que un cliente/experimento puede desactivar explícitamente pasando
# None (o "" desde un formulario web) en su capa: la ausencia de valor apaga
# la comparación, no equivale a "sin dato todavía".
_UMBRALES_DESACTIVABLES = {"cpc_max", "ctr_min", "thruplay_min", "cpa_max", "roas_min", "escalar_tope_dia"}
# Alias públicos para los formularios (dashboard) — misma tupla de claves.
ENTEROS = frozenset(_ENTEROS)
UMBRALES_DESACTIVABLES = frozenset(_UMBRALES_DESACTIVABLES)
# Cada regla dicha en palabras para «Cómo decide el motor» (misma clave que REGLAS_DEFECTO; sin claves de código a la
# vista, spec 2026-10-02 §4.7). N_: se traduce donde se muestra (|traducir en la plantilla), no acá.
ETIQUETAS = {
    "ventana_horas": N_("Horas mínimas corriendo"), "impresiones_min": N_("Impresiones mínimas"),
    "gasto_min_x_presupuesto": N_("Días de su presupuesto diario que debe haber gastado"),
    "cpc_max": N_("Costo por clic máximo (en la moneda de la cuenta)"), "ctr_min": N_("CTR mínimo (%)"),
    "thruplay_min": N_("Parte mínima que ve el video completo (0–1)"),
    "ventana_ventas_horas": N_("Horas para esperar ventas"), "cpa_max": N_("Costo por compra máximo (en la moneda de la cuenta)"),
    "roas_min": N_("ROAS mínimo"),
    "escalar_pct_dia": N_("Cuánto sube el presupuesto por día (%)"),
    "escalar_tope_dia": N_("Tope del presupuesto diario al escalar (en la moneda de la cuenta)"),
    "n_reediciones": N_("Versiones nuevas del guion al derivar"), "n_regeneraciones": N_("Clones nuevos al derivar (cada uno es un video nuevo que se cobra)"),
}
# Cómo se agrupan en el formulario: (título del grupo, reglas en el orden en que se leen). Toda clave de
# REGLAS_DEFECTO está en un solo grupo (una prueba lo exige): una regla que no esté aquí no se vería en el formulario.
GRUPOS_REGLAS = (
    (N_("Antes de juzgar una pieza"), ("ventana_horas", "impresiones_min", "gasto_min_x_presupuesto")),
    (N_("Cuándo pierde por tráfico"), ("cpc_max", "ctr_min", "thruplay_min")),
    (N_("Cuándo gana o pierde por ventas"), ("ventana_ventas_horas", "cpa_max", "roas_min")),
    (N_("Qué hace con una ganadora"), ("escalar_pct_dia", "escalar_tope_dia", "n_reediciones", "n_regeneraciones")),
)


def reglas_desde_formulario(form):
    """Convierte un formulario web en una capa de reglas: por cada clave de
    REGLAS_DEFECTO, vacío → no se guarda (hereda); número → se guarda (int en
    las enteras); `sin_<clave>` marcado en un umbral desactivable → None
    explícito (apaga el umbral). Devuelve (reglas, errores) donde errores es
    la lista de claves con valor no numérico."""
    reglas, errores = {}, []
    for k in REGLAS_DEFECTO:
        if k in _UMBRALES_DESACTIVABLES and form.get(f"sin_{k}"):
            reglas[k] = None
            continue
        crudo = (form.get(k) or "").strip()
        if crudo == "":
            continue
        n = _num(k, crudo)
        if n is None or n != n or n in (float("inf"), float("-inf")):
            errores.append(k)
            continue
        reglas[k] = n
    return reglas, errores


def _num(clave, valor):
    if valor is None or valor == "":
        return None
    try:
        return int(float(valor)) if clave in _ENTEROS else float(valor)
    except (TypeError, ValueError, OverflowError):
        return None


def _int_or_none(valor):
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        try:
            return int(float(valor))
        except (TypeError, ValueError):
            return None


def reglas_efectivas(reglas_cliente, reglas_experimento):
    out = dict(REGLAS_DEFECTO)
    for capa in (reglas_cliente or {}, reglas_experimento or {}):
        for k, v in capa.items():
            if k not in REGLAS_DEFECTO:
                continue
            if k in _UMBRALES_DESACTIVABLES and (v is None or v == ""):
                # Override explícito para apagar el umbral.
                out[k] = None
                continue
            n = _num(k, v)
            if n is not None:
                out[k] = n
            # Si n es None y la clave no es un umbral desactivable, se
            # conserva el valor de la capa anterior (no se toca out[k]).
    return out


def _f(m, k):
    try:
        return float(m.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def _resultado(veredicto, motivo, accion, puerta, numeros):
    return {"veredicto": veredicto, "motivo": motivo, "accion": accion, "puerta": puerta, "numeros": numeros}


def decidir(snapshots, reglas, contexto):
    """`contexto["es_imagen"]`: la pieza es una imagen, ThruPlay no aplica."""
    r = dict(REGLAS_DEFECTO, **(reglas or {}))
    c = contexto or {}
    if not snapshots:
        return _resultado("pendiente", gettext("Todavía no hay métricas."), None, 0, {})
    u = snapshots[-1]
    numeros = {k: _f(u, k) for k in ("impresiones", "clics_enlace", "ctr", "cpc", "thruplay_rate", "gasto", "compras", "cpa", "roas")}
    numeros["impresiones"] = int(numeros["impresiones"]); numeros["compras"] = int(numeros["compras"])
    horas = float(c.get("horas_activo") or 0)
    presupuesto = float(c.get("presupuesto_dia") or 0)
    gasto_min = r["gasto_min_x_presupuesto"] * presupuesto if presupuesto else 0
    dias = float(c.get("dias_experimento") or 0)
    transcurridos = float(c.get("dias_transcurridos") or 0)

    # Evidencia mínima: impresiones + gasto, o bien la ventana de horas
    # cumplida. Con CERO impresiones nunca hay evidencia (I-8): un anuncio
    # que Meta no entregó (rechazado, en revisión, sin subasta) no es un
    # perdedor — sería rescatar (con crédito) algo que nadie vio.
    evidencia = ((numeros["impresiones"] >= r["impresiones_min"] and numeros["gasto"] >= gasto_min)
                 or (horas >= r["ventana_horas"] and numeros["impresiones"] > 0))
    if not evidencia:
        if dias and transcurridos >= dias:
            return _resultado("inconcluso", gettext(
                "Cerró la ventana de %(dias)s días sin evidencia suficiente (%(imp)s impresiones, gasto %(gasto)s).",
                dias=int(dias), imp=numeros["impresiones"], gasto=f"{numeros['gasto']:.2f}"), "pausar", 0, numeros)
        return _resultado("pendiente", gettext(
            "Sin evidencia todavía: %(imp)s impresiones (mínimo %(imp_min)s), gasto %(gasto)s (mínimo %(gasto_min)s), "
            "%(horas)s h de %(ventana)s.", imp=numeros["impresiones"], imp_min=r["impresiones_min"],
            gasto=f"{numeros['gasto']:.2f}", gasto_min=f"{gasto_min:.2f}", horas=f"{horas:.0f}", ventana=r["ventana_horas"]),
            None, 0, numeros)

    # Puerta 1: tráfico.
    fallas = []
    if r["cpc_max"] is not None and numeros["cpc"] > r["cpc_max"]:
        fallas.append(gettext("CPC %(cpc)s > %(cpc_max)s", cpc=f"{numeros['cpc']:.2f}", cpc_max=f"{r['cpc_max']:.2f}"))
    if r["ctr_min"] is not None and numeros["ctr"] < r["ctr_min"]:
        fallas.append(gettext("CTR %(ctr)s%% < %(ctr_min)s%%", ctr=f"{numeros['ctr']:.2f}", ctr_min=f"{r['ctr_min']:.2f}"))
    if r["thruplay_min"] is not None and not c.get("es_imagen") and numeros["thruplay_rate"] < r["thruplay_min"]:
        fallas.append(gettext("ThruPlay %(tp)s%% < %(tp_min)s%%",
                              tp=f"{numeros['thruplay_rate'] * 100:.0f}", tp_min=f"{r['thruplay_min'] * 100:.0f}"))
    escalon = int(c.get("escalon_rescate") or 0)
    if fallas:
        accion = "archivar" if escalon >= 3 else "rescatar"
        return _resultado("perdedor", gettext("No pasó la puerta de tráfico: %(fallas)s.", fallas="; ".join(fallas)),
                          accion, 1, numeros)

    # Puerta 2: ventas (solo con atribución y al menos un umbral de venta activo).
    con_atribucion = c.get("atribucion") in ("pixel", "tienda", "triple_whale")
    sin_umbrales_venta = r["roas_min"] is None and r["cpa_max"] is None
    if con_atribucion and not sin_umbrales_venta:
        if horas < r["ventana_ventas_horas"]:
            return _resultado("pendiente", gettext(
                "Pasó tráfico; esperando %(ventana)s h para medir ventas (%(horas)s h).",
                ventana=r["ventana_ventas_horas"], horas=f"{horas:.0f}"), None, 2, numeros)
        if int(c.get("compras_pais", numeros["compras"]) or 0) < 3:
            v = _resultado("inconcluso", gettext("Menos de 3 compras entre las piezas del país: ventas inconclusas."),
                           None, 2, numeros)
            v["muestra_ventas_insuficiente"] = True
            return v
        ok_roas = r["roas_min"] is not None and numeros["roas"] >= r["roas_min"]
        ok_cpa = r["cpa_max"] is not None and numeros["compras"] > 0 and numeros["cpa"] <= r["cpa_max"]
        if not (ok_roas or ok_cpa):
            accion = "archivar" if escalon >= 3 else "rescatar"
            cpa_max_txt = gettext(" (máximo %(cpa_max)s)", cpa_max=r["cpa_max"]) if r["cpa_max"] is not None else ""
            return _resultado("perdedor", gettext(
                "Pasó tráfico pero no ventas: ROAS %(roas)s (mínimo %(roas_min)s), CPA %(cpa)s%(cpa_max_txt)s.",
                roas=f"{numeros['roas']:.2f}", roas_min=r["roas_min"], cpa=f"{numeros['cpa']:.2f}",
                cpa_max_txt=cpa_max_txt), accion, 2, numeros)
        motivo_ventas = (gettext("ROAS %(roas)s ≥ %(roas_min)s", roas=f"{numeros['roas']:.2f}", roas_min=r["roas_min"])
                         if ok_roas else
                         gettext("CPA %(cpa)s ≤ %(cpa_max)s", cpa=f"{numeros['cpa']:.2f}", cpa_max=r["cpa_max"]))
        puerta = 2
    elif con_atribucion:
        motivo_ventas = gettext("sin umbrales de ventas")
        puerta = 1
    else:
        motivo_ventas = gettext("sin ventas medibles")
        puerta = 1

    # Ranking: tercio superior de su país cuando hay ≥ 3 anuncios.
    total = int(c.get("total_pais") or 1)
    pos = _int_or_none(c.get("posicion"))
    if total >= 3 and pos is not None and pos > max(1, total // 3):
        return _resultado("pendiente", gettext(
            "Pasa umbrales pero no está en el tercio superior de su país (posición %(pos)s de %(total)s).",
            pos=pos, total=total), None, puerta, numeros)
    thruplay_txt = ("" if c.get("es_imagen") else
                    gettext("ThruPlay %(tp)s%% — ", tp=f"{numeros['thruplay_rate'] * 100:.0f}"))
    return _resultado("ganador", gettext(
        "Ganador: CTR %(ctr)s%%, CPC %(cpc)s, %(thruplay_txt)s%(motivo_ventas)s.",
        ctr=f"{numeros['ctr']:.2f}", cpc=f"{numeros['cpc']:.2f}", thruplay_txt=thruplay_txt,
        motivo_ventas=motivo_ventas), "escalar_y_derivar", puerta, numeros)

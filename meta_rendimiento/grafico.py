"""El gráfico «Día a día» de la pestaña Meta: barras de gasto y línea de valor de compras sobre un solo eje.

Hasta el 2026-10-08 vivía en `dashboard._grafico_tablero` (`app.extensions["grafico_tablero"]`) y su serie en
`triple_whale.panel._serie_dias`; main los borró con «Resultados de tu tienda» (Triple Whale ya pinta su propia
gráfica y el Tablero no pinta ninguna) y la pestaña Meta era la única que los usaba, así que al mezclar main se
mudaron aquí sin cambiar el cálculo. Sus estilos (`.tb-grafico`, `.tb-barra`…) viven en
`static/estilos/pantallas/meta.css`."""
import math
from datetime import date, timedelta

from flask_babel import gettext

import idiomas
import tablero

# Geometría del gráfico (viewBox fija; el SVG escala al ancho).
ANCHO, ALTO = 720, 220
MARGEN = {"izq": 60, "der": 12, "arriba": 12, "abajo": 26}


def serie_dias(desde, hasta, filas, clave_gasto="gasto", clave_ingresos="ingresos", clave_pedidos="pedidos"):
    """Un punto por día del rango (los días sin fila en cero), con la forma que espera `armar`."""
    por_dia = {f["fecha"]: f for f in filas}
    d, fin, salida = date.fromisoformat(desde), date.fromisoformat(hasta), []
    while d <= fin:
        f = por_dia.get(d.isoformat()) or {}
        salida.append({"dia": d.isoformat(), "gasto": float(f.get(clave_gasto) or 0),
                       "ingresos": float(f.get(clave_ingresos) or 0), "compras": int(round(f.get(clave_pedidos) or 0))})
        d += timedelta(days=1)
    return salida


def _nice_max(valor):
    """Máximo «bonito» para el eje: el primer 1/2/2,5/5/10 × 10^n que cubre
    el valor, para que las 4 marcas queden en números redondos."""
    if valor <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(valor))
    for f in (1, 2, 2.5, 5, 10):
        if f * exp >= valor:
            return float(f * exp)
    return float(10 * exp)


def _compacto(valor):
    """Etiqueta corta para el eje: 1,2 M / 250 k / 12 en español; 1.2 M / 250 k /
    12 en inglés (idiomas.separador_decimal — el recorte de ceros es a medida,
    así que no usa `idiomas.numero` completo)."""
    v = float(valor or 0)
    if v >= 1_000_000:
        t = f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".") + " M"
    elif v >= 1_000:
        t = f"{v / 1_000:.1f}".rstrip("0").rstrip(".") + " k"
    elif v == int(v):
        t = str(int(v))
    else:
        t = f"{v:.2f}".rstrip("0").rstrip(".")   # 0,5 y 0,25, no 0,50
    return t.replace(".", idiomas.separador_decimal())


def armar(serie):
    """Coordenadas listas para pintar la serie como SVG inline:
    barras de gasto y línea de ingresos sobre UN solo eje (las dos son dinero
    en `serie.moneda`, así que comparten escala), 4 marcas + máximo redondeado,
    etiqueta de fecha cada 5 días y un `titulo` por día para el tooltip nativo.
    None si no hay días o todo es cero (la plantilla muestra el estado vacío
    en vez de un gráfico en blanco)."""
    dias = (serie or {}).get("dias") or []
    moneda = (serie or {}).get("moneda") or tablero.MONEDA_POR_DEFECTO
    if not dias:
        return None
    tope = max(max(float(d["gasto"] or 0), float(d["ingresos"] or 0)) for d in dias)
    if tope <= 0:
        return None
    maximo = _nice_max(tope)
    m = MARGEN
    ancho_plot = ANCHO - m["izq"] - m["der"]
    alto_plot = ALTO - m["arriba"] - m["abajo"]
    base_y = m["arriba"] + alto_plot
    paso = ancho_plot / len(dias)
    ancho_barra = max(2.0, paso - 2)   # 2px de aire entre barras

    def y_de(v):
        return round(base_y - (float(v or 0) / maximo) * alto_plot, 2)

    salida = []
    for i, d in enumerate(dias):
        dd, mm = d["dia"][8:10], d["dia"][5:7]
        fecha_dia = date(int(d["dia"][0:4]), int(mm), int(dd))
        x = m["izq"] + i * paso
        gasto, ingresos = float(d["gasto"] or 0), float(d["ingresos"] or 0)
        salida.append({
            "dia": d["dia"], "gasto": gasto, "ingresos": ingresos, "compras": int(d.get("compras") or 0),
            "x": round(x, 2), "x_centro": round(x + paso / 2, 2), "ancho": round(ancho_barra, 2),
            "gasto_y": y_de(gasto), "ingresos_y": y_de(ingresos),
            "etiqueta": idiomas.dia_mes(fecha_dia) if i % 5 == 0 else "",
            "titulo": gettext("%(dd)s/%(mm)s · gasto %(gasto)s · ingresos %(ingresos)s",
                              dd=dd, mm=mm, gasto=tablero.dinero(gasto, moneda),
                              ingresos=tablero.dinero(ingresos, moneda)),
        })
    marcas = [{"valor": maximo * k / 4, "y": y_de(maximo * k / 4), "texto": _compacto(maximo * k / 4)} for k in range(5)]
    puntos = " ".join(f"{d['x_centro']},{d['ingresos_y']}" for d in salida)
    return {"ancho": ANCHO, "alto": ALTO, "margen": m, "base_y": base_y, "maximo": maximo, "moneda": moneda,
            "marcas": marcas, "dias": salida, "puntos_linea": puntos}

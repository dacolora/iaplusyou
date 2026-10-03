"""Presupuestos planificados, sin acceso a Meta ni efectos secundarios."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP

PRESUPUESTO_MINIMO_DIARIO = {"USD": 1, "COP": 4000, "MXN": 20, "EUR": 1, "BRL": 5, "PEN": 4, "CLP": 1000, "ARS": 1000}
SIN_DECIMALES = {"JPY", "CLP", "HUF", "ISK", "KRW", "TWD", "VND", "PYG", "UGX", "XAF", "XOF"}


def numero(valor):
    try:
        n = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ValueError("numero") from None
    if not n.is_finite() or n <= 0 or n > Decimal('1e15'):
        raise ValueError("numero")
    return n


def unidad(moneda):
    return Decimal('1') if moneda in SIN_DECIMALES else Decimal('.01')


def repartir(total, dias, anuncios_por_pais, moneda):
    total, dias = numero(total), numero(dias)
    if dias != int(dias) or dias > 90 or not anuncios_por_pais:
        raise ValueError("dias/paises")
    pesos = {p: numero(n) for p, n in anuncios_por_pais.items()}
    if any(n != int(n) for n in pesos.values()):
        raise ValueError("anuncios")
    suma = sum(pesos.values())
    u = unidad(moneda)
    minimo = Decimal(str(PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)))
    diarios = {p: (total * n / suma / dias).quantize(u, rounding=ROUND_DOWN) for p, n in pesos.items()}
    minimo_total = max(minimo * suma * dias / n for n in pesos.values()).quantize(u, rounding=ROUND_UP)
    return {"presupuestos": {p: float(n) for p, n in diarios.items()},
            "bajos": [p for p, n in diarios.items() if n < minimo],
            "total_minimo": float(minimo_total), "total_repartido": float(sum(diarios.values()) * dias)}


def atajos(moneda, anuncios_por_pais):
    anuncios = sum(numero(n) for n in anuncios_por_pais.values())
    minimo = Decimal(str(PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)))
    opciones = []
    for factor, dias in ((4, 4), (8, 7), (15, 10)):
        total = numero(anuncios * minimo * factor * dias)
        paso = Decimal(10) ** (total.adjusted() - 1)
        total = (total / paso).to_integral_value(rounding=ROUND_UP) * paso
        opciones.append({"total": float(total), "dias": dias})
    return opciones


def validar(total, dias, presupuestos, moneda):
    total, dias = numero(total), numero(dias)
    if dias != int(dias) or dias > 90 or not presupuestos:
        raise ValueError("dias/paises")
    valores = [numero(n) for n in presupuestos]
    minimo = Decimal(str(PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)))
    if any(n < minimo or n != n.quantize(unidad(moneda)) for n in valores):
        raise ValueError("minimo/precision")
    if sum(valores) * dias > total:
        raise ValueError("total")

"""La unidad en que Meta recibe la plata de cada moneda (su «offset»): el ÚNICO lugar de esa tabla.

Meta recibe presupuestos y topes en la unidad mínima de la moneda de la CUENTA publicitaria: centavos en las monedas
con offset 100 (USD, EUR, MXN, SEK…) y la moneda entera en las de offset 1 (COP, CLP, JPY…). Fuente: la tabla oficial
https://developers.facebook.com/docs/marketing-api/currencies, consultada el 2026-10-13.

Por qué existe (PND-319, 2026-10-13): hasta ese día Creatv tenía una lista escrita de memoria, sin el peso colombiano,
y mandó los presupuestos en COP 100 veces más altos (4 000 COP al día salían como 400 000). `lanzador`, `tareas.meta`,
`presupuesto_experimentos` y `meta_rendimiento.sync` importan de aquí; `tests/test_monedas_meta.py` compara la tabla
con la de Meta y `static/presupuesto_exp.js` repite las monedas en enteros (una prueba exige que coincidan).
"""

# Offset 1: Meta las recibe en la moneda entera.
SIN_DECIMALES = frozenset({"CLP", "COP", "CRC", "HUF", "IDR", "ISK", "JPY", "KRW", "PYG", "TWD", "VND"})

# Offset 100: Meta las recibe en centavos. Son las demás de la tabla oficial.
CON_DECIMALES = frozenset({
    "AED", "ARS", "AUD", "BDT", "BGN", "BHD", "BOB", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "DZD", "EGP", "EUR",
    "FBZ", "GBP", "GTQ", "HKD", "HNL", "HRK", "ILS", "INR", "JOD", "KES", "LTL", "LVL", "MOP", "MXN", "MYR", "NGN",
    "NIO", "NOK", "NZD", "PEN", "PHP", "PKR", "PLN", "QAR", "RON", "RSD", "RUB", "SAR", "SEK", "SGD", "SKK", "THB",
    "TRY", "UAH", "USD", "UYU", "VEF", "VES", "ZAR",
})

SOPORTADAS = SIN_DECIMALES | CON_DECIMALES


class MonedaNoSoportada(ValueError):
    """Una moneda que no está en la tabla de Meta: no se le manda ningún monto (no se sabe en qué unidad va)."""


def factor(moneda):
    """Cuántas unidades de Meta tiene una unidad de la moneda: 1 (offset 1) o 100 (offset 100). Una moneda fuera de
    la tabla lanza `MonedaNoSoportada`: adivinar la unidad es justo el error que costó PND-319."""
    m = (moneda or "").strip().upper()
    if m in SIN_DECIMALES:
        return 1
    if m in CON_DECIMALES:
        return 100
    raise MonedaNoSoportada(m or "(sin moneda)")


def a_unidad_meta(monto, moneda):
    """El monto en la moneda (4 000 COP, 14,28 USD) como lo recibe Meta (4 000; 1 428)."""
    return int(round(float(monto) * factor(moneda)))


def desde_unidad_meta(valor, moneda):
    """Lo que Meta devuelve en su unidad (`daily_budget`, `spend_cap`) en la moneda."""
    return float(valor) / factor(moneda)

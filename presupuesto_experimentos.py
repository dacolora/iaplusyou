"""El presupuesto de un experimento nuevo («Nuevo experimento › Cuánto»), sin acceso a Meta ni efectos secundarios.

La persona elige UN total y los días; Creatv reparte: el diario de cada país es el total, por la parte de anuncios
que tiene ese país, entre los días, redondeado HACIA ABAJO a la unidad de la moneda. Por eso lo que se muestra como
«Máximo que puede gastar» nunca se queda corto: la suma de los diarios por los días es ≤ el total.

Spec 2026-10-02 (§5.1 a §5.3). Este módulo es el ÚNICO lugar de:
- `PRESUPUESTO_MINIMO_DIARIO` (el mínimo diario que Meta acepta por moneda; `dashboard.py` lo importa de aquí);
- la cuenta del reparto (`repartir`) y de los atajos (`atajos`);
- la validación del servidor (`validar`): la de `exp_probar`, que no se fía de lo que calculó el navegador.

`static/presupuesto_exp.js` replica `repartir` y `atajos` para pintar la pantalla al instante; `tests/
test_presupuesto_experimentos.py` corre ambos con los mismos casos y exige resultados idénticos.
"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP

# Mínimo diario que Meta acepta por divisa (aprox., para avisar antes de fallar). Se compara contra la moneda de
# FACTURACIÓN de la cuenta, no la del país del conjunto.
PRESUPUESTO_MINIMO_DIARIO = {"USD": 1, "COP": 4000, "MXN": 20, "EUR": 1, "BRL": 5, "PEN": 4, "CLP": 1000, "ARS": 1000}
# Monedas sin decimales para Meta: la misma lista que `tareas.meta.MONEDAS_SIN_DECIMALES` (lo que `lanzador.centavos` manda
# sin multiplicar por 100); una prueba compara las dos.
SIN_DECIMALES = {"JPY", "CLP", "HUF", "ISK", "KRW", "TWD", "VND", "PYG", "UGX", "XAF", "XOF"}
# Monedas en las que el presupuesto se reparte en PESOS ENTEROS: las sin decimales y las de valor tan chico que un
# centavo no dice nada (COP y ARS, cuyo mínimo diario ya es de miles). Un peso entero siempre es válido para Meta
# (`centavos` lo multiplica por 100), así «21.428 COP al día» no sale como «21.428,57». Las demás llevan centavos.
EN_ENTEROS = SIN_DECIMALES | {"COP", "ARS"}
# Los atajos «Prueba rápida · Estándar · Fuerte» (spec §5.2): (veces el mínimo diario por anuncio, días). Son una
# SUGERENCIA, no el precio de un proveedor: el precio es la cifra que la persona elige.
ATAJOS = ((4, 4), (8, 7), (15, 10))
# Margen que se tolera de más en el servidor por redondeo (spec §5.3): el navegador siempre manda suma × días ≤ total.
MARGEN_TOTAL = Decimal("1.01")
MAX_DIAS = 90


class ErrorPresupuesto(ValueError):
    """Un presupuesto que el servidor no acepta. `codigo` dice por qué: numero, dias, paises, anuncios, minimo,
    precision o total (el reparto supera el total)."""

    def __init__(self, codigo):
        super().__init__(codigo)
        self.codigo = codigo


def numero(valor, codigo="numero"):
    try:
        n = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorPresupuesto(codigo) from None
    if not n.is_finite() or n <= 0 or n > Decimal("1e15"):
        raise ErrorPresupuesto(codigo)
    return n


def unidad(moneda):
    """El paso más chico con que se reparte en esa moneda: 1 peso si va en enteros, 0,01 si lleva centavos."""
    return Decimal("1") if moneda in EN_ENTEROS else Decimal(".01")


def minimo_diario(moneda):
    return Decimal(str(PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)))


def _dias(dias):
    d = numero(dias, "dias")
    if d != int(d) or d > MAX_DIAS:
        raise ErrorPresupuesto("dias")
    return d


def repartir(total, dias, anuncios_por_pais, moneda):
    """Reparte `total` en `dias` días entre los países según sus anuncios (`{pais: n_anuncios}`).

    Devuelve `presupuestos` (diario de cada país, redondeado hacia abajo), `bajos` (los países que quedan bajo el
    mínimo diario de Meta), `total_minimo` (el total más chico, a la unidad de la moneda, con el que ninguno queda
    bajo el mínimo) y `total_repartido` (suma de los diarios × días, que nunca pasa del total)."""
    total, dias = numero(total), _dias(dias)
    if not anuncios_por_pais:
        raise ErrorPresupuesto("paises")
    pesos = {p: numero(n, "anuncios") for p, n in anuncios_por_pais.items()}
    if any(n != int(n) for n in pesos.values()):
        raise ErrorPresupuesto("anuncios")
    suma = sum(pesos.values())
    u, minimo = unidad(moneda), minimo_diario(moneda)
    diarios = {p: (total * n / (suma * dias)).quantize(u, rounding=ROUND_DOWN) for p, n in pesos.items()}
    minimo_total = max(minimo * suma * dias / n for n in pesos.values()).quantize(u, rounding=ROUND_UP)
    return {"presupuestos": {p: float(n) for p, n in diarios.items()},
            "bajos": [p for p, n in diarios.items() if n < minimo],
            "total_minimo": float(minimo_total), "total_repartido": float(sum(diarios.values()) * dias)}


def atajos(moneda, anuncios_por_pais):
    """Las tres sugerencias (`[{total, dias}]`: rápida, estándar, fuerte): diario por anuncio = 4× / 8× / 15× el
    mínimo diario de Meta durante 4 / 7 / 10 días, con el total subido a 2 cifras significativas (así ningún país
    queda bajo el mínimo por redondear hacia abajo)."""
    anuncios = sum(numero(n, "anuncios") for n in anuncios_por_pais.values())
    minimo = minimo_diario(moneda)
    opciones = []
    for factor, dias in ATAJOS:
        total = anuncios * minimo * factor * dias
        paso = Decimal(10) ** (total.adjusted() - 1)
        opciones.append({"total": float((total / paso).to_integral_value(rounding=ROUND_UP) * paso), "dias": dias})
    return opciones


def validar(total, dias, presupuestos, moneda):
    """La comprobación del servidor para `exp_probar`: no se fía del navegador. `presupuestos` es el diario de cada
    país tal como llegó en el formulario. Levanta `ErrorPresupuesto` si algún diario queda bajo el mínimo de Meta,
    lleva más decimales que la moneda, o si la suma de los diarios por los días supera el total (con 1 % de margen
    por redondeo): así «Máximo que puede gastar» es verdad aunque alguien arme el POST a mano."""
    total, dias = numero(total), _dias(dias)
    if not presupuestos:
        raise ErrorPresupuesto("paises")
    valores = [numero(n) for n in presupuestos]
    if any(n < minimo_diario(moneda) for n in valores):
        raise ErrorPresupuesto("minimo")
    if any(n != n.quantize(unidad(moneda)) for n in valores):
        raise ErrorPresupuesto("precision")
    if sum(valores) * dias > total * MARGEN_TOTAL:
        raise ErrorPresupuesto("total")

"""Anota en un ajuste de deuda qué gastos paga, para que el cliente los vea uno por uno en Configuración › Gasto.

Cuando un proyecto pasa a cobrar con lo usado antes como deuda (pospago de happyflops, 2026-10-12: el ajuste
−US$ 948,63 por 1 164 gastos × 3), su gasto solo enseñaba lo de después. Esto llama a
`cobros.libro.detallar_uso_previo`, que comprueba que costo × margen dé el ajuste al centavo y anota el rango
de gastos y el margen en el `extra` del ajuste. No mueve plata: el saldo y la deuda quedan iguales.

    ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && TZ=America/Bogota venv/bin/python3 deploy/detallar_uso_previo.py happyflops 3 3'

Argumentos: proyecto, id del movimiento de ajuste y margen. Se puede repetir: con el mismo margen no cambia nada.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    from cobros import libro  # noqa: PLC0415 — después de arreglar sys.path
    cliente, movimiento_id, margen = argv[0], int(argv[1]), float(argv[2])
    try:
        uso = libro.detallar_uso_previo(cliente, movimiento_id, margen)
    except ValueError as e:
        print(f"No se anotó nada: {e}")
        return 1
    print(f"Ajuste {movimiento_id} de {cliente}: {uso['n']} gastos (ids {uso['desde_gasto'] + 1} a "
          f"{uso['hasta_gasto']}), costo US$ {uso['costo']:.4f} × {uso['margen']:g} = "
          f"US$ {uso['costo'] * uso['margen']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

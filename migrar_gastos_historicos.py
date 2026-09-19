"""
Relleno único de la tabla `gasto` (nació el 2026-09-18) con lo que ya se había
pagado antes de que existiera: el `costo_usd` de cada pieza cobrada y el `usd`
de cada swap listo de clientes/<c>/swaps.json. Sin esto el panel de admin y el
tile "Generación este mes" del Tablero mostraban US$ 0 en todos los proyectos.

Idempotente: se puede correr las veces que haga falta; lo que ya está en la
tabla (importado antes, o registrado por su propia tarea después del
despliegue) se salta. La lógica vive en gastos.importar_historico.

Uso:
    venv/bin/python3 migrar_gastos_historicos.py             # todos los proyectos
    venv/bin/python3 migrar_gastos_historicos.py happyflops  # uno solo
"""
import sys

import estado as estado_mod
import gastos


def migrar_todos(clientes=None):
    salida = {}
    for cliente in (clientes or estado_mod.listar_clientes()):
        salida[cliente] = gastos.importar_historico(cliente)
    return salida


if __name__ == "__main__":
    for cliente, r in migrar_todos(sys.argv[1:] or None).items():
        print(f"{cliente}: {r['piezas']} piezas + {r['swaps']} swaps -> US$ {r['usd']:.2f} importados")

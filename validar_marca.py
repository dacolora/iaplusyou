"""
Valida un archivo de "submundo" (temporada, colección o proyecto) de un cliente
contra su propio submundo.schema.json — la misma regla que el sistema de marca
diseñó ("un submundo nunca puede pisar un invariante") pero verificada por
código de forma mecánica, en vez de depender de que un chat de Claude lo revise
bien cada vez.

Uso:
    python validar_marca.py --cliente happyflops archivo.json
    python validar_marca.py --cliente happyflops --todos   # toda la carpeta submundos/
"""
import argparse
import json
import os
import sys

import jsonschema

BASE_DIR = os.path.dirname(__file__)


def _cargar_schema(cliente):
    path = os.path.join(BASE_DIR, "clientes", cliente, "marca", "schema.json")
    if not os.path.exists(path):
        raise RuntimeError(f"No encontré {path} — este cliente no tiene un submundo.schema.json.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validar_archivo(path_submundo, cliente):
    schema = _cargar_schema(cliente)
    with open(path_submundo, "r", encoding="utf-8") as f:
        submundo = json.load(f)

    validador = jsonschema.Draft202012Validator(schema)
    errores = sorted(validador.iter_errors(submundo), key=lambda e: list(e.path))

    if not errores:
        print(f"✅ {path_submundo} — válido, no rompe el schema ni ningún invariante.")
        return True

    print(f"❌ {path_submundo} — {len(errores)} problema(s):")
    for e in errores:
        ruta = ".".join(str(p) for p in e.path) or "(raíz)"
        print(f"   - en '{ruta}': {e.message}")
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archivos", nargs="*", help="Archivos JSON de submundo a validar")
    parser.add_argument("--cliente", required=True, help="Cliente cuyo schema.json usar (ej. happyflops)")
    parser.add_argument(
        "--todos", action="store_true",
        help="Valida todos los .json en clientes/<cliente>/marca/submundos/",
    )
    args = parser.parse_args()

    archivos = list(args.archivos)
    if args.todos:
        carpeta = os.path.join(BASE_DIR, "clientes", args.cliente, "marca", "submundos")
        if os.path.isdir(carpeta):
            archivos += [
                os.path.join(carpeta, f) for f in sorted(os.listdir(carpeta)) if f.endswith(".json")
            ]

    if not archivos:
        print("No pasaste ningún archivo. Usa --todos o dame rutas específicas.")
        sys.exit(1)

    resultados = [validar_archivo(a, args.cliente) for a in archivos]
    print(f"\n{sum(resultados)}/{len(resultados)} válidos.")
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()

"""Suma la tabla `gasto` por proveedor (la empresa que factura) y por mes, para compararla con las facturas.

Solo lee: no escribe nada en la base. Lo pidió la auditoría de cobros (PND-013, decisión 2026-10-13, lote 1):
lo anotado tiene que cuadrar con las facturas del mes de fal, WaveSpeed, Anthropic, Apify y Google.

    ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && venv/bin/python3 deploy/conciliar_gastos.py'
    venv/bin/python3 deploy/conciliar_gastos.py --desde 2026-09 --hasta 2026-10 --proyecto happyflops --csv

Cómo se reparte:
- Cada fila va a la empresa de su `proveedor` (`EMPRESAS`); un swap anota el modelo (`seedance25_edit`, `kling_o1`…)
  y se resuelve con `MODELOS`. Lo que no se reconoce sale con su nombre tal cual, para que nada se esconda.
- Una final (`fal/anthropic`) se parte por capas (`extra.capas`): `guion` es de Anthropic y lo demás de fal; lo que
  no cae en una capa (lo que una final se llevó de un intento fallido, PND-314) va a «fal/anthropic».
- Incluye `_creatv` (lo que paga Creatv también está en la factura). Las filas con `extra.estimado` o
  `conciliacion_pendiente` se cuentan aparte en «estimadas»: su monto es un estimado, no lo facturado.
- El mes es el de `creado_en` (la hora del servidor).
- Atria y TrendTrack no están en `gasto` (PND-335, decisión 2026-10-15, lote 3): son cupos de un plan de Creatv para la
  biblioteca global de referentes (y TrendTrack, además, recargas de créditos), no trabajo de un proyecto, y no se
  prorratean a los barridos. El informe los lista aparte como suscripciones fijas (`SUSCRIPCIONES_FIJAS`) para que su
  factura no se lea como un faltante.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EMPRESAS = {
    "anthropic": "anthropic",
    "wavespeed": "wavespeed",
    "fal": "fal", "fal/elevenlabs": "fal", "fal/minimax": "fal", "fal/whisper": "fal",
    "apify": "apify",
    "google": "google", "nano_banana": "google",
    "higgsfield": "higgsfield",
    "atria": "atria", "trendtrack": "trendtrack",
}
# Los swaps anotan el modelo como proveedor (tareas/swap._registrar_gasto).
MODELOS = {
    "wan27_edit": "wavespeed", "seedance25_edit": "wavespeed", "kling_o3_pro_edit": "wavespeed",
    "luma_ray32_edit": "wavespeed", "nano_banana_pro_ultra": "wavespeed", "seedream_v5_pro": "wavespeed",
    "kling_o1": "fal", "nano_banana_fal": "fal", "qwen_edit": "fal", "luma_modify": "fal",
    "wan_animate_replace": "fal", "flux_kontext": "fal", "gemini_omni_edit": "fal",
}
CAPAS_ANTHROPIC = ("guion",)
# PND-335: fuera de la tabla `gasto` a propósito (ver el docstring). Se comparan con su factura aparte.
SUSCRIPCIONES_FIJAS = (
    ("atria", "plan mensual de Atria (cupo de búsquedas de la biblioteca de referentes)"),
    ("trendtrack", "plan mensual de TrendTrack y sus recargas de créditos"),
)


def empresa(proveedor):
    p = (proveedor or "").strip().lower()
    if not p:
        return "sin proveedor"
    return EMPRESAS.get(p) or MODELOS.get(p) or p


def _partes(fila):
    """[(empresa, usd)] de una fila. Una final se parte por capas."""
    usd = float(fila["usd"] or 0)
    proveedor = (fila["proveedor"] or "").strip().lower()
    capas = (fila["extra"] or {}).get("capas") if proveedor == "fal/anthropic" else None
    if not isinstance(capas, dict):
        return [(empresa(proveedor), usd)]
    partes = defaultdict(float)
    for nombre, valor in capas.items():
        partes["anthropic" if nombre in CAPAS_ANTHROPIC else "fal"] += float(valor or 0)
    resto = round(usd - sum(partes.values()), 4)
    if resto > 0:
        partes["fal/anthropic"] += resto
    return list(partes.items())


def resumen(desde=None, hasta=None, proyecto=None):
    """{(mes, empresa): {"usd", "filas", "estimadas", "usd_estimado"}}. Solo lee."""
    import sqlalchemy as sa  # noqa: PLC0415 — después de arreglar sys.path
    import db  # noqa: PLC0415
    g = db.gasto
    q = sa.select(g.c.creado_en, g.c.proveedor, g.c.usd, g.c.extra)
    if proyecto:
        q = q.where(g.c.cliente == proyecto)
    if desde:
        q = q.where(g.c.creado_en >= f"{desde}-01")
    if hasta:
        q = q.where(g.c.creado_en < _mes_siguiente(hasta) + "-01")
    salida = defaultdict(lambda: {"usd": 0.0, "filas": 0, "estimadas": 0, "usd_estimado": 0.0})
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    for f in filas:
        mes = (f["creado_en"] or "")[:7]
        extra = f["extra"] or {}
        estimada = bool(extra.get("estimado") or extra.get("conciliacion_pendiente"))
        for emp, usd in _partes(f):
            s = salida[(mes, emp)]
            s["usd"] += usd
            s["filas"] += 1
            if estimada:
                s["estimadas"] += 1
                s["usd_estimado"] += usd
    return {k: {**v, "usd": round(v["usd"], 4), "usd_estimado": round(v["usd_estimado"], 4)}
            for k, v in sorted(salida.items())}


def _mes_siguiente(mes):
    anio, m = (int(x) for x in mes.split("-"))
    return f"{anio + (m == 12):04d}-{(m % 12) + 1:02d}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Suma la tabla gasto por proveedor y mes (solo lee).")
    ap.add_argument("--desde", help="AAAA-MM, incluido")
    ap.add_argument("--hasta", help="AAAA-MM, incluido")
    ap.add_argument("--proyecto", help="solo este proyecto (por defecto, todos, _creatv incluido)")
    ap.add_argument("--csv", action="store_true", help="salida en CSV (; como separador)")
    a = ap.parse_args(argv)
    datos = resumen(a.desde, a.hasta, a.proyecto)
    if a.csv:
        w = csv.writer(sys.stdout, delimiter=";")
        w.writerow(["mes", "proveedor", "usd", "filas", "estimadas", "usd_estimado"])
        for (mes, emp), v in datos.items():
            w.writerow([mes, emp, f"{v['usd']:.4f}", v["filas"], v["estimadas"], f"{v['usd_estimado']:.4f}"])
        for nombre, _ in SUSCRIPCIONES_FIJAS:
            w.writerow(["suscripcion_fija", nombre, "", "", "", ""])
        return 0
    totales = defaultdict(float)
    mes_actual = None
    for (mes, emp), v in datos.items():
        if mes != mes_actual:
            print(f"\n{mes}")
            mes_actual = mes
        nota = f"  ({v['estimadas']} estimadas: US$ {v['usd_estimado']:.2f})" if v["estimadas"] else ""
        print(f"  {emp:<16} US$ {v['usd']:>10.2f}  {v['filas']:>6} filas{nota}")
        totales[emp] += v["usd"]
    if totales:
        print("\nTotal")
        for emp, usd in sorted(totales.items()):
            print(f"  {emp:<16} US$ {usd:>10.2f}")
    else:
        print("Sin gastos en ese rango.")
    print("\nSuscripciones fijas (no están en la tabla gasto: su factura se revisa aparte, no es un faltante)")
    for nombre, que in SUSCRIPCIONES_FIJAS:
        print(f"  {nombre:<16} {que}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Informe de operación y de desarrollo, para sustentar una cuenta de cobro.

Todo lo que sale de acá tiene que ser VERIFICABLE contra una fuente real —
la bitácora (CSV append-only), el estado en disco, o el historial de git. Si un
dato no se puede probar, no se muestra o se muestra marcado como desconocido.
Nada de estimaciones presentadas como hechos: este informe se le enseña a un
cliente que está pagando.

Dos secciones, que responden a dos preguntas distintas:
  - OPERACIÓN: qué se generó y cuánto costó en APIs.
  - DESARROLLO: qué se construyó y cuánto tiempo tomó.
"""
import collections
import os
import subprocess
from datetime import datetime

import bitacora
import creative_flow
import swaps as swaps_mod

BASE_DIR = os.path.dirname(__file__)

# Estados de swap que representan una generación que el proveedor SÍ facturó.
# "error" no entra: la mayoría de los fallos registrados son 400 o falta de
# créditos, donde el modelo ni corrió.
ESTADOS_FACTURADOS = ("listo",)


def _git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def horas_de_desarrollo():
    """Horas medidas entre el primer y el último commit de cada día.

    Es deliberadamente un PISO, no una estimación optimista: no cuenta el
    trabajo anterior al primer commit del día, ni las sesiones que terminaron
    sin commit, ni los días de un solo commit (que quedan en 0). Se prefiere un
    número defendible a uno favorable."""
    salida = _git("log", "--format=%aI")
    if not salida:
        return {"horas": 0.0, "dias": 0, "detalle": []}

    por_dia = collections.defaultdict(list)
    for linea in salida.splitlines():
        try:
            dt = datetime.fromisoformat(linea.strip())
        except ValueError:
            continue
        por_dia[dt.date()].append(dt)

    detalle, total = [], 0.0
    for dia in sorted(por_dia):
        ts = sorted(por_dia[dia])
        horas = (ts[-1] - ts[0]).total_seconds() / 3600
        total += horas
        detalle.append({
            "fecha": dia.isoformat(),
            "commits": len(ts),
            "desde": ts[0].strftime("%H:%M"),
            "hasta": ts[-1].strftime("%H:%M"),
            "horas": round(horas, 1),
        })
    return {"horas": round(total, 1), "dias": len(detalle), "detalle": detalle}


def _contar_lineas(patrones):
    archivos = _git("ls-files", *patrones).splitlines()
    total = 0
    for rel in archivos:
        ruta = os.path.join(BASE_DIR, rel)
        try:
            with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                total += sum(1 for _ in f)
        except OSError:
            continue
    return len(archivos), total


def desarrollo():
    commits = _git("rev-list", "--count", "HEAD")
    fechas = _git("log", "--format=%ad", "--date=short").splitlines()
    archivos, lineas = _contar_lineas(["*.py", "*.html", "*.css"])
    proveedores = sorted(
        f[:-3] for f in os.listdir(os.path.join(BASE_DIR, "providers"))
        if f.endswith(".py") and f not in ("__init__.py", "aspect_ratio.py", "wavespeed_common.py")
    )
    uploaders_dir = os.path.join(BASE_DIR, "uploaders")
    plataformas = sorted(
        f.replace("_uploader.py", "") for f in os.listdir(uploaders_dir)
        if f.endswith("_uploader.py")
    ) if os.path.isdir(uploaders_dir) else []

    return {
        "commits": int(commits) if commits.isdigit() else 0,
        "desde": fechas[-1] if fechas else None,
        "hasta": fechas[0] if fechas else None,
        "archivos": archivos,
        "lineas": lineas,
        "proveedores": proveedores,
        "plataformas": plataformas,
        "tiempo": horas_de_desarrollo(),
    }


def operacion(cliente=None):
    """Generaciones ejecutadas y gasto real en APIs, leídos del estado en disco
    y de la bitácora. El gasto solo suma lo que quedó REGISTRADO: si un costo no
    se guardó, no se inventa."""
    clientes_dir = os.path.join(BASE_DIR, "clientes")
    clientes = [cliente] if cliente else sorted(
        c for c in os.listdir(clientes_dir) if os.path.isdir(os.path.join(clientes_dir, c))
    ) if os.path.isdir(clientes_dir) else []

    por_modelo = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    por_producto = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    total_usd = 0.0
    facturadas = fallidas = sin_costo = 0

    videos_cf = 0
    for cli in clientes:
        # Videos de CreativeFlowPlus: viven en otro archivo de estado, pero son
        # gasto real igual que los swaps y tienen que entrar al total.
        for entry in creative_flow.cargar(cli).values():
            usd = entry.get("usd") or 0.0
            if entry.get("estado") == "video_listo":
                videos_cf += 1
                facturadas += 1
                total_usd += usd
                if not usd:
                    sin_costo += 1
                por_modelo["wan3 (CreativeFlowPlus)"]["n"] += 1
                por_modelo["wan3 (CreativeFlowPlus)"]["usd"] += usd

        for entry in swaps_mod.cargar(cli).values():
            estado = entry.get("estado")
            usd = entry.get("usd") or 0.0
            if estado in ESTADOS_FACTURADOS:
                facturadas += 1
                total_usd += usd
                if not usd:
                    sin_costo += 1
                modelo = entry.get("proveedor") or "desconocido"
                por_modelo[modelo]["n"] += 1
                por_modelo[modelo]["usd"] += usd
                prod = entry.get("producto_id") or "desconocido"
                por_producto[prod]["n"] += 1
                por_producto[prod]["usd"] += usd
            elif estado == "error":
                fallidas += 1

    # La bitácora es append-only: conserva eventos de generaciones que después
    # se borraron desde la UI. Por eso su conteo puede ser MAYOR que el del
    # estado en disco, y esa diferencia se muestra explícitamente.
    eventos = bitacora.leer(limit=100000)
    if cliente:
        eventos = [e for e in eventos if e.get("cliente") == cliente]
    por_evento = collections.Counter((e.get("etapa"), e.get("estado")) for e in eventos)
    exitosos_bitacora = sum(n for (etapa, est), n in por_evento.items() if est == "ok")

    return {
        "total_usd": round(total_usd, 3),
        "videos_creative_flow": videos_cf,
        "facturadas": facturadas,
        "fallidas": fallidas,
        "sin_costo_registrado": sin_costo,
        "por_modelo": dict(sorted(por_modelo.items(), key=lambda kv: -kv[1]["usd"])),
        "por_producto": dict(sorted(por_producto.items(), key=lambda kv: -kv[1]["usd"])),
        "eventos_bitacora": len(eventos),
        "exitosos_bitacora": exitosos_bitacora,
        "primer_evento": eventos[-1].get("fecha", "")[:10] if eventos else None,
        "ultimo_evento": eventos[0].get("fecha", "")[:10] if eventos else None,
        # Generaciones que la bitácora vio terminar bien pero que ya no están en
        # el estado (se borraron desde la UI). Costaron dinero igual.
        "borradas_pero_registradas": max(0, por_evento.get(("swap", "ok"), 0) - facturadas),
    }


def completo(cliente=None):
    return {"operacion": operacion(cliente), "desarrollo": desarrollo()}

"""
Entrega del sprint (spec §2.6): enlaces de las piezas aprobadas y un zip con
todas, subido a R2 y guardado en `sprint.extra["zip"]`.
"""
import os
import re
import zipfile
from datetime import datetime

import requests

from sprints import datos
from storage import r2_uploader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def enlaces(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    salida = []
    for c in sp["campanas"]:
        for p in c["piezas"]:
            if p.get("revision") == "aprobada" and p.get("url_video"):
                salida.append({"cp_id": p["id"], "campana_n": int(c["orden"]) + 1, "persona": c["persona_nombre"],
                               "producto": c["catalogo_id"], "temporada": c["temporada_nombre"], "titulo": p.get("titulo") or "",
                               "tipo": p.get("tipo"), "url": p["url_video"]})
    return salida


def _slug(texto):
    s = re.sub(r"[^A-Za-z0-9]+", "-", (texto or "").strip()).strip("-")
    return s[:40] or "pieza"


def nombre_archivo(enlace, ext):
    return f"campana{enlace['campana_n']}_{enlace['tipo']}_{_slug(enlace['titulo'])}{ext}"


def _descargar(url):
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    return resp.content


def empaquetar(cliente, sprint_id, descargar=None):
    """Baja las aprobadas, arma el zip, lo sube a R2 y guarda el enlace."""
    descargar = descargar or _descargar
    lista = enlaces(cliente, sprint_id)
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, "sprints")
    os.makedirs(carpeta, exist_ok=True)
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M")
    nombre = f"sprint_{sprint_id}_{marca_tiempo}.zip"
    ruta = os.path.join(carpeta, nombre)
    usados = set()
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for e in lista:
            ext = ".mp4" if e["tipo"] == "video" else os.path.splitext(e["url"].split("?")[0])[1] or ".png"
            archivo = nombre_archivo(e, ext)
            if archivo in usados:
                archivo = f"{os.path.splitext(archivo)[0]}_{e['cp_id']}{ext}"
            usados.add(archivo)
            z.writestr(archivo, descargar(e["url"]))
    url = r2_uploader.upload_file(ruta, f"clientes/{cliente}/sprints/{nombre}", "application/zip")
    info = {"url": url, "n": len(lista), "creado_en": datetime.now().isoformat(timespec="seconds")}
    extra = datos.actualizar_extra_sprint(cliente, sprint_id, lambda e: {**e, "zip": info})
    if extra is None:
        raise datos.ErrorDatos("Ese sprint no existe.")
    datos.registrar_evento(cliente, sprint_id, "zip_listo", f"Zip de entrega con {len(lista)} pieza(s)", info)
    return info

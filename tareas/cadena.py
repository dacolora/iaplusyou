"""
Worker de la cadena de escenas de Flow Plus (spec 2026-09-30, «Generar todas
las escenas»). Cada escena es una pieza de Crear lanzada por la cola de siempre
(`flowplus_lanzar.lanzar`, prioridad de lote): hereda la recuperación de
WaveSpeed, el gasto real, el aviso de saldo y la tarjeta en Crear.

- `cadena_elementos` (paga centavos, max_intentos=1): crea los elementos de
  Kling que falten (caché en `kv`, gasto tipo `video`) y lanza la primera escena.
- `cadena_vigilar` (periódica, cada 60 s, gratis): por cada cadena viva mira la
  escena en curso; lista → saca su último fotograma, lo sube a R2 y lanza la
  siguiente; falló → detiene la cadena. Al terminar encola `cadena_unir`.
- `cadena_unir` (gratis): una edición del editor con todas las escenas.

Nada de esto decide gastar: la aprobación (con el precio visto) la hace la ruta
y cada escena se cobra en el cierre de Crear.
"""
import hashlib
import logging
import os
from contextlib import nullcontext

import sqlalchemy as sa
from flask_babel import gettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import creative_flow
import db
import flowplus_lanzar
import gastos
import idiomas
import trabajos
from final_edition import cortes, edicion_clon, insumos
from guiones import cadena, datos, escenas, medios
from guiones.refinador import ErrorRefinador
from providers import flowplus_modelos
from storage import r2_uploader
from tareas import registrar

log = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Como los lotes de Sprints (`sprints.produccion.PRIORIDAD_LOTE`): una pieza
# suelta de Crear (5) siempre pasa adelante.
PRIORIDAD_CADENA = 3
# Estados de una sesión de Crear que todavía pueden terminar en un video.
VIVOS_CREAR = ("prompt_pendiente", "prompt_listo", "video_generando")


def job_id(cliente, video_id, que):
    return f"{cliente}__cadena_{video_id}__{que}"


def _idioma(cliente):
    return idiomas.en_idioma(idiomas.de_proyecto(cliente)) if cliente else nullcontext()


# --------------------------------------------------------------------- kv ---

def _kv_leer(clave):
    with db.conectar() as con:
        return con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave)).scalar()


def _kv_guardar(clave, valor):
    with db.conectar() as con:
        con.execute(insert_sqlite(db.kv).values(clave=clave, valor=valor, actualizado_en=db.ahora())
                    .on_conflict_do_update(index_elements=["clave"],
                                           set_={"valor": valor, "actualizado_en": db.ahora()}))


def _sha(texto):
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- escenas ---

def _prompt_vigente(video_id, k):
    for p in datos.prompts_de_video(video_id):
        ex = p.get("extra") or {}
        if p["tipo"] == "clip" and ex.get("variante") == "principal" and ex.get("clip_index") == k:
            return p["texto_vigente"]
    raise ValueError(gettext("Esta escena todavía no tiene su prompt en el chat."))


def lanzar_escena(cliente, video_id, k):
    """Crea la sesión de Crear de la escena k y la manda a la cola. Devuelve su
    cf_id. La escena 1 lleva sus imágenes como referencias; las siguientes, el
    último cuadro de la anterior como imagen de arranque y sus elementos."""
    v = datos.video(cliente, video_id)
    est = cadena.estado(v)
    clip = next(c for c in v["clips"] if c["indice"] == k)
    imagenes = escenas.imagenes_para_crear(v, k)
    prompt = cadena.prompt_escena(_prompt_vigente(video_id, k), v, k, imagenes)
    primera = k == cadena.indices(v)[0]
    if primera:
        urls = [medios.url_publica(cliente, x["imagen"]) for x in imagenes]
        referencias = [{"tipo": "imagen", "url": u, "frame_url": u, "etiqueta": f"@Imagen {i}",
                        "titulo": f"Image {x['numero']}" + (f" · {x['nombre']}" if x["nombre"] else "")}
                       for i, (x, u) in enumerate(zip(imagenes, urls), start=1)]
        campos = {"referencias": referencias}
    else:
        frame = cadena.frame_anterior(est, k)
        if not frame:
            raise ValueError(gettext("Falta el último cuadro de la escena anterior."))
        elementos = [est["elementos"][cadena.id_imagen(x["imagen"])] for x in imagenes
                     if x["tipo"] in cadena.TIPOS_ELEMENTO]
        urls = []
        campos = {"imagen_inicial": frame, "elementos": elementos,
                  "referencias": [{"tipo": "imagen", "url": frame, "frame_url": frame, "etiqueta": "@Imagen 1",
                                   "titulo": f"{k - 1} → {k}"}]}
    duracion = flowplus_modelos.ajustar_duracion(cadena.MODELO, clip["duracion"])
    total = len(v["clips"])
    accion = f"{(v['guion'].get('titulo') or '')[:60]} · {k}/{total} · {clip.get('titulo') or ''}".strip(" ·")
    cf_id = creative_flow.crear(cliente, [], [], [], accion, duracion, "", "A", referencias_urls=urls, platforms=[])
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt, prompt_fuente=prompt, tipo="video",
                             modelo=cadena.MODELO, aspect_ratio=v["config"].get("formato") or "9:16", con_sonido=True,
                             sonido_texto="", musica_estilo="", calidad="final",
                             cadena={"guion_video_id": video_id, "indice": k}, **campos)
    datos.modificar_cadena(cliente, video_id, lambda e, _v: cadena.lanzada(e, k, cf_id))
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_CADENA):
        raise RuntimeError(gettext("No se pudo poner la escena en la cola."))
    return cf_id


def _fallar(cliente, video_id, k, error):
    try:
        datos.modificar_cadena(cliente, video_id, lambda e, _v: cadena.fallo(e, k, error) if e else e)
    except ErrorRefinador:
        log.exception("cadena: no se pudo marcar el fallo de la escena %s del video %s", k, video_id)


def _fotograma(cliente, video_id, k, entry):
    """Último cuadro del video crudo de la escena, subido a R2."""
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, "cadena")
    os.makedirs(carpeta, exist_ok=True)
    local = entry.get("video_local_crudo") or entry.get("video_local")
    if not (local and os.path.isfile(local)):
        local = insumos._descargar(entry.get("video_url_crudo") or entry.get("video_url"),
                                   os.path.join(carpeta, f"{video_id}_{k}.mp4"))
    jpg = cortes.ultimo_fotograma(local, os.path.join(carpeta, f"{video_id}_{k}.jpg"))
    return r2_uploader.upload_image(jpg, f"clientes/{cliente}/flowplus/cadena/{video_id}_{k}.jpg")


def vigilar_una(cliente, video_id):
    """Un paso de la cadena: cierra la escena en curso si terminó y lanza la
    que sigue (o termina). Seguro de llamar de más: sin cambios no hace nada."""
    v = datos.video(cliente, video_id)
    est = cadena.estado(v) if v else None
    if not est or est["estado"] != "corriendo":
        return
    with _idioma(cliente):
        actual = cadena.generando(est)
        if actual:
            k, cf_id = actual
            entry = creative_flow.cargar(cliente).get(cf_id)
            if entry is None:
                _fallar(cliente, video_id, k, gettext("La pieza de esta escena ya no está en Crear."))
                return
            if entry.get("estado") in VIVOS_CREAR:
                return
            if entry.get("estado") != "video_listo":
                _fallar(cliente, video_id, k, entry.get("error") or gettext("La escena no se pudo generar."))
                return
            frame = _fotograma(cliente, video_id, k, entry)
            est = datos.modificar_cadena(cliente, video_id, lambda e, _v: cadena.lista(e, k, frame))
        ks = cadena.indices(v)
        if est.get("detener"):
            datos.modificar_cadena(cliente, video_id, lambda e, _v: cadena.detenida(e))
            return
        siguiente = cadena.siguiente(est, ks)
        if siguiente is not None:
            try:
                lanzar_escena(cliente, video_id, siguiente)
            except Exception as e:  # noqa: BLE001 — la cadena queda detenida con el motivo
                log.exception("cadena: no se pudo lanzar la escena %s del video %s", siguiente, video_id)
                _fallar(cliente, video_id, siguiente, str(e))
            return
        if cadena.todas_listas(est, ks) and not est.get("preparando"):
            datos.modificar_cadena(cliente, video_id, lambda e, _v: cadena.terminada(e))
            trabajos.encolar(job_id(cliente, video_id, "unir"), "cadena_unir",
                             {"cliente": cliente, "video_id": video_id}, duracion_estimada=120, cliente=cliente,
                             max_intentos=2, prioridad=1)


# ----------------------------------------------------------------- tareas ---

@registrar("cadena_elementos")
def ejecutar_elementos(tarea):
    cliente, video_id = tarea["payload"]["cliente"], int(tarea["payload"]["video_id"])
    v = datos.video(cliente, video_id)
    est = cadena.estado(v) if v else None
    if not est or est["estado"] != "corriendo" or not est.get("preparando"):
        return gettext("No había nada que preparar.")
    nuevos = {}
    with _idioma(cliente):
        try:
            for e in cadena.elementos_necesarios(v, est["desde"]):
                if e["id"] in est["elementos"]:
                    continue
                sha = _sha(f"{cliente}:{e['id']}")
                clave = f"kling_elemento:{cliente}:{sha}"
                eid = _kv_leer(clave)
                if not eid:
                    url = medios.url_publica(cliente, e["imagen"])
                    eid = flowplus_modelos.crear_elemento(e["nombre"], e["descripcion"], url)
                    _kv_guardar(clave, eid)
                    gastos.registrar_seguro(cliente, "video", flowplus_modelos.PRECIO_ELEMENTO,
                                            f"kling_elemento:{sha}", detalle=f"Elemento de Kling · {e['nombre']}",
                                            proveedor="wavespeed", extra={"element_id": eid})
                nuevos[e["id"]] = eid
        except Exception as ex:  # noqa: BLE001 — la cadena se detiene antes de generar ningún video
            log.exception("cadena: no se pudieron crear los elementos del video %s", video_id)
            _fallar(cliente, video_id, est["desde"], gettext("No se pudieron preparar los personajes en Kling: %(e)s",
                                                             e=str(ex)[:300]))
            return gettext("No se pudieron crear los elementos.")
    datos.modificar_cadena(cliente, video_id, lambda e, _v: cadena.preparada(e, nuevos))
    vigilar_una(cliente, video_id)
    return gettext("Elementos listos; arrancó la primera escena.")


@registrar("cadena_vigilar")
def ejecutar_vigilar(tarea):
    for cliente, video_id in datos.cadenas_vivas():
        try:
            vigilar_una(cliente, video_id)
        except Exception:  # noqa: BLE001 — una cadena rota no frena a las demás; se reintenta en 60 s
            log.exception("cadena: falló el vigilante en el video %s", video_id)
    return None


@registrar("cadena_unir")
def ejecutar_unir(tarea):
    cliente, video_id = tarea["payload"]["cliente"], int(tarea["payload"]["video_id"])
    v = datos.video(cliente, video_id)
    est = cadena.estado(v) if v else None
    if not est or est["estado"] != "terminada" or est.get("edicion_id"):
        return gettext("No había nada que unir.")
    cf_ids = [est["escenas"][str(k)]["cf_id"] for k in cadena.indices(v)]
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, f"cadena_{video_id}")
    with _idioma(cliente):
        nombre = f"{v['guion'].get('titulo') or 'Flow Plus'} · {v['nombre']}"
        edicion_id = edicion_clon.crear_de_piezas(cliente, cf_ids, carpeta, nombre)
    datos.modificar_cadena(cliente, video_id, lambda e, _v: cadena.con_edicion(e, edicion_id))
    return gettext("Edición lista.")

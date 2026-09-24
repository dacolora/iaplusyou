"""
Tareas del worker para la biblioteca de referentes (spec 2026-09-23 §7).
Bloque 1: importar el swipe file de copycoders por fases — `anuncios` (bajar
la página y guardar filas), `imagenes` (tramos de TRAMO copias a R2) y
`traducir` (firmas y descripciones de familias con Claude) — cada tramo se
re-encola a sí mismo (patrón tareas/tiendas.py) para no bloquear al worker.
La única llamada pagada es la traducción: gasto tipo `otro` bajo `_creatv`.
"""
import os
from datetime import datetime, timedelta

import cola
import gastos
import trabajos
from nicho.avatares import costo_real, modelo_actual
from referentes import copycoders, datos, imagenes
from tareas import al_interrumpir, ref_sufijo, registrar

TIPO_IMPORTAR = "referentes_importar_copycoders"
JOB_IMPORTAR = "referentes:importar:copycoders"
SUFIJO_CONT = "__cont"
TRAMO = 100
LOTES_TRADUCCION = 3
FAMILIAS_POR_LLAMADA = 40
ESPERA_CONT = 5
ETAPAS_IMPORTAR = [("Leyendo la página", 1), ("Guardando anuncios", 2), ("Guardando imágenes", 12), ("Traduciendo", 3)]
CARPETA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "salidas", "referentes")


def _job_continuacion(job_id):
    return job_id[:-len(SUFIJO_CONT)] if job_id.endswith(SUFIJO_CONT) else job_id + SUFIJO_CONT


def trabajo_importacion():
    for job in (JOB_IMPORTAR, JOB_IMPORTAR + SUFIJO_CONT):
        if trabajos.en_curso(job):
            return job
    return None


def encolar_importar_copycoders(url=copycoders.URL_SWIPE, pedido_por=None):
    if trabajo_importacion():
        return False
    bid = datos.crear_barrido(None, "copycoders", {"url": url}, 0, pedido_por=pedido_por)
    return trabajos.encolar(JOB_IMPORTAR, TIPO_IMPORTAR, {"url": url, "barrido_id": bid, "fase": "anuncios"},
                            duracion_estimada=2400, etapas=ETAPAS_IMPORTAR, max_intentos=1, prioridad=2)


def _continuar(tarea, payload):
    cuando = (datetime.now() + timedelta(seconds=ESPERA_CONT)).isoformat(timespec="seconds")
    cola.encolar(TIPO_IMPORTAR, payload, job_id=_job_continuacion(tarea.get("job_id") or JOB_IMPORTAR),
                 duracion_estimada=2400, etapas=ETAPAS_IMPORTAR, ejecutar_desde=cuando, max_intentos=1, prioridad=2)


def _fase_anuncios(tarea, p, bid, avanzar):
    avanzar("Leyendo la página")
    html = copycoders.descargar_html(p["url"])
    filas = copycoders.extraer_datos(html)
    avanzar("Guardando anuncios")
    traidos = nuevos = 0
    for i, fila in enumerate(filas, 1):
        a = copycoders.normalizar(fila, p["url"])
        if not a:
            continue
        if a.get("familia"):
            datos.familia_asegurar(a["familia"], origen="copycoders")
        _, creado = datos.guardar_referente(a, cliente=None, barrido_id=bid)
        traidos += 1
        nuevos += int(creado)
        if i % 200 == 0:
            cola.reportar(tarea.get("job_id") or JOB_IMPORTAR, progreso=100.0 * i / len(filas), detalle=f"{i}/{len(filas)}")
    datos.actualizar_barrido(bid, estado="guardando", traidos=traidos, nuevos=nuevos, tarea_id=tarea.get("id"))
    _continuar(tarea, {**p, "fase": "imagenes"})
    return f"{traidos} anuncios leídos ({nuevos} nuevos); siguen las imágenes."


def _fase_imagenes(tarea, p, bid, avanzar):
    avanzar("Guardando imágenes")
    for r in datos.pendientes_imagen(fuente="copycoders", limite=TRAMO):
        try:
            url = imagenes.guardar_en_r2(r["anuncio_id"], r["imagen_origen"], CARPETA)
            datos.marcar_imagen(r["id"], "ok", url)
        except Exception:
            # No solo ImagenInvalida: guardar_en_r2 también puede lanzar un
            # error transitorio de R2/red (botocore, requests) — una imagen
            # mala no debe abortar el tramo entero (max_intentos=1).
            datos.marcar_imagen(r["id"], "error")
        c = datos.contar_imagenes("copycoders")
        total = sum(c.values()) or 1
        cola.reportar(tarea.get("job_id") or JOB_IMPORTAR, progreso=100.0 * (c["ok"] + c["error"]) / total,
                      detalle=f"{c['ok'] + c['error']}/{total}")
    c = datos.contar_imagenes("copycoders")
    datos.actualizar_barrido(bid, con_imagen=c["ok"])
    if c["pendiente"]:
        _continuar(tarea, {**p, "fase": "imagenes"})
        return f"Imágenes: {c['ok']} listas, {c['pendiente']} por bajar."
    _continuar(tarea, {**p, "fase": "traducir"})
    return f"Imágenes listas: {c['ok']} ({c['error']} fallaron). Sigue la traducción."


def _registrar_traduccion(tarea, bid, lote, ent, sal, detalle):
    usd = costo_real(ent, sal)
    gastos.registrar_seguro(datos.CLIENTE_CREATV, "otro", usd,
                            f"referentes:copycoders:traduccion:b{bid}{ref_sufijo(tarea)}:{lote}",
                            detalle=detalle, proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
    b = datos.barrido(bid) or {}
    datos.actualizar_barrido(bid, usd_real=round(float(b.get("usd_real") or 0.0) + usd, 4))


def _fase_traducir(tarea, p, bid, avanzar):
    avanzar("Traduciendo")
    progreso = False
    for lote in range(LOTES_TRADUCCION):
        pendientes = datos.sin_traducir(limite=TRAMO)
        if not pendientes:
            break
        trad, ent, sal = copycoders.traducir_firmas([(r["id"], r["firma"]) for r in pendientes])
        if datos.marcar_traducidas(list(trad.items())):
            progreso = True
        _registrar_traduccion(tarea, bid, f"firmas{lote}", ent, sal, "traducción de firmas copycoders")
        if not trad:
            break
    familias = [f for f in datos.familias() if not (f["descripcion"] or "").strip()]
    if familias:
        ejemplos = {}
        for f in familias[:FAMILIAS_POR_LLAMADA]:
            ejemplos[f["nombre"]] = [r["firma"] for r in datos.listar_por_familia(f["nombre"], limite=3) if r.get("firma")]
        desc, ent, sal = copycoders.describir_familias(list(ejemplos.items()))
        for f in familias:
            if f["nombre"] in desc:
                datos.familia_actualizar(f["id"], desc[f["nombre"]])
        _registrar_traduccion(tarea, bid, f"familias{len(familias)}", ent, sal, "descripción de familias copycoders")
    quedan = bool(datos.sin_traducir(limite=1))
    # Solo re-encolar por firmas si esta pasada avanzó algo: si una pasada
    # completa no tradujo ni una fila (Claude omitió las mismas otra vez), la
    # próxima pasada pegaría contra las mismas filas para siempre — un
    # re-encolado (y una llamada pagada) cada ESPERA_CONT segundos sin fin.
    if (quedan and progreso) or len(familias) > FAMILIAS_POR_LLAMADA:
        _continuar(tarea, {**p, "fase": "traducir"})
        return "Traduciendo firmas…"
    c = datos.contar_imagenes("copycoders")
    avisos = []
    if quedan:
        avisos.append(f"{len(datos.sin_traducir(limite=9999))} firmas no se pudieron traducir; "
                      "reintenta la importación más tarde.")
    if c["error"]:
        avisos.append(f"{c['error']} imágenes no se pudieron bajar; «Reintentar imágenes» las vuelve a pedir.")
    estado = "parcial" if (quedan or c["error"]) else "listo"
    datos.actualizar_barrido(bid, estado=estado, con_imagen=c["ok"], aviso=" ".join(avisos) or None)
    return f"Importación terminada: {c['ok']} referentes con imagen."


@registrar(TIPO_IMPORTAR)
def ejecutar_importar(tarea):
    p = tarea["payload"]
    bid = int(p["barrido_id"])
    fase = p.get("fase") or "anuncios"
    job = tarea.get("job_id") or JOB_IMPORTAR

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    try:
        if fase == "anuncios":
            return _fase_anuncios(tarea, p, bid, avanzar)
        if fase == "imagenes":
            return _fase_imagenes(tarea, p, bid, avanzar)
        return _fase_traducir(tarea, p, bid, avanzar)
    except Exception as e:
        datos.actualizar_barrido(bid, estado="error" if fase == "anuncios" else "parcial",
                                 aviso=cola.recortar(cola.sin_token(e), 300))
        raise


@al_interrumpir(TIPO_IMPORTAR)
def interrumpida_importar(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("barrido_id"):
        datos.actualizar_barrido(int(p["barrido_id"]), estado="parcial", aviso=cola.recortar(mensaje, 300))

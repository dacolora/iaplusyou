"""
Tareas del worker para la biblioteca de referentes (spec 2026-09-23 §7).
Bloque 1: importar el swipe file de copycoders por fases — `anuncios` (bajar
la página y guardar filas), `imagenes` (tramos de TRAMO copias a R2) y
`traducir` (firmas y descripciones de familias con Claude) — cada tramo se
re-encola a sí mismo (patrón tareas/tiendas.py) para no bloquear al worker.
La única llamada pagada es la traducción: gasto tipo `otro` bajo `_creatv`.

Bloque 4: `referentes_barrer` hace lo mismo por fases (`trayendo` -> Atria u
otra fuente de `referentes.fuentes`, `imagenes` -> R2, `clasificando` ->
Claude vía `referentes.clasificar`) para un `barrido` de un proyecto — un solo
job por `barrido_id` (no uno fijo como copycoders), reanudable desde el cursor
que la fuente devuelva. `referentes_clasificar` reutiliza la fase de
clasificación sola, para reintentar los pendientes/error de un barrido ya
traído. La única llamada pagada de este bloque es la clasificación: gasto
tipo `clasificacion`, una fila por referente (spec §11).
"""
import os
from datetime import datetime, timedelta

import anthropic
from flask_babel import gettext

import cola
import gastos
import trabajos
from idiomas import N_
from nicho.avatares import costo_real, modelo_actual
from referentes import clasificar, copycoders, datos, fuentes, imagenes
from referentes.fuentes.base import AVISO_CUOTA_AGOTADA, ErrorFuente
from tareas import al_interrumpir, ref_sufijo, registrar

TIPO_IMPORTAR = "referentes_importar_copycoders"
JOB_IMPORTAR = "referentes:importar:copycoders"
SUFIJO_CONT = "__cont"
TRAMO = 100
LOTES_TRADUCCION = 3
FAMILIAS_POR_LLAMADA = 40
ESPERA_CONT = 5
# Etapas de progreso: se guardan en español y `estado_trabajo` las traduce al mostrarlas.
ETAPA_LEER_PAGINA = N_("Leyendo la página")
ETAPA_GUARDAR_ANUNCIOS = N_("Guardando anuncios")
ETAPA_GUARDAR_IMAGENES = N_("Guardando imágenes")
ETAPA_TRADUCIR = N_("Traduciendo")
ETAPA_TRAER = N_("Trayendo anuncios")
ETAPA_CLASIFICAR = N_("Clasificando")
ETAPAS_IMPORTAR = [(ETAPA_LEER_PAGINA, 1), (ETAPA_GUARDAR_ANUNCIOS, 2), (ETAPA_GUARDAR_IMAGENES, 12), (ETAPA_TRADUCIR, 3)]

TIPO_BARRER = "referentes_barrer"
TIPO_CLASIFICAR = "referentes_clasificar"
ETAPAS_BARRER = [(ETAPA_TRAER, 1), (ETAPA_GUARDAR_IMAGENES, 12), (ETAPA_CLASIFICAR, 3)]
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
    avanzar(ETAPA_LEER_PAGINA)
    html = copycoders.descargar_html(p["url"])
    filas = copycoders.extraer_datos(html)
    avanzar(ETAPA_GUARDAR_ANUNCIOS)
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
    return gettext("%(traidos)s anuncios leídos (%(nuevos)s nuevos); siguen las imágenes.", traidos=traidos, nuevos=nuevos)


def _fase_imagenes(tarea, p, bid, avanzar):
    avanzar(ETAPA_GUARDAR_IMAGENES)
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
        return gettext("Imágenes: %(listas)s listas, %(pendientes)s por bajar.", listas=c["ok"], pendientes=c["pendiente"])
    _continuar(tarea, {**p, "fase": "traducir"})
    return gettext("Imágenes listas: %(listas)s (%(fallaron)s fallaron). Sigue la traducción.", listas=c["ok"],
                   fallaron=c["error"])


def _registrar_traduccion(tarea, bid, lote, ent, sal, detalle):
    usd = costo_real(ent, sal)
    gastos.registrar_seguro(datos.CLIENTE_CREATV, "otro", usd,
                            f"referentes:copycoders:traduccion:b{bid}{ref_sufijo(tarea)}:{lote}",
                            detalle=detalle, proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
    b = datos.barrido(bid) or {}
    datos.actualizar_barrido(bid, usd_real=round(float(b.get("usd_real") or 0.0) + usd, 4))


def _pagada_aunque_falle(tarea, bid, lote, detalle, llamada, *args):
    """Corre una llamada a Claude; si su respuesta no sirve pero ya se cobró
    (`FormatoInvalido` con tokens), registra ese gasto antes de repropagar."""
    try:
        return llamada(*args)
    except copycoders.FormatoInvalido as e:
        if e.tokens_entrada or e.tokens_salida:
            _registrar_traduccion(tarea, bid, f"{lote}:fallida", e.tokens_entrada, e.tokens_salida,
                                  gettext("%(detalle)s (respuesta inutilizable: %(error)s)", detalle=detalle, error=e))
        raise


def _fase_traducir(tarea, p, bid, avanzar):
    avanzar(ETAPA_TRADUCIR)
    progreso = False
    for lote in range(LOTES_TRADUCCION):
        pendientes = datos.sin_traducir(limite=TRAMO)
        if not pendientes:
            break
        trad, ent, sal = _pagada_aunque_falle(tarea, bid, f"firmas{lote}", gettext("traducción de firmas copycoders"),
                                              copycoders.traducir_firmas, [(r["id"], r["firma"]) for r in pendientes])
        if datos.marcar_traducidas(list(trad.items())):
            progreso = True
        _registrar_traduccion(tarea, bid, f"firmas{lote}", ent, sal, gettext("traducción de firmas copycoders"))
        if not trad:
            break
    familias = [f for f in datos.familias() if not (f["descripcion"] or "").strip()]
    if familias:
        ejemplos = {}
        for f in familias[:FAMILIAS_POR_LLAMADA]:
            ejemplos[f["nombre"]] = [r["firma"] for r in datos.listar_por_familia(f["nombre"], limite=3) if r.get("firma")]
        desc, ent, sal = _pagada_aunque_falle(tarea, bid, f"familias{len(familias)}",
                                              gettext("descripción de familias copycoders"),
                                              copycoders.describir_familias, list(ejemplos.items()))
        for f in familias:
            if f["nombre"] in desc:
                datos.familia_actualizar(f["id"], desc[f["nombre"]])
        _registrar_traduccion(tarea, bid, f"familias{len(familias)}", ent, sal,
                              gettext("descripción de familias copycoders"))
    quedan = bool(datos.sin_traducir(limite=1))
    # Solo re-encolar por firmas si esta pasada avanzó algo: si una pasada
    # completa no tradujo ni una fila (Claude omitió las mismas otra vez), la
    # próxima pasada pegaría contra las mismas filas para siempre — un
    # re-encolado (y una llamada pagada) cada ESPERA_CONT segundos sin fin.
    if (quedan and progreso) or len(familias) > FAMILIAS_POR_LLAMADA:
        _continuar(tarea, {**p, "fase": "traducir"})
        return gettext("Traduciendo firmas…")
    c = datos.contar_imagenes("copycoders")
    avisos = []
    if quedan:
        avisos.append(gettext("%(n)s firmas no se pudieron traducir; reintenta la importación más tarde.",
                              n=len(datos.sin_traducir(limite=9999))))
    if c["error"]:
        avisos.append(gettext("%(n)s imágenes no se pudieron bajar; «Reintentar imágenes» las vuelve a pedir.",
                              n=c["error"]))
    estado = "parcial" if (quedan or c["error"]) else "listo"
    datos.actualizar_barrido(bid, estado=estado, con_imagen=c["ok"], aviso=" ".join(avisos) or None)
    return gettext("Importación terminada: %(n)s referentes con imagen.", n=c["ok"])


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


TIPO_FAMILIAS_EN = "referentes_familias_en"
JOB_FAMILIAS_EN = "referentes:familias:en"


def encolar_familias_en(pedido_por=None):
    if trabajos.en_curso(JOB_FAMILIAS_EN):
        return False
    return trabajos.encolar(JOB_FAMILIAS_EN, TIPO_FAMILIAS_EN, {"pedido_por": pedido_por},
                            duracion_estimada=120, max_intentos=1)


def _registrar_familias_en(tarea, tanda, ent, sal, detalle):
    gastos.registrar_seguro(datos.CLIENTE_CREATV, "otro", costo_real(ent, sal),
                            f"referentes:familias_en{ref_sufijo(tarea)}:{tanda}", detalle=detalle,
                            proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})


@registrar(TIPO_FAMILIAS_EN)
def ejecutar_familias_en(tarea):
    """Descripciones en inglés de las familias (spec §B7): una llamada a
    Claude por tanda de FAMILIAS_POR_LLAMADA (las ~190 en una sola pasan el
    tope de 16 000 tokens de salida), con la descripción en español como
    ejemplo. Gasto tipo `otro` bajo `_creatv` por tanda, también si la
    respuesta no sirvió; lo ya escrito queda aunque una tanda falle y el
    próximo clic sigue con lo que falte."""
    pendientes = datos.familias_sin_descripcion_en()
    if not pendientes:
        return gettext("No hay familias sin descripción en inglés.")
    escritas = 0
    for n, i in enumerate(range(0, len(pendientes), FAMILIAS_POR_LLAMADA)):
        tanda = pendientes[i:i + FAMILIAS_POR_LLAMADA]
        try:
            desc, ent, sal = copycoders.describir_familias([(f["nombre"], [f["descripcion"]]) for f in tanda], idioma="en")
        except copycoders.FormatoInvalido as e:
            if e.tokens_entrada or e.tokens_salida:
                _registrar_familias_en(tarea, n, e.tokens_entrada, e.tokens_salida,
                                       gettext("familias en inglés (respuesta inutilizable: %(error)s)", error=e))
            raise
        for f in tanda:
            if f["nombre"] in desc:
                datos.familia_actualizar(f["id"], descripcion_en=desc[f["nombre"]])
                escritas += 1
        _registrar_familias_en(tarea, n, ent, sal, gettext("familias en inglés"))
    return gettext("Descripciones en inglés: %(n)s de %(total)s.", n=escritas, total=len(pendientes))


# ---------------------------------------------------------------- bloque 4 ---
# `referentes_barrer`: trae un barrido de una fuente (`referentes.fuentes`,
# hoy solo Atria) por fases, con un job por `barrido_id` (a diferencia del job
# fijo de copycoders arriba, acá puede haber varios barridos vivos a la vez,
# uno por cliente/consulta). `referentes_clasificar` reutiliza solo la fase de
# clasificación para reintentar los pendientes/error de un barrido ya traído.

def job_id_barrer(barrido_id):
    return f"referentes:barrer:{barrido_id}"


def trabajo_barrer(barrido_id):
    """job_id vivo (pendiente o en_curso) de ESTE barrido, sea que lo esté
    corriendo `referentes_barrer` (trayendo/imagenes/clasificando) o
    `referentes_clasificar` (clasificando solo) — ambos comparten el mismo
    job_id por barrido_id, así que nunca hay dos a la vez."""
    base = job_id_barrer(barrido_id)
    for job in (base, base + SUFIJO_CONT):
        if trabajos.en_curso(job):
            return job
    return None


def _job_continuacion_barrer(job_id):
    """Igual que `_job_continuacion` (copycoders): alterna el job_id VIVO
    entre base y base+SUFIJO_CONT. Debe operar sobre `job_id` (el que de
    verdad viene de la tarea/continuación anterior), nunca sobre un
    `job_id_barrer(bid)` recalculado desde cero — ese jamás lleva el sufijo,
    así que recortarle el final en vez de al `job_id` real trunca la cadena
    (bug real: colisionaba entre barridos distintos, p. ej. "referentes:ba")."""
    return job_id[:-len(SUFIJO_CONT)] if job_id.endswith(SUFIJO_CONT) else job_id + SUFIJO_CONT


def _continuar_barrer(tarea, payload, bid, tipo=TIPO_BARRER):
    cuando = (datetime.now() + timedelta(seconds=ESPERA_CONT)).isoformat(timespec="seconds")
    cola.encolar(tipo, payload, job_id=_job_continuacion_barrer(tarea.get("job_id") or job_id_barrer(bid)),
                cliente=tarea.get("cliente"),
                duracion_estimada=1800, etapas=ETAPAS_BARRER, ejecutar_desde=cuando, max_intentos=1, prioridad=2)


def encolar_barrer(cliente, fuente, consulta, tope, usd_estimado, pedido_por=None):
    """Crea el `barrido` y encola su primera fase (`trayendo`). `tope` se
    limita a 2000 acá (no solo en la ruta) porque esta función es el único
    punto de entrada real — cualquier ruta que la llame queda cubierta."""
    tope = min(int(tope or 0), 2000)
    bid = datos.crear_barrido(cliente, fuente, consulta, tope, pedido_por=pedido_por, usd_estimado=usd_estimado)
    trabajos.encolar(job_id_barrer(bid), TIPO_BARRER,
                     {"cliente": cliente, "barrido_id": bid, "fase": "trayendo",
                      "consulta": {**consulta, "fuente": fuente}, "tope": tope},
                     duracion_estimada=1800, etapas=ETAPAS_BARRER, max_intentos=1, prioridad=2, cliente=cliente)
    return bid


def encolar_clasificar_pendientes(cliente, barrido_id):
    """Reintenta solo la clasificación de los referentes `pendiente`/`error`
    de un barrido ya traído. `False` si el barrido no existe o ya hay un job
    vivo para él (trayendo, guardando imágenes o clasificando)."""
    if trabajo_barrer(barrido_id):
        return False
    b = datos.barrido(barrido_id)
    if not b:
        return False
    trabajos.encolar(job_id_barrer(barrido_id), TIPO_CLASIFICAR,
                     {"cliente": cliente, "barrido_id": barrido_id, "fase": "clasificando",
                      "consulta": {**(b.get("consulta") or {}), "fuente": b["fuente"]}, "tope": b.get("tope") or 0},
                     duracion_estimada=600, etapas=[(ETAPA_CLASIFICAR, 1)], max_intentos=1, prioridad=2, cliente=cliente)
    return True


def encolar_reintentar_imagenes(cliente, barrido_id):
    """Vuelve a `pendiente` las imágenes en `error` de un barrido y re-encola
    la fase de imágenes. `False` si el barrido no existe o ya hay un job vivo."""
    if trabajo_barrer(barrido_id):
        return False
    b = datos.barrido(barrido_id)
    if not b:
        return False
    datos.reintentar_imagenes(barrido_id)
    trabajos.encolar(job_id_barrer(barrido_id), TIPO_BARRER,
                     {"cliente": cliente, "barrido_id": barrido_id, "fase": "imagenes",
                      "consulta": {**(b.get("consulta") or {}), "fuente": b["fuente"]}, "tope": b.get("tope") or 0},
                     duracion_estimada=600, etapas=ETAPAS_BARRER, max_intentos=1, prioridad=2, cliente=cliente)
    return True


def _fase_trayendo(tarea, p, bid, avanzar):
    """Trae hasta `tope` anuncios de la fuente, retomando desde el cursor
    guardado en `barrido.extra.cursor_atria` (así una continuación no vuelve a
    pedir lo mismo). Un `ErrorFuente` sin nada traído todavía es un error real
    (nunca se llegó a guardar nada); si ya se trajo algo, se trata igual que
    el fin natural de la fuente (cursor_final=None) — Atria documenta que así
    señala una entrega parcial (p. ej. se acabó el cupo del mes a mitad).

    Esa entrega parcial (por excepción, atrapada acá abajo, O por el
    `AVISO_CUOTA_AGOTADA` que `traer()` manda por `avanzar` cuando ya venía
    trayendo algo EN esta misma llamada) antes no dejaba rastro: el barrido
    seguía a imágenes/clasificación como si la búsqueda se hubiera agotado
    sola. Se guarda en `extra.aviso_trayendo` para que `_fase_clasificando`
    (la fase final) lo sume a su propio aviso en vez de pisarlo (spec §12)."""
    avanzar(ETAPA_TRAER)
    b = datos.barrido(bid) or {}
    consulta = p["consulta"]
    tope = int(p["tope"])
    cursor = (b.get("extra") or {}).get("cursor_atria")
    traidos_total = int(b.get("traidos") or 0)
    nuevos_total = int(b.get("nuevos") or 0)
    fuente_mod = fuentes.por_tipo(consulta["fuente"])
    cliente_gasto = p.get("cliente") or datos.CLIENTE_CREATV
    cursor_final = cursor
    aviso_parcial = None
    cuota_agotada = False

    def avanzar_trayendo(etapa=None, detalle=None):
        nonlocal cuota_agotada
        if detalle == AVISO_CUOTA_AGOTADA:
            cuota_agotada = True
            return
        avanzar(etapa=etapa, detalle=detalle)

    try:
        for pagina, cursor_siguiente, meta in fuente_mod.traer(consulta, tope - traidos_total, avanzar_trayendo, cursor=cursor):
            if (meta or {}).get("aviso"):
                aviso_parcial = meta["aviso"]
            costo_real = (meta or {}).get("costo_real")
            # La referencia no varía por página dentro de esta misma tarea: si una
            # fuente futura reportara costo_real en MÁS de una página en una sola
            # llamada, gastos.registrar() (upsert por referencia) pisaría el costo
            # de páginas anteriores en vez de sumarlo. Ninguna fuente actual lo hace
            # (Atria: meta siempre {}; toda fuente de pago futura debe reportar
            # costo_real en, a lo sumo, un yield por llamada a traer(), o la
            # referencia necesita variar por página).
            if costo_real:
                gastos.registrar_seguro(cliente_gasto, "recoleccion", costo_real,
                                        f"referentes:barrer:{bid}:{consulta['fuente']}:t{tarea.get('id')}",
                                        detalle=gettext("%(fuente)s: %(n)s anuncio(s) reales", fuente=consulta["fuente"],
                                                        n=len(pagina)), proveedor=consulta["fuente"],
                                        extra={k: v for k, v in (meta or {}).items() if k != "costo_real"})
                # Mismo mecanismo que `_fase_clasificando` con su gasto de
                # Claude (Important 1 del review final): sin esto, el costo
                # real de Apify queda solo en `gastos` y "Mis barridos"
                # sigue mostrando Costo 0.00 aunque ya se haya pagado.
                b2 = datos.barrido(bid) or {}
                datos.actualizar_barrido(bid, usd_real=round(float(b2.get("usd_real") or 0.0) + costo_real, 4))
            for a in pagina:
                if not a or not a.get("anuncio_id") or not a.get("imagen_origen"):
                    continue
                a = dict(a, fuente=consulta["fuente"])
                _, creado = datos.guardar_referente(a, cliente=p["cliente"], barrido_id=bid)
                traidos_total += 1
                nuevos_total += int(creado)
            cursor_final = cursor_siguiente
            if traidos_total - int(b.get("traidos") or 0) >= TRAMO:
                break
    except ErrorFuente as e:
        # Una corrida ya cobrada (p. ej. Apify) que además falla sin entregar
        # nada debe registrar igual lo que se pagó -- "on failure after
        # paying, register what was paid with a detalle" (CLAUDE.md). Esto va
        # ANTES de decidir si es error total o entrega parcial: el costo se
        # registra en los dos casos.
        costo_real = getattr(e, "costo_real", None)
        if costo_real:
            gastos.registrar_seguro(cliente_gasto, "recoleccion", costo_real,
                                    f"referentes:barrer:{bid}:{consulta['fuente']}:t{tarea.get('id')}",
                                    detalle=gettext("%(fuente)s: corrida cobrada pero no se pudo leer del todo",
                                                    fuente=consulta["fuente"]), proveedor=consulta["fuente"],
                                    extra=getattr(e, "extra_gasto", {}))
            # Mismo motivo que en el bucle de arriba: esto también es plata
            # ya pagada y debe verse en "Mis barridos", aunque la corrida
            # haya terminado en error total.
            b2 = datos.barrido(bid) or {}
            datos.actualizar_barrido(bid, usd_real=round(float(b2.get("usd_real") or 0.0) + costo_real, 4))
        if traidos_total == 0:
            datos.actualizar_barrido(bid, estado="error", aviso=cola.recortar(str(e), 300))
            raise
        cursor_final = None
        aviso_parcial = gettext("Se detuvo de traer más anuncios: %(motivo)s.", motivo=e)
    if not aviso_parcial and cuota_agotada:
        aviso_parcial = gettext("Se detuvo de traer más anuncios: se acabó el cupo mensual de Atria.")
    extra = dict(b.get("extra") or {})
    extra["cursor_atria"] = cursor_final
    if aviso_parcial:
        extra["aviso_trayendo"] = cola.recortar(aviso_parcial, 300)
    datos.actualizar_barrido(bid, traidos=traidos_total, nuevos=nuevos_total, extra=extra, tarea_id=tarea.get("id"))
    if traidos_total >= tope or not cursor_final:
        datos.actualizar_barrido(bid, estado="guardando")
        _continuar_barrer(tarea, {**p, "fase": "imagenes"}, bid)
        return gettext("%(traidos)s anuncios traídos (%(nuevos)s nuevos); siguen las imágenes.",
                       traidos=traidos_total, nuevos=nuevos_total)
    _continuar_barrer(tarea, {**p, "fase": "trayendo"}, bid)
    return gettext("Trayendo… %(traidos)s/%(tope)s.", traidos=traidos_total, tope=tope)


def _fase_imagenes_barrer(tarea, p, bid, avanzar):
    """Igual que `_fase_imagenes` (copycoders) pero acotada a ESTE barrido
    (`barrido_id=bid`, nunca todas las pendientes globales) — nombre propio
    a propósito: un solo `_fase_imagenes` para los dos bloques pisaría la
    función de copycoders (mismo nombre de módulo) y rompería su import."""
    avanzar(ETAPA_GUARDAR_IMAGENES)
    for r in datos.pendientes_imagen(barrido_id=bid, limite=TRAMO):
        try:
            clave = f"{r['anuncio_id']}_r{r['id']}" if r.get("cliente") else r["anuncio_id"]
            url = imagenes.guardar_en_r2(clave, r["imagen_origen"], CARPETA)
            datos.marcar_imagen(r["id"], "ok", url)
        except Exception:
            # Igual que en copycoders: una imagen mala no debe abortar el
            # tramo entero (max_intentos=1) ni las que vengan después.
            datos.marcar_imagen(r["id"], "error")
    con_imagen, pendientes_img, _errores_img = datos.contar_imagenes_de_barrido(bid)
    datos.actualizar_barrido(bid, con_imagen=con_imagen)
    if pendientes_img:
        _continuar_barrer(tarea, {**p, "fase": "imagenes"}, bid)
        return gettext("Imágenes: %(listas)s listas, %(pendientes)s por bajar.", listas=con_imagen,
                       pendientes=pendientes_img)
    _continuar_barrer(tarea, {**p, "fase": "clasificando"}, bid)
    return gettext("Imágenes listas: %(listas)s. Sigue la clasificación.", listas=con_imagen)


def _clasificar_uno(cliente, r):
    """Clasifica un referente y actualiza sus columnas; un fallo de Claude
    (`ClasificacionInvalida`) deja `clasificacion=error` y el llamador sigue
    con el siguiente sin abortar el tramo. Lo mismo un `anthropic.BadRequestError`
    (4xx del propio proveedor, p. ej. "no pude procesar la imagen" — no tiene
    sentido reintentar la MISMA fila con la MISMA imagen): sin esto, un solo
    referente problemático revienta el tramo entero y, como queda
    `clasificacion=pendiente` y ordena primero por id, bloquea PERMANENTEMENTE
    todo lo demás del barrido (automático Y "Clasificar pendientes" pegan
    contra la misma fila cada vez). Un fallo de otro tipo (429, timeout, red)
    SÍ se deja subir — lo atrapa el wrapper de `ejecutar_barrer`/
    `ejecutar_clasificar`, que marca el barrido y corta el tramo (nada raro:
    max_intentos=1, no tiene sentido seguir gastando si la API está caída, y
    ese tipo de error SÍ suele resolverse solo en un reintento posterior).
    Devuelve (ok: bool, tokens_entrada, tokens_salida)."""
    vocabulario = [f["nombre"] for f in datos.familias()]
    try:
        resultado, ent, sal = clasificar.clasificar(r, vocabulario)
    except clasificar.ClasificacionInvalida as e:
        ent = getattr(e, "tokens_entrada", 0) or 0
        sal = getattr(e, "tokens_salida", 0) or 0
        extra = dict(r.get("extra") or {})
        extra["error_clasificacion"] = str(e)
        datos.actualizar_referente(r["id"], clasificacion="error", extra=extra)
        return False, ent, sal
    except anthropic.BadRequestError as e:
        # Un 400 no trae uso facturado (la llamada nunca llegó a completarse
        # del lado de Anthropic) — 0 tokens, así que el llamador (que solo
        # registra gasto si ent o sal son verdaderos) no registra nada.
        extra = dict(r.get("extra") or {})
        extra["error_clasificacion"] = cola.sin_token(str(e))
        datos.actualizar_referente(r["id"], clasificacion="error", extra=extra)
        return False, 0, 0
    familia = resultado["familia"]
    if resultado.get("familia_nueva"):
        fn = resultado["familia_nueva"]
        nombre_nuevo = f"EMERGING: {fn['nombre']}"
        descripcion_nueva = fn.get("descripcion") or ""
        # La descripción de una familia nueva va a la columna del idioma en
        # que Claude escribió (spec §B7, fix round 1): un proyecto clasificado
        # en inglés no debe dejar texto en inglés en la columna española que
        # leen los proyectos en español; un referente global (es+en) sigue
        # escribiendo español como siempre.
        if clasificar.salida_para(r)[0] == "en":
            datos.familia_asegurar(nombre_nuevo, "", origen="claude", descripcion_en=descripcion_nueva)
        else:
            datos.familia_asegurar(nombre_nuevo, descripcion_nueva, origen="claude")
        familia = nombre_nuevo
    # `actualizar_referente` reemplaza `extra` entero: se copia y se agrega el arranque.
    extra = dict(r.get("extra") or {})
    if resultado.get("lead"):
        extra["lead"] = resultado["lead"]
    if resultado.get("i18n"):
        extra["i18n"] = resultado["i18n"]
    datos.actualizar_referente(r["id"], etapa=resultado["etapa"], consciencia=resultado["consciencia"],
                               familia=familia, dolor=resultado["dolor"], firma=resultado["firma"],
                               clasificacion="claude", extra=extra)
    return True, ent, sal


def _fase_clasificando(tarea, p, bid, avanzar):
    """Compartida por `referentes_barrer` (su propia fase 3, automática) y
    `referentes_clasificar` (standalone, un clic explícito de "Clasificar
    pendientes") — por eso re-encola con `tipo=tipo_actual`: cada una debe
    seguir re-encolándose como el tipo con el que arrancó, nunca cruzarse a
    la otra.

    `pendientes_clasificacion` puede traer `pendiente` Y `error` (un fallo de
    Claude se reintenta en una pasada futura) — pero el tramo AUTOMÁTICO
    (dentro de `referentes_barrer`) pide `incluir_error=False`: el costo de
    un barrido ya se aprobó una vez al lanzarlo, así que no debe re-facturar
    la MISMA fila en error en cada tramo si Claude sigue fallando igual —
    esa fila queda para que la persona la reintente ella misma con
    "Clasificar pendientes" (que sí pide con `error` incluido, spec §11
    "sus filas pendiente/error"). Independientemente de eso, igual que
    `_fase_traducir` con las traducciones, una pasada que no clasifica NADA
    tampoco debe re-encolarse: sin la bandera `avanzo`, un referente
    permanentemente problemático (imagen no interpretable, prompt que Claude
    nunca cumple) reencolaría —y pagaría una llamada, en el caso standalone—
    cada ESPERA_CONT segundos para siempre, sin que el barrido llegue nunca a
    un estado final."""
    avanzar(ETAPA_CLASIFICAR)
    # «Mis barridos» lee `barrido.estado`: sin esto seguía en «Guardando
    # imágenes» durante toda la clasificación (2026-09-27). Al terminar, el
    # final de esta fase lo deja en listo/parcial como siempre.
    datos.actualizar_barrido(bid, estado="clasificando")
    cliente = p.get("cliente")
    cliente_gasto = cliente or datos.CLIENTE_CREATV
    tipo_actual = tarea.get("tipo") or TIPO_BARRER
    automatico = tipo_actual != TIPO_CLASIFICAR
    pendientes = datos.pendientes_clasificacion(barrido_id=bid, limite=TRAMO, incluir_error=not automatico)
    b = datos.barrido(bid) or {}
    clasificados = int(b.get("clasificados") or 0)
    avanzo = False
    for i, r in enumerate(pendientes, 1):
        ok, ent, sal = _clasificar_uno(cliente, r)
        avanzo = avanzo or ok
        if ent or sal:
            usd = costo_real(ent, sal)
            gastos.registrar_seguro(cliente_gasto, "clasificacion", usd, f"referentes:clasificar:{r['id']}{ref_sufijo(tarea)}",
                                    detalle=r.get("titular") or r.get("marca") or "", proveedor="anthropic",
                                    entregado=ok,   # una clasificación inválida no llegó (cobros §3.4)
                                    extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
            b2 = datos.barrido(bid) or {}
            datos.actualizar_barrido(bid, usd_real=round(float(b2.get("usd_real") or 0.0) + usd, 4))
        clasificados += int(ok)
        cola.reportar(tarea.get("job_id") or job_id_barrer(bid), progreso=100.0 * i / max(1, len(pendientes)),
                      detalle=f"{i}/{len(pendientes)}")
    # `pendientes_total` cuenta TODO lo que aún no está clasificado (pendiente
    # + error, `incluir_error` por defecto) — es la estadística que ve la
    # persona (columna `pendientes`, aviso final), independiente de cuáles de
    # esas filas el tramo automático está dispuesto a reintentar por su cuenta.
    filas_pendientes = datos.pendientes_clasificacion(barrido_id=bid, limite=9999)
    pendientes_total = len(filas_pendientes)
    datos.actualizar_barrido(bid, clasificados=clasificados, pendientes=pendientes_total)
    if pendientes_total and avanzo:
        _continuar_barrer(tarea, {**p, "fase": "clasificando"}, bid, tipo=tipo_actual)
        return gettext("Clasificando… %(n)s listos.", n=clasificados)
    # `error` (no `pendiente`, que a esta altura la fase de imágenes ya dejó
    # siempre en 0 — Important 1) es lo que de verdad hay que avisar y lo que
    # gatilla «Reintentar imágenes» en la plantilla.
    _, _pendiente_img, sin_imagen = datos.contar_imagenes_de_barrido(bid)
    avisos = []
    # El aviso de la fase "trayendo" (entrega parcial de Atria, ya sea por
    # cupo agotado o por un ErrorFuente con algo ya traído — spec §12) va
    # PRIMERO: si no se concatena acá, este `actualizar_barrido(..., aviso=)`
    # lo pisa en silencio con lo que esta fase encuentre.
    b_final = datos.barrido(bid) or {}
    aviso_trayendo = (b_final.get("extra") or {}).get("aviso_trayendo")
    if aviso_trayendo:
        avisos.append(aviso_trayendo)
    if pendientes_total:
        aviso_clasificar = gettext("%(n)s referentes no se pudieron clasificar; "
                                   "«Clasificar pendientes» los vuelve a pedir.", n=pendientes_total)
        # El motivo va a la vista: sin él, un reintento que falla igual parece
        # un botón que «no hace nada».
        motivos = [m for m in dict.fromkeys(str((r.get("extra") or {}).get("error_clasificacion") or "").strip()
                                            for r in filas_pendientes) if m]
        if motivos:
            motivo = cola.recortar(motivos[0], 160)
            aviso_clasificar += " " + (gettext("Motivo: %(motivo)s (y otros)", motivo=motivo) if len(motivos) > 1
                                       else gettext("Motivo: %(motivo)s", motivo=motivo))
        avisos.append(aviso_clasificar)
    if sin_imagen:
        avisos.append(gettext("%(n)s imágenes no se pudieron bajar; «Reintentar imágenes» las vuelve a pedir.",
                              n=sin_imagen))
    aviso = " ".join(avisos) or None
    datos.actualizar_barrido(bid, estado="parcial" if aviso else "listo", aviso=aviso)
    return gettext("Barrido terminado: %(n)s referentes clasificados.", n=clasificados)


@registrar(TIPO_BARRER)
def ejecutar_barrer(tarea):
    p = tarea["payload"]
    bid = int(p["barrido_id"])
    fase = p.get("fase") or "trayendo"

    # `etapa=None` por defecto: `referentes.fuentes.atria.traer()` llama a
    # este `avanzar` con SOLO `detalle=` (nunca `etapa`, spec Task 2) para
    # reportar progreso dentro de la fase "Trayendo anuncios" ya fijada más
    # arriba — con `etapa` obligatorio, esa llamada real revienta con
    # TypeError en el primer reporte de progreso de cualquier barrido real
    # (los dobles falsos de `traer` en las pruebas nunca llaman `avanzar`
    # así, por eso no se veía antes).
    def avanzar(etapa=None, detalle=None):
        cola.reportar(tarea.get("job_id") or job_id_barrer(bid), etapa=etapa, detalle=detalle)

    try:
        if fase == "trayendo":
            return _fase_trayendo(tarea, p, bid, avanzar)
        if fase == "imagenes":
            return _fase_imagenes_barrer(tarea, p, bid, avanzar)
        return _fase_clasificando(tarea, p, bid, avanzar)
    except Exception as e:
        # Mismo patrón que ejecutar_importar (y el resto de tareas/*.py): sin
        # esto, una excepción que no sea el ErrorFuente ya manejado adentro de
        # _fase_trayendo (p. ej. un bug de verdad, o la API de Anthropic caída
        # en medio de _fase_clasificando) deja la tarea en `error` pero el
        # barrido colgado para siempre en su estado anterior, sin aviso ni
        # forma de reintentar desde la UI.
        datos.actualizar_barrido(bid, estado="error" if fase == "trayendo" else "parcial",
                                 aviso=cola.recortar(cola.sin_token(e), 300))
        raise


@registrar(TIPO_CLASIFICAR)
def ejecutar_clasificar(tarea):
    p = tarea["payload"]
    bid = int(p["barrido_id"])

    def avanzar(etapa=None, detalle=None):
        cola.reportar(tarea.get("job_id") or job_id_barrer(bid), etapa=etapa, detalle=detalle)

    try:
        return _fase_clasificando(tarea, p, bid, avanzar)
    except Exception as e:
        datos.actualizar_barrido(bid, estado="parcial", aviso=cola.recortar(cola.sin_token(e), 300))
        raise


@al_interrumpir(TIPO_BARRER)
def interrumpida_barrer(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("barrido_id"):
        datos.actualizar_barrido(int(p["barrido_id"]), estado="parcial", aviso=cola.recortar(mensaje, 300))


@al_interrumpir(TIPO_CLASIFICAR)
def interrumpida_clasificar(tarea, mensaje):
    interrumpida_barrer(tarea, mensaje)

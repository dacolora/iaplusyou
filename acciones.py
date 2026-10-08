"""
Acciones del motor (Bloque 4): lo que el decisor recomienda sobre una pieza o
un país — pausar, escalar, derivar, rescatar, activar, archivar — pasa por
aquí. Dos puertas:

- `pedir(...)`: consulta el modo del experimento (modos.resolver) y el tope de
  gasto; o ejecuta la acción, o la deja como propuesta pendiente para el
  humano. En ambos casos escribe un evento.
- `ejecutar(...)`: hace la acción de verdad (Meta vía lanzador, producción vía
  derivaciones). Es idempotente sobre `experimento_pieza.extra`
  (`derivado`, `rescatado_en_escalon`, `archivado`): repetir una acción cara
  no vuelve a gastar. La marca la escribe `derivaciones.planificar` apenas
  la parte que gasta (producción) quedó guardada — antes de encolar y antes
  de la parte barata y reintentable (pausar en Meta) — y acá solo se
  refuerza (idempotente: `max` con lo que ya haya), así ni un fallo de
  Meta ni un fallo al encolar provocan doble producción (I-5).

Nada se activa solo: la única vía es `ejecutar(..., "activar", ...)`, que en
los modos manual/semi solo llega tras aprobar la propuesta.

`publicar_organico` (Bloque 7): la ganadora sale como contenido orgánico
(organico.py). No gasta crédito pero es público e irreversible, así que en
manual/semi siempre es propuesta — y `pedir` la deja con el texto YA
redactado (`payload["captions"]`) para que la persona lo lea/edite antes de
aprobar. Idempotente por la unicidad viva de `publicacion` (una plataforma
con publicación en cola/publicándose/publicada se salta) y por
`trabajos.en_curso`. `extra.publicado_organico` es solo una marca informativa
("ya salió orgánica alguna vez"), escrita apenas se encoló algo de verdad;
hoy nadie la lee para decidir nada.
"""
from contextlib import contextmanager

from flask_babel import gettext

import cola
import creative_flow
import decisor
import derivaciones
import experimentos
import gastos
import idiomas
import lanzador
import modos
import organico
import propuestas
import proyectos
import trabajos
from cobros import SaldoInsuficiente, libro
from tareas import organico as tareas_organico

# Acciones que pueden aumentar el gasto: chequean el tope antes de ejecutarse.
_ACCIONES_CON_GASTO = ("escalar", "activar", "derivar")
# Generaciones de derivación (extra.profundidad) a partir de las cuales
# "derivar" siempre queda como propuesta, sea cual sea el modo (I-9).
PROFUNDIDAD_MAXIMA = 2
# Rótulo de cada `accion` (propuesta.accion, la etiqueta que se ve): la clave
# guardada no cambia — |traducir en la plantilla, nunca acá.
ETIQUETAS_ACCION = {
    "pausar": idiomas.N_("pausar"), "escalar": idiomas.N_("escalar"), "derivar": idiomas.N_("derivar"),
    "rescatar": idiomas.N_("rescatar"), "activar": idiomas.N_("activar"), "archivar": idiomas.N_("archivar"),
    "publicar_organico": idiomas.N_("publicar orgánico"),
}


@contextmanager
def _del_proyecto(cliente):
    """Lo que un efecto GUARDA (eventos del lanzador, el experimento hijo)
    va en el idioma del proyecto aunque la acción la apruebe alguien que mira
    en otro idioma (I2); el mensaje que devuelve `ejecutar` queda afuera."""
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        yield


def _experimento(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError(gettext("Ese experimento no existe."))
    return ex


def _pieza(ex, ep_id):
    pz = next((p for p in ex["piezas"] if p["id"] == ep_id), None)
    if pz is None:
        raise ValueError(gettext("Esa pieza no está en el experimento."))
    return pz


def _pausar_si_activa(cliente, pz):
    """Pausa en Meta solo si hay anuncio y no está ya pausada (pausar_pieza
    exige meta_ad_id)."""
    if pz.get("meta_ad_id") and pz.get("estado") != "pausado":
        lanzador.pausar_pieza(cliente, pz["id"])


def _cadena_conceptos(cliente, cf_id, maximo=5):
    """La sesión de la pieza y, hacia arriba, de las que fue regenerada
    (`derivado_de`): archivar un concepto que perdió sus 3 escalones archiva
    toda la cadena, no solo la última regeneración. Tope de `maximo` saltos
    por si hubiera un ciclo en los datos."""
    if not cf_id:
        return []
    sesiones = creative_flow.cargar(cliente)
    cadena = []
    while cf_id and cf_id not in cadena and len(cadena) < maximo:
        cadena.append(cf_id)
        cf_id = (sesiones.get(cf_id) or {}).get("derivado_de")
    return cadena


def reglas_de(cliente, ex):
    return decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex.get("reglas"))


def tope_alcanzado(ex):
    """Aproximación del chequeo de tope: con el gasto acumulado ya en el tope
    total no se abre ninguna acción que gaste más."""
    tope = float(ex.get("tope_total") or 0)
    return tope > 0 and float(ex.get("gasto_acumulado") or 0) >= tope


def _registrar_evento_aprobada(cliente, experimento_id, accion, payload, propuesta_id, ep_id_evento, armar_mensaje):
    """Deja en la bitácora el evento de una propuesta aprobada a mano
    (dashboard.prop_aprobar/prop_aprobar_todas) — en el idioma del proyecto,
    porque es texto que se guarda (spec 2026-09-26 §B3: lo que se guarda
    sigue al proyecto, lo que responde una ruta sigue a quien mira). No hace
    nada si `propuesta_id` es None (la acción no vino de una propuesta:
    `pedir` ya registra su propio evento, en el idioma que puso quien la
    llamó — el worker). `armar_mensaje` es una función sin argumentos que
    arma EL MISMO texto que ya se le devolvió a quien aprobó (mismo msgid,
    mismos datos) — se llama DENTRO de idiomas.en_idioma(proyecto) para que
    tanto el gettext final como cualquier gettext/_nombres(...) anidado que
    arme por dentro queden en ese idioma, nunca en el de quien mira; no
    repite ningún efecto real, ya ocurrió antes de llegar acá. Un fallo acá
    no deshace la acción — ya se ejecutó de verdad — así que se traga."""
    if propuesta_id is None:
        return
    try:
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            experimentos.registrar_evento(
                cliente, experimento_id, "accion",
                gettext("%(mensaje)s (propuesta #%(id)s aprobada a mano)",
                        mensaje=armar_mensaje(), id=propuesta_id),
                {"accion": accion, "payload": payload, "propuesta_id": propuesta_id}, ep_id=ep_id_evento)
    except Exception:  # noqa: BLE001 — la acción ya pasó; un evento que falla no la deshace
        pass


def ejecutar(cliente, experimento_id, accion, payload, propuesta_id=None, ep_id_evento=None):
    """Ejecuta la acción y devuelve un mensaje corto de lo que pasó, en el
    idioma ambiente de quien llama (el proyecto, si es el worker — lo pone
    worker.ejecutar —; quien mira, si es una ruta). Lanza ValueError si la
    acción no existe o faltan datos. Lo que los efectos GUARDAN (eventos del
    lanzador, el experimento hijo, errores de publicación) va en el idioma del
    proyecto (`_del_proyecto`, I2 de la fase 4), y un ValueError que salga de
    adentro de un efecto, también. `propuesta_id`/`ep_id_evento`: cuando la
    acción viene de aprobar una propuesta a mano (dashboard._ejecutar_propuesta),
    además deja el evento en la bitácora en el idioma del proyecto — ver
    `_registrar_evento_aprobada`."""
    payload = payload or {}
    ex = _experimento(cliente, experimento_id)
    motivo = payload.get("motivo") or ""

    def _evento(plantilla, **kw):
        # kw ya son datos simples (nombres, países, números) — ninguno pasa
        # por gettext antes de aquí, así que evaluarlos ahora (fuera del
        # `with` que arma el mensaje guardado) es seguro; el «sin motivo» de
        # archivar es la única excepción y se resuelve aparte, arriba.
        _registrar_evento_aprobada(cliente, experimento_id, accion, payload, propuesta_id, ep_id_evento,
                                   lambda: gettext(plantilla, **kw))

    if accion == "pausar":
        pz = _pieza(ex, payload["ep_id"])
        with _del_proyecto(cliente):
            lanzador.pausar_pieza(cliente, pz["id"])
        _evento("Pausada %(nombre)s (%(pais)s).", nombre=pz["nombre"], pais=pz["pais"])
        return gettext("Pausada %(nombre)s (%(pais)s).", nombre=pz["nombre"], pais=pz["pais"])

    if accion == "escalar":
        pais = payload["pais"]
        reglas = reglas_de(cliente, ex)
        with _del_proyecto(cliente):
            nuevo = lanzador.escalar_pais(cliente, experimento_id, pais, reglas["escalar_pct_dia"],
                                          reglas["escalar_tope_dia"])
        _evento("Presupuesto de %(pais)s escalado a %(nuevo)s %(moneda)s por día.",
               pais=pais, nuevo=f"{nuevo:g}", moneda=ex.get("moneda") or "")
        return gettext("Presupuesto de %(pais)s escalado a %(nuevo)s %(moneda)s por día.",
                       pais=pais, nuevo=f"{nuevo:g}", moneda=ex.get("moneda") or "")

    if accion == "derivar":
        pz = _pieza(ex, payload["ep_id"])
        if (pz.get("extra") or {}).get("derivado"):
            _evento("%(nombre)s ya derivada: no se vuelve a producir.", nombre=pz["nombre"])
            return gettext("%(nombre)s ya derivada: no se vuelve a producir.", nombre=pz["nombre"])
        _exigir_saldo(cliente, ex, accion, payload)
        with _del_proyecto(cliente):
            hijo = derivaciones.planificar(cliente, experimento_id, "derivar", payload)
        # planificar ya marcó `derivado`; repetirlo es inocuo (misma bandera).
        experimentos.marcar_pieza(cliente, pz["id"], derivado=True)
        _evento("Derivación planificada a partir de %(nombre)s (experimento hijo %(hijo)s).",
               nombre=pz["nombre"], hijo=hijo)
        return gettext("Derivación planificada a partir de %(nombre)s (experimento hijo %(hijo)s).",
                       nombre=pz["nombre"], hijo=hijo)

    if accion == "rescatar":
        pz = _pieza(ex, payload["ep_id"])
        extra = pz.get("extra") or {}
        escalon_actual = int(pz.get("escalon_rescate") or 0)
        marcado = extra.get("rescatado_en_escalon")
        # A lo sumo un rescate por escalón. `planificar` sube
        # `escalon_rescate` de la pieza y acá se marca ese mismo número, así
        # que "ya marcado en el escalón actual (o más alto)" significa que el
        # rescate de este escalón ya se planificó: no se vuelve a producir ni
        # a gastar; solo se asegura la pausa (por si falló la primera vez).
        if marcado is not None and marcado >= escalon_actual:
            with _del_proyecto(cliente):
                _pausar_si_activa(cliente, pz)
            _evento("%(nombre)s ya rescatada (escalón %(escalon)s); pieza pausada.",
                   nombre=pz["nombre"], escalon=marcado)
            return gettext("%(nombre)s ya rescatada (escalón %(escalon)s); pieza pausada.",
                           nombre=pz["nombre"], escalon=marcado)
        _exigir_saldo(cliente, ex, accion, payload)
        with _del_proyecto(cliente):
            derivaciones.planificar(cliente, experimento_id, "rescatar", payload)
        # planificar ya dejó `rescatado_en_escalon` (I-5); acá se refuerza
        # ANTES de pausar y sin bajar lo que ya haya: si Meta falla al
        # pausar, la marca existe y una re-ejecución (reintento de la
        # propuesta) no vuelve a planificar — solo reintenta la pausa.
        pz_post = _pieza(_experimento(cliente, experimento_id), pz["id"])
        escalon = max(int(pz_post.get("escalon_rescate") or 0), escalon_actual + 1,
                      int((pz_post.get("extra") or {}).get("rescatado_en_escalon") or 0))
        experimentos.marcar_pieza(cliente, pz["id"], rescatado_en_escalon=escalon)
        with _del_proyecto(cliente):
            _pausar_si_activa(cliente, pz)
        _evento("Rescate planificado para %(nombre)s (escalón %(escalon)s); la pieza queda pausada.",
               nombre=pz["nombre"], escalon=escalon)
        return gettext("Rescate planificado para %(nombre)s (escalón %(escalon)s); la pieza queda pausada.",
                       nombre=pz["nombre"], escalon=escalon)

    if accion == "activar":
        ep_ids = list(payload.get("ep_ids") or ([payload["ep_id"]] if payload.get("ep_id") else []))
        if not ep_ids:
            raise ValueError(gettext("No hay piezas para activar."))
        if ex["estado"] not in ("pausado", "corriendo", "decidido"):
            raise ValueError(gettext("El experimento todavía no está en Meta."))
        # I-1: nunca `cambiar_estado(ACTIVE)` del experimento entero desde
        # acá — reactivaría en Meta las piezas que el decisor ya retiró.
        # `activar_pieza` reactiva campaña y conjunto por su cuenta.
        with _del_proyecto(cliente):
            for ep_id in ep_ids:
                lanzador.activar_pieza(cliente, ep_id)
        _evento("Activadas %(n)s pieza(s).", n=len(ep_ids))
        return gettext("Activadas %(n)s pieza(s).", n=len(ep_ids))

    if accion == "archivar":
        pz = _pieza(ex, payload["ep_id"])
        if (pz.get("extra") or {}).get("archivado"):
            _evento("%(nombre)s ya archivada.", nombre=pz["nombre"])
            return gettext("%(nombre)s ya archivada.", nombre=pz["nombre"])
        with _del_proyecto(cliente):
            _pausar_si_activa(cliente, pz)
        for cf_id in _cadena_conceptos(cliente, payload.get("cf_id")):
            creative_flow.archivar_concepto(cliente, cf_id, motivo)
        experimentos.marcar_pieza(cliente, pz["id"], archivado=True)
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            # El fallback «sin motivo» se resuelve en el idioma del proyecto
            # ANTES de pasarlo a _evento: si se resolviera afuera, quedaría en
            # el idioma de quien mira y el evento guardado mezclaría idiomas.
            motivo_evento = motivo or gettext("sin motivo")
        _evento("Archivado el concepto de %(nombre)s: %(motivo)s.", nombre=pz["nombre"], motivo=motivo_evento)
        return gettext("Archivado el concepto de %(nombre)s: %(motivo)s.",
                       nombre=pz["nombre"], motivo=motivo or gettext("sin motivo"))

    if accion == "publicar_organico":
        return _publicar_organico(cliente, ex, payload, propuesta_id, ep_id_evento)

    raise ValueError(gettext("Acción desconocida: %(accion)s.", accion=repr(accion)))


def _nombres(plataformas):
    return ", ".join(idiomas.traducir(organico.PLATAFORMAS.get(p, {}).get("nombre", p)) for p in plataformas)


def _plataformas_pedidas(cliente, payload):
    """Las plataformas del payload (o todas) que HOY tienen canal disponible,
    en el orden de organico.ORDEN, y las pedidas que ya no lo tienen."""
    disponibles = organico.disponibles(cliente)
    pedidas = [p for p in (payload.get("plataformas") or disponibles) if p in organico.PLATAFORMAS]
    return ([p for p in organico.ORDEN if p in pedidas and p in disponibles],
            [p for p in pedidas if p not in disponibles])


def _captions_completos(cliente, pieza_id, plataformas, captions):
    """`captions` del payload (lo que la persona vio/editó) completado con
    organico.redactar SOLO para las plataformas sin texto, y TODO pasado por
    organico.normalizar_captions: el texto editado a mano también se recorta
    y se le quitan los enlaces donde no van (redactar ya lo hace con el
    suyo; sobre texto ya ajustado es idempotente)."""
    out = {p: dict(v) for p, v in (captions or {}).items() if isinstance(v, dict)}
    faltantes = [p for p in plataformas if not ((out.get(p) or {}).get("caption") or "").strip()]
    if faltantes:
        out.update(organico.redactar(cliente, pieza_id, faltantes))
    return organico.normalizar_captions(cliente, pieza_id, out)


def _publicar_organico(cliente, ex, payload, propuesta_id=None, ep_id_evento=None):
    """Crea una `publicacion` (origen ganador) por plataforma disponible y
    encola UNA tarea organico_publicar (max_intentos=1) con todas. Sin canal
    disponible no es error: mensaje y nada más. Las plataformas con
    publicación viva se saltan (unicidad) — repetir la acción no publica dos
    veces. Una pieza de imagen no aplica (organico/publicador son solo de
    video; su `url_video` ES la imagen): mensaje y nada más, como sin canal.
    `propuesta_id`/`ep_id_evento`: igual que en `ejecutar` — si vienen, deja
    el evento en la bitácora en el idioma del proyecto."""
    def _evento(armar_mensaje):
        # `armar_mensaje` es una función sin argumentos: _registrar_evento_aprobada
        # la llama DENTRO de idiomas.en_idioma(proyecto), así que cualquier
        # gettext/_nombres(...) que arme por dentro (incluidos los avisos
        # anidados de sin_canal/saltadas) sale en ese idioma, nunca en el de
        # quien mira — nunca se evalúa aquí afuera.
        _registrar_evento_aprobada(cliente, ex["id"], "publicar_organico", payload, propuesta_id, ep_id_evento,
                                   armar_mensaje)

    pz = _pieza(ex, payload["ep_id"])
    ep_id, pieza_id = pz["id"], pz.get("pieza_id")
    if not pieza_id or not pz.get("url_video"):
        raise ValueError(gettext("%(nombre)s no tiene video para publicar.", nombre=pz["nombre"]))
    if pz.get("es_imagen"):
        _evento(lambda: gettext("%(nombre)s: Las imágenes no se publican en orgánico todavía.", nombre=pz["nombre"]))
        return gettext("%(nombre)s: Las imágenes no se publican en orgánico todavía.", nombre=pz["nombre"])
    plataformas, sin_canal = _plataformas_pedidas(cliente, payload)
    aviso_sin_canal = (gettext(" Sin canal conectado: %(nombres)s.", nombres=_nombres(sin_canal))
                      if sin_canal else "")
    if not plataformas:
        _evento(lambda: gettext(
            "No hay canales orgánicos disponibles para publicar %(nombre)s.%(aviso)s", nombre=pz["nombre"],
            aviso=(gettext(" Sin canal conectado: %(nombres)s.", nombres=_nombres(sin_canal)) if sin_canal else "")))
        return gettext("No hay canales orgánicos disponibles para publicar %(nombre)s.%(aviso)s",
                       nombre=pz["nombre"], aviso=aviso_sin_canal)

    job_id = tareas_organico.job_id_publicar(cliente, pieza_id)
    if trabajos.en_curso(job_id):
        _evento(lambda: gettext("Ya hay una publicación orgánica de %(nombre)s en curso; no se vuelve a encolar.",
                                nombre=pz["nombre"]))
        return gettext("Ya hay una publicación orgánica de %(nombre)s en curso; no se vuelve a encolar.",
                       nombre=pz["nombre"])

    vivas = {pub["plataforma"] for pub in organico.listar(cliente, pieza_id=pieza_id)
             if pub["estado"] in organico.ESTADOS_VIVOS}
    nuevas = [p for p in plataformas if p not in vivas]
    saltadas = [p for p in plataformas if p in vivas]
    pub_ids, creadas = [], []
    if nuevas:
        captions = _captions_completos(cliente, pieza_id, nuevas, payload.get("captions"))
        for p in nuevas:
            t = captions.get(p) or {}
            try:
                pub_ids.append(organico.crear(cliente, pieza_id, p, t.get("caption"), titulo=t.get("titulo"),
                                              origen="ganador", ep_id=ep_id))
                creadas.append(p)
            except organico.YaPublicada:
                # Carrera con otra creación (índice único parcial): ya hay una viva.
                saltadas.append(p)
                continue
            except ValueError as error:
                # Creación parcial (mismo criterio que org_publicar): lo ya
                # creado no puede quedar `en_cola` sin tarea bloqueando la
                # plataforma por unicidad; en `error` se reintenta desde el panel.
                with _del_proyecto(cliente):             # se guarda: idioma del proyecto (I2)
                    for pub_id in pub_ids:
                        organico.actualizar(cliente, pub_id, estado="error",
                                            error=gettext("No se creó la publicación en %(plataformas)s: %(error)s",
                                                          plataformas=_nombres([p]), error=error))
                raise
    aviso_saltadas = (gettext(" Ya estaba publicada (o en cola) en %(nombres)s.", nombres=_nombres(saltadas))
                      if saltadas else "")
    if not pub_ids:
        _evento(lambda: gettext(
            "%(nombre)s no tiene nada nuevo que publicar.%(saltadas)s%(sin_canal)s", nombre=pz["nombre"],
            saltadas=(gettext(" Ya estaba publicada (o en cola) en %(nombres)s.", nombres=_nombres(saltadas)) if saltadas else ""),
            sin_canal=(gettext(" Sin canal conectado: %(nombres)s.", nombres=_nombres(sin_canal)) if sin_canal else "")))
        return gettext("%(nombre)s no tiene nada nuevo que publicar.%(saltadas)s%(sin_canal)s",
                       nombre=pz["nombre"], saltadas=aviso_saltadas, sin_canal=aviso_sin_canal)

    encolada = trabajos.encolar(job_id, "organico_publicar", {"cliente": cliente, "pub_ids": pub_ids},
                                cliente=cliente, duracion_estimada=tareas_organico.DURACION_PUBLICAR,
                                etapas=tareas_organico.ETAPAS_PUBLICAR, max_intentos=1)
    if not encolada:
        # Entre en_curso() y encolar() alguien encoló la misma pieza: las filas
        # nuevas no tienen tarea; en `error` la persona las reintenta desde el panel.
        with _del_proyecto(cliente):                     # se guarda: idioma del proyecto (I2)
            for pub_id in pub_ids:
                organico.actualizar(cliente, pub_id, estado="error",
                                    error=gettext("Ya había una publicación de esta pieza en curso; reintenta cuando "
                                                  "termine."))
        _evento(lambda: gettext(
            "Ya hay una publicación orgánica de %(nombre)s en curso; las nuevas quedaron para reintentar.",
            nombre=pz["nombre"]))
        return gettext("Ya hay una publicación orgánica de %(nombre)s en curso; las nuevas quedaron para reintentar.",
                       nombre=pz["nombre"])
    # M-1: la bandera solo cuenta lo que de verdad quedó encolado — nadie más
    # la lee hoy (la idempotencia real es la unicidad viva + trabajos.en_curso),
    # pero que mienta sería peor que no existir.
    experimentos.marcar_pieza(cliente, ep_id, publicado_organico=True)
    _evento(lambda: gettext(
        "Publicación orgánica de %(nombre)s en cola: %(creadas)s.%(saltadas)s%(sin_canal)s", nombre=pz["nombre"],
        creadas=_nombres(creadas),
        saltadas=(gettext(" Ya estaba publicada (o en cola) en %(nombres)s.", nombres=_nombres(saltadas)) if saltadas else ""),
        sin_canal=(gettext(" Sin canal conectado: %(nombres)s.", nombres=_nombres(sin_canal)) if sin_canal else "")))
    return gettext("Publicación orgánica de %(nombre)s en cola: %(creadas)s.%(saltadas)s%(sin_canal)s",
                   nombre=pz["nombre"], creadas=_nombres(creadas), saltadas=aviso_saltadas, sin_canal=aviso_sin_canal)


def _propuesta_organica_pendiente(cliente, experimento_id, payload):
    """M-2: True si ya hay una propuesta `publicar_organico` pendiente para
    el mismo ep_id. `propuestas.crear` ya dedupe por (ep_id, pais, pieza_id,
    ep_ids) y descarta el payload nuevo devolviendo la propuesta vieja — pero
    eso pasa DESPUÉS de pagar una llamada a Claude en
    `_completar_propuesta_organica`. Chequear acá evita ese gasto evitable."""
    return any(p["accion"] == "publicar_organico" and p["payload"].get("ep_id") == payload.get("ep_id")
               for p in propuestas.pendientes(cliente, experimento_id))


def _completar_propuesta_organica(cliente, ex, payload):
    """La propuesta `publicar_organico` lleva las plataformas disponibles y
    el texto ya redactado por plataforma, para que la persona lo lea/edite
    antes de aprobar. Si redactar falla (Claude caído y sin contexto), la
    propuesta igual se crea con `captions_error`: al aprobarla, ejecutar
    vuelve a redactar. Una pieza que no está en el experimento sí es error."""
    payload = dict(payload)
    pz = _pieza(ex, payload["ep_id"])
    try:
        plataformas, _ = _plataformas_pedidas(cliente, payload)
        payload["plataformas"] = plataformas
        if plataformas and pz.get("pieza_id"):
            captions = _captions_completos(cliente, pz["pieza_id"], plataformas, payload.get("captions"))
            payload["captions"] = {p: captions[p] for p in plataformas if p in captions}
    except Exception as error:  # noqa: BLE001 — la propuesta vale más que el texto previo
        payload["captions_error"] = cola.sin_token(str(error))
    return payload


def _precio_estimado(cliente, ex, accion, payload):
    """{"usd", "texto"} de lo que costaría producir lo que pide `derivar` o
    `rescatar`, con `gastos.estimar` (precio a la vista antes de aprobar):

    - derivar: n_reediciones × final (un país, multiplicado por país — I2:
      cada país produce su propia final, no hay descuento por país extra)
      + n_regeneraciones × (video + final); cada regeneración k (0, 1, …)
      se valora con el modelo que ESA regeneración va a usar de verdad
      (`derivaciones.modelo_regeneracion`, el mismo que elige
      `_item_regeneracion`) — nunca con el modelo de la pieza original, que
      normalmente ni siquiera es el que se repite (I1).
    - rescatar: por escalón (1 y 2 → una re-edición = final del país de la
      pieza; 3 → una regeneración, siempre k=0 igual que `_planificar_rescatar`).

    Nunca lanza: sin sesión/modelo conocidos el texto es «precio no
    disponible» (`usd` None). No bloquea nada: solo informa."""
    # `gastos.SIN_PRECIO` está marcado con N_ (no traducido): quien lo mira
    # (no el proyecto, ver global-constraints) recibe el texto en su idioma,
    # así que pasa por gettext acá — nunca crudo en el payload/JSON de vuelta.
    sin_precio = gettext(gastos.SIN_PRECIO)
    try:
        pz = _pieza(ex, payload.get("ep_id"))
        cf_id = derivaciones._cf_id_de(pz)
        sesion = creative_flow.cargar(cliente).get(cf_id) or {}
        n_paises = max(1, len(ex.get("paises") or []))
        reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex.get("reglas"))
        if accion == "derivar":
            n_re, n_rg = int(reglas.get("n_reediciones") or 0), int(reglas.get("n_regeneraciones") or 0)
        else:
            escalon = min(3, max(int(pz.get("escalon_rescate") or 0) + 1, int(payload.get("salto") or 0)))
            n_re, n_rg = (1, 0) if escalon in (1, 2) else (0, 1)
            n_paises = 1
        final_1 = gastos.estimar("final", paises=1)
        if final_1["usd"] is None:
            return {"usd": None, "texto": sin_precio}
        final = n_paises * final_1["usd"]
        usd = n_re * final
        duracion = sesion.get("duracion_objetivo")
        con_sonido = sesion.get("con_sonido", True) is not False
        for k in range(n_rg):
            modelo = derivaciones.modelo_regeneracion(sesion, k)
            video = gastos.estimar("video", modelo=modelo, duracion=duracion, con_sonido=con_sonido,
                                  musica_estilo=sesion.get("musica_estilo"))
            if video["usd"] is None:
                return {"usd": None, "texto": sin_precio}
            usd += video["usd"] + final
        return {"usd": round(usd, 4), "texto": gastos.texto_precio(usd)}
    except Exception:  # noqa: BLE001 — el precio es informativo, nunca bloquea la acción
        return {"usd": None, "texto": sin_precio}


def _exigir_saldo(cliente, ex, accion, payload):
    """Cobros (spec 2026-10-08 §5): derivar y rescatar producen (clon y
    finales). El saldo se pide ANTES de `planificar`, que crea el experimento
    hijo y marca la pieza (`derivado`, `rescatado_en_escalon`): sin saldo no
    se gasta la única derivación ni el escalón; lanza SaldoInsuficiente."""
    libro.exigir(cliente, _precio_estimado(cliente, ex, accion, payload)["usd"])


def pedir(cliente, experimento_id, accion, payload, motivo):
    """Puerta del decisor. Devuelve ("ejecutada", mensaje) o
    ("propuesta", mensaje) según el modo del experimento y el tope; en ambos
    casos queda un evento (tipo `accion` o `propuesta`). Para derivar y
    rescatar deja en `payload["precio_estimado"]` lo que costaría producir
    (se muestra en la propuesta)."""
    payload = dict(payload or {})
    payload.setdefault("motivo", motivo)
    ex = _experimento(cliente, experimento_id)
    if accion in ("derivar", "rescatar") and ex.get("objetivo_meta") == "OUTCOME_APP_PROMOTION":
        # Spec 2026-10-07: en instalaciones de la app cada pieza tiene una fila por
        # plataforma; una pieza derivada nacería sin plataforma y el lanzador no
        # sabría ubicarla. Ganadora: solo escala; perdedora: ya se pidió pausar.
        mensaje = gettext("Derivar y rescatar no están disponibles en experimentos de instalaciones de la app.")
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            guardado = gettext("Derivar y rescatar no están disponibles en experimentos de instalaciones de la app.")
        experimentos.registrar_evento(cliente, experimento_id, "accion", guardado,
                                      datos={"accion": accion, "payload": payload, "modo": ex["modo"]},
                                      ep_id=payload.get("ep_id"))
        return "omitida", mensaje
    if accion in ("derivar", "rescatar") and "precio_estimado" not in payload:
        payload["precio_estimado"] = _precio_estimado(cliente, ex, accion, payload)
    puerta = modos.resolver(ex["modo"], accion)
    motivo_prop = motivo
    if accion in _ACCIONES_CON_GASTO and tope_alcanzado(ex):
        puerta = "propuesta"
        motivo_prop = gettext(
            "tope alcanzado (%(gasto)s de %(tope)s %(moneda)s); %(motivo)s",
            gasto=f"{ex.get('gasto_acumulado'):g}", tope=f"{ex.get('tope_total'):g}",
            moneda=ex.get("moneda") or "", motivo=motivo).strip()
    elif accion == "derivar" and experimentos.profundidad(ex) >= PROFUNDIDAD_MAXIMA:
        # I-9: a partir de la generación N un ganador ya no deriva solo (en
        # auto la cadena hijo → nieto → … no tendría freno); la persona
        # decide si abrir otra generación.
        puerta = "propuesta"
        motivo_prop = gettext(
            "profundidad máxima (%(n)s generaciones de derivación); %(motivo)s",
            n=experimentos.profundidad(ex), motivo=motivo).strip()
    if payload.get("solo_proponer") and puerta != "propuesta":
        # Doctrina, bloque 4 (§4): el diagnóstico apunta a algo que no es el
        # creativo (landing, oferta, estación): una persona decide, en todo modo.
        # (Si ya era propuesta por tope o profundidad, ese motivo se queda: ya
        # lleva el diagnóstico dentro.)
        puerta = "propuesta"
        motivo_prop = motivo
    ep_id = payload.get("ep_id")
    datos = {"accion": accion, "payload": payload, "modo": ex["modo"]}

    if puerta == "ejecutar":
        try:
            mensaje = ejecutar(cliente, experimento_id, accion, payload)
        except SaldoInsuficiente as e:
            # Modo automático sin saldo (cobros §5.4): no se consumió nada
            # (`_exigir_saldo` va antes de planificar); queda como propuesta
            # para que una persona la apruebe después de recargar.
            mensaje = None
            motivo_prop = f"{e.frase_proyecto()} {motivo}".strip()
        except Exception as error:
            experimentos.registrar_evento(cliente, experimento_id, "error",
                                          cola.sin_token(str(error)), datos=datos, ep_id=ep_id)
            raise
        if mensaje is not None:
            experimentos.registrar_evento(cliente, experimento_id, "accion",
                                          gettext("%(mensaje)s Motivo: %(motivo)s.", mensaje=mensaje, motivo=motivo),
                                          datos=datos, ep_id=ep_id)
            return "ejecutada", mensaje

    if accion == "publicar_organico" and not _propuesta_organica_pendiente(cliente, experimento_id, payload):
        payload = _completar_propuesta_organica(cliente, ex, payload)
    pid = propuestas.crear(cliente, experimento_id, accion, payload, motivo_prop)
    mensaje = gettext("Propuesta pendiente: %(accion)s (%(motivo)s).", accion=accion, motivo=motivo_prop)
    experimentos.registrar_evento(cliente, experimento_id, "propuesta", mensaje,
                                  datos={**datos, "propuesta_id": pid}, ep_id=ep_id)
    return "propuesta", mensaje

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
import cola
import creative_flow
import decisor
import derivaciones
import experimentos
import gastos
import lanzador
import modos
import organico
import propuestas
import proyectos
import trabajos
from tareas import organico as tareas_organico

# Acciones que pueden aumentar el gasto: chequean el tope antes de ejecutarse.
_ACCIONES_CON_GASTO = ("escalar", "activar", "derivar")
# Generaciones de derivación (extra.profundidad) a partir de las cuales
# "derivar" siempre queda como propuesta, sea cual sea el modo (I-9).
PROFUNDIDAD_MAXIMA = 2


def _experimento(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError("Ese experimento no existe.")
    return ex


def _pieza(ex, ep_id):
    pz = next((p for p in ex["piezas"] if p["id"] == ep_id), None)
    if pz is None:
        raise ValueError("Esa pieza no está en el experimento.")
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


def ejecutar(cliente, experimento_id, accion, payload):
    """Ejecuta la acción y devuelve un mensaje corto (en español) de lo que
    pasó. Lanza ValueError si la acción no existe o faltan datos."""
    payload = payload or {}
    ex = _experimento(cliente, experimento_id)
    motivo = payload.get("motivo") or ""

    if accion == "pausar":
        pz = _pieza(ex, payload["ep_id"])
        lanzador.pausar_pieza(cliente, pz["id"])
        return f"Pausada {pz['nombre']} ({pz['pais']})."

    if accion == "escalar":
        pais = payload["pais"]
        reglas = reglas_de(cliente, ex)
        nuevo = lanzador.escalar_pais(cliente, experimento_id, pais, reglas["escalar_pct_dia"], reglas["escalar_tope_dia"])
        return f"Presupuesto de {pais} escalado a {nuevo:g} {ex.get('moneda') or ''} por día."

    if accion == "derivar":
        pz = _pieza(ex, payload["ep_id"])
        if (pz.get("extra") or {}).get("derivado"):
            return f"{pz['nombre']} ya derivada: no se vuelve a producir."
        hijo = derivaciones.planificar(cliente, experimento_id, "derivar", payload)
        # planificar ya marcó `derivado`; repetirlo es inocuo (misma bandera).
        experimentos.marcar_pieza(cliente, pz["id"], derivado=True)
        return f"Derivación planificada a partir de {pz['nombre']} (experimento hijo {hijo})."

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
            _pausar_si_activa(cliente, pz)
            return f"{pz['nombre']} ya rescatada (escalón {marcado}); pieza pausada."
        derivaciones.planificar(cliente, experimento_id, "rescatar", payload)
        # planificar ya dejó `rescatado_en_escalon` (I-5); acá se refuerza
        # ANTES de pausar y sin bajar lo que ya haya: si Meta falla al
        # pausar, la marca existe y una re-ejecución (reintento de la
        # propuesta) no vuelve a planificar — solo reintenta la pausa.
        pz_post = _pieza(_experimento(cliente, experimento_id), pz["id"])
        escalon = max(int(pz_post.get("escalon_rescate") or 0), escalon_actual + 1,
                      int((pz_post.get("extra") or {}).get("rescatado_en_escalon") or 0))
        experimentos.marcar_pieza(cliente, pz["id"], rescatado_en_escalon=escalon)
        _pausar_si_activa(cliente, pz)
        return f"Rescate planificado para {pz['nombre']} (escalón {escalon}); la pieza queda pausada."

    if accion == "activar":
        ep_ids = list(payload.get("ep_ids") or ([payload["ep_id"]] if payload.get("ep_id") else []))
        if not ep_ids:
            raise ValueError("No hay piezas para activar.")
        if ex["estado"] not in ("pausado", "corriendo", "decidido"):
            raise ValueError("El experimento todavía no está en Meta.")
        # I-1: nunca `cambiar_estado(ACTIVE)` del experimento entero desde
        # acá — reactivaría en Meta las piezas que el decisor ya retiró.
        # `activar_pieza` reactiva campaña y conjunto por su cuenta.
        for ep_id in ep_ids:
            lanzador.activar_pieza(cliente, ep_id)
        return f"Activadas {len(ep_ids)} pieza(s)."

    if accion == "archivar":
        pz = _pieza(ex, payload["ep_id"])
        if (pz.get("extra") or {}).get("archivado"):
            return f"{pz['nombre']} ya archivada."
        _pausar_si_activa(cliente, pz)
        for cf_id in _cadena_conceptos(cliente, payload.get("cf_id")):
            creative_flow.archivar_concepto(cliente, cf_id, motivo)
        experimentos.marcar_pieza(cliente, pz["id"], archivado=True)
        return f"Archivado el concepto de {pz['nombre']}: {motivo or 'sin motivo'}."

    if accion == "publicar_organico":
        return _publicar_organico(cliente, ex, payload)

    raise ValueError(f"Acción desconocida: {accion!r}.")


def _nombres(plataformas):
    return ", ".join(organico.PLATAFORMAS.get(p, {}).get("nombre", p) for p in plataformas)


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


def _publicar_organico(cliente, ex, payload):
    """Crea una `publicacion` (origen ganador) por plataforma disponible y
    encola UNA tarea organico_publicar (max_intentos=1) con todas. Sin canal
    disponible no es error: mensaje y nada más. Las plataformas con
    publicación viva se saltan (unicidad) — repetir la acción no publica dos
    veces. Una pieza de imagen no aplica (organico/publicador son solo de
    video; su `url_video` ES la imagen): mensaje y nada más, como sin canal."""
    pz = _pieza(ex, payload["ep_id"])
    ep_id, pieza_id = pz["id"], pz.get("pieza_id")
    if not pieza_id or not pz.get("url_video"):
        raise ValueError(f"{pz['nombre']} no tiene video para publicar.")
    if pz.get("es_imagen"):
        return f"{pz['nombre']}: Las imágenes no se publican en orgánico todavía."
    plataformas, sin_canal = _plataformas_pedidas(cliente, payload)
    aviso_sin_canal = f" Sin canal conectado: {_nombres(sin_canal)}." if sin_canal else ""
    if not plataformas:
        return f"No hay canales orgánicos disponibles para publicar {pz['nombre']}.{aviso_sin_canal}"

    job_id = tareas_organico.job_id_publicar(cliente, pieza_id)
    if trabajos.en_curso(job_id):
        return f"Ya hay una publicación orgánica de {pz['nombre']} en curso; no se vuelve a encolar."

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
            except ValueError as error:
                # Carrera con otra creación (índice único parcial): ya hay una viva.
                if "ya está publicada" in str(error):
                    saltadas.append(p)
                    continue
                # Creación parcial (mismo criterio que org_publicar): lo ya
                # creado no puede quedar `en_cola` sin tarea bloqueando la
                # plataforma por unicidad; en `error` se reintenta desde el panel.
                for pub_id in pub_ids:
                    organico.actualizar(cliente, pub_id, estado="error",
                                        error=f"No se creó la publicación en {_nombres([p])}: {error}")
                raise
    aviso_saltadas = f" Ya estaba publicada (o en cola) en {_nombres(saltadas)}." if saltadas else ""
    if not pub_ids:
        return f"{pz['nombre']} no tiene nada nuevo que publicar.{aviso_saltadas}{aviso_sin_canal}"

    encolada = trabajos.encolar(job_id, "organico_publicar", {"cliente": cliente, "pub_ids": pub_ids},
                                cliente=cliente, duracion_estimada=tareas_organico.DURACION_PUBLICAR,
                                etapas=tareas_organico.ETAPAS_PUBLICAR, max_intentos=1)
    if not encolada:
        # Entre en_curso() y encolar() alguien encoló la misma pieza: las filas
        # nuevas no tienen tarea; en `error` la persona las reintenta desde el panel.
        for pub_id in pub_ids:
            organico.actualizar(cliente, pub_id, estado="error",
                                error="Ya había una publicación de esta pieza en curso; reintenta cuando termine.")
        return f"Ya hay una publicación orgánica de {pz['nombre']} en curso; las nuevas quedaron para reintentar."
    # M-1: la bandera solo cuenta lo que de verdad quedó encolado — nadie más
    # la lee hoy (la idempotencia real es la unicidad viva + trabajos.en_curso),
    # pero que mienta sería peor que no existir.
    experimentos.marcar_pieza(cliente, ep_id, publicado_organico=True)
    return (f"Publicación orgánica de {pz['nombre']} en cola: {_nombres(creadas)}.{aviso_saltadas}{aviso_sin_canal}")


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
    try:
        pz = _pieza(ex, payload.get("ep_id"))
        cf_id = derivaciones._cf_id_de(pz)
        sesion = creative_flow.cargar(cliente).get(cf_id) or {}
        n_paises = max(1, len(ex.get("paises") or []))
        reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex.get("reglas"))
        if accion == "derivar":
            n_re, n_rg = int(reglas.get("n_reediciones") or 0), int(reglas.get("n_regeneraciones") or 0)
        else:
            escalon = int(pz.get("escalon_rescate") or 0) + 1
            n_re, n_rg = (1, 0) if escalon in (1, 2) else (0, 1)
            n_paises = 1
        final_1 = gastos.estimar("final", paises=1)
        if final_1["usd"] is None:
            return {"usd": None, "texto": gastos.SIN_PRECIO}
        final = n_paises * final_1["usd"]
        usd = n_re * final
        duracion = sesion.get("duracion_objetivo")
        con_sonido = sesion.get("con_sonido", True) is not False
        for k in range(n_rg):
            modelo = derivaciones.modelo_regeneracion(sesion, k)
            video = gastos.estimar("video", modelo=modelo, duracion=duracion, con_sonido=con_sonido)
            if video["usd"] is None:
                return {"usd": None, "texto": gastos.SIN_PRECIO}
            usd += video["usd"] + final
        return {"usd": round(usd, 4), "texto": f"{gastos.formatear(usd)} aprox."}
    except Exception:  # noqa: BLE001 — el precio es informativo, nunca bloquea la acción
        return {"usd": None, "texto": gastos.SIN_PRECIO}


def pedir(cliente, experimento_id, accion, payload, motivo):
    """Puerta del decisor. Devuelve ("ejecutada", mensaje) o
    ("propuesta", mensaje) según el modo del experimento y el tope; en ambos
    casos queda un evento (tipo `accion` o `propuesta`). Para derivar y
    rescatar deja en `payload["precio_estimado"]` lo que costaría producir
    (se muestra en la propuesta)."""
    payload = dict(payload or {})
    payload.setdefault("motivo", motivo)
    ex = _experimento(cliente, experimento_id)
    if accion in ("derivar", "rescatar") and "precio_estimado" not in payload:
        payload["precio_estimado"] = _precio_estimado(cliente, ex, accion, payload)
    puerta = modos.resolver(ex["modo"], accion)
    motivo_prop = motivo
    if accion in _ACCIONES_CON_GASTO and tope_alcanzado(ex):
        puerta = "propuesta"
        motivo_prop = f"tope alcanzado ({ex.get('gasto_acumulado'):g} de {ex.get('tope_total'):g} {ex.get('moneda') or ''}); {motivo}".strip()
    elif accion == "derivar" and experimentos.profundidad(ex) >= PROFUNDIDAD_MAXIMA:
        # I-9: a partir de la generación N un ganador ya no deriva solo (en
        # auto la cadena hijo → nieto → … no tendría freno); la persona
        # decide si abrir otra generación.
        puerta = "propuesta"
        motivo_prop = f"profundidad máxima ({experimentos.profundidad(ex)} generaciones de derivación); {motivo}".strip()
    ep_id = payload.get("ep_id")
    datos = {"accion": accion, "payload": payload, "modo": ex["modo"]}

    if puerta == "ejecutar":
        try:
            mensaje = ejecutar(cliente, experimento_id, accion, payload)
        except Exception as error:
            experimentos.registrar_evento(cliente, experimento_id, "error",
                                          cola.sin_token(str(error)), datos=datos, ep_id=ep_id)
            raise
        experimentos.registrar_evento(cliente, experimento_id, "accion",
                                      f"{mensaje} Motivo: {motivo}.", datos=datos, ep_id=ep_id)
        return "ejecutada", mensaje

    if accion == "publicar_organico" and not _propuesta_organica_pendiente(cliente, experimento_id, payload):
        payload = _completar_propuesta_organica(cliente, ex, payload)
    pid = propuestas.crear(cliente, experimento_id, accion, payload, motivo_prop)
    mensaje = f"Propuesta pendiente: {accion} ({motivo_prop})."
    experimentos.registrar_evento(cliente, experimento_id, "propuesta", mensaje,
                                  datos={**datos, "propuesta_id": pid}, ep_id=ep_id)
    return "propuesta", mensaje

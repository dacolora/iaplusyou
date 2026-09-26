"""
Datos de los sprints de contenido (Parte 1 del spec): personas, temporadas,
sprints, campañas, referencias y eventos. Solo SQLAlchemy Core sobre
data/creatv.db; nada de proveedores ni de Flask. Las validaciones de negocio
(fechas, cantidades, unicidad) viven aquí; la validación contra el catálogo
de productos la hace la ruta, para que este módulo se pruebe sin carpetas de
clientes.
"""
import re
import time
from datetime import date

import sqlalchemy as sa

import db
from referentes import datos as referentes_datos

# Un color CSS hexadecimal (#rgb, #rrggbb, #rrggbbaa…). Todo lo que se pinta con
# style="background: …" en las plantillas pasa por aquí antes de guardarse.
COLOR_HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")

INTENCIONES = ("estilo_visual", "composicion", "paleta", "movimiento_camara", "tipografia",
               "transiciones", "storytelling", "iluminacion", "angulo_producto", "formato", "otro")
INTENCIONES_NOMBRE = {
    "estilo_visual": "Estilo visual", "composicion": "Composición", "paleta": "Paleta de colores",
    "movimiento_camara": "Movimiento de cámara", "tipografia": "Tipografía", "transiciones": "Transiciones",
    "storytelling": "Storytelling", "iluminacion": "Iluminación", "angulo_producto": "Ángulo de producto",
    "formato": "Formato", "otro": "Otro",
}
ESTADOS_SPRINT = ("planeando", "referencias", "listo_para_generar", "generando", "revision", "completado")
ESTADOS_CAMPANA = ("planeada", "referencias", "ideas_propuestas", "ideas_aprobadas", "generando", "revision", "completada")
TIPOS_TEMPORADA = ("comercial", "estacional", "propia")
ORIGENES_REFERENCIA = ("archivo", "link", "catalogo", "reutilizada", "biblioteca")
ORIGENES_PERSONA = ("manual", "sugerida_ia", "investigada")
TIPOS_PIEZA = ("video", "imagen")
ESTADOS_IDEA = ("propuesta", "aprobada", "descartada")
REVISIONES = ("pendiente", "aprobada", "rechazada")
PLATAFORMAS = ("instagram", "tiktok", "facebook", "youtube")
FUNNELS = ("tof", "mof", "bof")
FUNNELS_NOMBRE = {"tof": "Top of Funnel", "mof": "Middle of Funnel", "bof": "Bottom of Funnel"}

PERSONAJES_PREDETERMINADOS = [
    {
        "nombre": "Melissa",
        "resumen": "Thoughtful Giver",
        "descripcion": "30-50 años, principalmente mujeres (70%), viviendo en áreas suburbanas o urbanas. Buscan equilibrar familia, trabajo y vida social.",
        "edad_rango": "30-50",
        "tono": "Thoughtful, caring, reliable",
        "senales_visuales": ["Comfort", "Practical", "Warm"],
        "palabras_clave": ["Thoughtful gifts", "comfort", "personal", "genuine"],
        "color": "#6C5CE7",
        "origen": "manual",
    },
    {
        "nombre": "Marijke",
        "resumen": "Graceful Ageless",
        "descripcion": "Mujer de 60-75 años, jubilada o semi-jubilada, viviendo en área tranquila suburbana o rural. Activa a través de jardinería, caminatas y tiempo con familia.",
        "edad_rango": "60-75",
        "tono": "Stylish, independent, graceful",
        "senales_visuales": ["Elegant", "Quality", "Timeless"],
        "palabras_clave": ["Comfort", "style", "independence", "quality"],
        "color": "#00B894",
        "origen": "manual",
    },
    {
        "nombre": "Sophia",
        "resumen": "Busy Mom",
        "descripcion": "Mujer de 32-45 años viviendo en vecindario suburbano, balanceando trabajo de tiempo completo o parcial con vida familiar. Constantemente en movimiento cuidando a sus hijos.",
        "edad_rango": "32-45",
        "tono": "Reliable, composed, nurturing, capable",
        "senales_visuales": ["Practical", "Comfortable", "Strong"],
        "palabras_clave": ["Reliable", "comfort", "support", "practical"],
        "color": "#FDCB6E",
        "origen": "manual",
    },
]

_PERSONA_COLS = ("nombre", "resumen", "descripcion", "edad_rango", "tono", "senales_visuales", "palabras_clave",
                 "color", "origen", "archivada", "extra")
_TEMPORADA_COLS = ("nombre", "inicio", "fin", "contexto", "mood_visual", "tipo", "archivada", "extra")
_SPRINT_COLS = ("nombre", "inicio", "fin", "estado", "destinos", "referencias_objetivo_defecto", "notas",
                "archivado", "extra")
_CAMPANA_COLS = ("n_videos", "n_imagenes", "referencias_objetivo", "estado", "orden", "extra", "producto_id", "funnel")
_REFERENCIA_COLS = ("titulo", "intencion", "intencion_otro", "descripcion", "analisis", "analisis_estado", "orden",
                    "extra", "frame_url", "ruta_local")
_IDEA_COLS = ("titulo", "escena", "sonido", "enfoque", "gancho", "referencias_ids", "duracion_s", "plataformas",
              "estado_idea", "cf_id", "qa", "revision", "revision_motivo", "textos", "orden", "extra")
_PIEZA_TERMINADA = ("listo", "degradada")

# Reserva de una idea antes de crear su sesión de Crear (produccion.lanzar_lote):
# `campana_pieza.cf_id` guarda el placeholder "reservando_<cp_id>_<epoch>" hasta
# que el vínculo real lo reemplaza. Si el proceso muere en medio, la reserva
# vence a los RESERVA_TTL_S y la idea vuelve a contar como aprobada sin sesión.
RESERVA_PREFIJO = "reservando_"
RESERVA_TTL_S = 600


def reserva_placeholder(cp_id, ahora=None):
    return f"{RESERVA_PREFIJO}{int(cp_id)}_{int(ahora if ahora is not None else time.time())}"


def es_reserva(cf_id):
    return isinstance(cf_id, str) and cf_id.startswith(RESERVA_PREFIJO)


def reserva_vencida(cf_id, ahora=None):
    """True si `cf_id` es una reserva más vieja que RESERVA_TTL_S. El formato
    viejo sin hora ("reservando_<cp>") y una hora ilegible cuentan como
    vencidas. Un cf_id real (o None) nunca está vencido: no es reserva."""
    if not es_reserva(cf_id):
        return False
    partes = cf_id[len(RESERVA_PREFIJO):].split("_")
    if len(partes) < 2:
        return True
    try:
        creada = int(partes[-1])
    except ValueError:
        return True
    return (ahora if ahora is not None else time.time()) - creada > RESERVA_TTL_S


class ErrorDatos(ValueError):
    """Dato inválido; el mensaje se muestra tal cual a la persona."""


class CampanaDuplicada(ErrorDatos):
    """Ya hay una campaña con esa persona, producto y temporada en el sprint."""


# ------------------------------------------------------------ helpers ---

def _fecha(valor, campo):
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        raise ErrorDatos(f"La fecha de {campo} no es válida (usa AAAA-MM-DD).")


def _rango(inicio, fin, que):
    i, f = _fecha(inicio, "inicio"), _fecha(fin, "fin")
    if i >= f:
        raise ErrorDatos(f"En {que}, la fecha de inicio debe ser anterior a la de fin.")
    return i.isoformat(), f.isoformat()


def _a_dict(fila):
    return dict(fila._mapping)


def _fila(con, tabla, fila_id, cliente):
    return con.execute(sa.select(tabla).where(tabla.c.id == fila_id, tabla.c.cliente == cliente)).first()


def _actualizar(con, tabla, fila_id, cliente, permitidas, campos):
    malos = set(campos) - set(permitidas)
    if malos:
        raise ErrorDatos(f"Campos no editables: {', '.join(sorted(malos))}")
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), **campos))
    return r.rowcount == 1


def _bloquear(con, tabla, fila_id, cliente):
    """Toma el lock de escritura de SQLite ANTES de leer (semántica de
    `BEGIN IMMEDIATE`), igual que `experimentos._bloquear`: un UPDATE sin
    efecto sobre la fila objetivo obliga al driver a abrir la transacción y
    tomar el lock ya, así el SELECT que sigue dentro de la misma transacción
    ve lo que dejó el último escritor en vez de perder su actualización
    (lost update: gunicorn y el worker leen y escriben `extra` a la vez).
    Devuelve True si la fila existe."""
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=tabla.c.actualizado_en))
    return r.rowcount == 1


def _texto(v, largo=None):
    v = (v or "").strip()
    return v[:largo] if largo else v


def _color(v):
    """None/"" -> None; hexadecimal válido -> tal cual; otra cosa -> ErrorDatos."""
    v = (v or "").strip() if isinstance(v, str) else v
    if not v:
        return None
    if not isinstance(v, str) or not COLOR_HEX.match(v):
        raise ErrorDatos("El color debe ser hexadecimal, como #4d8dff.")
    return v


def _mood(mood_visual):
    """Copia del mood con la paleta filtrada a colores hexadecimales (lo que
    no cumple se descarta en silencio: viene de un campo libre o de Claude)."""
    m = dict(mood_visual or {})
    if "paleta" in m:
        m["paleta"] = [c for c in (m.get("paleta") or []) if isinstance(c, str) and COLOR_HEX.match(c)]
    return m


# ----------------------------------------------------------- personas ---

def crear_persona(cliente, nombre, resumen="", descripcion="", edad_rango="", tono="", senales_visuales=None,
                  palabras_clave=None, color=None, origen="manual", extra=None):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("La persona necesita un nombre.")
    if origen not in ORIGENES_PERSONA:
        raise ErrorDatos(f"Origen de persona inválido: {origen}. Opciones: {ORIGENES_PERSONA}")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.persona.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, resumen=_texto(resumen, 200),
            descripcion=_texto(descripcion), edad_rango=_texto(edad_rango, 20), tono=_texto(tono),
            senales_visuales=list(senales_visuales or []), palabras_clave=list(palabras_clave or []),
            color=_color(color), origen=origen, archivada=False,
            extra=dict(extra) if isinstance(extra, dict) else {})).inserted_primary_key[0]


def actualizar_persona(cliente, persona_id, /, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("La persona necesita un nombre.")
    if "origen" in campos and campos["origen"] not in ORIGENES_PERSONA:
        raise ErrorDatos(f"Origen de persona inválido: {campos['origen']}")
    if "color" in campos:
        campos["color"] = _color(campos["color"])
    with db.conectar() as con:
        return _actualizar(con, db.persona, persona_id, cliente, _PERSONA_COLS, campos)


def archivar_persona(cliente, persona_id, archivada=True):
    return actualizar_persona(cliente, persona_id, archivada=bool(archivada))


def personas(cliente, incluir_archivadas=False):
    p = db.persona
    q = sa.select(p).where(p.c.cliente == cliente)
    if not incluir_archivadas:
        q = q.where(p.c.archivada.is_(False))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q.order_by(p.c.nombre))]


def persona(cliente, persona_id):
    with db.conectar() as con:
        f = _fila(con, db.persona, persona_id, cliente)
    return _a_dict(f) if f else None


def asegurar_personajes_predeterminados(cliente):
    """Crea los 3 personajes predeterminados (Melissa, Marijke, Sophia) si no existen ya."""
    with db.conectar() as con:
        p = db.persona
        for pd in PERSONAJES_PREDETERMINADOS:
            existente = con.execute(sa.select(p.c.id).where(
                p.c.cliente == cliente, p.c.nombre == pd["nombre"])).scalar()
            if not existente:
                ahora = db.ahora()
                con.execute(p.insert().values(
                    cliente=cliente, creado_en=ahora, actualizado_en=ahora,
                    nombre=pd["nombre"], resumen=pd["resumen"], descripcion=pd["descripcion"],
                    edad_rango=pd["edad_rango"], tono=pd["tono"],
                    senales_visuales=pd["senales_visuales"], palabras_clave=pd["palabras_clave"],
                    color=pd["color"], origen=pd["origen"], archivada=False, extra={}))


# --------------------------------------------------------- temporadas ---

def crear_temporada(cliente, nombre, inicio, fin, contexto="", mood_visual=None, tipo="propia"):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("La temporada necesita un nombre.")
    if tipo not in TIPOS_TEMPORADA:
        raise ErrorDatos(f"Tipo de temporada inválido: {tipo}. Opciones: {TIPOS_TEMPORADA}")
    inicio, fin = _rango(inicio, fin, "la temporada")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.temporada.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, inicio=inicio, fin=fin,
            contexto=_texto(contexto), mood_visual=_mood(mood_visual), tipo=tipo, archivada=False,
            extra={})).inserted_primary_key[0]


def actualizar_temporada(cliente, temporada_id, /, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("La temporada necesita un nombre.")
    if "tipo" in campos and campos["tipo"] not in TIPOS_TEMPORADA:
        raise ErrorDatos(f"Tipo de temporada inválido: {campos['tipo']}")
    if "mood_visual" in campos:
        campos["mood_visual"] = _mood(campos["mood_visual"])
    if "inicio" in campos or "fin" in campos:
        actual = temporada(cliente, temporada_id) or {}
        campos["inicio"], campos["fin"] = _rango(campos.get("inicio", actual.get("inicio")),
                                                 campos.get("fin", actual.get("fin")), "la temporada")
    with db.conectar() as con:
        return _actualizar(con, db.temporada, temporada_id, cliente, _TEMPORADA_COLS, campos)


def archivar_temporada(cliente, temporada_id, archivada=True):
    return actualizar_temporada(cliente, temporada_id, archivada=bool(archivada))


def temporadas(cliente, incluir_archivadas=False):
    t = db.temporada
    q = sa.select(t).where(t.c.cliente == cliente)
    if not incluir_archivadas:
        q = q.where(t.c.archivada.is_(False))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q.order_by(t.c.inicio, t.c.nombre))]


def temporada(cliente, temporada_id):
    with db.conectar() as con:
        f = _fila(con, db.temporada, temporada_id, cliente)
    return _a_dict(f) if f else None


# ------------------------------------------------------------ eventos ---

def _evento(con, cliente, sprint_id, campana_id, tipo, mensaje, datos_=None):
    return con.execute(db.sprint_evento.insert().values(
        cliente=cliente, sprint_id=sprint_id, campana_id=campana_id, tipo=tipo, mensaje=mensaje,
        datos=datos_ or {}, creado_en=db.ahora())).inserted_primary_key[0]


def registrar_evento(cliente, sprint_id, tipo, mensaje, datos=None, campana_id=None):
    with db.conectar() as con:
        return _evento(con, cliente, sprint_id, campana_id, tipo, mensaje, datos)


def _eventos(con, cliente, sprint_id, limite):
    e = db.sprint_evento
    q = sa.select(e).where(e.c.cliente == cliente, e.c.sprint_id == sprint_id).order_by(e.c.id.desc())
    if limite:
        q = q.limit(limite)
    return [_a_dict(f) for f in con.execute(q)]


def eventos(cliente, sprint_id, limite=50):
    with db.conectar() as con:
        return _eventos(con, cliente, sprint_id, limite)


# ------------------------------------------------------------ sprints ---

def crear_sprint(cliente, nombre, inicio, fin, destinos=None, referencias_objetivo_defecto=5, notas=""):
    nombre = _texto(nombre, 200)
    if not nombre:
        raise ErrorDatos("El sprint necesita un nombre.")
    inicio, fin = _rango(inicio, fin, "el sprint")
    try:
        objetivo = int(referencias_objetivo_defecto if referencias_objetivo_defecto is not None else 5)
    except (TypeError, ValueError):
        raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
    if objetivo < 1:
        raise ErrorDatos("El objetivo de referencias debe ser al menos 1.")
    ahora = db.ahora()
    with db.conectar() as con:
        sid = con.execute(db.sprint.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, inicio=inicio, fin=fin,
            estado="planeando", destinos=list(destinos or []), referencias_objetivo_defecto=objetivo,
            notas=_texto(notas), archivado=False, extra={})).inserted_primary_key[0]
        _evento(con, cliente, sid, None, "sprint_creado", f"Sprint «{nombre}» creado", {"inicio": inicio, "fin": fin})
    return sid


def actualizar_sprint(cliente, sprint_id, /, **campos):
    if "estado" in campos and campos["estado"] not in ESTADOS_SPRINT:
        raise ErrorDatos(f"Estado de sprint inválido: {campos['estado']}")
    if "inicio" in campos or "fin" in campos:
        actual = sprint(cliente, sprint_id, con_eventos=False) or {}
        campos["inicio"], campos["fin"] = _rango(campos.get("inicio", actual.get("inicio")),
                                                 campos.get("fin", actual.get("fin")), "el sprint")
    with db.conectar() as con:
        return _actualizar(con, db.sprint, sprint_id, cliente, _SPRINT_COLS, campos)


def archivar_sprint(cliente, sprint_id, archivado=True):
    return actualizar_sprint(cliente, sprint_id, archivado=bool(archivado))


def actualizar_extra_sprint(cliente, sprint_id, fn):
    """Read-modify-write atómico de `sprint.extra`: toma el lock de escritura
    (`_bloquear`) antes de leer, todo en UNA transacción, igual que
    `experimentos.actualizar_extra`. Dos lotes (`produccion.lanzar_lote`) o una
    regeneración corriendo a la vez sobre el mismo sprint ya no se pisan el
    `costo_estimado_usd` acumulado ni `lote_en_curso`: cada llamada ve el
    `extra` que dejó la anterior, no una foto vieja. `fn(extra) -> extra`.
    Devuelve el `extra` escrito, o None si el sprint no existe."""
    with db.conectar() as con:
        if not _bloquear(con, db.sprint, sprint_id, cliente):
            return None
        f = _fila(con, db.sprint, sprint_id, cliente)
        if not f:
            return None
        extra = fn(dict(f.extra or {}))
        con.execute(db.sprint.update().where(db.sprint.c.id == sprint_id)
                    .values(actualizado_en=db.ahora(), extra=extra))
        return extra


def _campanas(con, cliente, sprint_id=None, campana_id=None):
    c, p, t, r = db.campana, db.persona, db.temporada, db.referencia
    conteo = (sa.select(r.c.campana_id, sa.func.count().label("total"),
                        sa.func.sum(sa.case((r.c.estado == "lista", 1), else_=0)).label("listas"))
              .where(r.c.cliente == cliente).group_by(r.c.campana_id).subquery())
    q = (sa.select(c, p.c.nombre.label("persona_nombre"), p.c.color.label("persona_color"),
                   t.c.nombre.label("temporada_nombre"), t.c.inicio.label("temporada_inicio"),
                   t.c.fin.label("temporada_fin"),
                   sa.func.coalesce(conteo.c.total, 0).label("referencias_total"),
                   sa.func.coalesce(conteo.c.listas, 0).label("referencias_listas"))
         .select_from(c.join(p, p.c.id == c.c.persona_id).join(t, t.c.id == c.c.temporada_id)
                      .outerjoin(conteo, conteo.c.campana_id == c.c.id))
         .where(c.c.cliente == cliente))
    if sprint_id is not None:
        q = q.where(c.c.sprint_id == sprint_id)
    if campana_id is not None:
        q = q.where(c.c.id == campana_id)
    salida = []
    for f in con.execute(q.order_by(c.c.orden, c.c.id)):
        d = _a_dict(f)
        todas = _ideas(con, cliente, campana_id=d["id"])
        piezas_ = [i for i in todas if not i["sin_sesion"] and i["estado_idea"] != "descartada"]
        d.update({"ideas": todas, "piezas": piezas_,
                  "piezas_listas": sum(1 for i in piezas_ if i["estado"] in _PIEZA_TERMINADA),
                  "piezas_aprobadas": sum(1 for i in piezas_ if i["revision"] == "aprobada"),
                  "referencias_total": int(d["referencias_total"] or 0),
                  "referencias_listas": int(d["referencias_listas"] or 0)})
        salida.append(d)
    return salida


def _sprint_dict(con, cliente, f, con_eventos):
    d = _a_dict(f)
    d["campanas"] = _campanas(con, cliente, sprint_id=d["id"])
    d["campanas_total"] = len(d["campanas"])
    d["piezas_planeadas"] = sum(int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0) for c in d["campanas"])
    d["eventos"] = _eventos(con, cliente, d["id"], 50) if con_eventos else []
    d["extra"] = d.get("extra") or {}
    return d


def sprints(cliente, incluir_archivados=False):
    s = db.sprint
    q = sa.select(s).where(s.c.cliente == cliente)
    if not incluir_archivados:
        q = q.where(s.c.archivado.is_(False))
    with db.conectar() as con:
        return [_sprint_dict(con, cliente, f, con_eventos=False) for f in con.execute(q.order_by(s.c.inicio.desc(), s.c.id.desc()))]


def sprint(cliente, sprint_id, con_eventos=True):
    with db.conectar() as con:
        f = _fila(con, db.sprint, sprint_id, cliente)
        return _sprint_dict(con, cliente, f, con_eventos) if f else None


# ----------------------------------------------------------- campañas ---

def combinaciones(cliente, sprint_id):
    c = db.campana
    with db.conectar() as con:
        return {(f.persona_id, f.catalogo_id, f.temporada_id) for f in con.execute(
            sa.select(c.c.persona_id, c.c.catalogo_id, c.c.temporada_id)
            .where(c.c.cliente == cliente, c.c.sprint_id == sprint_id))}


def _cantidades(n_videos, n_imagenes):
    try:
        n_videos, n_imagenes = int(n_videos or 0), int(n_imagenes or 0)
    except (TypeError, ValueError):
        raise ErrorDatos("Las cantidades de videos e imágenes deben ser números enteros.")
    if n_videos < 0 or n_imagenes < 0:
        raise ErrorDatos("Las cantidades no pueden ser negativas.")
    if n_videos + n_imagenes < 1:
        raise ErrorDatos("Una campaña necesita al menos un video o una imagen.")
    return n_videos, n_imagenes


def validar_cantidades(n_videos, n_imagenes):
    """Para que la ruta valide todas las campañas ANTES de crear el sprint."""
    return _cantidades(n_videos, n_imagenes)


def agregar_campana(cliente, sprint_id, persona_id, catalogo_id, temporada_id, n_videos, n_imagenes,
                    referencias_objetivo=None, funnel="tof"):
    n_videos, n_imagenes = _cantidades(n_videos, n_imagenes)
    catalogo_id = _texto(catalogo_id, 120)
    if not catalogo_id:
        raise ErrorDatos("Elige un producto.")
    if funnel not in FUNNELS:
        raise ErrorDatos(f"Funnel inválido: {funnel}. Opciones: {FUNNELS}")
    ahora = db.ahora()
    with db.conectar() as con:
        sp = _fila(con, db.sprint, sprint_id, cliente)
        if not sp:
            raise ErrorDatos("Ese sprint no existe.")
        if not _fila(con, db.persona, persona_id, cliente):
            raise ErrorDatos("Esa persona no existe en este proyecto.")
        if temporada_id and not _fila(con, db.temporada, temporada_id, cliente):
            raise ErrorDatos("Esa temporada no existe en este proyecto.")
        c = db.campana
        repetida = con.execute(sa.select(c.c.orden).where(
            c.c.sprint_id == sprint_id, c.c.persona_id == persona_id, c.c.catalogo_id == catalogo_id,
            c.c.temporada_id == temporada_id)).scalar()
        if repetida is not None:
            raise CampanaDuplicada(
                f"Esa combinación de persona, producto y temporada ya existe en la campaña {int(repetida) + 1}.")
        # max+1 y no count: si se borró una campaña intermedia, count repetiría un número ya usado.
        orden = con.execute(sa.select(sa.func.coalesce(sa.func.max(c.c.orden), -1) + 1)
                            .where(c.c.sprint_id == sprint_id)).scalar()
        try:
            objetivo = int(referencias_objetivo or sp.referencias_objetivo_defecto or 5)
        except (TypeError, ValueError):
            raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
        try:
            cid = con.execute(c.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, sprint_id=sprint_id, persona_id=persona_id,
                catalogo_id=catalogo_id, producto_id=None, temporada_id=temporada_id, n_videos=n_videos,
                n_imagenes=n_imagenes, referencias_objetivo=max(1, objetivo), estado="planeada", orden=orden,
                funnel=funnel, extra={})).inserted_primary_key[0]
        except sa.exc.IntegrityError:
            raise CampanaDuplicada("Esa combinación de persona, producto y temporada ya existe en este sprint.")
        _evento(con, cliente, sprint_id, cid, "campana_agregada", "Campaña agregada",
                {"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": temporada_id,
                 "n_videos": n_videos, "n_imagenes": n_imagenes, "funnel": funnel})
        con.execute(db.sprint.update().where(db.sprint.c.id == sprint_id).values(actualizado_en=ahora))
    return cid


def actualizar_campana(cliente, campana_id, /, **campos):
    if "n_videos" in campos or "n_imagenes" in campos:
        actual = campana(cliente, campana_id) or {}
        campos["n_videos"], campos["n_imagenes"] = _cantidades(campos.get("n_videos", actual.get("n_videos")),
                                                               campos.get("n_imagenes", actual.get("n_imagenes")))
    if "estado" in campos and campos["estado"] not in ESTADOS_CAMPANA:
        raise ErrorDatos(f"Estado de campaña inválido: {campos['estado']}")
    if "referencias_objetivo" in campos:
        try:
            campos["referencias_objetivo"] = max(1, int(campos["referencias_objetivo"]))
        except (TypeError, ValueError):
            raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
    with db.conectar() as con:
        return _actualizar(con, db.campana, campana_id, cliente, _CAMPANA_COLS, campos)


def eliminar_campana(cliente, campana_id):
    with db.conectar() as con:
        f = _fila(con, db.campana, campana_id, cliente)
        if not f:
            return False
        con.execute(db.referencia.delete().where(db.referencia.c.campana_id == campana_id))
        con.execute(db.campana_pieza.delete().where(db.campana_pieza.c.campana_id == campana_id))
        con.execute(db.sprint_evento.update().where(db.sprint_evento.c.campana_id == campana_id).values(campana_id=None))
        con.execute(db.campana.delete().where(db.campana.c.id == campana_id))
        _evento(con, cliente, f.sprint_id, None, "campana_eliminada", "Campaña eliminada",
                {"campana_id": campana_id, "catalogo_id": f.catalogo_id})
    return True


def campana(cliente, campana_id):
    with db.conectar() as con:
        lista = _campanas(con, cliente, campana_id=campana_id)
    return lista[0] if lista else None


def campanas(cliente, sprint_id):
    with db.conectar() as con:
        return _campanas(con, cliente, sprint_id=sprint_id)


# -------------------------------------------------------- referencias ---

def intencion_valida(lista):
    lista = [str(x) for x in (lista or []) if x]
    malas = [x for x in lista if x not in INTENCIONES]
    if malas:
        raise ErrorDatos(f"Intención desconocida: {', '.join(malas)}")
    return list(dict.fromkeys(lista))    # sin repetidos, en orden


def _estado_referencia(descripcion):
    return "lista" if (descripcion or "").strip() else "borrador"


def agregar_referencia(cliente, campana_id, tipo, url, frame_url=None, ruta_local=None, origen="archivo", titulo="",
                       intencion=None, descripcion=""):
    if tipo not in ("imagen", "video"):
        raise ErrorDatos(f"Tipo de referencia inválido: {tipo}")
    if origen not in ORIGENES_REFERENCIA:
        raise ErrorDatos(f"Origen de referencia inválido: {origen}")
    if not (url or "").strip():
        raise ErrorDatos("La referencia necesita una URL.")
    intencion = intencion_valida(intencion)
    descripcion = _texto(descripcion)
    ahora = db.ahora()
    with db.conectar() as con:
        c = _fila(con, db.campana, campana_id, cliente)
        if not c:
            raise ErrorDatos("Esa campaña no existe.")
        r = db.referencia
        orden = con.execute(sa.select(sa.func.count()).select_from(r).where(r.c.campana_id == campana_id)).scalar() or 0
        rid = con.execute(r.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, campana_id=campana_id, tipo=tipo, url=url.strip(),
            frame_url=frame_url, ruta_local=ruta_local, origen=origen, titulo=_texto(titulo, 200), intencion=intencion,
            intencion_otro=None, descripcion=descripcion, analisis=None, analisis_estado="pendiente",
            estado=_estado_referencia(descripcion), orden=orden, extra={})).inserted_primary_key[0]
        _evento(con, cliente, c.sprint_id, campana_id, "referencia_agregada", f"Referencia agregada ({tipo}, {origen})",
                {"referencia_id": rid, "titulo": _texto(titulo, 200)})
    return rid


def actualizar_referencia(cliente, referencia_id, /, **campos):
    campos.pop("estado", None)   # se deriva de descripcion; nunca lo fija quien llama
    if "intencion" in campos:
        campos["intencion"] = intencion_valida(campos["intencion"])
    if "descripcion" in campos:
        campos["descripcion"] = _texto(campos["descripcion"])
    if "intencion_otro" in campos:
        campos["intencion_otro"] = _texto(campos["intencion_otro"], 200) or None
    if "analisis_estado" in campos and campos["analisis_estado"] not in ("pendiente", "listo", "error"):
        raise ErrorDatos(f"Estado de análisis inválido: {campos['analisis_estado']}")
    permitidas = _REFERENCIA_COLS + ("estado",)
    if "descripcion" in campos:
        campos["estado"] = _estado_referencia(campos["descripcion"])
    with db.conectar() as con:
        return _actualizar(con, db.referencia, referencia_id, cliente, permitidas, campos)


def quitar_referencia(cliente, referencia_id):
    with db.conectar() as con:
        f = _fila(con, db.referencia, referencia_id, cliente)
        if not f:
            return False
        c = con.execute(sa.select(db.campana.c.sprint_id).where(db.campana.c.id == f.campana_id)).first()
        con.execute(db.referencia.delete().where(db.referencia.c.id == referencia_id))
        if c:
            _evento(con, cliente, c.sprint_id, f.campana_id, "referencia_quitada", "Referencia quitada",
                    {"referencia_id": referencia_id, "titulo": f.titulo})
    return True


def _referencias(con, cliente, campana_id=None, referencia_id=None):
    r, c = db.referencia, db.campana
    q = (sa.select(r, c.c.sprint_id.label("sprint_id")).select_from(r.join(c, c.c.id == r.c.campana_id))
         .where(r.c.cliente == cliente))
    if campana_id is not None:
        q = q.where(r.c.campana_id == campana_id)
    if referencia_id is not None:
        q = q.where(r.c.id == referencia_id)
    return [_a_dict(f) for f in con.execute(q.order_by(r.c.orden, r.c.id))]


def referencias(cliente, campana_id):
    with db.conectar() as con:
        return _referencias(con, cliente, campana_id=campana_id)


def referencia(cliente, referencia_id):
    with db.conectar() as con:
        lista = _referencias(con, cliente, referencia_id=referencia_id)
    return lista[0] if lista else None


def reutilizar_referencia(cliente, referencia_id, campana_destino_id):
    """Copia la referencia (con su análisis) a otra campaña, origen `reutilizada`."""
    origen = referencia(cliente, referencia_id)
    if not origen:
        raise ErrorDatos("Esa referencia no existe.")
    if origen["campana_id"] == campana_destino_id:
        raise ErrorDatos("Esa referencia ya está en esta campaña.")
    rid = agregar_referencia(cliente, campana_destino_id, origen["tipo"], origen["url"], frame_url=origen["frame_url"],
                             ruta_local=origen["ruta_local"], origen="reutilizada", titulo=origen["titulo"],
                             intencion=origen["intencion"], descripcion=origen["descripcion"])
    actualizar_referencia(cliente, rid, analisis=origen.get("analisis"),
                          analisis_estado=origen.get("analisis_estado") or "pendiente",
                          intencion_otro=origen.get("intencion_otro"))
    return rid


def agregar_referencia_biblioteca(cliente, campana_id, referente_id):
    """Trae un referente de la biblioteca (`referentes.datos`) como referencia
    ya analizada de la campaña (spec §10): no se encola `sprint_analizar_referencia`.
    Un mismo referente no entra dos veces a la misma campaña — si ya está, devuelve
    la fila existente en vez de duplicar."""
    ya = [r for r in referencias(cliente, campana_id) if (r.get("extra") or {}).get("referente_id") == referente_id]
    if ya:
        return ya[0]["id"]
    ref = referentes_datos.referente(cliente, referente_id)
    if not ref or ref.get("estado_imagen") != "ok":
        raise ErrorDatos("Ese referente no existe.")
    familia = next((f for f in referentes_datos.familias(cliente) if f["nombre"] == ref.get("familia")), None)
    firma = ref.get("firma") or ""
    rid = agregar_referencia(cliente, campana_id, "imagen", ref["imagen_url"], frame_url=ref["imagen_url"],
                             origen="biblioteca", titulo=ref.get("titular") or "", intencion=["formato"],
                             descripcion=firma)
    actualizar_referencia(cliente, rid, analisis={
        "familia": ref.get("familia"), "descripcion_familia": familia.get("descripcion") if familia else None,
        "etapa": ref.get("etapa"), "consciencia": ref.get("consciencia"), "dolor": ref.get("dolor"),
        "firma": firma, "resumen": firma,
    }, analisis_estado="listo", extra={"referente_id": referente_id})
    return rid


# -------------------------------------------------------------- ideas ---

def _ideas(con, cliente, campana_id=None, cp_id=None):
    """Ideas de una campaña unidas (LEFT JOIN) con la sesión de Crear que las
    generó: `pieza.legado_id == campana_pieza.cf_id`. Las finales tienen otro
    legado_id (`cf__idioma_pais`) y otro tipo, así que nunca se confunden."""
    cp, pz, c = db.campana_pieza, db.pieza, db.campana
    q = (sa.select(cp, c.c.sprint_id.label("sprint_id"), c.c.orden.label("campana_orden"),
                   pz.c.estado.label("estado"), pz.c.url_video, pz.c.url_miniatura, pz.c.url_local,
                   pz.c.costo_usd, pz.c.error.label("pieza_error"), pz.c.modelo)
         .select_from(cp.join(c, c.c.id == cp.c.campana_id)
                      .outerjoin(pz, sa.and_(pz.c.legado_id == cp.c.cf_id, pz.c.cliente == cp.c.cliente,
                                             pz.c.tipo.in_(TIPOS_PIEZA))))
         .where(cp.c.cliente == cliente))
    if campana_id is not None:
        q = q.where(cp.c.campana_id == campana_id)
    if cp_id is not None:
        q = q.where(cp.c.id == cp_id)
    salida = []
    for f in con.execute(q.order_by(cp.c.orden, cp.c.id)):
        d = _a_dict(f)
        d["referencias_ids"] = list(d.get("referencias_ids") or [])
        d["plataformas"] = list(d.get("plataformas") or [])
        d["extra"] = d.get("extra") or {}
        # Sin sesión de Crear que la represente: cf_id NULL o una reserva
        # vencida. Es lo que `produccion.pendientes` y los botones «Generar
        # lote» miran; una reserva viva NO es sin_sesion (otro lote la tiene).
        d["sin_sesion"] = not d["cf_id"] or reserva_vencida(d["cf_id"])
        salida.append(d)
    return salida


def _validar_idea(campos):
    if "tipo" in campos and campos["tipo"] not in TIPOS_PIEZA:
        raise ErrorDatos(f"Tipo de pieza inválido: {campos['tipo']}")
    if "estado_idea" in campos and campos["estado_idea"] not in ESTADOS_IDEA:
        raise ErrorDatos(f"Estado de idea inválido: {campos['estado_idea']}")
    if "revision" in campos and campos["revision"] not in REVISIONES:
        raise ErrorDatos(f"Revisión inválida: {campos['revision']}")
    if "plataformas" in campos:
        campos["plataformas"] = [p for p in (campos["plataformas"] or []) if p in PLATAFORMAS]
    if "referencias_ids" in campos:
        campos["referencias_ids"] = [int(x) for x in (campos["referencias_ids"] or [])]
    if "duracion_s" in campos and campos["duracion_s"] is not None:
        try:
            campos["duracion_s"] = float(campos["duracion_s"])
        except (TypeError, ValueError):
            raise ErrorDatos("La duración debe ser un número.")
    for k in ("titulo", "escena", "sonido", "gancho", "revision_motivo"):
        if k in campos and campos[k] is not None:
            campos[k] = _texto(campos[k], 200 if k in ("titulo", "gancho") else None)
    return campos


def crear_idea(cliente, campana_id, tipo, titulo, escena, sonido="", enfoque=None, gancho="", referencias_ids=None,
               duracion_s=None, plataformas=None, estado_idea="propuesta", extra=None):
    campos = _validar_idea({"tipo": tipo, "titulo": titulo, "escena": escena, "sonido": sonido, "gancho": gancho,
                            "referencias_ids": referencias_ids, "duracion_s": duracion_s, "plataformas": plataformas,
                            "estado_idea": estado_idea})
    if not campos["titulo"] or not campos["escena"]:
        raise ErrorDatos("Una idea necesita título y escena.")
    ahora = db.ahora()
    with db.conectar() as con:
        c = _fila(con, db.campana, campana_id, cliente)
        if not c:
            raise ErrorDatos("Esa campaña no existe.")
        cp = db.campana_pieza
        orden = con.execute(sa.select(sa.func.coalesce(sa.func.max(cp.c.orden), -1)).where(cp.c.campana_id == campana_id)).scalar() + 1
        cp_id = con.execute(cp.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, campana_id=campana_id, tipo=campos["tipo"],
            titulo=campos["titulo"], escena=campos["escena"], sonido=campos["sonido"] or None, enfoque=enfoque,
            gancho=campos["gancho"] or None, referencias_ids=campos["referencias_ids"], duracion_s=campos["duracion_s"],
            plataformas=campos["plataformas"], estado_idea=campos["estado_idea"], cf_id=None, qa=None,
            revision="pendiente", revision_motivo=None, textos=None, orden=orden,
            extra=dict(extra) if isinstance(extra, dict) else {})).inserted_primary_key[0]
        _evento(con, cliente, c.sprint_id, campana_id, "idea_creada", f"Idea «{campos['titulo']}» ({campos['tipo']})",
                {"cp_id": cp_id})
    return cp_id


def actualizar_idea(cliente, cp_id, /, **campos):
    campos = _validar_idea(campos)
    with db.conectar() as con:
        return _actualizar(con, db.campana_pieza, cp_id, cliente, _IDEA_COLS, campos)


def idea(cliente, cp_id):
    with db.conectar() as con:
        lista = _ideas(con, cliente, cp_id=cp_id)
    return lista[0] if lista else None


def ideas(cliente, campana_id, incluir_descartadas=True):
    with db.conectar() as con:
        lista = _ideas(con, cliente, campana_id=campana_id)
    return lista if incluir_descartadas else [i for i in lista if i["estado_idea"] != "descartada"]


def eliminar_idea(cliente, cp_id):
    with db.conectar() as con:
        f = _fila(con, db.campana_pieza, cp_id, cliente)
        if not f:
            return False
        if f.cf_id:
            raise ErrorDatos("Esa idea ya tiene una pieza generada; descártala en vez de borrarla.")
        c = con.execute(sa.select(db.campana.c.sprint_id).where(db.campana.c.id == f.campana_id)).first()
        con.execute(db.campana_pieza.delete().where(db.campana_pieza.c.id == cp_id))
        if c:
            _evento(con, cliente, c.sprint_id, f.campana_id, "idea_eliminada", f"Idea «{f.titulo}» eliminada", {"cp_id": cp_id})
    return True


def guardar_qa(cliente, cp_id, cf_id, qa):
    """Escribe `campana_pieza.qa` solo si la idea sigue apuntando a la sesión
    `cf_id` que se evaluó (el WHERE lleva el cf_id): si entre encolar el QA y
    terminarlo la pieza se regeneró, el veredicto de la sesión vieja no se le
    pega a la nueva. Devuelve True si tocó la fila."""
    cp = db.campana_pieza
    with db.conectar() as con:
        r = con.execute(cp.update().where(cp.c.id == cp_id, cp.c.cliente == cliente, cp.c.cf_id == cf_id)
                        .values(qa=qa, actualizado_en=db.ahora()))
        return r.rowcount == 1


def reclamar_cf(cliente, cp_id, cf_id, esperado=None):
    """Compare-and-swap de `campana_pieza.cf_id`: un solo UPDATE con el valor
    esperado en el WHERE, así dos `produccion.lanzar_lote`/`regenerar`
    concurrentes sobre la misma idea no generan dos sesiones (double spend).
    `esperado=None` (defecto) exige que la idea todavía no tenga sesión
    (`cf_id IS NULL`, el caso de una reserva antes de generar); si se pasa
    `esperado`, el swap solo ocurre cuando el valor actual es exactamente
    ese (el caso de `regenerar`, que reemplaza una sesión ya conocida por
    otra nueva). Devuelve True si el UPDATE tocó la fila (ganó la carrera),
    False si otra llamada ya se adelantó."""
    cp = db.campana_pieza
    condicion = cp.c.cf_id.is_(None) if esperado is None else (cp.c.cf_id == esperado)
    with db.conectar() as con:
        r = con.execute(cp.update().where(cp.c.id == cp_id, cp.c.cliente == cliente, condicion)
                        .values(cf_id=cf_id, actualizado_en=db.ahora()))
        return r.rowcount == 1


def eliminar_sprint(cliente, sprint_id):
    """Elimina un sprint completo: campañas, ideas, referencias, eventos. No reversible."""
    s = sprint(cliente, sprint_id)
    if not s:
        return False
    with db.conectar() as con:
        # Obtener IDs de campañas para eliminar referencias
        campanas_ids = con.execute(
            db.campana.select().where(
                (db.campana.c.sprint_id == sprint_id) &
                (db.campana.c.cliente == cliente)
            )
        ).fetchall()
        campanas_ids = [c.id for c in campanas_ids]

        # Eliminar referencias, ideas y eventos por campaña
        for cid in campanas_ids:
            con.execute(db.referencia.delete().where(
                (db.referencia.c.campana_id == cid)
            ))
            con.execute(db.campana_pieza.delete().where(
                (db.campana_pieza.c.campana_id == cid)
            ))
            con.execute(db.sprint_evento.delete().where(
                (db.sprint_evento.c.campana_id == cid)
            ))

        # Eliminar campañas
        con.execute(db.campana.delete().where(
            (db.campana.c.sprint_id == sprint_id) &
            (db.campana.c.cliente == cliente)
        ))

        # Eliminar eventos del sprint
        con.execute(db.sprint_evento.delete().where(
            (db.sprint_evento.c.sprint_id == sprint_id) &
            (db.sprint_evento.c.cliente == cliente)
        ))

        # Eliminar sprint
        con.execute(db.sprint.delete().where(
            (db.sprint.c.id == sprint_id) &
            (db.sprint.c.cliente == cliente)
        ))
    return True

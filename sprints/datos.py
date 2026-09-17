"""
Datos de los sprints de contenido (Parte 1 del spec): personas, temporadas,
sprints, campañas, referencias y eventos. Solo SQLAlchemy Core sobre
data/creatv.db; nada de proveedores ni de Flask. Las validaciones de negocio
(fechas, cantidades, unicidad) viven aquí; la validación contra el catálogo
de productos la hace la ruta, para que este módulo se pruebe sin carpetas de
clientes.
"""
from datetime import date

import sqlalchemy as sa

import db

INTENCIONES = ("estilo_visual", "composicion", "paleta", "movimiento_camara", "tipografia",
               "transiciones", "storytelling", "iluminacion", "angulo_producto", "otro")
INTENCIONES_NOMBRE = {
    "estilo_visual": "Estilo visual", "composicion": "Composición", "paleta": "Paleta de colores",
    "movimiento_camara": "Movimiento de cámara", "tipografia": "Tipografía", "transiciones": "Transiciones",
    "storytelling": "Storytelling", "iluminacion": "Iluminación", "angulo_producto": "Ángulo de producto",
    "otro": "Otro",
}
ESTADOS_SPRINT = ("planeando", "referencias", "listo_para_generar", "generando", "revision", "completado")
ESTADOS_CAMPANA = ("planeada", "referencias", "ideas_propuestas", "ideas_aprobadas", "generando", "revision", "completada")
TIPOS_TEMPORADA = ("comercial", "estacional", "propia")
ORIGENES_REFERENCIA = ("archivo", "link", "catalogo", "reutilizada")
ORIGENES_PERSONA = ("manual", "sugerida_ia")

_PERSONA_COLS = ("nombre", "resumen", "descripcion", "edad_rango", "tono", "senales_visuales", "palabras_clave",
                 "color", "origen", "archivada", "extra")
_TEMPORADA_COLS = ("nombre", "inicio", "fin", "contexto", "mood_visual", "tipo", "archivada", "extra")
_SPRINT_COLS = ("nombre", "inicio", "fin", "estado", "destinos", "referencias_objetivo_defecto", "notas",
                "archivado", "extra")
_CAMPANA_COLS = ("n_videos", "n_imagenes", "referencias_objetivo", "estado", "orden", "extra", "producto_id")
_REFERENCIA_COLS = ("titulo", "intencion", "intencion_otro", "descripcion", "analisis", "analisis_estado", "orden",
                    "extra", "frame_url", "ruta_local")


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


def _texto(v, largo=None):
    v = (v or "").strip()
    return v[:largo] if largo else v


# ----------------------------------------------------------- personas ---

def crear_persona(cliente, nombre, /, resumen="", descripcion="", edad_rango="", tono="", senales_visuales=None,
                  palabras_clave=None, color=None, origen="manual"):
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
            color=color, origen=origen, archivada=False, extra={})).inserted_primary_key[0]


def actualizar_persona(cliente, persona_id, /, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("La persona necesita un nombre.")
    if "origen" in campos and campos["origen"] not in ORIGENES_PERSONA:
        raise ErrorDatos(f"Origen de persona inválido: {campos['origen']}")
    with db.conectar() as con:
        return _actualizar(con, db.persona, persona_id, cliente, _PERSONA_COLS, campos)


def archivar_persona(cliente, persona_id, /, archivada=True):
    return actualizar_persona(cliente, persona_id, archivada=bool(archivada))


def personas(cliente, /, incluir_archivadas=False):
    p = db.persona
    q = sa.select(p).where(p.c.cliente == cliente)
    if not incluir_archivadas:
        q = q.where(p.c.archivada.is_(False))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q.order_by(p.c.nombre))]


def persona(cliente, /, persona_id):
    with db.conectar() as con:
        f = _fila(con, db.persona, persona_id, cliente)
    return _a_dict(f) if f else None


# --------------------------------------------------------- temporadas ---

def crear_temporada(cliente, nombre, /, inicio, fin, contexto="", mood_visual=None, tipo="propia"):
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
            contexto=_texto(contexto), mood_visual=dict(mood_visual or {}), tipo=tipo, archivada=False,
            extra={})).inserted_primary_key[0]


def actualizar_temporada(cliente, temporada_id, /, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("La temporada necesita un nombre.")
    if "tipo" in campos and campos["tipo"] not in TIPOS_TEMPORADA:
        raise ErrorDatos(f"Tipo de temporada inválido: {campos['tipo']}")
    if "inicio" in campos or "fin" in campos:
        actual = temporada(cliente, temporada_id) or {}
        campos["inicio"], campos["fin"] = _rango(campos.get("inicio", actual.get("inicio")),
                                                 campos.get("fin", actual.get("fin")), "la temporada")
    with db.conectar() as con:
        return _actualizar(con, db.temporada, temporada_id, cliente, _TEMPORADA_COLS, campos)


def archivar_temporada(cliente, temporada_id, /, archivada=True):
    return actualizar_temporada(cliente, temporada_id, archivada=bool(archivada))


def temporadas(cliente, /, incluir_archivadas=False):
    t = db.temporada
    q = sa.select(t).where(t.c.cliente == cliente)
    if not incluir_archivadas:
        q = q.where(t.c.archivada.is_(False))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q.order_by(t.c.inicio, t.c.nombre))]


def temporada(cliente, /, temporada_id):
    with db.conectar() as con:
        f = _fila(con, db.temporada, temporada_id, cliente)
    return _a_dict(f) if f else None

"""
Datos del módulo Nicho (spec §2): estudios, comentarios y avatares. ÚNICO
escritor de las tres tablas. Solo SQLAlchemy Core sobre data/creatv.db; nada
de Flask ni de proveedores. Aprobar un sub-avatar crea o actualiza una persona
de Sprints (origen `investigada`) a través de `sprints.datos`, que sigue siendo
el único escritor de `persona`.
"""
import re

import sqlalchemy as sa
from flask_babel import gettext

import cola
import db
import idiomas
from idiomas import N_
from nicho import calidad
from sprints import datos as sprints_datos
from sprints.sugerencias import COLORES

ESTADOS_ESTUDIO = ("armando", "generando", "revisando")
FUENTES_PLATAFORMA = ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress")   # claves de nicho.fuentes.plataformas (Partes 3 y 4)
FUENTES = ("texto", "csv", "reddit", "youtube", "apify") + FUENTES_PLATAFORMA
PAISES_ESTUDIO = ("CO", "MX", "US", "ES", "BR", "AR", "CL", "PE", "UY", "EC", "SE", "NO", "GB", "DE", "FR", "IT", "NL", "CA", "AU", "IN", "JP", "AE")
NOMBRES_PAIS = {"CO": N_("Colombia"), "MX": N_("México"), "US": N_("Estados Unidos"), "ES": N_("España"), "BR": N_("Brasil"),
                "AR": N_("Argentina"), "CL": N_("Chile"), "PE": N_("Perú"), "UY": N_("Uruguay"), "EC": N_("Ecuador"),
                "SE": N_("Suecia"), "NO": N_("Noruega"), "GB": N_("Reino Unido"), "DE": N_("Alemania"), "FR": N_("Francia"), "IT": N_("Italia"),
                "NL": N_("Países Bajos"), "CA": N_("Canadá"), "AU": N_("Australia"), "IN": N_("India"), "JP": N_("Japón"),
                "AE": N_("Emiratos Árabes Unidos")}
MAX_INVESTIGACIONES_PREVIAS = 3
TIPOS_AVATAR = ("nucleo", "sub")
BASES = ("emocion", "experiencia_producto")
ESTADOS_AVATAR = ("propuesto", "aprobado", "descartado")
# La clave guardada no cambia; la etiqueta se traduce al mostrarla (|traducir / gettext).
ETIQUETAS_ESTADO_ESTUDIO = {"armando": N_("armando"), "generando": N_("generando"), "revisando": N_("revisando")}
ETIQUETAS_ESTADO_AVATAR = {"propuesto": N_("propuesto"), "aprobado": N_("aprobado"), "descartado": N_("descartado")}
NIVELES_CONCIENCIA = ("inconsciente", "consciente_del_problema", "consciente_de_la_solucion",
                      "consciente_del_producto", "muy_consciente")
CLAVES_IDENTIDAD = ("quiere_que_vean", "cree_de_si", "quiere_lograr")
MAX_RECOLECCIONES = 20          # registros que se conservan en estudio.extra["recolecciones"]

_ESTUDIO_COLS = ("nombre", "producto", "catalogo_id", "tema", "idioma", "pais", "estado", "archivado", "generacion", "extra")
_AVATAR_COLS = ("nombre", "deseo", "resumen", "demografia", "edad_rango", "emocion", "identidad", "soluciones_previas",
                "situaciones", "comportamiento", "conciencia", "encaje_producto", "tono", "palabras_clave", "evidencia",
                "sin_evidencia", "estado", "persona_id", "orden", "base", "extra")
# Lo que el formulario de revisión puede tocar (estado/persona_id van por aprobar/descartar).
AVATAR_EDITABLES = ("nombre", "deseo", "base", "demografia", "edad_rango", "emocion", "identidad", "soluciones_previas",
                    "situaciones", "comportamiento", "conciencia", "encaje_producto", "tono", "palabras_clave")
_RE_IDIOMA = re.compile(r"^[a-z]{2,5}$")


class ErrorDatos(ValueError):
    """Dato inválido; el mensaje se muestra tal cual a la persona."""


def job_id_generar(cliente, estudio_id):
    """Un solo trabajo de generación vivo por estudio (spec §7): la ruta y la
    tarea usan este mismo id, y `recalcular` lo consulta en la cola."""
    return f"nicho:{cliente}:{int(estudio_id)}:generar"


def job_id_recolectar(cliente, estudio_id, fuente):
    """Una recolección viva por fuente y estudio (spec §7/§8): la ruta la
    encola con este id y la página muestra su barra mientras vive."""
    return f"nicho:{cliente}:{int(estudio_id)}:recolectar:{fuente}"


def job_id_completar(cliente, estudio_id):
    """Un completado vivo por estudio (spec 2026-09-29 §2)."""
    return f"nicho:{cliente}:{int(estudio_id)}:completar"


def job_id_inv(cliente, estudio_id, paso):
    """Un trabajo vivo por paso de la investigación (spec Parte 3 §1):
    `consultas`, `buscar:<plataforma>`, `seleccionar`. Las recolecciones y la
    generación conservan sus propios ids."""
    return f"nicho:{cliente}:{int(estudio_id)}:inv:{paso}"


# ------------------------------------------------------------ helpers ---

def _a_dict(fila):
    return dict(fila._mapping)


def _fila(con, tabla, fila_id, cliente):
    return con.execute(sa.select(tabla).where(tabla.c.id == fila_id, tabla.c.cliente == cliente)).first()


def _actualizar(con, tabla, fila_id, cliente, permitidas, campos):
    malos = set(campos) - set(permitidas)
    if malos:
        raise ErrorDatos(gettext("Campos no editables: %(malos)s", malos=", ".join(sorted(malos))))
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), **campos))
    return r.rowcount == 1


def _bloquear(con, tabla, fila_id, cliente):
    """Toma el lock de escritura de SQLite ANTES de leer (semántica de
    `BEGIN IMMEDIATE`), igual que `experimentos._bloquear`: un UPDATE sin
    efecto obliga al driver a abrir la transacción ya, así el SELECT que sigue
    ve lo que dejó el último escritor (gunicorn y el worker escriben `extra`
    a la vez). Devuelve True si la fila existe."""
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=tabla.c.actualizado_en))
    return r.rowcount == 1


def _texto(v, largo=None):
    v = (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())
    return v[:largo] if largo else v


def _idioma(v):
    v = (v or "").strip().lower()
    return v if _RE_IDIOMA.match(v) else "es"


def _pais(v, estricto=False):
    """ISO-3166-1 alfa-2 de PAISES_ESTUDIO o None. Con `estricto`, un valor no
    vacío fuera de la lista es ErrorDatos (formulario); sin él se ignora."""
    v = (v or "").strip().upper() if isinstance(v, str) else ""
    if not v:
        return None
    if v not in PAISES_ESTUDIO:
        if estricto:
            raise ErrorDatos(gettext("País no soportado: %(pais)s", pais=v))
        return None
    return v


# ----------------------------------------------------------- estudios ---

def crear_estudio(cliente, nombre, producto="", tema="", idioma="es", catalogo_id=None, pais=None):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos(gettext("El estudio necesita un nombre."))
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.estudio.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, producto=_texto(producto),
            catalogo_id=_texto(catalogo_id, 80) or None, tema=_texto(tema), idioma=_idioma(idioma), pais=_pais(pais),
            estado="armando", archivado=False, generacion=0, extra={})).inserted_primary_key[0]


def actualizar_estudio(cliente, estudio_id, /, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos(gettext("El estudio necesita un nombre."))
    if "idioma" in campos:
        campos["idioma"] = _idioma(campos["idioma"])
    if "pais" in campos:
        campos["pais"] = _pais(campos["pais"], estricto=True)
    if "estado" in campos and campos["estado"] not in ESTADOS_ESTUDIO:
        raise ErrorDatos(gettext("Estado de estudio inválido: %(estado)s", estado=campos["estado"]))
    for k in ("producto", "tema"):
        if k in campos:
            campos[k] = _texto(campos[k])
    if "catalogo_id" in campos:
        campos["catalogo_id"] = _texto(campos["catalogo_id"], 80) or None
    with db.conectar() as con:
        ok = _actualizar(con, db.estudio, estudio_id, cliente, _ESTUDIO_COLS, campos)
        if ok and "pais" in campos:
            _remarcar_mercado(con, cliente, estudio_id, campos["pais"])
        return ok


def _remarcar_mercado(con, cliente, estudio_id, pais):
    """`extra.mercado` de un comentario es relativo al país del estudio (spec
    Parte 4 §3): si el estudio cambia de país («Investigar de nuevo», «Editar
    estudio»), en la misma transacción cada comentario con `extra.pais` queda
    `local` si es el país nuevo y si no `otro` (la regla de
    `FuentePlataforma.recolectar`). Solo se escriben las filas que cambian."""
    c = db.comentario
    pais, ahora = (pais or "").upper(), db.ahora()
    filas = con.execute(sa.select(c.c.id, c.c.extra).where(c.c.cliente == cliente, c.c.estudio_id == estudio_id)).all()
    for f in filas:
        ex = f.extra if isinstance(f.extra, dict) else {}
        if not ex.get("pais"):
            continue
        mercado = "local" if str(ex["pais"]).upper() == pais else "otro"
        if ex.get("mercado") != mercado:
            con.execute(c.update().where(c.c.id == f.id).values(actualizado_en=ahora, extra={**ex, "mercado": mercado}))


def archivar_estudio(cliente, estudio_id, archivado=True):
    return actualizar_estudio(cliente, estudio_id, archivado=bool(archivado))


def actualizar_extra_estudio(cliente, estudio_id, fn):
    """Read-modify-write atómico de `estudio.extra` (lock antes de leer, una
    transacción). `fn(extra) -> extra`. Devuelve el extra escrito o None."""
    with db.conectar() as con:
        if not _bloquear(con, db.estudio, estudio_id, cliente):
            return None
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        extra = fn(dict(f.extra or {}))
        con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                    .values(actualizado_en=db.ahora(), extra=extra))
        return extra


def registrar_recoleccion(cliente, estudio_id, registro):
    """Anota una recolección (fuente, nuevos, repetidos, aviso) con fecha en
    `extra.recolecciones`; conserva las últimas MAX_RECOLECCIONES."""
    entrada = {**dict(registro or {}), "fecha": db.ahora()}

    def _fn(extra):
        lista = list(extra.get("recolecciones") or []) + [entrada]
        return {**extra, "recolecciones": lista[-MAX_RECOLECCIONES:]}
    return actualizar_extra_estudio(cliente, estudio_id, _fn)


def _conteos(con, cliente, ids):
    """Por estudio: comentarios por fuente (con excluidos) y sub-avatares por estado."""
    c, a = db.comentario, db.avatar
    fuentes, aprobados, subs = {}, {}, {}
    if not ids:
        return fuentes, aprobados, subs
    excluidos = sa.func.sum(sa.case((c.c.excluido.is_(True), 1), else_=0))
    for eid, fuente, n, exc in con.execute(
            sa.select(c.c.estudio_id, c.c.fuente, sa.func.count(), excluidos)
            .where(c.c.cliente == cliente, c.c.estudio_id.in_(ids)).group_by(c.c.estudio_id, c.c.fuente)):
        fuentes.setdefault(eid, {})[fuente] = {"total": int(n), "excluidos": int(exc or 0)}
    for eid, estado, n in con.execute(
            sa.select(a.c.estudio_id, a.c.estado, sa.func.count())
            .where(a.c.cliente == cliente, a.c.estudio_id.in_(ids), a.c.tipo == "sub").group_by(a.c.estudio_id, a.c.estado)):
        if estado == "aprobado":
            aprobados[eid] = int(n)
        if estado != "descartado":
            subs[eid] = subs.get(eid, 0) + int(n)
    return fuentes, aprobados, subs


def _decorar(e, fuentes, aprobados, subs):
    por_fuente = fuentes.get(e["id"], {})
    total = sum(v["total"] for v in por_fuente.values())
    e["comentarios_total"] = total
    e["comentarios_activos"] = total - sum(v["excluidos"] for v in por_fuente.values())
    e["fuentes"] = por_fuente
    e["avatares_aprobados"] = aprobados.get(e["id"], 0)
    e["avatares_total"] = subs.get(e["id"], 0)
    e["extra"] = dict(e.get("extra") or {})
    return e


def estudios(cliente, incluir_archivados=False):
    t = db.estudio
    q = sa.select(t).where(t.c.cliente == cliente)
    if not incluir_archivados:
        q = q.where(t.c.archivado.is_(False))
    with db.conectar() as con:
        lista = [_a_dict(f) for f in con.execute(q.order_by(t.c.id.desc()))]
        lista = [e for e in lista if not es_manual(e)]
        fuentes, aprobados, subs = _conteos(con, cliente, [e["id"] for e in lista])
    return [_decorar(e, fuentes, aprobados, subs) for e in lista]


def estudio(cliente, estudio_id):
    with db.conectar() as con:
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        fuentes, aprobados, subs = _conteos(con, cliente, [f.id])
    return _decorar(_a_dict(f), fuentes, aprobados, subs)


def recalcular(cliente, estudio_id, tarea_viva=None):
    """Re-deriva `estudio.estado` (spec §1): `generando` si hay una tarea viva
    con el job_id de generación (consultado en la cola salvo que el llamador
    ya lo sepa: la tarea misma pasa `tarea_viva=False` al terminar, porque
    desde adentro su fila sigue `en_curso`); si no, `revisando` cuando el
    estudio tiene algún avatar; si no, `armando`. Devuelve el estado o None."""
    if tarea_viva is None:
        fila = cola.consultar_por_job(job_id_generar(cliente, estudio_id))
        tarea_viva = bool(fila and fila["estado"] in ("pendiente", "en_curso"))
    with db.conectar() as con:
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        n = con.execute(sa.select(sa.func.count()).select_from(db.avatar).where(
            db.avatar.c.estudio_id == estudio_id, db.avatar.c.cliente == cliente)).scalar() or 0
        nuevo = "generando" if tarea_viva else ("revisando" if n else "armando")
        if nuevo != f.estado:
            con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                        .values(actualizado_en=db.ahora(), estado=nuevo))
    return nuevo


# -------------------------------------------------------- comentarios ---

def agregar_comentarios(cliente, estudio_id, fuente, lista):
    """Inserta comentarios ya normalizados (`nicho.fuentes.base.normalizar_comentario`)
    en UNA transacción con `INSERT OR IGNORE` sobre `uq_comentario_fuente`:
    los repetidos no duplican. Un dict sin texto o sin fuente_id se salta."""
    if fuente not in FUENTES:
        raise ErrorDatos(gettext("Fuente desconocida: %(fuente)s", fuente=fuente))
    ahora = db.ahora()
    nuevos = repetidos = 0
    with db.conectar() as con:
        if not _fila(con, db.estudio, estudio_id, cliente):
            raise ErrorDatos(gettext("Ese estudio no existe."))
        historicos = set()
        if fuente == "reddit":
            _bloquear(con, db.estudio, estudio_id, cliente)
            historicos = {(f.fuente_id, f.url) for f in con.execute(
                sa.select(db.comentario.c.fuente_id, db.comentario.c.url).where(
                    db.comentario.c.cliente == cliente, db.comentario.c.estudio_id == estudio_id,
                    db.comentario.c.fuente == "reddit")) if not f.fuente_id.startswith(("t1_", "t3_"))}
        for c in lista or []:
            texto = _texto((c or {}).get("texto"))
            fuente_id = _texto((c or {}).get("fuente_id"), 120)
            if not texto or not fuente_id:
                continue
            if (fuente == "reddit" and fuente_id.startswith(("t1_", "t3_"))
                    and c.get("url") and (fuente_id[3:], _texto(c["url"], 500)) in historicos):
                repetidos += 1
                continue
            r = con.execute(db.comentario.insert().prefix_with("OR IGNORE").values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id, fuente=fuente,
                fuente_id=fuente_id, texto=texto[:2000], url=_texto(c.get("url"), 500) or None,
                contexto=_texto(c.get("contexto"), 300) or None, puntuacion=c.get("puntuacion"),
                fecha=_texto(c.get("fecha"), 19) or None, excluido=False,
                extra=dict(c.get("extra")) if isinstance(c.get("extra"), dict) else {}))
            if r.rowcount == 1:
                nuevos += 1
            else:
                repetidos += 1
    return {"nuevos": nuevos, "repetidos": repetidos}


def comentarios(cliente, estudio_id, fuente=None, pagina=1, por_pagina=50):
    """Página de comentarios, más nuevo primero (incluye excluidos, con su bandera)."""
    c = db.comentario
    cond = [c.c.cliente == cliente, c.c.estudio_id == estudio_id]
    if fuente:
        cond.append(c.c.fuente == fuente)
    pagina = max(1, int(pagina or 1))
    por_pagina = max(1, min(200, int(por_pagina or 50)))
    with db.conectar() as con:
        total = int(con.execute(sa.select(sa.func.count()).select_from(c).where(*cond)).scalar() or 0)
        filas = con.execute(sa.select(c).where(*cond).order_by(c.c.id.desc())
                            .limit(por_pagina).offset((pagina - 1) * por_pagina)).all()
    return {"items": [_a_dict(f) for f in filas], "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // por_pagina))}


def comentario(cliente, comentario_id):
    with db.conectar() as con:
        f = _fila(con, db.comentario, comentario_id, cliente)
    return _a_dict(f) if f else None


def comentarios_para_generar(cliente, estudio_id):
    """Los que entran a Claude: no excluidos, en orden de id."""
    c = db.comentario
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(sa.select(c).where(
            c.c.cliente == cliente, c.c.estudio_id == estudio_id, c.c.excluido.is_(False)).order_by(c.c.id))]


def contar_por_fuente(cliente, estudio_id):
    with db.conectar() as con:
        fuentes, _, _ = _conteos(con, cliente, [estudio_id])
    return fuentes.get(estudio_id, {})


def excluir_comentario(cliente, comentario_id, excluido=True):
    with db.conectar() as con:
        r = con.execute(db.comentario.update().where(
            db.comentario.c.id == comentario_id, db.comentario.c.cliente == cliente)
            .values(actualizado_en=db.ahora(), excluido=bool(excluido)))
    return r.rowcount == 1


def borrar_fuente(cliente, estudio_id, fuente):
    """Borra todos los comentarios de una fuente en el estudio; devuelve cuántos."""
    with db.conectar() as con:
        r = con.execute(db.comentario.delete().where(
            db.comentario.c.cliente == cliente, db.comentario.c.estudio_id == estudio_id, db.comentario.c.fuente == fuente))
    return int(r.rowcount or 0)


def urls_comentarios(cliente, estudio_id):
    """{id: url} de todos los comentarios del estudio (para enlazar las citas
    en la revisión y en las exportaciones), incluidos los excluidos."""
    c = db.comentario
    with db.conectar() as con:
        return {int(f.id): f.url for f in con.execute(sa.select(c.c.id, c.c.url).where(
            c.c.cliente == cliente, c.c.estudio_id == estudio_id))}


def urls_de_comentarios(cliente, ids):
    """{id: url} de esos comentarios, de cualquier estudio del proyecto."""
    ids = [int(i) for i in ids or []]
    if not ids:
        return {}
    c = db.comentario
    with db.conectar() as con:
        return {int(f.id): f.url for f in con.execute(sa.select(c.c.id, c.c.url).where(c.c.cliente == cliente, c.c.id.in_(ids)))}


def _paises_de_filas(filas):
    salida = {}
    for f in filas:
        ex = f.extra if isinstance(f.extra, dict) else {}
        if ex.get("mercado") == "otro" and ex.get("pais"):
            salida[int(f.id)] = str(ex["pais"])[:2].upper()
    return salida


def paises_otro_mercado_de(cliente, ids):
    """{id: país} de esos comentarios (de cualquier estudio del proyecto) que son
    de otro mercado (`extra.mercado == "otro"`, spec Parte 4 §3), para la etiqueta
    de las citas que los usan."""
    ids = [int(i) for i in ids or []]
    if not ids:
        return {}
    c = db.comentario
    with db.conectar() as con:
        return _paises_de_filas(con.execute(sa.select(c.c.id, c.c.extra).where(c.c.cliente == cliente, c.c.id.in_(ids))))


# ----------------------------------------------------------- avatares ---

def _lista_textos(v, n=8, largo=300):
    """Solo listas: un texto suelto (formulario mal armado, Claude) se ignora."""
    if not isinstance(v, list):
        return []
    return [str(x).strip()[:largo] for x in v if str(x).strip()][:n]


def validar_campos_avatar(campos):
    """Normaliza los campos editables de un sub-avatar (formulario o Claude):
    recorta largos, castea listas, deja `base` en BASES, `conciencia.nivel`
    en NIVELES_CONCIENCIA o vacío (no se inventa), `identidad` con sus tres
    claves. Solo acepta claves de AVATAR_EDITABLES + evidencia/sin_evidencia."""
    permitidas = set(AVATAR_EDITABLES) | {"evidencia", "sin_evidencia"}
    malos = set(campos) - permitidas
    if malos:
        raise ErrorDatos(gettext("Campos no editables: %(malos)s", malos=", ".join(sorted(malos))))
    c = dict(campos)
    if "nombre" in c:
        c["nombre"] = _texto(c["nombre"], 120)
        if not c["nombre"]:
            raise ErrorDatos(gettext("El avatar necesita un nombre."))
    if "deseo" in c:
        c["deseo"] = _texto(c["deseo"], 300)
    for k in ("demografia", "emocion", "comportamiento", "encaje_producto", "tono"):
        if k in c:
            c[k] = _texto(c[k], 1500)
    if "edad_rango" in c:
        c["edad_rango"] = _texto(c["edad_rango"], 20)
    if "base" in c:
        c["base"] = c["base"] if c["base"] in BASES else "emocion"
    if "identidad" in c:
        ident = c["identidad"] if isinstance(c["identidad"], dict) else {}
        c["identidad"] = {k: _texto(ident.get(k), 1500) for k in CLAVES_IDENTIDAD}
    if "soluciones_previas" in c:
        limpias = []
        for s in (c["soluciones_previas"] if isinstance(c["soluciones_previas"], list) else [])[:8]:
            if isinstance(s, dict) and _texto(s.get("que")):
                limpias.append({"que": _texto(s.get("que"), 300), "por_que_fallo": _lista_textos(s.get("por_que_fallo"))})
        c["soluciones_previas"] = limpias
    if "situaciones" in c:
        c["situaciones"] = _lista_textos(c["situaciones"])
    if "palabras_clave" in c:
        c["palabras_clave"] = _lista_textos(c["palabras_clave"], n=8, largo=60)
    if "conciencia" in c:
        con_ = c["conciencia"] if isinstance(c["conciencia"], dict) else {}
        nivel = con_.get("nivel") if con_.get("nivel") in NIVELES_CONCIENCIA else ""
        c["conciencia"] = {"nivel": nivel, "detalle": _texto(con_.get("detalle"), 1500)}
    if "evidencia" in c:
        ev = []
        for e in (c["evidencia"] if isinstance(c["evidencia"], list) else [])[:8]:
            if isinstance(e, dict) and _texto(e.get("cita")):
                try:
                    ev.append({"comentario_id": int(e.get("comentario_id")), "cita": _texto(e.get("cita"), 500)})
                except (TypeError, ValueError):
                    continue
        c["evidencia"] = ev
    if "sin_evidencia" in c:
        c["sin_evidencia"] = bool(c["sin_evidencia"])
    return c


_SUB_VACIO = {"demografia": "", "edad_rango": "", "emocion": "", "identidad": {}, "soluciones_previas": [],
              "situaciones": [], "comportamiento": "", "conciencia": {}, "encaje_producto": "", "tono": "",
              "palabras_clave": [], "evidencia": [], "sin_evidencia": False}


def guardar_generacion(cliente, estudio_id, nucleos, resumen=None):
    """Una sola transacción (spec §4.6): sube `generacion`, borra los
    sub-avatares propuesto/descartado de corridas anteriores y los núcleos que
    quedan sin ningún aprobado, inserta lo nuevo con la generación actual,
    deja el estudio en `revisando` y guarda el resumen en extra."""
    ahora = db.ahora()
    a = db.avatar
    with db.conectar() as con:
        if not _bloquear(con, db.estudio, estudio_id, cliente):
            raise ErrorDatos(gettext("Ese estudio no existe."))
        f = _fila(con, db.estudio, estudio_id, cliente)
        g = int(f.generacion or 0) + 1
        con.execute(a.delete().where(a.c.estudio_id == estudio_id, a.c.cliente == cliente, a.c.tipo == "sub",
                                     a.c.estado.in_(("propuesto", "descartado"))))
        con_hijos = sa.select(a.c.padre_id).where(a.c.estudio_id == estudio_id, a.c.padre_id.isnot(None))
        con.execute(a.delete().where(a.c.estudio_id == estudio_id, a.c.cliente == cliente, a.c.tipo == "nucleo",
                                     a.c.id.notin_(con_hijos)))
        n_subs = 0
        for i, n in enumerate(nucleos or []):
            nid = con.execute(a.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id, padre_id=None,
                tipo="nucleo", base=None, orden=i, generacion=g, nombre=_texto(n.get("nombre"), 120) or gettext("Sin nombre"),
                deseo=_texto(n.get("deseo"), 300), resumen=_texto(n.get("resumen")), estado="propuesto", persona_id=None,
                extra={"error": _texto(n.get("error"), 500)} if n.get("error") else {}, **_SUB_VACIO)).inserted_primary_key[0]
            for j, s in enumerate(n.get("sub_avatares") or []):
                campos = {**_SUB_VACIO, "base": "emocion", **validar_campos_avatar(
                    {k: v for k, v in dict(s).items() if k in AVATAR_EDITABLES or k in ("evidencia", "sin_evidencia")})}
                campos["resumen"] = ""
                con.execute(a.insert().values(cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id,
                                              padre_id=nid, tipo="sub", orden=j, generacion=g, estado="propuesto",
                                              persona_id=None, extra={}, **campos))
                n_subs += 1
        extra = dict(f.extra or {})
        extra["ultima_generacion"] = {**dict(resumen or {}), "generacion": g, "fecha": ahora}
        extra.pop("ultimo_error", None)
        con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                    .values(actualizado_en=ahora, generacion=g, estado="revisando", extra=extra))
    return {"generacion": g, "nucleos": len(nucleos or []), "subs": n_subs}


def avatares(cliente, estudio_id):
    """Núcleos con sus `subs` anidados, en orden (generación, orden, id)."""
    a = db.avatar
    with db.conectar() as con:
        filas = [_a_dict(f) for f in con.execute(sa.select(a).where(
            a.c.estudio_id == estudio_id, a.c.cliente == cliente).order_by(a.c.generacion, a.c.orden, a.c.id))]
    nucleos = [dict(f, subs=[]) for f in filas if f["tipo"] == "nucleo"]
    por_id = {n["id"]: n for n in nucleos}
    for f in filas:
        if f["tipo"] == "sub" and f["padre_id"] in por_id:
            por_id[f["padre_id"]]["subs"].append(f)
    return nucleos


def avatar(cliente, avatar_id):
    with db.conectar() as con:
        f = _fila(con, db.avatar, avatar_id, cliente)
    return _a_dict(f) if f else None


def actualizar_avatar(cliente, avatar_id, /, **campos):
    campos = validar_campos_avatar({k: v for k, v in campos.items()})
    if "evidencia" in campos or "sin_evidencia" in campos:
        raise ErrorDatos(gettext("La evidencia no se edita a mano."))
    with db.conectar() as con:
        return _actualizar(con, db.avatar, avatar_id, cliente, _AVATAR_COLS, campos)


def _fusionar(vivos, nuevos, clave):
    """Listas: conserva cada entrada VIVA tal cual (nunca se descarta ni se
    reescribe) y agrega, al final, las de `nuevos` cuya `clave(item)` no
    repite la de una ya presente (sin distinguir mayúsculas)."""
    vivos = list(vivos or [])
    vistas = {clave(x) for x in vivos}
    fusion = list(vivos)
    for x in (nuevos or []):
        k = clave(x)
        if k not in vistas:
            vistas.add(k)
            fusion.append(x)
    return fusion


def guardar_completado(cliente, estudio_id, cambios):
    """Guarda en UNA transacción lo que completó Claude (`{avatar_id: campos}`,
    incluida la evidencia verificada). Ruling 23 (2026-09-29): decide contra
    la fila VIVA en el momento de escribir, no contra la foto de antes de
    llamar a Claude -- entre una y otra una persona pudo editar el avatar a
    mano. Los campos de texto y los fijos (identidad, conciencia) se funden
    con `calidad.fundir` (nunca pisa lo lleno de la fila viva); las listas
    (situaciones, palabras_clave, soluciones_previas, evidencia) se fusionan
    aparte SIEMPRE contra la fila viva -- conservan cada entrada que ya había
    (válida o no) y solo agregan las nuevas que no repiten, sin importar si la
    fila viva ya alcanzaba el mínimo (si no, un mínimo cumplido a mano
    descartaría en silencio lo nuevo que Claude sí encontró). Solo escribe las
    claves cuyo valor fundido difiere del que ya estaba. Devuelve los ids
    aprobados, para que quien llama actualice sus personas."""
    permitidas = set(AVATAR_EDITABLES) | {"evidencia", "sin_evidencia"}
    listas = ("situaciones", "palabras_clave", "soluciones_previas", "evidencia")
    aprobados = []
    with db.conectar() as con:
        for aid, campos in (cambios or {}).items():
            f = _fila(con, db.avatar, int(aid), cliente)
            if not f or f.estudio_id != int(estudio_id) or f.tipo != "sub":
                continue
            vivo = _a_dict(f)
            nuevos = validar_campos_avatar({k: v for k, v in dict(campos).items() if k in permitidas and k != "nombre"})
            fundido = calidad.fundir(vivo, nuevos)
            limpios = {k: fundido[k] for k in nuevos if k not in listas and fundido.get(k) != vivo.get(k)}
            if "situaciones" in nuevos:
                nueva = _fusionar(vivo.get("situaciones"), nuevos.get("situaciones"), lambda x: str(x).strip().lower())
                if nueva != (vivo.get("situaciones") or []):
                    limpios["situaciones"] = nueva
            if "palabras_clave" in nuevos:
                nueva = _fusionar(vivo.get("palabras_clave"), nuevos.get("palabras_clave"), lambda x: str(x).strip().lower())
                if nueva != (vivo.get("palabras_clave") or []):
                    limpios["palabras_clave"] = nueva
            if "soluciones_previas" in nuevos:
                validas = calidad.soluciones_validas(nuevos)
                nueva = _fusionar(vivo.get("soluciones_previas"), validas, lambda x: str((x or {}).get("que") or "").strip().lower())
                if nueva != (vivo.get("soluciones_previas") or []):
                    limpios["soluciones_previas"] = nueva
            if "evidencia" in nuevos:
                nueva = _fusionar(vivo.get("evidencia"), nuevos.get("evidencia"),
                                  lambda e: ((e or {}).get("comentario_id"), str((e or {}).get("cita") or "").strip().lower()))[:8]
                if nueva != (vivo.get("evidencia") or []):
                    limpios["evidencia"] = nueva
                    limpios["sin_evidencia"] = not nueva
            if limpios:
                _actualizar(con, db.avatar, int(aid), cliente, _AVATAR_COLS, limpios)
            if f.estado == "aprobado":
                aprobados.append(int(aid))
    return aprobados


def persona_desde_avatar(a):
    """Mapeo del spec §5: nombre, resumen ← deseo, descripción ← demografía +
    emoción + comportamiento + soluciones previas, edad, tono, señales
    visuales ← situaciones, palabras clave."""
    soluciones = []
    for s in a.get("soluciones_previas") or []:
        que = (s.get("que") or "").strip()
        if not que:
            continue
        fallas = ", ".join(x for x in (s.get("por_que_fallo") or []) if x)
        uso = gettext("Usó %(que)s", que=que)          # quien llama fija el idioma (el del proyecto)
        soluciones.append(uso + (f": {fallas}" if fallas else ""))
    partes = [a.get("demografia"), a.get("emocion"), a.get("comportamiento"), ". ".join(soluciones)]
    descripcion = ". ".join(p.strip().rstrip(".") for p in partes if p and p.strip())
    return {"nombre": a["nombre"], "resumen": (a.get("deseo") or "")[:200], "descripcion": descripcion,
            "edad_rango": a.get("edad_rango") or "", "tono": a.get("tono") or "",
            "senales_visuales": list(a.get("situaciones") or []), "palabras_clave": list(a.get("palabras_clave") or [])}


def aprobar_avatar(cliente, avatar_id):
    """Crea la persona (origen `investigada`) o, si el avatar ya tiene una,
    la actualiza y la desarchiva. Solo sub-avatares. Devuelve persona_id."""
    a = avatar(cliente, avatar_id)
    if not a:
        raise ErrorDatos(gettext("Ese avatar no existe."))
    if a["tipo"] != "sub":
        raise ErrorDatos(gettext("Solo se aprueban los sub-avatares; el núcleo es una agrupación."))
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):    # la persona se guarda: idioma del proyecto
        campos = persona_desde_avatar(a)
    est = estudio(cliente, a["estudio_id"])
    extra = {"avatar_id": a["id"], "estudio_id": a["estudio_id"], "identidad": dict(a.get("identidad") or {}),
             "conciencia": dict(a.get("conciencia") or {}), "encaje_producto": a.get("encaje_producto") or "",
             "evidencia": list(a.get("evidencia") or [])}
    pid = a.get("persona_id")
    existente = sprints_datos.persona(cliente, pid) if pid else None
    if existente:
        # Conserva lo que la persona ya traía en extra (p. ej. lo que se eligió en Sprints) y su origen.
        sprints_datos.actualizar_persona(cliente, pid, archivada=False, extra={**dict(existente.get("extra") or {}), **extra}, **campos)
    else:
        n = len(sprints_datos.personas(cliente, incluir_archivadas=True))
        pid = sprints_datos.crear_persona(cliente, origen="manual" if es_manual(est) else "investigada",
                                          color=COLORES[n % len(COLORES)], extra=extra, **campos)
    with db.conectar() as con:
        _actualizar(con, db.avatar, avatar_id, cliente, _AVATAR_COLS, {"estado": "aprobado", "persona_id": pid})
    return pid


def descartar_avatar(cliente, avatar_id):
    """Marca `descartado`; si ya tenía persona, la archiva (reversible)."""
    a = avatar(cliente, avatar_id)
    if not a or a["tipo"] != "sub":
        return False
    if a.get("persona_id"):
        sprints_datos.archivar_persona(cliente, a["persona_id"])
    with db.conectar() as con:
        return _actualizar(con, db.avatar, avatar_id, cliente, _AVATAR_COLS, {"estado": "descartado"})


def eliminar_estudio(cliente, estudio_id):
    """Elimina un estudio completo: comentarios, avatares, recolecciones. No reversible."""
    e = estudio(cliente, estudio_id)
    if not e:
        return False
    with db.conectar() as con:
        # Desconectar avatares de personas (no eliminar personas, son reutilizables)
        con.execute(db.avatar.update().where(
            (db.avatar.c.estudio_id == estudio_id) &
            (db.avatar.c.cliente == cliente)
        ).values(persona_id=None))
        # Eliminar avatares
        con.execute(db.avatar.delete().where(
            (db.avatar.c.estudio_id == estudio_id) &
            (db.avatar.c.cliente == cliente)
        ))
        # Eliminar comentarios
        con.execute(db.comentario.delete().where(
            (db.comentario.c.estudio_id == estudio_id) &
            (db.comentario.c.cliente == cliente)
        ))
        # Eliminar estudio
        con.execute(db.estudio.delete().where(
            (db.estudio.c.id == estudio_id) &
            (db.estudio.c.cliente == cliente)
        ))
    return True


# ------------------------------------------------------ investigación ---

def actualizar_investigacion(cliente, estudio_id, fn):
    """RMW bajo candado de `extra.investigacion` (Flask y el worker escriben a
    la vez): `fn(inv) -> inv_nuevo` recibe `{}` cuando no hay investigación.
    Devuelve lo escrito, o None si el estudio no existe."""
    salida = {}

    def _fn(extra):
        actual = extra.get("investigacion")
        nuevo = fn(dict(actual) if isinstance(actual, dict) else {})
        salida["inv"] = nuevo
        return {**extra, "investigacion": nuevo}
    if actualizar_extra_estudio(cliente, estudio_id, _fn) is None:
        return None
    return salida.get("inv")


def iniciar_investigacion(cliente, estudio_id, inv):
    """Deja `inv` como la investigación viva; la anterior (si la hay) pasa a
    `extra.investigaciones_previas` (últimas MAX_INVESTIGACIONES_PREVIAS)."""
    nuevo = dict(inv or {})

    def _fn(extra):
        anterior = extra.get("investigacion")
        previas = list(extra.get("investigaciones_previas") or [])
        if anterior:
            previas = (previas + [anterior])[-MAX_INVESTIGACIONES_PREVIAS:]
        return {**extra, "investigacion": nuevo, "investigaciones_previas": previas}
    extra = actualizar_extra_estudio(cliente, estudio_id, _fn)
    return extra["investigacion"] if extra else None


def investigacion(cliente, estudio_id):
    """La investigación viva del estudio, o `{}` (la plantilla mira `.estado`)."""
    e = estudio(cliente, estudio_id)
    inv = (e["extra"].get("investigacion") if e else None)
    return inv if isinstance(inv, dict) else {}


# ------------------------------------------------------ producto_nicho ---

_PRODUCTO_COLS = ("titulo", "marca", "precio", "moneda", "estrellas", "n_resenas", "url", "imagen", "consulta", "extra")


def _url_web(valor):
    """La URL si es http(s)://, si no None: el `url` y la `imagen` de un
    producto van a un enlace y a un <img>, y un «javascript:» no puede llegar
    ahí (lo filtraba solo nicho/fuentes/plataformas.py; ahora también el
    único escritor)."""
    texto = _texto(valor, 500)
    return texto if texto and texto.lower().startswith(("http://", "https://")) else None


def _producto_limpio(p):
    p = dict(p or {})
    fuente_id, titulo = _texto(p.get("fuente_id"), 120), _texto(p.get("titulo"), 300)
    if not fuente_id or not titulo:
        return None
    return {"fuente_id": fuente_id, "titulo": titulo, "marca": _texto(p.get("marca"), 120) or None,
            "precio": p.get("precio"), "moneda": (_texto(p.get("moneda"), 3) or None), "estrellas": p.get("estrellas"),
            "n_resenas": p.get("n_resenas"), "url": _url_web(p.get("url")), "imagen": _url_web(p.get("imagen")),
            "consulta": _texto(p.get("consulta"), 200),
            "extra": dict(p.get("extra")) if isinstance(p.get("extra"), dict) else {}}


def guardar_productos_nicho(cliente, estudio_id, plataforma, productos):
    """Upsert por (estudio, plataforma, fuente_id) en UNA transacción: los nuevos
    se insertan; los existentes actualizan título, precio, estrellas, reseñas,
    url, imagen, consulta y extra, y CONSERVAN relevante/motivo/resenas_traidas
    (el juicio de Claude y lo ya pagado no se pisan). Un dict sin id o sin
    título se salta."""
    if plataforma not in FUENTES_PLATAFORMA:
        raise ErrorDatos(gettext("Plataforma desconocida: %(plataforma)s", plataforma=plataforma))
    t, ahora = db.producto_nicho, db.ahora()
    nuevos = actualizados = 0
    with db.conectar() as con:
        if not _fila(con, db.estudio, estudio_id, cliente):
            raise ErrorDatos(gettext("Ese estudio no existe."))
        for p in productos or []:
            limpio = _producto_limpio(p)
            if not limpio:
                continue
            r = con.execute(t.insert().prefix_with("OR IGNORE").values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id, plataforma=plataforma,
                relevante=None, motivo=None, resenas_traidas=0, **limpio))
            if r.rowcount == 1:
                nuevos += 1
                continue
            con.execute(t.update().where(t.c.estudio_id == estudio_id, t.c.plataforma == plataforma,
                                         t.c.fuente_id == limpio["fuente_id"], t.c.cliente == cliente)
                        .values(actualizado_en=ahora, **{k: limpio[k] for k in _PRODUCTO_COLS}))
            actualizados += 1
    return {"nuevos": nuevos, "actualizados": actualizados}


def productos_nicho(cliente, estudio_id, plataforma=None, solo_relevantes=False, solo_sin_juzgar=False, fuente_ids=None):
    """Productos del estudio: por plataforma, más reseñas primero (sin dato al
    final), id. `solo_relevantes` = juzgados como del nicho; `solo_sin_juzgar`
    = `relevante IS NULL`; `fuente_ids` acota a esos ids de la plataforma."""
    t = db.producto_nicho
    cond = [t.c.cliente == cliente, t.c.estudio_id == estudio_id]
    if plataforma:
        cond.append(t.c.plataforma == plataforma)
    if solo_relevantes:
        cond.append(t.c.relevante.is_(True))
    if solo_sin_juzgar:
        cond.append(t.c.relevante.is_(None))
    if fuente_ids is not None:
        cond.append(t.c.fuente_id.in_([str(x) for x in fuente_ids] or ["__ninguno__"]))
    with db.conectar() as con:
        filas = con.execute(sa.select(t).where(*cond).order_by(
            t.c.plataforma, sa.desc(sa.func.coalesce(t.c.n_resenas, -1)), t.c.id)).all()
    salida = []
    for f in filas:
        d = _a_dict(f)
        d["resenas_traidas"] = int(d.get("resenas_traidas") or 0)
        d["extra"] = dict(d.get("extra") or {})
        salida.append(d)
    return salida


def marcar_relevancia(cliente, estudio_id, decisiones):
    """`decisiones = {id: {"relevante": bool, "motivo": str}}` sobre productos
    del estudio; ids ajenos se ignoran. Devuelve cuántos cambió."""
    t, n = db.producto_nicho, 0
    with db.conectar() as con:
        for pid, d in (decisiones or {}).items():
            r = con.execute(t.update().where(t.c.id == int(pid), t.c.estudio_id == estudio_id, t.c.cliente == cliente)
                            .values(actualizado_en=db.ahora(), relevante=bool((d or {}).get("relevante")),
                                    motivo=_texto((d or {}).get("motivo"), 300) or None))
            n += r.rowcount
    return n


def sumar_resenas_traidas(cliente, estudio_id, plataforma, conteos):
    """`conteos = {fuente_id: n}` -> suma n a `resenas_traidas` del producto de esa
    plataforma. Devuelve cuántos productos tocó (los n = 0 no cuentan)."""
    t, n = db.producto_nicho, 0
    with db.conectar() as con:
        for fuente_id, cuantos in (conteos or {}).items():
            if not cuantos:
                continue
            r = con.execute(t.update().where(t.c.estudio_id == estudio_id, t.c.cliente == cliente, t.c.plataforma == plataforma,
                                             t.c.fuente_id == str(fuente_id))
                            .values(actualizado_en=db.ahora(),
                                    resenas_traidas=sa.func.coalesce(t.c.resenas_traidas, 0) + int(cuantos)))
            n += r.rowcount
    return n


# ------------------------------------------------ avatares del proyecto ---

NOMBRE_ESTUDIO_MANUAL = N_("Avatares escritos a mano")
NOMBRE_NUCLEO_MANUAL = N_("Escritos a mano")


def es_manual(e):
    """True para el estudio oculto de los avatares escritos a mano."""
    return bool(((e or {}).get("extra") or {}).get("manual"))


def estudio_manual(cliente):
    """(estudio_id, nucleo_id) del estudio oculto (spec 2026-09-29 §1); lo
    crea la primera vez. Si una carrera dejara dos, se usa el de menor id."""
    t, a = db.estudio, db.avatar
    ahora = db.ahora()
    with db.conectar() as con:
        ocultos = [f.id for f in con.execute(sa.select(t.c.id, t.c.extra).where(t.c.cliente == cliente).order_by(t.c.id))
                   if (f.extra or {}).get("manual")]
        if ocultos:
            eid = ocultos[0]
        else:
            eid = con.execute(t.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=NOMBRE_ESTUDIO_MANUAL, producto="", catalogo_id=None,
                tema="", idioma=_idioma(idiomas.de_proyecto(cliente)), pais=None, estado="revisando", archivado=False,
                generacion=0, extra={"manual": True})).inserted_primary_key[0]
        nid = con.execute(sa.select(a.c.id).where(a.c.estudio_id == eid, a.c.cliente == cliente, a.c.tipo == "nucleo")
                          .order_by(a.c.id)).scalar()
        if nid is None:
            nid = con.execute(a.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=eid, padre_id=None, tipo="nucleo", base=None,
                orden=0, generacion=0, nombre=NOMBRE_NUCLEO_MANUAL, deseo="", resumen="", estado="propuesto", persona_id=None,
                extra={}, **_SUB_VACIO)).inserted_primary_key[0]
    return eid, nid


def _insertar_sub_manual(cliente, campos, estado, persona_id=None, extra=None):
    eid, nid = estudio_manual(cliente)
    a, ahora = db.avatar, db.ahora()
    with db.conectar() as con:
        orden = int(con.execute(sa.select(sa.func.count()).select_from(a).where(a.c.padre_id == nid)).scalar() or 0)
        return con.execute(a.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=eid, padre_id=nid, tipo="sub", orden=orden,
            generacion=0, estado=estado, persona_id=persona_id, resumen="", extra=dict(extra or {}),
            **{**_SUB_VACIO, "base": "emocion", **campos})).inserted_primary_key[0]


def crear_avatar_manual(cliente, campos):
    """Avatar escrito a mano: vive en el estudio oculto y nace aprobado (su
    persona se crea con origen `manual`). Devuelve el id del avatar."""
    limpios = validar_campos_avatar({k: v for k, v in dict(campos or {}).items() if k in AVATAR_EDITABLES})
    if not limpios.get("nombre"):
        raise ErrorDatos(gettext("El avatar necesita un nombre."))
    aid = _insertar_sub_manual(cliente, limpios, "propuesto", extra={"manual": True})
    aprobar_avatar(cliente, aid)
    return aid


def campos_desde_persona(p):
    """La ficha de avatar que corresponde a una persona sin avatar (mapeo inverso de `persona_desde_avatar`)."""
    ex = dict((p or {}).get("extra") or {})
    return validar_campos_avatar({
        "nombre": p.get("nombre") or "?", "deseo": p.get("resumen") or "", "demografia": p.get("descripcion") or "",
        "edad_rango": p.get("edad_rango") or "", "tono": p.get("tono") or "", "situaciones": list(p.get("senales_visuales") or []),
        "palabras_clave": list(p.get("palabras_clave") or []), "identidad": ex.get("identidad") or {},
        "conciencia": ex.get("conciencia") if isinstance(ex.get("conciencia"), dict) else {"nivel": ex.get("conciencia") or ""},
        "encaje_producto": ex.get("encaje_producto") or ""})


def avatar_desde_persona(cliente, persona_id):
    """El avatar con el que se edita una persona sin avatar (creada en Sprints o
    sugerida por IA): se crea UNA vez en el estudio oculto con los campos de la
    persona y enlazado a ella; si ya existe, se devuelve."""
    p = sprints_datos.persona(cliente, persona_id)
    if not p:
        raise ErrorDatos(gettext("Esa persona no existe."))
    a = db.avatar
    with db.conectar() as con:
        ya = con.execute(sa.select(a.c.id).where(a.c.cliente == cliente, a.c.persona_id == persona_id, a.c.tipo == "sub")
                         .order_by(a.c.id)).scalar()
    if ya:
        return ya
    aid = _insertar_sub_manual(cliente, campos_desde_persona(p), "descartado" if p.get("archivada") else "aprobado",
                               persona_id=persona_id, extra={"manual": True, "desde_persona": True})
    eid, _ = estudio_manual(cliente)
    sprints_datos.actualizar_persona(cliente, persona_id, extra={**dict(p.get("extra") or {}), "avatar_id": aid, "estudio_id": eid})
    return aid


def lista_avatares(cliente):
    """Todos los avatares del proyecto (spec 2026-09-29 §1, §3):
    {"nuevos": sub-avatares propuestos de estudios no archivados (más nuevo primero),
     "aprobados": personas no archivadas (con su avatar si lo tienen), por nombre,
     "otros": descartados y personas archivadas}.
    Cada elemento: {clave ("a<id>" o "p<id>"), avatar, persona, estudio {id, nombre,
    manual, archivado}, nucleo, faltantes, grupo}."""
    from nicho import calidad
    t, a = db.estudio, db.avatar
    with db.conectar() as con:
        estudios_ = {f.id: {"id": f.id, "nombre": f.nombre, "manual": bool((f.extra or {}).get("manual")), "archivado": bool(f.archivado)}
                     for f in con.execute(sa.select(t.c.id, t.c.nombre, t.c.extra, t.c.archivado).where(t.c.cliente == cliente))}
        filas = [_a_dict(f) for f in con.execute(sa.select(a).where(a.c.cliente == cliente).order_by(a.c.id.desc()))]
    nucleos = {f["id"]: f["nombre"] for f in filas if f["tipo"] == "nucleo"}
    subs = [f for f in filas if f["tipo"] == "sub"]
    personas = {p["id"]: p for p in sprints_datos.personas(cliente, incluir_archivadas=True)}
    representante = {}
    for s in subs:
        if s.get("persona_id") in personas and s["persona_id"] not in representante:
            representante[s["persona_id"]] = s["id"]

    def item(grupo, avatar=None, persona=None):
        est = estudios_.get(avatar["estudio_id"]) if avatar else None
        base = avatar if avatar else campos_desde_persona(persona)
        return {"clave": f"a{avatar['id']}" if avatar else f"p{persona['id']}", "avatar": avatar, "persona": persona, "estudio": est,
                "nucleo": nucleos.get(avatar["padre_id"]) if avatar else None, "grupo": grupo,
                "faltantes": calidad.faltantes(base, con_evidencia=bool(avatar) and not (est or {}).get("manual"))}

    nuevos, aprobados, otros = [], [], []
    for s in subs:
        est = estudios_.get(s["estudio_id"]) or {}
        p = personas.get(s.get("persona_id"))
        if p and representante.get(p["id"]) != s["id"]:
            continue                                            # la persona ya está representada por otro avatar
        if s["estado"] == "propuesto" and not p:
            if not est.get("archivado"):
                nuevos.append(item("nuevo", s))
        elif s["estado"] == "aprobado" and p and not p.get("archivada"):
            aprobados.append(item("aprobado", s, p))
        else:
            otros.append(item("otro", s, p))
    for pid, p in personas.items():
        if pid not in representante:
            (otros if p.get("archivada") else aprobados).append(item("otro" if p.get("archivada") else "aprobado", persona=p))
    aprobados.sort(key=lambda x: ((x["persona"] or {}).get("nombre") or "").lower())
    return {"nuevos": nuevos, "aprobados": aprobados, "otros": otros}


def resumen_avatares(cliente, muestra=12):
    """Lo liviano que muestra la pestaña Nicho: conteos y hasta `muestra` nombres."""
    l = lista_avatares(cliente)
    vivos = l["nuevos"] + l["aprobados"]
    return {"nuevos": len(l["nuevos"]), "aprobados": len(l["aprobados"]), "incompletos": sum(1 for x in vivos if x["faltantes"]),
            "muestra": [{"clave": x["clave"], "nombre": ((x["avatar"] or {}).get("nombre") if x["grupo"] == "nuevo" else (x["persona"] or {}).get("nombre")),
                         "grupo": x["grupo"], "incompleto": bool(x["faltantes"])} for x in vivos[:muestra]]}

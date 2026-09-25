"""
Único escritor de guion_lote, guion y guion_video (pipeline de Flow Plus,
spec 2026-09-25). Una fila con un trabajo en curso (lote `leyendo`, video
`recortando`/`armando`, imágenes `escribiendo`) lleva `iniciado_en`; si pasa
MINUTOS_TRABAJO sin terminar (el proceso se reinició a mitad de la llamada)
se lee como terminada con error, y un resultado que llegue tarde se descarta
(el gasto sí se suma).
"""
from datetime import datetime, timedelta

import sqlalchemy as sa

import db
from guiones.refinador import Conflicto, DatoInvalido, NoExiste

MINUTOS_TRABAJO = 6
INTERRUMPIDO = "Se interrumpió; vuelve a intentarlo."
MAX_TEXTO = 60000


def _limite():
    return (datetime.now() - timedelta(minutes=MINUTOS_TRABAJO)).isoformat(timespec="seconds")


def _dict(fila):
    return dict(fila._mapping) if fila is not None else None


# ---------------------------------------------------------------- lotes ---

def crear_lote(cliente, texto, fuente="texto", notion_page_id=None):
    texto = (texto or "").strip() if isinstance(texto, str) else ""
    if fuente == "texto" and not texto:
        raise DatoInvalido("Pega el guion primero.")
    if fuente == "notion" and not notion_page_id:
        raise DatoInvalido("Falta la página de Notion.")
    if len(texto) > MAX_TEXTO:
        raise DatoInvalido("El guion es demasiado largo (máximo 60 000 caracteres).")
    titulo = next((ln.strip() for ln in texto.splitlines() if ln.strip()), "Guion de Notion" if fuente == "notion" else "Guion")
    ahora = db.ahora()
    with db.conectar() as con:
        r = con.execute(sa.insert(db.guion_lote).values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, fuente=fuente, notion_page_id=notion_page_id,
            titulo=titulo[:200], texto_crudo=texto, estado="leyendo", usd=0.0, iniciado_en=ahora, extra={}))
        return int(r.inserted_primary_key[0])


def _vencer_lotes(con, cliente=None, lote_id=None):
    t = db.guion_lote
    q = t.update().where(t.c.estado == "leyendo", t.c.iniciado_en < _limite())
    q = q.where(t.c.cliente == cliente) if cliente is not None else q.where(t.c.id == lote_id)
    con.execute(q.values(estado="error", aviso=INTERRUMPIDO))


def lote_para_leer(lote_id):
    t = db.guion_lote
    with db.conectar() as con:
        _vencer_lotes(con, lote_id=lote_id)
        return _dict(con.execute(sa.select(t).where(t.c.id == lote_id)).first())


def poner_texto_lote(lote_id, titulo, texto):
    t = db.guion_lote
    with db.conectar() as con:
        con.execute(t.update().where(t.c.id == lote_id, t.c.estado == "leyendo").values(
            texto_crudo=(texto or "")[:MAX_TEXTO], titulo=((titulo or "").strip() or "Guion de Notion")[:200],
            actualizado_en=db.ahora()))


def terminar_lectura(lote_id, lecturas, usd):
    """Un guion por lectura, solo si el lote sigue `leyendo`; [] si llegó tarde."""
    t, g = db.guion_lote, db.guion
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(t.update().where(t.c.id == lote_id).values(usd=t.c.usd + float(usd or 0)))
        r = con.execute(t.update().where(t.c.id == lote_id, t.c.estado == "leyendo")
                        .values(estado="leido", aviso=None, actualizado_en=ahora))
        if r.rowcount != 1:
            return []
        cliente = con.execute(sa.select(t.c.cliente).where(t.c.id == lote_id)).scalar()
        ids = []
        for i, lec in enumerate(lecturas):
            r = con.execute(sa.insert(g).values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, lote_id=lote_id, orden=i,
                titulo=(lec.get("titulo") or f"Guion {i + 1}")[:200], lectura=lec, estado="leido", extra={}))
            ids.append(int(r.inserted_primary_key[0]))
        return ids


def fallar_lote(lote_id, aviso, usd=0.0):
    t = db.guion_lote
    with db.conectar() as con:
        con.execute(t.update().where(t.c.id == lote_id).values(usd=t.c.usd + float(usd or 0)))
        con.execute(t.update().where(t.c.id == lote_id, t.c.estado == "leyendo")
                    .values(estado="error", aviso=aviso, actualizado_en=db.ahora()))


def reintentar_lote(cliente, lote_id):
    t = db.guion_lote
    with db.conectar() as con:
        if con.execute(sa.select(t.c.id).where(t.c.id == lote_id, t.c.cliente == cliente)).first() is None:
            raise NoExiste("Ese guion no existe.")
        ahora = db.ahora()
        r = con.execute(t.update().where(t.c.id == lote_id, t.c.estado == "error")
                        .values(estado="leyendo", aviso=None, iniciado_en=ahora, actualizado_en=ahora))
        if r.rowcount != 1:
            raise Conflicto("Ese guion no está en error.")


def lotes(cliente):
    t, g, v = db.guion_lote, db.guion, db.guion_video
    n_videos = sa.select(sa.func.count()).where(v.c.guion_id == g.c.id).scalar_subquery()
    with db.conectar() as con:
        _vencer_lotes(con, cliente=cliente)
        filas = [_dict(f) for f in con.execute(
            sa.select(t.c.id, t.c.titulo, t.c.estado, t.c.aviso, t.c.fuente, t.c.creado_en)
            .where(t.c.cliente == cliente).order_by(t.c.id.desc()))]
        guiones = {}
        for f in con.execute(sa.select(g.c.id, g.c.lote_id, g.c.titulo, g.c.estado, n_videos.label("n_videos"))
                             .where(g.c.cliente == cliente).order_by(g.c.orden, g.c.id)):
            guiones.setdefault(f.lote_id, []).append(
                {"id": f.id, "titulo": f.titulo or "", "estado": f.estado, "n_videos": int(f.n_videos or 0)})
    for f in filas:
        f["guiones"] = guiones.get(f["id"], [])
    return filas


# -------------------------------------------------------------- guiones ---

def guion(cliente, guion_id):
    g, t, v = db.guion, db.guion_lote, db.guion_video
    with db.conectar() as con:
        d = _dict(con.execute(sa.select(g).where(g.c.id == guion_id, g.c.cliente == cliente)).first())
        if d is None:
            return None
        d["texto_crudo"] = con.execute(sa.select(t.c.texto_crudo).where(t.c.id == d["lote_id"])).scalar() or ""
        d["videos"] = [_dict(f) for f in con.execute(
            sa.select(v.c.id, v.c.version_n, v.c.nombre, v.c.estado, v.c.estado_imagenes)
            .where(v.c.guion_id == guion_id).order_by(v.c.version_n))]
    d["lectura"] = d.get("lectura") or {}
    return d


def guardar_lectura(cliente, guion_id, lectura):
    g = db.guion
    with db.conectar() as con:
        r = con.execute(g.update().where(g.c.id == guion_id, g.c.cliente == cliente, g.c.estado == "leido").values(
            lectura=lectura, titulo=(lectura.get("titulo") or "Guion")[:200], actualizado_en=db.ahora()))
        if r.rowcount == 1:
            return
        if con.execute(sa.select(g.c.id).where(g.c.id == guion_id, g.c.cliente == cliente)).first() is None:
            raise NoExiste("Ese guion no existe.")
        raise Conflicto("Este guion ya está confirmado; duplícalo para cambiar la lectura.")


def confirmar(cliente, guion_id):
    g = db.guion
    with db.conectar() as con:
        fila = con.execute(sa.select(g).where(g.c.id == guion_id, g.c.cliente == cliente)).first()
        if fila is None:
            raise NoExiste("Ese guion no existe.")
        if not (fila.lectura or {}).get("lineas"):
            raise DatoInvalido("El guion necesita al menos una línea antes de confirmarlo.")
        r = con.execute(g.update().where(g.c.id == guion_id, g.c.estado == "leido")
                        .values(estado="confirmado", actualizado_en=db.ahora()))
        if r.rowcount != 1:
            raise Conflicto("Este guion ya estaba confirmado.")


def duplicar(cliente, guion_id):
    g = db.guion
    with db.conectar() as con:
        fila = con.execute(sa.select(g).where(g.c.id == guion_id, g.c.cliente == cliente)).first()
        if fila is None:
            raise NoExiste("Ese guion no existe.")
        orden = con.execute(sa.select(sa.func.max(g.c.orden)).where(g.c.lote_id == fila.lote_id)).scalar() or 0
        ahora = db.ahora()
        titulo = f"{(fila.titulo or 'Guion')[:190]} (copia)"
        lectura = dict(fila.lectura or {}, titulo=titulo)
        r = con.execute(sa.insert(g).values(cliente=cliente, creado_en=ahora, actualizado_en=ahora,
                                            lote_id=fila.lote_id, orden=orden + 1, titulo=titulo,
                                            lectura=lectura, estado="leido", extra={}))
        return int(r.inserted_primary_key[0])


# --------------------------------------------------------------- videos ---

def nombre_version(config, version_n):
    dur = config.get("duracion_objetivo")
    modo = "voz en off" if config.get("modo") == "voiceover" else "diálogo"
    return f"{f'{dur} s' if dur else 'Completo'} · {modo} · v{version_n}"


_DEFECTOS_VIDEO = (("config", dict), ("recorte", dict), ("clips", list), ("hooks_alt", dict),
                   ("validaciones", list), ("avisos", list), ("imagenes", dict), ("extra", dict))


def _vencer_video(con, video_id):
    v, lim = db.guion_video, _limite()
    con.execute(v.update().where(v.c.id == video_id, v.c.estado == "recortando", v.c.iniciado_en < lim)
                .values(estado="configurando", aviso=INTERRUMPIDO))
    con.execute(v.update().where(v.c.id == video_id, v.c.estado == "armando", v.c.iniciado_en < lim)
                .values(estado="error", aviso=INTERRUMPIDO))
    con.execute(v.update().where(v.c.id == video_id, v.c.estado_imagenes == "escribiendo", v.c.iniciado_en < lim)
                .values(estado_imagenes="error", aviso_imagenes=INTERRUMPIDO))


def _video_completo(con, video_id):
    d = _dict(con.execute(sa.select(db.guion_video).where(db.guion_video.c.id == video_id)).first())
    if d is None:
        return None
    g = db.guion
    d["guion"] = _dict(con.execute(sa.select(g.c.id, g.c.titulo, g.c.lectura, g.c.lote_id)
                                   .where(g.c.id == d["guion_id"])).first())
    d["guion"]["lectura"] = d["guion"]["lectura"] or {}
    for clave, fabrica in _DEFECTOS_VIDEO:
        if d.get(clave) is None:
            d[clave] = fabrica()
    return d


def _bloquear_video(con, cliente, video_id):
    """Toma el lock de escritura de SQLite antes de leer (como experimentos._bloquear)."""
    v = db.guion_video
    r = con.execute(v.update().where(v.c.id == video_id, v.c.cliente == cliente)
                    .values(actualizado_en=v.c.actualizado_en))
    if r.rowcount != 1:
        raise NoExiste("Esa versión no existe.")
    _vencer_video(con, video_id)
    return con.execute(sa.select(v).where(v.c.id == video_id)).first()


def crear_video(cliente, guion_id, config, recorte=None, plan=None, estado="configurando"):
    g, v = db.guion, db.guion_video
    with db.conectar() as con:
        r = con.execute(g.update().where(g.c.id == guion_id, g.c.cliente == cliente)
                        .values(actualizado_en=g.c.actualizado_en))
        if r.rowcount != 1:
            raise NoExiste("Ese guion no existe.")
        if con.execute(sa.select(g.c.estado).where(g.c.id == guion_id)).scalar() != "confirmado":
            raise Conflicto("Confirma el guion antes de armar un video.")
        n = (con.execute(sa.select(sa.func.max(v.c.version_n)).where(v.c.guion_id == guion_id)).scalar() or 0) + 1
        ahora = db.ahora()
        r = con.execute(sa.insert(v).values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, guion_id=guion_id, version_n=n,
            nombre=nombre_version(config, n), config=config, recorte=recorte or {}, plan=plan, estado=estado,
            estado_imagenes="ninguno", iniciado_en=ahora if estado == "armando" else None, usd=0.0, extra={}))
        return int(r.inserted_primary_key[0])


def video(cliente, video_id):
    v = db.guion_video
    with db.conectar() as con:
        if con.execute(sa.select(v.c.id).where(v.c.id == video_id, v.c.cliente == cliente)).first() is None:
            return None
        _vencer_video(con, video_id)
        return _video_completo(con, video_id)


def video_para_trabajo(video_id):
    with db.conectar() as con:
        _vencer_video(con, video_id)
        return _video_completo(con, video_id)


def guardar_config(cliente, video_id, config):
    v = db.guion_video
    with db.conectar() as con:
        fila = _bloquear_video(con, cliente, video_id)
        if fila.estado != "configurando":
            raise Conflicto("Esta versión ya no se puede cambiar; crea una versión nueva.")
        con.execute(v.update().where(v.c.id == video_id).values(
            config=config, nombre=nombre_version(config, fila.version_n), aviso=None, actualizado_en=db.ahora()))


_YA_TRABAJANDO = {"recortando": "Claude está proponiendo qué quitar; espera a que termine.",
                  "armando": "Claude está armando los clips; espera a que termine.",
                  "armado": "Esta versión ya está armada; crea una versión nueva para cambiarla."}


def empezar(cliente, video_id, estado_nuevo, desde):
    v = db.guion_video
    with db.conectar() as con:
        fila = _bloquear_video(con, cliente, video_id)
        if fila.estado not in desde:
            raise Conflicto(_YA_TRABAJANDO.get(fila.estado, "Esta versión no admite esa acción ahora."))
        ahora = db.ahora()
        con.execute(v.update().where(v.c.id == video_id)
                    .values(estado=estado_nuevo, aviso=None, iniciado_en=ahora, actualizado_en=ahora))


def terminar_recorte(video_id, propuesta, motivos, quitadas, usd):
    v = db.guion_video
    con_motivos = {k: v for k, v in (motivos or {}).items() if k != "1"}
    con_propuesta = [n for n in (propuesta or []) if n != 1]
    con_quitadas = [n for n in (quitadas or []) if n != 1]
    with db.conectar() as con:
        con.execute(v.update().where(v.c.id == video_id).values(usd=v.c.usd + float(usd or 0)))
        r = con.execute(v.update().where(v.c.id == video_id, v.c.estado == "recortando").values(
            estado="configurando", recorte={"propuesta": con_propuesta, "motivos": con_motivos,
                                            "quitadas": sorted(con_quitadas)}, actualizado_en=db.ahora()))
        return r.rowcount == 1


def fallar(video_id, aviso, usd=0.0):
    v = db.guion_video
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(v.update().where(v.c.id == video_id).values(usd=v.c.usd + float(usd or 0)))
        con.execute(v.update().where(v.c.id == video_id, v.c.estado == "recortando")
                    .values(estado="configurando", aviso=aviso, actualizado_en=ahora))
        con.execute(v.update().where(v.c.id == video_id, v.c.estado == "armando")
                    .values(estado="error", aviso=aviso, actualizado_en=ahora))


def guardar_quitadas(cliente, video_id, quitadas):
    try:
        ns = sorted({int(n) for n in quitadas})
    except (TypeError, ValueError):
        raise DatoInvalido("Las líneas a quitar tienen que ser números.") from None
    if 1 in ns:
        raise DatoInvalido("La línea 1 (el hook) no se puede quitar.")
    v = db.guion_video
    with db.conectar() as con:
        fila = _bloquear_video(con, cliente, video_id)
        if fila.estado != "configurando":
            raise Conflicto("Esta versión ya no se puede cambiar; crea una versión nueva.")
        recorte = dict(fila.recorte or {}, quitadas=ns)
        con.execute(v.update().where(v.c.id == video_id).values(recorte=recorte, actualizado_en=db.ahora()))

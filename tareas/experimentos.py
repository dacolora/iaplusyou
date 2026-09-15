"""
Tareas del worker para Experimentos: lanzar (crea objetos en Meta, en pausa;
max_intentos=1 y hook de interrupción como meta_publicar), refrescar métricas
de un experimento y la periódica que refresca todos los que corren.
"""
import sqlalchemy as sa

import cola
import db
import experimentos
import lanzador
import trabajos
from tareas import al_interrumpir, registrar


def job_id_lanzar(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__lanzar"


def job_id_refrescar(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__refrescar"


@al_interrumpir("exp_lanzar")
def interrumpida(tarea, mensaje):
    p = tarea["payload"]
    ex = experimentos.obtener(p["cliente"], p["experimento_id"])
    if ex and ex["estado"] == "lanzando":
        experimentos.actualizar(p["cliente"], p["experimento_id"], estado="error", error=mensaje)


@registrar("exp_lanzar")
def exp_lanzar(tarea):
    p = tarea["payload"]
    job_id = tarea.get("job_id")
    return lanzador.lanzar(p["cliente"], p["experimento_id"],
                           on_etapa=lambda nombre: trabajos.reportar(job_id, etapa=nombre))


@registrar("exp_refrescar")
def exp_refrescar(tarea):
    p = tarea["payload"]
    n = lanzador.refrescar(p["cliente"], p["experimento_id"])
    return f"Métricas actualizadas ({n} anuncios)."


@registrar("exp_refrescar_todos")
def exp_refrescar_todos(tarea):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento.c.id, db.experimento.c.cliente).where(
            db.experimento.c.legado.is_(False), db.experimento.c.estado == "corriendo")).all()
    for eid, cliente in filas:
        cola.encolar("exp_refrescar", {"cliente": cliente, "experimento_id": eid}, cliente=cliente,
                     job_id=job_id_refrescar(cliente, eid), duracion_estimada=30, max_intentos=2)
    return f"{len(filas)} experimentos en cola."

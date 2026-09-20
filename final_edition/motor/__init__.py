"""Motor de render del editor (spec editor §2): compila un documento resuelto
a un plan de ffmpeg y lo ejecuta, por tramos si hace falta."""
import os

from final_edition.documento import duracion_ms
from final_edition.motor import compilador, render as render_mod, tramos


def renderizar(doc, rutas, salida, on_etapa=None, nucleos=1):
    """`doc` ya resuelto (documento.resolver). `rutas`: {material_id: ruta}
    más `png:<clip_id>` y `ass`. Devuelve {archivo, miniatura, duracion_s,
    tramos, con_ass}."""
    avisar = on_etapa or (lambda _n: None)
    con_ass = render_mod.tiene_libass()
    if not con_ass:
        avisar("Subtítulos sin libass: omitidos")
    total = duracion_ms(doc)
    if total == 0:
        plan = compilador.compilar(doc, rutas, con_ass=False)
        render_mod.ejecutar(plan, salida)
        render_mod.validar(salida, plan)
        return {"archivo": salida, "miniatura": salida, "duracion_s": 0.0, "tramos": 1, "con_ass": False}
    ventanas = tramos.partir(doc)
    if len(ventanas) == 1:
        plan = compilador.compilar(doc, rutas, con_ass=con_ass)
        avisar("Renderizando")
        render_mod.ejecutar(plan, salida, ass_ruta=rutas.get("ass"))
    else:
        parciales = []
        for i, v in enumerate(ventanas):
            avisar(f"Renderizando tramo {i + 1}/{len(ventanas)}")
            plan_i = compilador.compilar(doc, rutas, ventana=v, con_ass=con_ass)
            parcial = f"{salida}.tramo{i}.mp4"
            # compilador hornea `subtitles='{rutas['ass']}'` igual en todos los tramos (no lo varía por ventana), y cada ejecutar() es síncrono, así que reescribir ese mismo archivo en cada vuelta es seguro.
            render_mod.ejecutar(plan_i, parcial, ass_ruta=rutas.get("ass"))
            parciales.append(parcial)
        avisar("Uniendo tramos")
        render_mod.concatenar(parciales, salida)
        for p in parciales:
            os.remove(p)
        plan = compilador.compilar(doc, rutas, con_ass=con_ass)
    dur = render_mod.validar(salida, plan, tolerancia_s=0.3 if len(ventanas) > 1 else 0.2)
    mini = os.path.splitext(salida)[0] + "_miniatura.png"
    render_mod.miniatura(salida, mini, min(doc.get("miniatura_ms") or 0, total - 1))
    return {"archivo": salida, "miniatura": mini, "duracion_s": dur, "tramos": len(ventanas),
            "con_ass": con_ass and bool(plan.ass_texto)}

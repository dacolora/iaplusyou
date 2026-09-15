"""
Tareas del worker para Final Edition (Crear): preparar el guion base de una
sesión y producir una pieza final por idioma/país. Los cuerpos viven en
`final_edition` (`preparar_guion` / `producir`); acá solo se cablea el payload,
el reporte de etapas y el mensaje que ve la persona.

Ids de trabajo (los mismos que usa dashboard para encolar y consultar):
  final_guion    -> f"{cliente}__{cf_id}__final_guion"            (max_intentos=2)
  final_producir -> f"{cliente}__{cf_id}__{idioma}_{pais}__final"  (max_intentos=1)

`final_producir` va con max_intentos=1: cada capa cobra (voz, música,
localización) y `producir` ya deja la pieza en `error` con el motivo; la
persona decide si vuelve a producir desde la tarjeta.
"""
import creative_flow
import final_edition
import trabajos
from final_edition import ETAPAS_FINAL
from tareas import al_interrumpir, registrar


def job_id_guion(cliente, cf_id):
    return f"{cliente}__{cf_id}__final_guion"


def job_id_final(cliente, cf_id, idioma, pais):
    return f"{cliente}__{cf_id}__{idioma}_{pais}__final"


@registrar("final_guion")
def ejecutar_guion(tarea):
    """Escribe el guion base (capa 0) y lo deja guardado en la sesión. Es
    idempotente (sobrescribe el guion), así que puede reintentarse."""
    p = tarea["payload"]
    final_edition.preparar_guion(p["cliente"], p["cf_id"], p.get("opciones") or {})
    return "Guion listo — revísalo y produce las finales."


@registrar("final_producir")
def ejecutar_producir(tarea):
    """Produce la final `idioma`/`pais`. `producir` ya deja la pieza en la base
    (listo / degradada / error) — acá solo se traducen las etapas a la barra
    y se arma el mensaje."""
    p = tarea["payload"]
    cliente, cf_id, idioma, pais = p["cliente"], p["cf_id"], p["idioma"], p["pais"]
    job_id = tarea.get("job_id") or job_id_final(cliente, cf_id, idioma, pais)
    _, resumen = final_edition.producir(
        cliente, cf_id, idioma, pais, p.get("opciones") or {},
        on_etapa=lambda nombre: trabajos.reportar(job_id, etapa=nombre))
    if (resumen or {}).get("estado") == "degradada":
        return f"Final {idioma}_{pais} lista (sin voz/música)."
    return f"Final {idioma}_{pais} lista."


@al_interrumpir("final_producir")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad de una final: la pieza quedaría en `generando`
    para siempre. Solo si sigue ahí pasa a error (si ya terminó por otro
    camino no se pisa). final_guion no necesita hook: no deja estado a medias."""
    p = tarea["payload"]
    cliente = p["cliente"]
    final_id = f"{p['cf_id']}__{p['idioma']}_{p['pais']}"
    entry = creative_flow.final_por_legado(cliente, final_id)
    if entry is None or entry.get("estado") != "generando":
        return
    creative_flow.actualizar_final(cliente, final_id, estado="error", error=mensaje)


__all__ = ["ETAPAS_FINAL", "ejecutar_guion", "ejecutar_producir", "interrumpida", "job_id_guion", "job_id_final"]

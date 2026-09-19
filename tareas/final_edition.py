"""
Tareas del worker para Final Edition (Crear): preparar el guion base de una
sesión y producir una pieza final por idioma/país. Los cuerpos viven en
`final_edition` (`preparar_guion` / `producir`); acá solo se cablea el payload,
el reporte de etapas y el mensaje que ve la persona.

Ids de trabajo (los mismos que usa dashboard para encolar y consultar):
  final_guion    -> f"{cliente}__{cf_id}__final_guion"            (max_intentos=2)
  final_producir -> f"{cliente}__{cf_id}__{idioma}_{pais}__final"  (max_intentos=1)
                    (variante n: f"{cliente}__{cf_id}__{idioma}_{pais}__v{n}__final")

`final_producir` va con max_intentos=1: cada capa cobra (voz, música,
localización) y `producir` ya deja la pieza en `error` con el motivo; la
persona decide si vuelve a producir desde la tarjeta.
"""
import creative_flow
import final_edition
import trabajos
from final_edition import ETAPAS_FINAL
from tareas import al_interrumpir, ref_sufijo, registrar


def job_id_guion(cliente, cf_id):
    return f"{cliente}__{cf_id}__final_guion"


def job_id_final(cliente, cf_id, idioma, pais, variante=None):
    return f"{cliente}__{legado_final(cf_id, idioma, pais, variante)}__final"


def legado_final(cf_id, idioma, pais, variante=None):
    """Mismo legado_id que `creative_flow.crear_final` (sufijo `__v<n>` si hay
    variante)."""
    base = f"{cf_id}__{idioma}_{pais}"
    return f"{base}__v{int(variante)}" if variante is not None else base


def _variante(payload):
    return (payload.get("opciones") or {}).get("variante")


@registrar("final_guion")
def ejecutar_guion(tarea):
    """Escribe el guion base (capa 0) y lo deja guardado en la sesión. Es
    idempotente por tarea (sobrescribe el guion de LA MISMA tarea si se
    reintenta), pero cada tarea nueva ("Volver a escribir con IA") deja su
    propio cobro."""
    p = tarea["payload"]
    final_edition.preparar_guion(p["cliente"], p["cf_id"], p.get("opciones") or {}, ref_sufijo=ref_sufijo(tarea))
    return "Guion listo — revísalo y produce las finales."


@registrar("final_producir")
def ejecutar_producir(tarea):
    """Produce la final `idioma`/`pais`. `producir` ya deja la pieza en la base
    (listo / degradada / error) — acá solo se traducen las etapas a la barra
    y se arma el mensaje."""
    p = tarea["payload"]
    cliente, cf_id, idioma, pais = p["cliente"], p["cf_id"], p["idioma"], p["pais"]
    job_id = tarea.get("job_id") or job_id_final(cliente, cf_id, idioma, pais, variante=_variante(p))
    _, resumen = final_edition.producir(
        cliente, cf_id, idioma, pais, p.get("opciones") or {},
        on_etapa=lambda nombre: trabajos.reportar(job_id, etapa=nombre), ref_sufijo=ref_sufijo(tarea))
    nombre = f"Final {idioma}_{pais}"
    if _variante(p) is not None:
        nombre = f"Variante {_variante(p)} de la final {idioma}_{pais}"
    if (resumen or {}).get("estado") == "degradada":
        return f"{nombre} lista (sin voz/música)."
    return f"{nombre} lista."


@al_interrumpir("final_producir")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad de una final: la pieza quedaría en `generando`
    para siempre. Solo si sigue ahí pasa a error (si ya terminó por otro
    camino no se pisa). final_guion no necesita hook: no deja estado a medias."""
    p = tarea["payload"]
    cliente = p["cliente"]
    final_id = legado_final(p["cf_id"], p["idioma"], p["pais"], _variante(p))
    entry = creative_flow.final_por_legado(cliente, final_id)
    if entry is None or entry.get("estado") != "generando":
        return
    creative_flow.actualizar_final(cliente, final_id, estado="error", error=mensaje)


__all__ = ["ETAPAS_FINAL", "ejecutar_guion", "ejecutar_producir", "interrumpida", "job_id_guion", "job_id_final"]

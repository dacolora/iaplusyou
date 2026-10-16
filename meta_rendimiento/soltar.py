"""Soltar las cuentas de Meta de un proyecto cuando pierde su conexión (Desconectar, volver a modo propia, desasignar,
desconectar la agencia): /privacidad y /eliminar-datos prometen que se borra lo copiado de Meta (ruling R21,
2026-10-08; E2-R2 y S1, 2026-10-10).

Hasta PND-207 (decisión 2026-10-13) esto vivía en `dashboard._soltar_cuentas_meta` y cada ruta tenía que acordarse de
llamarlo: un llamador nuevo de `meta_conexion.borrar` o `meta_agencia.desasignar` dejaba las copias de un proyecto ya
desconectado. Ahora lo llaman ellas mismas (por `meta_conexion.soltar_copias`) y la ruta solo avisa si algo falló."""
import logging

log = logging.getLogger("creatv.meta_rendimiento.soltar")


def soltar(cliente):
    """Borra las métricas copiadas de las cuentas del proyecto y las deja libres para otro proyecto
    (`cuentas.elegir(cliente, [])`, que se lleva también los análisis «Cómo mejorarlo» de sus anuncios de fuente Meta y,
    después de esas filas, la imagen y el video que copiaron a R2), sus evaluaciones con IA (guardan nombres y métricas
    de anuncios de Meta; el gasto queda en `gasto`) y las miniaturas que esas evaluaciones copiaron a R2.

    El orden importa: primero se leen las claves de R2 (salen de las filas), después se borran las filas (lo que guarda
    los nombres y las métricas) y al final las miniaturas, con un solo cliente de R2: un R2 lento o caído nunca deja
    nombres ni métricas guardados. Los tres borrados son independientes: si uno falla, los otros se hacen igual.
    Nunca lanza: devuelve el tipo del primer error (nunca su texto: podría arrastrar un token), o None si todo se borró.
    La siguiente desconexión reintenta lo que quedó (las claves se vuelven a calcular de las filas que queden)."""
    from meta_rendimiento import analisis, cuentas, datos  # noqa: PLC0415 — tardío: lo llama meta_conexion

    fallo = None
    try:
        quitadas = cuentas.elegir(cliente, [])
        if quitadas.get("fallos_r2"):          # las filas ya se borraron; quedaron copias en R2 (S1)
            fallo = quitadas["fallos_r2"][0]
    except Exception as e:  # noqa: BLE001 — la desconexión no se deshace por esto
        log.warning("meta rendimiento: no se pudieron borrar las métricas copiadas de %s (%s)", cliente,
                    type(e).__name__)
        fallo = type(e).__name__
    claves = []
    try:
        claves = analisis.claves_miniaturas(cliente)
    except Exception as e:  # noqa: BLE001 — sin las claves no se borran las miniaturas, pero las filas sí
        log.warning("meta rendimiento: no se pudieron leer las miniaturas de %s (%s)", cliente, type(e).__name__)
        fallo = fallo or type(e).__name__
    try:
        datos.borrar_evaluaciones(cliente)
    except Exception as e:  # noqa: BLE001 — ídem; el borrado de arriba no depende de este ni este de aquel
        log.warning("meta rendimiento: no se pudieron borrar las evaluaciones de %s (%s)", cliente, type(e).__name__)
        fallo = fallo or type(e).__name__
    try:
        # Después de las filas y fuera de su camino: lo lento de R2 no retrasa el borrado de lo que guarda los nombres.
        _, fallos_r2 = analisis.borrar_claves(claves)
        if fallos_r2:
            fallo = fallo or fallos_r2[0]
    except Exception as e:  # noqa: BLE001 — `borrar_claves` no lanza; por si acaso, la desconexión sigue
        log.warning("meta rendimiento: no se pudieron borrar las miniaturas de %s (%s)", cliente, type(e).__name__)
        fallo = fallo or type(e).__name__
    return fallo

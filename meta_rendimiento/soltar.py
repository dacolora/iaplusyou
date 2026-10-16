"""Soltar las cuentas de Meta de un proyecto cuando pierde su conexión (Desconectar, volver a modo propia, desasignar,
desconectar la agencia): /privacidad y /eliminar-datos prometen que se borra lo copiado de Meta (ruling R21,
2026-10-08; E2-R2 y S1, 2026-10-10).

Hasta PND-207 (decisión 2026-10-13) esto vivía en `dashboard._soltar_cuentas_meta` y cada ruta tenía que acordarse de
llamarlo: un llamador nuevo de `meta_conexion.borrar` o `meta_agencia.desasignar` dejaba las copias de un proyecto ya
desconectado. Ahora lo llaman ellas mismas (por `meta_conexion.soltar_copias`) y la ruta solo avisa si algo falló."""
import logging

log = logging.getLogger("creatv.meta_rendimiento.soltar")


def barrer(cliente=None):
    """Borra lo copiado de las cuentas que ya no están elegidas en su proyecto (ronda 2 de PND-206/207, 2026-10-15):
    sus métricas en `datos.TABLAS_COPIA`, por lotes y cada lote en su transacción (`datos.borrar_huerfanas`), las
    miniaturas que su copia subió a R2 (leídas ANTES de borrar sus filas y borradas DESPUÉS, solo si la cuenta sigue sin
    elegir) y los análisis «Cómo mejorarlo» de fuente Meta que hubieran quedado (con sus copias en R2). Lo corre
    `meta_rend_limpiar`: la del proyecto que acaba de soltar una cuenta (con `cliente`) y la diaria (todos, también las
    huérfanas de antes de PND-206). Nunca lanza: devuelve (filas borradas, tipos de los errores); lo que falla, lo barre
    la próxima."""
    from meta_rendimiento import creativo, cuentas, datos, miniaturas  # noqa: PLC0415
    from triple_whale import datos as tw_datos  # noqa: PLC0415
    filas, fallos = 0, []
    try:
        huerfanas = sorted(datos.cuentas_huerfanas(cliente))
    except Exception as e:  # noqa: BLE001
        log.warning("meta limpieza: no se pudo calcular qué barrer (%s)", type(e).__name__)
        huerfanas, fallos = [], [type(e).__name__]
    # Primero los aprendizajes (llegan a los prompts de ideas y guiones): los de una cuenta que ya no está elegida
    # pierden el nombre del anuncio, por si falló al quitarla (auditoría de la ronda 2).
    import meta_conexion  # noqa: PLC0415
    for cli in ([cliente] if cliente else meta_conexion.clientes()):
        try:
            cuentas.sin_nombre_de_no_elegidas(cli)
        except Exception as e:  # noqa: BLE001
            log.warning("meta limpieza: no se quitaron nombres de aprendizajes (%s)", type(e).__name__)
            fallos.append(type(e).__name__)
    for cli, act in huerfanas:
        try:
            con_r2 = datos.anuncios_con_miniatura_r2(cli, act)
            filas += datos.borrar_huerfanas(cli, act)
            if con_r2 and cuentas.cuenta(cli, act) is None:       # si la volvieron a elegir, sus miniaturas se quedan
                fallos += miniaturas.borrar(cli, con_r2)
        except Exception as e:  # noqa: BLE001 — una cuenta que falla no frena a las demás
            log.warning("meta limpieza: una cuenta soltada no se barrió (%s)", type(e).__name__)
            fallos.append(type(e).__name__)
    try:
        analisis_huerfanos = sorted(tw_datos.cuentas_meta_huerfanas(cliente))
    except Exception as e:  # noqa: BLE001
        log.warning("meta limpieza: no se pudieron leer los análisis por barrer (%s)", type(e).__name__)
        analisis_huerfanos = []
        fallos.append(type(e).__name__)
    for cli, act in analisis_huerfanos:
        try:
            copiadas = tw_datos.borrar_analisis_meta(cli, [act], solo_no_elegidas=True)
            filas += len(copiadas)
            if copiadas:
                fallos += creativo.borrar_copias(cli, copiadas)[1]
        except Exception as e:  # noqa: BLE001
            log.warning("meta limpieza: unos análisis de una cuenta soltada no se borraron (%s)", type(e).__name__)
            fallos.append(type(e).__name__)
    return filas, fallos


def soltar(cliente):
    """Suelta las cuentas del proyecto (`cuentas.elegir(cliente, [])`: dejan de mostrarse y quedan libres para otro
    proyecto al instante, sus análisis «Cómo mejorarlo» de fuente Meta se borran con sus copias en R2 y sus métricas
    copiadas las borra por lotes la limpieza que encola, en los minutos siguientes), borra sus evaluaciones con IA
    (guardan nombres y métricas
    de anuncios de Meta; el gasto queda en `gasto`), las miniaturas que esas evaluaciones copiaron a R2 y el nombre del
    anuncio de los aprendizajes guardados desde un análisis de Meta (PND-295: la lección se queda).

    El orden importa: primero se leen las claves de R2 (salen de las filas), después se borran las filas (lo que guarda
    los nombres y las métricas) y al final las miniaturas, con un solo cliente de R2: un R2 lento o caído nunca deja
    nombres ni métricas guardados. Cada paso es independiente: si uno falla, los otros se hacen igual.
    Nunca lanza: devuelve el tipo del primer error (nunca su texto: podría arrastrar un token), o None si todo se borró.
    La siguiente desconexión reintenta lo que quedó (las claves se vuelven a calcular de las filas que queden)."""
    from meta_rendimiento import analisis, cuentas, datos  # noqa: PLC0415 — tardío: lo llama meta_conexion

    fallo = None
    try:
        quitadas = cuentas.elegir(cliente, [])   # las cuentas al instante; sus métricas, la limpieza que encola
        if quitadas.get("fallos_r2"):          # los análisis ya se borraron; quedaron copias en R2 (S1)
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
        # PND-295 (decisión 2026-10-13): un aprendizaje que la persona guardó desde un análisis de un anuncio de Meta
        # se queda (es una nota que guardó a propósito), pero sin el nombre del anuncio, que es dato de Meta. El texto
        # se rehace en el idioma del proyecto, como se guardan los aprendizajes.
        import idiomas  # noqa: PLC0415
        import proyectos  # noqa: PLC0415
        from doctrina import aprendizajes  # noqa: PLC0415
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            proyectos.reescribir_aprendizajes(cliente, aprendizajes.sin_nombre_de_meta)
    except Exception as e:  # noqa: BLE001 — ídem: los demás borrados no dependen de este
        log.warning("meta rendimiento: no se quitaron los nombres de Meta de los aprendizajes de %s (%s)", cliente,
                    type(e).__name__)
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

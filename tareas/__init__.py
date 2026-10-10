"""
Registro de tipos de tarea que ejecuta el worker. Cada módulo de tareas/ se
importa acá para que sus @registrar corran al arrancar el worker.

AL_INTERRUMPIR es el segundo registro: qué hacer con la entidad de dominio
(sesión de Crear, swap, anuncio) cuando recuperar_colgadas marca su tarea en
`error` sin más reintentos — la tarea muere, pero la fila de atrás quedaría
"generando"/"publicando" para siempre si nadie la toca. El hook recibe
`(tarea, mensaje)` y el worker lo envuelve en try/except: nunca tumba el ciclo.
"""
REGISTRO = {}
AL_INTERRUMPIR = {}

# Cobros (spec 2026-10-08 §5.1): tipos cuya ejecución puede llamar a un
# proveedor que cobra (WaveSpeed, fal, Anthropic, Apify, Atria, TrendTrack) a
# cuenta del proyecto. Si el proyecto cobra, trabajos.encolar exige saldo antes
# de encolarlos y el worker no los arranca con saldo ≤ 0 (salvo la continuación
# de una cadena). Todo tipo de tareas/ está aquí o en los exentos, con su motivo:
# tests/test_cobros_worker.py falla si uno nuevo no está en ninguno.
TIPOS_QUE_COBRAN = frozenset({
    # Crear y Flow Plus (WaveSpeed)
    "flowplus_video", "flowplus_imagen", "cadena_elementos", "swap_generar",
    # Voz y música (fal: MiniMax, ElevenLabs, Whisper)
    "audio_generar", "hablado_voz", "voz_propia_crear", "musica_generar", "editor_voz", "material_transcribir",
    # Final edition (Claude escribe el guion; voz y música por fal)
    "final_guion", "final_producir",
    # Doctrina, Sprints y Triple Whale (Claude)
    "producto_pedidos", "pieza_revisar", "sprint_analizar_referencia", "sprint_sugerir_personas",
    "sprint_reescribir_idea", "sprint_proponer_ideas", "sprint_qa_pieza", "referentes_sugerir_ia", "tw_evaluar",
    "tw_analizar_anuncio",      # «Cómo mejorarlo» de un anuncio: Whisper (fal) y Claude
    # Nicho e investigación (Apify y Claude)
    "nicho_recolectar", "nicho_generar_avatares", "nicho_completar_avatares",
    "nicho_inv_consultas", "nicho_inv_buscar", "nicho_inv_seleccionar",
    # Referentes pedidos por un proyecto (Apify, Atria, TrendTrack y Claude)
    "referentes_barrer", "referentes_clasificar",
    # Catálogo: la regla de fidelidad de cada producto la escribe Claude
    "catalogo_importar", "producto_vincular",
})

TIPOS_EXENTOS_DE_COBRO = {
    "flowplus_recuperar": "recupera un video ya pagado; no paga de nuevo",
    "flowplus_director": "el director lo paga Creatv (_creatv); el video que lanza pasa por su propio freno",
    "cadena_vigilar": "periódica: avanza las cadenas; cada escena la cobra flowplus_video",
    "cadena_unir": "une con ffmpeg escenas ya pagadas",
    "edicion_producir": "renderiza con ffmpeg materiales que ya existen",
    "edicion_proxy": "proxy con ffmpeg, sin proveedor",
    "edicion_desde_clon": "baja y mide el clon para editarlo; gratis",
    "material_de_pieza": "materializa una pieza de Crear como material; gratis",
    "materiales_limpiar": "periódica de mantenimiento",
    "exp_decidir": "el decisor pausa perdedoras y frena gasto en Meta: nunca se bloquea por saldo. "
                   "El diagnóstico con Claude de cada perdedora pide saldo antes (libro.exigir en "
                   "tareas/experimentos._diagnosticar): sin saldo quedan solo las pistas, sin llamar a Claude",
    "exp_decidir_todos": "periódica: solo encola exp_decidir",
    "exp_lanzar": "publica en Meta en pausa; la pauta la paga el cliente en su cuenta, no el saldo",
    "exp_refrescar": "lee métricas de Meta",
    "exp_refrescar_todos": "periódica: solo encola exp_refrescar",
    "exp_detalle": "lee el detalle de Meta",
    "exp_avanzar_todos": "periódica: avanza derivaciones; lo que produce pasa por su propio freno",
    "meta_publicar": "publica en Meta; no llama a un proveedor que cobra",
    "meta_refrescar": "lee métricas de Meta",
    "meta_rend_sincronizar": "lee métricas de las cuentas de Meta y las tasas del BCE; no cobra",
    "meta_rend_sincronizar_todas": "periódica: solo encola meta_rend_sincronizar",
    "meta_rend_limpiar": "periódica de mantenimiento",
    "organico_publicar": "publica en redes; el texto con IA se cobra en la ruta «Escribir con IA»",
    "sprint_referencia_link": "descarga el link; el análisis con Claude es su propia tarea",
    "sprint_qa_pendientes": "periódica: solo encola sprint_qa_pieza",
    "sprint_empaquetar": "arma el zip de la entrega",
    "referentes_importar_copycoders": "importación del admin; lo paga Creatv (_creatv)",
    "referentes_familias_en": "traducción del admin; la paga Creatv (_creatv)",
    "tienda_sync_productos": "sincronización automática del catálogo; frenarla dejaría la tienda desactualizada. "
                             "La regla de fidelidad de un producto nuevo (Claude) pide saldo antes, en "
                             "importador._regla_si_hay_saldo: sin saldo el producto entra sin regla",
    "tienda_sync_pedidos": "lee pedidos de la tienda",
    "tienda_sync_productos_todas": "periódica: solo encola tienda_sync_productos",
    "tienda_sync_pedidos_todas": "periódica: solo encola tienda_sync_pedidos",
    "tw_sincronizar": "lee datos de Triple Whale",
    "tw_sincronizar_todas": "periódica: solo encola tw_sincronizar",
    "tw_ganchos_preparar": "baja el video y lanza piezas de Crear; cada pieza la cobra flowplus_video",
    "tw_ganchos_vigilar": "periódica: mueve las variantes de los ganchos; cada clip lo cobra flowplus_video",
    "tw_gancho_armar": "arma con ffmpeg y el editor un clip ya pagado y el original",
    "salidas_limpiar": "periódica de mantenimiento",
    "cola_limpiar": "periódica de mantenimiento",
    "db_respaldar": "periódica de mantenimiento",
    "errores_limpiar": "periódica de mantenimiento",
    "cobros_verificar_recargas": "consulta a Bold, no cobra",
    "planes_renovar": "cobra la renovación del plan en Wompi: es ingreso de Creatv, no gasto de un proveedor; no pasa por el saldo",
}


def registrar(tipo):
    def _dec(fn):
        REGISTRO[tipo] = fn
        return fn
    return _dec


def al_interrumpir(tipo):
    """Registra `fn(tarea: dict, mensaje: str) -> None` para cuando una tarea
    de ese tipo queda en error por interrupción (reinicio del worker)."""
    def _dec(fn):
        AL_INTERRUMPIR[tipo] = fn
        return fn
    return _dec


class Continuar:
    """Lo que devuelve una tarea que no terminó su trabajo pero sabe cómo
    seguirlo: el worker la cierra `hecha` con `mensaje` y encola, en la misma
    transacción, la tarea `tipo` con `payload` y el MISMO job_id (la barra de la
    tarjeta sigue viva). Ej.: un video cuya espera se agotó sigue con
    `flowplus_recuperar` (spec 2026-09-28-crear-sin-cola)."""

    def __init__(self, tipo, payload, mensaje=None, ejecutar_desde=None, max_intentos=None):
        self.tipo, self.payload, self.mensaje, self.ejecutar_desde = tipo, payload, mensaje, ejecutar_desde
        self.max_intentos = max_intentos      # None: 1, como siempre (cola.terminar_y_encolar)


def ref_sufijo(tarea):
    """Marcador de intento (`:t<tarea_id>`) para la referencia de un gasto:
    el id de la fila `tarea` (nuevo por clic, estable en reintentos del
    mismo intento) — sin él, reproducir una final, un video/imagen o un
    swap pisaría el cobro real del intento anterior en vez de dejar su
    propia fila. Las llamadas fuera del worker (tests/scripts, sin
    `tarea["id"]`) caen a `t0`."""
    tarea_id = tarea.get("id")
    return f":t{tarea_id}" if tarea_id is not None else ":t0"


def cargar_todas():
    """Importa los módulos con tareas reales. Se llama desde worker.main(), no
    al importar el paquete, para que los tests puedan registrar tareas falsas
    sin arrastrar proveedores externos."""
    from tareas import audios, cadena, cobros, director, doctrina, edicion, experimentos, final_edition, flowplus, hablado, investigacion, mantenimiento, meta, meta_rendimiento, musica, nicho, organico, planes, referentes, sprints, swap, tiendas, triple_whale, voces_propias  # noqa: F401

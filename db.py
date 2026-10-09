"""
Base de datos del motor (SQLite + SQLAlchemy Core). Una sola base por servidor
en data/creatv.db (WAL), compartida por gunicorn y el worker. Las tablas siguen
el §2 de docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md.

Los JSON por cliente (clientes/<c>/*.json) NO desaparecen: los módulos que ya
existían (creative_flow.py, ads.py) cambian su almacenamiento a estas tablas
manteniendo la misma API de dicts.
"""
import contextlib
import os
import unicodedata
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, Float, Integer, JSON, MetaData, String, Table, Text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE = None


def url():
    return os.environ.get("CREATV_DB_URL") or f"sqlite:///{os.path.join(BASE_DIR, 'data', 'creatv.db')}"


def asegurar_carpeta():
    """Crea la carpeta del archivo SQLite (data/) si no existe. La usan engine()
    y migrations/env.py (que abre su propio engine con engine_from_config y en
    un checkout limpio fallaba con 'unable to open database file'). No hace
    nada con :memory: ni con otras bases."""
    u = url()
    if u.startswith("sqlite:///") and not u.endswith(":memory:"):
        os.makedirs(os.path.dirname(u.replace("sqlite:///", "")) or ".", exist_ok=True)


def pliegue(texto):
    """Texto para comparar sin tildes ni mayúsculas: «ÉLITE Cröcs» -> «elite crocs».
    También es la función SQL `pliegue(col)` de cada conexión (el lower() de SQLite
    solo baja ASCII y no quita tildes)."""
    if texto is None:
        return ""
    sin_marcas = "".join(ch for ch in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(ch))
    return sin_marcas.casefold().strip()


def _entero_env(nombre, defecto):
    try:
        return max(0, int(os.environ.get(nombre) or defecto))
    except ValueError:
        return defecto


def opciones_pool(u):
    """Pool de conexiones del engine (spec 2026-10-01-escala-y-monitoreo §3).
    Cada hilo de gunicorn (y cada hilo de fondo de trabajos.iniciar) toma una
    conexión prestada del pool y la devuelve al cerrar la transacción: abrir
    una conexión de SQLite cuesta los PRAGMAs y registrar `pliegue`, así que
    se reutilizan. `CREATV_DB_POOL` debe ser ≥ los hilos de gunicorn
    (deploy/gunicorn.conf.py); `CREATV_DB_POOL_EXTRA` son las que se abren de
    más en un pico y se cierran al devolverlas. Con otra base (Postgres, si
    algún día se migra) se agrega pre_ping y reciclar: el servidor corta las
    conexiones ociosas y SQLite no."""
    if u.startswith("sqlite") and ":memory:" in u:
        return {}
    opciones = {"pool_size": _entero_env("CREATV_DB_POOL", 10),
                "max_overflow": _entero_env("CREATV_DB_POOL_EXTRA", 10),
                "pool_timeout": _entero_env("CREATV_DB_POOL_ESPERA", 15)}
    if not u.startswith("sqlite"):
        opciones.update(pool_pre_ping=True, pool_recycle=1800)
    return opciones


def engine():
    """Engine singleton del proceso. SQLite con WAL para que gunicorn (hilos) y
    el worker (otro proceso) lean y escriban a la vez sin 'database is locked'."""
    global _ENGINE
    if _ENGINE is None:
        u = url()
        asegurar_carpeta()
        _ENGINE = sa.create_engine(u, connect_args={"check_same_thread": False, "timeout": 5}, future=True,
                                   **opciones_pool(u))

        @sa.event.listens_for(_ENGINE, "connect")
        def _pragmas(dbapi_con, _):
            cur = dbapi_con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA foreign_keys=ON")
            # Ordenar o agrupar sin índice usa un árbol temporal: en memoria, no
            # en un archivo de /tmp (el disco del VPS es lo más lento que tiene).
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.close()
            dbapi_con.create_function("pliegue", 1, pliegue, deterministic=True)
    return _ENGINE


def _reset_para_tests():
    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None


@contextlib.contextmanager
def conectar():
    """`with db.conectar() as con:` — una transacción; commit al salir sin error."""
    with engine().begin() as con:
        yield con


def ahora():
    return datetime.now().isoformat(timespec="seconds")


metadata = MetaData()


def _comunes():
    return [
        Column("cliente", String(80), nullable=False, index=True),
        Column("creado_en", String(19), nullable=False),
        Column("actualizado_en", String(19), nullable=False),
    ]


producto = Table("producto", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("fuente", String(20), nullable=False),          # shopify|woo|meli|csv|url|manual
    Column("fuente_id", String(120)),
    Column("nombre", String(200), nullable=False),
    Column("descripcion", Text),
    Column("precio", Float),
    Column("moneda", String(3)),
    Column("url_compra", Text),
    Column("fotos", JSON, default=list),
    Column("categoria", String(120)),
    Column("activo_catalogo_id", String(120)),
    Column("prioridad", Integer, default=0),
    Column("en_prueba", Boolean, default=False),
    Column("archivado", Boolean, default=False),
    Column("url_imagen_principal", String(500)),
    Column("extra", JSON, default=dict),                    # campos del conector sin columna propia (bloque 5)
    sa.UniqueConstraint("cliente", "fuente", "fuente_id", name="uq_producto_fuente"),
)

concepto = Table("concepto", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("producto_id", Integer, sa.ForeignKey("producto.id")),
    Column("origen", String(20), nullable=False),          # referente_link|ganador_derivado|rescate|manual
    Column("referencia_url", Text),
    Column("referencia_frames", JSON, default=list),
    Column("referencia_transcripcion", Text),
    Column("enfoque", String(20)),                          # producto|persona|unboxing
    Column("guion_base", JSON),
    Column("idioma_base", String(5), default="es"),
    Column("padre_concepto_id", Integer, sa.ForeignKey("concepto.id")),
    Column("motivo_archivo", Text),
    Column("archivado", Boolean, default=False),
    Column("legado_id", String(60), index=True),           # cf_... de creative_flow_pendientes.json
    Column("extra", JSON, default=dict),                    # campos legado que no tienen columna
)

pieza = Table("pieza", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("concepto_id", Integer, sa.ForeignKey("concepto.id"), nullable=False, index=True),
    Column("tipo", String(12), nullable=False),             # clon_limpio|final
    Column("idioma", String(5)),
    Column("pais", String(2)),
    Column("modelo", String(40)),
    Column("url_video", Text),
    Column("url_miniatura", Text),
    Column("url_local", Text),
    Column("duracion_s", Float),
    Column("aspect_ratio", String(6)),
    Column("capas", JSON, default=dict),
    Column("costo_usd", Float),
    Column("estado", String(16), nullable=False, default="pendiente"),  # pendiente|generando|listo|error|degradada
    Column("error", Text),
    Column("padre_pieza_id", Integer, sa.ForeignKey("pieza.id")),
    Column("guion", JSON),
    Column("legado_id", String(60), index=True),
    Column("extra", JSON, default=dict),
    Column("edicion_version_id", Integer),
    sa.Index("ix_pieza_padre", "padre_pieza_id"),  # finales de un proyecto (0026)
)

# --- editor (spec 2026-09-18-final-edition-editor-design.md §5) ---------------
edicion = Table("edicion", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("cf_id", String(60), index=True),                # sesión de Crear de la que nació (nullable)
    Column("tipo", String(8), nullable=False),              # video|imagen
    Column("nombre", String(120), nullable=False),
    Column("documento", JSON, nullable=False),
    Column("version_n", Integer, nullable=False, default=0),  # CAS del autoguardado
    Column("estado", String(12), nullable=False, default="borrador"),  # borrador|producida
    Column("creada_por", String(80)),
)

edicion_version = Table("edicion_version", metadata,
    Column("id", Integer, primary_key=True),
    Column("edicion_id", Integer, sa.ForeignKey("edicion.id"), nullable=False),
    Column("n", Integer, nullable=False),
    Column("documento", JSON, nullable=False),
    Column("motivo", String(10), nullable=False),           # producir|manual
    Column("creada_en", String(19), nullable=False),
    sa.UniqueConstraint("edicion_id", "n", name="uq_edicion_version_n"),
)

material = Table("material", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("tipo", String(12), nullable=False),             # video|imagen|audio|png_texto|proxy|tira|forma_onda
    Column("origen", String(12), nullable=False),           # crear|subida|catalogo|marca|voz|musica|sonido|efecto|grabacion|texto|traduccion
    Column("url", Text, nullable=False),
    Column("url_proxy", Text),
    Column("hash", String(64), nullable=False),
    Column("duracion_ms", Integer),
    Column("ancho", Integer),
    Column("alto", Integer),
    Column("bytes", Integer, nullable=False, default=0),
    Column("costo_usd", Float, default=0.0),
    Column("padre_id", Integer),
    Column("extra", JSON, default=dict),                    # palabras con tiempos, picos, cortes detectados
    Column("usado_en", String(19)),
    sa.UniqueConstraint("cliente", "hash", name="uq_material_hash"),
    sqlite_autoincrement=True,  # PND-040: una voz borrada nunca presta su identidad.
)

experimento = Table("experimento", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("producto_id", Integer, sa.ForeignKey("producto.id")),
    Column("nombre", String(200), nullable=False),
    Column("modo", String(8), nullable=False, default="manual"),  # manual|semi|auto
    Column("reglas", JSON, default=dict),
    Column("paises", JSON, default=list),
    Column("moneda", String(3)),
    Column("tope_total", Float),
    Column("dias", Integer),
    Column("objetivo_meta", String(30)),
    Column("atribucion", String(10), default="ninguna"),   # pixel|tienda|ninguna
    Column("estado", String(22), nullable=False, default="armando"),
    Column("meta_campaign_id", String(40)),
    Column("gasto_acumulado", Float, default=0.0),
    Column("legado", Boolean, default=False),               # True = importado de ads.json
    Column("destino_url", String(500)),
    Column("edad_min", Integer, default=18),
    Column("edad_max", Integer, default=65),
    Column("error", Text),
    Column("extra", JSON, default=dict),                    # lanzamiento: etapa, ids parciales
    sa.Index("uq_experimento_legado", "cliente", unique=True, sqlite_where=sa.text("legado = 1")),
)

experimento_pieza = Table("experimento_pieza", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("experimento_id", Integer, sa.ForeignKey("experimento.id"), nullable=False, index=True),
    Column("pieza_id", Integer, sa.ForeignKey("pieza.id")),
    Column("pais", String(2)),
    Column("meta_adset_id", String(40)),
    Column("meta_ad_id", String(40)),
    Column("meta_creative_id", String(40)),
    Column("estado_meta", String(30)),
    Column("veredicto", String(12), default="pendiente"),
    Column("veredicto_motivo", Text),
    Column("veredicto_en", String(19)),
    Column("escalon_rescate", Integer, default=0),
    Column("presupuesto_dia_actual", Float),
    Column("estado", String(16), nullable=False, default="en_cola"),  # en_cola|publicando|pausado|activo|error
    Column("error", Text),
    Column("legado_id", String(60), index=True),           # ad_... de ads.json
    Column("extra", JSON, default=dict),                    # nombre, fuente, contenido_url, objetivo, etc.
    sa.Index("ix_experimento_pieza_pieza", "pieza_id"),  # clave foránea (0026)
)

metrica_snapshot = Table("metrica_snapshot", metadata,
    Column("id", Integer, primary_key=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False, index=True),
    Column("tomado_en", String(19), nullable=False),
    Column("impresiones", Integer, default=0), Column("alcance", Integer, default=0),
    Column("frecuencia", Float, default=0.0), Column("clics", Integer, default=0),
    Column("clics_enlace", Integer, default=0), Column("ctr", Float, default=0.0),
    Column("cpc", Float, default=0.0), Column("cpm", Float, default=0.0),
    Column("thruplay", Integer, default=0), Column("thruplay_rate", Float, default=0.0),
    Column("gasto", Float, default=0.0), Column("compras", Integer, default=0),
    Column("ingresos", Float, default=0.0), Column("roas", Float, default=0.0),
    Column("cpa", Float, default=0.0),
    Column("fuente_ventas", String(8), default="ninguna"),
    Column("extra", JSON, default=dict),                    # resultado_nombre, estado_meta_texto, motivo_rechazo
    # base del delta del Tablero sin leer todo el historial (0026)
    sa.Index("ix_metrica_snapshot_pieza_tomado", "experimento_pieza_id", "tomado_en"),
)

# Detalle diario de Meta por anuncio (spec 2026-10-02 §3.1). Único escritor:
# meta_detalle.py. Una fila por anuncio y día de la cuenta de Meta; se reemplaza
# al volver a pedir el día (Meta corrige los últimos días).
metrica_dia = Table("metrica_dia", metadata,
    Column("id", Integer, primary_key=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
    Column("fecha", String(10), nullable=False),
    Column("impresiones", Integer, default=0), Column("alcance", Integer, default=0),
    Column("frecuencia", Float, default=0.0), Column("clics", Integer, default=0),
    Column("clics_enlace", Integer, default=0), Column("gasto", Float, default=0.0),
    Column("cpm", Float, default=0.0), Column("vistas_3s", Integer, default=0),
    Column("reproducciones", Integer, default=0), Column("p25", Integer, default=0),
    Column("p50", Integer, default=0), Column("p75", Integer, default=0),
    Column("p95", Integer, default=0), Column("p100", Integer, default=0),
    Column("thruplay", Integer, default=0), Column("tiempo_medio_s", Float, default=0.0),
    Column("visitas_pagina", Integer, default=0), Column("carrito", Integer, default=0),
    Column("pago_iniciado", Integer, default=0), Column("compras_meta", Integer, default=0),
    Column("ingresos_meta", Float, default=0.0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("experimento_pieza_id", "fecha", name="uq_metrica_dia_pieza_fecha"),
    sa.Index("ix_metrica_dia_fecha", "fecha"),
)

# Totales desde el inicio por anuncio y valor de una dimensión (ubicacion,
# edad_genero, dispositivo, region). Único escritor: meta_detalle.py; se
# reemplaza el juego completo de (anuncio, dimensión) en cada pasada.
metrica_desglose = Table("metrica_desglose", metadata,
    Column("id", Integer, primary_key=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
    Column("dimension", String(20), nullable=False),
    Column("clave", String(120), nullable=False),
    Column("impresiones", Integer, default=0), Column("clics_enlace", Integer, default=0),
    Column("gasto", Float, default=0.0), Column("vistas_3s", Integer, default=0),
    Column("thruplay", Integer, default=0), Column("compras_meta", Integer, default=0),
    Column("ingresos_meta", Float, default=0.0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("experimento_pieza_id", "dimension", "clave", name="uq_metrica_desglose_pieza_dim_clave"),
)

evento = Table("evento", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("experimento_id", Integer, sa.ForeignKey("experimento.id"), index=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id")),
    Column("tipo", String(30), nullable=False),
    Column("mensaje", Text, nullable=False),
    Column("datos", JSON, default=dict),
    Column("creado_en", String(19), nullable=False),
    sa.Index("ix_evento_experimento_pieza", "experimento_pieza_id"),  # clave foránea (0026)
)

propuesta = Table("propuesta", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("experimento_id", Integer, sa.ForeignKey("experimento.id"), nullable=False, index=True),
    Column("accion", String(12), nullable=False),           # publicar|activar|escalar|derivar|rescatar|pausar
    Column("payload", JSON, default=dict),
    Column("estado", String(10), nullable=False, default="pendiente"),
    Column("resuelta_en", String(19)),
)

tarea = Table("tarea", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), index=True),
    Column("job_id", String(200), index=True),              # el id que ya usa el polling del navegador
    Column("tipo", String(40), nullable=False),
    Column("payload", JSON, default=dict),
    Column("estado", String(10), nullable=False, default="pendiente", index=True),
    Column("intentos", Integer, default=0),
    Column("max_intentos", Integer, default=5),
    Column("prioridad", Integer, default=5),                # mayor = antes; los lotes de sprint van con 3
    Column("ejecutar_desde", String(19), nullable=False),
    Column("creada_en", String(19), nullable=False),
    Column("iniciada_en", String(19)),
    Column("terminada_en", String(19)),
    Column("mensaje", Text),
    Column("error", Text),
    # progreso para la barra del navegador (mismo modelo que trabajos.py)
    Column("duracion_estimada", Float, default=60.0),
    Column("etapas", JSON, default=list),                   # [[nombre, peso], ...]
    Column("etapa_actual", String(120)),
    Column("indice_etapa", Integer, default=0),
    Column("inicio_etapa", Float),                          # time.time()
    Column("inicio", Float),                                # time.time()
    Column("progreso_etapa", Float),
    Column("progreso_visto", Float, default=0.0),
    Column("detalle", Text),
    # Una sola tarea viva por job_id: es lo que hace atómico el dedupe de
    # cola.encolar aunque encolen dos procesos a la vez (migración 0003).
    sa.Index("uq_tarea_job_viva", "job_id", unique=True,
             sqlite_where=sa.text("estado IN ('pendiente','en_curso')")),
)

tienda = Table("tienda", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("tipo", String(10), nullable=False),
    Column("credenciales", Text),                           # cifrado (bloque 5)
    Column("nombre", String(120)),
    Column("dominio", String(200)),
    Column("ultima_sync_productos", String(19)),
    Column("ultima_sync_pedidos", String(19)),
    Column("estado", String(20), default="conectada"),
    Column("error", Text),
)

# Desde la migración 0032 (spec 2026-10-08 §3.2) esta tabla son los AJUSTES del proyecto: una fila por
# proyecto con moneda, modelo_atribucion, ventana_atribucion y extra (avisados, aviso_sin_ventas). Las
# columnas llave, dominio_tienda, zona_horaria, ultima_sincronizacion, estado y error YA NO SE LEEN NI SE
# ESCRIBEN (la conexión vive en tw_tienda); siguen aquí, intactas, para poder volver al despliegue anterior.
triple_whale = Table("triple_whale", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("llave", Text),                                   # SIN USO desde 0032 (ahora tw_tienda.llave)
    Column("dominio_tienda", String(200)),                   # SIN USO desde 0032
    Column("moneda", String(3)),                             # ISO 4217 (ej: USD, COP)
    Column("modelo_atribucion", String(50), default="Triple Attribution"),  # ej: Triple Attribution, Last Click 7d
    Column("ventana_atribucion", String(30), default="lifetime"),  # ej: lifetime, 7d
    Column("zona_horaria", String(50)),                      # SIN USO desde 0032
    Column("ultima_sincronizacion", String(19)),             # SIN USO desde 0032
    Column("estado", String(20), default="conectada"),       # SIN USO desde 0032
    Column("error", Text),                                   # SIN USO desde 0032
    Column("extra", JSON, default=dict),                     # avisados, aviso_sin_ventas (los backfill_desde/... viejos quedan sin uso)
)

# Una fila por tienda de Triple Whale conectada (spec 2026-10-08 §3.1, migración 0032): un proyecto puede
# tener varias, una por país. Único escritor: triple_whale_tiendas.py.
tw_tienda = Table("tw_tienda", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("pais", String(2)),                               # ISO 3166-1 alfa-2 en mayúsculas; None = sin elegir
    Column("dominio", String(200), nullable=False),          # normalizado (triple_whale.normalizar_dominio)
    Column("llave", Text),                                   # cifrado (Fernet)
    Column("zona_horaria", String(50)),                      # ej: America/Bogota (desde shop_timezone)
    Column("estado", String(20), default="conectada"),       # conectada / error
    Column("error", Text),
    Column("ultima_sincronizacion", String(19)),             # ISO 8601
    Column("extra", JSON, default=dict),                     # backfill_desde, ultimo_resumen, gasto_7d
    sa.UniqueConstraint("cliente", "dominio", name="uq_tw_tienda_dominio"),
    # una tienda por país; varias sin país se permiten mientras se eligen
    sa.Index("uq_tw_tienda_pais", "cliente", "pais", unique=True, sqlite_where=sa.text("pais IS NOT NULL")),
    # AUTOINCREMENT: el id de una tienda quitada no se reusa, así una evaluación vieja (tw_evaluacion.extra.
    # tienda_id) no toma el nombre de la tienda conectada después (auditoría de seguridad, 2026-10-08).
    sqlite_autoincrement=True,
)

# --- Triple Whale: métricas copiadas y evaluación (spec 2026-09-28, migraciones 0023 y 0024) ---
# Una fila por (proyecto, canal, anuncio, día): lo que reporta la plataforma
# (ads_table) más lo que atribuye el Triple Pixel con el modelo y la ventana
# del proyecto (pixel_joined_tvf). Es una copia: Triple Whale reatribuye días
# viejos, así que cada sync vuelve a pedir los últimos días y hace upsert.
# Pedidos en Float: los modelos lineales reparten un pedido entre anuncios.
tw_anuncio_dia = Table("tw_anuncio_dia", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("tienda_id", Integer, nullable=False),            # tw_tienda.id (0032); sin FK, como el resto
    Column("fecha", String(10), nullable=False),
    Column("canal", String(40), nullable=False),
    Column("ad_id", String(64), nullable=False),
    Column("cuenta_id", String(64)),
    Column("campana_id", String(64)), Column("campana", Text),
    Column("conjunto_id", String(64)), Column("conjunto", Text),
    Column("anuncio", Text), Column("estado_anuncio", String(30)),
    Column("creative_id", String(64)),
    Column("video_url", Text), Column("destino_url", Text),
    Column("utm_ok", Boolean),                               # is_utm_valid (None = TW no lo dijo)
    Column("gasto", Float, default=0.0), Column("impresiones", Integer, default=0),
    Column("clics", Integer, default=0), Column("clics_salida", Integer, default=0),
    Column("compras_canal", Float, default=0.0), Column("valor_canal", Float, default=0.0),
    Column("thruplays", Integer, default=0), Column("vistas_3s", Integer, default=0),
    Column("p25", Integer, default=0), Column("p50", Integer, default=0),
    Column("p75", Integer, default=0), Column("p100", Integer, default=0),
    Column("pedidos", Float, default=0.0), Column("ingresos", Float, default=0.0),
    Column("nc_pedidos", Float, default=0.0), Column("nc_ingresos", Float, default=0.0),
    Column("sesiones", Integer, default=0), Column("carritos", Integer, default=0),
    Column("checkouts", Integer, default=0),
    Column("con_pixel", Boolean, default=False),            # el Pixel respondió para ese día (aunque sin pedidos)
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("cliente", "tienda_id", "canal", "ad_id", "fecha", name="uq_tw_anuncio_dia"),
    sa.Index("ix_tw_anuncio_dia_cliente_fecha", "cliente", "fecha"),
    sa.Index("ix_tw_anuncio_dia_cliente_tienda_fecha", "cliente", "tienda_id", "fecha"),
)

# La tienda por día (blended_stats_tvf): ingresos y pedidos reales, gasto total.
tw_tienda_dia = Table("tw_tienda_dia", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("tienda_id", Integer, nullable=False),            # tw_tienda.id (0032)
    Column("fecha", String(10), nullable=False),
    Column("gasto", Float, default=0.0), Column("ingresos", Float, default=0.0),
    Column("pedidos", Float, default=0.0), Column("nc_pedidos", Float, default=0.0),
    Column("nc_ingresos", Float, default=0.0), Column("reembolsos", Float, default=0.0),
    Column("cogs", Float, default=0.0), Column("utilidad_neta", Float, default=0.0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("cliente", "tienda_id", "fecha", name="uq_tw_tienda_dia"),
)

# Una evaluación con IA de los anuncios (pagada, max_intentos=1): la muestra
# que se le mostró a Claude (`anuncios`) y lo que devolvió (`resultado`:
# patrones, por qué funciona cada anuncio e ideas de anuncios nuevos).
tw_evaluacion = Table("tw_evaluacion", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("estado", String(12), nullable=False, default="en_cola"),   # en_cola|analizando|lista|error
    Column("desde", String(10)), Column("hasta", String(10)),
    Column("moneda", String(3)),
    Column("anuncios", JSON, default=list),
    Column("resultado", JSON, default=dict),
    Column("usd", Float, default=0.0),
    Column("error", Text),
    Column("tarea_id", Integer),
    Column("pedido_por", String(80)),
    Column("extra", JSON, default=dict),
)

# Ventas por producto y día (orders_table.products_info): qué se vende de
# verdad, para saber qué producto empujar en los anuncios nuevos.
tw_producto_dia = Table("tw_producto_dia", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("tienda_id", Integer, nullable=False),            # tw_tienda.id (0032)
    Column("fecha", String(10), nullable=False),
    Column("producto_id", String(120), nullable=False),
    Column("nombre", Text), Column("sku", String(120)),
    Column("unidades", Float, default=0.0), Column("ingresos", Float, default=0.0),
    Column("pedidos", Float, default=0.0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("cliente", "tienda_id", "producto_id", "fecha", name="uq_tw_producto_dia"),
    sa.Index("ix_tw_producto_dia_cliente_fecha", "cliente", "fecha"),
    sa.Index("ix_tw_producto_dia_cliente_tienda_fecha", "cliente", "tienda_id", "fecha"),
)

# Tarjetas de análisis (spec 2026-10-08-triple-whale-tarjetas-analisis §3.1, migración 0034): el anuncio tal cual lo
# da ads_table (miniatura, video, título, copy). Una fila por (proyecto, canal, anuncio), SIN tienda: el mismo anuncio
# llega igual por todas las tiendas que comparten cuenta. Único escritor: triple_whale/datos.py (el borrado al quitar
# la última tienda, en triple_whale_tiendas.py como las copias).
tw_creativo = Table("tw_creativo", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("canal", String(40), nullable=False),
    Column("ad_id", String(64), nullable=False),
    Column("tipo", String(20)),                               # ad_type en minúsculas: video, image, carousel…
    Column("imagen_url", String(2000)),                       # ad_image_url (files.triplewhale.com)
    Column("video_url", String(2000)),
    Column("titulo", String(300)),
    Column("copy", Text),
    Column("cta", String(60)),
    Column("duracion_s", Float),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("cliente", "canal", "ad_id", name="uq_tw_creativo"),
)

# «Cómo mejorarlo» de un anuncio (spec §3.2): pagado, nunca se borra al quitar tiendas (como tw_evaluacion).
tw_analisis = Table("tw_analisis", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("tienda_id", Integer),                             # alcance pedido; None = «Todas»
    Column("canal", String(40), nullable=False),
    Column("ad_id", String(64), nullable=False),
    Column("estado", String(12), nullable=False, default="en_cola"),   # en_cola|analizando|lista|error
    Column("desde", String(10)), Column("hasta", String(10)),
    Column("moneda", String(3)),
    Column("foto", JSON, default=dict),                       # el anuncio cuando se pidió (spec §3.2)
    Column("resultado", JSON, default=dict),
    Column("medios", JSON, default=dict),                     # qué vio Claude
    Column("usd", Float, default=0.0),
    Column("error", Text),
    Column("tarea_id", Integer),
    Column("pedido_por", String(80)),
    sa.Index("ix_tw_analisis_anuncio", "cliente", "canal", "ad_id", "id"),
    sqlite_autoincrement=True,
)

pedido = Table("pedido", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("tienda_id", Integer, sa.ForeignKey("tienda.id")),
    Column("fuente_id", String(120), nullable=False),
    Column("fecha", String(19), nullable=False),
    Column("total", Float), Column("moneda", String(3)),
    Column("items", JSON, default=list),
    Column("utm_content", String(120)),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id")),
    sa.UniqueConstraint("cliente", "fuente_id", name="uq_pedido_fuente"),
    sa.Index("ix_pedido_experimento_pieza", "experimento_pieza_id"),  # clave foránea (0026)
)

# --- Publicación orgánica (bloque 7) ---

publicacion = Table("publicacion", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("pieza_id", Integer, sa.ForeignKey("pieza.id"), nullable=False),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id")),
    Column("plataforma", String(12), nullable=False),          # facebook|instagram|youtube|tiktok
    Column("estado", String(12), nullable=False, default="en_cola"),  # en_cola|publicando|publicada|error
    Column("caption", Text),
    Column("titulo", String(150)),
    Column("id_externo", String(120)),
    Column("url", String(500)),
    Column("error", Text),
    Column("publicado_en", String(19)),
    Column("origen", String(10), nullable=False, default="manual"),   # manual|ganador
    Column("extra", JSON, default=dict),
    sa.Index("ix_publicacion_cliente_pieza", "cliente", "pieza_id"),
    # Nunca dos veces la misma pieza en la misma plataforma mientras la
    # publicación esté viva (en cola, publicándose o publicada); una en
    # `error` sí se puede volver a encolar (migración 0009).
    sa.Index("uq_publicacion_viva", "cliente", "pieza_id", "plataforma", unique=True,
             sqlite_where=sa.text("estado IN ('en_cola','publicando','publicada')")),
    sa.Index("ix_publicacion_pieza", "pieza_id"),  # captions de Crear (0026)
)

# --- Gasto real por proyecto (docs/superpowers/plans/2026-09-18-gasto-real-por-proyecto.md) ---

gasto = Table("gasto", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("creado_en", String(19), nullable=False),
    Column("tipo", String(20), nullable=False),               # video|imagen|swap|guion|final|regla_producto|caption_organico|musica|otro
    Column("usd", Float, nullable=False, default=0.0),
    Column("proveedor", String(30)),
    Column("referencia", String(160), nullable=False),        # f"{tipo}:{id}" — un cobro real, una fila
    Column("detalle", String(300)),
    Column("extra", JSON),
    # Idempotencia de gastos.registrar: la segunda llamada con la misma
    # referencia actualiza usd/detalle, nunca duplica (migración 0010).
    sa.UniqueConstraint("cliente", "referencia", name="uq_gasto_referencia"),
    sa.Index("ix_gasto_cliente_creado", "cliente", "creado_en"),
    sa.Index("ix_gasto_creado", "creado_en"),  # «Últimos cobros» del panel (0026)
)

# --- Cobros: saldo prepagado por proyecto (docs/superpowers/specs/2026-10-08-cobros-saldo-prepagado-design.md §2) ---
# Montos en milésimas de dólar, enteros. Escritores únicos: cobros/libro.py
# (cuenta_saldo, movimiento_saldo, reserva_saldo) y cobros/recargas.py (recarga, pago_evento).

cuenta_saldo = Table("cuenta_saldo", metadata,
    Column("cliente", String(80), primary_key=True),
    Column("cobrar", Boolean, nullable=False, default=False),
    Column("margen", Float),                                   # NULL = kv cobros:margen_global
    Column("umbral_aviso", Integer, nullable=False, default=5000),
    Column("actualizado_en", String(19)),
    Column("actualizado_por", String(80)),
)

movimiento_saldo = Table("movimiento_saldo", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("creado_en", String(19), nullable=False),
    Column("tipo", String(16), nullable=False),                # recarga|cobro|reverso|no_cobrado|ajuste|anulacion|plan|vencimiento|incluido
    Column("milesimas", Integer, nullable=False),              # con signo
    Column("gasto_id", Integer),
    Column("recarga_id", Integer),
    Column("periodo_id", Integer),                             # periodo_plan: plan|vencimiento (0035)
    Column("job_id", String(160)),
    Column("tarea_id", Integer),
    Column("concepto", String(120), nullable=False),           # código; se traduce al pintar
    Column("detalle", String(300)),
    Column("usuario", String(80)),
    Column("extra", JSON),
    sa.UniqueConstraint("tipo", "gasto_id", name="uq_movimiento_gasto"),
    sa.UniqueConstraint("tipo", "recarga_id", name="uq_movimiento_recarga"),
    sa.UniqueConstraint("tipo", "periodo_id", name="uq_movimiento_periodo"),
    sa.Index("ix_movimiento_cliente_creado", "cliente", "creado_en"),
    sa.Index("ix_movimiento_job", "job_id"),
    sqlite_autoincrement=True,
)

reserva_saldo = Table("reserva_saldo", metadata,
    Column("cliente", String(80), primary_key=True),
    Column("job_id", String(160), primary_key=True),
    Column("milesimas", Integer, nullable=False),
    Column("creada_en", String(19), nullable=False),
)

recarga = Table("recarga", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("creada_en", String(19), nullable=False),
    Column("actualizada_en", String(19)),
    Column("medio", String(12), nullable=False),               # bold|wompi|manual
    Column("estado", String(12), nullable=False),              # pendiente|aprobada|rechazada|expirada|anulada
    Column("milesimas", Integer, nullable=False),
    Column("referencia", String(60), nullable=False, unique=True),
    Column("link_id", String(40)),
    Column("pago_id", String(40), unique=True),
    Column("pasarela_ref", String(40), unique=True),           # id de la transacción de Wompi (0035)
    Column("moneda_pago", String(3)),
    Column("total_pago", Integer),
    Column("medio_pago", String(20)),
    Column("usuario", String(80), nullable=False),
    Column("nota", String(300)),
    sqlite_autoincrement=True,
)

pago_evento = Table("pago_evento", metadata,
    Column("id", Integer, primary_key=True),
    Column("proveedor", String(12), nullable=False),
    Column("evento_id", String(64), nullable=False),
    Column("tipo", String(24), nullable=False),
    Column("referencia", String(60)),
    Column("recibido_en", String(19), nullable=False),
    Column("firma_ok", Boolean, nullable=False),
    Column("resultado", String(40), nullable=False),
    Column("cuerpo", JSON),
    sa.UniqueConstraint("proveedor", "evento_id", name="uq_pago_evento"),
    sa.Index("ix_pago_evento_recibido", "recibido_en"),
)

# --- Planes mensuales (docs/superpowers/specs/2026-10-09-planes-mensuales-wompi-design.md §2, migración 0035) ---
# Escritor único: cobros/planes.py (plan, suscripcion, periodo_plan, pago_plan). Los movimientos que
# acreditan o vencen un periodo los escribe cobros/libro.py.

plan = Table("plan", metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre", String(60), nullable=False),
    Column("precio_usd", Integer, nullable=False),             # mensual, dólares enteros
    Column("precio_anual_usd", Integer),                       # NULL = sin opción anual
    Column("margen", Float, nullable=False),                   # el de miembro, 1,00–5,00
    Column("tope_incluido_usd", Float, nullable=False, default=25.0),   # costo de proveedor regalado por mes
    Column("activo", Boolean, nullable=False, default=True),   # archivado = no se ofrece
    Column("orden", Integer, nullable=False, default=0),
    Column("creado_en", String(19)),
    Column("actualizado_en", String(19)),
    sqlite_autoincrement=True,
)

suscripcion = Table("suscripcion", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("plan_id", Integer, nullable=False),
    Column("ciclo", String(8), nullable=False),                # mensual|anual
    Column("estado", String(12), nullable=False),              # activa|cancelada|morosa|terminada
    Column("renovar", Boolean, nullable=False, default=True),
    Column("fuente_pago_id", String(40)),                      # payment_source de Wompi
    Column("medio_fuente", String(12)),                        # CARD|NEQUI
    Column("fuente_resumen", String(40)),                      # «Visa ···4242»; nunca el número
    Column("correo", String(120)),
    Column("cubierto_hasta", String(19)),
    Column("proximo_cobro", String(19)),
    Column("intentos_fallidos", Integer, nullable=False, default=0),
    # Precio que la persona aceptó (planes 5/8, revisión): las renovaciones cobran esto, nunca el precio actual del plan.
    Column("precio_usd", Integer),
    Column("precio_anual_usd", Integer),
    Column("usuario", String(80), nullable=False),
    Column("creada_en", String(19)),
    Column("actualizada_en", String(19)),
    # A lo más una suscripción no terminada por cliente.
    sa.Index("uq_suscripcion_viva", "cliente", unique=True, sqlite_where=sa.text("estado != 'terminada'")),
    sqlite_autoincrement=True,
)

periodo_plan = Table("periodo_plan", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("suscripcion_id", Integer, nullable=False),
    Column("inicio", String(19), nullable=False),
    Column("fin", String(19), nullable=False),
    Column("precio_usd", Integer, nullable=False),             # foto del plan para ese mes
    Column("margen", Float, nullable=False),
    Column("tope_incluido_usd", Float, nullable=False),
    Column("credito_milesimas", Integer, nullable=False),
    Column("pago_id", Integer),                                # pago_plan que lo cubre; NULL = activado a mano
    Column("cerrado", Boolean, nullable=False, default=False),
    sa.UniqueConstraint("suscripcion_id", "inicio", name="uq_periodo_suscripcion_inicio"),
    sqlite_autoincrement=True,
)

pago_plan = Table("pago_plan", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("suscripcion_id", Integer, nullable=False),
    Column("ciclo", String(8), nullable=False),
    Column("usd", Integer, nullable=False),
    Column("trm", Float),
    Column("monto_cop_centavos", Integer),
    Column("referencia", String(60), nullable=False, unique=True),   # pl-<suscripcion>-<AAAAMMDD>-<intento>
    Column("transaccion_id", String(40), unique=True),
    Column("estado", String(12), nullable=False),              # pendiente|aprobado|rechazado|error|anulado
    Column("motivo", String(300)),
    Column("creado_en", String(19)),
    Column("actualizado_en", String(19)),
    Column("medio", String(12), nullable=False),               # wompi|manual
    Column("usuario", String(80)),
    # La bolsa mensual que compró este pago (revisión 3 de la Task 5): cada periodo que abre, aunque abra meses
    # después, acredita esto y no el precio del plan de ese día.
    Column("precio_mes_usd", Integer),
    sqlite_autoincrement=True,
)

# ---------------------------------------------------- referentes ---
# Biblioteca de referentes (spec 2026-09-23 §3). `cliente` NULL = global de
# Creatv; por eso no usa _comunes() (que exige cliente NOT NULL).

referente_familia = Table("referente_familia", metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre", String(120), nullable=False, unique=True),
    Column("descripcion", Text),
    Column("descripcion_en", Text),                                   # §B7 (migración 0022)
    Column("origen", String(12), nullable=False, default="copycoders"),     # copycoders|claude|admin
    Column("creado_en", String(19), nullable=False),
)

barrido = Table("barrido", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), index=True),                              # NULL = global (admin)
    Column("creado_en", String(19), nullable=False),
    Column("actualizado_en", String(19), nullable=False),
    Column("fuente", String(12), nullable=False),                           # copycoders|atria|apify|trendtrack|triple_whale
    Column("consulta", JSON, default=dict),
    Column("tope", Integer, default=0),
    Column("estado", String(12), nullable=False, default="en_cola"),        # en_cola|trayendo|guardando|clasificando|listo|parcial|error
    Column("traidos", Integer, default=0),
    Column("nuevos", Integer, default=0),
    Column("clasificados", Integer, default=0),
    Column("pendientes", Integer, default=0),
    Column("con_imagen", Integer, default=0),
    Column("usd_estimado", Float, default=0.0),
    Column("usd_real", Float, default=0.0),
    Column("llamadas_fuente", Integer, default=0),
    Column("tarea_id", Integer),
    Column("pedido_por", String(40)),
    Column("aviso", Text),
    Column("extra", JSON, default=dict),
)

referente = Table("referente", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), index=True),                              # NULL = global
    Column("creado_en", String(19), nullable=False),
    Column("actualizado_en", String(19), nullable=False),
    Column("anuncio_id", String(40), nullable=False),          # id del Ad Library de Meta
    Column("pagina_id", String(40), index=True),                            # id de página de Meta (marca)
    Column("fuente", String(12), nullable=False),                           # copycoders|atria|apify|trendtrack|triple_whale
    Column("marca", String(160)),
    Column("url_anuncio", Text),
    Column("url_marca", Text),
    Column("titular", Text),
    Column("cuerpo", Text),
    Column("idioma", String(5)),
    Column("pais", String(2)),
    Column("tipo", String(8), nullable=False, default="imagen"),            # imagen|video|carrusel
    Column("imagen_url", Text),                                             # copia en R2
    Column("imagen_origen", Text),
    Column("estado_imagen", String(10), nullable=False, default="pendiente"),   # ok|pendiente|error
    Column("dias", Integer),
    Column("variantes", Integer),
    Column("primera_vez", String(10)),
    Column("ultima_vez", String(10)),
    Column("activo", Boolean),
    Column("etiquetas_fuente", JSON, default=dict),
    Column("etapa", String(3)),                                             # TOF|MOF|BOF
    Column("consciencia", String(16)),                                      # unaware|problem-aware|solution-aware|product-aware|most-aware
    Column("familia", String(120)),
    Column("dolor", String(120)),
    Column("firma", Text),
    Column("clasificacion", String(10), nullable=False, default="pendiente"),   # fuente|claude|pendiente|error
    Column("barrido_id", Integer, sa.ForeignKey("barrido.id"), index=True),
    Column("extra", JSON, default=dict),
    sa.Index("ix_referente_filtros", "cliente", "etapa", "consciencia", "familia"),
    sa.Index("ix_referente_fuente_estado", "fuente", "estado_imagen"),  # /admin/referentes (0026)
)

sa.Index("uq_referente_cliente_anuncio", referente.c.cliente, referente.c.anuncio_id,
         unique=True, sqlite_where=referente.c.cliente.isnot(None))
sa.Index("uq_referente_global_anuncio", referente.c.anuncio_id,
         unique=True, sqlite_where=referente.c.cliente.is_(None))

kv = Table("kv", metadata,
    Column("clave", String(120), primary_key=True),
    Column("valor", Text),
    Column("actualizado_en", String(19), nullable=False),
)

# Alertas (docs/superpowers/specs/2026-09-20-alertas-design.md §4 y §12): lo
# ÚNICO que se guarda de ellas. Cada alerta se calcula al vuelo; esta tabla
# solo recuerda qué descartó una persona y con qué huella (la «situación» de
# la alerta): si la situación cambia, la alerta vuelve a verse. PK compuesta
# para que el upsert sea atómico entre procesos (un blob en `kv` perdería
# descartes). Solo la escribe alertas.py (migración 0029).
alerta_descartada = Table("alerta_descartada", metadata,
    Column("cliente", String(80), primary_key=True),
    Column("clave", String(200), primary_key=True),
    Column("huella", String(64), nullable=False),
    Column("descartada_en", String(19), nullable=False),
)

# --- Cuentas (docs/superpowers/plans/2026-09-19-cuentas-correo-verificado.md) ---
# Tokens de verificación de correo y de restablecimiento de contraseña. El
# usuario sigue viviendo en usuarios.json; acá solo va el sha256 del token
# (nunca el token crudo), su tipo, para quién es, a qué correo se mandó,
# cuándo vence y cuándo se usó — de un solo uso (migración 0011).

token_cuenta = Table("token_cuenta", metadata,
    Column("id", Integer, primary_key=True),
    Column("usuario", String(80), nullable=False, index=True),
    Column("tipo", String(12), nullable=False),               # verificacion|restablecer
    Column("correo", String(254), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("creado_en", String(19), nullable=False),
    Column("vence_en", String(19), nullable=False),
    Column("usado_en", String(19)),
    Column("ip", String(45)),
)

# --- Sprints de contenido (docs/superpowers/specs/2026-09-16-sprints-design.md, Parte 1) ---

persona = Table("persona", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(120), nullable=False),
    Column("resumen", String(200)),
    Column("descripcion", Text),
    Column("edad_rango", String(20)),
    Column("tono", Text),
    Column("senales_visuales", JSON, default=list),
    Column("palabras_clave", JSON, default=list),
    Column("color", String(7)),
    Column("origen", String(12), nullable=False, default="manual"),      # manual|sugerida_ia
    Column("archivada", Boolean, default=False),
    Column("extra", JSON, default=dict),
)

temporada = Table("temporada", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(120), nullable=False),
    Column("inicio", String(10), nullable=False),                        # YYYY-MM-DD
    Column("fin", String(10), nullable=False),
    Column("contexto", Text),
    Column("mood_visual", JSON, default=dict),
    Column("tipo", String(12), nullable=False, default="propia"),        # comercial|estacional|propia
    Column("archivada", Boolean, default=False),
    Column("extra", JSON, default=dict),
)

sprint = Table("sprint", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(200), nullable=False),
    Column("inicio", String(10), nullable=False),
    Column("fin", String(10), nullable=False),
    Column("estado", String(20), nullable=False, default="planeando"),
    Column("destinos", JSON, default=list),                             # ["es_CO", ...]
    Column("referencias_objetivo_defecto", Integer, default=5),
    Column("notas", Text),
    Column("archivado", Boolean, default=False),
    Column("extra", JSON, default=dict),                                # listo_manual, qa_umbral, modelos del lote
    Column("pais", String(2)),                                          # mercado del sprint (0021)
    Column("idioma", String(5)),
    Column("marcas", JSON),                                             # [{nombre, pagina_id?}] a imitar
    Column("momento", JSON),                                            # {clave?, nombre, contexto?, inicio?, fin?, mood_visual?}
)

campana = Table("campana", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("sprint_id", Integer, sa.ForeignKey("sprint.id"), nullable=False, index=True),
    Column("persona_id", Integer, sa.ForeignKey("persona.id"), nullable=False),
    Column("catalogo_id", String(120), nullable=False),                  # carpeta del producto en el catálogo de Crear
    Column("producto_id", Integer, sa.ForeignKey("producto.id")),        # bloque 5, cuando enlace catálogo y tabla
    Column("temporada_id", Integer, sa.ForeignKey("temporada.id"), nullable=True),     # opcional desde 0020
    Column("n_videos", Integer, nullable=False, default=0),
    Column("n_imagenes", Integer, nullable=False, default=0),
    Column("referencias_objetivo", Integer, default=5),
    Column("estado", String(20), nullable=False, default="planeada"),
    Column("orden", Integer, default=0),
    Column("extra", JSON, default=dict),
    Column("funnel", String(3), default="tof"),                          # tof|mof|bof (migración 0014)
    Column("consciencia", String(24)),                                  # clave de doctrina.CONSCIENCIAS (0021)
    Column("dolor", Text),
    Column("familias", JSON),                                           # nombres de referente_familia
    Column("pais", String(2)),                                          # NULL = hereda del sprint
    Column("idioma", String(5)),
    Column("marcas", JSON),
)

referencia = Table("referencia", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("campana_id", Integer, sa.ForeignKey("campana.id"), nullable=False, index=True),
    Column("tipo", String(6), nullable=False),                          # imagen|video
    Column("url", Text, nullable=False),
    Column("frame_url", Text),
    Column("ruta_local", Text),
    Column("origen", String(12), nullable=False, default="archivo"),    # archivo|link|catalogo|reutilizada
    Column("titulo", String(200)),
    Column("intencion", JSON, default=list),                            # etiquetas de sprints.datos.INTENCIONES
    Column("intencion_otro", String(200)),
    Column("descripcion", Text),
    Column("analisis", JSON),
    Column("analisis_estado", String(10), default="pendiente"),         # pendiente|listo|error
    Column("estado", String(8), nullable=False, default="borrador"),    # borrador|lista
    Column("orden", Integer, default=0),
    Column("extra", JSON, default=dict),
)

campana_pieza = Table("campana_pieza", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("campana_id", Integer, sa.ForeignKey("campana.id"), nullable=False, index=True),
    Column("tipo", String(6), nullable=False),                          # video|imagen
    Column("titulo", String(200)),
    Column("escena", Text),
    Column("sonido", Text),
    Column("enfoque", String(20)),
    Column("gancho", String(200)),
    Column("referencias_ids", JSON, default=list),
    Column("duracion_s", Float),
    Column("plataformas", JSON, default=list),
    Column("estado_idea", String(10), nullable=False, default="propuesta"),   # propuesta|aprobada|descartada
    Column("cf_id", String(60), index=True),                            # legado_id de la sesión de Crear
    Column("qa", JSON),
    Column("revision", String(10), nullable=False, default="pendiente"),      # pendiente|aprobada|rechazada
    Column("revision_motivo", Text),
    Column("textos", JSON),
    Column("orden", Integer, default=0),
    Column("extra", JSON, default=dict),
)

sprint_evento = Table("sprint_evento", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("sprint_id", Integer, sa.ForeignKey("sprint.id"), nullable=False, index=True),
    Column("campana_id", Integer, sa.ForeignKey("campana.id")),
    Column("tipo", String(30), nullable=False),
    Column("mensaje", Text),
    Column("datos", JSON, default=dict),
    Column("creado_en", String(19), nullable=False),
    sa.Index("ix_sprint_evento_campana", "campana_id"),  # clave foránea (0026)
)

# --- Nicho y avatares (docs/superpowers/specs/2026-09-18-nicho-avatares-design.md §2, migración 0011) ---

estudio = Table("estudio", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(120), nullable=False),
    Column("producto", Text),                                   # qué vendemos (texto libre, prellenado desde el catálogo)
    Column("catalogo_id", String(80)),
    Column("tema", Text),                                       # qué investigar: nicho, mercado, dolores
    Column("idioma", String(5), nullable=False, default="es"),  # idioma de salida de los avatares
    Column("pais", String(2), index=True),                      # ISO-3166-1 alfa-2 (Parte 3, migración 0016 con ix_estudio_pais); NULL = sin país
    Column("estado", String(12), nullable=False, default="armando"),   # armando|generando|revisando
    Column("archivado", Boolean, default=False),
    Column("generacion", Integer, nullable=False, default=0),   # corridas de Claude
    Column("extra", JSON, default=dict),                        # recolecciones, ultima_generacion, ultimo_error
)

comentario = Table("comentario", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("estudio_id", Integer, sa.ForeignKey("estudio.id"), nullable=False, index=True),
    Column("fuente", String(12), nullable=False),               # texto|csv|reddit|youtube|apify
    Column("fuente_id", String(120), nullable=False),           # id en la fuente; hash del texto para texto/csv
    Column("texto", Text, nullable=False),
    Column("url", String(500)),
    Column("contexto", String(300)),                            # título del post / video / producto
    Column("puntuacion", Integer),                              # votos, likes o estrellas
    Column("fecha", String(19)),
    Column("excluido", Boolean, default=False),                 # nunca entra a la generación
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("estudio_id", "fuente", "fuente_id", name="uq_comentario_fuente"),
)

avatar = Table("avatar", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("estudio_id", Integer, sa.ForeignKey("estudio.id"), nullable=False, index=True),
    Column("padre_id", Integer, sa.ForeignKey("avatar.id")),    # NULL = núcleo; id del núcleo = sub-avatar
    Column("tipo", String(8), nullable=False),                  # nucleo|sub
    Column("base", String(24)),                                 # emocion|experiencia_producto (solo sub)
    Column("orden", Integer, nullable=False, default=0),
    Column("generacion", Integer, nullable=False, default=0),
    Column("nombre", String(120), nullable=False),
    Column("deseo", String(300)),
    Column("resumen", Text),                                    # solo núcleo
    Column("demografia", Text),
    Column("edad_rango", String(20)),
    Column("emocion", Text),
    Column("identidad", JSON, default=dict),                    # {quiere_que_vean, cree_de_si, quiere_lograr}
    Column("soluciones_previas", JSON, default=list),           # [{que, por_que_fallo: [..]}]
    Column("situaciones", JSON, default=list),
    Column("comportamiento", Text),
    Column("conciencia", JSON, default=dict),                   # {nivel, detalle}
    Column("encaje_producto", Text),
    Column("tono", Text),
    Column("palabras_clave", JSON, default=list),
    Column("evidencia", JSON, default=list),                    # [{comentario_id, cita}] verificadas
    Column("sin_evidencia", Boolean, default=False),
    Column("estado", String(12), nullable=False, default="propuesto"),   # propuesto|aprobado|descartado
    Column("persona_id", Integer, sa.ForeignKey("persona.id")),
    Column("extra", JSON, default=dict),
    sa.Index("ix_avatar_padre", "padre_id"),  # clave foránea (0026)
)

# --- Nicho Parte 3: productos encontrados por la investigación (migración 0016) ---

producto_nicho = Table("producto_nicho", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("estudio_id", Integer, sa.ForeignKey("estudio.id"), nullable=False, index=True),
    Column("plataforma", String(12), nullable=False),           # clave de nicho.fuentes.plataformas (amazon, meli, tiktok_shop, walmart, aliexpress)
    Column("fuente_id", String(120), nullable=False),           # ASIN, id de MELI, id de TikTok Shop
    Column("consulta", String(200), nullable=False, default=""),   # la búsqueda que lo encontró
    Column("titulo", String(300), nullable=False),
    Column("marca", String(120)),
    Column("precio", Float),
    Column("moneda", String(3)),
    Column("estrellas", Float),
    Column("n_resenas", Integer),                               # reseñas que la plataforma dice tener
    Column("url", String(500)),
    Column("imagen", String(500)),
    Column("relevante", Boolean, index=True),                   # NULL = Claude no lo ha juzgado
    Column("motivo", String(300)),
    Column("resenas_traidas", Integer, default=0),              # cuántas reseñas suyas se guardaron (no se vuelve a pagar)
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("estudio_id", "plataforma", "fuente_id", name="uq_producto_nicho_unico"),
)

# --- Flow Plus en Crear: prompts que se corrigen conversando con Claude antes de generar (migración 0018) ---

guion_prompt = Table("guion_prompt", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("origen", String(12), nullable=False, default="manual"),     # manual|pipeline
    Column("tipo", String(12), nullable=False, default="libre"),        # clip|imagen|libre
    Column("titulo", String(200)),
    Column("contexto", Text),                                           # guion o notas que Claude debe conocer
    Column("texto_fijo", JSON, default=list),                           # fragmentos que van literales en toda versión
    Column("texto_original", Text, nullable=False),
    Column("texto_vigente", Text, nullable=False),
    Column("version_n", Integer, nullable=False, default=1),            # CAS de usar/editar
    Column("estado", String(12), nullable=False, default="abierto"),    # abierto|aprobado
    Column("extra", JSON, default=dict),                                # el pipeline guarda video_id/clip_index
    sa.Index("ix_guion_prompt_cliente_actualizado", "cliente", "actualizado_en"),
)

guion_mensaje = Table("guion_mensaje", metadata,
    Column("id", Integer, primary_key=True),
    Column("prompt_id", Integer, sa.ForeignKey("guion_prompt.id"), nullable=False, index=True),
    Column("creado_en", String(19), nullable=False),
    Column("rol", String(8), nullable=False),                           # persona|claude
    Column("usuario", String(40)),
    Column("contenido", Text),
    Column("propuesta", Text),                                          # prompt COMPLETO propuesto; NULL = sin cambio
    Column("problemas", JSON, default=list),
    Column("estado", String(12), nullable=False, default="ok"),         # ok|pendiente|error
    Column("aplicada", Boolean, default=False),
    Column("usd", Float, default=0.0),
)

# --- Flow Plus: pipeline guion -> prompts (spec 2026-09-25, migración 0019) ---

guion_lote = Table("guion_lote", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("fuente", String(10), nullable=False, default="texto"),       # texto|notion
    Column("notion_page_id", String(40)),
    Column("titulo", String(200)),
    Column("texto_crudo", Text, nullable=False, default=""),
    Column("estado", String(12), nullable=False, default="leyendo"),     # leyendo|leido|error
    Column("aviso", Text),
    Column("usd", Float, default=0.0),
    Column("iniciado_en", String(19)),                                   # vencimiento del trabajo
    Column("extra", JSON, default=dict),
)

guion = Table("guion", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("lote_id", Integer, sa.ForeignKey("guion_lote.id"), nullable=False, index=True),
    Column("orden", Integer, nullable=False, default=0),
    Column("titulo", String(200)),
    Column("lectura", JSON, default=dict),
    Column("estado", String(12), nullable=False, default="leido"),       # leido|confirmado
    Column("extra", JSON, default=dict),
)

guion_video = Table("guion_video", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("guion_id", Integer, sa.ForeignKey("guion.id"), nullable=False, index=True),
    Column("version_n", Integer, nullable=False),
    Column("nombre", String(120)),
    Column("config", JSON, default=dict),
    Column("recorte", JSON, default=dict),
    Column("plan", JSON),
    Column("clips", JSON),
    Column("hooks_alt", JSON),
    Column("validaciones", JSON),
    Column("avisos", JSON),
    Column("imagenes", JSON),
    Column("estado", String(12), nullable=False, default="configurando"),  # configurando|recortando|armando|armado|invalido|error
    Column("estado_imagenes", String(12), nullable=False, default="ninguno"),  # ninguno|escribiendo|listo|error
    Column("aviso", Text),
    Column("aviso_imagenes", Text),
    Column("iniciado_en", String(19)),
    Column("usd", Float, default=0.0),
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("guion_id", "version_n", name="uq_guion_video_version"),
)

# --- monitoreo (spec 2026-10-01-escala-y-monitoreo §6, migración 0027) -------
# Un error de la plataforma por huella (origen + tipo + dónde + ruta): cuántas
# veces pasó, la primera y la última, y la traza de la última, sin tokens.
# Único escritor: monitoreo.py.
error_app = Table("error_app", metadata,
    Column("id", Integer, primary_key=True),
    Column("huella", String(40), nullable=False, unique=True),
    Column("origen", String(8), nullable=False),            # web|worker|hilo|log
    Column("tipo", String(120), nullable=False),            # clase de la excepción o el logger
    Column("mensaje", Text),
    Column("ubicacion", String(300)),                       # archivo:línea función() más adentro de la app
    Column("traza", Text),
    Column("ruta", String(200)),                            # endpoint, tipo de tarea o plantilla del log
    Column("metodo", String(8)),
    Column("url", String(500)),                             # sin query string
    Column("cliente", String(80)),
    Column("usuario", String(80)),
    Column("veces", Integer, nullable=False, default=1),
    Column("primera_vez", String(19), nullable=False),
    Column("ultima_vez", String(19), nullable=False),
    Column("estado", String(10), nullable=False, default="abierto"),   # abierto|resuelto|silenciado
    Column("resuelto_en", String(19)),
    Column("extra", JSON, default=dict),
    sa.Index("ix_error_app_estado_ultima", "estado", "ultima_vez"),
    sa.Index("ix_error_app_ultima", "ultima_vez"),
)


def crear_todo():
    """Solo para tests y scripts locales. En producción manda Alembic."""
    metadata.create_all(engine())

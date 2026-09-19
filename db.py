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


def engine():
    """Engine singleton del proceso. SQLite con WAL para que gunicorn (hilos) y
    el worker (otro proceso) lean y escriban a la vez sin 'database is locked'."""
    global _ENGINE
    if _ENGINE is None:
        u = url()
        asegurar_carpeta()
        _ENGINE = sa.create_engine(u, connect_args={"check_same_thread": False, "timeout": 5}, future=True)

        @sa.event.listens_for(_ENGINE, "connect")
        def _pragmas(dbapi_con, _):
            cur = dbapi_con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
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
)

kv = Table("kv", metadata,
    Column("clave", String(120), primary_key=True),
    Column("valor", Text),
    Column("actualizado_en", String(19), nullable=False),
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
)

campana = Table("campana", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("sprint_id", Integer, sa.ForeignKey("sprint.id"), nullable=False, index=True),
    Column("persona_id", Integer, sa.ForeignKey("persona.id"), nullable=False),
    Column("catalogo_id", String(120), nullable=False),                  # carpeta del producto en el catálogo de Crear
    Column("producto_id", Integer, sa.ForeignKey("producto.id")),        # bloque 5, cuando enlace catálogo y tabla
    Column("temporada_id", Integer, sa.ForeignKey("temporada.id"), nullable=False),
    Column("n_videos", Integer, nullable=False, default=0),
    Column("n_imagenes", Integer, nullable=False, default=0),
    Column("referencias_objetivo", Integer, default=5),
    Column("estado", String(20), nullable=False, default="planeada"),
    Column("orden", Integer, default=0),
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("sprint_id", "persona_id", "catalogo_id", "temporada_id", name="uq_campana_combinacion"),
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
)


def crear_todo():
    """Solo para tests y scripts locales. En producción manda Alembic."""
    metadata.create_all(engine())

# Mapa del repositorio


Regenerado desde el código del worktree el 2026-10-08.

824 fuentes: 630 Python, 131 plantillas, 46 JavaScript y 17 CSS. 46 declaraciones Table en db.py; 355 decoradores de rutas; 56 tareas con @registrar en tareas/.

Inventario del código local, incluidos archivos nuevos sin commit. Los conteos son declaraciones estáticas: las rutas de blueprints se muestran relativas a su prefijo y las altas por add_url_rule no se cuentan como decoradores. Las descripciones proceden del docstring del módulo; las líneas, del archivo actual. Se excluyen datos de clientes, secretos, submódulos y los dos artefactos generados mapa_codigo.html/style.css.


La guía del agente es AGENTS.md; las reglas de cada área viven en .claude/skills/. dashboard.py declara la web; worker.py ejecuta las tareas registradas. trabajos.py contiene tanto encolado como hilos: el inventario no presume que toda llamada pagada pase por el worker.


## Inventario

| Archivo | Líneas | Área | Docstring o funciones declaradas |
| --- | --- | --- | --- |
| _json_store.py | 47 | raíz | Helper genérico de lectura/escritura de un JSON por cliente — el mismo patrón |
| acciones.py | 545 | raíz | Acciones del motor (Bloque 4): lo que el decisor recomienda sobre una pieza o |
| admin.py | 375 | raíz | Panel de administrador: lo que el dueño de la plataforma necesita ver de |
| ads.py | 151 | raíz | Estado de Campañas (anuncios en Meta). Misma API de dicts de siempre — el |
| alertas.py | 689 | raíz | Alertas del proyecto: todo lo que necesita la atención de la persona, en un |
| atribucion.py | 93 | raíz | Atribución por tienda (Bloque 5): liga los pedidos que llegaron con |
| audios.py | 413 | raíz | Audios en Crear (spec docs/superpowers/specs/2026-09-28-crear-audios-design.md): |
| auth/auth_tiktok.py | 127 | auth | Autorización OAuth de una sola vez para TikTok. |
| auth/auth_youtube.py | 62 | auth | Autorización OAuth de una sola vez para YouTube. |
| banco_prompts.py | 84 | raíz | Banco de recetas para la acción central de FlowPlus. |
| bitacora.py | 29 | raíz | Registro simple de eventos (generación, storage, publicación) en un CSV. |
| catalogo_i18n.py | 135 | raíz | Catálogo de traducciones (Flask-Babel; spec 2026-09-26-idioma-y-modo-oscuro §B1). |
| catalogo_productos.py | 793 | raíz | Catálogo de productos para el flujo de "cambiar calzado": cada carpeta en |
| catalogo_vista.py | 116 | raíz | Catálogo › galería (spec 2026-09-28 §10.2): funciones puras sobre lo que ya |
| cifrado.py | 41 | raíz | Cifrado simétrico de credenciales de tiendas (spec §2 `tienda.credenciales`): |
| cola.py | 287 | raíz | Cola persistente sobre la tabla `tarea` (db.py). La consumen el worker |
| comparar_modelos.py | 158 | raíz | Corre la MISMA foto o el MISMO video, y el MISMO producto, contra varios modelos |
| comparar_seedance_turbo.py | 281 | raíz | Compara Seedance 2.5 con su acceso Turbo de WaveSpeed antes de cambiar el modelo |
| conceptos_imagen.py | 123 | raíz | Estado del flujo imagen-primero: una idea -> N escenas (conceptos) -> cada escena se |
| conectores/__init__.py | 49 | conectores | Paquete de conectores de tienda. `por_tipo("shopify")` devuelve la clase |
| conectores/_http.py | 117 | conectores | HTTP común de los conectores con API (Shopify, Woo, MELI). |
| conectores/base.py | 303 | conectores | Contrato común de los conectores de tienda (bloque 5 del motor de ecommerce). |
| conectores/csv_excel.py | 176 | conectores | Catálogo desde un archivo `.csv` o `.xlsx` subido por el cliente (sin API). |
| conectores/meli.py | 307 | conectores | Conector MercadoLibre — API pública con OAuth de usuario |
| conectores/shopify.py | 279 | conectores | Conector Shopify — Admin GraphQL (`/admin/api/2025-07/graphql.json`, header |
| conectores/shopify_publico.py | 338 | conectores | Conector `shopify_publico` (spec 2026-09-28 §6): el catálogo PÚBLICO de una |
| conectores/url.py | 329 | conectores | Un producto a partir de la URL de su página (sin API, sin credenciales). |
| conectores/woo.py | 149 | conectores | Conector WooCommerce — REST `wc/v3` con auth básica (consumer key/secret) |
| creative_flow.py | 529 | raíz | Estado de Crear (FlowPlus). Misma API de dicts de siempre (cargar/crear/ |
| cuentas.py | 301 | raíz | Cuentas: tokens de un solo uso (verificar correo, restablecer contraseña), |
| dashboard.py | 8703 | raíz | Dashboard web local: clientes, personajes, briefs/prompts, videos, aprobación y |
| db.py | 1002 | raíz | Base de datos del motor (SQLite + SQLAlchemy Core). Una sola base por servidor |
| decisor.py | 211 | raíz | Decisor (spec §5): función pura sobre snapshots + reglas + contexto. Tráfico |
| deploy/cola_vacia.py | 53 | deploy | ¿Se puede reiniciar el worker? Sale con 0 si la cola está vacía y con 1 si hay algo vivo. |
| deploy/gunicorn.conf.py | 55 | deploy | Configuración de gunicorn del VPS (spec 2026-10-01-escala-y-monitoreo §3). |
| derivaciones.py | 638 | raíz | Derivaciones (Bloque 4): producir piezas nuevas a partir de una pieza del |
| director.py | 311 | raíz | Director de prompts de Crear (spec 2026-09-18-director-prompts-crear-design §2). |
| doctrina/__init__.py | 529 | doctrina | Doctrina de venta (spec docs/superpowers/specs/2026-09-25-doctrina-copywriting-design.md). |
| doctrina/aprendizajes.py | 131 | doctrina | Aprendizajes por proyecto (doctrina, bloque 4; spec |
| doctrina/diagnostico.py | 228 | doctrina | Diagnóstico de una pieza perdedora (doctrina, bloque 4; spec |
| doctrina/pagina.py | 79 | doctrina | Página «Cómo escribe Creatv» (doctrina, bloque 2, §6): los textos de |
| doctrina/pedidos.py | 119 | doctrina | «Lo que Claude necesita» (doctrina, bloque 2, §5.2–5.3). |
| doctrina/producto.py | 132 | doctrina | Pruebas y pedidos de un producto (doctrina, bloque 2, §5). |
| doctrina/revisor.py | 485 | doctrina | El revisor de la pieza terminada (doctrina, bloque 3; spec |
| ediciones.py | 223 | raíz | Ediciones del editor (spec §5): CRUD sobre `edicion` y `edicion_version`. |
| estado.py | 56 | raíz | Manifiesto de estado de cada video: pendiente / rechazado / publicado. |
| estilos.py | 164 | raíz | Sistema de estilos (spec docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md). |
| experimentos.py | 774 | raíz | Experimentos del motor (no legado): un experimento agrupa piezas (finales por |
| final_edition/__init__.py | 863 | final_edition | Final edition: localización, producción y render de piezas finales por |
| final_edition/biblioteca.py | 476 | final_edition | Biblioteca del editor (spec editor capa 4b, Task 1): subir un archivo del |
| final_edition/borrador.py | 328 | final_edition | Borrador automático (spec §5 «Borrador», §7.2): del guion, los cortes y |
| final_edition/cortes.py | 156 | final_edition | Final Edition, capa 1: detección de cortes de escena con ffmpeg (`scdet`) y |
| final_edition/documento.py | 761 | final_edition | Documento de edición (spec editor §1): la única fuente de verdad de un |
| final_edition/edicion_clon.py | 96 | final_edition | «Editar este video» (editor, capa 4a): una edición nueva armada solo con |
| final_edition/encuadre.py | 114 | final_edition | El encuadre de un clip de la pista principal (editor, capa 5b, spec D4-D7): |
| final_edition/estimar.py | 46 | final_edition | Tiempo estimado de render (spec §2.2), para mostrarlo en el botón Producir. |
| final_edition/fotos.py | 107 | final_edition | Las copias de una foto que usa el editor (capa 5b): la que entra al |
| final_edition/fuentes.py | 366 | final_edition | Las fuentes del editor y su tabla tipográfica (spec editor capa 5c, D4/D6). |
| final_edition/geometria.py | 83 | final_edition | Geometría compartida navegador/servidor (spec editor §1.2 y §3): de |
| final_edition/guion.py | 662 | final_edition | Capa 0 de Final Edition: guion estructurado con Claude. |
| final_edition/insumos.py | 212 | final_edition | Insumos del borrador (spec §1 «Material», §2.3 «caché»): lo que el |
| final_edition/mezcla.py | 130 | final_edition | Mezcla de audio (spec estudio S1/S2): la única fábrica del filtro que junta |
| final_edition/motor/__init__.py | 73 | final_edition | Motor de render del editor (spec editor §2): compila un documento resuelto |
| final_edition/motor/compilador.py | 582 | final_edition | Compilador (spec §2.1): documento resuelto → Plan {entradas, filtergraph}. |
| final_edition/motor/render.py | 98 | final_edition | Ejecución del plan con ffmpeg (spec §2.1 punto 6 y §2.2): un proceso por |
| final_edition/motor/subtitulos.py | 308 | final_edition | Subtítulos como un solo archivo ASS (spec §2.1 punto 5): un filtro |
| final_edition/motor/tramos.py | 182 | final_edition | Partición del render por tramos (spec §2.2): cada `overlay` de ffmpeg |
| final_edition/musica.py | 155 | final_edition | Final Edition, capa 3: biblioteca propia de música de fondo generada con |
| final_edition/produccion.py | 504 | final_edition | Producción de una final por la vía del editor (spec §2.4, §5, §7.2): el |
| final_edition/rasterizar.py | 297 | final_edition | Rasterizador de texto del servidor (Pillow) — spec §2.1 punto 3 y §5 |
| final_edition/render.py | 211 | final_edition | Final Edition, capa 4b: render del video final con ffmpeg en un solo |
| final_edition/rutas_editor.py | 598 | final_edition | Blueprint del editor (capa 3: la vista previa de una edición). Rutas bajo |
| final_edition/sonido.py | 52 | final_edition | Sonido de la escena (spec estudio S1): sugerencia con Claude de qué se |
| final_edition/stickers.py | 390 | final_edition | Stickers propios del editor (capa 5c, D11): 20 dibujos sin palabras, hechos aquí con Pillow, sin nada que bajar |
| final_edition/subtitulos_fuente.py | 183 | final_edition | Subtítulos derivados del audio (editor, capa 5a, spec D1-D4): el |
| final_edition/tablero.py | 107 | final_edition | Tablero de Final edition (pedido de Daniel, 2026-10-02): la pestaña ya no |
| final_edition/texto.py | 363 | final_edition | Final Edition, capa 4a: texto en pantalla rasterizado con Pillow. |
| final_edition/textos_editor.py | 494 | final_edition | Textos que ve la persona en el editor (static/editor/*.js), por clave. El |
| final_edition/tipografia.py | 450 | final_edition | La maqueta del texto (spec editor capa 5c, D5): dado un texto, su estilo y la |
| final_edition/tipos.py | 152 | final_edition | Tipos y constantes compartidas de Final Edition: roles del guion, países |
| final_edition/transcripcion.py | 108 | final_edition | Transcripción automática para subtítulos del editor (capa 5a, spec D5): se |
| final_edition/vista_previa.py | 221 | final_edition | Lo que la página de vista previa del editor necesita (spec editor §3, |
| final_edition/voz.py | 168 | final_edition | Final Edition, capa 2: locución por bloque del guion. Por cada bloque |
| flowplus_lanzar.py | 33 | raíz | Encolar en el worker la generación de una sesión de Crear (FlowPlus): imagen o |
| flowplus_prompt.py | 536 | raíz | Arma el prompt final de FlowPlus a partir de lo que escribió la persona. |
| gastos.py | 629 | raíz | Gasto real por proyecto: cuánto dinero (USD) se le pagó a los proveedores |
| generador_prompts.py | 472 | raíz | Genera prompts candidatos de video (para Higgsfield) a partir de una idea, usando |
| guiones/__init__.py | 7 | guiones | Modo «Flow Plus» de Crear. `refinador` guarda cada prompt (texto original, |
| guiones/cadena.py | 302 | guiones | Cadena de escenas de Flow Plus (spec 2026-09-30, «Generar todas las escenas»): |
| guiones/claude.py | 125 | guiones | Un solo punto para hablar con Claude desde el pipeline de Flow Plus: la |
| guiones/clips.py | 407 | guiones | Paso 2 del pipeline de Flow Plus (spec 2026-09-25 §7): Claude planea los |
| guiones/config.py | 107 | guiones | Configuración de una versión de video de Flow Plus (spec 2026-09-25 §5): se |
| guiones/datos.py | 482 | guiones | Único escritor de guion_lote, guion y guion_video (pipeline de Flow Plus, |
| guiones/duracion.py | 102 | guiones | Duraciones del pipeline de Flow Plus (spec 2026-09-25 §6 y §7.2; spec del |
| guiones/escenas.py | 311 | guiones | Imágenes de cada escena (clip) de una versión de Flow Plus (spec 2026-09-30). |
| guiones/imagenes.py | 272 | guiones | Paso 3 del pipeline de Flow Plus (spec 2026-09-25 §8): qué imágenes de |
| guiones/lectura.py | 155 | guiones | Paso 1 del pipeline de Flow Plus (spec 2026-09-25 §4): Claude separa el |
| guiones/medios.py | 22 | guiones | URL pública de una imagen de escena de Flow Plus: lo subido ya está en R2; |
| guiones/notion.py | 132 | guiones | Leer un guion desde una página de Notion (spec 2026-09-25 §9). Cada |
| guiones/plantillas.py | 145 | guiones | Texto que va al generador (spec 2026-09-25 §7.3; spec del cliente §2.4): |
| guiones/recorte.py | 118 | guiones | «Proponer qué quitar» (spec 2026-09-25 §6): Claude ordena las líneas de |
| guiones/refinador.py | 605 | guiones | Prompts de Flow Plus que se corrigen conversando con Claude ANTES de generar. |
| guiones/rutas.py | 169 | guiones | Blueprint JSON del chat de Flow Plus (prefijo /cliente/<cliente>/guiones): |
| guiones/rutas_pipeline.py | 654 | guiones | Blueprint del pipeline de Flow Plus (spec 2026-09-25 §10): el panel de |
| hablado.py | 242 | raíz | Anuncio hablado en Crear (spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md): |
| hablado_rutas.py | 122 | raíz | Rutas de Crear › Anuncio hablado (Blueprint `hablado`, prefijo |
| higgsfield_client.py | 200 | raíz | Cliente simple para la API de Higgsfield (generación de video imagen-a-video). |
| idiomas.py | 307 | raíz | Idioma de la interfaz y del proyecto (spec docs/superpowers/specs/ |
| importador.py | 750 | raíz | Importador (Bloque 5): producto normalizado de un conector → fila `producto` |
| informe.py | 186 | raíz | Informe de operación y de desarrollo, para sustentar una cuenta de cobro. |
| lanzador.py | 721 | raíz | Lanzador multi-país (spec §4): traduce un experimento a objetos de Meta — |
| llaves.py | 293 | raíz | Puesta a punto: la lista de servicios externos que el proyecto necesita |
| mapa_codigo_generar.py | 304 | raíz | Inventario estático: regenera ESTRUCTURA.md y el mapa sin importar la app. |
| mapa_corporal.py | 158 | raíz | Mapa corporal: dónde va un producto sobre el cuerpo, y en qué proporción. |
| marca.py | 77 | raíz | Identidad de marca de un cliente: imágenes/videos de referencia + una guía de |
| materiales.py | 238 | raíz | Materiales del editor (spec §1, §2.3, §5): cada archivo que entra o se |
| meta_agencia.py | 596 | raíz | Meta en modo agencia: UNA conexión del Business Manager de Creatv (token de |
| meta_conexion.py | 616 | raíz | Conexión de un proyecto con Meta (Facebook Login for Business) y sus |
| meta_detalle.py | 383 | raíz | Detalle de Meta por anuncio para el centro de resultados (spec |
| meta_errores.py | 102 | raíz | Errores de Meta en palabras de persona. |
| mi_musica.py | 148 | raíz | Mi música (spec docs/superpowers/specs/2026-09-25-mi-musica-design.md): las |
| migrar_gastos_historicos.py | 30 | raíz | Relleno único de la tabla `gasto` (nació el 2026-09-18) con lo que ya se había |
| migrar_json_a_db.py | 89 | raíz | Importa a la base del motor lo que hoy vive en JSON por cliente: |
| migrations/env.py | 44 | migrations | run_migrations_offline, run_migrations_online |
| migrations/versions/0001_tablas_motor.py | 353 | migrations | tablas motor |
| migrations/versions/0002_indice_experimento_legado.py | 29 | migrations | indice experimento legado |
| migrations/versions/0003_indice_tarea_viva.py | 32 | migrations | indice tarea viva por job_id |
| migrations/versions/0004_experimento_extra.py | 37 | migrations | experimento: destino_url, edades, error, extra |
| migrations/versions/0005_producto_extra.py | 45 | migrations | producto: extra, url_imagen_principal; tienda: nombre, dominio, error |
| migrations/versions/0006_sprints.py | 161 | migrations | sprints de contenido: persona, temporada, sprint, campana, referencia, campana_pieza, sprint_evento |
| migrations/versions/0007_merge_sprints.py | 30 | migrations | merge sprints y producto_extra |
| migrations/versions/0008_tarea_prioridad.py | 28 | migrations | tarea: prioridad (mayor se atiende antes; lotes de sprint = 3) |
| migrations/versions/0009_publicacion.py | 56 | migrations | publicacion: publicación orgánica de una pieza por plataforma |
| migrations/versions/0010_gasto.py | 47 | migrations | gasto: costo real en USD de cada cobro de un proveedor, por proyecto |
| migrations/versions/0011_token_cuenta.py | 45 | migrations | token_cuenta: tokens de un solo uso para verificar correo y restablecer contraseña |
| migrations/versions/0012_editor.py | 84 | migrations | editor: edicion, edicion_version, material y pieza.edicion_version_id |
| migrations/versions/0013_nicho.py | 101 | migrations | nicho: estudio, comentario y avatar (comentarios reales -> avatares -> personas) |
| migrations/versions/0014_sprints_funnel.py | 27 | migrations | sprints: agregar campo funnel (TOF/MOF/BOF) a campana |
| migrations/versions/0015_triple_whale.py | 72 | migrations | Triple Whale tabla para conexiones y atribución. |
| migrations/versions/0016_nicho_investigacion.py | 67 | migrations | nicho investigación: producto_nicho y estudio.pais |
| migrations/versions/0017_referentes.py | 107 | migrations | biblioteca de referentes: referente, referente_familia y barrido |
| migrations/versions/0018_guiones.py | 64 | migrations | guiones: guion_prompt y guion_mensaje (chat con Claude para corregir un prompt antes de generar) |
| migrations/versions/0019_guiones_pipeline.py | 90 | migrations | pipeline de Flow Plus: guion_lote, guion y guion_video |
| migrations/versions/0020_campana_temporada_opcional.py | 33 | migrations | sprints: la temporada de una campaña pasa a ser opcional |
| migrations/versions/0021_sprints_tablero.py | 52 | migrations | sprints: tablero — mercado, marcas y momento en el sprint; enfoque en la campaña |
| migrations/versions/0022_familia_descripcion_en.py | 32 | migrations | referentes: descripción en inglés de cada familia de formato |
| migrations/versions/0023_triple_whale_rendimiento.py | 100 | migrations | triple whale: métricas por anuncio y día, tienda por día y evaluaciones con IA |
| migrations/versions/0024_triple_whale_productos.py | 42 | migrations | triple whale: ventas por producto y día |
| migrations/versions/0025_producto_fila_por_producto.py | 76 | migrations | producto: una fila comercial por producto (spec 2026-09-28 §8) |
| migrations/versions/0026_indices_escala.py | 59 | migrations | índices que pidió la auditoría de consultas (escala) |
| migrations/versions/0027_error_app.py | 53 | migrations | errores de la plataforma agrupados (monitoreo) |
| migrations/versions/0028_metricas_detalle.py | 56 | migrations | detalle diario y desgloses de Meta por anuncio |
| migrations/versions/0029_alerta_descartada.py | 37 | migrations | alertas descartadas por proyecto |
| migrations/versions/0030_referente_por_proyecto.py | 36 | migrations | Referentes únicos por proyecto (PND-006, 2026-10-02). |
| migrations/versions/0031_material_identidad.py | 19 | migrations | Identidad no reutilizable de materiales y voces (PND-040, 2026-10-03). |
| modos.py | 35 | raíz | Modos de operación de un experimento (Bloque 4): deciden si una acción que el |
| monitoreo.py | 610 | raíz | Monitoreo de la plataforma (spec docs/superpowers/specs/2026-10-01-escala-y-monitoreo-design.md |
| nicho/__init__.py | 5 | nicho | Nicho y avatares: comentarios reales de la gente -> avatares por deseo (núcleo) |
| nicho/avatares.py | 695 | nicho | Generación de avatares con Claude (spec §4): dos pasadas — núcleos por deseo |
| nicho/calidad.py | 106 | nicho | Qué es un avatar «completo» (spec 2026-09-29 §2) y cómo se funde lo que |
| nicho/datos.py | 1012 | nicho | Datos del módulo Nicho (spec §2): estudios, comentarios y avatares. ÚNICO |
| nicho/exportar.py | 161 | nicho | Exportación de un estudio (spec §6): `.md` como el doc "Desire-Based Core |
| nicho/fuentes/__init__.py | 52 | nicho | Registro de fuentes de comentarios por `tipo`, con carga perezosa (como |
| nicho/fuentes/_http.py | 72 | nicho | HTTP común de las fuentes conectadas que hablan con `requests` (Reddit y |
| nicho/fuentes/apify.py | 106 | nicho | Fuente `apify` (spec §3.5): reseñas de Amazon y comentarios de TikTok a través |
| nicho/fuentes/apify_actores.py | 214 | nicho | Actores de Apify permitidos (spec §3.5), mismo patrón que |
| nicho/fuentes/archivo.py | 137 | nicho | Fuente `csv` (spec §3.2): un archivo .csv (delimitador detectado con |
| nicho/fuentes/base.py | 127 | nicho | Contrato común de las fuentes de comentarios (spec §3.1). Toda fuente |
| nicho/fuentes/plataforma.py | 152 | nicho | Fuente genérica de una plataforma del registro (spec Parte 3 §4): busca |
| nicho/fuentes/plataformas.py | 676 | nicho | Registro de tiendas para la investigación automática del nicho (spec Parte 3 |
| nicho/fuentes/reddit.py | 245 | nicho | Fuente `reddit` (spec §3.3): API oficial de Reddit con token de solo lectura. |
| nicho/fuentes/texto.py | 34 | nicho | Fuente `texto` (spec §3.2): comentarios pegados a mano en un cuadro de texto. |
| nicho/fuentes/youtube.py | 224 | nicho | Fuente `youtube` (spec §3.4): YouTube Data API v3 con llave simple |
| nicho/investigacion.py | 493 | nicho | Máquina de estados de la investigación automática del nicho (spec Parte 3 |
| nicho/rutas.py | 745 | nicho | Rutas de la pestaña Nicho (Blueprint `nicho`, prefijo /cliente/<cliente>/nicho). |
| notificaciones.py | 152 | raíz | Avisos por correo del motor (Bloque 4): propuestas pendientes, ganadores, |
| organico.py | 795 | raíz | Publicación orgánica de una pieza (bloque 7): la ganadora de un experimento, |
| plantillas_anuncio.py | 224 | raíz | Recetas de tomas para «Crear super prompt con IA» (spec |
| plataformas.py | 3 | raíz | Preferencias de formato comunes a los caminos de generación. |
| precalentar_muestras.py | 46 | raíz | Precalienta las muestras de voz de la galería de Audios (Crear › Audios): |
| presupuesto_experimentos.py | 119 | raíz | El presupuesto de un experimento nuevo («Nuevo experimento › Cuánto»), sin acceso a Meta ni efectos secundarios. |
| prompt_swap.py | 204 | raíz | Los prompts de "cambiar producto" (antes "cambiar calzado"), en UN solo lugar. |
| prompts.py | 118 | raíz | Ideas y sus prompts candidatos, esperando aprobación ANTES de gastar créditos |
| propuestas.py | 126 | raíz | Propuestas del decisor (Bloque 4): acciones que el motor recomienda pero que, |
| providers/__init__.py | 0 | providers | Fuente de providers |
| providers/apify.py | 338 | providers | Mecánica compartida de la API de Apify (arrancar una corrida, sondearla hasta |
| providers/aspect_ratio.py | 76 | providers | Detecta el aspect ratio real de la foto/video original que el usuario subió, |
| providers/comparador_modelos.py | 132 | providers | Candidatos de edición de imagen/video que SÍ ven la foto de referencia del |
| providers/fal_audio.py | 257 | providers | Proveedores de audio de Final Edition y de Audios en Crear, todos vía fal.ai (providers/fal_client.py): |
| providers/fal_client.py | 91 | providers | Helper genérico para llamar cualquier modelo de fal.ai (todos comparten el mismo |
| providers/flowplus_modelos.py | 488 | providers | Modelos de FlowPlus (referencias + texto -> video nuevo, o -> imagen nueva), |
| providers/image_provider.py | 33 | providers | Capa única de generación de imagen. El resto del programa nunca habla directo con |
| providers/kling_o1_client.py | 43 | providers | Cliente para Kling O1 Video Edit (Kuaishou) vía fal.ai — el único modelo que |
| providers/nano_banana_client.py | 185 | providers | Cliente simple para Nano Banana (Gemini 2.5 Flash Image) — generación de imagen a |
| providers/seedance_client.py | 58 | providers | Cliente simple para Seedance 2.0 (ByteDance) vía fal.ai — el partner internacional |
| providers/video_provider.py | 37 | providers | Capa única de generación de video — mismo patrón que image_provider.py. El resto |
| providers/wan3_client.py | 98 | providers | Cliente para Wan 3.0 (Alibaba) vía WaveSpeed AI — genera un video NUEVO guiado |
| providers/wavespeed_client.py | 67 | providers | Cliente para Wan 2.7 Video Edit (Alibaba) vía WaveSpeed AI — edita un video |
| providers/wavespeed_common.py | 225 | providers | Helpers compartidos por los clientes de WaveSpeed AI — autenticación y el poll |
| providers/wavespeed_imagen.py | 168 | providers | Edición de IMAGEN vía WaveSpeed AI, y mejora de calidad como segunda pasada. |
| providers/wavespeed_video_edit.py | 84 | providers | Los editores de video "pesados" (premium) de WaveSpeed AI — todos toman un |
| proyectos.py | 287 | raíz | Nombre visible de un proyecto, separado de su identificador. |
| publicador.py | 96 | raíz | Publica un video ya aprobado en las plataformas que indique su brief. |
| reconstruir_historial.py | 126 | raíz | Reconstruye en swaps.json las generaciones que la bitácora prueba que ocurrieron |
| referencias_flowplus.py | 76 | raíz | Bandeja de referencias de FlowPlus, por cliente: lo que la persona va agregando |
| referencias_link.py | 206 | raíz | Referencias desde un link (FlowPlus): TrendTrack, TikTok, Instagram, YouTube… |
| referentes/__init__.py | 0 | referentes | Fuente de referentes |
| referentes/clasificar.py | 229 | referentes | Clasificación de un referente con Claude (visión) — spec 2026-09-23 §5. Una |
| referentes/copycoders.py | 226 | referentes | Importación del swipe file de copycoders (spec 2026-09-23 §2.1 y §7). La |
| referentes/datos.py | 599 | referentes | Biblioteca de referentes (spec 2026-09-23): anuncios reales clasificados por |
| referentes/fuentes/__init__.py | 47 | referentes | Registro de fuentes de barrido por `tipo`, con carga perezosa (como |
| referentes/fuentes/apify_actores.py | 56 | referentes | El actor de Apify que usa `apify_adlibrary.py` para la biblioteca de |
| referentes/fuentes/apify_adlibrary.py | 281 | referentes | Conector de barrido Apify para la biblioteca de referentes (spec bloque 5, |
| referentes/fuentes/atria.py | 244 | referentes | Conector de barrido Atria (spec 2026-09-23 §2.2, §4.1): Ad Library de Meta |
| referentes/fuentes/base.py | 47 | referentes | Contrato común de las fuentes de barrido (spec 2026-09-23 §4). Un módulo por |
| referentes/fuentes/trendtrack.py | 434 | referentes | Conector de barrido TrendTrack (trendtrack.io) para la biblioteca de referentes: |
| referentes/imagenes.py | 70 | referentes | Copia de la imagen de un referente a nuestro R2 (spec 2026-09-23 §6.2): la |
| referentes/lectura.py | 190 | referentes | Lectura de un referente para «Recrear con mi producto» fiel (spec |
| referentes/recrear.py | 486 | referentes | «Recrear con mi producto» (spec 2026-09-23 §9): un referente de la biblioteca |
| referentes/rutas.py | 641 | referentes | Blueprint de la pestaña Referentes (spec 2026-09-23 §8). Bloque 1: fragmentos |
| referentes/sugerir.py | 298 | referentes | Sugerencias de referentes de la biblioteca para una campaña de Sprints (spec |
| referentes/traducir.py | 68 | referentes | Barridos por palabra: SIEMPRE en inglés (2026-09-27, pedido del usuario). |
| registro_app.py | 232 | raíz | Registro (log) de la app en archivos que el administrador lee en |
| rendimiento/__init__.py | 0 | rendimiento | Fuente de rendimiento |
| rendimiento/auditar_indices.py | 124 | rendimiento | Plugin de pytest que audita los índices: corre `EXPLAIN QUERY PLAN` sobre cada |
| rendimiento/locustfile.py | 99 | rendimiento | Prueba de carga con Locust (spec 2026-10-01-escala-y-monitoreo §7): N personas |
| rendimiento/sembrar.py | 288 | rendimiento | Datos de carga para medir la plataforma con volumen realista, sin gastar nada |
| resultados.py | 1158 | raíz | Centro de resultados de Experimentos (spec 2026-10-02-experimentos-centro-de-resultados §4). |
| revisar.py | 85 | raíz | Revisa los videos pendientes (generados por run_batch.py) uno por uno. Abre cada |
| run_batch.py | 195 | raíz | Genera en lote los videos definidos en un archivo de briefs (JSON) usando la API de |
| saldo.py | 135 | raíz | Proveedor sin saldo (incidente 2026-09-30): la cuenta de WaveSpeed de Creatv se |
| sembrar_edicion_demo.py | 142 | raíz | Edición de demostración para probar la vista previa del editor (capa 3) |
| sprints/__init__.py | 3 | sprints | Sprints de contenido: planificación (persona × producto × temporada), |
| sprints/analisis.py | 149 | sprints | Análisis de una referencia con Claude (visión), persistido en |
| sprints/archivos.py | 60 | sprints | Referencias subidas a una campaña: se guardan en |
| sprints/calendario.py | 115 | sprints | Calendario comercial por país: fechas de temporadas que un proyecto adopta con |
| sprints/datos.py | 1148 | sprints | Datos de los sprints de contenido (Parte 1 del spec): personas, temporadas, |
| sprints/entrega.py | 78 | sprints | Entrega del sprint (spec §2.6): enlaces de las piezas aprobadas y un zip con |
| sprints/estado.py | 74 | sprints | Estados de campaña y sprint (spec §1.3). Se guardan en la base, pero se |
| sprints/ideas.py | 564 | sprints | Ideas por campaña (spec §2.1): el prompt maestro combina persona, producto, |
| sprints/produccion.py | 453 | sprints | Producción por lotes (spec §2.2): de cada idea aprobada a una sesión de Crear |
| sprints/progreso.py | 68 | sprints | Progreso de campañas y sprints (spec §1.4). Funciones puras sobre los dicts |
| sprints/qa.py | 254 | sprints | Control de calidad automático de una pieza generada (spec §2.4): Claude con |
| sprints/revision.py | 131 | sprints | Bandeja de revisión y cierre del sprint (spec §2.5, §2.6). Aprobar y rechazar |
| sprints/rutas.py | 1583 | sprints | Rutas de la pestaña Sprints (Blueprint `sprints`, prefijo |
| sprints/sugerencias.py | 84 | sprints | Personas (arquetipos de cliente) sugeridas por Claude a partir de la guía de |
| sprints/tablero.py | 129 | sprints | El tablero de un sprint (spec docs/superpowers/specs/2026-09-26-sprints-tablero-design.md): |
| static/angulo.js | 162 | static | Fuente de static |
| static/editor/audio.js | 99 | static | Fuente de static |
| static/editor/avisos_carga.js | 145 | static | Fuente de static |
| static/editor/avisos_editor.js | 71 | static | Fuente de static |
| static/editor/biblioteca.js | 1597 | static | Fuente de static |
| static/editor/encuadre.js | 199 | static | Fuente de static |
| static/editor/escala.js | 561 | static | Fuente de static |
| static/editor/formatos.js | 4 | static | Fuente de static |
| static/editor/geometria.js | 63 | static | Fuente de static |
| static/editor/guardado.js | 108 | static | Fuente de static |
| static/editor/historial.js | 67 | static | Fuente de static |
| static/editor/lienzo.js | 204 | static | Fuente de static |
| static/editor/lienzo_interaccion.js | 271 | static | Fuente de static |
| static/editor/linea_tiempo.js | 520 | static | Fuente de static |
| static/editor/motor_audio.js | 143 | static | Fuente de static |
| static/editor/numeros.js | 10 | static | Fuente de static |
| static/editor/operaciones.js | 1525 | static | Fuente de static |
| static/editor/pagina_editor.js | 759 | static | Fuente de static |
| static/editor/pendientes.js | 27 | static | Fuente de static |
| static/editor/precio.js | 43 | static | Fuente de static |
| static/editor/producir.js | 34 | static | Fuente de static |
| static/editor/propiedades.js | 924 | static | Fuente de static |
| static/editor/propiedades_modelo.js | 647 | static | Fuente de static |
| static/editor/reloj.js | 43 | static | Fuente de static |
| static/editor/resolver.js | 93 | static | Fuente de static |
| static/editor/seleccion.js | 267 | static | Fuente de static |
| static/editor/stickers_modelo.js | 101 | static | Fuente de static |
| static/editor/subtitulos.js | 143 | static | Fuente de static |
| static/editor/subtitulos_fuente.js | 187 | static | Fuente de static |
| static/editor/subtitulos_modelo.js | 393 | static | Fuente de static |
| static/editor/subtitulos_panel.js | 895 | static | Fuente de static |
| static/editor/texto.js | 73 | static | Fuente de static |
| static/editor/texto_canvas.js | 292 | static | Fuente de static |
| static/editor/textos.js | 496 | static | Fuente de static |
| static/editor/tiempo.js | 186 | static | Fuente de static |
| static/editor/tipografia.js | 327 | static | Fuente de static |
| static/editor/videos.js | 145 | static | Fuente de static |
| static/editor/vinculos.js | 279 | static | Fuente de static |
| static/editor/vista.js | 702 | static | Fuente de static |
| static/editor/voz_modelo.js | 246 | static | Fuente de static |
| static/editor/voz_panel.js | 1112 | static | Fuente de static |
| static/editor/zonas.js | 330 | static | Fuente de static |
| static/estilos/base.css | 9 | static | Fuente de static |
| static/estilos/legado/01-sistema-de-diseno.css | 971 | static | Fuente de static |
| static/estilos/legado/02-barra-lateral-dentro-de-un-proyecto.css | 919 | static | Fuente de static |
| static/estilos/legado/03-base-visual-comun-2026-09-25-spec.css | 96 | static | Fuente de static |
| static/estilos/legado/04-crear-flow-plus-corregir-prompts-con-cla.css | 226 | static | Fuente de static |
| static/estilos/legado/05-tablero-de-sprints-2026-09-26-spec.css | 136 | static | Fuente de static |
| static/estilos/legado/06-crear-compositor-2026-09-27-spec.css | 217 | static | Fuente de static |
| static/estilos/legado/07-celular-revision-de-pantallas-2026-09-28.css | 110 | static | Fuente de static |
| static/estilos/legado/08-crear-audios-crear-audios-html-spec-2026.css | 112 | static | Fuente de static |
| static/estilos/legado/09-catalogo-galeria-y-ficha-spec-2026-09-28.css | 107 | static | Fuente de static |
| static/estilos/legado/10-crear-anuncio-hablado-2026-10-01-crear-h.css | 67 | static | Fuente de static |
| static/estilos/legado/11-final-edition-tablero-2026-10-02-daniel.css | 183 | static | Fuente de static |
| static/estilos/legado/12-alertas-2026-10-02-spec-docs-superpowers.css | 61 | static | Fuente de static |
| static/estilos/pantallas/experimento-nuevo.css | 36 | static | Fuente de static |
| static/estilos/pantallas/experimentos.css | 463 | static | Fuente de static |
| static/estilos/pantallas/guia-estilos.css | 14 | static | Fuente de static |
| static/estilos/tokens.css | 101 | static | Fuente de static |
| static/exp_resultados.js | 486 | static | Fuente de static |
| static/hablado.js | 307 | static | Fuente de static |
| static/presupuesto_exp.js | 52 | static | Fuente de static |
| static/tablas.js | 47 | static | Fuente de static |
| storage/__init__.py | 0 | storage | Fuente de storage |
| storage/r2_cors.py | 70 | storage | CORS del bucket de R2 (spec editor §3, capa 3): la vista previa dibuja los |
| storage/r2_uploader.py | 125 | storage | Sube cada video generado a Cloudflare R2, para tener una copia propia y permanente |
| subir_personaje.py | 52 | raíz | Sube la imagen de referencia de un "personaje" que te mandó un cliente a tu storage |
| swaps.py | 63 | raíz | Estado del flujo "cambiar calzado": el usuario sube una foto, elige un producto del |
| tablero.py | 911 | raíz | Tablero (Bloque 6): agregaciones de solo lectura sobre los experimentos del |
| tareas/__init__.py | 57 | tareas | Registro de tipos de tarea que ejecuta el worker. Cada módulo de tareas/ se |
| tareas/audios.py | 108 | tareas | Audios en Crear (spec 2026-09-28 §4): sintetizar la voz con ElevenLabs vía |
| tareas/cadena.py | 246 | tareas | Worker de la cadena de escenas de Flow Plus (spec 2026-09-30, «Generar todas |
| tareas/director.py | 117 | tareas | Tarea del worker `flowplus_director` (spec director §4): compila el prompt por |
| tareas/doctrina.py | 85 | tareas | Tareas del worker de la doctrina de venta (bloques 2 y 3). |
| tareas/edicion.py | 542 | tareas | Tareas del worker para el editor (spec §2.4): |
| tareas/errores_voz.py | 33 | tareas | El error que dejan las tareas de voz (Audios, Mis voces y Anuncio hablado): |
| tareas/experimentos.py | 606 | tareas | Tareas del worker para Experimentos: lanzar (crea objetos en Meta, en pausa; |
| tareas/final_edition.py | 89 | tareas | Tareas del worker para Final Edition (su pestaña; hasta 2026-09-27 vivía en |
| tareas/flowplus.py | 737 | tareas | Tareas del worker para Crear (FlowPlus): generar el video o la imagen de una |
| tareas/hablado.py | 39 | tareas | Anuncio hablado en Crear (spec 2026-10-01 §3): «Escuchar la voz» paga la |
| tareas/investigacion.py | 451 | tareas | Tareas de la investigación automática del nicho (spec Parte 3 §1, §9) y el |
| tareas/mantenimiento.py | 143 | tareas | Tareas periódicas de mantenimiento (auditoría de rendimiento y |
| tareas/meta.py | 218 | tareas | Tareas del worker para Campañas: publicar un anuncio en Meta y refrescar sus |
| tareas/musica.py | 50 | tareas | Mi música (spec 2026-09-25): crear una canción con ElevenLabs vía fal y |
| tareas/nicho.py | 421 | tareas | Tareas del worker para Nicho (spec §8). |
| tareas/organico.py | 141 | tareas | Tarea del worker para la publicación orgánica (Bloque 7): publicar en las |
| tareas/referentes.py | 698 | tareas | Tareas del worker para la biblioteca de referentes (spec 2026-09-23 §7). |
| tareas/sprints.py | 448 | tareas | Tareas del worker para Sprints: analizar una referencia con Claude, sugerir |
| tareas/swap.py | 443 | tareas | Tarea del worker para Crear › Cambiar producto (swap): genera la foto o el |
| tareas/tiendas.py | 427 | tareas | Tareas del worker para tiendas conectadas (Bloque 5): sincronizar productos |
| tareas/triple_whale.py | 188 | tareas | Tareas del worker para Triple Whale (spec 2026-09-28 §4 y §6). |
| tareas/voces_propias.py | 46 | tareas | Voces propias de Audios (spec 2026-09-30 §3): crear una voz con MiniMax vía |
| templates/_angulo_editor.html | 67 | templates | Fuente de templates |
| templates/_anuncios_sueltos.html | 146 | templates | Fuente de templates |
| templates/_aprendizajes.html | 29 | templates | Fuente de templates |
| templates/_audios_lista.html | 33 | templates | Fuente de templates |
| templates/_audios_mis_voces.html | 22 | templates | Fuente de templates |
| templates/_avatar_ficha.html | 89 | templates | Fuente de templates |
| templates/_aviso_sin_saldo.html | 17 | templates | Fuente de templates |
| templates/_catalogo_campos_comerciales.html | 50 | templates | Fuente de templates |
| templates/_catalogo_ficha.html | 185 | templates | Fuente de templates |
| templates/_catalogo_grid.html | 28 | templates | Fuente de templates |
| templates/_catalogo_importar.html | 60 | templates | Fuente de templates |
| templates/_catalogo_tarjeta.html | 63 | templates | Fuente de templates |
| templates/_comparacion_modelos.html | 194 | templates | Fuente de templates |
| templates/_crear_audios.html | 546 | templates | Fuente de templates |
| templates/_crear_detalle.html | 122 | templates | Fuente de templates |
| templates/_crear_detalle_respuesta.html | 1 | templates | Fuente de templates |
| templates/_crear_flowplus.html | 1035 | templates | Fuente de templates |
| templates/_crear_flowplus_guiones.html | 275 | templates | Fuente de templates |
| templates/_crear_hablado.html | 36 | templates | Fuente de templates |
| templates/_crear_tarjetas.html | 81 | templates | Fuente de templates |
| templates/_crear_tarjetas_respuesta.html | 1 | templates | Fuente de templates |
| templates/_etiquetas_estado.html | 10 | templates | Fuente de templates |
| templates/_exp_gestionar.html | 221 | templates | Fuente de templates |
| templates/_exp_historial.html | 189 | templates | Fuente de templates |
| templates/_exp_macros.html | 97 | templates | Fuente de templates |
| templates/_exp_pieza.html | 128 | templates | Fuente de templates |
| templates/_exp_probar.html | 502 | templates | Fuente de templates |
| templates/_exp_resultados.html | 277 | templates | Fuente de templates |
| templates/_final_detalle.html | 252 | templates | Fuente de templates |
| templates/_final_detalle_respuesta.html | 1 | templates | Fuente de templates |
| templates/_final_macros.html | 34 | templates | Fuente de templates |
| templates/_final_tarjetas.html | 150 | templates | Fuente de templates |
| templates/_final_tarjetas_respuesta.html | 1 | templates | Fuente de templates |
| templates/_flowplus_bandeja.html | 27 | templates | Fuente de templates |
| templates/_form_reglas.html | 30 | templates | Fuente de templates |
| templates/_gpg_cadena.html | 75 | templates | Fuente de templates |
| templates/_gpg_clips.html | 86 | templates | Fuente de templates |
| templates/_gpg_escenas.html | 93 | templates | Fuente de templates |
| templates/_gpg_guion.html | 58 | templates | Fuente de templates |
| templates/_gpg_imagenes.html | 44 | templates | Fuente de templates |
| templates/_gpg_macros.html | 67 | templates | Fuente de templates |
| templates/_gpg_notion.html | 28 | templates | Fuente de templates |
| templates/_gpg_panel.html | 57 | templates | Fuente de templates |
| templates/_gpg_video.html | 85 | templates | Fuente de templates |
| templates/_hablado_macros.html | 10 | templates | Fuente de templates |
| templates/_hablado_panel.html | 80 | templates | Fuente de templates |
| templates/_idea_card.html | 37 | templates | Fuente de templates |
| templates/_idea_visual_card.html | 129 | templates | Fuente de templates |
| templates/_imagen_row.html | 46 | templates | Fuente de templates |
| templates/_llave_tarjeta.html | 36 | templates | Fuente de templates |
| templates/_maniqui.html | 56 | templates | Fuente de templates |
| templates/_meta_agencia_cliente.html | 72 | templates | Fuente de templates |
| templates/_meta_conectar.html | 104 | templates | Fuente de templates |
| templates/_meta_elegir_forma.html | 32 | templates | Fuente de templates |
| templates/_meta_propia_guia.html | 28 | templates | Fuente de templates |
| templates/_mi_musica.html | 41 | templates | Fuente de templates |
| templates/_nicho_avatares.html | 96 | templates | Fuente de templates |
| templates/_nicho_comentarios.html | 183 | templates | Fuente de templates |
| templates/_nicho_investigacion.html | 215 | templates | Fuente de templates |
| templates/_nicho_nav.html | 14 | templates | Fuente de templates |
| templates/_organico_publicar.html | 212 | templates | Fuente de templates |
| templates/_producto_doctrina.html | 55 | templates | Fuente de templates |
| templates/_progreso_row.html | 9 | templates | Fuente de templates |
| templates/_prompt_row.html | 38 | templates | Fuente de templates |
| templates/_referente_ficha.html | 32 | templates | Fuente de templates |
| templates/_referente_recrear.html | 123 | templates | Fuente de templates |
| templates/_referente_usar_en_sprint.html | 21 | templates | Fuente de templates |
| templates/_referentes_barridos.html | 59 | templates | Fuente de templates |
| templates/_referentes_grid.html | 31 | templates | Fuente de templates |
| templates/_referentes_traer.html | 157 | templates | Fuente de templates |
| templates/_revision_doctrina.html | 57 | templates | Fuente de templates |
| templates/_seccion_bitacora.html | 21 | templates | Fuente de templates |
| templates/_seccion_ideas.html | 80 | templates | Fuente de templates |
| templates/_seccion_marca.html | 109 | templates | Fuente de templates |
| templates/_seccion_personajes.html | 36 | templates | Fuente de templates |
| templates/_seccion_videos.html | 36 | templates | Fuente de templates |
| templates/_selector_productos.html | 69 | templates | Fuente de templates |
| templates/_selector_productos_nuevo.html | 75 | templates | Fuente de templates |
| templates/_sidebar.html | 99 | templates | Fuente de templates |
| templates/_sprint_lote_modal.html | 66 | templates | Fuente de templates |
| templates/_sprint_macros.html | 64 | templates | Fuente de templates |
| templates/_sprint_nav.html | 15 | templates | Fuente de templates |
| templates/_sprint_panel.html | 32 | templates | Fuente de templates |
| templates/_sprint_panel_armar.html | 167 | templates | Fuente de templates |
| templates/_sprint_panel_ideas.html | 100 | templates | Fuente de templates |
| templates/_sprint_panel_piezas.html | 74 | templates | Fuente de templates |
| templates/_sprint_qa.html | 20 | templates | Fuente de templates |
| templates/_sprint_sugeridos.html | 18 | templates | Fuente de templates |
| templates/_sprint_tarjeta.html | 21 | templates | Fuente de templates |
| templates/_tab_alertas.html | 93 | templates | Fuente de templates |
| templates/_tab_cambiar_calzado.html | 213 | templates | Fuente de templates |
| templates/_tab_catalogo.html | 530 | templates | Fuente de templates |
| templates/_tab_creativeflowplus.html | 1112 | templates | Fuente de templates |
| templates/_tab_experimentos.html | 30 | templates | Fuente de templates |
| templates/_tab_final.html | 305 | templates | Fuente de templates |
| templates/_tab_flowplus.html | 96 | templates | Fuente de templates |
| templates/_tab_nicho.html | 79 | templates | Fuente de templates |
| templates/_tab_referentes.html | 512 | templates | Fuente de templates |
| templates/_tab_settings.html | 760 | templates | Fuente de templates |
| templates/_tab_sprints.html | 68 | templates | Fuente de templates |
| templates/_tab_triple_whale.html | 94 | templates | Fuente de templates |
| templates/_triple_whale_conectar.html | 74 | templates | Fuente de templates |
| templates/_tw_panel.html | 366 | templates | Fuente de templates |
| templates/_video_card.html | 39 | templates | Fuente de templates |
| templates/_voces_galeria.html | 34 | templates | Fuente de templates |
| templates/admin_estilos.html | 102 | templates | Fuente de templates |
| templates/admin_meta.html | 250 | templates | Fuente de templates |
| templates/admin_referentes.html | 203 | templates | Fuente de templates |
| templates/admin_registros.html | 65 | templates | Fuente de templates |
| templates/admin_salud.html | 278 | templates | Fuente de templates |
| templates/base.html | 488 | templates | Fuente de templates |
| templates/campana_referencias.html | 224 | templates | Fuente de templates |
| templates/cliente.html | 192 | templates | Fuente de templates |
| templates/doctrina.html | 24 | templates | Fuente de templates |
| templates/editor.html | 798 | templates | Fuente de templates |
| templates/exp_nuevo.html | 33 | templates | Fuente de templates |
| templates/index.html | 84 | templates | Fuente de templates |
| templates/landing_cliente.html | 35 | templates | Fuente de templates |
| templates/legal.html | 14 | templates | Fuente de templates |
| templates/login.html | 22 | templates | Fuente de templates |
| templates/meta_elegir.html | 43 | templates | Fuente de templates |
| templates/nicho_avatares_proyecto.html | 45 | templates | Fuente de templates |
| templates/nicho_estudio.html | 55 | templates | Fuente de templates |
| templates/panel.html | 315 | templates | Fuente de templates |
| templates/recuperar.html | 17 | templates | Fuente de templates |
| templates/restablecer.html | 25 | templates | Fuente de templates |
| templates/sprint_detalle.html | 896 | templates | Fuente de templates |
| templates/sprint_entrega.html | 50 | templates | Fuente de templates |
| templates/sprint_revision.html | 184 | templates | Fuente de templates |
| tests/conftest.py | 114 | tests | base_temporal, sembrar_usuarios, usuarios_tmp, _sin_cache_meta, idioma_de_tests, _jpg_valido |
| tests/fixtures/copycoders_swipe.html | 8 | tests | Fuente de tests |
| tests/fixtures/generar_casos_editor.py | 501 | tests | Tablas de paridad Python↔navegador del editor (capa 3). Python es la |
| tests/fixtures/producto_og.html | 34 | tests | Fuente de tests |
| tests/fixtures_guiones.py | 80 | tests | Datos de prueba del pipeline de Flow Plus (sin red, sin Claude). |
| tests/i18n_util.py | 128 | tests | Detección de español en HTML (spec 2026-09-26 §Pruebas). Heurística: acentos, |
| tests/test_acciones.py | 675 | tests | ent, test_pedir_respeta_modo, test_pedir_con_tope_alcanzado_propone_aunque_sea_auto, test_ejecutar_derivar_rescatar_archivar_idempotentes, test_ejecutar_activar, test_ejecutar_activar_acepta_experimento_decidido |
| tests/test_admin.py | 226 | tests | Panel de administrador (admin.py): agrega, para TODOS los proyectos, el |
| tests/test_ads_db.py | 100 | tests | test_crear_y_cargar, test_actualizar_meta_ids_metricas_y_estado, test_error_y_eliminar, test_orden_y_aislamiento, test_metricas_historial, test_experimento_legado_unico_bajo_concurrencia |
| tests/test_alertas.py | 331 | tests | Núcleo de alertas.py (spec 2026-09-20-alertas-design.md §3 y §12): el |
| tests/test_alertas_fuentes.py | 1396 | tests | Fuentes de alertas.py, «puesta a punto» y «faltantes» (spec 2026-09-20-alertas-design.md |
| tests/test_apify_lote.py | 200 | tests | providers.apify.correr_lote: varias corridas a la vez, dataset leído en cualquier estado terminal, sin red. |
| tests/test_atribucion.py | 349 | tests | Atribución por tienda (atribucion.py): pedidos con utm → experimento_pieza, |
| tests/test_audios.py | 354 | tests | Audios en Crear (spec 2026-09-28): audios.py, el precio y el tipo de gasto. |
| tests/test_audios_mezcla_real.py | 45 | tests | Audios en Crear (spec 2026-09-28 §2): la mezcla de verdad con ffmpeg. |
| tests/test_audios_voz_cruda.py | 67 | tests | audios.voz_cruda (spec anuncio hablado §3): la voz cruda que comparten |
| tests/test_bandeja_lo_que_ves.py | 76 | tests | La bandeja de referencias es del proyecto (la comparten todas las personas |
| tests/test_base_visual.py | 123 | tests | Base visual común (spec 2026-09-25): marcado de la página del proyecto y |
| tests/test_biblioteca_editor.py | 584 | tests | Biblioteca del editor (capa 4b, Task 1): subir un archivo del proyecto a |
| tests/test_catalogo_archivar.py | 268 | tests | «Archivar» un producto entero desde su ficha (pedido de Daniel, 2026-10-01, |
| tests/test_catalogo_buscar.py | 9 | tests | test_encontrar_por_id_o_nombre |
| tests/test_catalogo_colores.py | 283 | tests | Catálogo por colores (spec 2026-09-28): un producto con `variantes` en |
| tests/test_catalogo_consumidores.py | 75 | tests | Quien busca la fila `producto` por un id de activo debe aceptar el id de un |
| tests/test_catalogo_vista.py | 72 | tests | catalogo_vista: puro (spec 2026-09-28 §10.2). |
| tests/test_cifrado.py | 35 | tests | test_cifra_y_descifra, test_sin_clave, test_clave_distinta_no_descifra, test_token_corrupto_o_no_ascii |
| tests/test_cola.py | 209 | tests | test_encolar_y_reclamar, test_encolar_dedupe_por_job_id, test_fallar_reintenta_con_espera_exponencial, test_fallar_agota_intentos, test_recuperar_colgadas, test_recuperar_colgadas_respeta_max_intentos |
| tests/test_cola_vacia.py | 43 | tests | deploy/cola_vacia.py dice «no reiniciar» mientras haya algo vivo en la cola. |
| tests/test_comparador_modelos.py | 87 | tests | providers/comparador_modelos.py: editar_imagen/editar_video para los 4 |
| tests/test_comparar_seedance_turbo.py | 162 | tests | comparar_seedance_turbo.py: regenerar con el acceso Turbo de WaveSpeed una |
| tests/test_conector_shopify_publico.py | 345 | tests | Conector `shopify_publico` (spec 2026-09-28 §6): catálogo público de una |
| tests/test_conectores_archivo_url.py | 470 | tests | Conectores de catálogo sin API: contrato normalizado, CSV/Excel y URL. |
| tests/test_conectores_tiendas.py | 858 | tests | Conectores con API: Shopify (GraphQL), WooCommerce (REST) y MercadoLibre |
| tests/test_configuracion_apartados.py | 52 | tests | Parte 3a de la mejora visual (spec 2026-09-26): Configuración en apartados |
| tests/test_cortes_ultimo_fotograma.py | 25 | tests | cortes.ultimo_fotograma: el último cuadro de un video (cadena de escenas de Flow Plus). |
| tests/test_crear_arreglos_2026_09_28.py | 90 | tests | Dos arreglos de Crear (2026-09-28): el botón «Rearmar con IA» ya no vive |
| tests/test_crear_compositor.py | 95 | tests | Crear como compositor (spec docs/superpowers/specs/2026-09-27-crear-compositor-design.md): |
| tests/test_crear_consejos_prompt.py | 25 | tests | Consejos para escribir el prompt en Crear (2026-09-27): el texto va tal cual |
| tests/test_crear_hablado_ui.py | 173 | tests | Crear › Anuncio hablado en la página (spec 2026-10-01 §1): el quinto modo, |
| tests/test_crear_mejorar_prompt.py | 105 | tests | «Que Wan mejore mi prompt» (Daniel, 2026-09-28): la casilla opcional que |
| tests/test_crear_prompt_tal_cual.py | 122 | tests | Incidente 2026-09-26: la generación directa de Crear manda el texto de la |
| tests/test_crear_sin_cola.py | 331 | tests | Crear sin videos perdidos (spec 2026-09-28-crear-sin-cola): un video cuya |
| tests/test_crear_solo_texto.py | 199 | tests | Crear sin referencias ni producto (2026-09-25): en el mismo formulario las |
| tests/test_creative_flow_db.py | 267 | tests | test_crear_actualizar_cargar_eliminar, test_cargar_ordena_por_creado_y_aisla_clientes, test_guardar_dict_completo, test_campos_extra_redondean, test_actualizar_y_eliminar_ignoran_piezas_final, test_crear_con_legado_id_y_creado_en |
| tests/test_cuentas.py | 496 | tests | Task 1 de cuentas con correo verificado: usuarios con correo, tokens de |
| tests/test_cuentas_idioma.py | 32 | tests | Correos de la cuenta (spec 2026-09-26 §B8): salen en el idioma de la persona |
| tests/test_db.py | 46 | tests | test_crea_todas_las_tablas, test_wal_activado, test_conectar_hace_commit, test_asegurar_carpeta_crea_el_directorio, test_asegurar_carpeta_ignora_memory |
| tests/test_decisor.py | 174 | tests | snap, test_reglas_efectivas_capas_y_tipos, test_sin_evidencia_queda_pendiente, test_evidencia_por_ventana_de_horas_aunque_falten_impresiones, test_perdedor_por_ctr_y_rescate, test_imagen_no_cae_por_thruplay |
| tests/test_derivaciones.py | 809 | tests | Bloque 4 — derivaciones: re-ediciones y regeneraciones asíncronas que |
| tests/test_detalles_visuales.py | 35 | tests | Parte 4 de la mejora visual (2026-09-26): fotos que no cargan, miniaturas de |
| tests/test_director.py | 371 | tests | Director de prompts (spec 2026-09-18 §2): Claude escribe los planos, el |
| tests/test_director_idioma.py | 21 | tests | El director escribe los planos en el idioma del proyecto (spec §B4). |
| tests/test_doctrina.py | 444 | tests | Doctrina de venta (spec 2026-09-25): vocabulario, textos, ángulo y verificador de cifras. |
| tests/test_doctrina_aprendizajes.py | 80 | tests | Doctrina, bloque 4: aprendizajes por proyecto. |
| tests/test_doctrina_diagnostico.py | 154 | tests | Doctrina, bloque 4: el diagnóstico de una pieza perdedora. |
| tests/test_doctrina_idioma.py | 86 | tests | Doctrina, bloque 3: la revisión de la pieza, los pedidos al cliente y los |
| tests/test_doctrina_pagina.py | 72 | tests | Página «Cómo escribe Creatv» (doctrina, bloque 2, §6). |
| tests/test_doctrina_pedidos.py | 91 | tests | «Lo que Claude necesita» (doctrina, bloque 2, §5.2–5.3). |
| tests/test_doctrina_producto.py | 60 | tests | Pruebas del producto (doctrina, bloque 2, §5). |
| tests/test_doctrina_revisor.py | 473 | tests | Doctrina, bloque 3: el revisor de la pieza terminada. |
| tests/test_documento.py | 764 | tests | cargar, test_valida_el_fixture_basico_y_deriva_duracion, test_imagen_sin_clips_de_tiempo_dura_cero, test_rechaza_formato_desconocido, _con_pistas, test_el_limite_de_pistas_es_veinte |
| tests/test_edicion_clon.py | 83 | tests | «Editar este video»: el documento que sale del clon crudo y la edición |
| tests/test_edicion_clon_varios.py | 22 | tests | edicion_clon.documento_varios: varias escenas en orden (cadena de escenas de Flow Plus). |
| tests/test_ediciones.py | 194 | tests | _doc, test_crear_y_cargar_valida_y_normaliza, test_crear_sin_nombre_lo_guarda_en_el_idioma_del_proyecto, test_crear_rechaza_documento_invalido, test_guardar_cas_dos_escrituras_una_pierde, test_guardar_marca_uso_de_materiales |
| tests/test_editor_js.py | 237 | tests | Pruebas de los módulos del editor en el navegador (static/editor/*.js). |
| tests/test_encuadre.py | 128 | tests | Geometría del encuadre (editor, capa 5b, D4-D6): `caja` (una fórmula para |
| tests/test_escala.py | 338 | tests | Escala (spec docs/superpowers/specs/2026-10-01-escala-y-monitoreo-design.md): |
| tests/test_estilos.py | 103 | tests | La hoja de estilos comparte etiquetas entre la barra superior de la página |
| tests/test_estilos_guia.py | 31 | tests | Guía de estilos (spec 2026-10-02-sistema-de-estilos §8): solo para el admin, con cada token y su contraste. |
| tests/test_estilos_sistema.py | 225 | tests | Sistema de estilos (spec docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md): |
| tests/test_estimar.py | 33 | tests | _doc, test_estimado_crece_con_duracion_capas_y_transiciones, test_mas_nucleos_reduce_casi_proporcional, test_texto_humano |
| tests/test_experimentos_db.py | 368 | tests | _pieza, _pieza_imagen, test_crear_y_cargar_experimento, test_cargar_excluye_legado, test_agregar_quitar_piezas_y_unicidad, test_agregar_pieza_rechaza_cruce_de_cliente |
| tests/test_fal_audio.py | 204 | tests | _capturar, test_tts_payload_y_costo, test_tts_timeout_personalizado_se_reenvia, test_tts_texto_vacio_lanza_value_error, test_transcribir_palabras, test_musica |
| tests/test_fe_borrador.py | 179 | tests | Borrador automático (puro): guion + cortes + materiales → documento del |
| tests/test_fe_cortes.py | 163 | tests | clips, test_ffprobe_json_devuelve_streams_y_format, test_duracion, test_ffmpeg_lanza_runtime_error_con_stderr, test_ffmpeg_respeta_variable_de_entorno, test_detectar_cortes_clip_con_corte_duro |
| tests/test_fe_guion.py | 730 | tests | _instalar_fake, _guion_valido, _sys, test_generar_con_correccion_con_errores_extra_pide_correccion_pero_no_bloquea_en_la_ultima_pasada, test_generar_con_correccion_sin_errores_extra_ni_bloqueantes_no_pide_correccion, test_generar_con_correccion_nunca_pierde_lo_pagado_si_la_correccion_rompe_el_guion |
| tests/test_fe_humo_capa2.py | 115 | tests | Prueba de humo de la capa 2 (slow): `final_edition.producir` de punta a |
| tests/test_fe_idioma.py | 49 | tests | Final edition, lo que arma Python (fase 6; decisión B de 2026-09-28: las |
| tests/test_fe_insumos.py | 189 | tests | Insumos del borrador: cada archivo del pipeline como material con caché. |
| tests/test_fe_mezcla.py | 130 | tests | Mezcla de audio (spec estudio S1/S2): presets, filtro compartido por el |
| tests/test_fe_musica.py | 113 | tests | proveedores_falsos, test_primera_llamada_genera_y_cachea, test_segunda_llamada_usa_cache_local, test_manifest_sin_archivo_local_descarga_de_nuevo, test_estilo_desconocido_lanza_error, test_on_progreso_se_pasa |
| tests/test_fe_musica_propia.py | 52 | tests | Canción de Mi música lista para mezclar: tramo desde inicio_s, en caché. |
| tests/test_fe_produccion.py | 865 | tests | Producción por la vía del editor (`final_edition/produccion.py`) con los |
| tests/test_fe_producir.py | 840 | tests | Orquestador de Final Edition (`final_edition.producir` / `preparar_guion`) |
| tests/test_fe_sonido.py | 42 | tests | test_sugerir_descripcion_arma_el_prompt_y_limpia_la_respuesta, test_sugerir_descripcion_recorta, test_sugerir_descripcion_manda_la_orden_de_idioma_al_principio_y_al_final, _llamar, _llamar |
| tests/test_fe_texto_render.py | 394 | tests | _png_recortado, _sin_solapes, logo, overlays, test_hook_png_recortado_en_tercio_superior, test_subtitulos_uno_por_palabra_con_ventanas_extendidas |
| tests/test_fe_tipos.py | 44 | tests | test_paises_tienen_idioma_y_moneda, test_formatear_precio, _guion, test_validar_guion_ok, test_validar_guion_errores, test_fuentes_existen |
| tests/test_fe_voz.py | 221 | tests | mp3_3s, _guion, proveedores_falsos, test_sintetizar_cinco_pistas_y_mezcla, test_palabras_desplazadas_por_bloque, test_bloque_que_no_cabe_ni_acelerado_se_marca_recortado |
| tests/test_final_tablero.py | 125 | tests | Tablero de Final edition (pedido de Daniel, 2026-10-02): la pestaña ya no |
| tests/test_flowplus_kling_cadena.py | 56 | tests | Kling O3 Pro imagen a video + elementos (cadena de escenas de Flow Plus, Etapa 0 verificada en WaveSpeed). |
| tests/test_flowplus_lanzar.py | 28 | tests | test_job_id_y_lanzar_encolan_con_prioridad, test_dashboard_delega_en_flowplus_lanzar |
| tests/test_flowplus_modelos_formatos.py | 106 | tests | Duraciones y formatos por modelo (Crear hasta 30 s; formatos verificados en |
| tests/test_flowplus_modelos_hablado.py | 63 | tests | Anuncio hablado (spec 2026-10-01 §2): registro HABLADO aparte de VIDEO, |
| tests/test_flowplus_modelos_sonido.py | 70 | tests | Sonido de la escena (spec estudio S1): los tres modelos de video piden el |
| tests/test_flowplus_prompt_contexto.py | 32 | tests | test_sin_contexto_el_prompt_es_identico, test_contexto_agrega_audiencia_y_temporada_al_principio, test_contexto_parcial_no_rompe |
| tests/test_flowplus_prompt_idioma.py | 53 | tests | flowplus_prompt en inglés (spec 2026-09-26 §B5): un proyecto en inglés |
| tests/test_flowplus_prompt_sin_solo_producto.py | 41 | tests | 2026-09-28: la persona pidió quitar el «solo producto, sin nadie» del prompt |
| tests/test_flowplus_prompt_sonido.py | 38 | tests | Línea SONIDO del prompt (spec estudio S1): describe el sonido de la escena |
| tests/test_flowplus_prompt_tokens.py | 182 | tests | Tokens de referencia (spec director §5): los modelos documentan `Image N` / |
| tests/test_flowplus_referencias_de_mas.py | 46 | tests | Incidente 2026-09-28 («mira lo que sacó»): Seedance 2.5 recibe UNA imagen de |
| tests/test_flowplus_wan_videos_ref.py | 67 | tests | Wan 3.0 con videos de referencia (incidente 2026-09-30 en Forja: un video de |
| tests/test_fotos.py | 128 | tests | `final_edition.fotos.preparar` (editor capa 5b, D2): la copia de una foto |
| tests/test_fuentes.py | 324 | tests | La tabla tipográfica de las fuentes del editor (capa 5c, D4): se lee de las |
| tests/test_gastos.py | 410 | tests | test_migracion_0010_sube_y_baja, test_registrar_es_idempotente_por_referencia, test_registrar_none_y_negativo_guardan_cero_y_tipo_desconocido_es_otro, test_resumen_mes_por_tipo_ignora_otro_mes, test_total_y_por_mes_desde_el_inicio, test_historial_mas_nuevo_primero_con_limite_y_desde |
| tests/test_gastos_historico.py | 99 | tests | Relleno único de la tabla `gasto` con los cobros anteriores a su existencia |
| tests/test_generador_idioma.py | 83 | tests | Lo que Claude escribe desde Catálogo, orgánico y la guía de marca sale en |
| tests/test_geometria.py | 45 | tests | _casos, test_caja_coincide_con_la_tabla_compartida, test_casos_expuestos_para_js, test_interpolar_sin_keyframes_devuelve_base, test_interpolar_lineal_entre_dos_keyframes, test_interpolar_fuera_del_rango_se_clava_en_los_extremos |
| tests/test_guia_agentes.py | 82 | tests | La guía para agentes sigue corta, con una skill por área, y un solo contrato. |
| tests/test_guiones_armar.py | 92 | tests | Armar clips de punta a punta con Claude falso: prompts al chat, rearmar, versiones. |
| tests/test_guiones_cadena.py | 141 | tests | Cadena de escenas de Flow Plus (spec 2026-09-30): lógica pura, sin base ni red. |
| tests/test_guiones_claude.py | 146 | tests | guiones/claude.py: parseo del JSON y gasto registrado siempre que se pagó. |
| tests/test_guiones_clips.py | 118 | tests | Validaciones V1-V6 y E1-E4 del plan de clips, con el plan de ejemplo y sus variantes rotas. |
| tests/test_guiones_config.py | 87 | tests | Configuración de un video desde el formulario del panel. |
| tests/test_guiones_datos.py | 98 | tests | guiones/datos.py: lotes y guiones, aislamiento por proyecto y vencimiento. |
| tests/test_guiones_datos_video.py | 152 | tests | Versiones de video: creación, estados de trabajo, recorte y vencimiento. |
| tests/test_guiones_doctrina.py | 82 | tests | Doctrina, bloque 4 (§7): los sitios de Flow Plus reciben su rebanada de la |
| tests/test_guiones_documento.py | 32 | tests | Documento .md del spec del cliente §2.7 con el texto vigente del chat. |
| tests/test_guiones_duracion.py | 71 | tests | Fórmula de duración del spec del cliente §2.2-§2.3 (puro). |
| tests/test_guiones_escenas.py | 209 | tests | Imágenes de cada escena de Flow Plus (spec 2026-09-30): pura, sin base ni red. |
| tests/test_guiones_idioma.py | 400 | tests | Flow Plus (guiones) en el idioma del proyecto (spec 2026-09-26 §B4): el |
| tests/test_guiones_imagenes.py | 51 | tests | Imágenes de referencia: qué hace falta, cierres fijos, tabla imagen↔clip y checklist. |
| tests/test_guiones_imagenes_escribir.py | 91 | tests | Escribir los prompts de imágenes con Claude falso y pasarlos al chat. |
| tests/test_guiones_lectura.py | 85 | tests | Paso 1: numerar, literalidad, edición y el hilo leer_lote con Claude falso. |
| tests/test_guiones_notion.py | 130 | tests | Notion: id desde el link, texto desde bloques anidados y paginados, errores sin filtrar la llave. |
| tests/test_guiones_plantillas.py | 100 | tests | Plantillas: formato exacto del spec del cliente §2.4 y el invariante con refinador.validar. |
| tests/test_guiones_recorte.py | 49 | tests | Recorte: el orden de Claude se aplica sin tocar la línea 1 y se detiene al entrar. |
| tests/test_guiones_refinador.py | 581 | tests | guiones.refinador: reglas de `validar` (puro), datos aislados por cliente, |
| tests/test_hablado.py | 182 | tests | Anuncio hablado (spec 2026-10-01 §1, §3, §4): la voz con las reglas de |
| tests/test_hablado_apagados.py | 98 | tests | Lo que se apaga para un anuncio hablado en Crear y Final edition (spec |
| tests/test_hablado_experimentos.py | 74 | tests | Experimentos y un anuncio hablado (spec 2026-10-01 §6): como una imagen, no |
| tests/test_hilos_seguros.py | 155 | tests | Lo que el carril de Crear (varias generaciones a la vez en el worker, |
| tests/test_hooks_agentes.py | 398 | tests | Los hooks de .claude/hooks/ frenan lo que deben y dejan pasar el trabajo normal. |
| tests/test_i18n_app_entera.py | 57 | tests | Con los valores de producción (DEFECTO="en", ACTIVO_PARA_TODOS=True), una |
| tests/test_i18n_catalogo.py | 136 | tests | Catálogo de traducciones (spec 2026-09-26 §B1, §Pruebas): todo texto marcado |
| tests/test_i18n_claude.py | 116 | tests | Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4): ningún |
| tests/test_i18n_editor.py | 303 | tests | El editor (capas 3-4b) en el idioma de quien mira (spec 2026-09-26 §B1, |
| tests/test_i18n_fugas.py | 971 | tests | Pantallas en inglés sin español visible (spec 2026-09-26 §Pruebas). Render |
| tests/test_i18n_guardado.py | 363 | tests | Lo que se GUARDA (un error de una publicación o de un experimento, el |
| tests/test_i18n_mensajes.py | 197 | tests | Mensajes que arma Python para una persona (spec 2026-09-26 §B1, §B8): |
| tests/test_i18n_nueva_idea.py | 91 | tests | El flujo viejo «Nueva idea» (9 plantillas sin pantalla viva) en inglés y en |
| tests/test_i18n_plantillas.py | 155 | tests | Plantillas ya traducidas (spec 2026-09-26 §Pruebas): en su FUENTE no queda |
| tests/test_idioma_por_defecto.py | 104 | tests | Inglés por defecto para todos (decisión de Daniel, 2026-09-28; spec |
| tests/test_idiomas.py | 190 | tests | idiomas.py (spec 2026-09-26-idioma-y-modo-oscuro §B1-§B2): el único módulo |
| tests/test_importador.py | 666 | tests | importador.py: producto normalizado → fila `producto` → activo del catálogo |
| tests/test_importador_colores.py | 224 | tests | importador.vincular_activo con `extra.variantes` (spec 2026-09-28 §7): |
| tests/test_indices_escala.py | 126 | tests | Índices de la auditoría de consultas (migración 0026) y la tabla de errores |
| tests/test_lanzador.py | 1035 | tests | entorno, test_centavos_y_url, test_lanzar_crea_campana_conjuntos_y_anuncios, test_lanzar_con_imagen_usa_creative_de_imagen, test_lanzar_retoma_sin_duplicar, test_lanzar_exige_piezas_y_estado |
| tests/test_llaves.py | 104 | tests | llaves.py: la lista de servicios de Configuración › Puesta a punto y su |
| tests/test_lote2_ui.py | 65 | tests | Regresiones de lote 2: JavaScript renderizado, sin navegador ni red. |
| tests/test_lote3_seguridad.py | 90 | tests | test_redacta_formatos_de_error, test_tapa_lo_que_la_version_vieja_tapaba_y_mas, test_no_cruza_saltos_de_linea_ni_rompe_el_json_del_error, test_el_plazo_corre_desde_que_se_tiene_el_candado, test_carga_inicial_escalonada_y_con_prioridad_baja, tarda_en_dar_el_candado |
| tests/test_lote5_experimentos.py | 71 | tests | test_pnd134_ultima_metrica_en_una_consulta_sin_cambiar_valores, test_pnd137_bloqueo_cuenta_vivos_sin_cargar_piezas, contar, pesado |
| tests/test_lote5_gasto.py | 54 | tests | test_pnd144_pista_pagada_fallida_conserva_gasto_y_video, test_pnd145_registra_antes_de_persistir_error, falla, descarga, falla |
| tests/test_lote5_higiene.py | 47 | tests | test_pnd077_los_tres_caminos_comparten_verticales, test_pnd078_atribucion_lee_capacidad_del_conector, test_pnd079_estados_compartidos_sin_aprobar_errores, conector |
| tests/test_lote5b_director.py | 57 | tests | test_pnd072_aviso_redactado_sin_cambiar_prompt, test_pnd072_encolado_compartido_preserva_contrato, falla, encolar |
| tests/test_lote5b_resultados_js.py | 70 | tests | Comportamiento del código JS con DOM y fetch dobles, sin navegador ni red. |
| tests/test_mapa_codigo_generar.py | 42 | tests | El generador inspecciona código de ejemplo; estas pruebas no leen documentos. |
| tests/test_mapa_corporal_idioma.py | 42 | tests | Mapa corporal y reglas de categoría en el idioma del proyecto (spec |
| tests/test_materiales.py | 255 | tests | r2_falso, test_hash_clave_es_estable_y_distingue_partes, test_obtener_o_crear_solo_produce_una_vez, test_obtener_o_crear_sobrevive_insert_concurrente, test_subir_deduplica_por_contenido, test_materiales_de_otro_cliente_no_se_mezclan |
| tests/test_meta_ads_bloque3.py | 54 | tests | auth_falsa, test_campaign_spend_cap, test_adset_y_ad_actualizaciones, test_insights_thruplay_y_ventas, llamar |
| tests/test_meta_ads_insights.py | 45 | tests | meta_ads/insights.py::obtener_resultados. Regresión: un fallo al leer el |
| tests/test_meta_agencia.py | 796 | tests | Meta en modo agencia (meta_agencia.py + meta_conexion): la conexión del |
| tests/test_meta_app_cliente.py | 120 | tests | Cada proyecto trae SU propia app de Meta (id, secret, config de login): |
| tests/test_meta_detalle.py | 528 | tests | meta_detalle (spec 2026-10-02 §3): traducir filas de Meta, pedir con |
| tests/test_meta_errores.py | 114 | tests | Errores de Meta en palabras de persona (2026-09-28): la alerta del Tablero y la |
| tests/test_mi_musica.py | 107 | tests | Mi música (spec 2026-09-25): canciones propias como `material` de audio. |
| tests/test_migracion.py | 71 | tests | _cliente_con_json, test_migra_y_es_idempotente, test_cliente_sin_json, test_migra_estados_a_mitad_de_camino_como_error |
| tests/test_migracion_0012.py | 50 | tests | test_tablas_del_editor_existen_en_metadata, test_material_unico_por_cliente_y_hash, test_migracion_0012_sube_y_baja |
| tests/test_migracion_0025.py | 45 | tests | Migración 0025 (spec 2026-09-28 §8; nació como 0022 y se renumeró al |
| tests/test_migracion_0028.py | 52 | tests | Migración 0028 (spec 2026-10-02 §3.1): metrica_dia y metrica_desglose suben, |
| tests/test_migracion_0029.py | 50 | tests | Migración 0029 (Alertas, spec 2026-09-20-alertas-design.md §4 y §12): la |
| tests/test_migracion_0030.py | 46 | tests | PND-006: unicidad por proyecto con biblioteca global independiente. |
| tests/test_migracion_0031.py | 35 | tests | PND-040: conservar identidad y filas al habilitar AUTOINCREMENT. |
| tests/test_migracion_triple_whale.py | 54 | tests | Migraciones 0023 y 0024 (spec 2026-09-28): tablas de Triple Whale, `triple_whale.extra` y ventas por producto. |
| tests/test_miniaturas_productos.py | 62 | tests | Miniaturas de las fotos del catálogo (auditoría 2026-09-28): el selector de |
| tests/test_modo_oscuro.py | 147 | tests | Modo oscuro (spec docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md, |
| tests/test_modos_propuestas.py | 124 | tests | test_tabla_de_puertas, test_propuestas_dedupe_por_pieza_id, test_propuestas_crud, test_crear_hijo, test_crear_hijo_copia_producto_id, test_crear_hijo_profundidad_tope_restante_e_idempotente |
| tests/test_monitoreo.py | 337 | tests | Salud de la plataforma (spec 2026-10-01-escala-y-monitoreo §6): errores |
| tests/test_motor_compilador.py | 668 | tests | _doc, _esperado, test_filtergraph_del_fixture_basico_sin_ass, test_con_ass_agrega_un_solo_filtro_subtitles_y_el_texto, test_sin_subtitulos_en_el_idioma_no_hay_filtro, test_ventana_de_tramo_una_linea_que_cruza_la_union_sale_desde_cero_en_el_segundo |
| tests/test_motor_idioma.py | 172 | tests | El motor de ecommerce escribe en el idioma del proyecto (spec 2026-09-26 |
| tests/test_motor_render.py | 624 | tests | medios, _doc, _streams, test_renderiza_video_basico_con_audio_y_miniatura, test_con_libass_los_subtitulos_entran_por_ass, test_sin_libass_se_omiten_subtitulos_y_avisa |
| tests/test_motor_subtitulos.py | 304 | tests | test_tiempo_ass_formato_centesimas, test_ventanas_cierran_por_cantidad_y_por_hueco, test_ventanas_cierran_por_duracion_maxima, test_ventanas_cierra_antes_de_pasar_max_caracteres, test_ventanas_sin_max_caracteres_se_comporta_como_hoy, test_ventanas_palabra_larga_sola_siempre_entra |
| tests/test_motor_tramos.py | 288 | tests | _doc, _con_textos, test_capas_cuenta_textos_imagenes_superpuestos_no_subtitulos, test_un_tramo_si_cabe, test_parte_en_fronteras_de_clips_cuando_se_pasa, test_no_corta_dentro_de_una_transicion |
| tests/test_movil.py | 326 | tests | Celular (spec 2026-09-26): menú que abre la barra lateral encima de la página. |
| tests/test_musica_elevenlabs.py | 78 | tests | Canción a medida con ElevenLabs vía fal (spec 2026-09-25). |
| tests/test_nicho_apify.py | 442 | tests | _fixture, test_registro_de_actores_y_estimado, test_junglee_tiene_un_solo_precio, test_estimar_minimo_de_junglee_y_precios_reales, test_corridas_amazon_una_por_link_con_el_minimo_y_memoria, test_validar_links_y_entradas |
| tests/test_nicho_avatares.py | 412 | tests | _c, test_seleccionar_excluye_ordena_y_alterna_fuentes, test_estimar_costo_y_costo_real, test_estimado_de_salida_reproduce_la_medicion_real, test_parsear_nucleos, test_parsear_subs_y_verificar_evidencia |
| tests/test_nicho_avatares_proyecto.py | 93 | tests | Avatares del proyecto (spec 2026-09-29 §1): estudio oculto, avatares escritos a mano, personas sin avatar y la lista única. |
| tests/test_nicho_cadena.py | 189 | tests | La investigación de punta a punta con todo falso (spec Parte 3): consultas → buscar → seleccionar → |
| tests/test_nicho_cadena_mercados.py | 173 | tests | Nicho Parte 4 de punta a punta (spec 2026-09-30 §5): un estudio en Colombia con Mercado Libre (local), |
| tests/test_nicho_calidad.py | 49 | tests | Qué es un avatar completo y cómo se funde lo que completa Claude (spec 2026-09-29 §2). |
| tests/test_nicho_datos.py | 214 | tests | _c, test_estudio_crear_listar_editar_archivar, test_estudio_valida, test_comentarios_agregar_dedup_paginar_excluir_borrar, test_comentarios_valida_fuente_y_estudio, test_extra_y_recolecciones |
| tests/test_nicho_datos_investigacion.py | 82 | tests | datos de la Parte 3: país del estudio, producto_nicho (tabla de la migración 0016) y extra.investigacion. |
| tests/test_nicho_db.py | 33 | tests | test_migracion_0013_crea_las_tablas, test_crear_todo_incluye_las_tablas |
| tests/test_nicho_export.py | 67 | tests | test_valor_y_subs_exportables, test_markdown, test_excel, test_urls_comentarios |
| tests/test_nicho_fuentes.py | 131 | tests | test_limpiar_y_hash, test_normalizar_comentario, test_error_fuente_y_fuente_base, test_registro_por_tipo, test_partir_texto_modos, test_fuente_texto_recolecta_normalizado |
| tests/test_nicho_http.py | 83 | tests | sin_espera, test_pedir_devuelve_cualquier_codigo_sin_reintentar, test_pedir_429_espera_retry_after_y_luego_se_rinde, test_pedir_5xx_reintenta_una_vez_y_red_caida_dos, test_fuente_aviso_y_llaves, __init__ |
| tests/test_nicho_investigacion.py | 587 | tests | Pure tests for nicho/investigacion.py state machine. |
| tests/test_nicho_investigacion_completo.py | 609 | tests | Comprehensive test suite for Nicho Parte 3 (investigación de nicho). |
| tests/test_nicho_mas_tiendas.py | 297 | tests | Nicho Parte 4 (spec 2026-09-30): Walmart y AliExpress, otro mercado, búsquedas por idioma y reseñas marcadas, sin red. |
| tests/test_nicho_plataforma.py | 268 | tests | FuentePlataforma: buscar productos y traer reseñas sobre el registro de plataformas y correr_lote, sin red. |
| tests/test_nicho_plataformas.py | 329 | tests | Registro de plataformas (spec Parte 3 §3): países, precios, entradas y lectores puros, sin red. |
| tests/test_nicho_reddit.py | 204 | tests | _fixture, entorno, test_id_post_desde_link, test_normalizar_params, test_parsear_busqueda_y_comentarios, test_recolectar_busca_y_lee_con_token |
| tests/test_nicho_youtube.py | 284 | tests | _fixture, _http_error, entorno, test_id_video_desde_link, test_normalizar_params, test_parsers |
| tests/test_notificaciones.py | 183 | tests | smtp_falso, test_sin_smtp_host_devuelve_false_sin_enviar, test_sin_destinatario_devuelve_false, test_envia_con_starttls_login_y_send, test_sin_usuario_no_hace_login, test_excepcion_devuelve_false |
| tests/test_operaciones_editor.py | 178 | tests | Las operaciones de edición del navegador (static/editor/operaciones.js) |
| tests/test_organico.py | 1006 | tests | Bloque 7 — publicación orgánica: tabla publicacion, canales, redacción |
| tests/test_outcome_sales.py | 169 | tests | Bloque 6: OUTCOME_SALES con Pixel. Meta exige `promoted_object` (pixel + |
| tests/test_perf_pagina_proyecto.py | 171 | tests | Auditoría de rendimiento 2026-09-28: la página del proyecto hacía una |
| tests/test_pixel.py | 160 | tests | Chequeo del Pixel de Meta: meta_ads/pixel.listar_pixels (submódulo) y |
| tests/test_plantillas_anuncio.py | 85 | tests | Recetas de tomas del director (spec 2026-09-18 §9, Etapa 3): datos puros, |
| tests/test_precio_form.py | 12 | tests | PND-005: precios escritos con miles y decimales, sin red. |
| tests/test_presupuesto_experimentos.py | 213 | tests | El presupuesto de «Nuevo experimento» (spec 2026-10-02 §5.1–§5.3): total + días → diario por país, atajos, |
| tests/test_providers_apify.py | 200 | tests | test_cabeceras_lleva_el_token_como_bearer, test_frase_estado, test_probar_token_ok, test_probar_token_401, test_arrancar_ok, test_arrancar_401_lanza_error_fuente |
| tests/test_proyectos_concurrencia.py | 38 | tests | PND-042: escritores reales simultáneos, JSON aislado. |
| tests/test_proyectos_meta_forma.py | 39 | tests | Forma elegida por el cliente para conectar Meta (spec §1): vive en |
| tests/test_proyectos_sonido.py | 47 | tests | test_preferencias_sonido_defecto_y_guardado, test_preferencias_flowplus_traen_duracion_por_defecto_y_el_idioma_ya_no_vive_ahi, test_preferencias_flowplus_filtra_un_idioma_prompt_viejo_del_json |
| tests/test_r2_cors.py | 51 | tests | La regla CORS del bucket: solo lectura (GET/HEAD) desde la plataforma y |
| tests/test_rasterizar.py | 467 | tests | _estilo, test_hook_mide_su_caja_y_tiene_alfa, test_ancho_max_parte_en_lineas, test_fondo_pildora_y_tarjeta_de_ancho_fijo, test_fuente_rara_o_inexistente_falla_claro, test_color_con_alfa_y_opacidad |
| tests/test_referentes_bilingue.py | 258 | tests | Biblioteca global de referentes en dos idiomas (spec 2026-09-26 §B7): |
| tests/test_referentes_clasificar.py | 228 | tests | test_validar_familia_del_vocabulario, test_validar_familia_nueva_cuando_ninguna_encaja, test_validar_familia_fuera_del_vocabulario_se_toma_como_familia_nueva, test_validar_familia_fuera_del_vocabulario_conserva_la_descripcion_si_viene, test_validar_familia_con_otras_mayusculas_usa_la_existente, test_validar_nunca_duplica_el_prefijo_emerging |
| tests/test_referentes_copycoders.py | 170 | tests | referentes.copycoders: parseo del HTML del swipe file y normalización. |
| tests/test_referentes_copycoders_proyecto.py | 141 | tests | Incidente 2026-09-28: la página del proyecto se quedaba cargando. La |
| tests/test_referentes_datos.py | 460 | tests | referentes.datos: único escritor de referente / referente_familia / barrido. |
| tests/test_referentes_fuentes.py | 62 | tests | test_tipos_incluye_atria, test_por_tipo_atria_devuelve_el_modulo, test_por_tipo_desconocido_lanza_keyerror, test_llaves_faltantes_atria, test_apify_registrado, test_apify_llaves_faltantes |
| tests/test_referentes_fuentes_apify_actores.py | 23 | tests | test_actor_y_precio_verificados, test_estimar_calcula_usd_y_topa_resultados, test_estimar_topa_al_maximo, test_estimar_minimo_uno |
| tests/test_referentes_fuentes_apify_adlibrary.py | 292 | tests | test_estimar_delega_al_registro_de_actores, test_traer_sin_token_lanza_error_fuente, test_traer_modo_palabra_arma_la_url_de_ad_library, test_url_varias_palabras_es_frase_exacta_y_una_sola_palabra_no, test_traer_modo_marca_usa_view_all_page_id, test_traer_normaliza_el_item_real |
| tests/test_referentes_fuentes_atria.py | 219 | tests | test_estimar_calcula_llamadas_por_page_size, test_probar_ok, test_probar_401_lanza_error_fuente, test_pedir_envuelve_timeout_como_error_fuente, test_pedir_envuelve_error_de_conexion_como_error_fuente, test_traer_con_error_de_red_a_mitad_de_paginacion_no_pierde_lo_ya_traido |
| tests/test_referentes_fuentes_trendtrack.py | 270 | tests | Conector TrendTrack (referentes/fuentes/trendtrack.py). La API real nunca se |
| tests/test_referentes_idioma.py | 103 | tests | Referentes: «Sugerir con IA», «Adaptar con IA» y el prompt determinista de |
| tests/test_referentes_imagenes.py | 64 | tests | referentes.imagenes: descarga (costura _bajar), validación con Pillow y subida a R2 (monkeypatch). |
| tests/test_referentes_lectura.py | 147 | tests | referentes.lectura: lectura de la referencia para «Recrear» fiel (spec |
| tests/test_referentes_recrear.py | 514 | tests | referentes.recrear: prompt determinista, adaptación con Claude, subida de |
| tests/test_referentes_sugerir.py | 380 | tests | _con_copycoders, _cand, test_elegir_una_familia_distinta_por_sugerencia, test_elegir_minimo_uno_aunque_objetivo_sea_cero_o_negativo, test_elegir_lista_vacia, test_candidatos_filtra_clasificacion_y_excluidos |
| tests/test_registro_app.py | 94 | tests | registro_app (spec 2026-10-01-escala-y-monitoreo §6.3): el archivo de |
| tests/test_rendimiento_sembrar.py | 47 | tests | rendimiento/sembrar.py: los datos de la prueba de carga se siembran y se |
| tests/test_resultados.py | 1225 | tests | resultados.py (spec 2026-10-02 §4): todo lo que pinta el centro de resultados. |
| tests/test_revision_lote4_gasto.py | 75 | tests | test_sonda125_muerte_en_la_mezcla_pierde_la_pista, test_pnd125_interrumpir_recuperacion_registra_musica_una_vez, test_pnd125_video_se_anota_apenas_descargado, muere, interrumpir |
| tests/test_revision_lote4_rutas.py | 103 | tests | _txt, test_sonda_solo_trafico, test_sonda_pixel_sin_gasto_historial, test_pnd138_gestionar_moneda_ajena, test_pnd138_historial_meses_previos_comparables, test_pnd139_centro_e_historial_cambio_de_fuente |
| tests/test_revision_lote4_ventas.py | 92 | tests | test_sonda_un_experimento_cop_apaga_el_roas_de_todos_los_meses, test_sonda_tw_cae_a_meta_sin_compras_y_vuelve, test_sonda_centro_con_un_experimento_cop_cerrado, test_pnd139_respaldo_ciego_anterior_a_ventana, test_pnd139_cambio_de_fuente_no_es_cero |
| tests/test_rutas_alertas.py | 694 | tests | Pestaña Alertas en dashboard.py (spec docs/superpowers/specs/2026-09-20-alertas-design.md §5-§7 y §12): |
| tests/test_rutas_audios.py | 434 | tests | Rutas de Audios en Crear (spec 2026-09-28 §4): JSON con la lista ya pintada. |
| tests/test_rutas_bloque4.py | 376 | tests | Rutas del Bloque 4 en dashboard: modo, reglas, propuestas (aprobar / |
| tests/test_rutas_catalogo.py | 547 | tests | Rutas del catálogo por colores (spec 2026-09-28 §10–11): imágenes de |
| tests/test_rutas_configuracion.py | 611 | tests | Configuración = puesta a punto (Task 4): las tarjetas de servicios |
| tests/test_rutas_crear_director.py | 468 | tests | Rutas de Crear con el director (spec 2026-09-18 §7). |
| tests/test_rutas_crear_formatos.py | 111 | tests | Crear: una pieza por clic (sin versiones ni enfoque manual), duración hasta |
| tests/test_rutas_crear_plantillas.py | 113 | tests | Receta de tomas en Crear (Etapa 3 del director, spec 2026-09-18 §9): solo |
| tests/test_rutas_crear_recuperar.py | 59 | tests | «Recuperar el video» (incidente 2026-09-28): cuando WaveSpeed tardó más de |
| tests/test_rutas_crear_reusar.py | 85 | tests | «Editar y crear otra a partir de esta» sin variables quemadas (pedido de |
| tests/test_rutas_crear_sonido.py | 166 | tests | La pestaña Crear muestra la tarifa con sonido y el indicador 🔊/🔇 de cada |
| tests/test_rutas_crear_videos_ref.py | 161 | tests | Rutas de Crear tras el incidente 2026-09-30. |
| tests/test_rutas_cuentas.py | 666 | tests | Task 2 de cuentas con correo verificado: las rutas y pantallas. Registro |
| tests/test_rutas_editor.py | 1660 | tests | Rutas de la vista previa del editor (capa 3): entra quien tiene acceso al |
| tests/test_rutas_exp_nuevo_presupuesto.py | 513 | tests | «Nuevo experimento › Cuánto» (E2 R4, spec 2026-10-02 §5.1–§5.3): el servidor rechaza un reparto que supera el total |
| tests/test_rutas_experimentos.py | 575 | tests | Rutas `exp_*` en dashboard: crear/piezas/lanzar/estado/presupuesto/refrescar/ |
| tests/test_rutas_experimentos_galeria.py | 133 | tests | La galería primero (spec 2026-09-20): «Nuevo experimento» abre con las piezas, |
| tests/test_rutas_final_edition.py | 959 | tests | Rutas de Final Edition en dashboard (preparar guion, guardar guion, |
| tests/test_rutas_guiones.py | 219 | tests | Rutas JSON del Blueprint guiones (chat de corrección de prompts de Flow Plus). |
| tests/test_rutas_guiones_pipeline.py | 538 | tests | Rutas del pipeline de Flow Plus: panel como fragmento, acciones JSON, aislamiento. |
| tests/test_rutas_hablado.py | 173 | tests | Rutas del anuncio hablado (spec 2026-10-01 §1, §3, §4): el panel por fetch, |
| tests/test_rutas_idioma.py | 111 | tests | Selector de idioma (spec 2026-09-26 §B3): cfg_idioma (cuenta / proyecto), |
| tests/test_rutas_mapa.py | 54 | tests | /mapa: el mapa conceptual del código (la versión interactiva de |
| tests/test_rutas_meta_agencia.py | 506 | tests | Meta en modo agencia, Task 2: el panel del admin (/admin/meta: conectar el |
| tests/test_rutas_meta_app.py | 88 | tests | Rutas de la app de Meta por proyecto: el cliente registra su app (id, |
| tests/test_rutas_meta_estado.py | 26 | tests | PND-114: la ruta legado usa el mismo candado que el worker de Meta. |
| tests/test_rutas_meta_forma.py | 370 | tests | El cliente elige cómo conectar Meta (spec §1-§4): elegir forma, buscar y |
| tests/test_rutas_mi_musica.py | 152 | tests | Rutas de Mi música (spec 2026-09-25): responden JSON con el panel ya |
| tests/test_rutas_nicho.py | 782 | tests | Rutas del Blueprint nicho: validan y delegan a nicho.datos / tareas.nicho; |
| tests/test_rutas_organico.py | 738 | tests | Rutas y UI de la publicación orgánica (Bloque 7, Task 3): Configuración › |
| tests/test_rutas_panel.py | 50 | tests | /panel rehecho como tablero de operación del admin: totales del mes, |
| tests/test_rutas_productos.py | 987 | tests | Rutas de productos (viven en Catálogo › Productos) y Configuración › Tienda |
| tests/test_rutas_referentes.py | 1556 | tests | Rutas del Blueprint referentes: grid y ficha como fragmentos; visibilidad por cliente. |
| tests/test_rutas_resultados.py | 752 | tests | Rutas del centro de resultados (E2, spec 2026-10-02 §2 y §4): el fragmento `exp_resultados`, el panel de |
| tests/test_rutas_sprints.py | 1103 | tests | Rutas del Blueprint sprints: validan y delegan a sprints.datos / tareas; |
| tests/test_rutas_tablero.py | 516 | tests | El Tablero (Bloque 6) fundido en Experimentos (E2, spec 2026-10-02): lo que antes era la pestaña Tablero ahora |
| tests/test_rutas_triple_whale.py | 294 | tests | Pestaña Triple Whale (spec 2026-09-28 §8): la página solo pinta el |
| tests/test_saldo.py | 105 | tests | Proveedor sin saldo (incidente 2026-09-30: WaveSpeed se quedó sin saldo a |
| tests/test_seguridad_auditoria.py | 318 | tests | Auditoría de seguridad 2026-10-01: lo que se corrigió, para que no vuelva. |
| tests/test_sembrar_edicion_demo.py | 74 | tests | La edición de demostración de la vista previa: medios sintéticos locales, |
| tests/test_sprint_sin_pais.py | 64 | tests | El sprint es para todos los países (pedido de Daniel, 2026-09-27): no lleva |
| tests/test_sprints_analisis.py | 239 | tests | test_parsear_json_tolera_bloques_de_codigo, test_parsear_json_descarta_hex_malformado_de_la_paleta, test_analizar_imagen_manda_url_y_reintenta, test_analizar_video_usa_fotogramas_locales, test_sugerir_personas_arma_prompt_y_colores, test_sugerir_personas_lista_cada_producto_una_vez_no_cada_color |
| tests/test_sprints_archivos.py | 37 | tests | _r2_falso, test_guardar_subida_imagen, test_registrar_local_video_extrae_fotograma, frame_falso |
| tests/test_sprints_calendario.py | 42 | tests | test_presets_por_pais_con_fechas_del_anio, test_tiene_calendario_dice_si_hubo_fallback, test_adoptar_crea_temporada_una_sola_vez, test_pais_del_proyecto |
| tests/test_sprints_datos.py | 442 | tests | test_persona_crear_listar_editar_archivar, test_persona_valida_nombre_y_origen, test_temporada_valida_fechas, _base, test_sprint_crear_y_validar, test_campana_repetida_y_cantidades |
| tests/test_sprints_db.py | 77 | tests | test_tablas_de_sprints_existen, _sprint_basico, test_campana_admite_la_misma_combinacion, test_migracion_0006_crea_las_tablas, test_alembic_tiene_una_sola_cabeza, test_migracion_0008_agrega_prioridad |
| tests/test_sprints_ideas.py | 629 | tests | _contando, test_parsear_valida_y_normaliza, test_faltantes_descuenta_vivas, _ctx, test_armar_prompt_incluye_todo_el_contexto, test_proponer_crea_ideas_y_reemplaza |
| tests/test_sprints_idioma.py | 206 | tests | Sprints: Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4); |
| tests/test_sprints_produccion.py | 538 | tests | escenario, test_estimar_cuenta_aprobadas_sin_sesion, test_crear_sesion_arma_referencias_prompt_y_vinculo, test_crear_sesion_sigue_la_preferencia_de_sonido_del_proyecto, test_crear_sesion_normaliza_y_recorta_el_sonido_de_la_idea, test_lanzar_lote_encola_con_prioridad_y_registra |
| tests/test_sprints_progreso_estado.py | 127 | tests | _c, test_progreso_campana_por_etapa, test_progreso_sprint_pondera_por_piezas, test_cobertura_sugiere_por_tipo_de_pieza, test_estado_campana_reglas, test_estado_sprint_reglas |
| tests/test_sprints_qa.py | 168 | tests | test_veredicto_puro, test_parsear_exige_score_y_cuatro_checks, test_formato_con_ffprobe_falso, test_evaluar_arma_prompt_y_mezcla_formato, test_evaluar_borra_el_temporal_aunque_falle_la_vision, _doctrina_ok |
| tests/test_sprints_revision_entrega.py | 130 | tests | _sprint_en_revision, test_aprobar_rechazar_y_aprobar_qa, test_resumen_cerrar_reabrir, test_enlaces_y_empaquetar, test_rechazar_conserva_registro_de_publicacion, test_nombre_archivo_normaliza_acentos |
| tests/test_sprints_tablero.py | 116 | tests | sprints.tablero: funciones puras de las tarjetas y la cabecera del tablero. |
| tests/test_sprints_tablero_datos.py | 153 | tests | sprints.datos para el tablero (spec 2026-09-26): mercado, marcas y momento |
| tests/test_sprints_tablero_entrega2.py | 476 | tests | Entrega 2 del tablero de Sprints (spec 2026-09-27): pestañas del panel, |
| tests/test_sprints_tablero_migracion.py | 105 | tests | Migración 0021 (tablero de Sprints, spec 2026-09-26): mercado, marcas y |
| tests/test_sprints_tablero_rutas.py | 500 | tests | Rutas del tablero de Sprints (spec 2026-09-26). Fixture `app` de |
| tests/test_sprints_temporada_opcional.py | 72 | tests | Campaña sin temporada (2026-09-26). El asistente ofrece la temporada como |
| tests/test_stickers.py | 108 | tests | Stickers propios del editor (capa 5c, D11): 20 PNG blancos sobre transparente, sin palabras, dibujados con |
| tests/test_subtitulos_fuente.py | 287 | tests | Subtítulos derivados del audio (editor, capa 5a, D1-D4): `mapear` (el |
| tests/test_tab_final.py | 285 | tests | Pestaña «Final edition» (decisión de Daniel, 2026-09-27): todo lo de final |
| tests/test_tablero.py | 719 | tests | Tablero (Bloque 6): deltas sobre snapshots acumulados, resumen del mes, |
| tests/test_tablero_cierre_ciego.py | 99 | tests | Sonda del guardián: el respaldo ciego es el CIERRE y la primera venta cayó dentro de la ventana. |
| tests/test_tablero_filtrar.py | 79 | tests | tablero.filtrar (spec 2026-10-02 §4.2): el centro de resultados reusa el motor |
| tests/test_tablero_moneda_ingresos.py | 19 | tests | test_pnd138_moneda_ajena_con_solo_ingresos |
| tests/test_tablero_rendimiento_ventas.py | 60 | tests | Sonda de 60 piezas/180 días y guarda determinista contra recorrer historias sin ventas. |
| tests/test_tarea_audio.py | 165 | tests | Tarea audio_generar (spec 2026-09-28 §4): voz por fal, mezcla, material y gasto. |
| tests/test_tarea_hablado.py | 73 | tests | Tarea hablado_voz (spec 2026-10-01 §3): la voz del anuncio hablado con la |
| tests/test_tarea_voz_propia.py | 32 | tests | Tarea voz_propia_crear (spec 2026-09-30 §3). |
| tests/test_tareas_audios_privacidad.py | 141 | tests | Revisión final de Audios Europa (F1): el error de un proveedor nunca llega a |
| tests/test_tareas_cadena.py | 151 | tests | Worker de la cadena de escenas de Flow Plus, con el proveedor, ffmpeg y R2 simulados. |
| tests/test_tareas_decidir.py | 465 | tests | exp_decidir (Bloque 4): veredictos por país, acciones vía acciones.pedir, |
| tests/test_tareas_director.py | 169 | tests | Tarea flowplus_director (spec §4): compila con Claude, guarda A/B en la |
| tests/test_tareas_doctrina.py | 65 | tests | Tarea `producto_pedidos` (doctrina, bloque 2, §5.3). |
| tests/test_tareas_edicion.py | 945 | tests | _doc, _gastos, entorno, test_job_ids, test_renderizar_final_devuelve_urls_versionadas_y_limpia_la_carpeta, test_renderizar_final_deriva_los_subtitulos_del_audio_antes_de_renderizar |
| tests/test_tareas_experimentos.py | 433 | tests | _sin_diagnostico_real, test_job_ids, _pieza_con_metricas, test_ranking_por_triple_whale_ordena_por_roas, test_exp_lanzar_llama_lanzador_y_reporta, test_exp_lanzar_interrumpida_marca_error |
| tests/test_tareas_final_edition.py | 115 | tests | Tareas del worker de Final Edition (`tareas/final_edition.py`): solo el |
| tests/test_tareas_flowplus.py | 1114 | tests | _estado_en_tmp, test_registra_tipos, test_etapas_mismos_pesos_que_dashboard, test_ejecutar_video_guarda_resultado, test_ejecutar_video_invalida_la_revision_de_la_doctrina_anterior, test_ejecutar_video_marca_error |
| tests/test_tareas_flowplus_hablado.py | 126 | tests | El worker y el anuncio hablado (spec 2026-10-01 §5): la misma tarea |
| tests/test_tareas_investigacion.py | 573 | tests | Cadena de la investigación: consultas, buscar, seleccionar, avanzar y los pasos de recolectar/generar (sin red, SQLite real). |
| tests/test_tareas_mantenimiento.py | 125 | tests | Mantenimiento periódico (auditoría 2026-09-28): salidas/, cola y respaldos. |
| tests/test_tareas_meta.py | 324 | tests | _creds_falsas, test_registra_tipos, test_refrescar_guarda_snapshot, test_refrescar_anuncio_inexistente, test_publicar_interrumpido_no_repite_campana, test_interrumpida_marca_el_anuncio_en_error_solo_si_publicando |
| tests/test_tareas_nicho.py | 512 | tests | _estudio, test_encolar_generar, test_ejecutar_generar_guarda_registra_gasto_y_recalcula, test_ejecutar_generar_falla_deja_error_y_estado, test_ejecutar_generar_falla_al_guardar_deja_error_y_estado, test_interrumpida_generar |
| tests/test_tareas_organico.py | 176 | tests | Tarea del worker `organico_publicar` (Bloque 7): cablea organico.publicar |
| tests/test_tareas_referentes.py | 1049 | tests | tareas.referentes: importación de copycoders por fases, sin red (costuras monkeypatcheadas). |
| tests/test_tareas_sprints.py | 612 | tests | _referencia, test_job_ids, test_analizar_referencia_guarda_analisis, test_analizar_referencia_error_deja_rastro, test_encolar_analisis_usa_el_worker, test_sugerir_personas_crea_filas |
| tests/test_tareas_swap.py | 318 | tests | test_registro_contiene_swap_generar, test_interrumpida_marca_el_swap_en_error, test_etapas_mismas_que_dashboard, test_lanzar_swap_encola, test_lanzar_swap_video_etapas_y_sin_mejora, test_ejecutar_sin_producto_marca_error |
| tests/test_tareas_tiendas.py | 594 | tests | Tareas del worker de tiendas (`tareas/tiendas.py`): sync de productos y |
| tests/test_tarjetas_ligeras.py | 436 | tests | Tarjetas ligeras y detalle bajo demanda (spec 2026-09-28): la página pinta |
| tests/test_tiendas_db.py | 376 | tests | clave, _pieza, test_conectar_listar_credenciales_desconectar, test_upsert_producto_conserva_marcas, test_pedidos, test_resolver_pedido_rechaza_pieza_ajena |
| tests/test_tipografia.py | 528 | tests | La maqueta del texto (capa 5c, D5): qué caracteres salen, dónde se parte cada |
| tests/test_trabajos_adaptador.py | 41 | tests | test_encolar_y_consultar_pendiente, test_consultar_en_curso_usa_la_curva_y_no_retrocede, test_consultar_terminada, test_memoria_sigue_funcionando |
| tests/test_transcripcion.py | 193 | tests | Transcripción automática para subtítulos (editor capa 5a, spec D5/D6): |
| tests/test_triple_whale.py | 247 | tests | Cliente de la API de Triple Whale y conexión por proyecto (spec |
| tests/test_triple_whale_analisis.py | 360 | tests | Evaluación con IA (spec 2026-09-28 §6): muestra, prompt, parseo con la |
| tests/test_triple_whale_avisos.py | 79 | tests | Avisos por correo tras cada copia de Triple Whale (spec 2026-09-28 §12). |
| tests/test_triple_whale_evaluacion.py | 144 | tests | Evaluación gratis del contenido (spec 2026-09-28 §5): métricas, veredicto, |
| tests/test_triple_whale_ideas_piezas.py | 98 | tests | Idea → pieza → anuncio (spec 2026-09-28 §14): «Llevar a Crear» deja en el |
| tests/test_triple_whale_sync.py | 279 | tests | Copia de Triple Whale a la base (spec 2026-09-28 §4) y sus tareas del worker. |
| tests/test_usuarios_por_cliente.py | 46 | tests | usuarios.por_cliente: las cuentas rol «cliente» de un proyecto (las alertas |
| tests/test_variantes.py | 214 | tests | Bloque 4 — variantes de Final edition (guion hook/estructura, finales |
| tests/test_vista_previa.py | 252 | tests | Datos de la página de vista previa del editor: destinos, materiales, |
| tests/test_voces_propias.py | 480 | tests | Voces propias (spec 2026-09-30 §3): clonar o diseñar con MiniMax vía fal, |
| tests/test_wavespeed_common.py | 145 | tests | El poll de WaveSpeed (incidente 2026-09-28): un fallo del proveedor se |
| tests/test_worker.py | 139 | tests | test_ciclo_ejecuta_y_termina, test_ciclo_falla_y_reprograma, test_tipo_desconocido_queda_en_error, test_periodicas_se_encolan_una_vez_por_ventana, test_periodicas_no_se_duplican_aunque_la_primera_termine, test_ciclo_no_reclama_si_debe_parar |
| tests/test_worker_carriles.py | 255 | tests | Carril de Crear (spec 2026-09-28-crear-sin-cola): las generaciones de Crear |
| tests/test_worker_idioma.py | 29 | tests | El worker corre cada tarea en el idioma de su proyecto (spec 2026-09-26 §B8): |
| tiendas.py | 591 | raíz | Tiendas conectadas (Shopify/Woo/MELI/CSV/URL), su catálogo normalizado |
| trabajos.py | 377 | raíz | Trabajos en segundo plano para las acciones lentas del dashboard (generar |
| triple_whale_tiendas.py | 161 | raíz | Conexión de Triple Whale por proyecto (tabla `triple_whale`). |
| uploaders/__init__.py | 0 | uploaders | Fuente de uploaders |
| uploaders/meta_uploader.py | 116 | uploaders | Subida de video a Facebook (Página) e Instagram (cuenta Business/Creator) vía Graph API. |
| uploaders/tiktok_uploader.py | 181 | uploaders | Subida de video a TikTok usando la Content Posting API (v2). |
| uploaders/youtube_uploader.py | 74 | uploaders | Subida de video a YouTube usando la YouTube Data API v3. |
| usuarios.py | 338 | raíz | Usuarios y control de acceso por proyecto. Un solo archivo usuarios.json en la |
| validar_marca.py | 77 | raíz | Valida un archivo de "submundo" (temporada, colección o proyecto) de un cliente |
| voces_propias.py | 419 | raíz | Voces propias de Audios (spec docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md §3): |
| worker.py | 340 | raíz | Worker de Creatv Machine: proceso aparte de gunicorn (servicio systemd |


## Rutas declaradas

| Método | Ruta relativa | Función | Dónde |
| --- | --- | --- | --- |
| GET | /trabajo/<path:job_id>/estado | estado_trabajo | dashboard.py:692 |
| POST | /cliente/<cliente>/personaje/subir | subir_personaje | dashboard.py:879 |
| POST | /cliente/<cliente>/personaje/<nombre>/eliminar | eliminar_personaje | dashboard.py:886 |
| POST | /cliente/<cliente>/escena/subir | subir_escena | dashboard.py:893 |
| POST | /cliente/<cliente>/escena/<nombre>/eliminar | eliminar_escena | dashboard.py:900 |
| POST | /cliente/<cliente>/producto_referencia/subir | subir_producto_referencia | dashboard.py:907 |
| POST | /cliente/<cliente>/producto_referencia/<nombre>/eliminar | eliminar_producto_referencia | dashboard.py:914 |
| POST | /cliente/<cliente>/logos/subir | subir_logo | dashboard.py:921 |
| POST | /cliente/<cliente>/logos/<nombre>/eliminar | eliminar_logo | dashboard.py:936 |
| POST | /cliente/<cliente>/marca/subir | subir_marca | dashboard.py:943 |
| POST | /cliente/<cliente>/marca/analizar | analizar_marca | dashboard.py:954 |
| POST | /cliente/<cliente>/marca/guardar | guardar_marca | dashboard.py:979 |
| GET | / | index | dashboard.py:1039 |
| GET | /privacidad | privacidad | dashboard.py:1193 |
| GET | /terminos | terminos | dashboard.py:1201 |
| GET | /eliminar-datos | eliminar_datos | dashboard.py:1208 |
| GET | /l/<cliente> | landing_cliente | dashboard.py:1229 |
| GET | /panel | panel | dashboard.py:1247 |
| GET | /salud | salud_publica | dashboard.py:1269 |
| GET | /admin/salud | admin_salud | dashboard.py:1281 |
| GET | /admin/estilos | admin_estilos | dashboard.py:1306 |
| POST | /admin/salud/errores/<int:error_id> | admin_salud_error | dashboard.py:1329 |
| POST | /admin/salud/errores/resolver-todos | admin_salud_resolver_todos | dashboard.py:1342 |
| POST | /admin/salud/metricas/reiniciar | admin_salud_reiniciar_metricas | dashboard.py:1356 |
| GET | /admin/salud/registros | admin_registros | dashboard.py:1365 |
| GET | /admin/salud/registros/<proceso>.log | admin_registros_descargar | dashboard.py:1379 |
| GET | /panel/gasto.csv | panel_gasto_csv | dashboard.py:1395 |
| GET | /mapa | mapa_codigo | dashboard.py:1430 |
| GET,POST | /login | login | dashboard.py:1445 |
| POST | /logout | logout | dashboard.py:1476 |
| POST | /proyectos/nuevo | crear_proyecto | dashboard.py:1483 |
| GET | /verificar/<token> | verificar_correo | dashboard.py:1568 |
| POST | /reenviar-verificacion | reenviar_verificacion | dashboard.py:1590 |
| GET,POST | /recuperar | recuperar | dashboard.py:1617 |
| GET,POST | /restablecer/<token> | restablecer | dashboard.py:1633 |
| POST | /cuenta/correo | cuenta_correo | dashboard.py:1671 |
| POST | /cuenta/password | cuenta_password | dashboard.py:1713 |
| POST | /cliente/<cliente>/cfg_idioma | cfg_idioma | dashboard.py:1742 |
| GET | /idioma/<codigo> | cambiar_idioma | dashboard.py:1770 |
| POST | /admin/usuarios/<usuario>/verificar | admin_usuario_verificar | dashboard.py:1789 |
| GET | /cliente/<cliente> | ver_cliente | dashboard.py:2115 |
| POST | /cliente/<cliente>/idea/nueva | nueva_idea | dashboard.py:2276 |
| POST | /cliente/<cliente>/idea/nueva_visual | nueva_idea_visual | dashboard.py:2368 |
| POST | /cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/aprobar | aprobar_concepto_imagen | dashboard.py:2406 |
| POST | /cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/descartar | descartar_concepto_imagen | dashboard.py:2432 |
| POST | /cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/animacion/<anim_id>/generar_video | generar_video_animacion | dashboard.py:2439 |
| POST | /cliente/<cliente>/idea/<idea_id>/eliminar_visual | eliminar_idea_visual | dashboard.py:2564 |
| GET | /cliente/<cliente>/productos/<path:producto_id>/imagen | imagen_producto | dashboard.py:2582 |
| GET | /cliente/<cliente>/productos/<path:producto_id>/imagen/<nombre> | imagen_producto_archivo | dashboard.py:2606 |
| POST | /cliente/<cliente>/nombre | guardar_nombre_proyecto | dashboard.py:2640 |
| POST | /cliente/<cliente>/preferencias/guardar | guardar_preferencias_swap | dashboard.py:2649 |
| POST | /cliente/<cliente>/preferencias_flowplus/guardar | guardar_preferencias_flowplus | dashboard.py:2670 |
| POST | /cliente/<cliente>/preferencias_sonido/guardar | guardar_preferencias_sonido | dashboard.py:2684 |
| GET | /cliente/<cliente>/doctrina | doctrina_pagina | dashboard.py:2794 |
| POST | /cliente/<cliente>/productos/crear | crear_producto | dashboard.py:2805 |
| POST | /cliente/<cliente>/productos/<producto_id>/actualizar | actualizar_producto | dashboard.py:2880 |
| POST | /cliente/<cliente>/productos/<producto_id>/imagenes/subir | subir_imagen_producto | dashboard.py:2905 |
| POST | /cliente/<cliente>/productos/<producto_id>/imagenes/<nombre>/eliminar | eliminar_imagen_producto | dashboard.py:2925 |
| POST | /cliente/<cliente>/productos/<producto_id>/eliminar | eliminar_producto | dashboard.py:2938 |
| POST | /cliente/<cliente>/productos/<producto_id>/colores | catalogo_color_agregar | dashboard.py:2962 |
| POST | /cliente/<cliente>/productos/<producto_id>/colores/<color_id>/quitar | catalogo_color_quitar | dashboard.py:2985 |
| POST | /cliente/<cliente>/productos/<producto_id>/fotos/<nombre>/mover | catalogo_foto_mover | dashboard.py:2995 |
| POST | /cliente/<cliente>/catalogo/producto/<producto_id>/crear-con | catalogo_crear_con | dashboard.py:3006 |
| POST | /cliente/<cliente>/catalogo/producto/<producto_id>/archivar | catalogo_archivar | dashboard.py:3021 |
| GET | /cliente/<cliente>/catalogo/grid | catalogo_grid | dashboard.py:3079 |
| GET | /cliente/<cliente>/catalogo/<cat>/<path:activo_id>/ficha | catalogo_ficha | dashboard.py:3113 |
| GET | /cliente/<cliente>/swap | ver_swap | dashboard.py:3422 |
| POST | /cliente/<cliente>/swap/generar | generar_swap | dashboard.py:3562 |
| GET | /cliente/<cliente>/swap/<swap_id>/original | imagen_swap_original | dashboard.py:3668 |
| POST | /cliente/<cliente>/swap/<swap_id>/eliminar | eliminar_swap | dashboard.py:3687 |
| POST | /cliente/<cliente>/ads/nueva_campana | nueva_campana | dashboard.py:3694 |
| POST | /cliente/<cliente>/swap/<swap_id>/enviar_a_publicidad | enviar_swap_a_publicidad | dashboard.py:3703 |
| POST | /cliente/<cliente>/video/<brief_id>/enviar_a_publicidad | enviar_video_a_publicidad | dashboard.py:3718 |
| POST | /cliente/<cliente>/meta/app | meta_app_guardar | dashboard.py:3764 |
| POST | /cliente/<cliente>/meta/app/borrar | meta_app_borrar | dashboard.py:3788 |
| GET | /cliente/<cliente>/meta/conectar | meta_conectar | dashboard.py:3799 |
| GET | /meta/callback | meta_callback | dashboard.py:3818 |
| GET,POST | /cliente/<cliente>/meta/elegir | meta_elegir | dashboard.py:3862 |
| POST | /cliente/<cliente>/meta/cancelar | meta_cancelar | dashboard.py:3927 |
| POST | /cliente/<cliente>/meta/desconectar | meta_desconectar | dashboard.py:3936 |
| POST | /cliente/<cliente>/meta/forma | meta_forma | dashboard.py:3997 |
| POST | /cliente/<cliente>/meta/agencia/buscar | meta_agencia_buscar | dashboard.py:4027 |
| POST | /cliente/<cliente>/meta/agencia/conectar | meta_agencia_conectar | dashboard.py:4042 |
| POST | /cliente/<cliente>/meta/agencia/avisar | meta_agencia_avisar | dashboard.py:4115 |
| POST | /cliente/<cliente>/meta/agencia/avisar/cancelar | meta_agencia_avisar_cancelar | dashboard.py:4155 |
| POST | /cliente/<cliente>/meta/agencia/salir | meta_agencia_salir | dashboard.py:4167 |
| GET | /admin/meta | admin_meta | dashboard.py:4231 |
| POST | /admin/meta/conectar | admin_meta_conectar | dashboard.py:4264 |
| POST | /admin/meta/desconectar | admin_meta_desconectar | dashboard.py:4284 |
| POST | /admin/meta/activos/actualizar | admin_meta_activos_actualizar | dashboard.py:4306 |
| POST | /admin/meta/asignar/<cliente> | admin_meta_asignar | dashboard.py:4326 |
| POST | /admin/meta/desasignar/<cliente> | admin_meta_desasignar | dashboard.py:4372 |
| POST | /admin/meta/solicitud/<cliente>/descartar | admin_meta_solicitud_descartar | dashboard.py:4388 |
| GET | /admin/referentes | admin_referentes | dashboard.py:4405 |
| POST | /admin/referentes/importar | admin_referentes_importar | dashboard.py:4476 |
| POST | /admin/referentes/traer | admin_referentes_traer | dashboard.py:4493 |
| POST | /admin/referentes/familias/<int:familia_id> | admin_referentes_familia | dashboard.py:4541 |
| POST | /admin/referentes/familias/ingles | admin_referentes_familias_en | dashboard.py:4552 |
| POST | /admin/referentes/barridos/<int:barrido_id>/clasificar | admin_referentes_clasificar | dashboard.py:4579 |
| POST | /admin/referentes/barridos/<int:barrido_id>/reintentar-imagenes | admin_referentes_reintentar_imagenes | dashboard.py:4601 |
| POST | /cliente/<cliente>/ads/publicar | publicar_ad | dashboard.py:4618 |
| POST | /cliente/<cliente>/ads/<ad_id>/actualizar | actualizar_resultados_ad | dashboard.py:4628 |
| POST | /cliente/<cliente>/ads/<ad_id>/estado | cambiar_estado_ad | dashboard.py:4650 |
| POST | /cliente/<cliente>/ads/<ad_id>/reintentar | reintentar_ad | dashboard.py:4682 |
| POST | /cliente/<cliente>/ads/<ad_id>/eliminar | eliminar_ad | dashboard.py:4695 |
| POST | /cliente/<cliente>/alertas/descartar | alertas_descartar | dashboard.py:5076 |
| POST | /cliente/<cliente>/alertas/restaurar | alertas_restaurar | dashboard.py:5097 |
| GET | /cliente/<cliente>/tablero/mes.csv | tab_descargar_csv | dashboard.py:5107 |
| GET | /cliente/<cliente>/gasto/mes.csv | gasto_csv | dashboard.py:5230 |
| GET | /cliente/<cliente>/experimentos/resultados | exp_resultados | dashboard.py:5248 |
| GET | /cliente/<cliente>/experimentos/pieza/<int:ep_id> | exp_pieza | dashboard.py:5277 |
| GET | /cliente/<cliente>/experimentos/nuevo | exp_nuevo | dashboard.py:5293 |
| POST | /cliente/<cliente>/experimentos/nuevo | exp_crear | dashboard.py:5305 |
| POST | /cliente/<cliente>/experimentos/probar | exp_probar | dashboard.py:5433 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/piezas | exp_agregar_pieza | dashboard.py:5547 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/piezas/<int:ep_id>/quitar | exp_quitar_pieza | dashboard.py:5565 |
| POST | /cliente/<cliente>/experimentos/meter | exp_meter_pieza | dashboard.py:5582 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/lanzar | exp_lanzar | dashboard.py:5606 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/estado | exp_estado | dashboard.py:5644 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/presupuesto | exp_presupuesto | dashboard.py:5663 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/refrescar | exp_refrescar | dashboard.py:5695 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/cerrar | exp_cerrar | dashboard.py:5713 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/modo | exp_modo | dashboard.py:5746 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/reglas | exp_reglas | dashboard.py:5777 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/decidir | exp_decidir_ahora | dashboard.py:5795 |
| POST | /cliente/<cliente>/propuestas/<int:pid>/aprobar | prop_aprobar | dashboard.py:5878 |
| POST | /cliente/<cliente>/propuestas/<int:pid>/rechazar | prop_rechazar | dashboard.py:5903 |
| POST | /cliente/<cliente>/experimentos/<int:eid>/propuestas/aprobar_todas | prop_aprobar_todas | dashboard.py:5921 |
| POST | /cliente/<cliente>/organico/redactar | org_redactar | dashboard.py:6020 |
| POST | /cliente/<cliente>/organico/publicar | org_publicar | dashboard.py:6040 |
| POST | /cliente/<cliente>/organico/<int:pub_id>/reintentar | org_reintentar | dashboard.py:6125 |
| POST | /cliente/<cliente>/config/reglas | cfg_reglas | dashboard.py:6167 |
| POST | /cliente/<cliente>/config/correo | cfg_correo | dashboard.py:6183 |
| POST | /cliente/<cliente>/productos/importar/archivo | prod_importar_archivo | dashboard.py:6352 |
| POST | /cliente/<cliente>/productos/importar/url | prod_importar_url | dashboard.py:6406 |
| POST | /cliente/<cliente>/productos/<int:pid>/pruebas | prod_prueba_agregar | dashboard.py:6423 |
| POST | /cliente/<cliente>/productos/<int:pid>/pruebas/<prueba_id>/borrar | prod_prueba_borrar | dashboard.py:6438 |
| POST | /cliente/<cliente>/productos/<int:pid>/pedidos/actualizar | prod_pedidos_actualizar | dashboard.py:6448 |
| POST | /cliente/<cliente>/productos/<int:pid>/pedidos/<pedido_id>/responder | prod_pedido_responder | dashboard.py:6465 |
| POST | /cliente/<cliente>/productos/<int:pid>/pedidos/<pedido_id>/descartar | prod_pedido_descartar | dashboard.py:6480 |
| POST | /cliente/<cliente>/productos/<int:pid>/marcar | prod_marcar | dashboard.py:6490 |
| POST | /cliente/<cliente>/productos/<int:pid>/archivar | prod_archivar | dashboard.py:6532 |
| POST | /cliente/<cliente>/productos/<int:pid>/vincular | prod_vincular | dashboard.py:6548 |
| POST | /cliente/<cliente>/productos/<int:pid>/fotos | prod_fotos_subir | dashboard.py:6570 |
| POST | /cliente/<cliente>/productos/<int:pid>/experimento | prod_experimento | dashboard.py:6620 |
| POST | /cliente/<cliente>/config/tienda/conectar | tienda_conectar | dashboard.py:6659 |
| GET | /cliente/<cliente>/config/tienda/meli/iniciar | tienda_meli_iniciar | dashboard.py:6718 |
| GET | /meli/callback | meli_callback | dashboard.py:6743 |
| POST | /cliente/<cliente>/config/tienda/<int:tid>/sincronizar | tienda_sync | dashboard.py:6779 |
| POST | /cliente/<cliente>/config/tienda/<int:tid>/desconectar | tienda_desconectar | dashboard.py:6803 |
| POST | /cliente/<cliente>/config/pixel/refrescar | cfg_pixel_refrescar | dashboard.py:6833 |
| POST | /cliente/<cliente>/prompt/<prompt_id>/guardar | guardar_prompt | dashboard.py:6845 |
| POST | /cliente/<cliente>/prompt/<prompt_id>/aprobar | aprobar_prompt | dashboard.py:6923 |
| POST | /cliente/<cliente>/prompt/<prompt_id>/regenerar_imagen | regenerar_imagen | dashboard.py:6943 |
| POST | /cliente/<cliente>/prompt/<prompt_id>/aprobar_imagen | aprobar_imagen | dashboard.py:6962 |
| POST | /cliente/<cliente>/prompt/<prompt_id>/rechazar | rechazar_prompt | dashboard.py:7041 |
| POST | /cliente/<cliente>/idea/<idea_id>/eliminar | eliminar_idea | dashboard.py:7052 |
| POST | /cliente/<cliente>/aprobar/<brief_id> | aprobar | dashboard.py:7062 |
| POST | /cliente/<cliente>/rechazar/<brief_id> | rechazar | dashboard.py:7097 |
| GET | /cliente/<cliente>/crear/tarjetas | crear_tarjetas | dashboard.py:7112 |
| GET | /cliente/<cliente>/creative_flow/<cf_id>/detalle | cf_detalle | dashboard.py:7124 |
| GET | /cliente/<cliente>/final/tarjetas | final_tarjetas | dashboard.py:7136 |
| GET | /cliente/<cliente>/creative_flow/<cf_id>/final/detalle | fe_detalle_video | dashboard.py:7154 |
| GET | /cliente/<cliente>/creative_flow/<cf_id>/final/<final_id>/detalle | fe_detalle_final | dashboard.py:7167 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/descartar | cf_descartar | dashboard.py:7180 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/angulo | cf_angulo | dashboard.py:7232 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/revisar | cf_revisar | dashboard.py:7251 |
| POST | /cliente/<cliente>/aprendizajes | apr_agregar | dashboard.py:7265 |
| POST | /cliente/<cliente>/aprendizajes/<aid>/quitar | apr_quitar | dashboard.py:7279 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/final/preparar | fe_preparar | dashboard.py:7311 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/final/guion | fe_guardar_guion | dashboard.py:7336 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/final/producir | fe_producir | dashboard.py:7375 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/final/<final_id>/descartar | fe_descartar | dashboard.py:7451 |
| POST | /cliente/<cliente>/flowplus/referencias/subir | fp_subir_referencias | dashboard.py:7542 |
| GET | /cliente/<cliente>/flowplus/referencias/bandeja | fp_bandeja | dashboard.py:7564 |
| POST | /cliente/<cliente>/flowplus/referencias/link | fp_agregar_link | dashboard.py:7570 |
| POST | /cliente/<cliente>/flowplus/referencias/<rid>/quitar | fp_quitar_referencia | dashboard.py:7615 |
| POST | /cliente/<cliente>/flowplus/referencias/vaciar | fp_vaciar_referencias | dashboard.py:7623 |
| POST | /cliente/<cliente>/musica/subir | mm_subir | dashboard.py:7647 |
| POST | /cliente/<cliente>/musica/<int:mid>/borrar | mm_borrar | dashboard.py:7662 |
| POST | /cliente/<cliente>/musica/crear | mm_crear | dashboard.py:7674 |
| GET | /cliente/<cliente>/musica/lista | mm_lista | dashboard.py:7688 |
| GET | /cliente/<cliente>/audios/lista | au_lista | dashboard.py:7714 |
| POST | /cliente/<cliente>/audios/crear | au_crear | dashboard.py:7719 |
| POST | /cliente/<cliente>/audios/<int:aid>/borrar | au_borrar | dashboard.py:7735 |
| POST | /cliente/<cliente>/audios/muestra | au_muestra | dashboard.py:7749 |
| GET | /cliente/<cliente>/audios/<int:aid>/descargar | au_descargar | dashboard.py:7769 |
| GET | /cliente/<cliente>/audios/voces | vp_lista | dashboard.py:7835 |
| POST | /cliente/<cliente>/audios/voces/disenar | vp_disenar | dashboard.py:7840 |
| POST | /cliente/<cliente>/audios/voces/clonar | vp_clonar | dashboard.py:7854 |
| POST | /cliente/<cliente>/audios/voces/<int:vid>/borrar | vp_borrar | dashboard.py:7890 |
| POST | /cliente/<cliente>/flowplus/reusar/<cf_id> | fp_reusar | dashboard.py:7904 |
| POST | /cliente/<cliente>/flowplus/describir | fp_describir | dashboard.py:7991 |
| POST | /cliente/<cliente>/creative_flow/crear | cf_crear_video | dashboard.py:8009 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/prompt | cf_guardar_prompt | dashboard.py:8287 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/rearmar | cf_rearmar | dashboard.py:8314 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/recuperar | cf_recuperar | dashboard.py:8341 |
| POST | /cliente/<cliente>/creative_flow/sugerir_sonido | fp_sugerir_sonido | dashboard.py:8366 |
| POST | /cliente/<cliente>/creative_flow/<cf_id>/generar_video | cf_generar_video | dashboard.py:8387 |
| POST | /cliente/<cliente>/cfg_triple_whale/conectar | cfg_triple_whale_conectar | dashboard.py:8587 |
| POST | /cliente/<cliente>/cfg_triple_whale/probar | cfg_triple_whale_probar | dashboard.py:8619 |
| POST | /cliente/<cliente>/cfg_triple_whale/ajustes | cfg_triple_whale_ajustes | dashboard.py:8648 |
| POST | /cliente/<cliente>/cfg_triple_whale/desconectar | cfg_triple_whale_desconectar | dashboard.py:8667 |
| GET | /<int:edicion_id> | ver | final_edition/rutas_editor.py:39 |
| GET | /<int:edicion_id>/materiales | materiales_json | final_edition/rutas_editor.py:85 |
| PUT | /<int:edicion_id> | guardar | final_edition/rutas_editor.py:112 |
| POST | /<int:edicion_id>/producir | producir | final_edition/rutas_editor.py:153 |
| POST | /<int:edicion_id>/subtitulos/estimar | subtitulos_estimar | final_edition/rutas_editor.py:284 |
| POST | /<int:edicion_id>/subtitulos/transcribir | transcribir_subtitulos | final_edition/rutas_editor.py:318 |
| POST | /<int:edicion_id>/voz/estimar | voz_estimar | final_edition/rutas_editor.py:376 |
| POST | /<int:edicion_id>/voz | voz | final_edition/rutas_editor.py:408 |
| GET | /voz/<clave> | voz_material | final_edition/rutas_editor.py:445 |
| POST | /materiales/grabacion | grabacion | final_edition/rutas_editor.py:458 |
| POST | /desde/<cf_id> | desde_clon | final_edition/rutas_editor.py:474 |
| POST | /materiales/subir | subir_material | final_edition/rutas_editor.py:498 |
| POST | /materiales/<material_id>/borrar | borrar_material | final_edition/rutas_editor.py:512 |
| GET | /biblioteca | ver_biblioteca | final_edition/rutas_editor.py:531 |
| POST | /biblioteca/pieza/<cf_id> | agregar_pieza | final_edition/rutas_editor.py:536 |
| POST | /biblioteca/sticker/<sticker_id> | agregar_sticker | final_edition/rutas_editor.py:556 |
| GET | /materiales | materiales_por_id | final_edition/rutas_editor.py:573 |
| GET | /prompts | prompts | guiones/rutas.py:69 |
| POST | /prompts | prompt_crear | guiones/rutas.py:74 |
| GET | /prompts/<int:pid> | prompt_ver | guiones/rutas.py:91 |
| POST | /prompts/<int:pid>/mensajes | prompt_mensaje | guiones/rutas.py:99 |
| POST | /prompts/<int:pid>/usar | prompt_usar | guiones/rutas.py:113 |
| POST | /prompts/<int:pid>/editar | prompt_editar | guiones/rutas.py:132 |
| POST | /prompts/<int:pid>/aprobar | prompt_aprobar | guiones/rutas.py:146 |
| POST | /prompts/<int:pid>/reabrir | prompt_reabrir | guiones/rutas.py:162 |
| GET | /panel | panel | guiones/rutas_pipeline.py:153 |
| POST | /lotes | lote_crear | guiones/rutas_pipeline.py:163 |
| GET | /notion | notion_estado | guiones/rutas_pipeline.py:192 |
| POST | /notion | notion_conectar | guiones/rutas_pipeline.py:197 |
| POST | /notion/borrar | notion_borrar | guiones/rutas_pipeline.py:215 |
| POST | /lotes/<int:lid>/reintentar | lote_reintentar | guiones/rutas_pipeline.py:223 |
| POST | /guiones/<int:gid>/lectura | guion_lectura | guiones/rutas_pipeline.py:242 |
| POST | /guiones/<int:gid>/confirmar | guion_confirmar | guiones/rutas_pipeline.py:255 |
| POST | /guiones/<int:gid>/duplicar | guion_duplicar | guiones/rutas_pipeline.py:266 |
| POST | /guiones/<int:gid>/videos | video_crear | guiones/rutas_pipeline.py:284 |
| POST | /videos/<int:vid>/config | video_config | guiones/rutas_pipeline.py:297 |
| POST | /videos/<int:vid>/calcular | video_calcular | guiones/rutas_pipeline.py:310 |
| POST | /videos/<int:vid>/recorte/proponer | video_recorte_proponer | guiones/rutas_pipeline.py:323 |
| POST | /videos/<int:vid>/recorte | video_recorte | guiones/rutas_pipeline.py:338 |
| POST | /videos/<int:vid>/armar | video_armar | guiones/rutas_pipeline.py:351 |
| POST | /videos/<int:vid>/nueva-version | video_nueva_version | guiones/rutas_pipeline.py:363 |
| GET | /videos/<int:vid> | video_ver | guiones/rutas_pipeline.py:380 |
| GET | /videos/<int:vid>/documento.md | video_documento | guiones/rutas_pipeline.py:389 |
| POST | /videos/<int:vid>/imagenes | video_imagenes | guiones/rutas_pipeline.py:402 |
| GET | /videos/<int:vid>/imagenes.md | video_imagenes_md | guiones/rutas_pipeline.py:414 |
| POST | /videos/<int:vid>/escenas/<int:indice> | escena_imagenes | guiones/rutas_pipeline.py:434 |
| POST | /videos/<int:vid>/imagenes/subir | escena_subir | guiones/rutas_pipeline.py:450 |
| POST | /videos/<int:vid>/imagenes/catalogo | escena_catalogo | guiones/rutas_pipeline.py:487 |
| POST | /videos/<int:vid>/imagenes/quitar | escena_quitar | guiones/rutas_pipeline.py:507 |
| POST | /videos/<int:vid>/escenas/<int:indice>/crear | escena_a_crear | guiones/rutas_pipeline.py:520 |
| POST | /videos/<int:vid>/cadena | cadena_aprobar | guiones/rutas_pipeline.py:574 |
| POST | /videos/<int:vid>/cadena/detener | cadena_detener | guiones/rutas_pipeline.py:620 |
| GET | /bloque-global | bloque_global_ver | guiones/rutas_pipeline.py:636 |
| POST | /bloque-global | bloque_global_guardar | guiones/rutas_pipeline.py:642 |
| GET | /panel | panel | hablado_rutas.py:48 |
| POST | /foto | foto | hablado_rutas.py:61 |
| POST | /voz | voz | hablado_rutas.py:82 |
| POST | /crear | crear | hablado_rutas.py:106 |
| POST | /estudios | crear | nicho/rutas.py:178 |
| GET | /<int:eid> | ver | nicho/rutas.py:192 |
| POST | /<int:eid>/editar | editar | nicho/rutas.py:255 |
| POST | /<int:eid>/archivar | archivar | nicho/rutas.py:269 |
| POST | /<int:eid>/eliminar | eliminar | nicho/rutas.py:276 |
| POST | /<int:eid>/comentarios/texto | comentarios_texto | nicho/rutas.py:294 |
| POST | /<int:eid>/comentarios/archivo | comentarios_archivo | nicho/rutas.py:312 |
| POST | /comentario/<int:cid>/excluir | comentario_excluir | nicho/rutas.py:334 |
| POST | /<int:eid>/comentarios/borrar/<fuente> | comentarios_borrar | nicho/rutas.py:343 |
| POST | /<int:eid>/recolectar/<fuente> | recolectar | nicho/rutas.py:355 |
| GET | /<int:eid>/recolectar/apify/estimar | apify_estimar | nicho/rutas.py:385 |
| POST | /<int:eid>/generar | generar | nicho/rutas.py:397 |
| POST | /avatar/<int:aid>/editar | avatar_editar | nicho/rutas.py:458 |
| POST | /avatar/<int:aid>/aprobar | avatar_aprobar | nicho/rutas.py:473 |
| POST | /avatar/<int:aid>/descartar | avatar_descartar | nicho/rutas.py:488 |
| GET | /avatares | avatares_proyecto | nicho/rutas.py:500 |
| POST | /avatares/nuevo | avatar_crear | nicho/rutas.py:516 |
| POST | /persona/<int:pid>/ficha | persona_ficha | nicho/rutas.py:531 |
| POST | /persona/<int:pid>/archivar | persona_archivar | nicho/rutas.py:542 |
| POST | /<int:eid>/completar | completar | nicho/rutas.py:561 |
| GET | /<int:eid>/exportar.md | exportar_md | nicho/rutas.py:590 |
| GET | /<int:eid>/exportar.xlsx | exportar_xlsx | nicho/rutas.py:598 |
| GET | /<int:eid>/investigacion/estimar | investigacion_estimar | nicho/rutas.py:664 |
| POST | /<int:eid>/investigacion | investigacion_iniciar | nicho/rutas.py:679 |
| POST | /<int:eid>/investigacion/reanudar | investigacion_reanudar | nicho/rutas.py:714 |
| POST | /<int:eid>/investigacion/cancelar | investigacion_cancelar | nicho/rutas.py:736 |
| POST | /copycoders | copycoders | referentes/rutas.py:74 |
| GET | /grid | grid | referentes/rutas.py:99 |
| GET | /traer | traer_form | referentes/rutas.py:151 |
| POST | /traer | traer_post | referentes/rutas.py:171 |
| GET | /<int:rid>/recrear | recrear_form | referentes/rutas.py:288 |
| POST | /<int:rid>/recrear/leer | recrear_leer | referentes/rutas.py:333 |
| POST | /<int:rid>/recrear/adaptar | recrear_adaptar | referentes/rutas.py:356 |
| POST | /<int:rid>/recrear/generar | recrear_generar | referentes/rutas.py:405 |
| GET | /<int:rid>/ficha | ficha | referentes/rutas.py:535 |
| GET | /barridos | barridos | referentes/rutas.py:581 |
| POST | /<int:bid>/clasificar_pendientes | clasificar_pendientes | referentes/rutas.py:607 |
| POST | /<int:bid>/reintentar_imagenes | reintentar_imagenes | referentes/rutas.py:617 |
| GET | /<int:rid>/usar_en_sprint | usar_en_sprint | referentes/rutas.py:627 |
| POST | /personas | persona_crear | sprints/rutas.py:148 |
| POST | /personas/<int:pid> | persona_editar | sprints/rutas.py:165 |
| POST | /personas/<int:pid>/conciencia | persona_conciencia | sprints/rutas.py:180 |
| POST | /personas/<int:pid>/archivar | persona_archivar | sprints/rutas.py:211 |
| POST | /personas/sugerir | personas_sugerir | sprints/rutas.py:217 |
| POST | /temporadas | temporada_crear | sprints/rutas.py:232 |
| POST | /temporadas/<int:tid> | temporada_editar | sprints/rutas.py:244 |
| POST | /temporadas/<int:tid>/archivar | temporada_archivar | sprints/rutas.py:262 |
| POST | /temporadas/adoptar | temporada_adoptar | sprints/rutas.py:268 |
| POST | /temporadas/pais | calendario_pais | sprints/rutas.py:279 |
| GET | /<int:sid>/campanas/<int:cid>/panel | campana_panel | sprints/rutas.py:503 |
| GET | /<int:sid>/campanas/<int:cid>/piezas | campana_piezas | sprints/rutas.py:545 |
| GET | /<int:sid>/campanas/<int:cid>/sugeridos | campana_sugeridos | sprints/rutas.py:554 |
| POST | /<int:sid>/campanas/<int:cid>/campo | campana_campo | sprints/rutas.py:579 |
| POST | /nuevo | crear | sprints/rutas.py:690 |
| GET | /<int:sid> | ver | sprints/rutas.py:724 |
| GET | /<int:sid>/progreso | progreso_json | sprints/rutas.py:748 |
| POST | /<int:sid>/campo | sprint_campo | sprints/rutas.py:758 |
| GET | /<int:sid>/campanas/<int:cid>/tarjeta | campana_tarjeta | sprints/rutas.py:778 |
| POST | /<int:sid>/listo | marcar_listo | sprints/rutas.py:788 |
| POST | /<int:sid>/archivar | archivar | sprints/rutas.py:810 |
| POST | /<int:sid>/eliminar | eliminar | sprints/rutas.py:819 |
| POST | /<int:sid>/campanas | campana_agregar | sprints/rutas.py:841 |
| POST | /<int:sid>/campanas/<int:cid> | campana_editar | sprints/rutas.py:872 |
| POST | /<int:sid>/campanas/<int:cid>/eliminar | campana_eliminar | sprints/rutas.py:886 |
| GET | /<int:sid>/campanas/<int:cid> | campana_ver | sprints/rutas.py:904 |
| POST | /<int:sid>/campanas/<int:cid>/referencias | referencias_subir | sprints/rutas.py:943 |
| POST | /<int:sid>/campanas/<int:cid>/referencias/catalogo | referencias_catalogo | sprints/rutas.py:987 |
| POST | /<int:sid>/campanas/<int:cid>/referencias/reutilizar | referencias_reutilizar | sprints/rutas.py:1019 |
| POST | /campanas/<int:cid>/referencias_biblioteca | campana_referencias_biblioteca | sprints/rutas.py:1031 |
| POST | /campanas/<int:cid>/sugerir_ia | campana_sugerir_ia | sprints/rutas.py:1065 |
| GET | /<int:sid>/campanas/<int:cid>/referencias/estado | referencias_estado | sprints/rutas.py:1085 |
| POST | /referencias/<int:rid> | referencia_editar | sprints/rutas.py:1093 |
| POST | /referencias/<int:rid>/quitar | referencia_quitar | sprints/rutas.py:1138 |
| POST | /referencias/<int:rid>/reanalizar | referencia_reanalizar | sprints/rutas.py:1148 |
| GET | /<int:sid>/campanas/<int:cid>/ideas | campana_ideas | sprints/rutas.py:1174 |
| POST | /<int:sid>/campanas/<int:cid>/ideas/proponer | ideas_proponer | sprints/rutas.py:1187 |
| POST | /<int:sid>/campanas/<int:cid>/ideas/aprobar_todas | ideas_aprobar_todas | sprints/rutas.py:1213 |
| POST | /ideas/<int:cp_id> | idea_editar | sprints/rutas.py:1232 |
| POST | /ideas/<int:cp_id>/aprobar | idea_aprobar | sprints/rutas.py:1268 |
| POST | /ideas/<int:cp_id>/reescribir | idea_reescribir | sprints/rutas.py:1281 |
| POST | /ideas/<int:cp_id>/angulo | idea_angulo | sprints/rutas.py:1304 |
| POST | /ideas/<int:cp_id>/descartar | idea_descartar | sprints/rutas.py:1325 |
| POST | /ideas/<int:cp_id>/otra | idea_otra | sprints/rutas.py:1343 |
| GET | /<int:sid>/lote/estimar | lote_estimar | sprints/rutas.py:1367 |
| POST | /<int:sid>/lote | lote | sprints/rutas.py:1378 |
| POST | /ideas/<int:cp_id>/reintentar | pieza_reintentar | sprints/rutas.py:1419 |
| POST | /ideas/<int:cp_id>/regenerar | pieza_regenerar | sprints/rutas.py:1436 |
| GET | /<int:sid>/revision | revision | sprints/rutas.py:1459 |
| POST | /ideas/<int:cp_id>/revision | pieza_revision | sprints/rutas.py:1468 |
| POST | /ideas/<int:cp_id>/qa | pieza_qa | sprints/rutas.py:1501 |
| POST | /<int:sid>/revision/aprobar_qa | revision_aprobar_qa | sprints/rutas.py:1525 |
| POST | /<int:sid>/cerrar | cerrar | sprints/rutas.py:1535 |
| POST | /<int:sid>/reabrir | reabrir | sprints/rutas.py:1548 |
| POST | /<int:sid>/entrega/zip | entrega_zip | sprints/rutas.py:1574 |


## Tablas declaradas

| Tabla | Dónde |
| --- | --- |
| producto | db.py:126 |
| concepto | db.py:147 |
| pieza | db.py:165 |
| edicion | db.py:191 |
| edicion_version | db.py:203 |
| material | db.py:213 |
| experimento | db.py:233 |
| experimento_pieza | db.py:258 |
| metrica_snapshot | db.py:280 |
| metrica_dia | db.py:301 |
| metrica_desglose | db.py:324 |
| evento | db.py:337 |
| propuesta | db.py:349 |
| tarea | db.py:359 |
| tienda | db.py:391 |
| triple_whale | db.py:404 |
| tw_anuncio_dia | db.py:425 |
| tw_tienda_dia | db.py:455 |
| tw_evaluacion | db.py:470 |
| tw_producto_dia | db.py:487 |
| pedido | db.py:500 |
| publicacion | db.py:516 |
| gasto | db.py:542 |
| referente_familia | db.py:563 |
| barrido | db.py:572 |
| referente | db.py:595 |
| kv | db.py:637 |
| alerta_descartada | db.py:649 |
| token_cuenta | db.py:662 |
| persona | db.py:676 |
| temporada | db.py:692 |
| sprint | db.py:705 |
| campana | db.py:723 |
| referencia | db.py:746 |
| campana_pieza | db.py:766 |
| sprint_evento | db.py:789 |
| estudio | db.py:803 |
| comentario | db.py:818 |
| avatar | db.py:834 |
| producto_nicho | db.py:867 |
| guion_prompt | db.py:891 |
| guion_mensaje | db.py:907 |
| guion_lote | db.py:923 |
| guion | db.py:937 |
| guion_video | db.py:948 |
| error_app | db.py:976 |


## Tareas declaradas

| Tipo | Función | Dónde |
| --- | --- | --- |
| audio_generar | ejecutar | tareas/audios.py:44 |
| cadena_elementos | ejecutar_elementos | tareas/cadena.py:188 |
| cadena_vigilar | ejecutar_vigilar | tareas/cadena.py:223 |
| cadena_unir | ejecutar_unir | tareas/cadena.py:233 |
| flowplus_director | ejecutar | tareas/director.py:62 |
| edicion_producir | ejecutar_producir | tareas/edicion.py:282 |
| edicion_proxy | ejecutar_proxy | tareas/edicion.py:340 |
| material_transcribir | ejecutar_transcribir | tareas/edicion.py:416 |
| editor_voz | ejecutar_voz | tareas/edicion.py:462 |
| materiales_limpiar | ejecutar_limpiar | tareas/edicion.py:511 |
| edicion_desde_clon | ejecutar_desde_clon | tareas/edicion.py:517 |
| material_de_pieza | ejecutar_material_de_pieza | tareas/edicion.py:529 |
| exp_lanzar | exp_lanzar | tareas/experimentos.py:68 |
| exp_refrescar | exp_refrescar | tareas/experimentos.py:76 |
| exp_detalle | exp_detalle | tareas/experimentos.py:97 |
| exp_refrescar_todos | exp_refrescar_todos | tareas/experimentos.py:125 |
| exp_decidir_todos | exp_decidir_todos | tareas/experimentos.py:137 |
| exp_decidir | exp_decidir | tareas/experimentos.py:531 |
| exp_avanzar_todos | exp_avanzar_todos | tareas/experimentos.py:582 |
| final_guion | ejecutar_guion | tareas/final_edition.py:45 |
| final_producir | ejecutar_producir | tareas/final_edition.py:56 |
| flowplus_imagen | ejecutar_imagen | tareas/flowplus.py:358 |
| flowplus_video | ejecutar_video | tareas/flowplus.py:432 |
| flowplus_recuperar | recuperar_video | tareas/flowplus.py:506 |
| hablado_voz | ejecutar | tareas/hablado.py:26 |
| nicho_inv_consultas | ejecutar_consultas | tareas/investigacion.py:288 |
| nicho_inv_buscar | ejecutar_buscar | tareas/investigacion.py:329 |
| nicho_inv_seleccionar | ejecutar_seleccionar | tareas/investigacion.py:388 |
| salidas_limpiar | ejecutar_salidas_limpiar | tareas/mantenimiento.py:122 |
| cola_limpiar | ejecutar_cola_limpiar | tareas/mantenimiento.py:128 |
| db_respaldar | ejecutar_db_respaldar | tareas/mantenimiento.py:134 |
| errores_limpiar | ejecutar_errores_limpiar | tareas/mantenimiento.py:140 |
| meta_publicar | publicar | tareas/meta.py:82 |
| meta_refrescar | refrescar | tareas/meta.py:195 |
| musica_generar | ejecutar | tareas/musica.py:25 |
| nicho_generar_avatares | ejecutar_generar | tareas/nicho.py:86 |
| nicho_recolectar | ejecutar_recolectar | tareas/nicho.py:287 |
| nicho_completar_avatares | ejecutar_completar | tareas/nicho.py:382 |
| organico_publicar | publicar | tareas/organico.py:75 |
| sprint_analizar_referencia | ejecutar_analizar | tareas/sprints.py:82 |
| sprint_sugerir_personas | ejecutar_sugerir | tareas/sprints.py:105 |
| sprint_referencia_link | ejecutar_link | tareas/sprints.py:120 |
| sprint_reescribir_idea | ejecutar_reescribir_idea | tareas/sprints.py:157 |
| sprint_proponer_ideas | ejecutar_proponer_ideas | tareas/sprints.py:179 |
| referentes_sugerir_ia | ejecutar_sugerir_biblioteca | tareas/sprints.py:218 |
| sprint_qa_pieza | ejecutar_qa_pieza | tareas/sprints.py:300 |
| sprint_qa_pendientes | ejecutar_qa_pendientes | tareas/sprints.py:403 |
| sprint_empaquetar | ejecutar_empaquetar | tareas/sprints.py:444 |
| swap_generar | ejecutar | tareas/swap.py:167 |
| tienda_sync_productos | tienda_sync_productos | tareas/tiendas.py:179 |
| tienda_sync_pedidos | tienda_sync_pedidos | tareas/tiendas.py:250 |
| catalogo_importar | catalogo_importar | tareas/tiendas.py:290 |
| producto_vincular | producto_vincular | tareas/tiendas.py:341 |
| tienda_sync_productos_todas | tienda_sync_productos_todas | tareas/tiendas.py:380 |
| tienda_sync_pedidos_todas | tienda_sync_pedidos_todas | tareas/tiendas.py:402 |
| voz_propia_crear | ejecutar | tareas/voces_propias.py:27 |


## Cómo regenerarlo

`python3 mapa_codigo_generar.py` lee las fuentes locales con AST. La publicación del artifact del mapa corresponde a Claude.

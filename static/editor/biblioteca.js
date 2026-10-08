// Biblioteca del editor (capa 4b, Task 6): el panel de la izquierda (en el
// celular, la hoja que sube desde abajo) con seis pestañas:
//
// - Medios: «Subir» (varios archivos; cada uno con su barra y, si falla, su
//   error en llano debajo), los videos e imágenes del proyecto y, debajo,
//   «Videos de Crear» (las piezas listas; la que todavía no es material se
//   prepara al tocar «+» — gratis — y se agrega sola cuando está). Capa 5b
//   (D12): «+» sobre una imagen abre un menú chico — «Como clip del video»
//   (una foto en la fila del video) o «Encima del video» (la capa de
//   siempre); arrastrarla a la fila del video la pone como foto, a otra fila,
//   encima. Una imagen sin copia liviana la pide como un video (gratis).
// - Audio: «Subir audio» y los audios del proyecto (subidos, de Mi música y,
//   capa 5a, las grabaciones, las voces con IA y las locuciones de Crear ›
//   Audios), con «Escuchar» y «+» (desde el cabezal: una voz como voz, lo
//   demás como música — escala.rolDeMaterial). Arriba, en
//   `zona("audio")`, la voz en off de voz_panel.js (capa 5a: voz con IA y
//   grabar con el micrófono).
// - Texto: cuatro muestras (Título, Subtítulo, Precio, Llamado) con su estilo;
//   tocar una la pone en el cabezal, la deja elegida y pide el foco para su
//   texto (editor.enfocarTexto: el panel de propiedades lo atiende). Capa 5c
//   (D12.1): debajo, «Para vender» — seis plantillas (OFERTA, NUEVO, -50 %,
//   ENVÍO GRATIS…) que entran igual, escritas en su fuente y con su fondo.
// - Stickers (capa 5c, D11 y D12.2): una cuadrícula por sección — flechas,
//   marcas a mano y formas (los 20 PNG blancos de la casa, sobre un fondo
//   oscuro) y, solo si la fuente de emojis está, los emojis de anuncio —.
//   Tocar un sticker pide al servidor su material (gratis: la primera vez que
//   se usa en el proyecto lo sube; ruta `agregar_sticker`) y lo agrega como
//   una capa de imagen del color de su ficha, que «Editar» cambia; tocar un
//   emoji agrega un texto con ese emoji solo. Con el mouse, los tres también
//   se arrastran a la línea de tiempo. El pie del panel de emojis trae la
//   atribución de Twemoji (CC-BY 4.0), que su licencia exige.
// - Subtítulos (capa 5a): la llena subtitulos_panel.js en la zona que da
//   `zona("subtitulos")`; la biblioteca solo la muestra.
// - Transiciones: las cinco que el render hace; tocar una la pone (500 ms) en
//   el video elegido o en el corte más cercano al cabezal.
//
// `zona(panel)` es el lugar (un div al principio del panel, debajo de su
// título) donde otro módulo pone lo suyo sin tocar el resto del panel, y
// `mostrar(panel)` muestra ese panel (la página, además, marca la pestaña).
//
// «+» (o tocar un texto o una transición) agrega en el cabezal; con el mouse,
// cualquier cosa se arrastra a la línea de tiempo (LineaTiempo.puntoEn dice
// qué hay bajo el puntero y .resaltar lo marca). Con el dedo no se arrastra:
// en el celular la hoja tapa la línea de tiempo, y deslizar mueve la lista.
// Qué operación pide cada cosa lo decide escala.pedidoAgregar (puro, probado
// en Node); todo material entra a la vista previa (editor.agregarMateriales)
// ANTES de operar. Los videos y audios nuevos se preparan en el servidor
// (copia liviana, tira, picos: gratis): se pregunta cada 3 s, hasta 5 min,
// y lo que llega se le pasa a la vista previa, que lo cambia al pausar.
//
// Capa 4c: «Borrar» (con confirmación) en cada archivo subido o video de
// Crear preparado de «Tus archivos» y en cada audio subido — gratis; el
// servidor se niega si alguna edición lo usa, y la cuota descuenta.
//
// Solo toca el DOM de su panel, la línea de tiempo por puntoEn/resaltar y la
// edición por `editor`. No hace nada al importarse (lo prueba Node).
import { materialesUsados } from "./avisos_carga.js";
import {
  avisoTransicion, DURACION_TRANSICION_MS, efectoTransicion, nombreTransicion, pedidoAgregar, rolDeMaterial,
  textoEfectoTransicion,
} from "./escala.js";
import * as operaciones from "./operaciones.js";
import { TRANSICIONES } from "./operaciones.js";
import { mensajeSesion, sesionTerminada } from "./guardado.js";
import { evaluarRespuesta } from "./pendientes.js";
import { mensajeConflicto, textoSegundos } from "./propiedades_modelo.js";
import { plantillasTexto, seccionesStickers } from "./stickers_modelo.js";
import { t } from "./textos.js";
import { pistaPrincipal } from "./tiempo.js";
import { idiomaDeVoz } from "./voz_modelo.js";

// ---- Lo puro (lo prueba tests/js/biblioteca.test.mjs) ---------------------

// Espejo de final_edition/biblioteca.EXTENSIONES (tipo por extensión) y de
// materiales.LIMITES (bytes por tipo): tests/test_editor_js.py compara los dos.
export const EXTENSIONES_SUBIDA = {".mp4": "video", ".mov": "video", ".webm": "video", ".m4v": "video", ".jpg": "imagen", ".jpeg": "imagen", ".png": "imagen", ".webp": "imagen", ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio", ".ogg": "audio"};
export const LIMITES_SUBIDA = {"video": 209715200, "imagen": 20971520, "audio": 20971520};

export const INTERVALO_BIBLIOTECA_MS = 3000;
export const TOPE_ESPERA_MS = 5 * 60 * 1000;

// La frase entera por tipo (clave de textos.js): «El video pesa más de…».
const PESA = { video: "bib.pesa_video", imagen: "bib.pesa_imagen", audio: "bib.pesa_audio" };

export function tipoDeArchivo(nombre) {
  const m = /\.[^./\\]+$/.exec(String(nombre ?? ""));
  return (m && EXTENSIONES_SUBIDA[m[0].toLowerCase()]) || null;
}

// El `accept` de un <input type=file> para esos tipos.
export function aceptarPara(tipos) {
  return Object.entries(EXTENSIONES_SUBIDA).filter(([, tipo]) => tipos.includes(tipo)).map(([ext]) => ext).join(",");
}

// Lo que el servidor rechazaría igual, dicho antes de mandar el archivo.
export function revisarArchivo(nombre, bytes) {
  const tipo = tipoDeArchivo(nombre);
  if (!tipo) return t("bib.tipo_no");
  const tope = LIMITES_SUBIDA[tipo];
  if (Number(bytes) > tope) return t(PESA[tipo], { mb: Math.floor(tope / (1024 * 1024)) });
  return null;
}

// El error de una subida, en llano: el del servidor si lo dijo; si no, según
// qué pasó (`red`: no hubo respuesta; `redirigido`: llegó la página de entrar).
export function mensajeSubida({ status = 0, cuerpo = null, redirigido = false, red = false } = {}) {
  if (red) return t("bib.sin_conexion_subir");
  if (redirigido) return t("bib.sesion_subir");
  if (cuerpo && typeof cuerpo === "object" && typeof cuerpo.error === "string" && cuerpo.error) return cuerpo.error;
  if (status === 413) return t("bib.muy_grande");
  if (status >= 500) return t("bib.servidor");
  return t("bib.error_subir", { status });
}

// Qué va en cada lista: Medios (videos e imágenes, sin los que ya son una
// pieza de Crear: esos están en su sección), Audio (subidos, de Mi música y,
// capa 5a, las grabaciones, las voces con IA y las locuciones de Crear ›
// Audios; una voz de guion — sin nombre: un bloque por destino — no se agrega
// a mano) y las piezas de Crear.
const ORIGENES_AUDIO = ["subida", "musica", "grabacion", "locucion"];
const esAudioDeLista = (m) => m.tipo === "audio" && (ORIGENES_AUDIO.includes(m.origen) || (m.origen === "voz" && Boolean(m.nombre)));

export function repartir(bib) {
  const materiales = Array.isArray(bib?.materiales) ? bib.materiales.filter(Boolean) : [];
  const piezas = Array.isArray(bib?.piezas) ? bib.piezas.filter(Boolean) : [];
  const dePieza = new Set(piezas.map((p) => p.material_id).filter((id) => id !== null && id !== undefined));
  return {
    medios: materiales.filter((m) => (m.tipo === "video" || m.tipo === "imagen") && !dePieza.has(m.id)),
    audios: materiales.filter(esAudioDeLista),
    piezas,
  };
}

function medidas(m, formato) {
  if (Number(m?.ancho) > 0 && Number(m?.alto) > 0) return [Number(m.ancho), Number(m.alto)];
  const f = /^(\d+):(\d+)$/.exec(String(formato ?? ""));
  return f ? [Number(f[1]), Number(f[2])] : null;
}

// La miniatura de un material (o de una pieza que todavía no lo es, con su
// `formato`): la primera celda de la tira (una celda por segundo de fuente,
// así que el fondo mide `celdas × 100 %` de la caja), o el video mismo en el
// cuadro 0,1 s, o la imagen. `proporcion` es la de la caja que la contiene.
export function miniatura(m, { formato = null } = {}) {
  if (!m) return { clase: "audio" };
  if (m.tipo === "audio") return { clase: "audio" };
  const wh = medidas(m, formato);
  const forma = wh ? { proporcion: `${wh[0]} / ${wh[1]}`, vertical: wh[1] > wh[0] } : { proporcion: "16 / 9", vertical: false };
  if (m.tipo === "imagen") return { clase: "imagen", url: m.url_proxy || m.url, ...forma };   // capa 5b: la copia liviana (D13)
  if (m.tira_url && Number(m.duracion_ms) > 0) {
    const celdas = Math.max(1, Math.ceil(Number(m.duracion_ms) / 1000));
    return { clase: "tira", url: m.tira_url, tamano: `${celdas * 100}% 100%`, ...forma };
  }
  return { clase: "video", url: `${m.url_proxy || m.url}#t=0.1`, ...forma };
}

export function duracionTexto(ms) {
  if (!(Number(ms) > 0)) return "";
  const s = Math.max(1, Math.round(Number(ms) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// Lo que la vista previa espera del servidor (tarea edicion_proxy): la copia
// liviana de un video (su tira sale de la misma tarea) o de una imagen (capa
// 5b, D13: una foto subida a mitad de la sesión la pide sin recargar) y los
// picos de un audio. Espejo de vista_previa.pendientes.
export function faltaPreparar(m) {
  if (m?.tipo === "video" || m?.tipo === "imagen") return !m.url_proxy;
  if (m?.tipo === "audio") return m.picos === null || m.picos === undefined;
  return false;
}

// Revisión final de la capa 5b: el repintado que esperaba a que se cerrara el
// menú de una imagen (`pintarAlCerrar`), cuando lo cerró un toque AFUERA
// (pointerdown), espera a que ese toque termine y su click salga: en el
// pointerup (o pointercancel, si el dedo corrió la lista) se programa para
// después (`setTimeout(…, 0)`). Si no, la lista nueva reemplazaba la tarjeta
// bajo el dedo y el toque no llegaba a nada. `fn` corre una sola vez.
export function despuesDelToque(doc, fn, programar = (f, ms) => setTimeout(f, ms)) {
  let hecho = false;
  const listo = () => {
    doc.removeEventListener("pointerup", listo, true);
    doc.removeEventListener("pointercancel", listo, true);
    programar(() => {
      if (hecho) return;
      hecho = true;
      fn();
    }, 0);
  };
  doc.addEventListener("pointerup", listo, true);
  doc.addEventListener("pointercancel", listo, true);
}

// Capa 5b (D12): «+» sobre una imagen pregunta cómo entra — como un clip más
// del video (una foto en la fila del video, después del clip del cabezal) o
// encima del video (la capa de imagen de siempre). `como` va tal cual a
// escala.pedidoAgregar. En una edición de imagen (la principal no es un
// video, revisión final) solo queda «Encima»: `_clic` la agrega sin menú.
export function opcionesImagen(doc = null) {
  const encima = { como: "capa", texto: t("bib.encima") };
  if (doc && pistaPrincipal(doc)?.tipo !== "video") return [encima];
  return [{ como: "clip", texto: t("bib.como_clip") }, encima];
}

// Lo que se dice al agregar una foto al video: cuánto dura y dónde se cambia.
export function textoFotoAgregada(duracionMs) {
  return t("bib.foto_agregada", { duracion: textoSegundos(duracionMs) });
}

// Lo que se dice después de poner una transición desde la biblioteca
// (`pedido`: ["ponerTransicion", clipId, tipo, ms]; `cosa`: {transicion,
// nombre}): {texto, error}. Capa 5b (D9): lo que le pasó de verdad a esa
// unión entre el documento de antes y el de después — «junta los dos clips y
// el video quedó X más corto», o que quedó en corte o más corta —; si no hay
// nada de eso, lo de antes (avisoTransicion, o «quedó en la unión»). Elegir
// «Corte» a propósito nunca se avisa como un problema.
export function mensajeTransicion(antes, despues, pedido, cosa) {
  if (cosa?.transicion === "corte") return { texto: t("bib.union_corte"), error: false };
  const efecto = efectoTransicion(antes, despues, pedido[1]);
  if (efecto) return { texto: textoEfectoTransicion(efecto, cosa?.nombre ?? ""), error: efecto.tipo !== "junta" };
  const aviso = avisoTransicion(despues, pedido[1], pedido[2], pedido[3] ?? DURACION_TRANSICION_MS);
  return { texto: aviso ?? t("bib.en_union", { nombre: cosa?.nombre ?? "" }), error: Boolean(aviso) };
}

// Lo que se ve en las listas (cómo va la carga, los materiales, las piezas y
// cuáles se están preparando), escrito para comparar: si al preguntar por las
// piezas (cada 3 s mientras una se prepara) sale igual, no se repinta nada —
// repintar recarga las miniaturas, se lleva el foco y se traga un clic a medias.
export function firmaListado({ carga = null, datos = null, preparando = [] } = {}) {
  return JSON.stringify([carga, datos?.materiales ?? [], datos?.piezas ?? [], [...preparando].map(String).sort()]);
}

export function urlPieza(plantilla, cfId) {
  return String(plantilla).replace("__CF__", encodeURIComponent(cfId));
}

// Capa 4c: lo que «Borrar» puede quitar — lo subido y los videos de Crear ya
// preparados (espejo de final_edition/biblioteca.ORIGENES_BORRABLES). Nunca
// el logo, una voz de guion ni una canción de Mi música: la creada tiene
// origen «musica» y la subida trae `mi_musica` (vista_previa.material_para);
// las dos se borran en Crear › Mi música. Capa 5a (Task 6): una grabación del
// micrófono SÍ se borra desde aquí (es solo suya, como una subida).
export const ORIGENES_BORRABLES = ["subida", "crear", "grabacion"];

export function puedeBorrarse(m) {
  return Boolean(m) && ORIGENES_BORRABLES.includes(m.origen) && !m.mi_musica;
}

export function urlBorrar(plantilla, id) {
  return String(plantilla).replace("__ID__", encodeURIComponent(String(id)));
}

// Capa 5c (D11): la ruta que vuelve un sticker material del proyecto
// (`editor.agregar_sticker`, gratis) cuelga de la de la biblioteca:
// <biblioteca>/sticker/<id>. El id sale del manifiesto, pero se codifica igual.
export function urlSticker(biblioteca, id) {
  return `${String(biblioteca)}/sticker/${encodeURIComponent(String(id))}`;
}

// Lo que se dice cuando un sticker no se pudo agregar: el motivo que dio el
// servidor (sin el punto final, que va dentro de un paréntesis); si no dijo
// nada —un 500 con una página HTML cuando R2 falla—, el número del error; sin
// red, «sin conexión»; con la sesión vencida, eso (la edición pendiente no se
// pierde: se dice que recargue).
export function mensajeSticker({ status = 0, cuerpo = null, redirigido = false, red = false } = {}) {
  if (redirigido) return mensajeSesion();
  let motivo;
  if (red) motivo = t("bib.sticker_sin_conexion");
  else if (cuerpo && typeof cuerpo === "object" && typeof cuerpo.error === "string" && cuerpo.error.trim()) {
    motivo = cuerpo.error.trim().replace(/[.\s]+$/, "");
  } else motivo = t("bib.sticker_error_http", { status });
  return t("bib.sticker_error", { error: motivo });
}

// Por qué no se ofrece borrar ese material ahora (o null): el servidor solo
// ve lo guardado, así que lo que usa la edición abierta se mira aquí.
export function motivoNoBorrar(m, doc) {
  if (!puedeBorrarse(m)) return t("bib.no_se_borra");
  if (materialesUsados(doc).has(Number(m.id))) return t("bib.en_uso_esta");
  return null;
}

// Los datos de la biblioteca sin ese material (uno NUEVO): sale de la lista
// y la pieza de Crear que lo tenía queda sin material (se puede volver a
// preparar, gratis).
export function quitarMaterial(datos, id) {
  return {
    materiales: (datos?.materiales ?? []).filter((m) => m.id !== id),
    piezas: (datos?.piezas ?? []).map((p) => (p.material_id === id ? { ...p, material_id: null } : p)),
  };
}

// Las muestras de texto: los presets de operaciones.agregarTexto (con su
// nombre en el idioma de la página: función, no constante, porque ningún
// módulo llama a t() al cargarse).
export function textosBiblioteca() {
  return [
    { preset: "titulo", nombre: t("bib.texto_titulo") },
    { preset: "subtitulo", nombre: t("bib.texto_subtitulo") },
    { preset: "precio", nombre: t("clip.precio") },
    { preset: "llamado", nombre: t("bib.texto_llamado") },
  ];
}

const DESCRIPCIONES_TRANSICION = {
  corte: "bib.tr_corte",
  fundido: "bib.tr_fundido",
  deslizar: "bib.tr_deslizar",
  zoom: "bib.tr_zoom",
  desenfoque: "bib.tr_desenfoque",
};

export function transicionesBiblioteca() {
  return TRANSICIONES.map((tipo) => ({
    tipo, nombre: nombreTransicion(tipo), descripcion: DESCRIPCIONES_TRANSICION[tipo] ? t(DESCRIPCIONES_TRANSICION[tipo]) : "",
  }));
}

// ---- El panel (DOM) ---------------------------------------------------------

const SVG = "http://www.w3.org/2000/svg";
const ARRASTRE_MIN_PX = 5;
const COLOR_RE = /^#[0-9a-fA-F]{3,8}$/;
// Iconos (viewBox 24×24, trazo): texto fijo de este módulo, sin datos de nadie.
const ICONOS = {
  subir: '<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>',
  mas: '<path d="M12 5v14M5 12h14"/>',
  video: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5z"/>',
  imagen: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M20 16l-4.5-4.5L7 19"/>',
  nota: '<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
  texto: '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
  transicion: '<path d="M4 6l8 6-8 6zM20 6l-8 6 8 6z"/>',
  play: '<path d="M8 5l11 7-11 7z"/>',
  pausa: '<path d="M8 5v14M16 5v14"/>',
  cerrar: '<path d="M6 6l12 12M18 6L6 18"/>',
  borrar: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  capas: '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4M4 16l8 4 8-4"/>',
};
// El icono de cada opción del menú de una imagen (opcionesImagen).
const ICONO_COMO = { clip: "video", capa: "capas" };
const MENU_COMO_MARGEN_PX = 8;
const ICONO_DE = { video: "video", pieza: "video", imagen: "imagen", sticker: "imagen", audio: "nota", texto: "texto", transicion: "transicion" };
// El título de un panel cuando la página no trae su pestaña (normalmente lo da el nombre de la pestaña).
const TITULO_PANEL = { stickers: "bib.stickers" };
const ESTADO_SUBIDA = {
  espera: () => t("bib.en_espera"),
  subiendo: (s) => t("bib.subiendo", { n: Math.round(s.progreso * 100) }),
  procesando: () => t("guardado.guardando"),
  lista: () => t("bib.listo"),
  error: () => t("bib.no_subio"),
};

function el(tag, clase, padre, texto) {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (texto !== undefined) n.textContent = texto;
  if (padre) padre.append(n);
  return n;
}

function icono(nombre, tam = 16) {
  const s = document.createElementNS(SVG, "svg");
  for (const [k, v] of Object.entries({ class: "ed-bib-icono", viewBox: "0 0 24 24", width: String(tam), height: String(tam),
    "aria-hidden": "true", focusable: "false", fill: "none", stroke: "currentColor", "stroke-width": "1.8",
    "stroke-linecap": "round", "stroke-linejoin": "round" })) s.setAttribute(k, v);
  s.innerHTML = ICONOS[nombre] ?? ICONOS.video;
  return s;
}

const cssUrl = (url) => `url("${String(url).replace(/["\\\n]/g, encodeURIComponent)}")`;
const tieneArchivos = (e) => [...(e.dataTransfer?.types ?? [])].includes("Files");

// El nombre de un material en la biblioteca: el suyo, o uno según qué es (el
// logo del proyecto tiene origen «marca», el de insumos.logo).
export function nombreDe(m) {
  if (m?.nombre) return String(m.nombre);
  if (m?.tipo === "imagen") return t(m.origen === "marca" ? "bib.logo" : "clip.imagen");
  if (m?.tipo === "audio") {
    if (m.origen === "musica") return t("bib.cancion");
    if (m.origen === "grabacion") return t("fila.grabacion");
    return t(rolDeMaterial(m) === "voz" ? "fila.voz" : "fila.audio");
  }
  return t(m?.origen === "crear" ? "bib.video_crear" : "fila.video");
}

// Lo que dice debajo del nombre de un audio: su duración y de dónde viene.
const DE_DONDE_AUDIO = { grabacion: "fila.grabacion", voz: "voz.titulo_ia", locucion: "bib.locucion", musica: "bib.mi_musica" };

export function detalleAudio(m) {
  const de = m?.mi_musica ? "bib.mi_musica" : DE_DONDE_AUDIO[m?.origen] ?? "bib.subido";
  return [duracionTexto(m?.duracion_ms), t(de)].filter(Boolean).join(" · ");
}

// El «+» de un audio: como voz o como música (rolDeMaterial).
export function etiquetaMas(m, nombre) {
  return t(rolDeMaterial(m) === "voz" ? "bib.agregar_voz" : "bib.agregar_musica", { nombre });
}

export class Biblioteca {
  // `contenedor`: #ed-panel-biblioteca (la caja que corre hacia abajo);
  // `pestanas`: la lista de pestañas (la página ya marca la elegida; aquí se
  // muestra su panel); `urls`: las de datos-editor; `linea`: la LineaTiempo;
  // `nombresIdioma`: {es: "Español", …} (el aviso de una voz en otro idioma).
  // Capa 5c: `stickers` (datos.stickers: los 20 de la casa con su URL) y
  // `tabla` (config.tipografia: sin su fuente de emojis no hay emojis).
  constructor({ contenedor, pestanas, urls, editor, linea, nombresIdioma = {}, stickers = [], tabla = null }) {
    this.contenedor = contenedor;
    this.nombresIdioma = nombresIdioma ?? {};
    this.stickers = Array.isArray(stickers) ? stickers : [];
    this.tabla = tabla ?? null;
    this.pidiendoSticker = new Set();   // id de sticker cuyo material se está pidiendo: otro toque no suma otro
    this.pestanas = pestanas;
    this.urls = urls ?? {};
    this.editor = editor;
    this.linea = linea;
    this.datos = { materiales: [], piezas: [] };
    this.carga = "cargando";            // "cargando" | "lista" | "error"
    this.cosas = new Map();             // data-clave -> lo que agrega (la `cosa` de pedidoAgregar) + su nombre
    this.subidas = [];                  // en espera de subir, una por archivo
    this.subiendo = false;
    this.preparando = new Map();        // cf_id -> {desde, pedido: {punto} | null}; pedido = agregarla al tenerla
    this.esperando = new Map();         // material_id -> desde: su copia liviana (video) o sus picos (audio)
    this.pedidosPreparar = new Set();   // material_id ya pedido al servidor (`preparar=`): se pide una vez
    this.borrados = new Set();          // material_id borrado desde aquí: no vuelve a la lista
    this.relojPiezas = null;
    this.relojMateriales = null;
    this.arrastre = null;               // {clave, cosa, pointerId, x0, y0, x, y, activo, fantasma, origen, cuadro}
    this.pintarAlSoltar = false;        // llegó algo a mitad de un arrastre: las listas se pintan al soltar
    this.pintarAlCerrar = false;        // llegó algo con el menú de una imagen abierto: se pintan al cerrarlo
    this.suprimirClic = false;          // el clic que el navegador manda tras soltar un arrastre
    this.escucha = null;                // {clave, audio}
    this.relojMensaje = null;
    this.observador = null;
    this.como = null;                   // el menú «¿Cómo agregar?» de una imagen: {clave, cosa, boton, menu}
    this.alTocarFueraComo = (e) => {
      if (this.como && !this.como.menu.contains(e.target) && !this.como.boton.contains(e.target)) {
        this._cerrarComo({ porToque: true });
      }
    };
    this.alTeclaComo = (e) => {
      if (e.key !== "Escape" || !this.como) return;
      e.preventDefault();
      e.stopPropagation();                // no cierra la hoja del celular: solo el menú
      this._cerrarComo({ devolverFoco: true });
    };
    this.alMoverComo = () => this._cerrarComo();
    this.alMover = (e) => this._moverArrastre(e);
    this.alSoltar = (e) => this._soltarArrastre(e);
    this.alCancelar = (e) => {
      if (this.arrastre && e.pointerId === this.arrastre.pointerId) this._terminarArrastre();
    };
    this.alTecla = (e) => {
      if (e.key !== "Escape" || !this.arrastre?.activo) return;
      e.preventDefault();
      e.stopPropagation();                // no cierra la hoja del celular
      this._terminarArrastre();
    };
    this._construir();
    this.mostrar(pestanas.querySelector('[aria-selected="true"]')?.dataset.panel ?? "medios");
    pestanas.addEventListener("click", (e) => {
      const b = e.target.closest("[data-panel]");
      if (b) this.mostrar(b.dataset.panel);
    });
    editor.escuchar((que) => {
      if (que === "documento") this._pintarMarca();
      else if (que === "materiales") this._sumarDeLaVista();
    });
    this._pintarMarca();
    this.cargar();
  }

  // ---- Armar el panel (una vez) ----

  _construir() {
    const c = this.contenedor;
    c.replaceChildren();
    c.classList.add("ed-bib");
    this.mensaje = el("p", "editor-aviso ed-bib-mensaje", c);
    this.mensaje.setAttribute("aria-live", "polite");
    this.mensaje.hidden = true;
    this.paneles = {};
    for (const panel of ["medios", "audio", "texto", "stickers", "subtitulos", "transiciones"]) {
      const s = el("section", "ed-bib-panel", c);
      s.dataset.panel = panel;
      s.hidden = true;
      // en la columna las pestañas van solo con el icono: el panel dice cuál es
      const nombre = this.pestanas.querySelector(`[data-panel="${panel}"]`)?.textContent.trim();
      el("h2", "ed-titulo ed-bib-cabeza", s, nombre || (TITULO_PANEL[panel] ? t(TITULO_PANEL[panel]) : ""));
      this.paneles[panel] = s;
    }
    this.listaSubidas = {};
    this._construirMedios();
    this._construirAudio();
    this._construirTextos();
    this._construirStickers();
    this._construirTransiciones();
    // escuchas una sola vez (delegación): repintar las listas no suma escuchas
    c.addEventListener("click", (e) => this._clic(e));
    c.addEventListener("pointerdown", (e) => this._abajo(e));
    c.addEventListener("dragstart", (e) => e.preventDefault());    // las miniaturas no se arrastran solas
    // archivos de la computadora: soltarlos en cualquier lugar de la página los
    // sube (y así el navegador no abre el archivo en lugar del editor)
    c.addEventListener("dragover", (e) => {
      if (tieneArchivos(e)) c.classList.add("ed-bib-soltando");
    });
    c.addEventListener("dragleave", (e) => {
      if (!c.contains(e.relatedTarget)) c.classList.remove("ed-bib-soltando");
    });
    window.addEventListener("dragover", (e) => {
      if (tieneArchivos(e)) e.preventDefault();
    });
    window.addEventListener("drop", (e) => {
      if (!tieneArchivos(e)) return;
      e.preventDefault();
      c.classList.remove("ed-bib-soltando");
      this._soltarArchivos([...e.dataTransfer.files]);
    });
  }

  _barraSubir(panel, texto, tipos) {
    const p = this.paneles[panel];
    const barra = el("div", "ed-bib-barra", p);
    const boton = el("button", "btn-sm ed-bib-subir", barra);
    boton.type = "button";
    boton.dataset.subir = panel;
    boton.append(icono("subir", 16), el("span", "", null, texto));
    const entrada = el("input", "", barra);
    entrada.type = "file";
    entrada.multiple = true;
    entrada.hidden = true;
    entrada.accept = aceptarPara(tipos);
    entrada.dataset.entrada = panel;
    entrada.addEventListener("change", () => {
      const archivos = [...(entrada.files ?? [])];
      entrada.value = "";
      this.subir(archivos, panel);
    });
    el("span", "ed-bib-ayuda ed-bib-ayuda-arrastre", barra, t("bib.arrastra"));
    this.listaSubidas[panel] = el("ul", "ed-bib-subidas", p);
  }

  _construirMedios() {
    const p = this.paneles.medios;
    this._barraSubir("medios", t("bib.subir"), ["video", "imagen"]);
    el("h3", "ed-bib-titulo", p, t("bib.tus_archivos"));
    this.grillaMedios = el("div", "ed-bib-grilla", p);
    el("h3", "ed-bib-titulo", p, t("bib.videos_crear"));
    this.grillaPiezas = el("div", "ed-bib-grilla", p);
  }

  _construirAudio() {
    const p = this.paneles.audio;
    this._barraSubir("audio", t("bib.subir_audio"), ["audio"]);
    el("h3", "ed-bib-titulo", p, t("bib.audios"));
    this.listaAudios = el("div", "ed-bib-audios", p);
  }

  _construirTextos() {
    const p = this.paneles.texto;
    el("p", "ed-bib-ayuda", p, t("bib.ayuda_textos"));
    const g = el("div", "ed-bib-textos", p);
    for (const muestra of textosBiblioteca()) this._botonTexto(g, muestra.preset, muestra.nombre);
    // capa 5c (D12.1): las plantillas para vender, con el mismo estilo de muestra
    el("h3", "ed-bib-titulo", p, t("bib.para_vender"));
    const v = el("div", "ed-bib-textos ed-bib-plantillas", p);
    for (const plantilla of plantillasTexto()) this._botonTexto(v, plantilla.preset, plantilla.texto);
  }

  // Una muestra de texto (o plantilla): un botón escrito con el estilo con que
  // entra (`ed-bib-texto-<preset>`, en el CSS de la página).
  _botonTexto(grilla, preset, nombre) {
    const clave = `t:${preset}`;
    this.cosas.set(clave, { tipo: "texto", preset, nombre });
    const b = el("button", `ed-bib-texto ed-bib-texto-${preset}`, grilla);
    b.type = "button";
    b.dataset.clave = clave;
    b.dataset.arrastrable = "";
    b.setAttribute("aria-label", t("bib.agregar_texto", { nombre }));
    el("span", "ed-bib-texto-muestra", b, nombre);
    return b;
  }

  // «Stickers» (capa 5c): una cuadrícula por sección, cada título justo antes
  // de la suya. Los stickers son blancos (se tiñen al agregarlos): sus
  // miniaturas van sobre un fondo oscuro. El pie con la atribución de Twemoji
  // sale siempre que sale la sección de emojis (la licencia lo exige).
  _construirStickers() {
    const p = this.paneles.stickers;
    const secciones = seccionesStickers(this.stickers, this.tabla);
    for (const { seccion, titulo, items } of secciones) {
      el("h3", "ed-bib-titulo", p, titulo);
      const g = el("div", "ed-stickers-cuadricula", p);
      g.dataset.seccion = seccion;
      for (const item of items) g.append(item.emoji === undefined ? this._botonSticker(item) : this._botonEmoji(item.emoji));
    }
    if (secciones.some((s) => s.seccion === "emojis")) el("p", "ed-bib-ayuda ed-stickers-atribucion", p, t("bib.atribucion_emoji"));
  }

  _botonSticker(item) {
    const clave = `s:${item.id}`;
    this.cosas.set(clave, { tipo: "sticker", sticker: item, nombre: item.nombre });
    const b = el("button", "ed-sticker");
    b.type = "button";
    b.dataset.clave = clave;
    b.dataset.arrastrable = "";
    b.title = item.nombre;
    b.setAttribute("aria-label", item.nombre);
    const img = el("img", "", b);
    img.alt = "";                                   // el nombre lo dice el botón
    img.loading = "lazy";
    img.decoding = "async";
    img.draggable = false;
    img.src = item.url;
    return b;
  }

  _botonEmoji(emoji) {
    const clave = `e:${emoji}`;
    this.cosas.set(clave, { tipo: "texto", preset: "emoji", literal: emoji, nombre: emoji });
    const b = el("button", "ed-sticker ed-sticker-emoji", null, emoji);
    b.type = "button";
    b.dataset.clave = clave;
    b.dataset.arrastrable = "";
    b.title = emoji;
    b.setAttribute("aria-label", emoji);
    return b;
  }

  _construirTransiciones() {
    const p = this.paneles.transiciones;
    el("p", "ed-bib-ayuda", p, t("bib.ayuda_transiciones"));
    const g = el("div", "ed-bib-transiciones", p);
    for (const tr of transicionesBiblioteca()) {
      const clave = `tr:${tr.tipo}`;
      this.cosas.set(clave, { tipo: "transicion", transicion: tr.tipo, nombre: tr.nombre });
      const b = el("button", "ed-bib-transicion", g);
      b.type = "button";
      b.dataset.clave = clave;
      b.dataset.arrastrable = "";
      b.setAttribute("aria-label", t("bib.transicion", { nombre: tr.nombre, descripcion: tr.descripcion }));
      const muestra = el("span", `ed-bib-tr-muestra ed-bib-tr-${tr.tipo}`, b);
      muestra.setAttribute("aria-hidden", "true");
      el("span", "ed-bib-tr-a", muestra);
      el("span", "ed-bib-tr-b", muestra);
      const txt = el("span", "ed-bib-tr-texto", b);
      el("span", "ed-bib-tr-nombre", txt, tr.nombre);
      el("span", "ed-bib-tr-desc", txt, tr.descripcion);
    }
  }

  // El lugar de otro módulo dentro de un panel (capa 5a: la pestaña
  // «Subtítulos», la voz en «Audio»): un div.ed-bib-zona al principio del
  // panel, debajo de su título, creado una vez. null si el panel no existe.
  // Ningún control de una zona lleva los data-* que esta clase atiende
  // (data-agregar, data-borrar, data-clave…): sus clics no son de aquí.
  zona(panel) {
    const s = this.paneles[panel];
    if (!s) return null;
    let z = s.querySelector(":scope > .ed-bib-zona");
    if (!z) {
      z = el("div", "ed-bib-zona");
      const cabeza = s.querySelector(":scope > .ed-bib-cabeza");
      if (cabeza) cabeza.after(z);
      else s.prepend(z);
    }
    return z;
  }

  mostrar(panel) {
    if (!this.paneles[panel]) return;
    this.panel = panel;
    for (const [k, s] of Object.entries(this.paneles)) s.hidden = k !== panel;
    const nombre = this.pestanas.querySelector(`[data-panel="${panel}"]`)?.textContent.trim();
    if (nombre) this.contenedor.setAttribute("aria-label", nombre);
    if (panel !== "audio") this._pararEscucha();
    if (panel !== "medios") this._cerrarComo();
  }

  // El color de marca de la edición, para la muestra «Precio».
  _pintarMarca() {
    const color = this.editor.doc()?.marca?.color;
    if (typeof color === "string" && COLOR_RE.test(color)) this.contenedor.style.setProperty("--ed-marca", color);
    else this.contenedor.style.removeProperty("--ed-marca");
  }

  _decir(texto, error = false) {
    clearTimeout(this.relojMensaje);
    this.mensaje.textContent = texto || "";
    this.mensaje.hidden = !texto;
    this.mensaje.classList.toggle("error", Boolean(texto) && error);
    if (texto) this.relojMensaje = setTimeout(() => this._decir(""), error ? 10000 : 5000);
  }

  // ---- Las listas (se repintan cuando llega algo) ----

  async cargar() {
    this.carga = "cargando";
    this._pintarListas();
    const { que, j } = await this._pedirJSON(this.urls.biblioteca);
    if (que !== "json" || !j || typeof j !== "object") {
      this.carga = "error";
      this._pintarListas();
      return;
    }
    this.datos = { materiales: Array.isArray(j.materiales) ? j.materiales : [], piezas: Array.isArray(j.piezas) ? j.piezas : [] };
    this.carga = "lista";
    // una pieza que ya se estaba preparando (otra pestaña): se sigue, sin agregarla sola
    for (const p of this.datos.piezas) {
      if (p.preparando && !p.material_id && !this.preparando.has(p.cf_id)) this.preparando.set(p.cf_id, { desde: Date.now(), pedido: null });
    }
    this._pintarListas();
    this._programarPiezas();
  }

  _material(id) {
    if (id === null || id === undefined) return null;
    return this.datos.materiales.find((m) => m.id === id) ?? null;
  }

  // Capa 5a: una voz o una grabación que otro panel acaba de poner en la
  // edición (voz_panel.js) entra a la lista sin recargar. Solo audios de la
  // lista que todavía no estaban, y nunca uno que se borró desde aquí (la vista
  // previa conserva sus materiales).
  _sumarDeLaVista() {
    if (this.carga !== "lista") return;
    let cambio = false;
    for (const m of Object.values(this.editor.materiales?.() ?? {})) {
      if (!m || this._material(m.id) || this.borrados.has(m.id) || !esAudioDeLista(m)) continue;
      const { palabras: _p, ...sinPalabras } = m;          // la lista no carga palabras
      this.datos.materiales = [sinPalabras, ...this.datos.materiales];
      cambio = true;
    }
    if (cambio) this._pintarListas();
  }

  // Suma (o reemplaza, por id) un material a la lista; true si cambió algo.
  _ponerMaterial(m) {
    const i = this.datos.materiales.findIndex((x) => x.id === m.id);
    if (i < 0) {
      this.datos.materiales = [m, ...this.datos.materiales];
      return true;
    }
    if (JSON.stringify(this.datos.materiales[i]) === JSON.stringify(m)) return false;
    this.datos.materiales = this.datos.materiales.map((x, k) => (k === i ? m : x));
    return true;
  }

  _pintarListas() {
    if (this.arrastre?.activo) {
      this.pintarAlSoltar = true;
      return;
    }
    if (this.como) {                      // el menú de una imagen está abierto: no se repinta bajo el dedo
      this.pintarAlCerrar = true;
      return;
    }
    this.pintarAlSoltar = false;
    this.pintarAlCerrar = false;
    for (const k of [...this.cosas.keys()]) if (k.startsWith("m:") || k.startsWith("p:")) this.cosas.delete(k);
    this.observador?.disconnect();
    if (this.carga !== "lista") {
      const estado = () => (this.carga === "error" ? this._errorCarga() : this._vacio(t("bib.cargando")));
      this.grillaMedios.replaceChildren(estado());
      this.grillaPiezas.replaceChildren();
      this.listaAudios.replaceChildren(estado());
      return;
    }
    const { medios, audios, piezas } = repartir(this.datos);
    this.grillaMedios.replaceChildren(...(medios.length ? medios.map((m) => this._itemMaterial(m))
      : [this._vacio(t("bib.vacio_medios"))]));
    this.grillaPiezas.replaceChildren(...(piezas.length ? piezas.map((p) => this._itemPieza(p))
      : [this._vacio(t("bib.vacio_piezas"))]));
    this.listaAudios.replaceChildren(...(audios.length ? audios.map((m) => this._filaAudio(m))
      : [this._vacio(t("bib.vacio_audios"))]));
  }

  _vacio(texto) {
    return el("p", "ed-bib-vacio", null, texto);
  }

  _errorCarga() {
    const n = el("div", "ed-bib-vacio");
    el("p", "", n, t("bib.error_carga"));
    const b = el("button", "btn-sm", n, t("bib.reintentar"));
    b.type = "button";
    b.dataset.reintentar = "";
    return n;
  }

  _botonMas(clave, etiqueta, desactivado = false) {
    const b = el("button", "ed-bib-mas");
    b.type = "button";
    b.dataset.agregar = clave;
    b.disabled = desactivado;
    b.title = t("bib.agregar");
    b.setAttribute("aria-label", etiqueta);
    b.append(icono("mas", 16));
    return b;
  }

  // «Borrar» (capa 4c): un botón con el tacho, solo en lo que se puede borrar.
  _botonBorrar(m, nombre) {
    const b = el("button", "ed-bib-borrar");
    b.type = "button";
    b.dataset.borrar = String(m.id);
    b.title = t("bib.borrar_titulo");
    b.setAttribute("aria-label", t("bib.borrar_nombre", { nombre }));
    b.append(icono("borrar", 14));
    return b;
  }

  // La miniatura dentro de su caja cuadrada (fondo oscuro, sin deformar).
  _mini(mini, duracion) {
    const caja = el("div", "ed-bib-mini");
    let dentro;
    if (mini.clase === "imagen") {
      dentro = el("img", "", caja);
      dentro.alt = "";
      dentro.loading = "lazy";
      dentro.decoding = "async";
      dentro.draggable = false;
      dentro.src = mini.url;
    } else if (mini.clase === "video") {
      dentro = el("video", "", caja);
      dentro.muted = true;
      dentro.preload = "metadata";
      dentro.playsInline = true;
      dentro.draggable = false;
      dentro.setAttribute("aria-hidden", "true");
      dentro.dataset.src = mini.url;        // se carga al verse (muchas piezas = muchos videos)
      this._observar(dentro);
    } else {
      // la tira: una caja con la forma del video, a lo ancho o a lo alto del cuadro
      dentro = el("div", `ed-bib-mini-tira ${mini.vertical ? "ed-bib-vertical" : "ed-bib-horizontal"}`, caja);
      dentro.style.backgroundImage = cssUrl(mini.url);
      dentro.style.backgroundSize = mini.tamano;
      dentro.style.aspectRatio = mini.proporcion;
    }
    // una imagen o un video llenan el cuadro sin deformarse (object-fit: contain): su forma real la sabe el navegador
    dentro.classList.add("ed-bib-mini-medio");
    if (duracion) el("span", "ed-bib-duracion", caja, duracion);
    return caja;
  }

  _observar(video) {
    const cargar = (v) => {
      if (v.dataset.src) v.src = v.dataset.src;
      delete v.dataset.src;
    };
    if (typeof IntersectionObserver !== "function") return cargar(video);
    if (!this.observador) {
      this.observador = new IntersectionObserver((vistos) => {
        for (const v of vistos) {
          if (!v.isIntersecting) continue;
          this.observador.unobserve(v.target);
          cargar(v.target);
        }
      }, { root: this.contenedor, rootMargin: "200px 0px" });
    }
    this.observador.observe(video);
  }

  _itemMaterial(m) {
    const clave = `m:${m.id}`;
    const nombre = nombreDe(m);
    this.cosas.set(clave, { tipo: m.tipo, material: m, nombre });
    const item = el("div", "ed-bib-item");
    item.dataset.clave = clave;
    item.dataset.arrastrable = "";
    item.title = nombre;
    const mini = this._mini(miniatura(m), m.tipo === "video" ? duracionTexto(m.duracion_ms) : "");
    const mas = this._botonMas(clave, t("bib.agregar_nombre", { nombre }));
    if (m.tipo === "imagen") {                     // capa 5b (D12): pregunta cómo entra
      mas.setAttribute("aria-haspopup", "dialog");
      mas.setAttribute("aria-expanded", "false");
    }
    mini.append(mas);
    if (puedeBorrarse(m) && this.urls.borrar_material) mini.append(this._botonBorrar(m, nombre));
    item.append(mini);
    el("span", "ed-bib-nombre", item, nombre);
    return item;
  }

  _itemPieza(p) {
    const clave = `p:${p.cf_id}`;
    const material = this._material(p.material_id);
    const nombre = p.nombre || t("bib.video_crear");
    this.cosas.set(clave, { tipo: "pieza", pieza: p, material, nombre });
    const preparando = !material && (this.preparando.has(p.cf_id) || Boolean(p.preparando));
    const item = el("div", `ed-bib-item${preparando ? " ed-bib-preparando" : ""}`);
    item.dataset.clave = clave;
    if (!preparando) item.dataset.arrastrable = "";
    item.title = nombre;
    const mini = this._mini(material ? miniatura(material) : miniatura({ tipo: "video", url: p.video_url }, { formato: p.formato }),
      material ? duracionTexto(material.duracion_ms) : "");
    if (preparando) el("span", "ed-bib-estado", mini, t("bib.preparando"));
    mini.append(this._botonMas(clave, preparando ? t("bib.se_prepara", { nombre }) : t("bib.agregar_nombre", { nombre }), preparando));
    item.append(mini);
    el("span", "ed-bib-nombre", item, nombre);
    return item;
  }

  _filaAudio(m) {
    const clave = `m:${m.id}`;
    const nombre = nombreDe(m);
    this.cosas.set(clave, { tipo: "audio", material: m, nombre });
    const fila = el("div", "ed-bib-audio");
    fila.dataset.clave = clave;
    fila.dataset.arrastrable = "";
    fila.title = nombre;
    el("span", "ed-bib-audio-icono", fila).append(icono("nota", 18));
    const txt = el("span", "ed-bib-audio-texto", fila);
    el("span", "ed-bib-nombre", txt, nombre);
    el("span", "ed-bib-audio-detalle", txt, detalleAudio(m));
    const oir = el("button", "btn-sm ed-bib-escuchar", fila);
    oir.type = "button";
    oir.dataset.escuchar = clave;
    this._pintarBotonEscucha(oir, nombre);
    fila.append(this._botonMas(clave, etiquetaMas(m, nombre)));
    if (puedeBorrarse(m) && this.urls.borrar_material) fila.append(this._botonBorrar(m, nombre));
    return fila;
  }

  // ---- Tocar ----

  _clic(e) {
    if (this.suprimirClic) {                // el clic que sigue a soltar un arrastre
      this.suprimirClic = false;
      return;
    }
    const objetivo = e.target;
    const subir = objetivo.closest?.("[data-subir]");
    if (subir) return this.contenedor.querySelector(`[data-entrada="${subir.dataset.subir}"]`)?.click();
    const como = objetivo.closest?.("[data-agregar-como]");
    if (como) return void this._elegirComo(como.dataset.agregarComo);
    const mas = objetivo.closest?.("[data-agregar]");
    if (mas) {
      if (this.cosas.get(mas.dataset.agregar)?.tipo === "imagen") {
        if (opcionesImagen(this.editor.doc()).length > 1) return this._alternarComo(mas.dataset.agregar, mas);
        return void this.agregar(mas.dataset.agregar, null, undefined, { como: "capa" });   // edición de imagen
      }
      return void this.agregar(mas.dataset.agregar);
    }
    const oir = objetivo.closest?.("[data-escuchar]");
    if (oir) return this._escuchar(oir.dataset.escuchar);
    const borrar = objetivo.closest?.("[data-borrar]");
    if (borrar) return void this.borrar(Number(borrar.dataset.borrar));
    const quitar = objetivo.closest?.("[data-quitar-subida]");
    if (quitar) return quitar.closest(".ed-bib-subida")?.remove();
    if (objetivo.closest?.("[data-reintentar]")) return void this.cargar();
    const tarjeta = objetivo.closest?.("button[data-clave]");          // un texto o una transición
    if (tarjeta) void this.agregar(tarjeta.dataset.clave);
  }

  // Agrega lo que muestra `clave` en el cabezal (sin `punto`) o donde se
  // soltó (`punto` de LineaTiempo.puntoEn). Una pieza de Crear que todavía no
  // es material se prepara primero y se agrega sola al tenerla. `como` (capa
  // 5b, solo una imagen sin `punto`): "clip" la pone como foto en el video,
  // "capa" (o nada) encima — lo que eligió en el menú del «+».
  agregar(clave, punto = null, cosa = this.cosas.get(clave), { como = null } = {}) {
    if (!cosa) return false;
    if (cosa.tipo === "pieza") return this._agregarPieza(cosa, punto);
    if (cosa.tipo === "sticker") return this._agregarSticker(cosa, punto);
    return this._operar(cosa, punto, como);
  }

  _operar(cosa, punto, como = null) {
    const ed = this.editor;
    if (cosa.material) ed.agregarMateriales({ [cosa.material.id]: cosa.material });   // antes de operar
    const destino = ed.destino?.() ?? null;
    const antes = ed.doc();
    const pedido = pedidoAgregar(antes, cosa, { punto, cabezalMs: ed.tiempo(), seleccion: ed.seleccion, destino, como });
    if (!pedido) {
      this._decir(t("bib.sin_videos"), true);
      return false;
    }
    if (!ed.operar(...pedido)) {
      const motivo = ed.enConflicto?.() ? mensajeConflicto() : this._motivo(pedido);
      this._decir(motivo ?? t("bib.no_agregado"), true);
      return false;
    }
    if (cosa.tipo === "transicion") {
      const { texto, error } = mensajeTransicion(antes, ed.doc(), pedido, cosa);
      this._decir(texto, error);
    } else if (pedido[0] === "agregarFoto") {
      // la foto nueva queda elegida (operaciones.agregarFoto): su duración, y que se cambia en «Editar»
      const foto = (pistaPrincipal(ed.doc())?.clips ?? []).find((c) => c.id === ed.seleccion);
      this._decir(foto ? textoFotoAgregada(foto.duracion_ms) : t("bib.agregado", { nombre: cosa.nombre }));
    } else if (cosa.tipo === "sticker") {
      this._decir(t("bib.sticker_agregado"));        // su color se cambia en «Editar»
    } else if (cosa.tipo === "texto" && cosa.preset === "emoji") {
      this._decir(t("bib.agregado", { nombre: cosa.nombre }));      // un emoji no se escribe: el teclado no sube
    } else if (cosa.tipo === "texto") {
      this._decir(t("bib.texto_agregado"));
      ed.enfocarTexto();
    } else if (cosa.tipo === "audio" && rolDeMaterial(cosa.material) === "voz"
      && idiomaDeVoz(cosa.material.idioma, destino).habla) {
      // habla otro idioma que el destino: quedó sonando en todos (D10)
      const habla = idiomaDeVoz(cosa.material.idioma, destino).habla;
      this._decir(t("voz.todos_idiomas", { idioma: this.nombresIdioma[habla] ?? habla }));
    } else {
      this._decir(t("bib.agregado", { nombre: cosa.nombre }));
    }
    if (cosa.material && faltaPreparar(cosa.material)) this._esperar(cosa.material.id);
    return true;
  }

  // ---- «¿Cómo agregar?» de una imagen (capa 5b, D12) ----
  // Un menú chico junto al «+» (fijo en la pantalla, así no lo corta la
  // columna ni la hoja del celular): «Como clip del video» o «Encima del
  // video». Se cierra al elegir, con Esc (el foco vuelve al «+»), con un toque
  // afuera, al correr la lista o al cambiar el tamaño de la ventana.

  _alternarComo(clave, boton) {
    if (this.como?.clave === clave) return this._cerrarComo({ devolverFoco: true });
    this._abrirComo(clave, boton);
  }

  _abrirComo(clave, boton) {
    const cosa = this.cosas.get(clave);
    if (!cosa) return;
    this._cerrarComo();
    const menu = el("div", "ed-bib-como", this.contenedor);
    menu.setAttribute("role", "dialog");
    const titulo = el("p", "ed-bib-como-titulo", menu, t("bib.agregar_imagen", { nombre: cosa.nombre }));
    titulo.id = "ed-bib-como-titulo";
    menu.setAttribute("aria-labelledby", titulo.id);
    for (const o of opcionesImagen(this.editor.doc())) {
      const b = el("button", "ed-bib-como-opcion", menu);
      b.type = "button";
      b.dataset.agregarComo = o.como;
      b.append(icono(ICONO_COMO[o.como] ?? "imagen", 18), el("span", "", null, o.texto));
    }
    // con el teclado, salir del menú con Tab lo cierra (con el mouse, Safari no
    // enfoca el botón tocado — `relatedTarget` null —: ahí lo cierra el toque afuera)
    menu.addEventListener("focusout", (e) => {
      const a = e.relatedTarget;
      if (a && this.como?.menu === menu && !menu.contains(a) && a !== this.como.boton) this._cerrarComo();
    });
    this.como = { clave, cosa, boton, menu };
    boton.setAttribute("aria-expanded", "true");
    this._ponerComo();
    document.addEventListener("pointerdown", this.alTocarFueraComo, true);
    document.addEventListener("keydown", this.alTeclaComo, true);
    this.contenedor.addEventListener("scroll", this.alMoverComo, { passive: true });
    window.addEventListener("resize", this.alMoverComo);
    menu.querySelector("button")?.focus({ preventScroll: true });
  }

  // Debajo del «+», alineado a su derecha; si no cabe debajo, encima. Nunca
  // fuera de la pantalla (MENU_COMO_MARGEN_PX de cada borde).
  _ponerComo() {
    const { boton, menu } = this.como ?? {};
    if (!menu?.isConnected) return;
    const b = boton.getBoundingClientRect();
    const m = menu.getBoundingClientRect();
    const ancho = window.innerWidth || document.documentElement.clientWidth || 0;
    const alto = window.innerHeight || document.documentElement.clientHeight || 0;
    const margen = MENU_COMO_MARGEN_PX;
    const x = Math.max(margen, Math.min(b.right - m.width, ancho - m.width - margen));
    const abajo = b.bottom + 4;
    const y = abajo + m.height + margen <= alto ? abajo : Math.max(margen, b.top - 4 - m.height);
    menu.style.left = `${Math.round(x)}px`;
    menu.style.top = `${Math.round(y)}px`;
  }

  _cerrarComo({ devolverFoco = false, porToque = false } = {}) {
    const como = this.como;
    if (!como) return;
    this.como = null;
    document.removeEventListener("pointerdown", this.alTocarFueraComo, true);
    document.removeEventListener("keydown", this.alTeclaComo, true);
    this.contenedor.removeEventListener("scroll", this.alMoverComo);
    window.removeEventListener("resize", this.alMoverComo);
    como.menu.remove();
    if (como.boton.isConnected) como.boton.setAttribute("aria-expanded", "false");
    // lo que llegó mientras estaba abierto; si lo cerró un toque afuera, después de su click
    if (this.pintarAlCerrar && porToque) despuesDelToque(document, () => this.pintarAlCerrar && this._pintarListas());
    else if (this.pintarAlCerrar) this._pintarListas();
    // el foco vuelve a su «+» (el nuevo, si la lista se repintó)
    const boton = como.boton.isConnected ? como.boton : this.contenedor.querySelector(`[data-agregar="${como.clave}"]`);
    if (devolverFoco) boton?.focus({ preventScroll: true });
  }

  _elegirComo(como) {
    const abierto = this.como;
    if (!abierto) return;
    this._cerrarComo({ devolverFoco: true });
    // la de la lista nueva si se repintó al cerrar (con su copia liviana, si llegó mientras tanto)
    void this.agregar(abierto.clave, null, this.cosas.get(abierto.clave) ?? abierto.cosa, { como });
  }

  // Por qué la página rechazó una operación (el mismo mensaje que muestra
  // debajo del video), para decirlo también aquí: en el celular la hoja tapa
  // ese aviso. Se vuelve a probar la operación (pura) solo cuando falló.
  _motivo(pedido) {
    try {
      operaciones[pedido[0]](this.editor.doc(), ...pedido.slice(1), this.editor.info());
      return null;                         // no es la operación: la edición está bloqueada (otra pestaña)
    } catch (e) {
      return e?.name === "OperacionInvalida" ? e.message : null;
    }
  }

  // Un sticker de la casa (capa 5c, D11): el servidor lo vuelve material del
  // proyecto (gratis, una vez por proyecto; después lo encuentra por su hash)
  // y vuelve el material, que se agrega como una capa de imagen del color de
  // su ficha, en UNA operación (un toque, un deshacer). Mientras se pide, otro
  // toque en el mismo sticker no hace nada (los lentos no se acumulan).
  async _agregarSticker(cosa, punto) {
    const { id, color } = cosa.sticker;
    this.pidiendoSticker ??= new Set();
    if (this.pidiendoSticker.has(id)) return false;
    this.pidiendoSticker.add(id);
    try {
      let r;
      let j = null;
      try {
        r = await fetch(urlSticker(this.urls.biblioteca, id), {
          method: "POST", credentials: "same-origin", headers: { Accept: "application/json", "X-Requested-With": "fetch" },
        });
        // un 500 con una página HTML (R2 falló) o la página de entrar no son JSON
        if (!sesionTerminada(r)) j = await r.json().catch(() => null);
      } catch {
        this._decir(mensajeSticker({ red: true }), true);
        return false;
      }
      if (sesionTerminada(r)) {
        this._decir(mensajeSticker({ redirigido: true }), true);
        return false;
      }
      if (!r.ok || !j?.material) {
        this._decir(mensajeSticker({ status: r.status, cuerpo: j }), true);
        return false;
      }
      return this._operar({ tipo: "sticker", material: j.material, tinte: color, nombre: cosa.nombre }, punto);
    } finally {
      this.pidiendoSticker.delete(id);
    }
  }

  async _agregarPieza(cosa, punto) {
    const p = cosa.pieza;
    const material = cosa.material ?? this._material(p.material_id);
    if (material) return this._operar({ tipo: "video", material, nombre: cosa.nombre }, punto);
    const ya = this.preparando.get(p.cf_id);
    if (ya) {
      ya.pedido = { punto };
      this._decir(t("bib.se_agrega_sola", { nombre: cosa.nombre }));
      return false;
    }
    this.preparando.set(p.cf_id, { desde: Date.now(), pedido: { punto } });
    this._pintarListas();
    this._decir(t("bib.preparando_pieza", { nombre: cosa.nombre }));
    let r;
    let j = null;
    try {
      r = await fetch(urlPieza(this.urls.agregar_pieza, p.cf_id), {
        method: "POST", credentials: "same-origin", headers: { Accept: "application/json" },
      });
      j = await r.json().catch(() => null);
    } catch {
      this.preparando.delete(p.cf_id);
      this._pintarListas();
      this._decir(t("bib.sin_conexion_pieza"), true);
      return false;
    }
    const prep = this.preparando.get(p.cf_id);
    if (r.redirected) {
      this.preparando.delete(p.cf_id);
      this._pintarListas();
      this._decir(t("bib.sesion"), true);
      return false;
    }
    if (r.status === 202) {
      this._programarPiezas();
      return false;
    }
    this.preparando.delete(p.cf_id);
    if (r.ok && j?.material && evaluarRespuesta(r) === "json") {
      this._ponerMaterial(j.material);
      this.datos.piezas = this.datos.piezas.map((x) => (x.cf_id === p.cf_id ? { ...x, material_id: j.material.id, preparando: false } : x));
      this._pintarListas();
      return this._operar({ tipo: "video", material: j.material, nombre: cosa.nombre }, prep?.pedido?.punto ?? punto);
    }
    this._pintarListas();
    this._decir(j?.error || t("bib.error_pieza", { status: r.status }), true);
    return false;
  }

  // ---- Borrar (capa 4c) ----

  // Pregunta antes (no se puede deshacer); lo que usa la edición abierta ni
  // se manda. El servidor se niega si otra edición (o una versión producida)
  // lo usa y dice cuál. Borrado, sale de la lista y deja de contar en la cuota.
  async borrar(id) {
    const m = this._material(id);
    if (!m) return false;
    const nombre = nombreDe(m);
    const motivo = motivoNoBorrar(m, this.editor.doc());
    if (motivo) {
      this._decir(motivo, true);
      return false;
    }
    if (!window.confirm(t("bib.borrar_confirmar", { nombre }))) return false;
    let r;
    let j = null;
    try {
      r = await fetch(urlBorrar(this.urls.borrar_material, id), {
        method: "POST", credentials: "same-origin", headers: { Accept: "application/json" },
      });
      if (!sesionTerminada(r)) j = await r.json().catch(() => null);
    } catch {
      this._decir(t("bib.borrar_sin_conexion"), true);
      return false;
    }
    if (sesionTerminada(r)) {
      this._decir(mensajeSesion(), true);
      return false;
    }
    if (!r.ok || !j?.ok) {
      this._decir(j?.error || t("bib.borrar_error", { status: r.status }), true);
      return false;
    }
    if (this.escucha?.clave === `m:${id}`) this._pararEscucha();
    this.esperando.delete(id);
    this.borrados.add(id);
    this.datos = quitarMaterial(this.datos, id);
    this._pintarListas();
    this._decir(t("bib.borrado", { nombre }));
    return true;
  }

  // ---- Preguntar por lo que el servidor prepara (cada 3 s, hasta 5 min) ----

  async _pedirJSON(url) {
    try {
      const r = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      const que = evaluarRespuesta(r);
      return que === "json" ? { que, j: await r.json() } : { que };
    } catch {
      return { que: "reintentar" };
    }
  }

  _programarPiezas() {
    if (this.relojPiezas || !this.preparando.size) return;
    this.relojPiezas = setTimeout(async () => {
      try {
        await this._revisarPiezas();
      } finally {
        this.relojPiezas = null;
        this._programarPiezas();
      }
    }, INTERVALO_BIBLIOTECA_MS);
  }

  _firma() {
    return firmaListado({ carga: this.carga, datos: this.datos, preparando: [...this.preparando.keys()] });
  }

  async _revisarPiezas() {
    const antes = this._firma();
    const { que, j } = await this._pedirJSON(this.urls.biblioteca);
    const ahora = Date.now();
    if (que === "json" && j) {
      this.datos = { materiales: Array.isArray(j.materiales) ? j.materiales : [], piezas: Array.isArray(j.piezas) ? j.piezas : [] };
      this.carga = "lista";
    }
    for (const [cf, prep] of [...this.preparando]) {
      const p = this.datos.piezas.find((x) => x.cf_id === cf);
      const nombre = p?.nombre || t("bib.ese_video");
      if (p?.material_id) {
        this.preparando.delete(cf);
        let m = this._material(p.material_id);
        if (!m) m = (await this._pedirJSON(`${this.urls.materiales_por_id}?ids=${p.material_id}`)).j?.materiales?.[p.material_id] ?? null;
        if (m) this._ponerMaterial(m);
        if (prep.pedido && m) this._operar({ tipo: "video", material: m, nombre: p.nombre || t("bib.video_crear") }, prep.pedido.punto ?? null);
      } else if (que === "json" && (!p || !p.preparando) && ahora - prep.desde > 2 * INTERVALO_BIBLIOTECA_MS) {
        this.preparando.delete(cf);                     // la preparación terminó sin material: falló
        if (prep.pedido) this._decir(t("bib.no_preparo", { nombre }), true);
      } else if (que === "parar" || ahora - prep.desde > TOPE_ESPERA_MS) {
        this.preparando.delete(cf);
        if (prep.pedido) this._decir(t("bib.tarda", { nombre }), true);
      }
    }
    if (this._firma() !== antes) this._pintarListas();      // sin cambios, nada se repinta
  }

  _esperar(id) {
    if (!this.esperando.has(id)) this.esperando.set(id, Date.now());
    this._programarMateriales();
  }

  _programarMateriales() {
    if (this.relojMateriales || !this.esperando.size) return;
    this.relojMateriales = setTimeout(async () => {
      try {
        await this._revisarMateriales();
      } finally {
        this.relojMateriales = null;
        this._programarMateriales();
      }
    }, INTERVALO_BIBLIOTECA_MS);
  }

  // La copia liviana, la tira o los picos que llegaron pasan a la vista
  // previa (que cambia los archivos al pausar) y a las miniaturas. La primera
  // pregunta por cada material le pide al servidor que lo prepare
  // (`preparar=`, gratis): una canción de Mi música nunca tuvo picos y nadie
  // más lo pediría. Una vez por material: si falla, no se reencola cada 3 s.
  async _revisarMateriales() {
    const ahora = Date.now();
    for (const [id, desde] of [...this.esperando]) if (ahora - desde > TOPE_ESPERA_MS) this.esperando.delete(id);
    if (!this.esperando.size) return;
    const ids = [...this.esperando.keys()];
    this.pedidosPreparar ??= new Set();
    const nuevos = ids.filter((id) => !this.pedidosPreparar.has(id));
    const url = `${this.urls.materiales_por_id}?ids=${ids.join(",")}${nuevos.length ? `&preparar=${nuevos.join(",")}` : ""}`;
    const { que, j } = await this._pedirJSON(url);
    if (que === "json") for (const id of nuevos) this.pedidosPreparar.add(id);
    if (que === "parar") {
      this.esperando.clear();
      return;
    }
    if (que !== "json" || !j) return;
    const recibidos = j.materiales ?? {};
    const listos = {};
    let cambio = false;
    for (const id of ids) {
      const m = recibidos[id];
      if (!m) {                                        // ya no existe (o no es de este proyecto)
        this.esperando.delete(id);
        continue;
      }
      cambio = this._ponerMaterial(m) || cambio;
      if (!faltaPreparar(m)) {
        listos[m.id] = m;
        this.esperando.delete(id);
      }
    }
    if (Object.keys(listos).length) this.editor.agregarMateriales(listos);
    if (cambio) this._pintarListas();
  }

  // ---- Subir (una a la vez, cada archivo con su barra y su error) ----

  _soltarArchivos(archivos) {
    if (!archivos.length) return;
    const panel = tipoDeArchivo(archivos[0].name) === "audio" ? "audio" : "medios";
    if (this.panel !== panel) this.pestanas.querySelector(`[data-panel="${panel}"]`)?.click();
    this.subir(archivos, panel);
  }

  subir(archivos, panel = "medios") {
    const lista = this.listaSubidas[panel] ?? this.listaSubidas.medios;
    for (const archivo of archivos) {
      const error = revisarArchivo(archivo.name, archivo.size);
      const s = { archivo, nombre: archivo.name, estado: error ? "error" : "espera", progreso: 0, error, nodo: null };
      s.nodo = this._filaSubida(s);
      lista.append(s.nodo);
      if (!error) this.subidas.push(s);
    }
    this._siguienteSubida();
  }

  _filaSubida(s) {
    const li = el("li", "ed-bib-subida");
    const cabeza = el("div", "ed-bib-subida-cabeza", li);
    el("span", "ed-bib-nombre", cabeza, s.nombre).title = s.nombre;
    el("span", "ed-bib-subida-estado", cabeza);
    const quitar = el("button", "ed-bib-quitar", cabeza);
    quitar.type = "button";
    quitar.dataset.quitarSubida = "";
    quitar.title = t("bib.quitar");
    quitar.setAttribute("aria-label", t("bib.quitar_nombre", { nombre: s.nombre }));
    quitar.append(icono("cerrar", 14));
    const barra = el("progress", "", li);
    barra.max = 1;
    barra.setAttribute("aria-label", t("bib.subida_de", { nombre: s.nombre }));
    el("p", "editor-aviso error ed-bib-subida-error", li);
    this._pintarSubida(s, li);
    return li;
  }

  _pintarSubida(s, li = s.nodo) {
    if (!li) return;
    li.dataset.estado = s.estado;
    li.querySelector(".ed-bib-subida-estado").textContent = ESTADO_SUBIDA[s.estado]?.(s) ?? "";
    const barra = li.querySelector("progress");
    barra.hidden = s.estado === "error" || s.estado === "lista";
    if (s.estado === "procesando") barra.removeAttribute("value");          // sin número: el servidor la mide y la guarda
    else barra.value = s.estado === "espera" ? 0 : s.progreso;
    li.querySelector(".ed-bib-quitar").hidden = s.estado !== "error";
    const error = li.querySelector(".ed-bib-subida-error");
    error.textContent = s.estado === "error" ? s.error || "" : "";
    error.hidden = s.estado !== "error";
  }

  _siguienteSubida() {
    if (this.subiendo) return;
    const s = this.subidas.shift();
    if (!s) return;
    this.subiendo = true;
    this._enviar(s).finally(() => {
      this.subiendo = false;
      this._siguienteSubida();
    });
  }

  // XMLHttpRequest (no fetch) para ver el avance de la subida.
  _enviar(s) {
    return new Promise((listo) => {
      const xhr = new XMLHttpRequest();
      const fallo = (mensaje) => {
        s.estado = "error";
        s.error = mensaje;
        this._pintarSubida(s);
        listo();
      };
      s.estado = "subiendo";
      this._pintarSubida(s);
      xhr.open("POST", this.urls.subir);
      xhr.setRequestHeader("Accept", "application/json");
      xhr.upload.addEventListener("progress", (e) => {
        if (!e.lengthComputable || s.estado !== "subiendo") return;
        s.progreso = e.total ? e.loaded / e.total : 0;
        this._pintarSubida(s);
      });
      xhr.upload.addEventListener("load", () => {
        s.estado = "procesando";
        this._pintarSubida(s);
      });
      xhr.addEventListener("load", () => {
        let cuerpo = null;
        try {
          cuerpo = JSON.parse(xhr.responseText);
        } catch { /* no era JSON (la página de entrar, un error del servidor) */ }
        const ruta = (u) => new URL(u, location.href).pathname;
        const redirigido = Boolean(xhr.responseURL) && ruta(xhr.responseURL) !== ruta(this.urls.subir);
        if (xhr.status === 200 && !redirigido && cuerpo?.material) {
          this._subido(s, cuerpo.material);
          listo();
          return;
        }
        fallo(mensajeSubida({ status: xhr.status, cuerpo, redirigido }));
      });
      for (const ev of ["error", "abort", "timeout"]) xhr.addEventListener(ev, () => fallo(mensajeSubida({ red: true })));
      const fd = new FormData();
      fd.append("archivo", s.archivo, s.archivo.name);
      xhr.send(fd);
    });
  }

  _subido(s, m) {
    s.estado = "lista";
    this._pintarSubida(s);
    this._ponerMaterial(m);
    this.editor.agregarMateriales({ [m.id]: m });
    if (this.carga === "lista") this._pintarListas();
    else void this.cargar();                     // la lista no había cargado: se trae entera (ya con este)
    if (faltaPreparar(m)) this._esperar(m.id);
    setTimeout(() => s.nodo?.remove(), 2500);
  }

  // ---- Escuchar un audio antes de agregarlo ----

  _pintarBotonEscucha(boton, nombre) {
    const sonando = this.escucha?.clave === boton.dataset.escuchar;
    boton.setAttribute("aria-pressed", String(sonando));
    boton.setAttribute("aria-label", t(sonando ? "bib.parar_nombre" : "bib.escuchar_nombre", { nombre }));
    boton.title = t(sonando ? "bib.parar" : "bib.escuchar");
    boton.replaceChildren(icono(sonando ? "pausa" : "play", 14));
  }

  _escuchar(clave) {
    const cosa = this.cosas.get(clave);
    if (!cosa?.material?.url) return;
    const otra = this.escucha?.clave !== clave;
    this._pararEscucha();
    if (!otra) return;
    const audio = new Audio(cosa.material.url);
    this.escucha = { clave, audio };
    audio.addEventListener("ended", () => this._pararEscucha());
    audio.play().catch(() => {
      if (this.escucha?.audio !== audio) return;
      this._pararEscucha();
      this._decir(t("bib.no_escucha"), true);
    });
    this._pintarEscuchas();
  }

  _pararEscucha() {
    if (!this.escucha) return;
    const { audio } = this.escucha;
    this.escucha = null;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    this._pintarEscuchas();
  }

  _pintarEscuchas() {
    for (const b of this.listaAudios.querySelectorAll("[data-escuchar]")) {
      this._pintarBotonEscucha(b, this.cosas.get(b.dataset.escuchar)?.nombre ?? "");
    }
  }

  // ---- Arrastrar a la línea de tiempo (mouse y lápiz) ----
  // Con el dedo no: en el celular la hoja tapa la línea, y deslizar mueve la
  // lista. El arrastre escucha en `window` (no captura el puntero): si la
  // lista se repinta a mitad, nada se corta — igual se deja para después.

  _abajo(e) {
    if (e.button !== 0 || !e.isPrimary || e.pointerType === "touch" || this.arrastre) return;
    const item = e.target.closest?.("[data-arrastrable]");
    if (!item || !this.contenedor.contains(item) || e.target.closest("[data-agregar], [data-escuchar], [data-borrar], .ed-bib-como")) return;
    e.preventDefault();                           // sin seleccionar texto ni robar el foco (S, Supr, Ctrl+Z siguen andando)
    this.arrastre = {
      clave: item.dataset.clave, cosa: this.cosas.get(item.dataset.clave), pointerId: e.pointerId,
      x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, activo: false, fantasma: null, origen: item, cuadro: 0,
    };
    window.addEventListener("pointermove", this.alMover);
    window.addEventListener("pointerup", this.alSoltar);
    window.addEventListener("pointercancel", this.alCancelar);
    window.addEventListener("keydown", this.alTecla, true);
  }

  _moverArrastre(e) {
    const a = this.arrastre;
    if (!a || e.pointerId !== a.pointerId) return;
    a.x = e.clientX;
    a.y = e.clientY;
    if (!a.activo) {
      if (Math.hypot(a.x - a.x0, a.y - a.y0) < ARRASTRE_MIN_PX) return;
      this._empezarArrastre();
    }
    if (!a.cuadro) {
      a.cuadro = requestAnimationFrame(() => {
        a.cuadro = 0;
        this._pintarArrastre();
      });
    }
  }

  _empezarArrastre() {
    const a = this.arrastre;
    if (!a.cosa) return this._terminarArrastre();
    a.activo = true;
    this._pararEscucha();
    const f = el("div", "ed-bib-fantasma", document.body);
    f.setAttribute("aria-hidden", "true");
    f.append(icono(ICONO_DE[a.cosa.tipo] ?? "video", 16));
    el("span", "", f, a.cosa.nombre ?? "");
    a.fantasma = f;
    a.origen.classList.add("ed-bib-origen");
    document.body.classList.add("ed-bib-arrastrando");
    this._pintarArrastre();
  }

  _pintarArrastre() {
    const a = this.arrastre;
    if (!a?.activo) return;
    a.fantasma.style.transform = `translate(${Math.round(a.x + 14)}px, ${Math.round(a.y + 14)}px)`;
    const punto = this.linea.puntoEn(a.x, a.y);
    a.fantasma.classList.toggle("ed-bib-fantasma-dentro", Boolean(punto));
    this.linea.resaltar(punto);
  }

  _soltarArrastre(e) {
    const a = this.arrastre;
    if (!a || e.pointerId !== a.pointerId) return;
    const punto = a.activo ? this.linea.puntoEn(e.clientX, e.clientY) : null;
    this._terminarArrastre();
    if (!a.activo) return;                        // fue un toque: el clic hace lo suyo
    this.suprimirClic = true;                     // el navegador puede mandar un clic al soltar: no es un toque
    setTimeout(() => { this.suprimirClic = false; }, 0);
    if (punto) void this.agregar(a.clave, punto, a.cosa);
  }

  _terminarArrastre() {
    const a = this.arrastre;
    this.arrastre = null;
    window.removeEventListener("pointermove", this.alMover);
    window.removeEventListener("pointerup", this.alSoltar);
    window.removeEventListener("pointercancel", this.alCancelar);
    window.removeEventListener("keydown", this.alTecla, true);
    if (a?.cuadro) cancelAnimationFrame(a.cuadro);
    if (a?.activo) {
      this.linea.resaltar(null);
      a.fantasma?.remove();
      a.origen?.classList.remove("ed-bib-origen");
      document.body.classList.remove("ed-bib-arrastrando");
    }
    if (this.pintarAlSoltar) this._pintarListas();
  }
}

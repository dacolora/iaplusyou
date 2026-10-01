// Panel de propiedades del editor (capa 4b, Task 7): lo puro. Qué formulario
// le toca a lo elegido (`formaDe`), los valores que muestra (`modelo`, uno por
// forma, siempre con la misma forma de objeto), los cambios que pide cada
// control para operaciones.cambiar (en las unidades del documento: fracciones
// del lienzo) y cómo se escriben los valores. propiedades.js solo pone esto en
// el DOM; lo prueba tests/js/propiedades_modelo.test.mjs.
//
// Formas: "documento" (nada elegido: la mezcla de toda la edición), "video"
// (un clip de la principal), "texto", "imagen", "audio" (música, efecto, voz…),
// "sonido" (el espejo de p_sonido: no se edita, se cambia desde su video) y
// "otro" (un video encima u otra pista que el render no hace: solo borrar).
import { FORMATOS } from "./formatos.js";
import { etiquetaClip, nombreTransicion } from "./escala.js";
import {
  cambiaPorDestino, FUENTES, ID_SONIDO, MEZCLAS, sincronizarSonido, TRANSICIONES, VELOCIDADES,
} from "./operaciones.js";
import * as operaciones from "./operaciones.js";
import { valorDestino, VARIABLE_PRECIO } from "./resolver.js";
import { separadorDecimal, t } from "./textos.js";
import { pistaPrincipal, tamanoCapaImagen } from "./tiempo.js";

// Los nombres que ve la persona son CLAVES de textos.js: se traducen donde se
// usan (ningún módulo llama a t() al cargarse).
export const NOMBRES_MEZCLA = { equilibrada: "prop.mezcla_equilibrada", voz_protagonista: "prop.mezcla_voz", ambiente_protagonista: "prop.mezcla_ambiente" };
const AYUDAS_MEZCLA = {
  equilibrada: "prop.ayuda_equilibrada",
  voz_protagonista: "prop.ayuda_voz",
  ambiente_protagonista: "prop.ayuda_ambiente",
};

// La duración de una transición (ms): el deslizador del formulario del video.
export const TRANSICION_MS = { min: 200, max: 1500, paso: 100, defecto: 500 };
// Tamaño de un texto en px del lienzo: el mismo tope que aplica operaciones.cambiar.
export const TAMANO_TEXTO_PX = { min: 12, max: 200 };
// Grosor del contorno en px del lienzo (el preset «Título» usa 4).
export const GROSOR_PX = { min: 1, max: 20, defecto: 4 };
const SOMBRA_PX = 3;                              // el preset «Subtítulo»
// El radio del fondo (fracción de la altura; el render lo recorta a media
// caja): 1 es una píldora, el poco de «caja» apenas redondea las esquinas.
export const RADIO_FONDO = { pildora: 1, caja: 0.01 };
const FONDO_NUEVO = { color: "#000000", opacidad: 0.8, relleno_x: 0.03, relleno_y: 0.015 };
// Un fundido dura como mucho la mitad del clip, y nunca más de esto.
export const FUNDIDO_MAX_MS = 5000;
const FUNDIDO_PASO_MS = 100;
// El tope de transform.escala en operaciones.cambiar.
export const ESCALA = { min: 0.05, max: 5 };

// Las tres fuentes de static/fonts (operaciones.FUENTES), con la clave del nombre que se lee.
export const NOMBRES_FUENTE = { "Inter-Bold": "prop.fuente_inter_gruesa", "Inter-SemiBold": "prop.fuente_inter_media", "SpaceGrotesk-Bold": "prop.fuente_space" };
// La paleta del color del texto; el color de marca entra tercero (`paletaDe`).
export const COLORES = [
  { nombre: "prop.color_blanco", color: "#FFFFFF" },
  { nombre: "prop.color_negro", color: "#000000" },
  { nombre: "prop.color_amarillo", color: "#FFD60A" },
  { nombre: "prop.color_rojo", color: "#E53935" },
];

const NOMBRES_ROL = { musica: "fila.musica", efecto: "fila.efecto", voz: "fila.voz", grabacion: "fila.grabacion", sonido: "fila.sonido", subida: "fila.audio" };
const CLAVE_DESTINO = /^[a-z]{2}(_[A-Z]{2})?$/;   // lo que acepta operaciones.editarTexto
const COLOR_RE = /^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/;

const acotar = (v, min, max) => Math.min(max, Math.max(min, v));
const casi = (a, b) => Math.abs(Number(a) - Number(b)) < 1e-6;
const lienzo = (formato) => FORMATOS[formato] ?? FORMATOS["9:16"];

// "#abcdef" o "#ABCDEF80" -> "#ABCDEF" (lo que muestra un <input type=color>);
// lo que no es un color, `defecto`.
export function colorBase(c, defecto = "#FFFFFF") {
  return typeof c === "string" && COLOR_RE.test(c) ? c.slice(0, 7).toUpperCase() : defecto;
}

// ---- Cómo se escriben los valores ----

const decimal = (n, max) => String(Number(n.toFixed(max))).replace(".", separadorDecimal());

export function textoPorcentaje(n) {
  return t("prop.porcentaje", { n: Math.round(Number(n) || 0) });
}

export function textoSegundos(ms) {
  return `${decimal(Math.round((Number(ms) || 0) / 100) / 10, 1)} s`;
}

export function textoVelocidad(v) {
  return `${decimal(Number(v), 2)}×`;
}

// ---- Qué está elegido ----

export function buscar(doc, id) {
  if (id === null || id === undefined) return null;
  for (const pista of doc?.pistas ?? []) {
    const indice = pista.clips.findIndex((c) => c.id === id);
    if (indice >= 0) return { pista, clip: pista.clips[indice], indice };
  }
  return null;
}

function formaDeHallado(doc, h) {
  if (!h) return "documento";
  const { pista } = h;
  if (pista.id === ID_SONIDO) return "sonido";
  const principal = pistaPrincipal(doc);
  if (pista.tipo === "video") return pista === principal ? "video" : "otro";
  if (pista.tipo === "texto") return "texto";
  if (pista.tipo === "imagen") return pista === principal ? "otro" : "imagen";
  if (pista.tipo === "audio") return "audio";
  return "otro";
}

export function formaDe(doc, id) {
  return formaDeHallado(doc, buscar(doc, id));
}

// Qué decide si el formulario se ARMA de nuevo (otra forma u otro clip) o
// solo se le ponen los valores nuevos (mientras se arrastra un deslizador, el
// formulario no se puede rehacer: se perdería el arrastre).
export function claveForma(m) {
  return `${m.forma}:${m.clipId ?? ""}`;
}

// ---- Los valores de cada formulario ----

// `destino`: "<idioma>_<PAIS>" que se está viendo (editor.destino()); `info`:
// {material_id: {duracion_ms, tiene_audio}} (editor.info()); `materiales`:
// los de la vista previa (para las medidas de una imagen).
export function modelo(doc, id, { destino = null, info = {}, materiales = {} } = {}) {
  const h = buscar(doc, id);
  const forma = formaDeHallado(doc, h);
  switch (forma) {
    case "video": return modeloVideo(doc, h, info);
    case "texto": return modeloTexto(doc, h, destino);
    case "imagen": return modeloImagen(doc, h, materiales);
    case "audio": return modeloAudio(h);
    case "sonido": return modeloSonido(doc, h);
    case "otro": return { forma, clipId: h.clip.id, nombre: t(h.pista.tipo === "superpuesto" ? "fila.superpuesto" : "prop.clip") };
    default: return modeloDocumento(doc);
  }
}

function modeloDocumento(doc) {
  const mz = doc?.mezcla ?? {};
  const volumenes = mz.volumenes && typeof mz.volumenes === "object" ? mz.volumenes : {};
  return {
    forma: "documento",
    clipId: null,
    ayuda: t("prop.ayuda_vacia"),
    mezcla: MEZCLAS.includes(mz.preset) ? mz.preset : "equilibrada",
    aMedida: Object.values(volumenes).some((v) => v !== null && v !== undefined),
    opcionesMezcla: MEZCLAS.map((valor) => ({ valor, texto: t(NOMBRES_MEZCLA[valor]), ayuda: t(AYUDAS_MEZCLA[valor]) })),
  };
}

// El espejo del sonido de la escena de un clip de la principal tal como
// quedaría tras operar (sincronizarSonido: un documento del borrador todavía
// nombra sus espejos s0, s1…), o null si no hay sonido que espejar.
function espejoDe(doc, clipId, info) {
  const sync = sincronizarSonido(structuredClone(doc), info);
  const id = `s_${clipId}`.slice(0, 40);
  return sync.pistas.find((p) => p.id === ID_SONIDO)?.clips.find((c) => c.id === id) ?? null;
}

// El volumen del sonido de la escena de un clip de la principal. En una
// edición sin `p_sonido` (la receta no lo pidió: operaciones.sincronizarSonido
// nunca la crea) el video suena en 0, «Sin sonido», y el deslizador sigue
// disponible: moverlo (operaciones.volumenSonido) la crea para ese clip.
function sonidoDeVideo(doc, clip, info) {
  const espejo = espejoDe(doc, clip.id, info);
  if (espejo) return { disponible: true, porcentaje: Math.round(Number(espejo.audio?.volumen ?? 1) * 100), motivo: null };
  const sinPista = !(doc?.pistas ?? []).some((p) => p.id === ID_SONIDO);
  if (sinPista && motivoRechazo(doc, "volumenSonido", [clip.id, 0], info) === null) {
    return { disponible: true, porcentaje: 0, motivo: t("prop.sin_sonido") };
  }
  const velocidad = Number(clip.velocidad ?? 1);
  return { disponible: false, porcentaje: 0,
           motivo: velocidad !== 1 ? t("prop.velocidad_sin_sonido") : t("prop.video_sin_sonido") };
}

function modeloVideo(doc, { pista, clip, indice }, info) {
  const velocidad = Number(clip.velocidad ?? 1);
  const sonido = sonidoDeVideo(doc, clip, info);
  const ultimo = indice === pista.clips.length - 1;
  const tr = clip.transicion;
  const conTransicion = Boolean(tr) && (tr.tipo ?? "corte") !== "corte" && Number(tr.duracion_ms) > 0;
  const soloUno = pista.clips.length <= 1;
  return {
    forma: "video",
    clipId: clip.id,
    nombre: t("fila.video"),
    velocidad,
    velocidades: VELOCIDADES.map((v) => ({ valor: v, texto: textoVelocidad(v) })),
    sonido,
    kenBurns: clip.ken_burns === "in" || clip.ken_burns === "out" ? clip.ken_burns : null,
    transicion: {
      disponible: !ultimo,
      motivo: ultimo ? t("prop.ultimo_video") : null,
      tipo: conTransicion ? tr.tipo : "corte",
      duracionMs: conTransicion ? Number(tr.duracion_ms) : TRANSICION_MS.defecto,
      min: TRANSICION_MS.min, max: TRANSICION_MS.max, paso: TRANSICION_MS.paso,
    },
    transiciones: TRANSICIONES.map((tipo) => ({ valor: tipo, texto: nombreTransicion(tipo) })),
    puedeBorrar: !soloUno,
    motivoBorrar: soloUno ? t("op.un_clip") : null,
  };
}

// La clave con que editarTexto guarda el texto: el destino que se ve o, sin
// uno válido, el idioma base de la edición.
function claveTexto(doc, destino) {
  if (typeof destino === "string" && CLAVE_DESTINO.test(destino)) return destino;
  return typeof doc?.idioma_base === "string" && /^[a-z]{2}$/.test(doc.idioma_base) ? doc.idioma_base : "es";
}

function textoDe(doc, pista, clip, destino) {
  const clave = claveTexto(doc, destino);
  const tx = clip.texto ?? {};
  if (!("variable" in tx)) return { valor: String(tx.literal ?? ""), editable: true, destino: clave, nota: null };
  if (tx.variable === VARIABLE_PRECIO) {
    return { valor: etiquetaClip(pista, clip, doc, destino), editable: false, destino: clave,
             nota: t("prop.nota_precio") };
  }
  const [idioma, pais] = clave.split("_");
  const valor = valorDestino(doc.variables?.textos?.[tx.variable], idioma, pais);
  return { valor: valor === null || valor === undefined ? "" : String(valor), editable: true, destino: clave,
           nota: t("prop.nota_por_pais", { destino: clave.replace("_", " · ") }) };
}

export function paletaDe(doc, color) {
  const marca = typeof doc?.marca?.color === "string" && COLOR_RE.test(doc.marca.color)
    ? [{ nombre: "prop.color_marca", color: colorBase(doc.marca.color) }] : [];
  const lista = [...COLORES.slice(0, 2), ...marca, ...COLORES.slice(2)];
  return lista.map((c) => ({ ...c, nombre: t(c.nombre), elegido: c.color === color }));
}

// Capa 4c: el video final dibuja los textos con Inter / Space Grotesk, que no
// traen emojis — el rasterizador del servidor los quita
// (rasterizar.sin_glifos_faltantes) en vez de dibujar cajas —, pero la vista
// previa sí los muestra (el navegador cae a la fuente de emojis del equipo):
// el panel lo avisa. ® ™ © no cuentan (las fuentes los traen).
const EMOJI_RE = /(?![\u00A9\u00AE\u2122])\p{Extended_Pictographic}|\p{Regional_Indicator}/u;
export function avisoEmoji() {
  return t("prop.aviso_emoji");
}

export function tieneEmoji(texto) {
  return typeof texto === "string" && EMOJI_RE.test(texto);
}

function modeloTexto(doc, { pista, clip }, destino) {
  const [, alto] = lienzo(doc.formato);
  const e = clip.estilo ?? {};
  const color = colorBase(e.color);
  const tf = clip.transform ?? {};
  const fondo = e.fondo && typeof e.fondo === "object" ? e.fondo : null;
  const texto = textoDe(doc, pista, clip, destino);
  return {
    forma: "texto",
    clipId: clip.id,
    nombre: t("fila.texto"),
    texto,
    avisoEmoji: tieneEmoji(texto.valor) ? avisoEmoji() : null,
    fuente: typeof e.fuente === "string" ? e.fuente : null,
    fuentes: FUENTES.map((f) => ({ valor: f, texto: NOMBRES_FUENTE[f] ? t(NOMBRES_FUENTE[f]) : f })),
    tamano: { px: Math.round(acotar(Number(e.tamano ?? 0.04) * alto, TAMANO_TEXTO_PX.min, TAMANO_TEXTO_PX.max)),
              min: TAMANO_TEXTO_PX.min, max: TAMANO_TEXTO_PX.max },
    color,
    paleta: paletaDe(doc, color),
    contorno: {
      activo: Boolean(e.contorno),
      color: colorBase(e.contorno?.color, "#000000"),
      grosorPx: Math.round(acotar(Number(e.contorno?.grosor ?? 0.002) * alto, GROSOR_PX.min, GROSOR_PX.max)),
      min: GROSOR_PX.min, max: GROSOR_PX.max,
    },
    sombra: { activo: Boolean(e.sombra) },
    fondo: {
      tipo: !fondo ? "ninguno" : Number(fondo.radio ?? 0.02) >= 0.5 ? "pildora" : "caja",
      color: colorBase(fondo?.color, "#000000"),
      opacidad: Math.round(Number(fondo?.opacidad ?? 0.8) * 100),
    },
    alineacion: ["izquierda", "centro", "derecha"].includes(e.alineacion) ? e.alineacion : "centro",
    animacion: clip.animacion?.entrada ?? "ninguna",
    centrado: { x: casi(tf.x ?? 0.5, 0.5), y: casi(tf.y ?? 0.5, 0.5) },
  };
}

// Una imagen se mide en % del ANCHO de la pantalla (lo que se ve), no en su
// escala (que multiplica el tamaño natural, que nadie conoce). Tamaño natural:
// tiempo.tamanoCapaImagen, el mismo respaldo que el servidor y la vista previa.
function porcentajeDe(escala, clip, material, formato) {
  const [ancho] = lienzo(formato);
  const [w] = tamanoCapaImagen(clip, material);
  return (escala * w / ancho) * 100;
}

export function escalaDePorcentaje(pct, clip, material, formato) {
  const [ancho] = lienzo(formato);
  const [w] = tamanoCapaImagen(clip, material);
  return acotar((Number(pct) / 100) * ancho / w, ESCALA.min, ESCALA.max);
}

// «Llenar la pantalla»: cubrirla entera, centrada (como agregarImagen con
// `llenar`); una imagen muy chica llega hasta el tope de la escala.
export function cambioLlenar(clip, material, formato) {
  const [ancho, alto] = lienzo(formato);
  const [w, h] = tamanoCapaImagen(clip, material);
  return { transform: { escala: Math.min(ESCALA.max, Math.max(ancho / w, alto / h)), x: 0.5, y: 0.5 } };
}

function modeloImagen(doc, { clip }, materiales) {
  const material = materiales?.[clip.material_id] ?? null;
  const tf = clip.transform ?? {};
  const escala = Number(tf.escala ?? 1);
  const [ancho, alto] = lienzo(doc.formato);
  const [w, h] = tamanoCapaImagen(clip, material);
  const cubrir = Math.max(ancho / w, alto / h);
  const llenar = cambioLlenar(clip, material, doc.formato).transform;
  const centrada = casi(tf.x ?? 0.5, 0.5) && casi(tf.y ?? 0.5, 0.5);
  return {
    forma: "imagen",
    clipId: clip.id,
    nombre: t("clip.imagen"),
    tamano: {
      porcentaje: Math.round(porcentajeDe(escala, clip, material, doc.formato)),
      min: Math.max(1, Math.ceil(porcentajeDe(ESCALA.min, clip, material, doc.formato))),
      max: Math.floor(porcentajeDe(ESCALA.max, clip, material, doc.formato)),
    },
    opacidad: Math.round(Number(tf.opacidad ?? 1) * 100),
    centrada,
    llena: centrada && casi(escala, llenar.escala),
    llenar: { alcanza: cubrir <= ESCALA.max },
  };
}

function modeloAudio({ clip }) {
  const a = clip.audio ?? {};
  const rol = clip.rol_audio ?? "subida";
  const volumen = Number(a.volumen ?? 1);
  return {
    forma: "audio",
    clipId: clip.id,
    nombre: t(NOMBRES_ROL[rol] ?? "fila.audio"),
    volumen: Math.round(volumen * 100),
    silenciado: volumen === 0,
    fundidos: {
      entradaMs: Math.max(0, Math.round(Number(a.fundido_entrada_ms ?? 0))),
      salidaMs: Math.max(0, Math.round(Number(a.fundido_salida_ms ?? 0))),
      max: Math.min(FUNDIDO_MAX_MS, Math.floor(Number(clip.duracion_ms) / 2 / FUNDIDO_PASO_MS) * FUNDIDO_PASO_MS),
      paso: FUNDIDO_PASO_MS,
    },
    nota: cambiaPorDestino(clip) ? t("prop.nota_voz") : null,
  };
}

// El espejo se cambia desde su video: el de la principal que lo generó (por
// id, `s_<id>`; en un documento del borrador, s0/s1…, por su lugar y material).
function modeloSonido(doc, { clip }) {
  const principal = pistaPrincipal(doc);
  const clips = principal && principal.tipo === "video" ? principal.clips : [];
  const dueno = clips.find((c) => `s_${c.id}`.slice(0, 40) === clip.id)
    ?? clips.find((c) => c.inicio_ms === clip.inicio_ms && c.material_id === clip.material_id);
  return { forma: "sonido", clipId: clip.id, principalId: dueno?.id ?? null };
}

// ---- Los cambios que pide cada control (para operaciones.cambiar) ----

export function cambioContorno(activo, formato) {
  const [, alto] = lienzo(formato);
  return { estilo: { contorno: activo ? { color: "#000000", grosor: GROSOR_PX.defecto / alto } : null } };
}

export function cambioGrosor(px, formato) {
  const [, alto] = lienzo(formato);
  return { estilo: { contorno: { grosor: Number(px) / alto } } };
}

export function cambioSombra(activo, formato) {
  const [, alto] = lienzo(formato);
  return { estilo: { sombra: activo ? { color: "#000000", dx: SOMBRA_PX / alto, dy: SOMBRA_PX / alto } : null } };
}

// Ninguno · Píldora · Caja. Con un fondo ya puesto solo cambia la forma (su
// color y su opacidad se quedan: operaciones.cambiar fusiona); sin fondo, uno
// entero, negro al 80 % (el de documento.py).
export function cambioFondo(tipo, fondoActual) {
  if (tipo === "ninguno") return { estilo: { fondo: null } };
  if (!(tipo in RADIO_FONDO)) throw new Error(`Forma de fondo desconocida: ${tipo}`);
  const radio = RADIO_FONDO[tipo];
  return { estilo: { fondo: fondoActual ? { radio } : { ...FONDO_NUEVO, radio } } };
}

// «Silenciar» baja a 0 y recuerda cuánto tenía; «Volver a oír» lo devuelve
// (o 100 % si no hay nada que recordar: se silenció en otra visita).
export function alternarSilencio(volumen, recordado) {
  if (Number(volumen) > 0) return { volumen: 0, recordar: Number(volumen) };
  return { volumen: Number(recordado) > 0 ? Number(recordado) : 1, recordar: null };
}

// Por qué la página no aplicó una operación (el mismo mensaje que muestra
// debajo del video, que en el celular tapa la hoja): se vuelve a probar, pura.
// null si la operación sí se puede (la edición estaba bloqueada, por ejemplo).
export function motivoRechazo(doc, nombre, args, info = {}) {
  try {
    operaciones[nombre](doc, ...args, info);
    return null;
  } catch (e) {
    return e?.name === "OperacionInvalida" ? e.message : null;
  }
}

// Lo que dicen el panel y la biblioteca cuando otra pestaña guardó antes (el
// guardado quedó en «conflicto» y la página ya no deja editar): el aviso de
// debajo del video no sirve de nada si la hoja del celular lo tapa.
export function mensajeConflicto() {
  return t("prop.conflicto");
}

// El mensaje para una operación que la página no aplicó: el conflicto si lo
// hay; si no, el porqué de la operación (motivoRechazo) o `otro`.
export function mensajeRechazo(doc, nombre, args, info = {}, {
  conflicto = false, otro = t("prop.rechazo"),
} = {}) {
  if (conflicto) return mensajeConflicto();
  return motivoRechazo(doc, nombre, args, info) ?? otro;
}

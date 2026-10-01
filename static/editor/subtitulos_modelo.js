// La pestaña «Subtítulos» del editor (capa 5a, Task 7; spec D4, D6, D7, D12):
// lo puro — qué fuentes se ofrecen y por qué no, qué archivos pide cada una
// (y cuáles faltan transcribir), en qué estado está el idioma del destino,
// las líneas del listado (con lo corregido y lo que se oyó), qué dice el
// botón y cómo se escribe un tiempo. Sin DOM ni red: lo prueba Node
// (tests/js/subtitulos_modelo.test.mjs); subtitulos_panel.js lo pone en la
// página. Los textos con t() (se traducen al usarse, nunca al cargar). El
// dinero nunca se formatea aquí: el servidor manda `precio` ya escrito.
import { ESTILOS_SUBTITULOS, ID_SONIDO } from "./operaciones.js";
import { colorBase } from "./propiedades_modelo.js";
import { valorDestino } from "./resolver.js";
import { derivar, fuentesDe, materialesDeFuente } from "./subtitulos_fuente.js";
import { ventanas } from "./subtitulos.js";
import { separadorDecimal, t } from "./textos.js";

// El listado agrupa siempre igual, sea cual sea el estilo (la tabla D7 de
// karaoke): de a 4 palabras, menos de 1,8 s y hasta 22 caracteres.
export const LINEA_MAX_PALABRAS = 4;
export const LINEA_MAX_MS = 1800;
export const LINEA_MAX_CARACTERES = 22;

// ---- Fuentes ----

const CLAVE_MATERIAL_RE = /^material:(\d+)$/;

// {tipo} -> "voz" | "sonido" | "material:<id>" (lo que va en el `value` de
// cada opción); lo que no es una fuente, null.
export function claveDeFuente(f) {
  if (f?.tipo === "voz" || f?.tipo === "sonido") return f.tipo;
  const id = Number(f?.material_id);
  return f?.tipo === "material" && Number.isInteger(id) && id > 0 ? `material:${id}` : null;
}

export function fuenteDeClave(clave) {
  if (clave === "voz" || clave === "sonido") return { tipo: clave };
  const m = CLAVE_MATERIAL_RE.exec(String(clave ?? ""));
  const id = m ? Number(m[1]) : 0;
  return id > 0 ? { tipo: "material", material_id: id } : null;
}

// Una voz del guion de la vía automática (borrador.es_voz_de_guion: rol voz
// y `bloque` no vacío): un clip por bloque, cada uno con su material. «La voz»
// ya los cubre a todos; ofrecerlos sueltos daría varios «Audio «Voz»» iguales
// que subtitulan un solo bloque (y nada en otro país del mismo idioma).
const esVozDeGuion = (clip) => clip?.rol_audio === "voz" && Boolean(clip?.bloque);

// Claves de textos.js del nombre de un audio sin nombre propio, por su rol.
const NOMBRE_ROL = { voz: "fila.voz", musica: "fila.musica", efecto: "fila.efecto", grabacion: "fila.grabacion" };

function nombreAudio(m, clip = null) {
  if (m?.nombre) return String(m.nombre);
  return t(NOMBRE_ROL[clip?.rol_audio] ?? "fila.audio");
}

// Las fuentes que se pueden subtitular en el destino que se ve (`resuelto`,
// el documento resuelto): la voz (si hay clips de voz en este destino), el
// sonido de los videos de la principal (si alguno trae sonido: uno todavía
// sin medir cuenta, el servidor salta los mudos) y un «Audio «…»» por cada
// material distinto de los audios de la edición (una canción, un efecto,
// una grabación o una voz con IA; nunca las voces del guion, que van en «La
// voz»). Como en la derivación, una pista oculta o silenciada no cuenta.
// [{clave, etiqueta, disponible, motivo}].
export function fuentesDisponibles(resuelto, materiales = {}) {
  if (!resuelto) return [];
  const mats = materiales ?? {};
  const voz = materialesDeFuente(resuelto, { tipo: "voz" });
  const sonido = materialesDeFuente(resuelto, { tipo: "sonido" });
  const conSonido = sonido.some((id) => mats[id]?.tiene_audio !== false);
  const out = [
    { clave: "voz", etiqueta: t("sub.fuente_voz"), disponible: voz.length > 0, motivo: voz.length ? null : t("sub.sin_voz") },
    { clave: "sonido", etiqueta: t("sub.fuente_sonido"), disponible: conSonido, motivo: conSonido ? null : t("sub.sin_sonido") },
  ];
  const vistos = new Set();
  for (const pista of resuelto.pistas ?? []) {
    if (pista.tipo !== "audio" || pista.id === ID_SONIDO || pista.oculta || pista.silenciada) continue;
    for (const clip of pista.clips ?? []) {
      const id = Number(clip.material_id);
      if (esVozDeGuion(clip) || !Number.isInteger(id) || id <= 0 || vistos.has(id)) continue;
      vistos.add(id);
      out.push({
        clave: `material:${id}`, etiqueta: t("sub.fuente_audio", { nombre: nombreAudio(mats[id], clip) }),
        disponible: true, motivo: null,
      });
    }
  }
  return out;
}

// La opción que queda elegida al repintar: la que eligió la persona (si
// todavía se puede), si no la que el idioma ya usa, si no la primera que se
// puede; null si no hay ninguna.
export function fuentePorDefecto(opciones, estado, previa = null) {
  const se = (clave) => (opciones ?? []).some((o) => o.clave === clave && o.disponible);
  if (previa && se(previa)) return previa;
  if (estado?.clave && se(estado.clave)) return estado.clave;
  return (opciones ?? []).find((o) => o.disponible)?.clave ?? null;
}

// ¿Ya se transcribió? `palabras` (lista, aunque vacía: música sin letra
// cuenta como hecha) o, en un material que llegó sin ellas (la biblioteca no
// las manda), `tiene_palabras`.
const conPalabras = (m) => Array.isArray(m?.palabras);
const transcrito = (m) => conPalabras(m) || m?.tiene_palabras === true;

// Qué archivos pide una fuente en este destino: `todos` (ordenados), los
// `mudos` (videos sin sonido: el servidor los salta), los que `faltan`
// transcribir (se pagan) y los que ya están transcritos en el servidor pero
// cuyas palabras todavía no llegaron a la página (`cargar`: gratis, se piden
// antes de aplicar).
export function pedido(resuelto, clave, materiales = {}) {
  const vacio = { todos: [], faltan: [], mudos: [], cargar: [] };
  const fuente = fuenteDeClave(clave);
  if (!resuelto || !fuente) return vacio;
  const mats = materiales ?? {};
  const todos = materialesDeFuente(resuelto, fuente);
  const mudos = todos.filter((id) => mats[id]?.tipo === "video" && mats[id]?.tiene_audio === false);
  const resto = todos.filter((id) => !mudos.includes(id));
  return {
    todos,
    faltan: resto.filter((id) => !transcrito(mats[id])),
    mudos,
    cargar: resto.filter((id) => transcrito(mats[id]) && !conPalabras(mats[id])),
  };
}

// ---- Estado del idioma del destino (D4) ----

// {tipo, clave, n}: «ninguno» (sin fuentes ni palabras guardadas para este
// destino), «legado» (sin fuentes, con las palabras absolutas del borrador
// automático), «quitados» (`[]`: gana sobre las guardadas) o «derivados»
// (con la clave de su primera fuente). `n` = palabras: las guardadas, o las
// derivadas — de `palabrasPorMaterial` si se da (con «Mostrar» apagado el
// resuelto ya no las trae), si no las del resuelto.
export function estadoPanel(doc, resuelto, palabrasPorMaterial = null) {
  const { idioma, pais } = resuelto?.destino ?? {};
  const sub = doc?.subtitulos ?? {};
  const fuentes = fuentesDe(sub, idioma, pais);
  if (fuentes === null) {
    const guardadas = valorDestino(sub.palabras ?? {}, idioma, pais) ?? [];
    return guardadas.length ? { tipo: "legado", clave: null, n: guardadas.length } : { tipo: "ninguno", clave: null, n: 0 };
  }
  if (!fuentes.length) return { tipo: "quitados", clave: null, n: 0 };
  const n = palabrasPorMaterial ? derivar(resuelto, palabrasPorMaterial).length : (resuelto?.subtitulos?.palabras ?? []).length;
  return { tipo: "derivados", clave: claveDeFuente(fuentes[0]), n };
}

export function textoEstado(estado, materiales = {}) {
  switch (estado?.tipo) {
    case "legado":
      return t("sub.estado_legado");
    case "quitados":
      return t("sub.estado_quitados");
    case "derivados": {
      const n = Number(estado.n) || 0;
      if (estado.clave === "voz") return t("sub.estado_voz", { n });
      if (estado.clave === "sonido") return t("sub.estado_sonido", { n });
      const f = fuenteDeClave(estado.clave);
      return t("sub.estado_audio", { nombre: nombreAudio((materiales ?? {})[f?.material_id]), n });
    }
    default:
      return t("sub.estado_ninguno");
  }
}

// ---- El listado «Lo que dicen los subtítulos» ----

const limpio = (s) => String(s ?? "").split(/\s+/).filter(Boolean).join(" ");

// Las líneas del listado a partir de las palabras derivadas
// (subtitulos_fuente.derivar: con `material_id` e `indice`) o de las de
// legado (sin ellos: de solo lectura). Cada palabra dice si está corregida
// y qué se oyó (`original`, de la transcripción del material; null si no se
// sabe). `ventanas` agrupa sin cambiar el orden, así que cada palabra de una
// línea es la siguiente de la lista.
export function lineasListado(derivadas, materiales = {}) {
  const lista = [...(derivadas ?? [])].sort((a, b) => Number(a.t_ms) - Number(b.t_ms));
  const mats = materiales ?? {};
  let k = 0;
  return ventanas(lista, LINEA_MAX_PALABRAS, LINEA_MAX_MS, LINEA_MAX_CARACTERES).map((v) => ({
    t_ms: v.t_ms,
    dur_ms: v.dur_ms,
    palabras: v.palabras.map(() => {
      const w = lista[k++];
      const conRef = w.material_id !== undefined && w.material_id !== null;
      const transcritas = conRef ? mats[w.material_id]?.palabras : null;
      const oida = Array.isArray(transcritas) ? transcritas[w.indice] : undefined;
      const original = oida === undefined ? null : limpio(oida?.texto);
      return {
        texto: w.texto,
        material_id: conRef ? w.material_id : null,
        indice: conRef ? w.indice : null,
        corregida: original !== null && limpio(w.texto) !== original,
        original,
      };
    }),
  }));
}

// La línea que suena en `tMs` ([t, t + dur)), o -1.
export function lineaEn(lineas, tMs) {
  return (lineas ?? []).findIndex((l) => l.t_ms <= tMs && tMs < l.t_ms + l.dur_ms);
}

// ---- El botón y los tiempos ----

// Lo que dice «Generar subtítulos» (D6): mientras corre, la etapa; mientras
// se calcula el precio o si falló, eso; si no hay nada que pagar, «(gratis)»;
// si no, el precio TAL CUAL lo escribió el servidor.
export function textoBoton({ calculando = false, precio = "", gratis = false, error = false, corriendo = false, etapa = "" } = {}) {
  if (corriendo) return t("sub.generando", { etapa: etapa || "" }).trim();
  if (calculando) return t("sub.calculando");
  if (error) return t("sub.error_precio");
  if (gratis) return t("sub.generar_gratis");
  return t("sub.generar_precio", { precio });
}

// «0:03,2»: minutos, segundos y décimas (cortadas, como un reloj: nunca
// «0:60,0») con el separador del idioma de quien mira.
export function textoTiempo(ms) {
  const decimas = Math.floor(Math.max(0, Number(ms) || 0) / 100);
  const min = Math.floor(decimas / 600);
  const seg = Math.floor((decimas % 600) / 10);
  return `${min}:${String(seg).padStart(2, "0")}${separadorDecimal()}${decimas % 10}`;
}

// ---- Lo que pidió un trabajo pagado (para ponerlo aunque se recargue) ----

// El job_id es uno por edición: el sello (la hora del 202) dice de CUÁL vez es.
// Pasada media hora se descarta: ese trabajo ya terminó o se colgó.
export const ENCARGO_MAX_MS = 30 * 60 * 1000;
const RELOJ_ADELANTADO_MS = 60 * 1000;

// Lo guardado (ya leído del almacenamiento), si es de ese trabajo, tiene su
// forma y su sello es de hace menos de ENCARGO_MAX_MS; si no, null.
export function encargoGuardado(valor, job, ahoraMs = Date.now()) {
  if (!valor || typeof valor !== "object" || valor.job !== job) return null;
  const sello = Number(valor.sello);
  if (!Number.isFinite(sello) || ahoraMs - sello > ENCARGO_MAX_MS || sello - ahoraMs > RELOJ_ADELANTADO_MS) return null;
  if (!/^[a-z]{2}$/.test(String(valor.idioma)) || !fuenteDeClave(valor.clave) || !Array.isArray(valor.ids)) return null;
  return { idioma: valor.idioma, clave: valor.clave, ids: valor.ids.map(Number).filter((id) => Number.isInteger(id) && id > 0) };
}

// El idioma de lo que se dice, por defecto: el del destino que se ve, si se
// puede transcribir; si no, el primero de la lista.
export function idiomaPorDefecto(destino, idiomas) {
  const lista = idiomas ?? [];
  const idioma = String(destino ?? "").split("_")[0];
  return lista.includes(idioma) ? idioma : (lista[0] ?? null);
}

// ---- Estilo, color, altura (D7) ----

const NOMBRE_ESTILO = {
  karaoke: "sub.estilo_karaoke", caja: "sub.estilo_caja", palabra_grande: "sub.estilo_palabra_grande", minimal: "sub.estilo_minimal",
};

export function estilosPanel(estilos) {
  return ESTILOS_SUBTITULOS.map((id) => ({ id, nombre: t(NOMBRE_ESTILO[id]), resalta: Boolean(estilos?.[id]?.resalta) }));
}

const COLORES_RESALTADO = [
  { color: "#FFD400", nombre: "prop.color_amarillo" },
  { color: "#3DDC84", nombre: "sub.color_verde" },
  { color: "#FFFFFF", nombre: "prop.color_blanco" },
];

// Los colores de la palabra que suena: amarillo, verde, blanco y el de la
// marca de la edición (si es un color: `#RRGGBB`, sin la transparencia).
export function coloresResaltado(doc) {
  const lista = COLORES_RESALTADO.map((c) => ({ color: c.color, nombre: t(c.nombre) }));
  const marca = colorBase(doc?.marca?.color, null);
  if (marca && !lista.some((c) => c.color === marca)) lista.push({ color: marca, nombre: t("prop.color_marca") });
  return lista;
}

// El color con que se ve la palabra que suena (el del documento o el del
// estilo); null en un estilo que no resalta. Un estilo desconocido es karaoke.
export function resaltadoElegido(subtitulos, estilos) {
  const id = estilos?.[subtitulos?.estilo_id] ? subtitulos.estilo_id : "karaoke";
  const e = estilos?.[id];
  if (!e?.resalta) return null;
  return colorBase(subtitulos?.resaltado, null) ?? colorBase(e.resaltado, null);
}

// «Altura» (10–90): más alto en el deslizador es más arriba en el video, al
// revés que `posicion` (el centro de la línea, desde arriba: 0,78 = abajo).
const POSICION_DEFECTO = 0.78;

export const POSICIONES = [
  { valor: 0.2, texto: "sub.arriba" },
  { valor: 0.5, texto: "prop.centro" },
  { valor: 0.78, texto: "sub.abajo" },
];

export function alturaDePosicion(posicion) {
  const p = Number.isFinite(Number(posicion)) && posicion !== null ? Number(posicion) : POSICION_DEFECTO;
  return Math.round((1 - p) * 100);
}

export function posicionDeAltura(altura) {
  return Math.round(100 - Number(altura)) / 100;
}

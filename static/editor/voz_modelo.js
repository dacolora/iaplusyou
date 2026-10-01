// La voz en off de la pestaña «Audio» (capa 5a, Task 8; spec D8, D9, D12,
// D13): lo puro. Con qué formato graba el navegador, el reloj de la
// grabación, por qué no se puede grabar, el estado del texto, el filtro de la
// galería, el idioma con que arranca el formulario, lo que dice el botón
// «Crear la voz», lo que se guarda para retomar un trabajo si la página se
// recarga y lo que se dice al agregar. voz_panel.js solo pone esto en el DOM;
// lo prueba tests/js/voz_modelo.test.mjs. No toca document ni window.
//
// El dinero nunca se escribe aquí: el servidor manda `precio` ya escrito (en
// el idioma de quien mira) y el botón lo pone TAL CUAL. El texto de la voz es
// contenido de la persona: nunca pasa por textos.js.
import { t } from "./textos.js";

// Los formatos que prueba MediaRecorder, en orden (D8): opus en webm (Chrome,
// Edge, Firefox), mp4/AAC (Safari; el servidor lo recibe como .m4a), opus en
// ogg y webm sin códec dicho. Las extensiones son las que acepta
// final_edition/biblioteca.EXTENSIONES_GRABACION (tests/test_editor_js.py).
export const FORMATOS_GRABACION = [["audio/webm;codecs=opus", ".webm"], ["audio/mp4", ".m4a"], ["audio/ogg;codecs=opus", ".ogg"], ["audio/webm", ".webm"]];

// Tope de una grabación: 5 minutos (biblioteca.MAX_GRABACION_MS).
export const MAX_GRABACION_MS = 300000;

// El navegador la corta sola UN segundo antes del tope: el reloj pregunta cada
// 250 ms y se pasaría unos ms (fix round 1; el servidor además recorta lo que
// se pase por menos de 2 s, biblioteca.MARGEN_GRABACION_MS).
export const MARGEN_CORTE_MS = 1000;

export function corteGrabacion(maxMs = MAX_GRABACION_MS) {
  return Math.max(0, Number(maxMs) - MARGEN_CORTE_MS);
}

// `esSoportado`: MediaRecorder.isTypeSupported (o null si no existe).
export function elegirGrabacion(esSoportado) {
  if (typeof esSoportado !== "function") return null;
  for (const [mime, ext] of FORMATOS_GRABACION) {
    try {
      if (esSoportado(mime)) return { mime, ext };
    } catch {
      return null;
    }
  }
  return null;
}

// La extensión de lo que de verdad grabó el navegador (MediaRecorder.mimeType
// puede traer el códec, o venir vacío si se creó sin pedir un tipo): webm si
// no se sabe, lo más común.
export function extensionDeMime(mime) {
  const base = String(mime ?? "").toLowerCase().split(";")[0].trim();
  if (base === "audio/mp4") return ".m4a";
  if (base === "audio/ogg") return ".ogg";
  return ".webm";
}

// «0:07», «4:59»: minutos y segundos CORTADOS (un reloj nunca dice 5:00
// antes de tiempo).
export function relojTexto(ms) {
  const s = Math.floor(Math.max(0, Number(ms) || 0) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// «0:07 de 5:00».
export function textoReloj(actualMs, maxMs = MAX_GRABACION_MS) {
  return t("grab.reloj", { actual: relojTexto(actualMs), max: relojTexto(maxMs) });
}

// Por qué este navegador no puede grabar (una CLAVE de textos.js), o null.
// Sin navigator.mediaDevices, casi siempre es una página que no es segura
// (http fuera de localhost); `seguro` (window.isSecureContext), si se sabe,
// lo distingue de un navegador viejo.
export function motivoSinGrabar({ hayMediaDevices = false, hayMediaRecorder = false, formato = null, seguro = null } = {}) {
  if (seguro === false) return "grab.inseguro";
  if (!hayMediaDevices) return seguro === true ? "grab.no_soporta" : "grab.inseguro";
  if (!hayMediaRecorder || !formato) return "grab.no_soporta";
  return null;
}

// El error de getUserMedia, en llano (una CLAVE de textos.js).
const ERRORES_MICROFONO = {
  NotAllowedError: "grab.permiso", SecurityError: "grab.permiso",
  NotFoundError: "grab.sin_micro", OverconstrainedError: "grab.sin_micro",
};

export function mensajeMicrofono(nombreError) {
  return ERRORES_MICROFONO[nombreError] ?? "grab.error";
}

// El texto de la voz: cuántos caracteres lleva (lo que cuenta el `maxlength`
// del campo), si se puede crear y, si no, por qué (una CLAVE).
export function estadoTexto(texto, max) {
  const s = typeof texto === "string" ? texto : "";
  const n = s.length;
  if (!s.trim()) return { n, valido: false, clave: "voz.texto_vacio" };
  if (n > Number(max)) return { n, valido: false, clave: "voz.texto_largo" };
  return { n, valido: true, clave: null };
}

// Los filtros de la galería (las mismas de Crear › Audios): «Todas» no filtra.
export const FILTROS_VOZ = [
  { valor: "", clave: "voz.filtro_todas" },
  { valor: "mujer", clave: "voz.filtro_mujer" },
  { valor: "hombre", clave: "voz.filtro_hombre" },
];

export function filtrarVoces(fichas, genero) {
  const lista = Array.isArray(fichas) ? fichas.filter(Boolean) : [];
  return genero ? lista.filter((f) => f.genero === genero) : lista;
}

// El idioma con que arranca el formulario: el del destino que se ve si la
// voz lo habla; si no, el del proyecto (`defecto`); si tampoco, el primero.
export function idiomaInicial(destino, idiomas, defecto) {
  const lista = Array.isArray(idiomas) ? idiomas : [];
  const delDestino = String(destino ?? "").split("_")[0];
  if (lista.includes(delDestino)) return delDestino;
  if (lista.includes(defecto)) return defecto;
  return lista[0] ?? null;
}

// Lo que dice «Crear la voz» y si se puede tocar (D6: ningún pago sin el
// precio a la vista). Con el precio sin calcular el botón queda ACTIVO: el
// clic solo vuelve a pedir el precio (voz_panel.js nunca crea sin él).
export function botonCrear({ vacio = false, calculando = false, error = false, gratis = false, precio = "",
  corriendo = false, etapa = "", conflicto = false } = {}) {
  if (corriendo) {
    const base = t("voz.creando", { etapa: "" }).trim();
    const nombre = String(etapa ?? "").trim();
    // la primera etapa se llama como el botón («Creando la voz»): no se repite
    const texto = nombre && !base.toLowerCase().startsWith(nombre.toLowerCase()) ? t("voz.creando", { etapa: nombre }).trim() : base;
    return { texto, desactivado: true };
  }
  if (vacio) return { texto: t("voz.texto_vacio"), desactivado: true };
  if (calculando) return { texto: t("voz.calculando"), desactivado: true };
  if (error) return { texto: t("voz.sin_precio"), desactivado: Boolean(conflicto) };
  if (gratis) return { texto: t("voz.crear_gratis"), desactivado: Boolean(conflicto) };
  if (precio) return { texto: t("voz.crear_precio", { precio }), desactivado: Boolean(conflicto) };
  return { texto: t("voz.calculando"), desactivado: true };
}

// Lo que cambia el precio (para no volver a pedirlo si nada cambió): el
// texto como lo cuenta el servidor (espacios juntos), la voz, la velocidad y
// el idioma.
export function firmaPedido({ texto = "", voz = "", velocidad = "", idioma = "" } = {}) {
  const limpio = String(texto ?? "").split(/\s+/).filter(Boolean).join(" ");
  return JSON.stringify([limpio, String(voz ?? ""), String(velocidad ?? ""), String(idioma ?? "")]);
}

// En qué idioma suena una voz que entra (D10, fix round 1): con el del
// destino que se ve SOLO si la voz habla ese idioma (`idiomaVoz`); si habla
// otro, sin idioma (suena en todos) y `habla` dice cuál, para avisarlo. Una
// grabación no dice su idioma: el del destino. Sin destino, sin etiqueta.
export function idiomaDeVoz(idiomaVoz, destino) {
  const delDestino = String(destino ?? "").split("_")[0];
  if (!IDIOMA_RE.test(delDestino)) return { idioma: null, habla: null };
  const habla = IDIOMA_RE.test(String(idiomaVoz ?? "")) ? idiomaVoz : null;
  if (habla && habla !== delDestino) return { idioma: null, habla };
  return { idioma: delDestino, habla: null };
}

// ---- Retomar un trabajo si la página se recarga ----

// El job_id de la voz es uno por edición: el sello (la hora del 202) dice de
// CUÁL vez es, y pasada media hora se descarta (ya terminó o se colgó).
export const ENCARGO_VOZ_MAX_MS = 30 * 60 * 1000;
const RELOJ_ADELANTADO_MS = 60 * 1000;
const CLAVE_VOZ_RE = /^[0-9a-f]{64}$/;
const IDIOMA_RE = /^[a-z]{2}$/;

// Lo guardado (ya leído del almacenamiento): {clave, idioma, habla} si es de
// ese trabajo, tiene su forma y su sello es reciente; si no, null. `idioma` es
// el del clip (idiomaDeVoz: null = suena en todos) y `habla`, el de la voz
// cuando no es el del destino (para avisarlo).
export function encargoVozGuardado(valor, job, ahoraMs = Date.now()) {
  if (!valor || typeof valor !== "object" || valor.job !== job) return null;
  const sello = Number(valor.sello);
  if (!Number.isFinite(sello) || ahoraMs - sello > ENCARGO_VOZ_MAX_MS || sello - ahoraMs > RELOJ_ADELANTADO_MS) return null;
  if (!CLAVE_VOZ_RE.test(String(valor.clave))) return null;
  const idioma = valor.idioma ?? null;
  const habla = valor.habla ?? null;
  if ([idioma, habla].some((i) => i !== null && !IDIOMA_RE.test(String(i)))) return null;
  return { clave: valor.clave, idioma, habla };
}

// ---- Grabar ----

// El nivel del micrófono (0 en silencio, 1 a tope) desde los bytes de
// AnalyserNode.getByteTimeDomainData (128 = silencio): la raíz de la media de
// los cuadrados, un poco realzada para que una voz normal se vea.
export function nivelDe(bytes) {
  const n = bytes?.length ?? 0;
  if (!n) return 0;
  let suma = 0;
  for (let i = 0; i < n; i += 1) {
    const v = (bytes[i] - 128) / 128;
    suma += v * v;
  }
  return Math.min(1, Math.sqrt(suma / n) * 1.8);
}

// La hora local «HH:MM» que viaja con la grabación: el servidor la nombra
// «Grabación 14:32» en el idioma del proyecto.
export function horaLocal(fecha = new Date()) {
  return `${String(fecha.getHours()).padStart(2, "0")}:${String(fecha.getMinutes()).padStart(2, "0")}`;
}

export function nombreArchivo(ext) {
  const valida = FORMATOS_GRABACION.some(([, e]) => e === ext);
  return `grabacion${valida ? ext : ".webm"}`;
}

// El error de subir una grabación, en llano: el del servidor si lo dijo; si
// no, según qué pasó (`red`: no hubo respuesta; `redirigido`: llegó la página
// de entrar).
export function mensajeGrabacionSubida({ status = 0, cuerpo = null, redirigido = false, red = false } = {}) {
  if (red) return t("bib.sin_conexion_subir");
  if (redirigido) return t("bib.sesion_subir");
  if (cuerpo && typeof cuerpo === "object" && typeof cuerpo.error === "string" && cuerpo.error) return cuerpo.error;
  return t("grab.error_subir", { status });
}

// ---- Al agregar ----

// Qué se dice cuando la voz (`tipo` "ia") o la grabación entra en el cabezal:
// si no cupo entera (operaciones.vozCortada dio un número), hasta dónde quedó
// (un aviso: `error`); si habla otro idioma que el del destino
// (`hablaNombre`), que quedó sonando en todos; si no, que entró. Una voz con
// IA ofrece ir a «Subtítulos» (sus palabras ya vienen: ponerlos es gratis; si
// Whisper falló, ahí se generan).
export function avisoAgregada({ tipo = "ia", conPalabras = false, cortadaMs = null, hablaNombre = null } = {}) {
  const ia = tipo === "ia";
  if (Number.isFinite(cortadaMs) && cortadaMs !== null) {
    return { texto: t("voz.cortada", { tiempo: relojTexto(cortadaMs) }), irSubtitulos: ia, error: true };
  }
  if (hablaNombre) return { texto: t("voz.todos_idiomas", { idioma: hablaNombre }), irSubtitulos: ia, error: false };
  if (!ia) return { texto: t("grab.agregada"), irSubtitulos: false, error: false };
  return { texto: t(conPalabras ? "voz.agregada_subtitulos" : "voz.agregada_sin_subtitulos"), irSubtitulos: true, error: false };
}

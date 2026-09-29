// Biblioteca del editor (capa 4b, Task 6): el panel de la izquierda (en el
// celular, la hoja que sube desde abajo) con cuatro pestañas:
//
// - Medios: «Subir» (varios archivos; cada uno con su barra y, si falla, su
//   error en llano debajo), los videos e imágenes del proyecto y, debajo,
//   «Videos de Crear» (las piezas listas; la que todavía no es material se
//   prepara al tocar «+» — gratis — y se agrega sola cuando está).
// - Audio: «Subir audio» y los audios del proyecto (subidos y de Mi música),
//   con «Escuchar» y «+» (entra como música desde el cabezal).
// - Texto: cuatro muestras (Título, Subtítulo, Precio, Llamado) con su estilo;
//   tocar una la pone en el cabezal, la deja elegida y pide el foco para su
//   texto (editor.enfocarTexto: el panel de propiedades lo atiende).
// - Transiciones: las cinco que el render hace; tocar una la pone (500 ms) en
//   el video elegido o en el corte más cercano al cabezal.
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
// Solo toca el DOM de su panel, la línea de tiempo por puntoEn/resaltar y la
// edición por `editor`. No hace nada al importarse (lo prueba Node).
import {
  avisoTransicion, DURACION_TRANSICION_MS, nombreTransicion, pedidoAgregar,
} from "./escala.js";
import * as operaciones from "./operaciones.js";
import { TRANSICIONES } from "./operaciones.js";
import { evaluarRespuesta } from "./pendientes.js";
import { mensajeConflicto } from "./propiedades_modelo.js";
import { t } from "./textos.js";

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
// pieza de Crear: esos están en su sección), Audio (subidos y de Mi música;
// una voz de guion no se agrega a mano) y las piezas de Crear.
export function repartir(bib) {
  const materiales = Array.isArray(bib?.materiales) ? bib.materiales.filter(Boolean) : [];
  const piezas = Array.isArray(bib?.piezas) ? bib.piezas.filter(Boolean) : [];
  const dePieza = new Set(piezas.map((p) => p.material_id).filter((id) => id !== null && id !== undefined));
  return {
    medios: materiales.filter((m) => (m.tipo === "video" || m.tipo === "imagen") && !dePieza.has(m.id)),
    audios: materiales.filter((m) => m.tipo === "audio" && (m.origen === "subida" || m.origen === "musica")),
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
  if (m.tipo === "imagen") return { clase: "imagen", url: m.url, ...forma };
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
// liviana de un video (su tira sale de la misma tarea) y los picos de un audio.
export function faltaPreparar(m) {
  if (m?.tipo === "video") return !m.url_proxy;
  if (m?.tipo === "audio") return m.picos === null || m.picos === undefined;
  return false;
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
};
const ICONO_DE = { video: "video", pieza: "video", imagen: "imagen", audio: "nota", texto: "texto", transicion: "transicion" };
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
  if (m?.tipo === "audio") return t(m.origen === "musica" ? "bib.cancion" : "fila.audio");
  return t(m?.origen === "crear" ? "bib.video_crear" : "fila.video");
}

export class Biblioteca {
  // `contenedor`: #ed-panel-biblioteca (la caja que corre hacia abajo);
  // `pestanas`: la lista de pestañas (la página ya marca la elegida; aquí se
  // muestra su panel); `urls`: las de datos-editor; `linea`: la LineaTiempo.
  constructor({ contenedor, pestanas, urls, editor, linea }) {
    this.contenedor = contenedor;
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
    this.relojPiezas = null;
    this.relojMateriales = null;
    this.arrastre = null;               // {clave, cosa, pointerId, x0, y0, x, y, activo, fantasma, origen, cuadro}
    this.pintarAlSoltar = false;        // llegó algo a mitad de un arrastre: las listas se pintan al soltar
    this.suprimirClic = false;          // el clic que el navegador manda tras soltar un arrastre
    this.escucha = null;                // {clave, audio}
    this.relojMensaje = null;
    this.observador = null;
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
    this._mostrar(pestanas.querySelector('[aria-selected="true"]')?.dataset.panel ?? "medios");
    pestanas.addEventListener("click", (e) => {
      const b = e.target.closest("[data-panel]");
      if (b) this._mostrar(b.dataset.panel);
    });
    editor.escuchar((que) => {
      if (que === "documento") this._pintarMarca();
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
    for (const panel of ["medios", "audio", "texto", "transiciones"]) {
      const s = el("section", "ed-bib-panel", c);
      s.dataset.panel = panel;
      s.hidden = true;
      // en la columna las pestañas van solo con el icono: el panel dice cuál es
      el("h2", "ed-titulo ed-bib-cabeza", s, this.pestanas.querySelector(`[data-panel="${panel}"]`)?.textContent.trim() ?? "");
      this.paneles[panel] = s;
    }
    this.listaSubidas = {};
    this._construirMedios();
    this._construirAudio();
    this._construirTextos();
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
    for (const muestra of textosBiblioteca()) {
      const clave = `t:${muestra.preset}`;
      this.cosas.set(clave, { tipo: "texto", preset: muestra.preset, nombre: muestra.nombre });
      const b = el("button", `ed-bib-texto ed-bib-texto-${muestra.preset}`, g);
      b.type = "button";
      b.dataset.clave = clave;
      b.dataset.arrastrable = "";
      b.setAttribute("aria-label", t("bib.agregar_texto", { nombre: muestra.nombre }));
      el("span", "ed-bib-texto-muestra", b, muestra.nombre);
    }
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

  _mostrar(panel) {
    if (!this.paneles[panel]) return;
    this.panel = panel;
    for (const [k, s] of Object.entries(this.paneles)) s.hidden = k !== panel;
    const nombre = this.pestanas.querySelector(`[data-panel="${panel}"]`)?.textContent.trim();
    if (nombre) this.contenedor.setAttribute("aria-label", nombre);
    if (panel !== "audio") this._pararEscucha();
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
    this.pintarAlSoltar = false;
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
    mini.append(this._botonMas(clave, t("bib.agregar_nombre", { nombre })));
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
    el("span", "ed-bib-audio-detalle", txt, [duracionTexto(m.duracion_ms), m.origen === "musica" ? t("bib.mi_musica") : t("bib.subido")]
      .filter(Boolean).join(" · "));
    const oir = el("button", "btn-sm ed-bib-escuchar", fila);
    oir.type = "button";
    oir.dataset.escuchar = clave;
    this._pintarBotonEscucha(oir, nombre);
    fila.append(this._botonMas(clave, t("bib.agregar_musica", { nombre })));
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
    const mas = objetivo.closest?.("[data-agregar]");
    if (mas) return void this.agregar(mas.dataset.agregar);
    const oir = objetivo.closest?.("[data-escuchar]");
    if (oir) return this._escuchar(oir.dataset.escuchar);
    const quitar = objetivo.closest?.("[data-quitar-subida]");
    if (quitar) return quitar.closest(".ed-bib-subida")?.remove();
    if (objetivo.closest?.("[data-reintentar]")) return void this.cargar();
    const tarjeta = objetivo.closest?.("button[data-clave]");          // un texto o una transición
    if (tarjeta) void this.agregar(tarjeta.dataset.clave);
  }

  // Agrega lo que muestra `clave` en el cabezal (sin `punto`) o donde se
  // soltó (`punto` de LineaTiempo.puntoEn). Una pieza de Crear que todavía no
  // es material se prepara primero y se agrega sola al tenerla.
  agregar(clave, punto = null, cosa = this.cosas.get(clave)) {
    if (!cosa) return false;
    if (cosa.tipo === "pieza") return this._agregarPieza(cosa, punto);
    return this._operar(cosa, punto);
  }

  _operar(cosa, punto) {
    const ed = this.editor;
    if (cosa.material) ed.agregarMateriales({ [cosa.material.id]: cosa.material });   // antes de operar
    const pedido = pedidoAgregar(ed.doc(), cosa, { punto, cabezalMs: ed.tiempo(), seleccion: ed.seleccion });
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
      const aviso = avisoTransicion(ed.doc(), pedido[1], pedido[2], pedido[3] ?? DURACION_TRANSICION_MS);
      this._decir(aviso ?? (cosa.transicion === "corte" ? t("bib.union_corte") : t("bib.en_union", { nombre: cosa.nombre })),
        Boolean(aviso));
    } else if (cosa.tipo === "texto") {
      this._decir(t("bib.texto_agregado"));
      ed.enfocarTexto();
    } else {
      this._decir(t("bib.agregado", { nombre: cosa.nombre }));
    }
    if (cosa.material && faltaPreparar(cosa.material)) this._esperar(cosa.material.id);
    return true;
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
    if (!item || !this.contenedor.contains(item) || e.target.closest("[data-agregar], [data-escuchar]")) return;
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

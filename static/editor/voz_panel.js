// La voz en off, arriba de la pestaña «Audio» de la biblioteca (capa 5a,
// Task 8; spec D8, D9, D10, D12): dos botones que abren su formulario ahí
// mismo, uno a la vez.
//
// - «Voz con IA»: lo que va a decir (con su contador), la galería de voces en
//   dos columnas (Todas · Mujer · Hombre; ▶ escucha la muestra de esa voz en
//   el idioma elegido), la velocidad, el idioma y «Crear la voz» con el precio
//   que calcula el servidor (gratis si esa voz ya existe). Pagar encola el
//   trabajo; la barra lo sigue (y lo retoma si la página se recarga) y, al
//   terminar, trae la voz con sus palabras y la pone en el cabezal como una
//   OPERACIÓN sobre el documento de ese momento (lo editado mientras tanto no
//   se pierde). Sus subtítulos ya están listos: el aviso lleva a «Subtítulos».
// - «Grabar tu voz» (gratis): Grabar/Parar con el reloj y el nivel del
//   micrófono, se detiene sola a los 5 minutos; después se escucha y se usa
//   (se sube con su barra; el servidor la pasa a mp3) o se descarta. El
//   micrófono se suelta al parar, al descartar y al dejar la pestaña.
//
// Las dos entran como VOZ (agacha la música) con el idioma del destino que se
// ve (D10; «Suena en», en propiedades, lo cambia) — salvo una voz con IA que
// habla otro idioma: entra sonando en todos y se avisa (voz_modelo.idiomaDeVoz).
// Lo que se decide es de voz_modelo.js (puro, probado en Node); aquí solo el
// DOM, la red y el micrófono. La edición se toca SOLO por `editor` (pagina_editor.js); con la
// edición cambiada en otra pestaña (`enConflicto`) no se paga ni se agrega
// nada. Mientras la pestaña no se ve no se pide el precio (se pide al
// mostrarse: aviso "biblioteca"). No hace nada al importarse (lo prueba Node).
import { faltaPreparar, INTERVALO_BIBLIOTECA_MS, TOPE_ESPERA_MS } from "./biblioteca.js";
import { mensajeSesion, sesionTerminada } from "./guardado.js";
import { vozCortada } from "./operaciones.js";
import { mensajeConflicto, mensajeRechazo } from "./propiedades_modelo.js";
import { t } from "./textos.js";
import {
  avisoAgregada, botonCrear, corteGrabacion, elegirGrabacion, encargoVozGuardado, estadoTexto, extensionDeMime,
  filtrarVoces, FILTROS_VOZ, firmaPedido, horaLocal, idiomaDeVoz, idiomaInicial, MAX_GRABACION_MS, mensajeGrabacionSubida,
  mensajeMicrofono, motivoSinGrabar, nivelDe, nombreArchivo, textoReloj, tiempoDeEntrada,
} from "./voz_modelo.js";

export const ESPERA_ESTIMAR_MS = 400;
export const INTERVALO_TRABAJO_MS = 1500;
const REINTENTOS_ESTIMAR = 3;           // si el precio no se pudo calcular, se reintenta solo (gratis)
const REINTENTO_ESTIMAR_MS = 8000;
// Sin ninguna respuesta del estado del trabajo durante este rato seguido, se
// deja de preguntar y se pide recargar (la voz sigue en el servidor).
export const SIN_RESPUESTA_MS = 15 * 60 * 1000;
const RELOJ_GRABACION_MS = 250;
const MIB = 1024 * 1024;
const SVG = "http://www.w3.org/2000/svg";
// Iconos (viewBox 24×24, trazo): texto fijo de este módulo.
const ICONOS = {
  ia: '<path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8z"/><path d="M18.5 15l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8z"/>',
  micro: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
};

function el(tag, clase, padre, texto) {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (texto !== undefined) n.textContent = texto;
  if (padre) padre.append(n);
  return n;
}

function boton(clase, padre, texto) {
  const b = el("button", clase, padre, texto);
  b.type = "button";
  return b;
}

function icono(nombre) {
  const s = document.createElementNS(SVG, "svg");
  for (const [k, v] of Object.entries({ class: "ed-voz-icono", viewBox: "0 0 24 24", width: "20", height: "20",
    "aria-hidden": "true", focusable: "false", fill: "none", stroke: "currentColor", "stroke-width": "1.8",
    "stroke-linecap": "round", "stroke-linejoin": "round" })) s.setAttribute(k, v);
  s.innerHTML = ICONOS[nombre];
  return s;
}

export class VozPanel {
  // `contenedor`: la zona de arriba de «Audio» (biblioteca.zona("audio"));
  // `editor`: el de pagina_editor.js; `datos`: los de la página (urls, voces,
  // voz, grabacion, trabajos_vivos, edicion).
  constructor({ contenedor, editor, datos }) {
    this.contenedor = contenedor;
    this.editor = editor;
    this.datos = datos ?? {};
    this.urls = this.datos.urls ?? {};
    this.voces = Array.isArray(this.datos.voces) ? this.datos.voces.filter((f) => f?.nombre) : [];
    this.cfg = this.datos.voz ?? {};
    this.maxCaracteres = Number(this.cfg.max_caracteres) || 3000;
    this.maxGrabacionMs = Number(this.datos.grabacion?.max_ms) || MAX_GRABACION_MS;
    this.maxBytes = Number(this.datos.grabacion?.max_bytes) || 20 * MIB;
    this.abierto = null;                // "ia" | "grabar" | null
    this.filtro = "";
    this.idiomaTocado = false;          // la persona eligió el idioma: otro destino no lo cambia
    this.estimado = null;               // {firma, calculando | error | gratis | precio, reintentos}
    this.turnoEstimar = 0;
    this.relojEstimar = null;
    this.enviando = false;              // el POST de «Crear la voz» va en camino
    this.trabajo = null;                // {job, encargo: {clave, idioma} | null, etapa, progreso, fallos, sinRespuestaDesde}
    this.relojTrabajo = null;
    this.relojMensaje = null;
    this.muestra = null;                // {voz, boton}: la muestra que suena (en this.reproductor)
    this.turnoMuestra = 0;              // la última muestra pedida gana
    this.grab = { estado: "listo" };    // listo | pidiendo | grabando | grabada | subiendo
    this.esperando = new Map();         // material_id -> desde: sus picos (la onda y la agachada de la música)
    this.relojPicos = null;
    this.sucio = true;                  // algo cambió mientras la pestaña no se veía
    if (!contenedor || !editor) return;
    this._construir();
    editor.escuchar((que) => {
      if (que === "biblioteca") this._alMostrar();
      else if (que === "destino") this._alCambiarDestino();
    });
    if (typeof window !== "undefined") window.addEventListener("pagehide", () => this._soltarMicrofono());
    this.pintar();
    void this._retomar();
  }

  // ---- Armar (una vez) ----

  _construir() {
    const c = this.contenedor;
    const raiz = el("div", "ed-voz", c);
    this.raiz = raiz;
    const acciones = el("div", "ed-voz-acciones", raiz);
    this.abrirIA = this._botonAbrir(acciones, "ed-voz-abrir-ia", "ed-voz-ia", "ia", t("voz.titulo_ia"));
    this.abrirGrabar = this._botonAbrir(acciones, "ed-voz-abrir-grabar", "ed-grab", "micro", t("voz.titulo_grabar"));

    // los avisos (los dos formularios): el texto, «Ir a Subtítulos» y lo técnico plegado
    this.cajaMensaje = el("div", "ed-voz-mensaje", raiz);
    this.cajaMensaje.setAttribute("aria-live", "polite");
    this.aviso = el("p", "editor-aviso ed-voz-aviso", this.cajaMensaje);
    this.aviso.id = "ed-voz-aviso";
    this.aviso.hidden = true;
    this.irSubtitulos = boton("btn-sm ed-voz-ir", this.cajaMensaje, t("voz.ir_subtitulos"));
    this.irSubtitulos.id = "ed-voz-ir-subtitulos";
    this.irSubtitulos.hidden = true;
    this.detalle = el("details", "ed-voz-detalle", this.cajaMensaje);
    this.detalle.hidden = true;
    el("summary", "", this.detalle, t("prop.detalle_tecnico"));
    this.detalleTexto = el("pre", "", this.detalle);

    this._construirIA(raiz);
    this._construirGrabar(raiz);

    // escuchas una sola vez (delegación)
    raiz.addEventListener("click", (e) => this._clic(e));
    raiz.addEventListener("change", (e) => this._cambio(e));
    raiz.addEventListener("input", (e) => this._entrada(e));
  }

  _botonAbrir(padre, id, controla, nombreIcono, texto) {
    const b = boton("ed-voz-abrir", padre);
    b.id = id;
    b.setAttribute("aria-expanded", "false");
    b.setAttribute("aria-controls", controla);
    b.append(icono(nombreIcono), el("span", "", null, texto));
    return b;
  }

  _construirIA(raiz) {
    const s = el("section", "ed-voz-bloque", raiz);
    s.id = "ed-voz-ia";
    s.hidden = true;
    s.setAttribute("aria-labelledby", "ed-voz-abrir-ia");
    this.bloqueIA = s;
    // lo que va a decir
    const campo = el("div", "ed-voz-campo", s);
    const lTexto = el("label", "ed-voz-etiqueta", campo, t("voz.texto"));
    lTexto.htmlFor = "ed-voz-texto";
    this.texto = el("textarea", "", campo);
    Object.assign(this.texto, { id: "ed-voz-texto", rows: 4, maxLength: this.maxCaracteres });
    this.texto.setAttribute("aria-describedby", "ed-voz-contador");
    this.texto.spellcheck = true;
    this.contador = el("small", "ed-voz-contador", campo);
    this.contador.id = "ed-voz-contador";
    // la galería (el fieldset y su leyenda agrupan los radios de las tarjetas)
    const fs = el("fieldset", "ed-voz-campo", s);
    const leyenda = el("legend", "", fs, t("voz.elige"));
    leyenda.id = "ed-voz-elige";
    this.filtros = el("div", "ed-voz-filtro", fs);
    this.filtros.id = "ed-voz-filtro";
    this.botonesFiltro = FILTROS_VOZ.map((f) => {
      const b = boton("btn-sm", this.filtros, t(f.clave));
      b.dataset.filtro = f.valor;
      b.setAttribute("aria-pressed", String(f.valor === this.filtro));
      return b;
    });
    this.lista = el("div", "ed-voz-voces", fs);
    this.lista.id = "ed-voz-voces";
    this.tarjetas = this.voces.map((f, i) => {
      const tarjeta = el("div", "ed-voz-voz", this.lista);
      tarjeta.dataset.voz = f.nombre;
      tarjeta.dataset.genero = f.genero ?? "";
      const l = el("label", "ed-voz-elegir", tarjeta);
      const r = el("input", "", l);
      Object.assign(r, { type: "radio", name: "ed-voz-voz", value: f.nombre, checked: i === 0 });
      el("span", "ed-voz-nombre", l, f.nombre);
      el("small", "ed-voz-tono", l, [f.genero_nombre, f.tono].filter(Boolean).join(" · "));
      const play = boton("ed-voz-play", tarjeta, "▶");
      play.dataset.muestra = f.nombre;
      play.setAttribute("aria-label", t("voz.escuchar", { voz: f.nombre }));
      play.title = play.getAttribute("aria-label");
      play.setAttribute("aria-pressed", "false");
      return tarjeta;
    });
    // velocidad e idioma
    const fila = el("div", "ed-voz-fila", s);
    const cVel = el("div", "ed-voz-campo", fila);
    const lVel = el("label", "ed-voz-etiqueta", cVel, t("voz.velocidad"));
    lVel.htmlFor = "ed-voz-velocidad";
    this.selVelocidad = el("select", "", cVel);
    this.selVelocidad.id = "ed-voz-velocidad";
    for (const [clave, nombre] of Object.entries(this.cfg.velocidades ?? {})) this.selVelocidad.append(new Option(nombre, clave));
    if ([...this.selVelocidad.options].some((o) => o.value === "normal")) this.selVelocidad.value = "normal";
    const cIdioma = el("div", "ed-voz-campo", fila);
    const lIdioma = el("label", "ed-voz-etiqueta", cIdioma, t("voz.idioma"));
    lIdioma.htmlFor = "ed-voz-idioma";
    this.selIdioma = el("select", "", cIdioma);
    this.selIdioma.id = "ed-voz-idioma";
    const nombres = this.cfg.nombres_idioma ?? {};
    for (const i of this.cfg.idiomas ?? []) this.selIdioma.append(new Option(nombres[i] ?? i, i));
    this._ponerIdiomaInicial();
    // las muestras suenan en UN solo <audio> (Safari solo deja sonar el que ya
    // sonó con un toque); si el navegador no lo deja sonar solo, se muestran
    // sus controles para tocar ▶ ahí
    this.reproductor = el("audio", "ed-voz-muestra", s);
    this.reproductor.id = "ed-voz-muestra";
    this.reproductor.preload = "none";
    this.reproductor.hidden = true;
    this.reproductor.addEventListener("ended", () => this._pararMuestra());
    // «Crear la voz» y su barra
    this.crearBoton = boton("btn-generar ed-voz-crear", s);
    this.crearBoton.id = "ed-voz-crear";
    this.progreso = el("progress", "ed-voz-progreso", s);
    this.progreso.id = "ed-voz-progreso";
    this.progreso.max = 100;
    this.progreso.hidden = true;
    this.progreso.setAttribute("aria-labelledby", "ed-voz-crear");
  }

  _construirGrabar(raiz) {
    const s = el("section", "ed-grab", raiz);
    s.id = "ed-grab";
    s.hidden = true;
    s.setAttribute("aria-labelledby", "ed-voz-abrir-grabar");
    this.bloqueGrab = s;
    this.motivo = el("p", "ed-voz-nota ed-grab-motivo", s);
    this.motivo.id = "ed-grab-motivo";
    this.motivo.hidden = true;
    const controles = el("div", "ed-grab-controles", s);
    this.grabarBoton = boton("btn-generar ed-grab-grabar", controles, t("grab.grabar"));
    this.grabarBoton.id = "ed-grab-grabar";
    this.pararBoton = boton("btn-sm ed-grab-parar", controles, t("grab.parar"));
    this.pararBoton.id = "ed-grab-parar";
    this.pararBoton.hidden = true;
    this.reloj = el("span", "ed-grab-reloj", controles, textoReloj(0, this.maxGrabacionMs));
    this.reloj.id = "ed-grab-reloj";
    this.reloj.setAttribute("role", "timer");
    this.nivel = el("div", "ed-grab-nivel", s);
    this.nivel.id = "ed-grab-nivel";
    for (const [k, v] of Object.entries({ role: "meter", "aria-label": t("grab.nivel"), "aria-valuemin": "0",
      "aria-valuemax": "100", "aria-valuenow": "0" })) this.nivel.setAttribute(k, v);
    this.nivelBarra = el("span", "ed-grab-nivel-barra", this.nivel);
    // lo grabado: escucharlo, usarlo o descartarlo
    this.resultado = el("div", "ed-grab-resultado", s);
    this.resultado.hidden = true;
    const lEscuchar = el("p", "ed-voz-nota", this.resultado, t("grab.escuchala"));
    lEscuchar.id = "ed-grab-escuchala";
    this.escuchar = el("audio", "", this.resultado);
    this.escuchar.id = "ed-grab-escuchar";
    this.escuchar.controls = true;
    this.escuchar.preload = "metadata";
    this.escuchar.setAttribute("aria-labelledby", "ed-grab-escuchala");
    const acc = el("div", "ed-grab-acciones", this.resultado);
    this.usarBoton = boton("btn-generar ed-grab-usar", acc, t("grab.usar"));
    this.usarBoton.id = "ed-grab-usar";
    this.descartarBoton = boton("btn-sm ed-grab-descartar", acc, t("grab.descartar"));
    this.descartarBoton.id = "ed-grab-descartar";
    // la subida
    this.subida = el("div", "ed-grab-subida", s);
    this.subida.hidden = true;
    this.subidaTexto = el("span", "", this.subida);
    this.subidaTexto.id = "ed-grab-progreso-texto";
    this.subidaBarra = el("progress", "ed-grab-progreso", this.subida);
    this.subidaBarra.id = "ed-grab-progreso";
    this.subidaBarra.max = 1;
    this.subidaBarra.setAttribute("aria-labelledby", "ed-grab-progreso-texto");
  }

  _ponerIdiomaInicial() {
    if (this.idiomaTocado || !this.selIdioma) return;
    const i = idiomaInicial(this.editor.destino?.(), this.cfg.idiomas ?? [], this.cfg.idioma_defecto);
    if (i) this.selIdioma.value = i;
  }

  // ---- Pintar ----

  // ¿Se ve? Oculta (otro panel de la biblioteca) o en la hoja del celular
  // cerrada (visibility: hidden), no.
  _visible() {
    if (!this.raiz?.isConnected || this.raiz.closest("[hidden]")) return false;
    return typeof this.raiz.checkVisibility === "function" ? this.raiz.checkVisibility({ visibilityProperty: true }) : true;
  }

  pintar() {
    if (!this.raiz) return;
    for (const [b, cual] of [[this.abrirIA, "ia"], [this.abrirGrabar, "grabar"]]) {
      b.setAttribute("aria-expanded", String(this.abierto === cual));
    }
    this.bloqueIA.hidden = this.abierto !== "ia";
    this.bloqueGrab.hidden = this.abierto !== "grabar";
    if (!this._visible()) {             // se pide el precio al mostrarse (aviso "biblioteca")
      this.sucio = true;
      this._pintarCrear();
      return;
    }
    this.sucio = false;
    if (this.abierto === "ia") this._pedirEstimado();
    this._pintarTexto();
    this._pintarCrear();
    this._pintarGrabar();
  }

  _pedido() {
    return {
      texto: this.texto.value, voz: this._vozElegida(), velocidad: this.selVelocidad.value || "normal", idioma: this.selIdioma.value,
    };
  }

  _vozElegida() {
    return this.lista.querySelector('input[name="ed-voz-voz"]:checked')?.value ?? this.voces[0]?.nombre ?? "";
  }

  _pintarTexto() {
    const est = estadoTexto(this.texto.value, this.maxCaracteres);
    this.contador.textContent = est.clave === "voz.texto_largo" ? t(est.clave, { max: this.maxCaracteres })
      : t("voz.contador", { n: est.n, max: this.maxCaracteres });
    this.contador.classList.toggle("error", est.clave === "voz.texto_largo");
  }

  _pintarCrear() {
    if (!this.crearBoton) return;
    const est = estadoTexto(this.texto.value, this.maxCaracteres);
    const corriendo = Boolean(this.trabajo) || this.enviando;
    const e = this.estimado;
    const vigente = e && e.firma === firmaPedido(this._pedido()) ? e : null;
    const b = !corriendo && !est.valido
      ? { texto: t(est.clave, { max: this.maxCaracteres }), desactivado: true }
      : botonCrear({
        corriendo, etapa: this.trabajo?.etapa ?? "", calculando: Boolean(vigente?.calculando) || (!vigente && est.valido),
        error: Boolean(vigente?.error), gratis: Boolean(vigente?.gratis), precio: vigente?.precio ?? "",
        conflicto: this._enConflicto(),
      });
    this.crearBoton.textContent = b.texto;
    this.crearBoton.disabled = b.desactivado;
    this.progreso.hidden = !this.trabajo;
    if (this.trabajo) this.progreso.value = Math.max(0, Math.min(100, Number(this.trabajo.progreso) || 0));
  }

  _pintarGrabar() {
    const g = this.grab;
    this.bloqueGrab.dataset.estado = g.estado;
    const motivo = this._motivoSinGrabar();
    this.motivo.textContent = motivo ? t(motivo) : "";
    this.motivo.hidden = !motivo;
    const grabando = g.estado === "grabando";
    const conGrabacion = g.estado === "grabada" || g.estado === "subiendo";
    this.grabarBoton.hidden = grabando || conGrabacion;
    this.grabarBoton.disabled = Boolean(motivo) || g.estado === "pidiendo";
    if (motivo) this.grabarBoton.setAttribute("aria-describedby", "ed-grab-motivo");
    else this.grabarBoton.removeAttribute("aria-describedby");
    this.pararBoton.hidden = !grabando;
    this.nivel.hidden = !grabando;
    this.resultado.hidden = !conGrabacion;
    this.usarBoton.disabled = g.estado === "subiendo";
    this.descartarBoton.disabled = g.estado === "subiendo";
    this.subida.hidden = g.estado !== "subiendo";
    if (!grabando && !conGrabacion) this.reloj.textContent = textoReloj(0, this.maxGrabacionMs);
  }

  _decir(texto, error = false, { irSubtitulos = false } = {}) {
    clearTimeout(this.relojMensaje);
    this.aviso.textContent = texto || "";
    this.aviso.hidden = !texto;
    this.aviso.classList.toggle("error", Boolean(texto) && error);
    this.irSubtitulos.hidden = !texto || !irSubtitulos;
    if (texto) this.relojMensaje = setTimeout(() => this._decir(""), irSubtitulos ? 20000 : error ? 12000 : 6000);
    if (!error) this._detalle("");
  }

  // Lo técnico (el código de la respuesta, el error tal cual) va plegado.
  _detalle(texto) {
    this.detalleTexto.textContent = texto || "";
    this.detalle.hidden = !texto;
    if (!texto) this.detalle.open = false;
  }

  _enConflicto() {
    return Boolean(this.editor.enConflicto?.());
  }

  // La biblioteca cambió de pestaña: si esta se ve, se pone al día; si se
  // dejó de ver, el micrófono se suelta (lo grabado queda para escucharlo) y
  // la muestra se calla.
  _alMostrar() {
    if (this._visible()) {
      if (this.sucio) this.pintar();
      return;
    }
    this._pararMuestra();
    if (this.grab.estado === "grabando") this.parar();
  }

  _alCambiarDestino() {
    this._ponerIdiomaInicial();
    this.pintar();
  }

  // ---- Lo que hace la persona ----

  _clic(e) {
    const b = e.target.closest?.("button");
    if (!b || !this.raiz.contains(b)) return;
    if (e.detail > 0) b.blur();           // con el mouse el foco no se queda (Espacio, S o Supr lo volverían a usar)
    if (b === this.abrirIA) return this._abrir("ia");
    if (b === this.abrirGrabar) return this._abrir("grabar");
    if (b === this.irSubtitulos) {
      this._decir("");
      return this.editor.mostrarBiblioteca?.("subtitulos");
    }
    if (b.dataset.filtro !== undefined) return this._filtrar(b.dataset.filtro);
    if (b.dataset.muestra) return void this._escucharMuestra(b.dataset.muestra, b);
    if (b === this.crearBoton) return void this.crear();
    if (b === this.grabarBoton) return void this.grabar();
    if (b === this.pararBoton) return this.parar();
    if (b === this.usarBoton) return this.usar();
    if (b === this.descartarBoton) return this.descartar();
  }

  _cambio(e) {
    const n = e.target;
    if (n.name === "ed-voz-voz") {
      this._pararMuestra();
      this.pintar();
    } else if (n === this.selIdioma) {
      this.idiomaTocado = true;
      this._pararMuestra();
      this.pintar();
    } else if (n === this.selVelocidad) {
      this.pintar();
    }
  }

  _entrada(e) {
    if (e.target !== this.texto) return;
    this._pintarTexto();
    this._pedirEstimado();
    this._pintarCrear();
  }

  // Uno a la vez: tocar el abierto lo cierra. Cerrar «Grabar» mientras graba
  // para la grabación (y suelta el micrófono).
  _abrir(cual) {
    const nuevo = this.abierto === cual ? null : cual;
    if (this.abierto === "grabar" && nuevo !== "grabar" && this.grab.estado === "grabando") this.parar();
    if (nuevo !== "ia") this._pararMuestra();
    this.abierto = nuevo;
    this.pintar();
    if (nuevo === "ia" && !this.texto.value && window.matchMedia?.("(pointer: fine)").matches) this.texto.focus({ preventScroll: true });
  }

  _filtrar(valor) {
    this.filtro = valor;
    for (const b of this.botonesFiltro) b.setAttribute("aria-pressed", String(b.dataset.filtro === valor));
    const visibles = new Set(filtrarVoces(this.voces, valor).map((f) => f.nombre));
    for (const tarjeta of this.tarjetas) tarjeta.hidden = !visibles.has(tarjeta.dataset.voz);
    // la elegida quedó oculta: se elige la primera que se ve
    if (!visibles.has(this._vozElegida())) {
      const primera = this.tarjetas.find((x) => !x.hidden)?.querySelector("input");
      if (primera) primera.checked = true;
      this._pararMuestra();
    }
    this.pintar();
  }

  // ---- La muestra de una voz (gratis: la paga Creatv una vez por voz e idioma) ----

  async _escucharMuestra(voz, boton) {
    if (this.muestra?.voz === voz) return this._pararMuestra();   // tocarla otra vez la calla
    this._pararMuestra();
    const turno = ++this.turnoMuestra;
    boton.setAttribute("aria-busy", "true");
    boton.title = t("bib.cargando");
    const fd = new FormData();
    fd.append("voz", voz);
    fd.append("idioma", this.selIdioma.value);
    let r = null;
    let j = null;
    try {
      r = await fetch(this.urls.muestra_voz, {
        method: "POST", body: fd, credentials: "same-origin", headers: { Accept: "application/json", "X-Requested-With": "fetch" },
      });
      if (!sesionTerminada(r)) j = await r.json().catch(() => null);
    } catch {
      r = null;
    }
    boton.removeAttribute("aria-busy");
    boton.title = boton.getAttribute("aria-label") ?? "";
    if (turno !== this.turnoMuestra) return;                      // otra muestra, o la persona se fue
    if (r && sesionTerminada(r)) return this._decir(mensajeSesion(), true);
    if (!r) return this._decir(t("sub.sin_conexion"), true);
    if (!r.ok || !j?.ok || !j.url) {
      this._decir(typeof j?.error === "string" && j.error ? j.error : t("voz.no_muestra"), true);
      return this._detalle(`HTTP ${r.status}`);
    }
    const audio = this.reproductor;
    this.muestra = { voz, boton };
    boton.setAttribute("aria-pressed", "true");
    audio.src = j.url;
    audio.setAttribute("aria-label", boton.getAttribute("aria-label") ?? "");
    audio.play().catch(() => {
      // el navegador no la deja sonar sola (Safari, si la muestra tardó): sus
      // controles, para tocar ▶ ahí mismo
      if (this.muestra?.voz !== voz) return;
      audio.controls = true;
      audio.hidden = false;
    });
  }

  _pararMuestra() {
    this.turnoMuestra += 1;                                       // una que todavía se pedía ya no suena
    const m = this.muestra;
    if (!m) return;
    this.muestra = null;
    m.boton.setAttribute("aria-pressed", "false");
    const audio = this.reproductor;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    audio.controls = false;
    audio.hidden = true;
  }

  // ---- El precio (D6: ningún pago sin un clic en un botón con el precio) ----

  // Pide el precio 400 ms después del último cambio de texto, voz, velocidad
  // o idioma; una respuesta vieja (algo cambió) se descarta. Con el texto
  // vacío no se pide nada. `reintentosForzados`: un clic de la persona.
  _pedirEstimado(forzar = false, reintentosForzados = null) {
    if (this.abierto !== "ia" || !this._visible()) {
      this.sucio = true;
      return;
    }
    const pedido = this._pedido();
    const firma = firmaPedido(pedido);
    if (!estadoTexto(pedido.texto, this.maxCaracteres).valido || !pedido.voz || !pedido.idioma) {
      clearTimeout(this.relojEstimar);
      this.turnoEstimar += 1;
      this.estimado = null;
      return;
    }
    if (!forzar && this.estimado?.firma === firma) return;
    clearTimeout(this.relojEstimar);
    const turno = ++this.turnoEstimar;
    const reintentos = reintentosForzados ?? (forzar && this.estimado?.firma === firma ? (this.estimado.reintentos ?? 0) : 0);
    this.estimado = { firma, calculando: true, reintentos };
    this.relojEstimar = setTimeout(() => void this._estimar(firma, pedido, turno, reintentos), ESPERA_ESTIMAR_MS);
  }

  async _estimar(firma, pedido, turno, reintentos) {
    let res;
    try {
      const { r, j } = await this._pedirJSON(this.urls.voz_estimar, pedido);
      if (r.ok && j && typeof j === "object" && j.ya_existe) res = { firma, gratis: true };
      else if (r.ok && j && typeof j === "object" && j.usd !== null && j.usd !== undefined && j.precio) {
        res = { firma, precio: String(j.precio) };
      } else res = { firma, error: true, reintentos };
    } catch {
      res = { firma, error: true, reintentos };
    }
    if (turno !== this.turnoEstimar) return;
    this.estimado = res;
    this._pintarCrear();
    if (res.error && reintentos < REINTENTOS_ESTIMAR) {
      this.estimado.reintentos = reintentos + 1;
      this.relojEstimar = setTimeout(() => {
        if (this.estimado?.firma === firma && this.estimado.error) {
          this._pedirEstimado(true);
          this._pintarCrear();
        }
      }, REINTENTO_ESTIMAR_MS);
    }
  }

  async _pedirJSON(url, cuerpo = undefined) {
    const opciones = { method: cuerpo === undefined ? "GET" : "POST", credentials: "same-origin", headers: { Accept: "application/json" } };
    if (cuerpo !== undefined) {
      opciones.headers["Content-Type"] = "application/json";
      opciones.body = JSON.stringify(cuerpo);
    }
    const r = await fetch(url, opciones);
    const sesion = sesionTerminada(r);
    const j = sesion ? null : await r.json().catch(() => null);
    return { r, j, sesion };
  }

  // ---- Crear la voz ----

  async crear() {
    if (this.trabajo || this.enviando) return;
    if (this._enConflicto()) return this._decir(mensajeConflicto(), true);
    const tMs = this.editor.tiempo?.() ?? null;          // el cabezal del clic: se guarda con el trabajo
    const pedido = this._pedido();
    if (!estadoTexto(pedido.texto, this.maxCaracteres).valido) return this.texto.focus();
    const e = this.estimado;
    if (!e || e.firma !== firmaPedido(pedido) || e.calculando) {          // sin precio a la vista no se paga
      this._pedirEstimado();
      this._pintarCrear();
      return;
    }
    if (e.error) {                                                         // se vuelve a pedir el precio, nada más
      this._pedirEstimado(true, REINTENTOS_ESTIMAR);
      this._pintarCrear();
      return;
    }
    // en qué idioma suena: el del destino solo si la voz lo habla (si no, en todos)
    const { idioma, habla } = idiomaDeVoz(pedido.idioma, this.editor.destino?.());
    this._decir("");
    this.enviando = true;
    this._pintarCrear();
    let res;
    try {
      res = await this._pedirJSON(this.urls.voz, pedido);
    } catch (err) {
      this.enviando = false;
      this._pintarCrear();
      this._decir(t("sub.sin_conexion"), true);
      this._detalle(String(err?.message ?? err ?? ""));
      return;
    }
    this.enviando = false;
    const { r, j, sesion } = res;
    if (sesion) {
      this._pintarCrear();
      return this._decir(mensajeSesion(), true);
    }
    if (r.status === 202 && j?.job_id && j?.clave) return this.seguir(j.job_id, { clave: j.clave, idioma, habla, tMs });
    this._pintarCrear();
    if (r.ok && j?.material) {                                             // ya existía con sus palabras: gratis
      this._agregar(j.material, { tipo: "ia", idioma, habla });
      this._pedirEstimado(true);
      return;
    }
    this._decir(typeof j?.error === "string" && j.error ? j.error : t("voz.fallo"), true);
    this._detalle(`HTTP ${r.status}`);
  }

  // Sigue el trabajo de la voz (el que se acaba de encolar o el que ya
  // corría al abrir la página) preguntando cada 1,5 s; `encargo` dice qué
  // traer al terminar (null si no se sabe: se pidió en otra pestaña).
  // `nuevo`: recién encolado (se guarda con su sello y con `tMs`, el cabezal
  // del clic, para que al retomar tras recargar la voz entre ahí y no en
  // 0:00; mientras la página sigue abierta entra en el cabezal de ese momento,
  // como siempre).
  seguir(jobId, encargo = null, { nuevo = true } = {}) {
    if (!jobId) return;
    clearTimeout(this.relojTrabajo);
    const enVista = encargo && nuevo ? { ...encargo, tMs: null } : encargo;
    this.trabajo = { job: jobId, encargo: enVista, etapa: "", progreso: 0, fallos: 0, sinRespuestaDesde: null };
    if (encargo && nuevo) this._guardarEncargo(jobId, encargo);
    this._pintarCrear();
    void this._sondear();
  }

  async _sondear() {
    const tr = this.trabajo;
    if (!tr) return;
    let j = null;
    try {
      const url = String(this.urls.estado_trabajo ?? "").replace("__JOB__", encodeURIComponent(tr.job));
      const r = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (r.ok && !sesionTerminada(r)) j = await r.json().catch(() => null);
    } catch {
      j = null;
    }
    if (this.trabajo !== tr) return;
    if (!j || typeof j !== "object") {                         // sin red o algo raro: se vuelve a preguntar, más lento
      tr.fallos += 1;
      tr.sinRespuestaDesde ??= Date.now();
      if (Date.now() - tr.sinRespuestaDesde >= SIN_RESPUESTA_MS) {   // ya no se sabe nada: se deja de preguntar
        this.trabajo = null;
        this._pintarCrear();
        this._decir(t("voz.sin_respuesta"), true);
        return;
      }
      this.relojTrabajo = setTimeout(() => void this._sondear(), INTERVALO_TRABAJO_MS * (tr.fallos > 3 ? 4 : 1));
      return;
    }
    tr.fallos = 0;
    tr.sinRespuestaDesde = null;
    if (j.estado === "en_progreso") {
      tr.etapa = typeof j.etapa === "string" ? j.etapa : "";
      tr.progreso = Number(j.progreso) || 0;
      this._pintarCrear();
      this.relojTrabajo = setTimeout(() => void this._sondear(), INTERVALO_TRABAJO_MS);
      return;
    }
    // terminó: bien, con error o ya no se sabe de él. Lo guardado para retomar
    // se borra solo cuando la voz entró en la edición: si algo falla antes, al
    // recargar se vuelve a intentar (gratis: la voz ya está creada).
    this.trabajo = null;
    this._pintarCrear();
    if (j.estado === "error") {
      this._decir(j.mensaje ? t("voz.error", { mensaje: String(j.mensaje) }) : t("voz.fallo"), true);
      return;
    }
    // sin lo que pidió (otra pestaña, o sin almacenamiento) no se sabe qué voz traer
    if (!tr.encargo) return this._decir(t("voz.terminada"));
    if (await this._traerYAgregar(tr.encargo)) this._olvidarEncargo();
    if (this.abierto === "ia") this._pedirEstimado(true);              // esa voz ya existe: «gratis»
  }

  // Trae (gratis) la voz terminada con sus palabras y la pone en el cabezal.
  // `callado`: al abrir la página, una voz que ya no existe no se anuncia.
  async _traerYAgregar(encargo, { callado = false } = {}) {
    let res;
    try {
      res = await this._pedirJSON(String(this.urls.voz_material ?? "").replace("__CLAVE__", encodeURIComponent(encargo.clave)));
    } catch (err) {
      if (callado) return false;
      this._decir(t("sub.sin_conexion"), true);
      this._detalle(String(err?.message ?? err ?? ""));
      return false;
    }
    const { r, j, sesion } = res;
    if (sesion) {
      if (!callado) this._decir(mensajeSesion(), true);
      return false;
    }
    if (!r.ok || !j?.material) {
      if (callado) return false;
      this._decir(typeof j?.error === "string" && j.error ? j.error : t("voz.fallo"), true);
      this._detalle(`HTTP ${r.status}`);
      return false;
    }
    return this._agregar(j.material, { tipo: "ia", idioma: encargo.idioma ?? null, habla: encargo.habla ?? null,
                                       tMs: encargo.tMs ?? null });
  }

  // Pone una voz (o una grabación) en el cabezal, en una pista de voz, con su
  // idioma (idiomaDeVoz: el del destino que se veía, o null si la voz habla
  // otro — `habla` —; D10), como una operación sobre el documento de AHORA;
  // dice si no cupo entera o si quedó sonando en todos los idiomas. `tMs`:
  // dónde entra una voz retomada tras recargar (tiempoDeEntrada); sin él, el
  // cabezal de ahora.
  _agregar(material, { tipo, idioma = null, habla = null, tMs = null }) {
    const ed = this.editor;
    if (!material || material.id === undefined || material.id === null) return false;
    if (this._enConflicto()) {
      this._decir(mensajeConflicto(), true);
      return false;
    }
    ed.agregarMateriales({ [material.id]: material });       // antes de operar
    const antes = ed.doc();
    const args = [material, tiempoDeEntrada({ tMs }, ed.tiempo()), { rol: "voz", idioma }];
    if (!ed.operar("agregarAudio", ...args)) {
      this._decir(mensajeRechazo(ed.doc(), "agregarAudio", args, ed.info(), { conflicto: this._enConflicto() }), true);
      return false;
    }
    const cortadaMs = vozCortada(antes, ed.doc(), ed.seleccion, ed.info());
    const conPalabras = Array.isArray(material.palabras) && material.palabras.length > 0;
    const hablaNombre = habla ? (this.cfg?.nombres_idioma?.[habla] ?? habla) : null;
    const aviso = avisoAgregada({ tipo, conPalabras, cortadaMs, hablaNombre });
    this._decir(aviso.texto, aviso.error, { irSubtitulos: aviso.irSubtitulos });
    if (faltaPreparar(material)) this._esperarPicos(material.id);
    return true;
  }

  // La onda y la agachada de la música necesitan los picos, que el servidor
  // prepara aparte (gratis): se pregunta cada 3 s, hasta 5 min.
  _esperarPicos(id) {
    if (!this.esperando.has(id)) this.esperando.set(id, Date.now());
    if (this.relojPicos) return;
    this.relojPicos = setTimeout(async () => {
      try {
        await this._revisarPicos();
      } finally {
        this.relojPicos = null;
        if (this.esperando.size) this._esperarPicos([...this.esperando.keys()][0]);
      }
    }, INTERVALO_BIBLIOTECA_MS);
  }

  async _revisarPicos() {
    const ahora = Date.now();
    for (const [id, desde] of [...this.esperando]) if (ahora - desde > TOPE_ESPERA_MS) this.esperando.delete(id);
    if (!this.esperando.size || !this.urls.materiales_por_id) return;
    const ids = [...this.esperando.keys()];
    let res;
    try {
      res = await this._pedirJSON(`${this.urls.materiales_por_id}?ids=${ids.join(",")}&palabras=1`);
    } catch {
      return;
    }
    if (res.sesion) {
      this.esperando.clear();
      return;
    }
    const recibidos = res.r.ok ? res.j?.materiales ?? {} : {};
    const listos = {};
    for (const id of ids) {
      const m = recibidos[id];
      if (m && !faltaPreparar(m)) {
        listos[id] = m;
        this.esperando.delete(id);
      }
    }
    if (Object.keys(listos).length) this.editor.agregarMateriales(listos);
  }

  // ---- Retomar tras recargar ----

  // Qué pidió un trabajo, para ponerlo aunque la página se recargue mientras
  // corre (solo en esta pestaña), con su sello: el job_id es uno por edición y
  // uno guardado de hace más de media hora se descarta (encargoVozGuardado).
  _claveAlmacen() {
    return `ed-voz-trabajo:${this.datos.edicion?.id ?? ""}`;
  }

  _guardarEncargo(job, encargo) {
    try {
      sessionStorage.setItem(this._claveAlmacen(), JSON.stringify({ job, sello: Date.now(), ...encargo }));
    } catch { /* sin almacenamiento: no pasa nada */ }
  }

  _leerEncargo() {
    try {
      return JSON.parse(sessionStorage.getItem(this._claveAlmacen()) ?? "null");
    } catch {
      return null;
    }
  }

  _olvidarEncargo() {
    try {
      sessionStorage.removeItem(this._claveAlmacen());
    } catch { /* nada */ }
  }

  // Al abrir: si la voz de esta edición se sigue creando, se retoma su barra;
  // si terminó justo mientras la página se recargaba, se trae y se pone (lo
  // guardado se borra solo cuando entró; si no, vence a la media hora).
  async _retomar() {
    const vivo = this.datos.trabajos_vivos?.voz;
    const guardado = this._leerEncargo();
    if (vivo) {
      this.seguir(vivo, encargoVozGuardado(guardado, vivo, Date.now()), { nuevo: false });
      return;
    }
    const encargo = guardado ? encargoVozGuardado(guardado, guardado.job, Date.now()) : null;
    if (encargo && await this._traerYAgregar(encargo, { callado: true })) this._olvidarEncargo();
  }

  // ---- Grabar con el micrófono (gratis) ----

  _formatoGrabacion() {
    if (typeof MediaRecorder === "undefined") return null;
    return elegirGrabacion((mime) => MediaRecorder.isTypeSupported(mime));
  }

  _motivoSinGrabar() {
    const nav = typeof navigator !== "undefined" ? navigator : null;
    return motivoSinGrabar({
      hayMediaDevices: typeof nav?.mediaDevices?.getUserMedia === "function",
      hayMediaRecorder: typeof MediaRecorder !== "undefined",
      formato: this._formatoGrabacion(),
      seguro: typeof window !== "undefined" && typeof window.isSecureContext === "boolean" ? window.isSecureContext : null,
    });
  }

  async grabar() {
    if (this.grab.estado !== "listo") return;
    const motivo = this._motivoSinGrabar();
    if (motivo) return this._decir(t(motivo), true);
    const formato = this._formatoGrabacion();
    this._decir("");
    this.grab = { estado: "pidiendo" };
    this._pintarGrabar();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      this.grab = { estado: "listo" };
      this._pintarGrabar();
      this._decir(t(mensajeMicrofono(err?.name)), true);
      this._detalle(String(err?.name ?? err ?? ""));
      return;
    }
    // la persona se fue mientras el navegador preguntaba: no se graba nada
    if (this.grab.estado !== "pidiendo" || this.abierto !== "grabar" || !this._visible()) {
      for (const pista of stream.getTracks()) pista.stop();
      if (this.grab.estado === "pidiendo") this.grab = { estado: "listo" };
      this._pintarGrabar();
      return;
    }
    let recorder;
    try {
      recorder = new MediaRecorder(stream, { mimeType: formato.mime });
    } catch {
      try {
        recorder = new MediaRecorder(stream);
      } catch (err) {
        for (const pista of stream.getTracks()) pista.stop();
        this.grab = { estado: "listo" };
        this._pintarGrabar();
        this._decir(t("grab.error"), true);
        this._detalle(String(err?.name ?? err ?? ""));
        return;
      }
    }
    const g = { estado: "grabando", stream, recorder, partes: [], inicio: performance.now(), duracionMs: 0, tope: false };
    this.grab = g;
    recorder.addEventListener("dataavailable", (ev) => {
      if (ev.data?.size) g.partes.push(ev.data);
    });
    recorder.addEventListener("stop", () => this._grabacionLista(g));
    recorder.addEventListener("error", () => {
      if (this.grab === g && g.estado === "grabando") this.parar();
    });
    try {
      recorder.start(1000);
    } catch (err) {
      this._soltarMicrofono(g);
      this.grab = { estado: "listo" };
      this._pintarGrabar();
      this._decir(t("grab.error"), true);
      this._detalle(String(err?.name ?? err ?? ""));
      return;
    }
    this._medirNivel(g);
    g.relojId = setInterval(() => this._tic(g), RELOJ_GRABACION_MS);
    this._pintarGrabar();
    this.reloj.textContent = textoReloj(0, this.maxGrabacionMs);
    this.pararBoton.focus({ preventScroll: true });
  }

  _tic(g) {
    if (this.grab !== g || g.estado !== "grabando") return;
    if (!this._visible()) return this.parar();                   // la hoja se cerró o se fue a otra pestaña: se suelta el micrófono
    const ms = Math.min(this.maxGrabacionMs, performance.now() - g.inicio);
    this.reloj.textContent = textoReloj(ms, this.maxGrabacionMs);
    // un segundo antes del tope: este reloj se pasa unos ms (y el servidor
    // rechaza lo que pasa de 5 min con margen)
    if (ms >= corteGrabacion(this.maxGrabacionMs)) this.parar({ tope: true });
  }

  // El nivel del micrófono con un AnalyserNode (no se guarda nada): una barra
  // que se mueve mientras se habla. Sin Web Audio, sin barra.
  _medirNivel(g) {
    try {
      const Contexto = window.AudioContext || window.webkitAudioContext;
      g.ctx = new Contexto();
      g.ctx.resume?.()?.catch?.(() => {});          // Safari lo crea suspendido
      const analizador = g.ctx.createAnalyser();
      analizador.fftSize = 1024;
      g.ctx.createMediaStreamSource(g.stream).connect(analizador);
      const bytes = new Uint8Array(analizador.fftSize);
      const cuadro = () => {
        if (this.grab !== g || g.estado !== "grabando") return;
        analizador.getByteTimeDomainData(bytes);
        const n = nivelDe(bytes);
        this.nivelBarra.style.transform = `scaleX(${n.toFixed(3)})`;
        this.nivel.setAttribute("aria-valuenow", String(Math.round(n * 100)));
        g.cuadro = requestAnimationFrame(cuadro);
      };
      g.cuadro = requestAnimationFrame(cuadro);
    } catch {
      g.ctx = null;
    }
  }

  // Para la grabación (lo grabado queda para escucharlo y usarlo) y suelta
  // el micrófono. `tope`: llegó a los 5 minutos (se dice).
  parar({ tope = false } = {}) {
    const g = this.grab;
    if (g.estado !== "grabando") return;
    g.estado = "parando";
    g.tope = tope;
    g.duracionMs = Math.min(corteGrabacion(this.maxGrabacionMs), performance.now() - g.inicio);
    try {
      if (g.recorder.state !== "inactive") g.recorder.stop();
      else this._grabacionLista(g);
    } catch {
      this._grabacionLista(g);
    }
    this._soltarMicrofono(g);
  }

  _soltarMicrofono(g = this.grab) {
    if (!g) return;
    clearInterval(g.relojId);
    if (g.cuadro) cancelAnimationFrame(g.cuadro);
    g.cuadro = 0;
    for (const pista of g.stream?.getTracks?.() ?? []) pista.stop();
    if (g.ctx && g.ctx.state !== "closed") g.ctx.close().catch(() => {});
    g.ctx = null;
    this.nivelBarra.style.transform = "scaleX(0)";
    this.nivel.setAttribute("aria-valuenow", "0");
  }

  _grabacionLista(g) {
    if (this.grab !== g || g.estado === "grabada") return;
    const mime = g.recorder?.mimeType || g.partes[0]?.type || "";
    const blob = new Blob(g.partes, mime ? { type: mime } : {});
    if (!blob.size) {
      this.grab = { estado: "listo" };
      this._pintarGrabar();
      this._decir(t("grab.error"), true);
      return;
    }
    g.blob = blob;
    g.ext = extensionDeMime(mime);
    g.url = URL.createObjectURL(blob);
    g.estado = "grabada";
    this.escuchar.src = g.url;
    this.reloj.textContent = textoReloj(g.duracionMs, this.maxGrabacionMs);
    this._pintarGrabar();
    if (g.tope) this._decir(t("grab.tope"));
    if (this._visible()) this.usarBoton.focus({ preventScroll: true });
  }

  descartar() {
    const g = this.grab;
    if (g.estado === "subiendo" || g.estado === "pidiendo") return;
    if (g.estado === "grabando") this.parar();
    this._limpiarGrabacion(g);
  }

  // Suelta el micrófono y lo grabado; el formulario vuelve a «Grabar».
  _limpiarGrabacion(g) {
    this._soltarMicrofono(g);
    if (g.url) URL.revokeObjectURL(g.url);
    this.escuchar.pause();
    this.escuchar.removeAttribute("src");
    this.escuchar.load();
    this.grab = { estado: "listo" };
    this._pintarGrabar();
  }

  // Sube lo grabado (gratis; el servidor la pasa a mp3) con su barra y la
  // pone en el cabezal como voz con el idioma del destino que se ve.
  usar() {
    const g = this.grab;
    if (g.estado !== "grabada" || !g.blob) return;
    if (this._enConflicto()) return this._decir(mensajeConflicto(), true);
    if (g.blob.size > this.maxBytes) return this._decir(t("bib.pesa_audio", { mb: Math.floor(this.maxBytes / MIB) }), true);
    const { idioma } = idiomaDeVoz(null, this.editor.destino?.());   // una grabación: el idioma del destino
    this._decir("");
    g.estado = "subiendo";
    this._pintarSubida(0);
    this._pintarGrabar();
    const xhr = new XMLHttpRequest();
    const fallo = (mensaje, detalle = "") => {
      if (this.grab !== g) return;
      g.estado = "grabada";
      this._pintarGrabar();
      this._decir(mensaje, true);
      if (detalle) this._detalle(detalle);
    };
    xhr.open("POST", this.urls.grabacion);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && e.total) this._pintarSubida(e.loaded / e.total);
    });
    xhr.upload.addEventListener("load", () => this._pintarSubida(null));     // el servidor la pasa a mp3
    xhr.addEventListener("load", () => {
      let cuerpo = null;
      try {
        cuerpo = JSON.parse(xhr.responseText);
      } catch { /* no era JSON (la página de entrar, un error del servidor) */ }
      const ruta = (u) => new URL(u, location.href).pathname;
      const redirigido = Boolean(xhr.responseURL) && ruta(xhr.responseURL) !== ruta(this.urls.grabacion);
      if (xhr.status === 200 && !redirigido && cuerpo?.material) {
        if (this.grab !== g) return;
        // ya subida: el formulario vuelve a «Grabar» (si no se pudo poner en la
        // edición, lo grabado queda para volver a intentarlo)
        if (this._agregar(cuerpo.material, { tipo: "grabacion", idioma })) this._limpiarGrabacion(g);
        else {
          g.estado = "grabada";
          this._pintarGrabar();
        }
        return;
      }
      fallo(mensajeGrabacionSubida({ status: xhr.status, cuerpo, redirigido }), `HTTP ${xhr.status}`);
    });
    for (const ev of ["error", "abort", "timeout"]) xhr.addEventListener(ev, () => fallo(mensajeGrabacionSubida({ red: true })));
    const fd = new FormData();
    fd.append("archivo", g.blob, nombreArchivo(g.ext));
    fd.append("hora", horaLocal());
    xhr.send(fd);
  }

  // `parte`: 0–1, o null mientras el servidor la convierte (sin número).
  _pintarSubida(parte) {
    if (parte === null) {
      this.subidaBarra.removeAttribute("value");
      this.subidaTexto.textContent = t("guardado.guardando");
      return;
    }
    this.subidaBarra.value = Math.max(0, Math.min(1, parte));
    this.subidaTexto.textContent = t("bib.subiendo", { n: Math.round(parte * 100) });
  }
}

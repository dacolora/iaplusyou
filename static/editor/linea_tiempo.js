// Línea de tiempo del editor (capa 4a): DOM + Pointer Events. Dibuja la regla,
// las filas (capas arriba, la principal con su tira de fotogramas, el audio
// abajo) y el cabezal. Tocar un clip lo selecciona; arrastrarlo lo mueve (la
// principal se reordena, lo demás se corre en el tiempo con imán); arrastrar
// un borde lo recorta; tocar la regla o el fondo lleva el cabezal ahí. No
// cambia el documento: le pide a la página la operación (`alOperar`).
//
// La cuenta (qué operación pide soltar un arrastre, cómo se ve el clip
// mientras tanto, los nombres) vive en escala.js, que prueba Node; aquí solo
// el DOM. Las escuchas van una sola vez en el lienzo (delegación): redibujar
// no suma escuchas. En pantalla táctil la línea se desliza con el dedo: tocar
// (sin deslizar) elige un clip o lleva el cabezal, y solo el clip ya elegido
// se arrastra — si no, deslizar sobre la fila del video nunca movería la vista.
//
// Capa 4b: todo va en UNA caja que corre en los dos sentidos (la página nunca
// de lado): a la izquierda la columna de cabeceras (icono + nombre de cada
// fila) queda fija mientras la línea corre, y la regla queda arriba al bajar
// entre muchas filas. Cada audio con `picos` dibuja su onda en un <canvas>
// (escala.barrasOnda), rehecho en cada dibujar (zoom, recorte, volumen). Para
// soltar desde la biblioteca: `puntoEn(x, y)` dice qué hay bajo el dedo y
// `resaltar(punto | null)` marca esa fila y dónde entraría. Cada unión de la
// principal con transición lleva su marca (escala.unionesConTransicion);
// tocarla elige el clip de antes (el que tiene la transición).
import {
  ANCHO_MIN_PX, barrasOnda, cabeceraFila, estiloArrastre, etiquetaClip, filasVisuales, fondoTira, ladosRecortables, marcasRegla,
  msAPx, msInsercion, nombreFila, PASO_ONDA_PX, PPS_DEFECTO, PPS_MAX, PPS_MIN, puntoSoltar, pxAMs, soltar, unionesConTransicion,
  VENTANA_PICOS_MS,
} from "./escala.js";
import { ID_SONIDO } from "./operaciones.js";
import { t } from "./textos.js";
import { duracionMs, pistaPrincipal } from "./tiempo.js";

const ALTO_FILA = { video: 56, superpuesto: 34, imagen: 30, texto: 30, audio: 36 };
const ALTO_ESPEJO = 24;          // el sonido de la escena: sin onda (su material es el video), fila baja
const ETIQUETA_ONDA_PX = 13;     // arriba del clip de audio va su nombre; la onda, debajo
const ONDA_MAX_PX = 8192;        // ancho máximo del canvas de una onda: más ancho, se estira
const IMAN_PX = 8;
const ARRASTRE_MIN_PX = 4;
const MARGEN_FIN_PX = 120;       // lugar vacío tras el último clip, para soltar ahí

// Iconos de las cabeceras (viewBox 24×24, trazo): texto fijo, sin datos de nadie.
const ICONOS = {
  video: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5z"/>',
  texto: '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
  imagen: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M20 16l-4.5-4.5L7 19"/>',
  musica: '<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
  voz: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
  sonido: '<path d="M4 9.5v5h4l5 4v-13l-5 4z"/><path d="M16.5 9a4.5 4.5 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11"/>',
  transicion: '<path d="M4 6l8 6-8 6zM20 6l-8 6 8 6z"/>',
};

function iconoSvg(nombre, tam, clase) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [k, v] of Object.entries({ class: clase, viewBox: "0 0 24 24", width: String(tam), height: String(tam),
    "aria-hidden": "true", focusable: "false", fill: "none", stroke: "currentColor", "stroke-width": "1.8",
    "stroke-linecap": "round", "stroke-linejoin": "round" })) svg.setAttribute(k, v);
  svg.innerHTML = ICONOS[nombre] ?? ICONOS.video;              // texto fijo de este módulo
  return svg;
}

function el(tag, clase, padre) {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (padre) padre.append(n);
  return n;
}

export class LineaTiempo {
  // `destino()`: el `<idioma>_<PAIS>` de la vista previa, para escribir los
  // textos variables con su valor en ese destino. `ventanaPicosMs`: cada
  // cuánto de fuente hay un pico (config.ventana_picos_ms de la página).
  constructor({ contenedor, zoom, materiales = () => ({}), destino = () => null, alSeleccionar = () => {}, alOperar = () => {},
    alIr = () => {}, ventanaPicosMs = VENTANA_PICOS_MS }) {
    Object.assign(this, { contenedor, zoomInput: zoom, materiales, destino, alSeleccionar, alOperar, alIr });
    this.ventanaPicosMs = Number(ventanaPicosMs) > 0 ? Number(ventanaPicosMs) : VENTANA_PICOS_MS;
    this._pps = PPS_DEFECTO;
    this.doc = null;
    this.seleccion = null;
    this.cabezalMs = 0;
    this.arrastre = null;        // {id, modo, lado, pointerId, x0, dx, activo, el, ancho0}
    this.buscando = null;        // pointerId mientras se lleva el cabezal con el mouse
    this.toque = null;           // pantalla táctil: lo que hará el toque si no se desliza
    this.resaltado = null;       // lo que pidió resaltar la biblioteca mientras arrastra
    this.scroll = el("div", "linea-scroll", contenedor);
    this.marco = el("div", "ed-linea-marco", this.scroll);
    this.cabeceras = el("div", "ed-cabeceras", this.marco);
    el("div", "ed-cabeceras-esquina", this.cabeceras);
    this.listaCabeceras = el("div", "ed-cabeceras-filas", this.cabeceras);
    this.lienzo = el("div", "linea-lienzo", this.marco);
    this.regla = el("div", "linea-regla", this.lienzo);
    this.filas = el("div", "linea-filas", this.lienzo);
    this.cabezal = el("div", "linea-cabezal", this.lienzo);
    this.marcaSoltar = el("div", "ed-marca-soltar", this.lienzo);
    this.marcaSoltar.hidden = true;
    this.lienzo.addEventListener("pointerdown", (e) => this._abajo(e));
    this.lienzo.addEventListener("pointermove", (e) => this._mover(e));
    this.lienzo.addEventListener("pointerup", (e) => this._arriba(e));
    this.lienzo.addEventListener("pointercancel", (e) => this._cancelar(e));
    this.lienzo.addEventListener("lostpointercapture", (e) => this._cancelar(e));
    this.scroll.addEventListener("wheel", (e) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      this.pps = this._pps * (e.deltaY < 0 ? 1.15 : 1 / 1.15);
    }, { passive: false });
    if (zoom) {
      zoom.min = String(PPS_MIN);
      zoom.max = String(PPS_MAX);
      zoom.value = String(this._pps);
      zoom.addEventListener("input", () => { this.pps = Number(zoom.value); });
    }
  }

  get pps() {
    return this._pps;
  }

  // Cambia el zoom dejando el cabezal en el mismo lugar de la pantalla. A
  // mitad de un arrastre no: lo corrido está medido en px de la escala de antes.
  set pps(v) {
    if (!Number.isFinite(v) || this.arrastre) {
      if (this.zoomInput) this.zoomInput.value = String(Math.round(this._pps));
      return;
    }
    const previo = this._pps;
    this._pps = Math.max(PPS_MIN, Math.min(PPS_MAX, v));
    if (this.zoomInput) this.zoomInput.value = String(Math.round(this._pps));
    if (!this.doc) return;
    const enPantalla = msAPx(this.cabezalMs, previo) - this.scroll.scrollLeft;
    this._redibujar();
    this.scroll.scrollLeft = Math.max(0, msAPx(this.cabezalMs, this._pps) - enPantalla);
  }

  dibujar(doc, { seleccion = null, cabezalMs = 0 } = {}) {
    this.doc = doc;
    this.seleccion = seleccion;
    const pps = this._pps;
    const total = duracionMs(doc);
    const visible = Math.max(0, this.scroll.clientWidth - this.cabeceras.offsetWidth);
    this.lienzo.style.width = `${Math.max(visible, msAPx(total, pps) + MARGEN_FIN_PX)}px`;
    this.regla.replaceChildren(...marcasRegla(total, pps).map((m) => {
      const n = el("span", "linea-marca");
      n.style.left = `${m.px}px`;
      n.textContent = m.etiqueta;
      return n;
    }));
    const principal = pistaPrincipal(doc);
    const mats = this.materiales() ?? {};
    const destino = this.destino();
    const ondas = [];
    const cabeceras = [];
    this.filas.replaceChildren(...filasVisuales(doc).map((pista) => {
      const fila = el("div", `linea-fila linea-fila-${pista.tipo}${pista === principal ? " linea-principal" : ""}`);
      const espejo = pista.id === ID_SONIDO;
      const alto = espejo ? ALTO_ESPEJO : (ALTO_FILA[pista.tipo] ?? 30);
      fila.dataset.pista = pista.id;
      fila.dataset.tipo = pista.tipo;
      fila.style.height = `${alto}px`;
      fila.title = nombreFila(pista, doc);
      cabeceras.push(this._cabecera(pista, doc, alto, fila.title, pista.clips.some((c) => c.id === seleccion)));
      for (const clip of pista.clips) {
        const c = el("div", `linea-clip linea-${pista.tipo}${espejo ? " linea-espejo" : ""}${clip.id === seleccion ? " linea-seleccion" : ""}`, fila);
        c.dataset.clip = clip.id;
        c.style.left = `${msAPx(clip.inicio_ms, pps)}px`;
        c.style.width = `${Math.max(ANCHO_MIN_PX, msAPx(clip.duracion_ms, pps))}px`;
        const etiqueta = etiquetaClip(pista, clip, doc, destino);
        c.title = etiqueta || fila.title;
        if (pista.tipo === "video" || pista.tipo === "superpuesto") {
          const tira = fondoTira(clip, mats[clip.material_id], pps);
          if (tira) {
            c.style.backgroundImage = `url("${String(tira.imagen).replace(/["\\\n]/g, encodeURIComponent)}")`;
            c.style.backgroundSize = tira.tamano;
            c.style.backgroundPosition = tira.posicion;
          } else {
            el("span", "linea-etiqueta", c).textContent = fila.title;   // sin tira todavía: al menos el nombre
          }
          if (Number(clip.velocidad ?? 1) !== 1) el("span", "linea-insignia", c).textContent = `${clip.velocidad}×`;
        } else {
          const picos = pista.tipo === "audio" ? mats[clip.material_id]?.picos : null;
          if (Array.isArray(picos) && picos.length) {
            // la onda debajo del nombre; el canvas se pinta ya puesto en la página
            c.classList.add("ed-con-onda");
            const canvas = el("canvas", "ed-onda", c);
            canvas.setAttribute("aria-hidden", "true");
            const altoOnda = alto - 2 - ETIQUETA_ONDA_PX;          // 2: el borde del clip
            canvas.style.height = `${altoOnda}px`;
            ondas.push({ canvas, clip, picos, ancho: parseFloat(c.style.width) - 2, alto: altoOnda });
          }
          el("span", "linea-etiqueta", c).textContent = etiqueta;
        }
        // sin asas: el sonido de la escena y la voz que cambia por país
        for (const lado of ladosRecortables(pista, clip)) el("span", "linea-asa", c).dataset.lado = lado;
      }
      if (pista === principal) {
        for (const u of unionesConTransicion(doc)) {
          const m = el("span", `ed-union${u.clipId === seleccion ? " ed-union-elegida" : ""}`, fila);
          m.dataset.clip = u.clipId;
          m.style.left = `${msAPx(u.ms, pps)}px`;
          m.title = t("tl.transicion", { nombre: u.nombre });
          m.append(iconoSvg("transicion", 12, "ed-union-icono"));
        }
      }
      return fila;
    }));
    this.listaCabeceras.replaceChildren(...cabeceras);
    if (ondas.length) {
      const color = getComputedStyle(ondas[0].canvas).color;
      for (const o of ondas) this._pintarOnda(o, color);
    }
    this._pintarResaltado();
    this.moverCabezal(cabezalMs);
    // redibujado a mitad de un arrastre (llegó una tira, cambió el zoom): el
    // clip arrastrado es otro nodo, se le vuelve a poner donde va el dedo
    if (this.arrastre) {
      this.arrastre.el = this._nodoClip(this.arrastre.id);
      if (this.arrastre.activo) this._pintarArrastre();
    }
  }

  // `seguir` (reproduciendo): si el cabezal sale de lo visible, la línea corre con él.
  moverCabezal(tMs, { seguir = false } = {}) {
    this.cabezalMs = tMs;
    const x = msAPx(tMs, this._pps);
    this.cabezal.style.left = `${x}px`;
    if (seguir && !this.arrastre && this.buscando === null) {
      // lo que se ve de la línea: la caja menos la columna de cabeceras, que la tapa
      const s = this.scroll;
      const visible = s.clientWidth - this.cabeceras.offsetWidth;
      if (x < s.scrollLeft || x > s.scrollLeft + visible - 16) s.scrollLeft = Math.max(0, x - visible / 4);
    }
  }

  // Qué hay bajo un punto de la pantalla para soltar ahí algo de la
  // biblioteca: `{pistaId, tipo, tMs, indicePrincipal}` (escala.puntoSoltar;
  // `indicePrincipal` solo sobre la fila del video), o null si el punto está
  // fuera de la línea de tiempo. Sobre la columna de cabeceras cuenta el
  // primer instante que se ve; sobre la regla, ninguna fila.
  puntoEn(clientX, clientY) {
    if (!this.doc) return null;
    const caja = this.scroll.getBoundingClientRect();
    if (!(clientX >= caja.left && clientX < caja.right && clientY >= caja.top && clientY < caja.bottom)) return null;
    const lienzo = this.lienzo.getBoundingClientRect();
    const x = Math.max(clientX, this.cabeceras.getBoundingClientRect().right) - lienzo.left;
    const sobreRegla = clientY < this.regla.getBoundingClientRect().bottom;
    const filas = [...this.filas.children].map((f) => {
      const r = f.getBoundingClientRect();
      return { pistaId: f.dataset.pista, tipo: f.dataset.tipo, top: r.top - lienzo.top, alto: r.height };
    });
    return puntoSoltar(this.doc, filas, x, sobreRegla ? -1 : clientY - lienzo.top, this._pps, {
      toleranciaMs: pxAMs(IMAN_PX, this._pps), cabezalMs: this.cabezalMs,
    });
  }

  // Marca la fila (y su cabecera) de un punto de `puntoEn` y una raya donde
  // entraría: en la principal, el lugar entre clips; en otra fila, el instante;
  // fuera de las filas, a lo alto de todas. `null` lo quita. Sobrevive a un
  // redibujado mientras la biblioteca sigue arrastrando.
  resaltar(punto) {
    this.resaltado = punto ? { ...punto } : null;
    this._pintarResaltado();
  }

  _pintarResaltado() {
    for (const n of this.marco.querySelectorAll(".ed-fila-destino")) n.classList.remove("ed-fila-destino");
    const p = this.resaltado;
    if (!p || !this.doc) {
      this.marcaSoltar.hidden = true;
      return;
    }
    let top = this.filas.offsetTop;
    let alto = this.filas.offsetHeight;
    if (p.pistaId) {
      const cual = `[data-pista="${CSS.escape(p.pistaId)}"]`;
      const fila = this.filas.querySelector(cual);
      this.listaCabeceras.querySelector(cual)?.classList.add("ed-fila-destino");
      if (fila) {
        fila.classList.add("ed-fila-destino");
        top = fila.offsetTop;
        alto = fila.offsetHeight;
      }
    }
    const enPrincipal = p.indicePrincipal !== null && p.indicePrincipal !== undefined;
    const ms = enPrincipal ? msInsercion(this.doc, p.indicePrincipal) : Math.max(0, Number(p.tMs) || 0);
    Object.assign(this.marcaSoltar.style, { left: `${msAPx(ms, this._pps)}px`, top: `${top}px`, height: `${alto}px` });
    this.marcaSoltar.hidden = false;
  }

  _cabecera(pista, doc, alto, titulo, elegida) {
    const { icono, nombre } = cabeceraFila(pista, doc);
    const n = el("div", `ed-cabecera ed-cabecera-${icono}${elegida ? " ed-cabecera-elegida" : ""}`);
    n.dataset.pista = pista.id;
    n.style.height = `${alto}px`;
    n.title = titulo;
    n.append(iconoSvg(icono, 16, "ed-cabecera-icono"));
    el("span", "ed-cabecera-nombre", n).textContent = nombre;
    return n;
  }

  // La onda de un clip de audio en su canvas: a la densidad de la pantalla,
  // y si el clip es tan ancho que el canvas pasaría de ONDA_MAX_PX, un canvas
  // más chico que el navegador estira (las barras nunca bajan de 2 px suyos).
  _pintarOnda({ canvas, clip, picos, ancho, alto }, color) {
    if (!(ancho > 0) || !(alto > 0)) return;
    const dpr = Math.max(1, Number(globalThis.devicePixelRatio) || 1);
    const w = Math.max(1, Math.min(ONDA_MAX_PX, Math.round(ancho * dpr)));
    const h = Math.max(1, Math.round(alto * dpr));
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const escala = w / ancho;                                 // px del canvas por px de la línea
    const paso = Math.max(2, PASO_ONDA_PX * escala);
    const grosor = Math.max(1, paso * (2 / 3));
    ctx.fillStyle = color;
    for (const b of barrasOnda(picos, clip, this._pps * escala, h, { ventanaMs: this.ventanaPicosMs, paso })) {
      ctx.fillRect(b.x, h - b.alto, grosor, b.alto);
    }
  }

  _redibujar() {
    if (this.doc) this.dibujar(this.doc, { seleccion: this.seleccion, cabezalMs: this.cabezalMs });
  }

  _nodoClip(id) {
    return this.filas.querySelector(`[data-clip="${CSS.escape(id)}"]`);
  }

  _msEn(e) {
    return Math.max(0, pxAMs(e.clientX - this.lienzo.getBoundingClientRect().left, this._pps));
  }

  _capturar(pointerId) {
    try {
      this.lienzo.setPointerCapture(pointerId);
    } catch { /* el puntero ya se soltó */ }
  }

  _soltarCaptura(pointerId) {
    if (this.lienzo.hasPointerCapture?.(pointerId)) this.lienzo.releasePointerCapture(pointerId);
  }

  _pintarArrastre() {
    const a = this.arrastre;
    if (!a?.el) return;
    const { x, ancho } = estiloArrastre({ modo: a.modo, lado: a.lado, dx: a.dx, ancho: a.ancho0 });
    a.el.classList.add("linea-arrastrando");
    a.el.style.transform = `translateX(${x}px)`;
    a.el.style.width = `${ancho}px`;
  }

  _abajo(e) {
    if (!this.doc || e.button !== 0 || !e.isPrimary || this.arrastre || this.buscando !== null || this.toque) return;
    // tocar la línea saca el foco del control de antes (zoom, velocidad): el
    // preventDefault del arrastre no lo movería y S, Supr o Ctrl+Z irían a él
    const activo = document.activeElement;
    if (activo && activo !== document.body) activo.blur?.();
    const tactil = e.pointerType === "touch";
    // la marca de una transición: elige el clip que la tiene (el de antes del corte)
    const union = e.target.closest?.(".ed-union");
    if (union) {
      if (tactil) this.toque = { pointerId: e.pointerId, clip: union.dataset.clip };
      else {
        this.alSeleccionar(union.dataset.clip);
        e.preventDefault();
      }
      return;
    }
    const clipEl = e.target.closest?.(".linea-clip");
    if (clipEl && !clipEl.classList.contains("linea-espejo")) {
      const id = clipEl.dataset.clip;
      if (tactil && id !== this.seleccion) {
        this.toque = { pointerId: e.pointerId, clip: id };
        return;
      }
      const lado = e.target.closest(".linea-asa")?.dataset.lado ?? null;
      this.alSeleccionar(id);                       // redibuja: el nodo del clip es otro
      const nodo = this._nodoClip(id);
      this.arrastre = { id, modo: lado ? "recorte" : "mover", lado, pointerId: e.pointerId, x0: e.clientX, dx: 0,
                        activo: false, el: nodo, ancho0: nodo ? parseFloat(nodo.style.width) || 0 : 0 };
      this._capturar(e.pointerId);
      e.preventDefault();
      return;
    }
    if (tactil) {
      this.toque = { pointerId: e.pointerId, clip: null, soltar: !clipEl, ms: this._msEn(e) };
      return;
    }
    if (!clipEl) this.alSeleccionar(null);
    this.buscando = e.pointerId;
    this._capturar(e.pointerId);
    this.alIr(this._msEn(e));
  }

  _mover(e) {
    if (this.buscando === e.pointerId) {
      this.alIr(this._msEn(e));
      return;
    }
    const a = this.arrastre;
    if (!a || a.pointerId !== e.pointerId) return;
    a.dx = e.clientX - a.x0;
    if (!a.activo && Math.abs(a.dx) < ARRASTRE_MIN_PX) return;
    a.activo = true;
    this._pintarArrastre();
  }

  _arriba(e) {
    const toque = this.toque;
    if (toque && toque.pointerId === e.pointerId) {
      this.toque = null;
      if (toque.clip) {
        this.alSeleccionar(toque.clip);
      } else {
        if (toque.soltar) this.alSeleccionar(null);
        this.alIr(toque.ms);
      }
      return;
    }
    if (this.buscando === e.pointerId) {
      this.buscando = null;
      this._soltarCaptura(e.pointerId);
      return;
    }
    const a = this.arrastre;
    if (!a || a.pointerId !== e.pointerId) return;
    this.arrastre = null;
    this._soltarCaptura(e.pointerId);
    if (!a.activo) return;                          // fue un toque: ya quedó elegido
    const pedido = soltar(this.doc, a.id, {
      modo: a.modo, lado: a.lado, deltaMs: pxAMs(a.dx, this._pps),
      toleranciaMs: pxAMs(IMAN_PX, this._pps), cabezalMs: this.cabezalMs,
    });
    try {
      if (pedido) this.alOperar(...pedido);
    } finally {
      // si la página no redibujó (nada que cambiar, o la operación falló) el
      // clip vuelve a su lugar
      if (a.el?.isConnected) this._redibujar();
    }
  }

  _cancelar(e) {
    if (this.toque?.pointerId === e.pointerId) this.toque = null;
    const a = this.arrastre;
    const mio = (a && a.pointerId === e.pointerId) || this.buscando === e.pointerId;
    if (!mio) return;
    this.arrastre = null;
    this.buscando = null;
    if (a?.activo) this._redibujar();
  }
}

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
import {
  ANCHO_MIN_PX, estiloArrastre, etiquetaClip, filasVisuales, fondoTira, ladosRecortables, marcasRegla, msAPx, nombreFila,
  PPS_DEFECTO, PPS_MAX, PPS_MIN, pxAMs, soltar,
} from "./escala.js";
import { ID_SONIDO } from "./operaciones.js";
import { duracionMs, pistaPrincipal } from "./tiempo.js";

const ALTO_FILA = { video: 56, superpuesto: 34, imagen: 30, texto: 30, audio: 28 };
const IMAN_PX = 8;
const ARRASTRE_MIN_PX = 4;
const MARGEN_FIN_PX = 120;       // lugar vacío tras el último clip, para soltar ahí

function el(tag, clase, padre) {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (padre) padre.append(n);
  return n;
}

export class LineaTiempo {
  // `destino()`: el `<idioma>_<PAIS>` de la vista previa, para escribir los
  // textos variables con su valor en ese destino.
  constructor({ contenedor, zoom, materiales = () => ({}), destino = () => null, alSeleccionar = () => {}, alOperar = () => {},
    alIr = () => {} }) {
    Object.assign(this, { contenedor, zoomInput: zoom, materiales, destino, alSeleccionar, alOperar, alIr });
    this._pps = PPS_DEFECTO;
    this.doc = null;
    this.seleccion = null;
    this.cabezalMs = 0;
    this.arrastre = null;        // {id, modo, lado, pointerId, x0, dx, activo, el, ancho0}
    this.buscando = null;        // pointerId mientras se lleva el cabezal con el mouse
    this.toque = null;           // pantalla táctil: lo que hará el toque si no se desliza
    this.scroll = el("div", "linea-scroll", contenedor);
    this.lienzo = el("div", "linea-lienzo", this.scroll);
    this.regla = el("div", "linea-regla", this.lienzo);
    this.filas = el("div", "linea-filas", this.lienzo);
    this.cabezal = el("div", "linea-cabezal", this.lienzo);
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
    this.lienzo.style.width = `${Math.max(this.scroll.clientWidth, msAPx(total, pps) + MARGEN_FIN_PX)}px`;
    this.regla.replaceChildren(...marcasRegla(total, pps).map((m) => {
      const n = el("span", "linea-marca");
      n.style.left = `${m.px}px`;
      n.textContent = m.etiqueta;
      return n;
    }));
    const principal = pistaPrincipal(doc);
    const mats = this.materiales() ?? {};
    const destino = this.destino();
    this.filas.replaceChildren(...filasVisuales(doc).map((pista) => {
      const fila = el("div", `linea-fila linea-fila-${pista.tipo}${pista === principal ? " linea-principal" : ""}`);
      const espejo = pista.id === ID_SONIDO;
      fila.dataset.pista = pista.id;
      fila.style.height = `${ALTO_FILA[pista.tipo] ?? 30}px`;
      fila.title = nombreFila(pista, doc);
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
          el("span", "linea-etiqueta", c).textContent = etiqueta;
        }
        // sin asas: el sonido de la escena y la voz que cambia por país
        for (const lado of ladosRecortables(pista, clip)) el("span", "linea-asa", c).dataset.lado = lado;
      }
      return fila;
    }));
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
      const s = this.scroll;
      if (x < s.scrollLeft || x > s.scrollLeft + s.clientWidth - 16) s.scrollLeft = Math.max(0, x - s.clientWidth / 4);
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
    const t = this.toque;
    if (t && t.pointerId === e.pointerId) {
      this.toque = null;
      if (t.clip) {
        this.alSeleccionar(t.clip);
      } else {
        if (t.soltar) this.alSeleccionar(null);
        this.alIr(t.ms);
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

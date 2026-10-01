// Tocar, mover y agrandar sobre el video (capa 4b, Task 8). Una capa
// transparente encima del lienzo (#ed-interaccion, del mismo tamaño) escucha
// el puntero:
// - tocar elige la capa de arriba bajo el dedo (texto o imagen; también queda
//   elegida en la línea de tiempo: va por editor.seleccionar); tocar donde no
//   hay ninguna capa suelta lo elegido;
// - lo elegido muestra su caja con un asa en la esquina opuesta al ancla;
//   arrastrar la caja la mueve (se pega al centro y lo muestran las guías),
//   arrastrar el asa la agranda o la achica (transform.escala); se puede
//   arrastrar de una vez una capa que todavía no estaba elegida;
// - tocar el video donde no hay ninguna capa elige el clip de la principal que
//   suena en el cabezal (capa 5b, D8; en una transición, el que entra);
//   arrastrar sobre el video mueve qué parte del cuadro se ve (su `encuadre`:
//   la imagen sigue al dedo y se pega al centro) y, con ese clip elegido, el
//   asa de la esquina lo acerca o lo aleja (zoom 1–4). Su caja es la parte
//   del cuadro que se ve (encuadre.cajaVisible, lo mismo que dibuja
//   lienzo.dibujarPrincipal), medida con vista.medidasPrincipal;
// - dos toques seguidos en un texto llevan a escribirlo (editor.enfocarTexto);
// - arrastrar pausa la reproducción, y cada arrastre queda en UN deshacer (la
//   clave "<clipId>:transform" de editor.operarCon; en el video,
//   "<clipId>:encuadre");
// - la caja sigue a la capa mientras corre el tiempo o cambia el documento, y
//   desaparece si en ese instante la capa no está.
//
// Solo DOM y eventos: la cuenta (qué se tocó, cuánto se mueve o se agranda,
// si fue un doble toque) es de seleccion.js, que prueba Node, sobre el
// documento que se DIBUJA (vista.resuelto, con las variables del destino) y
// las medidas de los textos del propio lienzo (vista.medidasTexto). La caja,
// el asa y las guías son dibujo: no reciben el puntero.
import {
  asaDe, cajaElegida, cajaEncuadreElegida, cambiosArrastre, cursorEn, esDobleToque, esTexto, gestoEn, IMAN_PX,
  MARGEN_ASA_PX, porcentaje, puntoEnLienzo, RADIO_ASA_PX, superaUmbral,
} from "./seleccion.js";

function el(tag, clase, padre) {
  const n = document.createElement(tag);
  n.className = clase;
  n.hidden = true;
  padre.append(n);
  return n;
}

function transformDe(doc, id) {
  for (const p of doc?.pistas ?? []) for (const c of p.clips ?? []) if (c.id === id) return { ...(c.transform ?? {}) };
  return null;
}

const ES_ENCUADRE = new Set(["encuadre", "asa_encuadre"]);

export class InteraccionLienzo {
  // `escenario`: #ed-escenario (mide lo que se ve del lienzo); `lienzo`:
  // #lienzo; `editor`: el de pagina_editor.js; `vista`: la VistaPrevia.
  constructor({ escenario, lienzo, editor, vista }) {
    this.lienzo = lienzo;
    this.editor = editor;
    this.vista = vista;
    this.capa = escenario.querySelector("#ed-interaccion");
    if (!this.capa) {
      this.capa = document.createElement("div");
      this.capa.id = "ed-interaccion";
      this.capa.className = "ed-interaccion";
      this.capa.setAttribute("aria-hidden", "true");
      escenario.append(this.capa);
    }
    this.caja = el("div", "ed-caja", this.capa);
    this.guiaV = el("div", "ed-guia ed-guia-v", this.capa);
    this.guiaH = el("div", "ed-guia ed-guia-h", this.capa);
    this.asa = el("div", "ed-asa", this.capa);
    this.gesto = null;            // el puntero apretado sobre una capa
    this.toque = null;            // el último toque (sin arrastrar), para el doble toque
    this.cuadro = 0;              // requestAnimationFrame con el arrastre por aplicar
    // D8: las medidas del cuadro de un clip de la principal (sin ellas, una
    // vista sin medidasPrincipal, el video no se toca: lo de antes)
    this.medidasPrincipal = typeof vista.medidasPrincipal === "function" ? (id) => vista.medidasPrincipal(id) : null;
    this.escuchas = [
      ["pointerdown", (e) => this._abajo(e)],
      ["pointermove", (e) => this._mover(e)],
      ["pointerup", (e) => this._arriba(e)],
      ["pointercancel", (e) => this._cancelar(e)],
      ["lostpointercapture", (e) => this._cancelar(e)],
    ];
    for (const [tipo, fn] of this.escuchas) this.capa.addEventListener(tipo, fn);
    // la caja sigue a la capa: cambios del documento, de lo elegido, del
    // destino, materiales que llegan y cada cuadro que se dibuja ("tiempo")
    this.dejar = editor.escuchar(() => this.pintar());
    this.pintar();
  }

  destruir() {
    this._terminar();
    for (const [tipo, fn] of this.escuchas) this.capa.removeEventListener(tipo, fn);
    this.dejar?.();
    for (const n of [this.caja, this.guiaV, this.guiaH, this.asa]) n.remove();
  }

  // ---- Dibujo ----

  // Píxeles del lienzo por píxel de pantalla (el lienzo se muestra achicado);
  // null si no se ve.
  _medida() {
    const rect = this.lienzo.getBoundingClientRect();
    if (!(rect.width > 0) || !(rect.height > 0)) return null;
    return { rect, proporcion: this.lienzo.width / rect.width };
  }

  pintar() {
    const doc = this.vista.resuelto;
    const id = this.editor.seleccion;
    const medida = doc && id ? this._medida() : null;
    const t = this.vista.tiempo();
    const capa = medida ? cajaElegida(doc, t, id, this.vista.materiales, this.vista.medidasTexto(t)) : null;
    // si lo elegido es el clip de la principal del cabezal: la parte del cuadro que se ve
    const video = medida && !capa ? cajaEncuadreElegida(doc, t, id, this.medidasPrincipal) : null;
    const caja = capa ?? video;
    this.caja.hidden = !caja;
    this.asa.hidden = !caja;
    this.caja.classList.toggle("ed-encuadre-caja", Boolean(video));
    this.asa.classList.toggle("ed-encuadre-asa", Boolean(video));
    if (!caja) return;
    const c = porcentaje(caja, doc.formato);
    Object.assign(this.caja.style, { left: `${c.left}%`, top: `${c.top}%`, width: `${c.width}%`, height: `${c.height}%` });
    const a = porcentaje(asaDe(caja, caja.ancla, doc.formato, MARGEN_ASA_PX * medida.proporcion), doc.formato);
    Object.assign(this.asa.style, { left: `${a.left}%`, top: `${a.top}%` });
  }

  _guias(guias) {
    this.guiaV.hidden = !guias?.vertical;
    this.guiaH.hidden = !guias?.horizontal;
  }

  // ---- Puntero ----

  // Qué hay bajo el puntero (seleccion.gestoEn), o null si no hay nada que
  // tocar todavía (sin destino preparado, lienzo sin tamaño).
  _gestoEn(e) {
    const doc = this.vista.resuelto;
    const medida = doc ? this._medida() : null;
    if (!medida) return null;
    const p = puntoEnLienzo(e.clientX, e.clientY, medida.rect, this.lienzo.width, this.lienzo.height);
    const t = this.vista.tiempo();
    const g = gestoEn(doc, t, p.x, p.y, {
      seleccion: this.editor.seleccion, materiales: this.vista.materiales, medidasTexto: this.vista.medidasTexto(t),
      radioAsa: RADIO_ASA_PX * medida.proporcion, margenAsa: MARGEN_ASA_PX * medida.proporcion,
      medidasPrincipal: this.medidasPrincipal,
    });
    return { ...g, doc, punto: p, proporcion: medida.proporcion };
  }

  _abajo(e) {
    if (!e.isPrimary || e.button !== 0 || this.gesto) return;
    const g = this._gestoEn(e);
    if (!g) return;
    e.preventDefault();
    // como en la línea de tiempo: tocar el video saca el foco del control de
    // antes (un deslizador, el texto), así S, Supr o Ctrl+Z no van a él
    const activo = document.activeElement;
    if (activo && activo !== document.body) activo.blur?.();
    if (g.tipo === "vacio") {
      this.toque = null;
      if (this.editor.seleccion !== null) this.editor.seleccionar(null);
      return;
    }
    const transform = transformDe(this.editor.doc(), g.id);
    if (!transform) return;
    if (g.id !== this.editor.seleccion) this.editor.seleccionar(g.id);   // la caja aparece bajo el dedo
    this.gesto = {
      pointerId: e.pointerId, tipo: g.tipo, id: g.id, alTocar: g.alTocar, texto: esTexto(g.doc, g.alTocar),
      // el imán del centro: IMAN_PX de pantalla, en px del lienzo
      transform, caja: g.caja, formato: g.doc.formato, inicio: g.punto, iman: IMAN_PX * g.proporcion,
      // D8: el encuadre y las medidas del cuadro al empezar, y el asa (el zoom se mide desde ahí)
      encuadre: g.encuadre ?? null, medidas: g.medidas ?? null, asa: g.asa ?? null,
      x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, activo: false,
    };
    try {
      this.capa.setPointerCapture(e.pointerId);
    } catch { /* el puntero ya se soltó */ }
  }

  _mover(e) {
    const g = this.gesto;
    if (!g) {
      if (e.pointerType === "mouse" && !e.buttons) this._cursor(e);
      return;
    }
    if (g.pointerId !== e.pointerId) return;
    const dx = e.clientX - g.x0;
    const dy = e.clientY - g.y0;
    if (!g.activo) {
      if (!superaUmbral(dx, dy, e.pointerType)) return;
      g.activo = true;
      this.toque = null;
      if (this.vista.ocupado()) this.vista.pausar();
    }
    g.x = e.clientX;
    g.y = e.clientY;
    // un cambio por cuadro, no uno por evento del puntero
    if (!this.cuadro) {
      this.cuadro = requestAnimationFrame(() => {
        this.cuadro = 0;
        this._aplicar();
      });
    }
  }

  // El cambio desde donde empezó el arrastre (no acumulado: cada paso
  // reemplaza al anterior dentro del mismo deshacer). Se mide en píxeles del
  // lienzo contra DÓNDE ESTÁ AHORA el lienzo: si la página se corre durante el
  // arrastre (en el celular la barra de arriba cambia de alto cuando «Guardado»
  // pasa a «Cambios sin guardar…»), la capa sigue bajo el dedo.
  _aplicar() {
    const g = this.gesto;
    if (!g?.activo) return;
    const medida = this._medida();
    if (!medida) return;
    const p = puntoEnLienzo(g.x, g.y, medida.rect, this.lienzo.width, this.lienzo.height);
    const { cambios, guias } = cambiosArrastre(g, p.x - g.inicio.x, p.y - g.inicio.y);
    this._guias(g.tipo === "caja" || g.tipo === "encuadre" ? guias : null);
    if (!cambios) return;                // el cuadro todavía sin medidas: nada que mover
    const clave = `${g.id}:${ES_ENCUADRE.has(g.tipo) ? "encuadre" : "transform"}`;
    if (!this.editor.operarCon({ clave }, "cambiar", g.id, cambios)) this._terminar();
  }

  _arriba(e) {
    const g = this.gesto;
    if (!g || g.pointerId !== e.pointerId) return;
    if (this.cuadro) {                 // lo último del arrastre que no alcanzó a aplicarse
      cancelAnimationFrame(this.cuadro);
      this.cuadro = 0;
      this._aplicar();
    }
    this._terminar();
    if (g.activo) return;
    // fue un toque: dentro de la caja de lo elegido, gana la capa de arriba
    if (g.alTocar !== this.editor.seleccion) this.editor.seleccionar(g.alTocar);
    const toque = { t: e.timeStamp, x: e.clientX, y: e.clientY, id: g.alTocar };
    if (g.texto && esDobleToque(this.toque, toque)) {
      this.toque = null;
      this.editor.enfocarTexto();
    } else {
      this.toque = toque;
    }
  }

  _cancelar(e) {
    if (this.gesto?.pointerId === e.pointerId) this._terminar();
  }

  _terminar() {
    const g = this.gesto;
    this.gesto = null;
    if (this.cuadro) {
      cancelAnimationFrame(this.cuadro);
      this.cuadro = 0;
    }
    this._guias(null);
    if (g && this.capa.hasPointerCapture?.(g.pointerId)) this.capa.releasePointerCapture(g.pointerId);
  }

  // Con el mouse, el cursor dice qué pasaría al apretar: mover o agrandar.
  _cursor(e) {
    const cursor = cursorEn(this._gestoEn(e));
    if (this.capa.style.cursor !== cursor) this.capa.style.cursor = cursor;
  }
}

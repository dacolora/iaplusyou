// Panel de propiedades del editor (capa 4b, Task 7): la columna de la derecha
// («Editar»; en el celular, la hoja que sube desde abajo). Un formulario por
// clase de lo elegido:
//
// - Video (la pista principal): velocidad, volumen del sonido de la escena,
//   encuadre, zoom lento, transición al siguiente (y su duración) y borrar.
// - Foto (capa 5b: una foto como clip de la principal): cuánto dura (en vez
//   de velocidad y sonido, que una foto no tiene), encuadre, zoom lento,
//   transición al siguiente y borrar.
// - «Encuadre» (capa 5b, D4/D8; video y foto): llenar o ajustar con el fondo
//   desenfocado, acercar el cuadro (100–400 %) y centrarlo — qué parte se ve
//   se elige arrastrando sobre el video (lienzo_interaccion.js).
// - Texto: el texto (y, bajo el campo, lo que no sale en el video — capa 5c,
//   D7.5 —, con «Mostrar los emojis» en un texto de antes), fuente (por
//   familia, cada nombre en su letra: D9.4), tamaño, ancho del texto y «Sin
//   límite» (D7.2), color, contorno, sombra, fondo, alineación, animación de
//   entrada, centrar y borrar.
// - Imagen: tamaño (en % del ancho de la pantalla), opacidad, «Llenar la
//   pantalla», «Centrar» y borrar.
// - Audio (música, efecto, voz…): volumen, fundidos, silenciar, «Suena en»
//   (capa 5a, D10: solo una voz agregada en el editor), «Subtítulos de este
//   audio» (abre esa pestaña de la biblioteca) y borrar.
// - Nada elegido: la mezcla de toda la edición y qué hacer.
//
// Qué formulario toca y qué valores muestra lo decide propiedades_modelo.js
// (puro, probado en Node); aquí solo se pone en el DOM. El formulario se ARMA
// cuando cambia lo elegido y, con cualquier otro cambio, solo se le ponen los
// valores nuevos: rehacerlo a mitad de un arrastre cortaría el arrastre. Un
// deslizador opera al moverse con la clave "<clipId>:<campo>" (un solo
// deshacer por arrastre). El campo de texto no se toca mientras se escribe en
// él (editarTexto recorta los espacios: el cursor saltaría).
//
// Solo toca el DOM de su panel y la edición por `editor` (pagina_editor.js).
// No hace nada al importarse (lo prueba Node).
import { avisoTransicion } from "./escala.js";
import {
  alternarSilencio, buscar, cambioAncho, cambioCentrarEncuadre, cambioContorno, cambioFondo, cambioGrosor, cambioLlenar,
  cambioModoEncuadre, cambioSinLimite, cambioSombra, cambioSuenaEn, cambioZoomEncuadre, claveForma, escalaDePorcentaje,
  mensajeRechazo, modelo, msDeDuracionFoto, textoDuracionFoto, textoPorcentaje, textoSegundos,
} from "./propiedades_modelo.js";
import { t } from "./textos.js";

function el(tag, clase, padre, texto) {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (texto !== undefined) n.textContent = texto;
  if (padre) padre.append(n);
  return n;
}

// `texto` es la CLAVE de textos.js: se traduce al armar el formulario
// (`traducidas`), nunca al cargar el módulo.
const KEN_BURNS = [
  { valor: "ninguno", texto: "prop.ninguno" },
  { valor: "in", texto: "prop.acercar" },
  { valor: "out", texto: "prop.alejar" },
];
const FONDOS = [
  { valor: "ninguno", texto: "prop.ninguno" },
  { valor: "pildora", texto: "prop.pildora" },
  { valor: "caja", texto: "prop.caja" },
];
const ALINEACIONES = [
  { valor: "izquierda", texto: "prop.izquierda" },
  { valor: "centro", texto: "prop.centro" },
  { valor: "derecha", texto: "prop.derecha" },
];
const ANIMACIONES = [
  { valor: "ninguna", texto: "prop.ninguna" },
  { valor: "deslizar", texto: "prop.anim_deslizar" },
];
const TEXTO_VACIO = "prop.texto_vacio";
const traducidas = (lista) => lista.map((o) => ({ ...o, texto: t(o.texto) }));

export class Propiedades {
  // `contenedor`: #ed-panel-propiedades (la caja que corre hacia abajo);
  // `editor`: el de pagina_editor.js; `materiales()`: los de la vista previa
  // (las medidas de una imagen, para su tamaño en % y «Llenar la pantalla»);
  // `nombresIdioma`: {es: "Español", …} para «Suena en» (capa 5a);
  // `medidasPrincipal(clipId)`: [ancho, alto] que se ven del cuadro de un
  // clip de la principal (vista.medidasPrincipal; capa 5b: «Encuadre» avisa
  // si el cuadro no tiene margen para moverse — sin ella, las del material).
  // Capa 5c: `catalogoFuentes` (config.catalogo_fuentes: las fuentes que la
  // página tiene, para la lista por familia) y `tabla` (config.tipografia:
  // qué no sale en el video de un texto).
  constructor({
    contenedor, editor, materiales = () => ({}), nombresIdioma = {}, medidasPrincipal = null, catalogoFuentes = [], tabla = null,
  }) {
    this.contenedor = contenedor;
    this.editor = editor;
    this.materiales = materiales;
    this.catalogoFuentes = Array.isArray(catalogoFuentes) ? catalogoFuentes : [];
    this.tabla = tabla ?? null;
    this.fuentesPedidas = false;      // la lista de fuentes ya pidió bajarlas todas (D9.3)
    this.medidasPrincipal = typeof medidasPrincipal === "function" ? medidasPrincipal : null;
    this.nombresIdioma = nombresIdioma ?? {};
    this.m = null;                    // el modelo que se ve
    this.clave = null;                // forma:clipId del formulario armado
    this.pintores = [];               // (m) => pone los valores de m en un control
    this.textarea = null;
    this.silencios = new Map();       // clipId -> volumen antes de «Silenciar»
    this.relojMensaje = null;
    contenedor.replaceChildren();
    this.mensaje = el("p", "editor-aviso ed-prop-mensaje", contenedor);
    this.mensaje.setAttribute("aria-live", "polite");
    this.mensaje.hidden = true;
    this.cuerpo = el("div", "ed-prop", contenedor);
    // un clic con el mouse no deja el foco en el botón (Espacio lo volvería a apretar)
    this.cuerpo.addEventListener("click", (e) => {
      const b = e.target.closest?.("button");
      if (b && e.detail > 0) b.blur();
    });
    editor.escuchar((que) => {
      if (que === "foco-texto") this.enfocarTexto();
      else if (que !== "tiempo") this.pintar();
    });
    this.pintar();
  }

  // ---- Pintar ----

  pintar() {
    const ed = this.editor;
    const m = modelo(ed.doc(), ed.seleccion, {
      destino: ed.destino(), info: ed.info(), materiales: this.materiales() ?? {}, nombresIdioma: this.nombresIdioma,
      medidasPrincipal: this.medidasPrincipal, catalogoFuentes: this.catalogoFuentes, tabla: this.tabla,
    });
    const otra = claveForma(m) !== this.clave;
    this.m = m;
    if (otra) this._armar(m);
    for (const pintor of this.pintores) pintor(m);
  }

  // Agregar un texto lo deja elegido y pide escribirlo (editor.enfocarTexto,
  // que en el celular ya subió esta hoja): el campo, con todo seleccionado
  // para que lo que se escriba reemplace «Escribe aquí» (o «Escribe el precio»).
  enfocarTexto() {
    this.pintar();
    const area = this.textarea;
    if (!area || area.disabled || area.readOnly) return;
    const poner = () => {
      area.focus();
      area.select();
    };
    poner();
    if (document.activeElement !== area) requestAnimationFrame(poner);   // la hoja todavía estaba subiendo
  }

  _armar(m) {
    const teniaFoco = this.cuerpo.contains(document.activeElement);
    this.clave = claveForma(m);
    this.pintores = [];
    this.textarea = null;
    this.cuerpo.replaceChildren();
    this.cuerpo.dataset.forma = m.forma;
    const armar = {
      documento: this._armarDocumento, video: this._armarVideo, foto: this._armarFoto, texto: this._armarTexto,
      imagen: this._armarImagen,
      audio: this._armarAudio, sonido: this._armarSonido, otro: this._armarOtro,
    }[m.forma] ?? this._armarDocumento;
    armar.call(this, m);
    // lo que tenía el foco se fue con el formulario de antes: queda en el panel
    if (teniaFoco) this.contenedor.closest("[tabindex]")?.focus({ preventScroll: true });
  }

  _decir(texto, error = false) {
    clearTimeout(this.relojMensaje);
    this.mensaje.textContent = texto || "";
    this.mensaje.hidden = !texto;
    this.mensaje.classList.toggle("error", Boolean(texto) && error);
    if (texto) this.relojMensaje = setTimeout(() => this._decir(""), error ? 10000 : 6000);
  }

  // ---- Operar ----

  // Una operación de operaciones.js sobre la edición; con `clave`, los pasos
  // seguidos quedan en UN deshacer. Si la página la rechaza, el control
  // vuelve a mostrar el valor que de verdad quedó (un deslizador no se queda
  // donde se soltó) y el porqué se dice también aquí (en el celular la hoja
  // tapa el aviso de debajo del video); con la edición cambiada en otra
  // pestaña, eso mismo.
  _operar(clave, nombre, ...args) {
    const ed = this.editor;
    const ok = clave ? ed.operarCon({ clave }, nombre, ...args) : ed.operar(nombre, ...args);
    if (ok) {
      if (this.mensaje.classList.contains("error")) this._decir("");
    } else {
      this.pintar();
      this._decir(mensajeRechazo(ed.doc(), nombre, args, ed.info(), { conflicto: Boolean(ed.enConflicto?.()) }), true);
    }
    return ok;
  }

  _cambiar(clave, cambios) {
    return this._operar(clave, "cambiar", this.m.clipId, cambios);
  }

  _clip() {
    return buscar(this.editor.doc(), this.m?.clipId)?.clip ?? null;
  }

  _borrar() {
    if (this.m?.clipId) this._operar(null, "borrar", this.m.clipId);
  }

  // ---- Controles: cada uno se arma una vez y anota su pintor ----

  _cabeza(nombre) {
    el("h3", "ed-prop-nombre", this.cuerpo, nombre);
  }

  _seccion(padre = this.cuerpo, visible = null) {
    const s = el("div", "ed-prop-sub", padre);
    if (visible) this.pintores.push((m) => { s.hidden = !visible(m); });
    return s;
  }

  _nota(padre, leer, clase = "") {
    const p = el("p", `ed-prop-nota ${clase}`.trim(), padre);
    this.pintores.push((m) => {
      const texto = leer(m);
      p.textContent = texto || "";
      p.hidden = !texto;
    });
    return p;
  }

  // Deslizador con su etiqueta y su valor escrito al lado. `leer(m)` da
  // {valor, min?, max?, deshabilitado?, texto?}; `aplicar(v)` opera al moverse.
  _deslizador(padre, { id, etiqueta, min = 0, max = 100, paso = 1, escribir = textoPorcentaje, leer, aplicar }) {
    const campo = el("div", "ed-prop-campo", padre);
    const fila = el("div", "ed-prop-fila", campo);
    const label = el("label", "ed-prop-etiqueta", fila, etiqueta);
    label.htmlFor = id;
    const salida = el("output", "ed-prop-valor", fila);
    salida.setAttribute("for", id);
    const input = el("input", "", campo);
    Object.assign(input, { type: "range", id, min: String(min), max: String(max), step: String(paso) });
    input.addEventListener("input", () => {
      const v = Number(input.value);
      salida.textContent = escribir(v);
      aplicar(v);
    });
    input.addEventListener("change", () => this.pintar());      // al soltar: el valor que de verdad quedó
    this.pintores.push((m) => {
      const r = leer(m);
      if (r.min !== undefined) input.min = String(r.min);
      if (r.max !== undefined) input.max = String(r.max);
      input.disabled = Boolean(r.deshabilitado);
      if (input.value !== String(r.valor)) input.value = String(r.valor);
      salida.textContent = r.texto ?? escribir(r.valor);
    });
    return input;
  }

  // Opciones excluyentes (radios con la forma de .segmentado de style.css).
  // `opciones`: [{valor, texto, fuente?}]; `leer(m)` da {valor, deshabilitado?}.
  _opciones(padre, { nombre, etiqueta, opciones, leer, aplicar, lista = false }) {
    const fs = el("fieldset", "ed-prop-campo", padre);
    el("legend", "ed-prop-etiqueta", fs, etiqueta);
    const grupo = el("div", `segmentado ed-prop-segmentado${lista ? " ed-prop-lista" : ""}`, fs);
    const radios = opciones.map((o) => {
      const l = el("label", "", grupo);
      const r = el("input", "", l);
      Object.assign(r, { type: "radio", name: nombre, value: String(o.valor) });
      const s = el("span", "", l, o.texto);
      if (o.fuente) s.style.fontFamily = `"${o.fuente}", var(--font-body)`;
      r.addEventListener("change", () => {
        if (r.checked) aplicar(o.valor);
      });
      return r;
    });
    this.pintores.push((m) => {
      const r = leer(m);
      for (const radio of radios) {
        radio.checked = radio.value === String(r.valor);
        radio.disabled = Boolean(r.deshabilitado);
      }
    });
    return fs;
  }

  _casilla(padre, { etiqueta, leer, aplicar }) {
    const l = el("label", "ed-prop-casilla", padre);
    const c = el("input", "", l);
    c.type = "checkbox";
    l.append(etiqueta);
    c.addEventListener("change", () => aplicar(c.checked));
    this.pintores.push((m) => {
      c.checked = Boolean(leer(m));
    });
    return c;
  }

  // Un color libre (<input type=color>) con su etiqueta en la misma fila.
  _color(padre, { id, etiqueta, leer, aplicar }) {
    const fila = el("div", "ed-prop-fila", padre);
    const label = el("label", "ed-prop-etiqueta", fila, etiqueta);
    label.htmlFor = id;
    const input = el("input", "ed-prop-color", fila);
    Object.assign(input, { type: "color", id });
    input.addEventListener("input", () => aplicar(input.value.toUpperCase()));
    this.pintores.push((m) => {
      const v = leer(m).toLowerCase();
      if (input.value !== v) input.value = v;
    });
    return input;
  }

  _boton(padre, { texto, clase = "btn-sm", leer = null, aplicar }) {
    const b = el("button", clase, padre, texto);
    b.type = "button";
    b.addEventListener("click", () => aplicar());
    if (leer) {
      this.pintores.push((m) => {
        const r = leer(m);
        b.disabled = Boolean(r.deshabilitado);
        if (r.texto !== undefined) b.textContent = r.texto;
        if (r.titulo !== undefined) b.title = r.titulo || "";
        if (r.presionado !== undefined) b.setAttribute("aria-pressed", String(Boolean(r.presionado)));
      });
    }
    return b;
  }

  _botonBorrar(leer = null) {
    const fila = el("div", "ed-prop-acciones ed-prop-pie", this.cuerpo);
    this._boton(fila, { texto: t("prop.borrar"), clase: "btn-sm btn-peligro", leer, aplicar: () => this._borrar() });
  }

  // ---- Los formularios ----

  // Nada elegido: qué hacer y la mezcla de toda la edición.
  _armarDocumento(m) {
    const vacio = el("div", "estado-vacio ed-vacio ed-prop-vacio", this.cuerpo);
    el("p", "estado-vacio-texto", vacio, m.ayuda);
    this._cabeza(t("prop.toda"));
    const fs = el("fieldset", "ed-prop-campo", this.cuerpo);
    el("legend", "ed-prop-etiqueta", fs, t("prop.mezcla"));
    const lista = el("div", "ed-prop-mezclas", fs);
    const radios = m.opcionesMezcla.map((o) => {
      const l = el("label", "opcion-tarjeta", lista);
      const r = el("input", "", l);
      Object.assign(r, { type: "radio", name: "ed-prop-mezcla", value: o.valor });
      el("strong", "", l, o.texto);
      el("small", "", l, o.ayuda);
      r.addEventListener("change", () => {
        if (r.checked) this._operar(null, "cambiarMezcla", o.valor);
      });
      return r;
    });
    this.pintores.push((x) => {
      for (const r of radios) r.checked = r.value === x.mezcla;
    });
    this._nota(fs, (x) => (x.aMedida ? t("prop.a_medida") : null));
  }

  _armarVideo(m) {
    const id = m.clipId;
    this._cabeza(t("fila.video"));
    // Velocidad (antes en la barra de herramientas: conserva su id)
    const campo = el("div", "ed-prop-campo", this.cuerpo);
    const label = el("label", "ed-prop-etiqueta", campo, t("prop.velocidad"));
    label.htmlFor = "h-velocidad";
    const vel = el("select", "", campo);
    vel.id = "h-velocidad";
    for (const v of m.velocidades) vel.append(new Option(v.texto, String(v.valor)));
    vel.addEventListener("change", () => {
      vel.blur();                    // si no, S, Supr y Ctrl+Z irían al select
      this._operar(null, "cambiarVelocidad", id, Number(vel.value));
    });
    this.pintores.push((x) => {
      vel.value = String(x.velocidad);
    });
    // El sonido de la escena (lo que suena es su espejo en p_sonido)
    this._deslizador(this.cuerpo, {
      id: "ed-prop-sonido", etiqueta: t("prop.volumen_sonido"),
      leer: (x) => ({ valor: x.sonido.porcentaje, deshabilitado: !x.sonido.disponible,
                      texto: x.sonido.disponible ? undefined : "—" }),
      aplicar: (v) => this._operar(`${id}:sonido`, "volumenSonido", id, v / 100),
    });
    this._nota(this.cuerpo, (x) => x.sonido.motivo);
    this._armarEncuadre(m);
    this._armarZoomLento();
    this._armarTransicion(m);
    this._botonBorrar((x) => ({ deshabilitado: !x.puedeBorrar, titulo: x.motivoBorrar }));
  }

  // Capa 5b (D1, D8): una foto de la principal. Cuánto dura, en segundos con
  // la coma del idioma (se aplica al soltar el campo: Enter o tocar afuera; lo
  // que no es un número vuelve a lo de antes, y los topes —0,1 a 60 s— los
  // pone operaciones.cambiarDuracionFoto), y en vez de velocidad y sonido, la
  // nota de por qué no los tiene.
  _armarFoto(m) {
    const id = m.clipId;
    this._cabeza(m.nombre);
    const campo = el("div", "ed-prop-campo ed-foto-duracion", this.cuerpo);
    const label = el("label", "ed-prop-etiqueta", campo, t("prop.duracion_foto"));
    label.htmlFor = "ed-foto-duracion";
    const fila = el("div", "ed-foto-campo", campo);
    const input = el("input", "", fila);
    Object.assign(input, { type: "text", id: "ed-foto-duracion", inputMode: "decimal", autocomplete: "off", spellcheck: false });
    // la «s» es solo visual: un lector de pantalla oye «… en segundos» (revisión final)
    input.setAttribute("aria-label", t("prop.duracion_foto_segundos"));
    el("span", "ed-foto-unidad", fila, "s").setAttribute("aria-hidden", "true");
    input.addEventListener("change", () => {
      const ms = msDeDuracionFoto(input.value);
      if (ms !== null && ms !== this.m?.duracionMs) this._operar(null, "cambiarDuracionFoto", id, ms);
      this.pintar();
      if (this.m?.forma === "foto") input.value = textoDuracionFoto(this.m.duracionMs);   // lo que de verdad quedó
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        input.blur();                  // aplica (change) y las teclas vuelven a la página
      } else if (e.key === "Escape") {
        input.value = textoDuracionFoto(this.m?.duracionMs);
        input.blur();
      }
    });
    this.pintores.push((x) => {
      if (document.activeElement !== input) input.value = textoDuracionFoto(x.duracionMs);   // no mientras se escribe
    });
    this._nota(this.cuerpo, (x) => x.nota);
    this._armarEncuadre(m);
    this._armarZoomLento();
    this._armarTransicion(m);
    this._botonBorrar((x) => ({ deshabilitado: !x.puedeBorrar, titulo: x.motivoBorrar }));
  }

  _armarZoomLento() {
    this._opciones(this.cuerpo, {
      nombre: "ed-prop-zoom", etiqueta: t("prop.zoom_lento"), opciones: traducidas(KEN_BURNS),
      leer: (x) => ({ valor: x.kenBurns ?? "ninguno" }),
      aplicar: (v) => this._cambiar(null, { ken_burns: v === "ninguno" ? null : v }),
    });
  }

  // «Encuadre» (capa 5b, D4/D8) de un video o una foto de la principal:
  // llenar o ajustar con el fondo desenfocado, acercar el cuadro (un deshacer
  // por arrastre del deslizador) y centrarlo. Qué parte se ve se elige
  // arrastrando sobre el video: lo dice la ayuda, y si el cuadro no tiene
  // margen para moverse (mide justo el lienzo), pide acercarlo.
  _armarEncuadre(m) {
    const id = m.clipId;
    const fs = this._opciones(this.cuerpo, {
      nombre: "ed-encuadre-modo", etiqueta: t("prop.encuadre"), opciones: m.encuadre.opciones,
      leer: (x) => ({ valor: x.encuadre.modo }),
      aplicar: (v) => this._cambiar(null, cambioModoEncuadre(v)),
    });
    fs.classList.add("ed-encuadre");
    fs.querySelector(".ed-prop-segmentado")?.classList.add("ed-encuadre-modos");
    this._deslizador(fs, {
      id: "ed-encuadre-zoom", etiqueta: t("prop.encuadre_zoom"), min: 100, max: 400,
      leer: (x) => ({ valor: x.encuadre.zoomPct }),
      aplicar: (v) => this._cambiar(`${id}:encuadre-zoom`, cambioZoomEncuadre(v)),
    });
    const acciones = el("div", "ed-prop-acciones", fs);
    this._boton(acciones, {
      texto: t("prop.centrar"), leer: (x) => ({ deshabilitado: x.encuadre.centrado }),
      aplicar: () => this._cambiar(null, cambioCentrarEncuadre()),
    }).id = "ed-encuadre-centrar";
    this._nota(fs, (x) => x.encuadre.ayuda);
    this._nota(fs, (x) => x.encuadre.aviso, "ed-prop-aviso");
  }

  // Transición al siguiente video: el tipo y su duración. Si no cupo entera
  // (el primer video no tiene de dónde sacar la cola), se dice aquí.
  _armarTransicion(m) {
    const id = m.clipId;
    const fs = el("fieldset", "ed-prop-campo", this.cuerpo);
    el("legend", "ed-prop-etiqueta", fs, t("prop.transicion_siguiente"));
    const campo = el("div", "ed-prop-campo", fs);
    const label = el("label", "ed-prop-etiqueta ed-prop-etiqueta-sub", campo, t("prop.tipo"));
    label.htmlFor = "ed-prop-transicion";
    const tipo = el("select", "", campo);
    tipo.id = "ed-prop-transicion";
    for (const tr of m.transiciones) tipo.append(new Option(tr.texto, tr.valor));
    const poner = (valor, ms, clave = null) => {
      if (!this._operar(clave, "ponerTransicion", id, valor, ms)) return;
      const aviso = avisoTransicion(this.editor.doc(), id, valor, ms);
      if (aviso) this._decir(aviso, true);
    };
    const duracion = this._deslizador(fs, {
      id: "ed-prop-transicion-ms", etiqueta: t("prop.duracion"), min: m.transicion.min, max: m.transicion.max,
      paso: m.transicion.paso, escribir: textoSegundos,
      leer: (x) => ({ valor: x.transicion.duracionMs, texto: textoSegundos(x.transicion.duracionMs),
                      deshabilitado: !x.transicion.disponible || x.transicion.tipo === "corte" }),
      aplicar: (v) => poner(this.m.transicion.tipo, v, `${id}:transicion`),
    });
    tipo.addEventListener("change", () => {
      tipo.blur();
      poner(tipo.value, Number(duracion.value) || m.transicion.duracionMs);
    });
    this.pintores.push((x) => {
      tipo.value = x.transicion.tipo;
      tipo.disabled = !x.transicion.disponible;
    });
    this._nota(fs, (x) => x.transicion.motivo);
    this._nota(fs, (x) => x.transicion.ayuda);         // capa 5b, D9: junta los dos clips
  }

  _armarTexto(m) {
    const id = m.clipId;
    const formato = () => this.editor.doc().formato;
    this._cabeza(t("fila.texto"));
    // El texto: se aplica al escribir (un deshacer por racha) y nunca vacío.
    const campo = el("div", "ed-prop-campo", this.cuerpo);
    const label = el("label", "ed-prop-etiqueta", campo, t("fila.texto"));
    label.htmlFor = "ed-prop-texto";
    const area = el("textarea", "", campo);
    Object.assign(area, { id: "ed-prop-texto", rows: 3 });
    this.textarea = area;
    const vacio = el("p", "ed-prop-nota ed-prop-error", campo, t(TEXTO_VACIO));
    vacio.hidden = true;
    area.addEventListener("input", () => {
      const escrito = area.value;
      vacio.hidden = Boolean(escrito.trim());
      if (!vacio.hidden) return;
      this._operar(`${id}:texto`, "editarTexto", id, escrito, this.m.texto.destino);
    });
    area.addEventListener("blur", () => {
      vacio.hidden = true;
      // lo que quedó guardado (sin espacios de más; vacío = lo de antes) — salvo
      // que el campo se esté yendo con su formulario (otro clip elegido)
      if (area.isConnected && this.textarea === area) this.pintar();
    });
    this.pintores.push((x) => {
      area.readOnly = !x.texto.editable;
      if (document.activeElement !== area && area.value !== x.texto.valor) area.value = x.texto.valor;
    });
    this._nota(campo, (x) => x.texto.nota);
    this._armarAvisos(campo);                                     // capa 5c: se ven mientras se escribe
    this._armarFuentes(m);
    this._deslizador(this.cuerpo, {
      id: "ed-prop-tamano", etiqueta: t("prop.tamano"), min: m.tamano.min, max: m.tamano.max, escribir: (v) => String(v),
      leer: (x) => ({ valor: x.tamano.px }),
      aplicar: (v) => this._cambiar(`${id}:tamano`, { estilo: { tamano: v } }),
    });
    this._armarAncho(m);
    this._paleta(m);
    // Contorno: sí/no y, si sí, su color y su grosor
    this._casilla(this.cuerpo, {
      etiqueta: t("prop.contorno"), leer: (x) => x.contorno.activo,
      aplicar: (si) => this._cambiar(null, cambioContorno(si, formato())),
    });
    const contorno = this._seccion(this.cuerpo, (x) => x.contorno.activo);
    this._color(contorno, {
      id: "ed-prop-contorno-color", etiqueta: t("prop.color_contorno"), leer: (x) => x.contorno.color,
      aplicar: (c) => this._cambiar(`${id}:contorno-color`, { estilo: { contorno: { color: c } } }),
    });
    this._deslizador(contorno, {
      id: "ed-prop-grosor", etiqueta: t("prop.grosor"), min: m.contorno.min, max: m.contorno.max, escribir: (v) => String(v),
      leer: (x) => ({ valor: x.contorno.grosorPx }),
      aplicar: (v) => this._cambiar(`${id}:grosor`, cambioGrosor(v, formato())),
    });
    this._casilla(this.cuerpo, {
      etiqueta: t("prop.sombra"), leer: (x) => x.sombra.activo,
      aplicar: (si) => this._cambiar(null, cambioSombra(si, formato())),
    });
    // Fondo: la forma y, con uno puesto, su color y su opacidad
    this._opciones(this.cuerpo, {
      nombre: "ed-prop-fondo", etiqueta: t("prop.fondo"), opciones: traducidas(FONDOS),
      leer: (x) => ({ valor: x.fondo.tipo }),
      aplicar: (v) => this._cambiar(null, cambioFondo(v, this._clip()?.estilo?.fondo ?? null)),
    });
    const fondo = this._seccion(this.cuerpo, (x) => x.fondo.tipo !== "ninguno");
    this._color(fondo, {
      id: "ed-prop-fondo-color", etiqueta: t("prop.color_fondo"), leer: (x) => x.fondo.color,
      aplicar: (c) => this._cambiar(`${id}:fondo-color`, { estilo: { fondo: { color: c } } }),
    });
    this._deslizador(fondo, {
      id: "ed-prop-fondo-opacidad", etiqueta: t("prop.opacidad_fondo"),
      leer: (x) => ({ valor: x.fondo.opacidad }),
      aplicar: (v) => this._cambiar(`${id}:fondo-opacidad`, { estilo: { fondo: { opacidad: v / 100 } } }),
    });
    this._opciones(this.cuerpo, {
      nombre: "ed-prop-alineacion", etiqueta: t("prop.alineacion"), opciones: traducidas(ALINEACIONES),
      leer: (x) => ({ valor: x.alineacion }),
      aplicar: (v) => this._cambiar(null, { estilo: { alineacion: v } }),
    });
    this._opciones(this.cuerpo, {
      nombre: "ed-prop-animacion", etiqueta: t("prop.animacion"), opciones: traducidas(ANIMACIONES),
      leer: (x) => ({ valor: x.animacion }),
      aplicar: (v) => this._cambiar(null, { animacion: { entrada: v } }),
    });
    const fs = el("fieldset", "ed-prop-campo", this.cuerpo);
    el("legend", "ed-prop-etiqueta", fs, t("prop.posicion"));
    const acciones = el("div", "ed-prop-acciones", fs);
    this._boton(acciones, {
      texto: t("prop.centrar_ancho"), leer: (x) => ({ deshabilitado: x.centrado.x, titulo: x.centrado.x ? t("prop.centrado_ancho") : "" }),
      aplicar: () => this._cambiar(null, { transform: { x: 0.5 } }),
    });
    this._boton(acciones, {
      texto: t("prop.centrar_alto"), leer: (x) => ({ deshabilitado: x.centrado.y, titulo: x.centrado.y ? t("prop.centrado_alto") : "" }),
      aplicar: () => this._cambiar(null, { transform: { y: 0.5 } }),
    });
    this._botonBorrar();
  }

  // Capa 5c (D7.5): lo que no sale en el video como se escribió, bajo el
  // campo del texto (propiedades_modelo.avisosTexto); el de un texto de antes
  // trae «Mostrar los emojis» — una operación, un deshacer. Se rehace solo
  // cuando los avisos cambian (no a cada letra).
  _armarAvisos(padre) {
    const caja = el("div", "ed-prop-avisos", padre);
    caja.setAttribute("aria-live", "polite");
    let firma = null;
    this.pintores.push((x) => {
      const nueva = JSON.stringify(x.avisos);
      if (nueva === firma) return;
      firma = nueva;
      caja.replaceChildren();
      caja.hidden = x.avisos.length === 0;
      for (const a of x.avisos) {
        el("p", "ed-prop-nota ed-prop-aviso", caja, a.texto);
        if (a.accion !== "actualizar") continue;
        const fila = el("div", "ed-prop-acciones", caja);
        this._boton(fila, {
          texto: t("prop.mostrar_emojis"), aplicar: () => this._operar(null, "actualizarTexto", this.m.clipId),
        }).id = "ed-prop-mostrar-emojis";
      }
    });
  }

  // Capa 5c (D9.4): la lista de fuentes por familia de estilo (un encabezado
  // por familia, solo las que tienen fuentes), cada nombre escrito en su
  // fuente. La página baja al abrir solo las fuentes que usa el documento
  // (D9.3): la primera vez que se pinta esta lista pide las demás, para que
  // cada nombre se vea en su letra (vista.cargarFuentes no pide dos veces la
  // misma).
  _armarFuentes(m) {
    const fs = el("fieldset", "ed-prop-campo ed-fuentes", this.cuerpo);
    el("legend", "ed-prop-etiqueta", fs, t("prop.fuente"));
    const radios = [];
    for (const g of m.fuentes) {
      const grupo = el("div", "ed-fuentes-grupo", fs);
      const titulo = el("p", "ed-fuentes-familia", grupo, g.texto);
      titulo.id = `ed-fuentes-${g.categoria}`;
      grupo.setAttribute("role", "group");
      grupo.setAttribute("aria-labelledby", titulo.id);
      const lista = el("div", "segmentado ed-prop-segmentado", grupo);
      lista.classList.add("ed-prop-lista");             // como la lista de _opciones: una opción por línea
      for (const f of g.fuentes) {
        const l = el("label", "", lista);
        const r = el("input", "", l);
        Object.assign(r, { type: "radio", name: "ed-prop-fuente", value: f.valor });
        r.setAttribute("aria-label", f.texto);
        el("span", "", l, f.texto).style.fontFamily = `"${f.valor}", var(--font-body)`;
        r.addEventListener("change", () => {
          if (r.checked) this._cambiar(null, { estilo: { fuente: f.valor } });
        });
        radios.push(r);
      }
    }
    this.pintores.push((x) => {
      for (const r of radios) r.checked = r.value === String(x.fuente);
    });
    const ids = m.fuentes.flatMap((g) => g.fuentes.map((f) => f.valor));
    if (!this.fuentesPedidas && ids.length) {
      this.fuentesPedidas = true;
      this.editor.cargarFuentes?.(ids);
    }
  }

  // «Ancho del texto» (capa 5c, D7.2): 30–100 % del ancho del video (un
  // deshacer por arrastre: clave <id>:ancho) y «Sin límite», que deja el
  // deslizador quieto. Los dos en una fila que se envuelve en el celular.
  _armarAncho(m) {
    const id = m.clipId;
    const campo = el("div", "ed-prop-campo ed-prop-ancho", this.cuerpo);
    const fila = el("div", "ed-prop-fila", campo);
    const label = el("label", "ed-prop-etiqueta", fila, t("prop.ancho"));
    label.htmlFor = "ed-prop-ancho";
    const salida = el("output", "ed-prop-valor", fila);
    salida.setAttribute("for", "ed-prop-ancho");
    const controles = el("div", "ed-prop-ancho-fila", campo);
    const input = el("input", "", controles);
    Object.assign(input, { type: "range", id: "ed-prop-ancho", min: String(m.ancho.min), max: String(m.ancho.max), step: "1" });
    input.addEventListener("input", () => {
      const v = Number(input.value);
      salida.textContent = textoPorcentaje(v);
      this._cambiar(`${id}:ancho`, cambioAncho(v));
    });
    input.addEventListener("change", () => this.pintar());      // al soltar: el valor que de verdad quedó
    const etiqueta = el("label", "ed-prop-casilla", controles);
    const casilla = el("input", "", etiqueta);
    Object.assign(casilla, { type: "checkbox", id: "ed-prop-sin-limite" });
    etiqueta.append(t("prop.sin_limite"));
    casilla.addEventListener("change", () => this._cambiar(null, cambioSinLimite(casilla.checked)));
    this.pintores.push((x) => {
      input.disabled = x.ancho.sinLimite;
      if (input.value !== String(x.ancho.pct)) input.value = String(x.ancho.pct);
      salida.textContent = x.ancho.sinLimite ? "—" : textoPorcentaje(x.ancho.pct);
      casilla.checked = x.ancho.sinLimite;
    });
  }

  // Color del texto: blanco, negro, el de la marca, amarillo, rojo y uno libre.
  _paleta(m) {
    const id = m.clipId;
    const fs = el("fieldset", "ed-prop-campo", this.cuerpo);
    el("legend", "ed-prop-etiqueta", fs, t("prop.color"));
    const fila = el("div", "ed-prop-colores", fs);
    const muestras = m.paleta.map((c) => {
      const b = el("button", "ed-prop-muestra", fila);
      b.type = "button";
      b.style.background = c.color;
      b.title = c.nombre;
      b.setAttribute("aria-label", c.nombre);
      b.addEventListener("click", () => this._cambiar(null, { estilo: { color: c.color } }));
      return { b, color: c.color };
    });
    const otro = el("label", "ed-prop-otro", fila);
    const input = el("input", "ed-prop-color", otro);
    input.type = "color";
    otro.append(t("prop.otro"));
    input.addEventListener("input", () => this._cambiar(`${id}:color`, { estilo: { color: input.value.toUpperCase() } }));
    this.pintores.push((x) => {
      for (const { b, color } of muestras) b.setAttribute("aria-pressed", String(color === x.color));
      const v = x.color.toLowerCase();
      if (input.value !== v) input.value = v;
    });
  }

  _armarImagen(m) {
    const id = m.clipId;
    const medidas = () => {
      const clip = this._clip();
      return { clip, material: this.materiales()?.[clip?.material_id] ?? null, formato: this.editor.doc().formato };
    };
    this._cabeza(t("clip.imagen"));
    this._deslizador(this.cuerpo, {
      id: "ed-prop-imagen-tamano", etiqueta: t("prop.tamano_imagen"), min: m.tamano.min, max: m.tamano.max,
      leer: (x) => ({ valor: x.tamano.porcentaje, min: x.tamano.min, max: x.tamano.max }),
      aplicar: (v) => {
        const { clip, material, formato } = medidas();
        if (clip) this._cambiar(`${id}:escala`, { transform: { escala: escalaDePorcentaje(v, clip, material, formato) } });
      },
    });
    this._deslizador(this.cuerpo, {
      id: "ed-prop-imagen-opacidad", etiqueta: t("prop.opacidad"),
      leer: (x) => ({ valor: x.opacidad }),
      aplicar: (v) => this._cambiar(`${id}:opacidad`, { transform: { opacidad: v / 100 } }),
    });
    const acciones = el("div", "ed-prop-acciones", this.cuerpo);
    this._boton(acciones, {
      texto: t("prop.llenar"), leer: (x) => ({ deshabilitado: x.llena }),
      aplicar: () => {
        const { clip, material, formato } = medidas();
        if (!clip || !this._cambiar(null, cambioLlenar(clip, material, formato))) return;
        if (!this.m.llenar.alcanza) this._decir(t("prop.imagen_chica"), true);
      },
    });
    this._boton(acciones, {
      texto: t("prop.centrar"), leer: (x) => ({ deshabilitado: x.centrada }),
      aplicar: () => this._cambiar(null, { transform: { x: 0.5, y: 0.5 } }),
    });
    this._botonBorrar();
  }

  _armarAudio(m) {
    const id = m.clipId;
    this._cabeza(m.nombre);
    this._deslizador(this.cuerpo, {
      id: "ed-prop-volumen", etiqueta: t("prop.volumen"),
      leer: (x) => ({ valor: x.volumen }),
      aplicar: (v) => {
        this.silencios.delete(id);
        this._cambiar(`${id}:volumen`, { audio: { volumen: v / 100 } });
      },
    });
    for (const [campo, etiqueta, clave] of [["entradaMs", t("prop.fundido_entrada"), "fundido_entrada_ms"],
      ["salidaMs", t("prop.fundido_salida"), "fundido_salida_ms"]]) {
      this._deslizador(this.cuerpo, {
        id: `ed-prop-${clave.replaceAll("_", "-")}`, etiqueta, min: 0, max: m.fundidos.max, paso: m.fundidos.paso,
        escribir: textoSegundos,
        leer: (x) => ({ valor: x.fundidos[campo], max: x.fundidos.max, texto: textoSegundos(x.fundidos[campo]),
                        deshabilitado: x.fundidos.max <= 0 }),
        aplicar: (v) => this._cambiar(`${id}:${clave}`, { audio: { [clave]: v } }),
      });
    }
    const acciones = el("div", "ed-prop-acciones", this.cuerpo);
    this._boton(acciones, {
      texto: t("prop.silenciar"),
      leer: (x) => ({ texto: x.silenciado ? t("prop.volver_oir") : t("prop.silenciar"), presionado: x.silenciado }),
      aplicar: () => {
        const antes = this._clip()?.audio?.volumen ?? 1;
        const r = alternarSilencio(antes, this.silencios.get(id) ?? null);
        if (!this._cambiar(null, { audio: { volumen: r.volumen } })) return;
        if (r.recordar === null) this.silencios.delete(id);
        else this.silencios.set(id, r.recordar);
      },
    });
    this._nota(this.cuerpo, (x) => x.nota);
    this._armarSuenaEn();
    // «Subtítulos de este audio»: la pestaña Subtítulos (ahí se elige de dónde
    // salen y se generan, con el precio a la vista)
    const subtitulos = el("div", "ed-prop-acciones", this.cuerpo);
    this._boton(subtitulos, {
      texto: t("prop.subtitulos_audio"), leer: (x) => ({ deshabilitado: !x.subtitulos }),
      aplicar: () => this.editor.mostrarBiblioteca?.("subtitulos"),
    }).id = "ed-prop-subtitulos-audio";
    this._botonBorrar();
  }

  // «Suena en» (capa 5a, D10): una voz agregada en el editor suena solo en su
  // idioma o en todos. Las opciones cambian con el destino que se ve, así que
  // se vuelven a poner cuando cambian.
  _armarSuenaEn() {
    const campo = el("div", "ed-prop-campo", this.cuerpo);
    const label = el("label", "ed-prop-etiqueta", campo, t("prop.suena_en"));
    label.htmlFor = "ed-prop-suena-en";
    const sel = el("select", "", campo);
    sel.id = "ed-prop-suena-en";
    sel.addEventListener("change", () => {
      sel.blur();                    // si no, S, Supr y Ctrl+Z irían al select
      this._cambiar(null, cambioSuenaEn(sel.value));
    });
    this.pintores.push((x) => {
      campo.hidden = !x.suena_en;
      if (!x.suena_en) return;
      const firma = JSON.stringify(x.suena_en.opciones);
      if (sel.dataset.firma !== firma) {
        sel.replaceChildren(...x.suena_en.opciones.map((o) => new Option(o.texto, o.valor)));
        sel.dataset.firma = firma;
      }
      sel.value = x.suena_en.valor;
    });
  }

  // El sonido de la escena sigue a su video: se cambia desde ahí.
  _armarSonido(m) {
    this._cabeza(t("fila.sonido_escena"));
    el("p", "ed-prop-nota", this.cuerpo, t("prop.nota_sonido"));
    const acciones = el("div", "ed-prop-acciones", this.cuerpo);
    this._boton(acciones, {
      texto: t("prop.elegir_video"), leer: (x) => ({ deshabilitado: !x.principalId }),
      aplicar: () => this.m.principalId && this.editor.seleccionar(this.m.principalId),
    });
  }

  // Algo que el video final no hace (un video encima de otro): solo se borra.
  _armarOtro(m) {
    this._cabeza(m.nombre);
    el("p", "ed-prop-nota", this.cuerpo, t("prop.nota_otro"));
    this._botonBorrar();
  }
}

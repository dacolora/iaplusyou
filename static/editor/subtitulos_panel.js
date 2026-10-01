// La pestaña «Subtítulos» del editor (capa 5a, Task 7; spec D4, D6, D7, D12):
// lo que se ve dentro de la zona que le da la biblioteca
// (`biblioteca.zona("subtitulos")`), de arriba abajo:
//
// - el estado del idioma que se ve («Subtítulos de la voz · 42 palabras.») y
//   «Mostrar los subtítulos»;
// - «¿De dónde salen?»: la voz, el sonido del video o un audio de la edición
//   (las que no se pueden, apagadas y con su porqué), el idioma de lo que se
//   dice (solo si hay algo que transcribir) y «Generar subtítulos» con el
//   precio que calcula el servidor (gratis si todo ya está transcrito: no se
//   llama a nadie). Pagar encola la transcripción; la barra sigue el trabajo
//   (y lo retoma si la página se recarga) y, al terminar, trae las palabras y
//   pone la fuente con una OPERACIÓN sobre el documento de ese momento (nunca
//   reemplaza el documento: lo editado mientras tanto no se pierde);
// - el estilo (cuatro tarjetas que se ven como su estilo), el color de la
//   palabra que suena, la altura y el tamaño;
// - «Lo que dicen los subtítulos»: una línea por fila con su tiempo (lleva el
//   cabezal ahí), sus palabras (tocar una la abre para corregirla: Enter
//   guarda, Esc la deja, vacía se quita; una corregida se marca y puede volver
//   a lo que se oyó) y «Quitar la línea»; la línea que suena se marca;
// - «Quitar los subtítulos de este idioma» (con confirmación).
//
// Lo que se decide (qué fuentes, qué falta, las líneas, los textos) es de
// subtitulos_modelo.js (puro, probado en Node); aquí solo el DOM y la red. La
// edición se toca SOLO por `editor` (pagina_editor.js); con la edición
// cambiada en otra pestaña (`enConflicto`) no se cambia nada ni se paga nada.
// No hace nada al importarse (lo prueba Node).
import { mensajeSesion, sesionTerminada } from "./guardado.js";
import { ESTILOS_SUBTITULOS } from "./operaciones.js";
import { avisoEmoji, mensajeConflicto, textoPorcentaje, tieneEmoji } from "./propiedades_modelo.js";
import { valorDestino } from "./resolver.js";
import { derivar, palabrasDe } from "./subtitulos_fuente.js";
import {
  alturaDePosicion, coloresResaltado, estadoPanel, estilosPanel, fuenteDeClave, fuentePorDefecto, fuentesDisponibles,
  idiomaPorDefecto, lineaEn, lineasListado, pedido, posicionDeAltura, POSICIONES, resaltadoElegido, textoBoton, textoEstado,
  textoTiempo,
} from "./subtitulos_modelo.js";
import { t } from "./textos.js";

export const ESPERA_ESTIMAR_MS = 300;
export const INTERVALO_TRABAJO_MS = 1500;
const REINTENTOS_ESTIMAR = 3;           // si el precio no se pudo calcular, se reintenta solo (gratis)
const REINTENTO_ESTIMAR_MS = 8000;
const MAX_CORRECCION = 120;             // operaciones.MAX_CORRECCION / documento (D3)
const PEDIDO_VACIO = { todos: [], faltan: [], mudos: [], cargar: [] };

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

const idiomaDe = (destino) => String(destino ?? "").split("_")[0];

export class SubtitulosPanel {
  // `contenedor`: la zona de la pestaña (biblioteca.zona("subtitulos"));
  // `editor`: el de pagina_editor.js; `datos`: los de la página (urls,
  // config.subtitulos.estilos, subtitulos.idiomas, trabajos_vivos, edicion).
  constructor({ contenedor, editor, datos }) {
    this.contenedor = contenedor;
    this.editor = editor;
    this.datos = datos ?? {};
    this.urls = this.datos.urls ?? {};
    this.estilos = this.datos.config?.subtitulos?.estilos ?? {};
    this.idiomas = this.datos.subtitulos?.idiomas ?? [];
    this.nombresIdioma = this.datos.subtitulos?.nombres_idioma ?? {};
    this.claveElegida = null;           // la fuente que tocó la persona (null: la que toque)
    this.clave = null;                  // la fuente que se ve elegida
    this.idioma = null;                 // idioma de lo que se dice
    this.destinoVisto = undefined;
    this.estado = { tipo: "ninguno", clave: null, n: 0 };
    this.pedidoActual = PEDIDO_VACIO;
    this.estimado = null;               // {firma, calculando | error | gratis | precio}
    this.turnoEstimar = 0;
    this.relojEstimar = null;
    this.enviando = false;              // el POST de «Generar» va en camino
    this.trabajo = null;                // {job, pedido: {idioma, clave, ids} | null, etapa, progreso, fallos}
    this.relojTrabajo = null;
    this.relojMensaje = null;
    this.editando = null;               // la palabra abierta para corregir
    this.lineas = [];
    this.firmaLineas = null;
    this.firmaFuentes = null;
    this.firmaColores = null;
    this.lineaActual = -1;
    if (!contenedor || !editor) return;
    this._construir();
    editor.escuchar((que) => {
      if (que === "tiempo") this._marcarLinea();
      else if (que === "biblioteca") this._alMostrar();
      else if (que === "documento" || que === "destino" || que === "materiales") this.pintar();
    });
    this.pintar();
    const vivo = this.datos.trabajos_vivos?.subtitulos;
    if (vivo) this.seguir(vivo, this._pedidoGuardado(vivo));
  }

  // ---- Armar (una vez) ----

  _construir() {
    const c = this.contenedor;
    c.replaceChildren();
    const raiz = el("div", "ed-sub", c);
    this.raiz = raiz;
    this.aviso = el("p", "editor-aviso ed-sub-aviso", raiz);
    this.aviso.id = "ed-sub-aviso";
    this.aviso.setAttribute("aria-live", "polite");
    this.aviso.hidden = true;
    this.detalle = el("details", "ed-sub-detalle", raiz);
    this.detalle.id = "ed-sub-detalle";
    this.detalle.hidden = true;
    el("summary", "", this.detalle, t("prop.detalle_tecnico"));
    this.detalleTexto = el("pre", "", this.detalle);

    // 1. Estado y «Mostrar los subtítulos»
    const s1 = el("div", "ed-sub-seccion ed-sub-primera", raiz);
    this.estadoTexto = el("p", "ed-sub-estado", s1);
    this.estadoTexto.id = "ed-sub-estado";
    const casilla = el("label", "ed-sub-casilla", s1);
    this.visibles = el("input", "", casilla);
    this.visibles.type = "checkbox";
    this.visibles.id = "ed-sub-visibles";
    el("span", "", casilla, t("sub.mostrar"));

    // 2. ¿De dónde salen? + idioma + «Generar»
    const s2 = el("fieldset", "ed-sub-seccion", raiz);
    el("legend", "", s2, t("sub.de_donde"));
    this.listaFuentes = el("div", "ed-sub-fuentes", s2);
    this.listaFuentes.id = "ed-sub-fuente";
    this.zonaGenerar = el("div", "ed-sub-campo", s2);
    this.campoIdioma = el("div", "ed-sub-campo", this.zonaGenerar);
    const lIdioma = el("label", "ed-sub-etiqueta", this.campoIdioma, t("sub.idioma_habla"));
    lIdioma.htmlFor = "ed-sub-idioma";
    this.selIdioma = el("select", "", this.campoIdioma);
    this.selIdioma.id = "ed-sub-idioma";
    for (const i of this.idiomas) this.selIdioma.append(new Option(this.nombresIdioma[i] ?? i, i));
    this.generarBoton = boton("btn-generar ed-sub-generar", this.zonaGenerar);
    this.generarBoton.id = "ed-sub-generar";
    this.progreso = el("progress", "ed-sub-progreso", this.zonaGenerar);
    this.progreso.id = "ed-sub-progreso";
    this.progreso.max = 100;
    this.progreso.hidden = true;

    // 3. Estilo, color, altura y tamaño
    const s3 = el("fieldset", "ed-sub-seccion", raiz);
    el("legend", "", s3, t("sub.estilo"));
    this.listaEstilos = el("div", "ed-sub-estilos", s3);
    this.listaEstilos.id = "ed-sub-estilos";
    const muestra = t("sub.muestra").split(/\s+/).filter(Boolean);
    this.botonesEstilo = estilosPanel(this.estilos).map((e) => {
      const b = boton("ed-sub-estilo", this.listaEstilos);
      b.dataset.estilo = e.id;
      b.setAttribute("aria-pressed", "false");
      const caja = el("span", `ed-sub-muestra ed-sub-muestra-${e.id}`, b);
      caja.setAttribute("aria-hidden", "true");
      this._muestra(el("span", "", caja), e, muestra);
      el("span", "ed-sub-estilo-nombre", b, e.nombre);
      return b;
    });
    this.campoResaltado = el("fieldset", "ed-sub-campo", s3);
    this.campoResaltado.id = "ed-sub-resaltado";
    el("legend", "", this.campoResaltado, t("sub.resaltado"));
    this.listaColores = el("div", "ed-sub-colores", this.campoResaltado);
    const altura = el("fieldset", "ed-sub-campo", s3);
    const leyendaAltura = el("legend", "", altura, t("sub.altura"));
    leyendaAltura.id = "ed-sub-altura-titulo";
    this.listaPosiciones = el("div", "ed-sub-opciones", altura);
    this.listaPosiciones.id = "ed-sub-posicion";
    this.botonesPosicion = POSICIONES.map((p) => {
      const b = boton("btn-sm", this.listaPosiciones, t(p.texto));
      b.dataset.posicion = String(p.valor);
      b.setAttribute("aria-pressed", "false");
      return b;
    });
    const filaAltura = el("div", "ed-sub-fila-rango", altura);
    this.altura = el("input", "", filaAltura);
    Object.assign(this.altura, { type: "range", id: "ed-sub-altura", min: "10", max: "90", step: "1" });
    this.altura.setAttribute("aria-labelledby", "ed-sub-altura-titulo");
    this.alturaValor = el("output", "ed-sub-valor", filaAltura);
    this.alturaValor.setAttribute("for", "ed-sub-altura");
    const tam = el("div", "ed-sub-campo", s3);
    const filaTam = el("div", "ed-sub-fila-rango", tam);
    const lTam = el("label", "ed-sub-etiqueta", filaTam, t("prop.tamano"));
    lTam.htmlFor = "ed-sub-tamano";
    this.tamanoValor = el("output", "ed-sub-valor", filaTam);
    this.tamanoValor.setAttribute("for", "ed-sub-tamano");
    this.tamano = el("input", "", tam);
    Object.assign(this.tamano, { type: "range", id: "ed-sub-tamano", min: "60", max: "160", step: "5" });

    // 4. Lo que dicen
    this.seccionLineas = el("div", "ed-sub-seccion", raiz);
    const titulo = el("h3", "ed-sub-titulo", this.seccionLineas, t("sub.lineas"));
    titulo.id = "ed-sub-lineas-titulo";
    const ayuda = el("p", "ed-sub-nota", this.seccionLineas, t("sub.ayuda_lineas"));
    ayuda.id = "ed-sub-lineas-ayuda";
    this.emoji = el("p", "ed-sub-nota ed-sub-advertencia", this.seccionLineas, avisoEmoji());
    this.emoji.id = "ed-sub-emoji";
    this.emoji.hidden = true;
    this.listaLineas = el("ol", "ed-sub-lineas", this.seccionLineas);
    this.listaLineas.id = "ed-sub-lineas";
    this.listaLineas.setAttribute("aria-labelledby", "ed-sub-lineas-titulo");

    // 5. Quitar todo (este idioma)
    const pie = el("div", "ed-sub-pie", raiz);
    this.quitarBoton = boton("btn-sm btn-peligro", pie, t("sub.quitar_todos"));
    this.quitarBoton.id = "ed-sub-quitar";

    // Escuchas una sola vez (delegación): repintar no suma escuchas.
    raiz.addEventListener("click", (e) => this._clic(e));
    raiz.addEventListener("change", (e) => this._cambio(e));
    raiz.addEventListener("input", (e) => this._entrada(e));
    raiz.addEventListener("keydown", (e) => this._tecla(e));
    // con una palabra abierta, tocar otra no le quita el foco antes del clic
    // (si no, guardar la primera rehace la lista y el clic se pierde)
    raiz.addEventListener("pointerdown", (e) => {
      if (this.editando && e.target.closest?.("button.ed-sub-palabra")) e.preventDefault();
    });
  }

  // La muestra de una tarjeta de estilo: «Así se ven» escrito como ese
  // estilo (Palabra grande: solo la primera palabra; los que resaltan, una
  // palabra con el color de la palabra que suena).
  _muestra(span, estilo, palabras) {
    const lista = estilo.id === "palabra_grande" ? palabras.slice(0, 1) : palabras;
    const sonando = estilo.resalta ? Math.min(1, lista.length - 1) : -1;
    lista.forEach((p, i) => {
      if (i) span.append(" ");
      if (i === sonando) el("span", "ed-sub-sonando", span, p);
      else span.append(p);
    });
  }

  // ---- Pintar ----

  pintar() {
    if (!this.raiz) return;
    const ed = this.editor;
    const doc = ed.doc();
    const r = ed.resuelto?.() ?? null;
    const mats = ed.materiales?.() ?? {};
    const destino = ed.destino?.() ?? null;
    if (destino !== this.destinoVisto) {             // otro destino: lo de antes no vale (D12)
      this.destinoVisto = destino;
      this.claveElegida = null;
      this.idioma = idiomaPorDefecto(destino, this.idiomas);
      if (this.idioma) this.selIdioma.value = this.idioma;
    }
    const sub = doc?.subtitulos ?? {};
    this.estado = r ? estadoPanel(doc, r, palabrasDe(mats)) : { tipo: "ninguno", clave: null, n: 0 };
    // sin resuelto: todavía arranca (o ese destino no se pudo preparar: lo dice el aviso de debajo del video)
    this.estadoTexto.textContent = r ? textoEstado(this.estado, mats) : (destino ? "" : t("bib.cargando"));
    this.estadoTexto.dataset.tipo = this.estado.tipo;
    this.visibles.checked = sub.visibles !== false;
    const opciones = r ? fuentesDisponibles(r, mats) : [];
    this.clave = fuentePorDefecto(opciones, this.estado, this.claveElegida);
    this._pintarFuentes(opciones);
    this.pedidoActual = r && this.clave ? pedido(r, this.clave, mats) : PEDIDO_VACIO;
    this._pedirEstimado();
    this._pintarGenerar();
    this._pintarEstilo(doc);
    this._pintarLineas(doc, r, mats);
    this.quitarBoton.hidden = !(this.estado.tipo === "derivados" || this.estado.tipo === "legado");
  }

  _pintarFuentes(opciones) {
    const firma = JSON.stringify(opciones);
    if (firma !== this.firmaFuentes) {
      this.firmaFuentes = firma;
      this.listaFuentes.replaceChildren(...opciones.map((o) => {
        const l = el("label", "ed-sub-fuente");
        const r = el("input", "", l);
        Object.assign(r, { type: "radio", name: "ed-sub-fuente", value: o.clave, disabled: !o.disponible });
        const txt = el("span", "", l);
        el("strong", "", txt, o.etiqueta);
        if (o.motivo) el("small", "", txt, o.motivo);
        return l;
      }));
    }
    for (const r of this.listaFuentes.querySelectorAll('input[name="ed-sub-fuente"]')) r.checked = r.value === this.clave;
  }

  // ¿Ya está puesta la fuente elegida, con todo transcrito y a la vista? Entonces
  // no hay nada que generar (la derivación la sigue sola: D1).
  _yaPuesta() {
    const p = this.pedidoActual;
    return this.estado.tipo === "derivados" && this.estado.clave === this.clave && !p.faltan.length && !p.cargar.length;
  }

  _pintarGenerar() {
    const p = this.pedidoActual;
    const corriendo = Boolean(this.trabajo) || this.enviando;
    const est = this.estimado;
    this.zonaGenerar.hidden = !corriendo && (this._yaPuesta() || !this.clave || !p.todos.length);
    this.campoIdioma.hidden = corriendo || !p.faltan.length || Boolean(est?.gratis);
    this.generarBoton.textContent = textoBoton({
      corriendo, etapa: this.trabajo?.etapa ?? "", calculando: Boolean(est?.calculando), error: Boolean(est?.error),
      gratis: Boolean(est?.gratis), precio: est?.precio ?? "",
    });
    this.generarBoton.disabled = corriendo || !est || Boolean(est.calculando) || Boolean(est.error) || this._enConflicto();
    this.progreso.hidden = !this.trabajo;
    if (this.trabajo) this.progreso.value = Math.max(0, Math.min(100, Number(this.trabajo.progreso) || 0));
  }

  _pintarEstilo(doc) {
    const sub = doc?.subtitulos ?? {};
    const estiloId = ESTILOS_SUBTITULOS.includes(sub.estilo_id) ? sub.estilo_id : "karaoke";
    for (const b of this.botonesEstilo) b.setAttribute("aria-pressed", String(b.dataset.estilo === estiloId));
    // las muestras que resaltan, con el color elegido (o el del estilo)
    this.raiz.style.setProperty("--ed-sub-resaltado", resaltadoElegido({ ...sub, estilo_id: "karaoke" }, this.estilos) ?? "#FFD400");
    const resaltado = resaltadoElegido(sub, this.estilos);
    this.campoResaltado.hidden = !resaltado;
    const colores = coloresResaltado(doc);
    const firma = JSON.stringify(colores);
    if (firma !== this.firmaColores) {
      this.firmaColores = firma;
      this.listaColores.replaceChildren(...colores.map((c) => {
        const b = boton("ed-sub-color");
        b.dataset.color = c.color;
        b.style.background = c.color;
        b.title = c.nombre;
        b.setAttribute("aria-label", c.nombre);
        return b;
      }));
    }
    for (const b of this.listaColores.children) b.setAttribute("aria-pressed", String(b.dataset.color === resaltado));
    const posicion = Number.isFinite(Number(sub.posicion)) && sub.posicion !== null ? Number(sub.posicion) : 0.78;
    for (const b of this.botonesPosicion) b.setAttribute("aria-pressed", String(Math.abs(Number(b.dataset.posicion) - posicion) < 0.005));
    const alt = alturaDePosicion(sub.posicion);
    if (document.activeElement !== this.altura) this.altura.value = String(alt);
    this.alturaValor.textContent = textoPorcentaje(alt);
    const escala = Math.round((Number(sub.escala) || 1) * 100);
    if (document.activeElement !== this.tamano) this.tamano.value = String(escala);
    this.tamanoValor.textContent = textoPorcentaje(escala);
  }

  _pintarLineas(doc, r, mats) {
    let lineas = [];
    let soloLectura = false;
    if (r && this.estado.tipo === "derivados") {
      lineas = lineasListado(derivar(r, palabrasDe(mats)), mats);
    } else if (r && this.estado.tipo === "legado") {
      const { idioma, pais } = r.destino ?? {};
      lineas = lineasListado(valorDestino(doc?.subtitulos?.palabras ?? {}, idioma, pais) ?? [], {});
      soloLectura = true;
    }
    this.lineas = lineas;
    this.seccionLineas.hidden = !lineas.length;
    const firma = JSON.stringify([soloLectura, lineas]);
    // mientras se corrige una palabra no se rehace la lista (se perdería lo
    // escrito): se rehace al cerrarla
    if (firma !== this.firmaLineas && !this.editando) {
      this.firmaLineas = firma;
      this.listaLineas.replaceChildren(...lineas.map((l, i) => this._linea(l, i, soloLectura)));
      this.lineaActual = -2;            // que _marcarLinea vuelva a marcar
    }
    this._pintarEmoji();
    this._marcarLinea();
  }

  _linea(linea, i, soloLectura) {
    const li = el("li", "ed-sub-linea");
    li.dataset.linea = String(i);
    const cuando = textoTiempo(linea.t_ms);
    const tiempo = boton("ed-sub-tiempo", li, cuando);
    tiempo.dataset.ir = String(linea.t_ms);
    tiempo.title = t("sub.ir_a", { tiempo: cuando });
    tiempo.setAttribute("aria-label", tiempo.title);
    const caja = el("span", "ed-sub-palabras", li);
    for (const p of linea.palabras) {
      if (soloLectura || p.material_id === null) {
        el("span", "ed-sub-palabra ed-sub-palabra-fija", caja, p.texto);
        continue;
      }
      const b = boton(`ed-sub-palabra${p.corregida ? " ed-sub-corregida" : ""}`, caja, p.texto);
      b.dataset.material = String(p.material_id);
      b.dataset.indice = String(p.indice);
      if (p.corregida) b.title = t("sub.corregida", { original: p.original });
    }
    if (!soloLectura && linea.palabras.some((p) => p.material_id !== null)) {
      const q = boton("ed-sub-quitar-linea", li, "×");
      q.dataset.quitarLinea = String(i);
      q.title = t("sub.quitar_linea");
      q.setAttribute("aria-label", t("sub.quitar_linea"));
    }
    return li;
  }

  _pintarEmoji() {
    const escrito = this.editando?.input?.value ?? "";
    const hay = tieneEmoji(escrito) || this.lineas.some((l) => l.palabras.some((p) => tieneEmoji(p.texto)));
    this.emoji.hidden = !hay;
  }

  // La línea que suena (la del cabezal) lleva aria-current.
  _marcarLinea() {
    if (!this.listaLineas) return;
    const i = lineaEn(this.lineas, this.editor.tiempo?.() ?? 0);
    if (i === this.lineaActual) return;
    this.lineaActual = i;
    for (const li of this.listaLineas.children) {
      if (Number(li.dataset.linea) === i) li.setAttribute("aria-current", "true");
      else li.removeAttribute("aria-current");
    }
  }

  // La página abrió una pestaña (editor.mostrarBiblioteca): si es esta, se
  // ve la línea del cabezal (tocar un bloque de la fila «Subtítulos» la abre
  // en esa línea).
  _alMostrar() {
    requestAnimationFrame(() => {
      if (!this.raiz || this.raiz.closest("[hidden]")) return;
      this._marcarLinea();
      this.listaLineas.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest" });
    });
  }

  _decir(texto, error = false) {
    clearTimeout(this.relojMensaje);
    this.aviso.textContent = texto || "";
    this.aviso.hidden = !texto;
    this.aviso.classList.toggle("error", Boolean(texto) && error);
    if (texto) this.relojMensaje = setTimeout(() => this._decir(""), error ? 12000 : 6000);
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

  // ---- Lo que hace la persona ----

  _clic(e) {
    const b = e.target.closest?.("button");
    if (!b || !this.raiz.contains(b)) return;
    if (e.detail > 0 && !b.dataset.material) b.blur();   // con el mouse el foco no se queda (Espacio lo volvería a apretar)
    if (b === this.generarBoton) return void this.generar();
    if (b === this.quitarBoton) return this._quitarTodos();
    if (b.dataset.estilo) return this._operar(null, "cambiarSubtitulos", { estilo_id: b.dataset.estilo });
    if (b.dataset.color) return this._operar(null, "cambiarSubtitulos", { resaltado: b.dataset.color });
    if (b.dataset.posicion) return this._operar(null, "cambiarSubtitulos", { posicion: Number(b.dataset.posicion) });
    if (b.dataset.ir !== undefined) return this.editor.ir?.(Number(b.dataset.ir) || 0);
    if (b.dataset.quitarLinea !== undefined) return this._quitarLinea(Number(b.dataset.quitarLinea));
    if (b.dataset.restaurar !== undefined) return this._cerrarPalabra(true, null);
    if (b.dataset.material) return this._abrirPalabra(b);
  }

  _cambio(e) {
    const n = e.target;
    if (n === this.visibles) {
      this._operar(null, "cambiarSubtitulos", { visibles: n.checked });
    } else if (n.name === "ed-sub-fuente") {
      if (!n.checked) return;
      this.claveElegida = n.value;
      this._decir("");
      this.pintar();
    } else if (n === this.selIdioma) {
      this.idioma = n.value;
    } else if (n === this.altura || n === this.tamano) {
      this.pintar();                   // al soltar: el valor que de verdad quedó
    }
  }

  _entrada(e) {
    const n = e.target;
    if (n === this.altura) {
      this.alturaValor.textContent = textoPorcentaje(Number(n.value));
      this._operar("sub:posicion", "cambiarSubtitulos", { posicion: posicionDeAltura(Number(n.value)) });
    } else if (n === this.tamano) {
      this.tamanoValor.textContent = textoPorcentaje(Number(n.value));
      this._operar("sub:escala", "cambiarSubtitulos", { escala: Number(n.value) / 100 });
    } else if (n === this.editando?.input) {
      this._pintarEmoji();
    }
  }

  _tecla(e) {
    const n = e.target;
    if (n === this.editando?.input) {
      if (e.key === "Enter") {
        e.preventDefault();
        this._cerrarPalabra(true, undefined, true);
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();            // no baja la hoja del celular
        this._cerrarPalabra(false, undefined, true);
      }
      return;
    }
    // Supr o Borrar sobre una palabra la quitan (y no borran el clip elegido)
    if ((e.key === "Delete" || e.key === "Backspace") && n?.dataset?.material && n.classList.contains("ed-sub-palabra")) {
      e.preventDefault();
      e.stopPropagation();
      if (e.repeat) return;
      const k = [...this.listaLineas.querySelectorAll("button.ed-sub-palabra")].indexOf(n);
      if (this._operar(null, "corregirPalabra", Number(n.dataset.material), Number(n.dataset.indice), "")) {
        // el foco sigue en la lista (la palabra que quedó en ese lugar), no en la página
        const quedan = this.listaLineas.querySelectorAll("button.ed-sub-palabra");
        (quedan[k] ?? quedan[k - 1])?.focus({ preventScroll: true });
      }
    }
  }

  // Una operación de operaciones.js; si la página la rechaza, el porqué se
  // dice aquí (en el celular la hoja tapa el aviso de debajo del video) y los
  // controles vuelven a lo que de verdad quedó.
  _operar(clave, nombre, ...args) {
    const ed = this.editor;
    if (this._enConflicto()) {
      this._decir(mensajeConflicto(), true);
      this.pintar();
      return false;
    }
    const ok = clave ? ed.operarCon({ clave }, nombre, ...args) : ed.operar(nombre, ...args);
    if (!ok) {
      this._decir(this._enConflicto() ? mensajeConflicto() : t("prop.rechazo"), true);
      this.pintar();
    }
    return ok;
  }

  _quitarLinea(i) {
    const linea = this.lineas[i];
    if (!linea) return;
    const refs = linea.palabras.filter((p) => p.material_id !== null).map((p) => ({ material_id: p.material_id, indice: p.indice }));
    if (refs.length) this._operar(null, "quitarLinea", refs);
  }

  _quitarTodos() {
    if (this._enConflicto()) return this._decir(mensajeConflicto(), true);
    if (!window.confirm(t("sub.confirmar_quitar"))) return;
    this._operar(null, "ponerFuentesSubtitulos", idiomaDe(this.editor.destino?.()), []);
  }

  // ---- Corregir una palabra ----

  _palabra(materialId, indice) {
    for (const l of this.lineas) {
      for (const p of l.palabras) if (p.material_id === materialId && p.indice === indice) return p;
    }
    return null;
  }

  _abrirPalabra(tocada) {
    if (this._enConflicto()) return this._decir(mensajeConflicto(), true);
    const materialId = Number(tocada.dataset.material);
    const indice = Number(tocada.dataset.indice);
    this._cerrarPalabra(true);                    // la que estaba abierta (puede rehacer la lista)
    const b = this.listaLineas.querySelector(`button[data-material="${materialId}"][data-indice="${indice}"]`);
    const palabra = this._palabra(materialId, indice);
    if (!palabra || !b) return;
    const caja = el("span", "ed-sub-editor");
    const input = el("input", "ed-sub-palabra-campo", caja);
    Object.assign(input, { type: "text", value: palabra.texto, maxLength: MAX_CORRECCION, size: Math.max(4, palabra.texto.length + 1) });
    input.setAttribute("aria-labelledby", "ed-sub-lineas-titulo");
    input.setAttribute("aria-describedby", "ed-sub-lineas-ayuda");
    input.setAttribute("autocomplete", "off");
    input.spellcheck = true;
    if (palabra.corregida) {
      const volver = boton("btn-sm ed-sub-restaurar", caja, t("sub.restaurar"));
      volver.dataset.restaurar = "";
      volver.title = t("sub.corregida", { original: palabra.original });
      volver.addEventListener("pointerdown", (e) => e.preventDefault());   // el campo no pierde el foco antes del clic
    }
    b.replaceWith(caja);
    this.editando = { materialId, indice, input, caja, boton: b, texto: palabra.texto };
    input.addEventListener("blur", () => {
      if (this.editando?.input === input) this._cerrarPalabra(true);    // tocar fuera guarda lo escrito
    });
    input.focus();
    input.select();
    this._pintarEmoji();
  }

  // Cierra la palabra abierta: `guardar` aplica lo escrito (o `valor`: null =
  // volver a lo que se oyó; "" = quitarla). `teclado`: el foco vuelve a la
  // palabra (Enter o Esc), no se pierde en la página.
  _cerrarPalabra(guardar, valor = undefined, teclado = false) {
    const ed = this.editando;
    if (!ed) return;
    this.editando = null;
    const escrito = valor === undefined ? ed.input.value : valor;
    const cambia = guardar && (escrito === null || String(escrito).trim().split(/\s+/).join(" ") !== ed.texto);
    if (cambia) this._operar(null, "corregirPalabra", ed.materialId, ed.indice, escrito);
    if (ed.caja.isConnected) ed.caja.replaceWith(ed.boton);        // no cambió nada: vuelve la palabra
    this.pintar();
    if (teclado) {
      const sel = `[data-material="${ed.materialId}"][data-indice="${ed.indice}"]`;
      (this.listaLineas.querySelector(sel) ?? this.listaLineas.querySelector(".ed-sub-palabra"))?.focus({ preventScroll: true });
    }
  }

  // ---- Generar (D6: ningún pago sin un clic en un botón con el precio) ----

  // Pide el precio de lo que falta transcribir de la fuente elegida, 300 ms
  // después del último cambio; sin nada que transcribir, «(gratis)» sin
  // llamar a nadie. Una respuesta vieja (la fuente cambió) se descarta.
  _pedirEstimado(forzar = false) {
    const p = this.pedidoActual;
    const firma = JSON.stringify([this.clave, p.faltan]);
    if (!forzar && this.estimado?.firma === firma) return;
    clearTimeout(this.relojEstimar);
    const turno = ++this.turnoEstimar;
    const reintentos = forzar && this.estimado?.firma === firma ? (this.estimado.reintentos ?? 0) : 0;
    if (!this.clave || !p.todos.length) {
      this.estimado = null;
      return;
    }
    if (!p.faltan.length) {
      this.estimado = { firma, gratis: true };
      return;
    }
    this.estimado = { firma, calculando: true, reintentos };
    this.relojEstimar = setTimeout(() => void this._estimar(firma, [...p.faltan], turno, reintentos), ESPERA_ESTIMAR_MS);
  }

  async _estimar(firma, ids, turno, reintentos) {
    let res;
    try {
      const { r, j } = await this._pedirJSON(this.urls.subtitulos_estimar, { material_ids: ids });
      if (r.ok && j && typeof j === "object" && j.gratis) res = { firma, gratis: true };
      else if (r.ok && j && typeof j === "object" && j.usd !== null && j.usd !== undefined && j.precio) {
        res = { firma, precio: String(j.precio) };
      } else res = { firma, error: true, reintentos };
    } catch {
      res = { firma, error: true, reintentos };
    }
    if (turno !== this.turnoEstimar) return;
    this.estimado = res;
    this._pintarGenerar();
    if (res.error && reintentos < REINTENTOS_ESTIMAR) {
      this.estimado.reintentos = reintentos + 1;
      this.relojEstimar = setTimeout(() => {
        if (this.estimado?.firma === firma && this.estimado.error) {
          this._pedirEstimado(true);
          this._pintarGenerar();
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

  async generar() {
    if (this.trabajo || this.enviando) return;
    if (this._enConflicto()) return this._decir(mensajeConflicto(), true);
    const ed = this.editor;
    const r = ed.resuelto?.();
    const clave = this.clave;
    if (!r || !clave) return;
    const p = pedido(r, clave, ed.materiales?.() ?? {});
    if (!p.todos.length) return;
    const encargo = { idioma: idiomaDe(ed.destino?.()), clave, ids: p.todos.filter((id) => !p.mudos.includes(id)) };
    this._decir("");
    if (!p.faltan.length || this.estimado?.gratis) {         // ya transcrito: gratis, sin llamar a nadie
      await this._aplicar(encargo);
      return;
    }
    this.enviando = true;
    this._pintarGenerar();
    let res;
    try {
      res = await this._pedirJSON(this.urls.transcribir, { material_ids: encargo.ids, idioma: this.idioma ?? encargo.idioma });
    } catch (e) {
      this.enviando = false;
      this._pintarGenerar();
      this._decir(t("sub.sin_conexion"), true);
      this._detalle(String(e?.message ?? e ?? ""));
      return;
    }
    this.enviando = false;
    const { r: resp, j, sesion } = res;
    if (sesion) {
      this._pintarGenerar();
      return this._decir(mensajeSesion(), true);
    }
    if (resp.status === 202 && j?.job_id) return this.seguir(j.job_id, encargo);
    if (resp.ok && j?.listo) {
      this._pintarGenerar();
      await this._aplicar(encargo);
      return;
    }
    this._pintarGenerar();
    this._decir(typeof j?.error === "string" && j.error ? j.error : t("sub.error", { mensaje: `HTTP ${resp.status}` }), true);
    this._detalle(`HTTP ${resp.status}`);
  }

  // Sigue un trabajo de transcripción (el que se acaba de encolar o el que ya
  // corría al abrir la página) preguntando cada 1,5 s; `encargo` dice qué
  // poner al terminar (null si no se sabe: se traen las palabras y la persona
  // elige, ya gratis).
  seguir(jobId, encargo = null) {
    if (!jobId) return;
    clearTimeout(this.relojTrabajo);
    this.trabajo = { job: jobId, encargo, etapa: "", progreso: 0, fallos: 0 };
    if (encargo) this._guardarEncargo(jobId, encargo);
    this._pintarGenerar();
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
      this.relojTrabajo = setTimeout(() => void this._sondear(), INTERVALO_TRABAJO_MS * (tr.fallos > 3 ? 4 : 1));
      return;
    }
    tr.fallos = 0;
    if (j.estado === "en_progreso") {
      tr.etapa = typeof j.etapa === "string" ? j.etapa : "";
      tr.progreso = Number(j.progreso) || 0;
      this._pintarGenerar();
      this.relojTrabajo = setTimeout(() => void this._sondear(), INTERVALO_TRABAJO_MS);
      return;
    }
    // terminó: bien, con error (lo que sí se transcribió igual se usa) o ya no se sabe de él
    this.trabajo = null;
    this._olvidarEncargo();
    this._pintarGenerar();
    const error = j.estado === "error" ? String(j.mensaje || "error") : null;
    if (error) this._detalle(String(j.mensaje || ""));
    if (tr.encargo) {
      await this._aplicar(tr.encargo, { error });
      return;
    }
    // un trabajo de antes de recargar: se traen las palabras; poner la fuente es gratis desde aquí
    await this._cargarPalabras(this._idsDeLaEdicion());
    this._decir(error ? t("sub.error", { mensaje: error }) : t("sub.listos"), Boolean(error));
  }

  // Trae (gratis) las palabras que todavía no están en la página y pone la
  // fuente en el idioma del encargo, como una operación sobre el documento de
  // AHORA. Si ninguno de sus archivos trae palabras (música sin letra,
  // silencio), lo dice y no cambia nada.
  async _aplicar(encargo, { error = null } = {}) {
    const mats0 = this.editor.materiales?.() ?? {};
    const traer = encargo.ids.filter((id) => !Array.isArray(mats0[id]?.palabras));
    if (traer.length && !(await this._cargarPalabras(traer))) return;
    if (this._enConflicto()) return this._decir(mensajeConflicto(), true);
    const mats = this.editor.materiales?.() ?? {};
    const palabras = encargo.ids.reduce((n, id) => n + (Array.isArray(mats[id]?.palabras) ? mats[id].palabras.length : 0), 0);
    if (!palabras) {
      this._decir(error ? t("sub.error", { mensaje: error }) : t("sub.ninguna_palabra"), Boolean(error));
      return;
    }
    const fuente = fuenteDeClave(encargo.clave);
    if (!fuente || !this._operar(null, "ponerFuentesSubtitulos", encargo.idioma, [fuente])) return;
    this.claveElegida = null;
    this._decir(error ? t("sub.error", { mensaje: error }) : t("sub.listos"), Boolean(error));
  }

  async _cargarPalabras(ids) {
    const lista = [...new Set((ids ?? []).map(Number).filter((id) => Number.isInteger(id) && id > 0))];
    if (!lista.length) return true;
    try {
      const url = `${this.urls.materiales_por_id}?ids=${lista.join(",")}&palabras=1`;
      const { r, j, sesion } = await this._pedirJSON(url);
      if (sesion) {
        this._decir(mensajeSesion(), true);
        return false;
      }
      if (!r.ok || !j || typeof j.materiales !== "object") {
        this._decir(t("sub.error", { mensaje: `HTTP ${r.status}` }), true);
        this._detalle(`HTTP ${r.status}`);
        return false;
      }
      this.editor.agregarMateriales(j.materiales);
      return true;
    } catch (e) {
      this._decir(t("sub.sin_conexion"), true);
      this._detalle(String(e?.message ?? e ?? ""));
      return false;
    }
  }

  // Los videos y audios de la edición (lo que pudo transcribir un trabajo del
  // que no se sabe qué pidió).
  _idsDeLaEdicion() {
    const mats = this.editor.materiales?.() ?? {};
    return (this.editor.doc()?.materiales ?? []).map(Number).filter((id) => ["video", "audio"].includes(mats[id]?.tipo));
  }

  // Qué pidió un trabajo, para ponerlo aunque la página se recargue mientras
  // corre (solo en esta pestaña; sin almacenamiento, se pierde y la persona
  // lo pone con un clic, ya gratis).
  _claveAlmacen() {
    return `ed-sub-trabajo:${this.datos.edicion?.id ?? ""}`;
  }

  _guardarEncargo(job, encargo) {
    try {
      sessionStorage.setItem(this._claveAlmacen(), JSON.stringify({ job, ...encargo }));
    } catch { /* sin almacenamiento: no pasa nada */ }
  }

  _pedidoGuardado(job) {
    try {
      const v = JSON.parse(sessionStorage.getItem(this._claveAlmacen()) ?? "null");
      if (!v || v.job !== job || !/^[a-z]{2}$/.test(String(v.idioma)) || !fuenteDeClave(v.clave) || !Array.isArray(v.ids)) return null;
      return { idioma: v.idioma, clave: v.clave, ids: v.ids.map(Number).filter((id) => Number.isInteger(id) && id > 0) };
    } catch {
      return null;
    }
  }

  _olvidarEncargo() {
    try {
      sessionStorage.removeItem(this._claveAlmacen());
    } catch { /* nada */ }
  }
}

// Página del editor (capas 4a y 4b): une la vista previa, la línea de tiempo,
// las operaciones con deshacer/rehacer, el autoguardado y «Producir». Cada
// operación sale de operaciones.js (pura); si es inválida se muestra su
// mensaje y nada cambia. Si otra pestaña guardó antes («conflicto»), el
// guardado se detiene y la página ya no deja editar: lo que se hiciera aquí
// no se podría guardar; se ofrece recargar.
//
// Capa 4b: la disposición tipo CapCut (editor.html) — biblioteca |
// reproductor | propiedades, y abajo las herramientas y la línea de tiempo; en
// el celular la biblioteca y las propiedades son hojas que suben desde abajo
// (`#ed-abrir-*`, «Listo»). Los módulos que llenan esos paneles (biblioteca,
// propiedades, tocar sobre el video) se enganchan SOLO por `editor`, el objeto
// de abajo: así ninguno toca al otro ni a la historia, el guardado o la vista.
// (Tocar sobre el video además LEE la vista: el documento que se dibuja, las
// medidas de los textos y el tiempo; la pausa al arrastrar es lo único que le
// pide.)
//
//   editor.operar(nombre, ...args)          una operación de operaciones.js; la
//                                           página agrega `info()` al final.
//                                           Devuelve true si se aplicó (aunque
//                                           no cambiara nada), false si no.
//   editor.operarCon({clave}, nombre, ...)  igual, fusionando en UN deshacer los
//                                           pasos seguidos con la misma clave
//                                           (un deslizador: "<clipId>:<campo>");
//                                           `null` o `{}` = sin clave
//   editor.seleccionar(id | null)           elige un clip (y lo marca en la línea)
//   editor.seleccion                        el id elegido, o null
//   editor.doc()                            el documento actual (no se toca: las
//                                           operaciones devuelven uno nuevo)
//   editor.tiempo()                         el cabezal, en ms
//   editor.destino()                        "<idioma>_<PAIS>" que se está viendo
//   editor.info()                           {id: {duracion_ms, tiene_audio}}
//   editor.enConflicto()                    true si otra pestaña guardó antes: la
//                                           página ya no deja editar y los paneles
//                                           piden recargar
//   editor.agregarMateriales(mapa)          suma materiales (forma de
//                                           material_para) a la vista previa
//                                           ANTES de operar con ellos
//   editor.enfocarTexto()                   pide el foco para escribir el texto
//                                           elegido (la biblioteca, al agregar
//                                           un texto): en el celular sube la
//                                           hoja «Editar» y avisa "foco-texto"
//                                           — quien muestra ese campo
//                                           (propiedades.js) lo enfoca
//   editor.escuchar(fn) -> dejar()          fn(que) después de cada cambio:
//                                           "documento" | "seleccion" |
//                                           "materiales" | "destino" | "tiempo"
//                                           | "foco-texto"
//
// Reglas de los avisos (avisos_editor.js, probadas en Node):
// - «seleccion» sale solo si la selección cambió de verdad, también cuando la
//   cambió una operación (duplicar elige la copia: "documento" y después
//   "seleccion"); una operación inválida, rechazada o sin cambio no avisa.
// - Un oyente puede operar o elegir algo al enterarse: lo que eso avisa espera
//   a que la vuelta en curso termine, en orden y una vez cada aviso; quien lo
//   recibe ya ve el estado último. Si un oyente provoca un aviso cada vez que
//   se entera, se corta (y se anota en la consola) en vez de colgar la página.
import { Avisos } from "./avisos_editor.js";
import { Biblioteca } from "./biblioteca.js";
import { pedidoCortar } from "./escala.js";
import { Guardado } from "./guardado.js";
import { Historial } from "./historial.js";
import { InteraccionLienzo } from "./lienzo_interaccion.js";
import { LineaTiempo } from "./linea_tiempo.js";
import * as operaciones from "./operaciones.js";
import { Propiedades } from "./propiedades.js";
import { listaY, ponerTextos, t } from "./textos.js";
import { infoDe, VistaPrevia } from "./vista.js";

const datos = JSON.parse(document.getElementById("datos-editor").textContent);
// Los textos en el idioma de quien mira (ruta editor.ver), antes de construir
// nada: ningún módulo llama a t() al cargarse.
ponerTextos(datos.textos, datos.idioma_ui);
const $ = (id) => document.getElementById(id);
const historial = new Historial(datos.documento);
let seleccion = null;
const avisos = new Avisos();

const vista = new VistaPrevia({
  datos,
  alCambiarTiempo: (ms, reproduciendo) => {
    linea.moverCabezal(ms, { seguir: reproduciendo });
    avisos.notificar("tiempo");
  },
  alCambiarMateriales: () => refrescar("materiales"),
});
const linea = new LineaTiempo({
  contenedor: $("linea"),
  zoom: $("linea-zoom"),
  materiales: () => vista.materiales,
  destino: () => vista.destino,
  ventanaPicosMs: datos.config?.ventana_picos_ms,
  alSeleccionar: (id) => seleccionar(id),
  alOperar: operar,
  alIr: (ms) => {
    vista.ir(ms);
    linea.moverCabezal(vista.tiempo());
  },
});
const guardado = new Guardado({ url: datos.urls.guardar, versionN: datos.edicion.version_n, alCambiar: pintarGuardado });

const TEXTO_GUARDADO = {
  guardado: () => t("guardado.ok"),
  pendiente: () => t("guardado.pendiente"),
  guardando: () => t("guardado.guardando"),
  error: (m) => t("guardado.error", { mensaje: m }),
  conflicto: (m) => m,
};

// El último argumento de cada operación: {id: {duracion_ms, tiene_audio}}.
function info() {
  return infoDe(vista.materiales);
}

function aviso(texto) {
  const n = $("aviso-edicion");
  n.textContent = texto || "";
  n.hidden = !texto;
}

function pintarGuardado(estado, mensaje) {
  const n = $("estado-guardado");
  n.dataset.estado = estado;
  n.textContent = TEXTO_GUARDADO[estado]?.(mensaje) ?? "";
  n.title = n.textContent;          // en el celular el hueco es fijo: un error largo termina en «…»
  $("recargar").hidden = estado !== "conflicto";
  pintarHerramientas();
}

function buscarClip(id) {
  for (const pista of historial.actual.pistas) for (const clip of pista.clips) if (clip.id === id) return { pista, clip };
  return null;
}

function pintarHerramientas() {
  const bloqueada = guardado.estado === "conflicto";
  const sel = seleccion ? buscarClip(seleccion) : null;
  const editableSel = Boolean(sel) && sel.pista.id !== operaciones.ID_SONIDO && !bloqueada;
  $("h-deshacer").disabled = bloqueada || !historial.puedeDeshacer;
  $("h-rehacer").disabled = bloqueada || !historial.puedeRehacer;
  $("h-cortar").disabled = bloqueada;
  $("h-borrar").disabled = !editableSel;
  $("h-duplicar").disabled = !editableSel;
}

// `que`: "documento" (el documento cambió: la vista lo re-resuelve),
// "materiales", "destino", o null (solo se redibuja; si la selección cambió,
// eso se avisa igual).
function refrescar(que = "documento") {
  if (que === "documento") vista.setDocumento(historial.actual);
  if (seleccion && !buscarClip(seleccion)) seleccion = null;
  linea.dibujar(historial.actual, { seleccion, cabezalMs: vista.tiempo() });
  pintarHerramientas();
  avisos.cambio(que, seleccion);
}

function seleccionar(id) {
  seleccion = id ?? null;
  refrescar(null);
}

// En conflicto no se edita: nada de lo que se haga se podría guardar.
function editable() {
  if (guardado.estado !== "conflicto") return true;
  aviso(t("editar.conflicto"));
  return false;
}

function operar(nombre, ...args) {
  return operarCon({}, nombre, ...args);
}

// `clave`: pasos seguidos con la misma clave quedan en UN deshacer
// (Historial.aplicar); sin clave (o con `opciones` null) cada operación es su
// propio paso.
function operarCon(opciones, nombre, ...args) {
  const clave = opciones?.clave ?? null;
  if (!editable()) {
    refrescar(null);
    return false;
  }
  let res;
  try {
    res = operaciones[nombre](historial.actual, ...args, info());
  } catch (e) {
    const invalida = e.name === "OperacionInvalida";
    if (!invalida) console.error(e);
    aviso(invalida ? e.message : t("editar.fallo", { error: e.message }));
    refrescar(null);
    return false;
  }
  aviso("");
  seleccion = res.seleccion;
  if (JSON.stringify(res.doc) === JSON.stringify(historial.actual)) {   // nada cambió: ni historial ni guardado
    refrescar(null);
    return true;
  }
  historial.aplicar(res.doc, { clave });
  refrescar();
  guardado.pedir(res.doc);
  return true;
}

// «Cortar» y la tecla S: el clip elegido en el cabezal (cualquier pista), o
// sin nada elegido el video bajo el cabezal (escala.pedidoCortar). Con un clip
// elegido y el cabezal fuera de él no se corta otra cosa: se dice.
function cortar() {
  const pedido = pedidoCortar(historial.actual, seleccion, vista.tiempo());
  if (pedido) operar(...pedido);
  else if (editable()) aviso(t("editar.cabezal_elegido"));
}

function deshacer() {
  if (!editable()) return;
  const doc = historial.deshacer();
  if (!doc) return;
  aviso("");
  refrescar();
  guardado.pedir(doc);
}

function rehacer() {
  if (!editable()) return;
  const doc = historial.rehacer();
  if (!doc) return;
  aviso("");
  refrescar();
  guardado.pedir(doc);
}

// Un clic con el mouse no deja el foco en el botón: si no, Espacio
// (reproducir) lo volvería a apretar — otro corte. Con el teclado (detail 0)
// el foco se queda donde está.
function herramienta(id, fn) {
  $(id).addEventListener("click", (e) => {
    if (e.detail > 0) e.currentTarget.blur();
    fn();
  });
}

function montarHerramientas() {
  herramienta("h-cortar", cortar);
  herramienta("h-borrar", () => seleccion && operar("borrar", seleccion));
  herramienta("h-duplicar", () => seleccion && operar("duplicar", seleccion));
  herramienta("h-deshacer", deshacer);
  herramienta("h-rehacer", rehacer);
  // La velocidad está en el formulario del video, en «Editar» (propiedades.js).
  $("recargar").addEventListener("click", () => location.reload());
  // Espacio y flechas son de la vista previa (vista.js); estas, de la edición.
  document.addEventListener("keydown", (e) => {
    if ($("producir-dialogo").open) return;
    if (e.key === "Escape" && hojaAbierta) {        // celular: Esc baja la hoja abierta
      e.preventDefault();
      cerrarHoja();
      return;
    }
    if (e.target.closest?.("input, select, textarea")) return;
    const tecla = (e.key || "").toLowerCase();
    const mod = e.metaKey || e.ctrlKey;
    if (mod && tecla === "z") {
      e.preventDefault();
      if (e.shiftKey) rehacer();
      else deshacer();
    } else if (mod && tecla === "y") {
      e.preventDefault();
      rehacer();
    } else if (mod || e.altKey) {
      // otros atajos del navegador (Cmd+S, Ctrl+R…) siguen siendo suyos
    } else if (tecla === "s") {
      e.preventDefault();
      if (!e.repeat) cortar();
    } else if ((e.key === "Delete" || e.key === "Backspace") && seleccion) {
      e.preventDefault();
      if (!e.repeat) operar("borrar", seleccion);
    } else if (e.key === "+" || e.key === "=") {
      linea.pps *= 1.25;
    } else if (e.key === "-") {
      linea.pps /= 1.25;
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (!guardado.sinGuardar) return;
    e.preventDefault();
    e.returnValue = "";
  });
}

function montarProducir() {
  const boton = $("producir");
  const dialogo = $("producir-dialogo");
  if (!datos.cf_id) {
    boton.disabled = true;
    boton.title = t("producir.sin_clon");
    return;
  }
  const minutos = Math.max(1, Math.round((Number(datos.estimado_s) || 60) / 60));
  $("producir-tiempo").textContent = minutos === 1 ? t("producir.un_minuto") : t("producir.minutos", { n: minutos });
  const nombre = (d) => d.replace("_", " · ");
  const lista = $("producir-destinos");
  for (const d of datos.destinos) {
    const l = document.createElement("label");
    const c = document.createElement("input");
    c.type = "checkbox";
    c.value = d;
    c.checked = true;
    l.append(c, ` ${nombre(d)}`);
    lista.append(l);
  }
  const avisar = (texto) => {
    $("producir-aviso").textContent = texto || "";
    $("producir-aviso").hidden = !texto;
  };
  // Ya hay una final de ese destino que no salió de esta edición (la vía
  // automática, con voz, u otra edición): producir la reemplaza, así que se
  // pregunta antes. La confirmación vale para esa selección: cambiarla la quita.
  const pedirReemplazo = (destinos) => {
    const cuales = listaY(destinos.map(nombre));
    $("producir-reemplazo-texto").textContent = t(destinos.length === 1 ? "producir.reemplazo_una" : "producir.reemplazo_varias",
      { destinos: cuales });
    $("producir-reemplazo").hidden = false;
    $("producir-reemplazar").hidden = false;
    $("producir-confirmar").hidden = true;
  };
  const sinReemplazo = () => {
    $("producir-reemplazo").hidden = true;
    $("producir-reemplazar").hidden = true;
    $("producir-confirmar").hidden = false;
  };
  lista.addEventListener("change", () => {
    avisar("");
    sinReemplazo();
  });
  boton.addEventListener("click", () => {
    avisar("");
    sinReemplazo();
    dialogo.showModal();
  });
  $("producir-cancelar").addEventListener("click", () => dialogo.close());
  $("producir-confirmar").addEventListener("click", () => producir(false));
  $("producir-reemplazar").addEventListener("click", () => producir(true));

  async function producir(reemplazar) {
    const destinos = [...lista.querySelectorAll("input:checked")].map((c) => c.value);
    if (!destinos.length) return avisar(t("producir.marca_destino"));
    $("producir-confirmar").disabled = true;
    $("producir-reemplazar").disabled = true;
    avisar("");
    try {
      await guardado.ahora();        // se produce lo que se ve: primero se guarda lo pendiente
      if (guardado.estado === "conflicto" || guardado.estado === "error") {
        return avisar(t("producir.guardar_antes", { mensaje: guardado.mensaje }));
      }
      const r = await fetch(datos.urls.producir, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ version_n: guardado.versionN, destinos, ...(reemplazar ? { reemplazar: true } : {}) }),
      });
      const j = await r.json().catch(() => ({}));
      if (r.status === 409 && Array.isArray(j.reemplazos) && j.reemplazos.length) return pedirReemplazo(j.reemplazos);
      if (!r.ok) return avisar([j.error || t("producir.error", { status: r.status }), ...(j.problemas ?? [])].join(" "));
      const n = (j.producidas ?? []).filter((p) => p.encolada).length;
      dialogo.close();
      aviso("");
      $("producir-hecho-texto").textContent = n
        ? t(n === 1 ? "producir.hecha_una" : "producir.hechas", { n })
        : t("producir.ya_estaban");
      if (j.url) $("producir-hecho-enlace").href = j.url;
      $("producir-hecho").hidden = false;
    } catch {
      avisar(t("producir.sin_conexion"));
    } finally {
      $("producir-confirmar").disabled = false;
      $("producir-reemplazar").disabled = false;
    }
  }
}

// ---- Disposición (capa 4b) ----
// Las pestañas de la biblioteca (Medios · Audio · Texto · Transiciones) solo
// marcan cuál está elegida; qué muestra cada una es de la biblioteca. En el
// celular, los botones de abajo abren la hoja (y, los de la biblioteca, tocan
// su pestaña: quien atienda las pestañas se entera igual que con un clic).
let hojaAbierta = null;      // "ed-biblioteca" | "ed-propiedades" | null
let abridor = null;          // el botón que la abrió: el foco vuelve ahí

function pestanas() {
  return [...$("ed-pestanas-biblioteca").querySelectorAll("[data-panel]")];
}

function marcarPestana(boton) {
  for (const b of pestanas()) {
    const elegida = b === boton;
    b.setAttribute("aria-selected", String(elegida));
    b.tabIndex = elegida ? 0 : -1;
  }
  $("ed-biblioteca").dataset.panelActivo = boton.dataset.panel;
  pintarAcciones();
}

function pintarAcciones() {
  const panel = $("ed-biblioteca").dataset.panelActivo;
  for (const b of document.querySelectorAll("[data-abrir-hoja]")) {
    const abierta = hojaAbierta === b.dataset.abrirHoja;
    b.setAttribute("aria-expanded", String(abierta));
    b.classList.toggle("ed-activa", abierta && (!b.dataset.abrirPanel || b.dataset.abrirPanel === panel));
  }
}

function abrirHoja(id, desde) {
  hojaAbierta = id;
  abridor = desde;
  for (const h of ["ed-biblioteca", "ed-propiedades"]) $(h).classList.toggle("ed-hoja-abierta", h === id);
  pintarAcciones();
  $(id).focus({ preventScroll: true });
}

function cerrarHoja() {
  const volver = abridor;
  hojaAbierta = null;
  abridor = null;
  for (const h of ["ed-biblioteca", "ed-propiedades"]) $(h).classList.remove("ed-hoja-abierta");
  pintarAcciones();
  volver?.focus({ preventScroll: true });
}

function montarDisposicion() {
  const lista = $("ed-pestanas-biblioteca");
  lista.addEventListener("click", (e) => {
    const b = e.target.closest("[data-panel]");
    if (b) marcarPestana(b);
  });
  // flechas entre pestañas (el patrón de pestañas: una sola entra con Tab)
  lista.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const todas = pestanas();
    const i = todas.indexOf(e.target.closest("[data-panel]"));
    if (i < 0) return;
    e.preventDefault();
    const otra = todas[(i + (e.key === "ArrowRight" ? 1 : -1) + todas.length) % todas.length];
    otra.focus();
    otra.click();
  });
  for (const b of document.querySelectorAll("[data-abrir-hoja]")) {
    b.addEventListener("click", () => {
      const panel = b.dataset.abrirPanel;
      const yaAbierta = hojaAbierta === b.dataset.abrirHoja
        && (!panel || $("ed-biblioteca").dataset.panelActivo === panel);
      if (yaAbierta) return cerrarHoja();        // tocar otra vez el mismo botón la baja
      if (panel) lista.querySelector(`[data-panel="${panel}"]`)?.click();
      abrirHoja(b.dataset.abrirHoja, b);
    });
  }
  for (const b of document.querySelectorAll("[data-cerrar-hoja]")) b.addEventListener("click", cerrarHoja);
}

// Agregar un texto (o, en el video, tocarlo dos veces) lo deja elegido; el
// campo para escribirlo está en «Editar»: en el celular esa es una hoja, así
// que se sube antes de avisar (el foco va a la hoja y después al campo, que
// pone propiedades.js). En el escritorio la columna ya se ve.
const CELULAR = "(max-width: 760px)";

function enfocarTexto() {
  const celular = window.matchMedia?.(CELULAR).matches;
  if (hojaAbierta === "ed-biblioteca" || (celular && hojaAbierta !== "ed-propiedades")) {
    abrirHoja("ed-propiedades", $("ed-abrir-propiedades"));
  }
  avisos.notificar("foco-texto");
}

// La única puerta para los módulos de la capa 4b (ver el comentario de arriba):
// las tareas 5–8 se lo pasan a sus módulos al crearlos, aquí abajo.
const editor = Object.freeze({
  operar,
  operarCon,
  seleccionar,
  get seleccion() {
    return seleccion;
  },
  doc: () => historial.actual,
  tiempo: () => vista.tiempo(),
  destino: () => vista.destino,
  info,
  enConflicto: () => guardado.estado === "conflicto",
  agregarMateriales: (mapa) => vista.agregarMateriales(mapa),
  enfocarTexto,
  escuchar: (fn) => avisos.escuchar(fn),
});

montarHerramientas();
montarProducir();
montarDisposicion();
// la biblioteca (Medios · Audio · Texto · Transiciones): carga lo del proyecto
// mientras la vista previa arranca
new Biblioteca({ contenedor: $("ed-panel-biblioteca"), pestanas: $("ed-pestanas-biblioteca"), urls: datos.urls, editor, linea });
// las propiedades de lo elegido («Editar»: un formulario por clase de clip, o
// la mezcla de la edición si no hay nada elegido)
new Propiedades({ contenedor: $("ed-panel-propiedades"), editor, materiales: () => vista.materiales });
// tocar, mover y agrandar los textos y las imágenes sobre el video (necesita
// la vista previa: el documento que se dibuja y las medidas de los textos)
new InteraccionLienzo({ escenario: $("ed-escenario"), lienzo: $("lienzo"), editor, vista });
refrescar(null);           // la línea se ve ya, aunque las fuentes tarden en cargar
await vista.iniciar();
refrescar(null);           // con el reloj listo: el cabezal donde está
// otro destino: los textos variables de la línea cambian (vista.js ya escucha
// este select desde iniciar(), así que cuando esto corre el destino ya cambió)
$("destino").addEventListener("change", () => refrescar("destino"));

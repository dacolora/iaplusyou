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
//   editor.ir(tMs)                          lleva el cabezal a tMs (pausa si
//                                           reproducía)
//   editor.resuelto()                       el documento del destino que se ve,
//                                           resuelto y con los subtítulos ya
//                                           derivados (null antes de arrancar)
//   editor.materiales()                     {id: material} de la vista previa
//                                           (con `palabras` si se transcribió)
//   editor.mostrarBiblioteca(panel)         abre esa pestaña de la biblioteca
//                                           (en el celular sube su hoja); como
//                                           todo cambio de pestaña, avisa
//                                           "biblioteca"
//   editor.enfocarTexto()                   pide el foco para escribir el texto
//                                           elegido (la biblioteca, al agregar
//                                           un texto): en el celular sube la
//                                           hoja «Editar» y avisa "foco-texto"
//                                           — quien muestra ese campo
//                                           (propiedades.js) lo enfoca
//   editor.escuchar(fn) -> dejar()          fn(que) después de cada cambio:
//                                           "documento" | "seleccion" |
//                                           "materiales" | "destino" | "tiempo"
//                                           | "foco-texto" | "biblioteca" (la
//                                           biblioteca cambió de pestaña: quien
//                                           no pinta oculto se pone al día)
//
// Capa 5b (D10): «todo sigue a su clip». Cada operación pasa por
// vinculos.operar dentro de operarCon: con «Vincular» prendido (el botón
// #h-vincular de las herramientas, prendido por defecto y recordado por quien
// mira en localStorage), los textos, imágenes y voces que estaban encima de un
// clip del video lo siguen cuando ese clip se recorta, se corta, se borra, se
// mueve o cambia de velocidad. Lo movido y la operación son UN paso de
// deshacer y UN guardado (es el mismo documento). Apagado, todo es como antes.
// Si después dos voces suenan a la vez, se avisa bajo el video (#aviso-voces).
//
// Reglas de los avisos (avisos_editor.js, probadas en Node):
// - «seleccion» sale solo si la selección cambió de verdad, también cuando la
//   cambió una operación (duplicar elige la copia: "documento" y después
//   "seleccion"); una operación inválida, rechazada o sin cambio no avisa.
// - Un oyente puede operar o elegir algo al enterarse: lo que eso avisa espera
//   a que la vuelta en curso termine, en orden y una vez cada aviso; quien lo
//   recibe ya ve el estado último. Si un oyente provoca un aviso cada vez que
//   se entera, se corta (y se anota en la consola) en vez de colgar la página.
import { arreglarAlAbrir, avisosCarga } from "./avisos_carga.js";
import { Avisos } from "./avisos_editor.js";
import { Biblioteca } from "./biblioteca.js";
import { pedidoCortar } from "./escala.js";
import { Guardado, sesionTerminada } from "./guardado.js";
import { Historial } from "./historial.js";
import { InteraccionLienzo } from "./lienzo_interaccion.js";
import { LineaTiempo } from "./linea_tiempo.js";
import * as operaciones from "./operaciones.js";
import { respuestaProducir } from "./producir.js";
import { Propiedades } from "./propiedades.js";
import { PalabrasPendientes } from "./subtitulos_modelo.js";
import { SubtitulosPanel } from "./subtitulos_panel.js";
import { listaY, ponerTextos, t } from "./textos.js";
import { infoDe, VistaPrevia } from "./vista.js";
import * as vinculos from "./vinculos.js";
import { VozPanel } from "./voz_panel.js";

// Los textos en el idioma de quien mira (ruta editor.ver), antes de construir
// nada: ningún módulo llama a t() al cargarse. Se ponen al leer `datos`, dentro
// de su declaración: nada de nivel superior se ejecuta suelto antes de
// declararlo todo (capa 4c, lo vigila tests/test_editor_js.py).
function leerDatos() {
  const d = JSON.parse(document.getElementById("datos-editor").textContent);
  ponerTextos(d.textos, d.idioma_ui);
  return d;
}

const datos = leerDatos();
const $ = (id) => document.getElementById(id);
// Capa 4c: un clip que pide más material del que hay (el render fallaría) se
// acorta al abrir con el mismo `normalizar` que usa cada operación (y un
// «deslizar» de la capa 4b recibe su duración) — la vista previa muestra lo
// que se va a producir. Se guarda solo, AL FINAL del arranque (abajo del
// todo: `guardado.pedir` pinta el estado con TEXTO_GUARDADO, que tiene que
// existir ya), y solo si el documento cambió de verdad. «Se acortó solo» se
// dice una vez, hasta el próximo cambio.
const alAbrir = arreglarAlAbrir(datos.documento, infoDe(datos.materiales));
datos.documento = alAbrir.doc;
let acortadoAlAbrir = alAbrir.acortado;
const historial = new Historial(datos.documento);
let seleccion = null;
// «Vincular» (D10.9): lo que eligió quien mira; sin nada guardado (o si el
// navegador no deja leerlo), prendido.
let vincular = vinculos.leerVincular(almacenSeguro());
// El gesto con clave en curso (vinculos.operarGesto): su base y la cadena
// sin seguir. Se olvida al deshacer/rehacer, al guardar, en conflicto (y al
// recargar, claro); cambiar de clave empieza otro.
let gesto = null;
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
  alIr: (ms) => ir(ms),
  // capa 5a: la fila de solo lectura «Subtítulos» (las palabras del destino
  // que se ve, ya derivadas); tocar un bloque abre la pestaña en esa línea
  subtitulos: () => vista.resuelto?.subtitulos ?? null,
  estilosSubtitulos: datos.config?.subtitulos?.estilos ?? null,
  alSubtitulo: (ms) => {
    ir(ms);
    mostrarBiblioteca("subtitulos");
  },
});
const guardado = new Guardado({ url: datos.urls.guardar, versionN: datos.edicion.version_n, alCambiar: pintarGuardado });
// Revisión final de la capa 5a: lo que entra a la edición desde la biblioteca
// (una grabación transcrita, una voz con IA, una pieza de Crear) llega con
// `tiene_palabras` pero sin `palabras`; el render las lee del servidor, así
// que la vista previa las trae (gratis) en cuanto el material está en la
// edición — en UN lugar, `refrescar`, por donde pasa todo cambio.
const palabrasPendientes = new PalabrasPendientes({
  pedir: async (ids) => {
    const r = await fetch(`${datos.urls.materiales_por_id}?ids=${ids.join(",")}&palabras=1`,
      { headers: { Accept: "application/json" } });
    if (sesionTerminada(r)) return {};        // la sesión se cerró: no se insiste (los paneles ya lo dicen)
    if (!r.ok) return null;                   // se reintenta en el próximo cambio
    const j = await r.json().catch(() => null);
    return j && typeof j.materiales === "object" && j.materiales ? j.materiales : null;
  },
  agregar: (mapa) => vista.agregarMateriales(mapa),
});

const TEXTO_GUARDADO = {
  guardado: () => t("guardado.ok"),
  pendiente: () => t("guardado.pendiente"),
  guardando: () => t("guardado.guardando"),
  error: (m) => t("guardado.error", { mensaje: m }),
  conflicto: (m) => m,
};

// localStorage, o null si el navegador no deja tocarlo (modo privado de
// Safari, cookies bloqueadas): «Vincular» funciona igual, solo no se recuerda.
function almacenSeguro() {
  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

// El último argumento de cada operación: {id: {duracion_ms, tiene_audio}}.
function info() {
  return infoDe(vista.materiales);
}

function ir(ms) {
  vista.ir(ms);
  linea.moverCabezal(vista.tiempo());
}

// El aviso bajo el video: un error por defecto (en rojo); `error: false` para
// algo que solo se cuenta, y `breve` para que se vaya solo a los 3 s si nadie
// lo reemplazó antes (lo de «Vincular», revisión final de la capa 5b).
let avisoBreve = null;
function aviso(texto, { error = true, breve = false } = {}) {
  const n = $("aviso-edicion");
  if (avisoBreve !== null) clearTimeout(avisoBreve);
  avisoBreve = null;
  n.textContent = texto || "";
  n.hidden = !texto;
  n.classList.toggle("error", error);
  if (breve && texto) {
    avisoBreve = setTimeout(() => {
      avisoBreve = null;
      if (n.textContent === texto) aviso("");
    }, 3000);
  }
}

function pintarGuardado(estado, mensaje, detalle = "") {
  if (estado === "guardando" || estado === "conflicto") gesto = null;
  const n = $("estado-guardado");
  n.dataset.estado = estado;
  n.textContent = TEXTO_GUARDADO[estado]?.(mensaje) ?? "";
  // en el celular el hueco es fijo: un error largo termina en «…». Lo técnico
  // (la ruta del validador) no se muestra: queda aquí, para soporte (capa 4c).
  n.title = detalle ? `${n.textContent}\n${detalle}` : n.textContent;
  $("recargar").hidden = estado !== "conflicto";
  pintarHerramientas();
}

// Los avisos de carga (capa 4c): se recalculan en cada refresco con el
// documento vigente, así que se van en cuanto una edición los arregla.
function pintarAvisoCarga(id, a) {
  const n = $(id);
  if (!n) return;
  n.textContent = a?.texto ?? "";
  n.hidden = !a;
  n.classList.toggle("error", Boolean(a?.error));
}

function pintarAvisosCarga() {
  const a = avisosCarga(historial.actual, info(), vista.materiales, { acortado: acortadoAlAbrir });
  pintarAvisoCarga("aviso-recortes", a.recortes);
  pintarAvisoCarga("aviso-faltan", a.faltan);
  pintarAvisoCarga("aviso-voces", a.voces);
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
  if (que === "documento") {
    vista.setDocumento(historial.actual);
    if (historial.actual !== datos.documento) acortadoAlAbrir = false;   // «se acortó solo» dura hasta el próximo cambio
  }
  if (seleccion && !buscarClip(seleccion)) seleccion = null;
  linea.dibujar(historial.actual, { seleccion, cabezalMs: vista.tiempo() });
  pintarHerramientas();
  pintarAvisosCarga();
  if (que === "documento" || que === "materiales") palabrasPendientes.revisar(historial.actual, vista.materiales);
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
// propio paso. Un gesto con clave se deriva de su base (vinculos.operarGesto,
// revisión final de la capa 5b): con «Vincular», dónde queda una capa no
// depende del camino que hizo el deslizador.
function operarCon(opciones, nombre, ...args) {
  const clave = opciones?.clave ?? null;
  if (!editable()) {
    gesto = null;
    refrescar(null);
    return false;
  }
  let res;
  try {
    // con «Vincular», lo que estaba encima de un clip del video lo sigue (el
    // mismo documento: un paso de deshacer, un guardado)
    res = vinculos.operarGesto(operaciones[nombre], historial.actual, args, info(),
      { vincular, clave, gesto, continua: historial.fusionaria(clave) });
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
    // el gesto sigue sobre el mismo documento (el último del historial)
    gesto = res.gesto ? { ...res.gesto, ultimo: historial.actual } : null;
    refrescar(null);
    return true;
  }
  gesto = res.gesto;
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
  gesto = null;
  const doc = historial.deshacer();
  if (!doc) return;
  aviso("");
  refrescar();
  guardado.pedir(doc);
}

function rehacer() {
  if (!editable()) return;
  gesto = null;
  const doc = historial.rehacer();
  if (!doc) return;
  aviso("");
  refrescar();
  guardado.pedir(doc);
}

// «Vincular» (D10.9): prendido, lo de encima sigue a su clip del video;
// apagado, se queda donde está. No cambia la edición (es una forma de
// editar, no algo que se produce): no va al historial ni se guarda con ella.
function pintarVincular() {
  const b = $("h-vincular");
  if (!b) return;
  b.setAttribute("aria-pressed", String(vincular));
  b.title = t(vincular ? "editar.vincular_si" : "editar.vincular_no");
}

function alternarVincular() {
  vincular = !vincular;
  gesto = null;
  vinculos.guardarVincular(almacenSeguro(), vincular);
  pintarVincular();
  // en el celular el `title` no se ve nunca: se dice al tocarlo
  aviso(t(vincular ? "editar.vincular_si" : "editar.vincular_no"), { error: false, breve: true });
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
  if ($("h-vincular")) herramienta("h-vincular", alternarVincular);
  pintarVincular();
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
      // la página de entrar (sesión vencida) no es JSON: ni se intenta leer
      const j = sesionTerminada(r) ? null : await r.json().catch(() => null);
      const res = respuestaProducir(r, j);             // producir.js (puro, probado en Node)
      if (res.que === "reemplazo") return pedirReemplazo(res.destinos);
      if (res.que === "error") return avisar(res.texto);
      dialogo.close();
      aviso("");
      $("producir-hecho-texto").textContent = res.texto;
      if (res.url) $("producir-hecho-enlace").href = res.url;
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
  // después de que la biblioteca muestre el panel (escucha el mismo clic, más
  // tarde) y, en el celular, de que suba la hoja: así el panel ya se ve
  queueMicrotask(() => avisos.notificar("biblioteca"));
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

// Capa 5a: abre una pestaña de la biblioteca desde otro lado (tocar un bloque
// de la fila «Subtítulos»): en el celular sube primero su hoja; el clic en la
// pestaña la marca y la muestra (montarDisposicion y la biblioteca lo
// atienden) y marcarPestana avisa "biblioteca" (el panel que se abrió se pone
// al día).
function mostrarBiblioteca(panel) {
  const boton = $("ed-pestanas-biblioteca").querySelector(`[data-panel="${panel}"]`);
  if (!boton) return;
  if (window.matchMedia?.(CELULAR).matches && hojaAbierta !== "ed-biblioteca") {
    abrirHoja("ed-biblioteca", $(`ed-abrir-${panel}`));
  }
  boton.click();
}

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
  ir,
  resuelto: () => vista.resuelto,
  materiales: () => vista.materiales,
  mostrarBiblioteca,
  enfocarTexto,
  escuchar: (fn) => avisos.escuchar(fn),
});

// Los paneles que se enganchan por `editor` (dentro de una función: lo de
// nivel superior que ejecuta algo va después de declararlo todo).
function montarPaneles() {
  // la biblioteca (Medios · Audio · Texto · Subtítulos · Transiciones): carga
  // lo del proyecto mientras la vista previa arranca
  const nombresIdioma = datos.voz?.nombres_idioma ?? datos.subtitulos?.nombres_idioma ?? {};
  const biblioteca = new Biblioteca({
    contenedor: $("ed-panel-biblioteca"), pestanas: $("ed-pestanas-biblioteca"), urls: datos.urls, editor, linea,
    nombresIdioma,
  });
  // capa 5a: la pestaña «Subtítulos» (si al abrir ya corría una transcripción
  // de esta edición, retoma su barra)
  new SubtitulosPanel({ contenedor: biblioteca.zona("subtitulos"), editor, datos });
  // capa 5a (Task 8): la voz en off arriba de «Audio» — voz con IA y grabar
  // con el micrófono (si al abrir ya se creaba una voz, retoma su barra)
  new VozPanel({ contenedor: biblioteca.zona("audio"), editor, datos });
  // las propiedades de lo elegido («Editar»: un formulario por clase de clip,
  // o la mezcla de la edición si no hay nada elegido; «Suena en» nombra los
  // idiomas como la galería de voces; «Encuadre» mide el cuadro que se dibuja)
  new Propiedades({ contenedor: $("ed-panel-propiedades"), editor, materiales: () => vista.materiales,
                    nombresIdioma, medidasPrincipal: (id) => vista.medidasPrincipal(id) });
  // tocar, mover y agrandar los textos y las imágenes sobre el video (necesita
  // la vista previa: el documento que se dibuja y las medidas de los textos)
  new InteraccionLienzo({ escenario: $("ed-escenario"), lienzo: $("lienzo"), editor, vista });
}

montarHerramientas();
montarProducir();
montarDisposicion();
montarPaneles();
refrescar(null);           // la línea se ve ya, aunque las fuentes tarden en cargar
// lo arreglado al abrir también se guarda (ya con todo declarado y montado:
// ver arreglarAlAbrir arriba; tests/test_editor_js.py vigila el orden)
if (alAbrir.guardar) guardado.pedir(historial.actual);
await vista.iniciar();
// con el reloj listo: el cabezal donde está, y ya hay destino elegido (la
// pestaña Subtítulos y la fila de la línea lo necesitan resuelto)
refrescar("destino");
// otro destino: los textos variables de la línea cambian (vista.js ya escucha
// este select desde iniciar(), así que cuando esto corre el destino ya cambió)
$("destino").addEventListener("change", () => refrescar("destino"));

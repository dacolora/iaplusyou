// Página del editor (capa 4a): une la vista previa, la línea de tiempo, las
// operaciones con deshacer/rehacer, el autoguardado y «Producir». Cada
// operación sale de operaciones.js (pura); si es inválida se muestra su
// mensaje y nada cambia. Si otra pestaña guardó antes («conflicto»), el
// guardado se detiene y la página ya no deja editar: lo que se hiciera aquí
// no se podría guardar; se ofrece recargar.
import { Guardado } from "./guardado.js";
import { Historial } from "./historial.js";
import { LineaTiempo } from "./linea_tiempo.js";
import * as operaciones from "./operaciones.js";
import { VistaPrevia } from "./vista.js";

const datos = JSON.parse(document.getElementById("datos-editor").textContent);
const $ = (id) => document.getElementById(id);
const historial = new Historial(datos.documento);
let seleccion = null;

const vista = new VistaPrevia({
  datos,
  alCambiarTiempo: (t, reproduciendo) => linea.moverCabezal(t, { seguir: reproduciendo }),
  alCambiarMateriales: () => refrescar(false),
});
const linea = new LineaTiempo({
  contenedor: $("linea"),
  zoom: $("linea-zoom"),
  materiales: () => vista.materiales,
  destino: () => vista.destino,
  alSeleccionar: (id) => { seleccion = id; refrescar(false); },
  alOperar: operar,
  alIr: (t) => {
    vista.ir(t);
    linea.moverCabezal(vista.tiempo());
  },
});
const guardado = new Guardado({ url: datos.urls.guardar, versionN: datos.edicion.version_n, alCambiar: pintarGuardado });

const TEXTO_GUARDADO = {
  guardado: () => "Guardado",
  pendiente: () => "Cambios sin guardar…",
  guardando: () => "Guardando…",
  error: (m) => `No se guardó: ${m}`,
  conflicto: (m) => m,
};

function duraciones() {
  const out = {};
  for (const [k, m] of Object.entries(vista.materiales)) if (m?.duracion_ms) out[k] = m.duracion_ms;
  return out;
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
  const esVideo = editableSel && (sel.pista.tipo === "video" || sel.pista.tipo === "superpuesto");
  $("h-velocidad").disabled = !esVideo;
  $("h-velocidad").value = String(esVideo ? Number(sel.clip.velocidad ?? 1) : 1);
}

function refrescar(docCambio = true) {
  if (docCambio) vista.setDocumento(historial.actual);
  if (seleccion && !buscarClip(seleccion)) seleccion = null;
  linea.dibujar(historial.actual, { seleccion, cabezalMs: vista.tiempo() });
  pintarHerramientas();
}

// En conflicto no se edita: nada de lo que se haga se podría guardar.
function editable() {
  if (guardado.estado !== "conflicto") return true;
  aviso("Esta edición cambió en otra pestaña: recarga la página para seguir editando.");
  return false;
}

function operar(nombre, ...args) {
  if (!editable()) {
    refrescar(false);
    return;
  }
  let res;
  try {
    res = operaciones[nombre](historial.actual, ...args, duraciones());
  } catch (e) {
    const invalida = e.name === "OperacionInvalida";
    if (!invalida) console.error(e);
    aviso(invalida ? e.message : `No se pudo hacer ese cambio (${e.message}). La edición quedó como estaba.`);
    refrescar(false);
    return;
  }
  aviso("");
  seleccion = res.seleccion;
  if (JSON.stringify(res.doc) === JSON.stringify(historial.actual)) {   // nada cambió: ni historial ni guardado
    refrescar(false);
    return;
  }
  historial.aplicar(res.doc);
  refrescar();
  guardado.pedir(res.doc);
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
  for (const v of operaciones.VELOCIDADES) $("h-velocidad").append(new Option(`${v}×`, String(v)));
  herramienta("h-cortar", () => operar("cortarEn", vista.tiempo()));
  herramienta("h-borrar", () => seleccion && operar("borrar", seleccion));
  herramienta("h-duplicar", () => seleccion && operar("duplicar", seleccion));
  herramienta("h-deshacer", deshacer);
  herramienta("h-rehacer", rehacer);
  // Como los botones: el select no se queda con el foco (si no, S, Supr y
  // Ctrl+Z irían a él y las flechas cambiarían la velocidad sin querer).
  $("h-velocidad").addEventListener("change", (e) => {
    e.target.blur();
    if (seleccion) operar("cambiarVelocidad", seleccion, Number(e.target.value));
  });
  $("recargar").addEventListener("click", () => location.reload());
  // Espacio y flechas son de la vista previa (vista.js); estas, de la edición.
  document.addEventListener("keydown", (e) => {
    if ($("producir-dialogo").open || e.target.closest?.("input, select, textarea")) return;
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
      if (!e.repeat) operar("cortarEn", vista.tiempo());
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
    boton.title = "Esta edición no está unida a un video de Crear: todavía no se puede producir desde aquí.";
    return;
  }
  const minutos = Math.max(1, Math.round((Number(datos.estimado_s) || 60) / 60));
  $("producir-tiempo").textContent = minutos === 1 ? "cerca de un minuto por destino" : `unos ${minutos} minutos por destino`;
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
  const avisar = (t) => {
    $("producir-aviso").textContent = t || "";
    $("producir-aviso").hidden = !t;
  };
  const unir = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} y ${xs.at(-1)}` : xs[0]);
  // Ya hay una final de ese destino que no salió de esta edición (la vía
  // automática, con voz, u otra edición): producir la reemplaza, así que se
  // pregunta antes. La confirmación vale para esa selección: cambiarla la quita.
  const pedirReemplazo = (destinos) => {
    const cuales = unir(destinos.map(nombre));
    $("producir-reemplazo-texto").textContent = destinos.length === 1
      ? `Ya hay una final de ${cuales} hecha por otro camino (puede tener voz). Si produces, esta la reemplaza.`
      : `Ya hay finales de ${cuales} hechas por otro camino (pueden tener voz). Si produces, estas las reemplazan.`;
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
    if (!destinos.length) return avisar("Marca al menos un destino.");
    $("producir-confirmar").disabled = true;
    $("producir-reemplazar").disabled = true;
    avisar("");
    try {
      await guardado.ahora();        // se produce lo que se ve: primero se guarda lo pendiente
      if (guardado.estado === "conflicto" || guardado.estado === "error") {
        return avisar(`Primero hay que guardar: ${guardado.mensaje}`);
      }
      const r = await fetch(datos.urls.producir, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ version_n: guardado.versionN, destinos, ...(reemplazar ? { reemplazar: true } : {}) }),
      });
      const j = await r.json().catch(() => ({}));
      if (r.status === 409 && Array.isArray(j.reemplazos) && j.reemplazos.length) return pedirReemplazo(j.reemplazos);
      if (!r.ok) return avisar([j.error || `No se pudo producir (error ${r.status}).`, ...(j.problemas ?? [])].join(" "));
      const n = (j.producidas ?? []).filter((p) => p.encolada).length;
      dialogo.close();
      aviso("");
      $("producir-hecho-texto").textContent = n
        ? `Produciendo ${n} final${n === 1 ? "" : "es"}. Las vas a ver en Final edition cuando terminen.`
        : "Esos destinos ya se estaban produciendo.";
      if (j.url) $("producir-hecho-enlace").href = j.url;
      $("producir-hecho").hidden = false;
    } catch {
      avisar("Sin conexión: no se pudo producir. Vuelve a intentar.");
    } finally {
      $("producir-confirmar").disabled = false;
      $("producir-reemplazar").disabled = false;
    }
  }
}

montarHerramientas();
montarProducir();
refrescar(false);          // la línea se ve ya, aunque las fuentes tarden en cargar
await vista.iniciar();
refrescar(false);          // con el reloj listo: el cabezal donde está
// otro destino: los textos variables de la línea cambian (vista.js ya escucha
// este select desde iniciar(), así que cuando esto corre el destino ya cambió)
$("destino").addEventListener("change", () => refrescar(false));

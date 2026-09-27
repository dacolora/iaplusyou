// Página de la vista previa del editor (capa 3, solo lectura): elige el
// destino, resuelve el documento, lleva el reloj y dibuja cada cuadro.
//
// Mientras el sonido carga («Cargando el sonido…», `cargando`) el botón ya
// dice ⏸ pero el reloj todavía no corre: pausar, buscar en la barra o cambiar
// de destino en ese rato PAUSA (nunca lanza un segundo «reproducir»), y
// MotorAudio descarta la llamada que quedó vieja.
//
// Las imágenes (y los videos, en videos.js) se piden sin `crossOrigin`: en la
// capa 3 el lienzo solo se mira, y así se ve aunque el almacenamiento no mande
// CORS. La capa 5 (producir desde el editor lee el lienzo como PNG) tiene que
// volver a poner `crossOrigin = "anonymous"` cuando R2 tenga su regla CORS.
import { dibujarCuadro } from "./lienzo.js";
import { MotorAudio } from "./motor_audio.js";
import { evaluarRespuesta, INTERVALO_SONDEO_MS, listos, TOPE_SONDEO_MS } from "./pendientes.js";
import { Reloj } from "./reloj.js";
import { resolver } from "./resolver.js";
import { cuadroVecino, duracionMs } from "./tiempo.js";
import { Videos } from "./videos.js";

const datos = JSON.parse(document.getElementById("datos-editor").textContent);
const cfg = datos.config;
const $ = (id) => document.getElementById(id);
const lienzo = $("lienzo");
const ctx = lienzo.getContext("2d");
[lienzo.width, lienzo.height] = cfg.formatos[datos.documento.formato];

let materiales = datos.materiales;
let doc = null;
let reloj = null;
let turno = 0;                      // invalida un «reproducir» que quedó esperando el audio
let cargando = false;               // «reproducir» esperando el sonido: el reloj aún no corre
let pedido = true;                  // redibujar en el próximo cuadro
let errorDibujo = false;            // el aviso de un error al dibujar sale una sola vez
const pedirCuadro = () => { pedido = true; };
const ocupado = () => Boolean(reloj?.reproduciendo || cargando);
const fallasCarga = new Set();      // material_id cuyo archivo no cargó (video o imagen)
let videos = new Videos(materiales, pedirCuadro, avisarFalla);
const audio = new MotorAudio(cfg, materiales);
const imagenes = new Map();
const imagenesFallidas = new Set();

const recursos = {
  material: (mid) => materiales[mid] ?? null,
  fuentePrincipal(clip) {
    if (materiales[clip.material_id]?.tipo === "imagen") return recursos.imagen(clip.material_id);
    const el = videos.elementoDe(clip);
    return el && el.readyState >= 2 ? el : null;
  },
  // un material que falló no se reintenta ni pide redibujar en cada cuadro
  fallo: (clip) => imagenesFallidas.has(Number(clip.material_id)) || videos.fallo(clip),
  medidas: (f) => (f instanceof HTMLVideoElement ? [f.videoWidth, f.videoHeight] : [f.naturalWidth, f.naturalHeight]),
  imagen(mid) {
    const id = Number(mid);
    if (imagenesFallidas.has(id)) return null;
    let img = imagenes.get(id);
    if (!img) {
      const m = materiales[id];
      if (!m) return null;
      img = new Image();
      img.addEventListener("load", pedirCuadro);
      img.addEventListener("error", () => {
        imagenesFallidas.add(id);
        avisarFalla(id);
        pedirCuadro();
      });
      img.src = m.url;
      imagenes.set(id, img);
    }
    return img.complete && img.naturalWidth ? img : null;
  },
};

// Los avisos de la plantilla más los que nacen aquí (carga, dibujo).
function aviso(id, texto, error = false) {
  let el = $(id);
  if (!el) {
    if (!texto) return;
    el = document.createElement("p");
    el.id = id;
    el.className = "editor-aviso";
    document.querySelector(".editor-avisos").append(el);
  }
  el.textContent = texto || "";
  el.hidden = !texto;
  el.classList.toggle("error", Boolean(error));
}

function nombreMaterial(mid) {
  const m = materiales[mid];
  const tipo = m?.tipo === "imagen" ? "la imagen" : m?.tipo === "video" ? "el video" : "el archivo";
  let archivo = "";
  try {
    archivo = decodeURIComponent(String(m?.url_proxy || m?.url || "").split("?")[0].split("/").pop() || "");
  } catch { /* nombre raro: solo el tipo */ }
  return archivo ? `${tipo} «${archivo.slice(0, 40)}»` : tipo;
}

function avisarFalla(mid) {
  fallasCarga.add(Number(mid));
  mostrarFallas();
}

function enumerar(lista) {
  try {
    return new Intl.ListFormat("es", { type: "conjunction" }).format(lista);
  } catch {
    return lista.join(", ");
  }
}

function mostrarFallas() {
  const lista = [...fallasCarga].map(nombreMaterial);
  const varias = lista.length > 1;
  aviso("aviso-carga", lista.length
    ? `No se ${varias ? "pudieron" : "pudo"} cargar ${enumerar(lista)} (el enlace no respondió o el archivo ya no está): ${varias ? "esas partes quedan vacías" : "esa parte queda vacía"} en la vista previa.`
    : "", true);
}

function avisoSonido() {
  const n = audio.fallidos.size;
  return n
    ? `No se pudo cargar el sonido de ${n} archivo(s) (puede ser la conexión o que el almacenamiento no dé permiso de lectura): la vista previa sigue sin ese sonido.`
    : "";
}

function formatoTiempo(ms) {
  const s = Math.max(0, ms) / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}

function elegirDestino(clave) {
  const t = reloj ? reloj.tiempo() : 0;
  if (ocupado()) pausar();
  const [idioma, pais] = clave.split("_");
  try {
    doc = resolver(datos.documento, idioma, pais);
    aviso("aviso-destino", "");
  } catch (e) {
    doc = null;
    aviso("aviso-destino", e.name === "VariableSinValor" ? `${e.message} Elige otro destino.`
      : `No se pudo preparar este destino: ${e.message}`, true);
    return;
  }
  const dur = duracionMs(doc);
  reloj = new Reloj(() => audio.ahoraMs(), dur);
  reloj.ir(Math.min(t, dur));
  $("barra").max = String(dur);
  pedirCuadro();
}

async function reproducir() {
  if (!doc || ocupado()) return;
  if (reloj.terminado()) reloj.ir(0);
  const miTurno = ++turno;
  cargando = true;
  $("reproducir").textContent = "⏸";
  $("reproducir").setAttribute("aria-label", "Pausar");
  aviso("aviso-audio", "Cargando el sonido…");
  let inicio = null;
  let falla = null;
  try {
    inicio = await audio.reproducir(doc, reloj.tiempo());
  } catch (e) {
    falla = e;
  }
  if (miTurno !== turno) return;     // pausar() llegó mientras cargaba: ya dejó todo quieto
  cargando = false;
  if (falla) {
    inicio = audio.ahoraMs();
    aviso("aviso-audio", `La vista previa va sin sonido: ${falla.message}`, true);
  } else if (inicio === null) {      // MotorAudio la descartó por vieja
    pausar();
    return;
  } else {
    aviso("aviso-audio", avisoSonido(), audio.fallidos.size > 0);
  }
  reloj.reproducir(inicio);
}

function pausar() {
  turno++;
  if (cargando) aviso("aviso-audio", avisoSonido(), audio.fallidos.size > 0);
  cargando = false;
  reloj?.pausar();
  audio.detener();
  videos.pausarTodo();
  $("reproducir").textContent = "▶";
  $("reproducir").setAttribute("aria-label", "Reproducir");
  pedirCuadro();
}

function cuadro() {
  // el próximo cuadro se pide primero: un error al dibujar no apaga la vista
  requestAnimationFrame(cuadro);
  if (!doc || !reloj) return;
  try {
    const t = reloj.tiempo();
    const rep = reloj.reproduciendo;
    videos.sincronizar(doc, t, rep);
    if (rep || pedido) {
      pedido = false;
      const r = dibujarCuadro(ctx, doc, t, recursos, cfg);
      $("aproximada").hidden = !r.aproximada;
      if (r.faltaCuadro) pedido = true;        // el video todavía no tiene ese cuadro
      $("tiempo").textContent = `${formatoTiempo(t)} / ${formatoTiempo(reloj.dur)}`;
      if (document.activeElement !== $("barra")) $("barra").value = String(Math.round(t));
    }
    if (rep && reloj.terminado()) pausar();
  } catch (e) {
    if (!errorDibujo) {
      errorDibujo = true;
      console.error(e);
      aviso("aviso-dibujo", `La vista previa tuvo un problema al dibujar (${e.message}). Recarga la página; si se repite, avísanos.`, true);
    }
  }
}

// Copias livianas (y picos del sonido) que el servidor todavía prepara: se
// pregunta cada INTERVALO_SONDEO_MS y lo que ya esté listo se usa enseguida
// aunque falten otros — nunca mientras reproduce o carga el sonido (se deja
// para la próxima vuelta). Pasado TOPE_SONDEO_MS, o si la respuesta no sirve
// (sesión vencida, edición borrada), se deja de preguntar y se avisa.
const inicioSondeo = performance.now();

function rendirsePendientes() {
  const n = datos.pendientes.length;
  aviso("aviso-preparando", `No se ${n > 1 ? "pudieron" : "pudo"} preparar las copias livianas de ${n} archivo(s): la vista previa sigue con los originales (se ve igual, solo tarda más en cargar).`);
}

function usarListos(j) {
  const ids = listos(datos.pendientes, j);
  datos.pendientes = (j.pendientes ?? []).map(Number);
  if (!ids.length) return;
  materiales = { ...materiales };
  for (const mid of ids) materiales[mid] = j.materiales[mid];
  audio.materiales = materiales;
  videos.renovar(materiales, ids);
  for (const mid of ids) if (materiales[mid]?.tipo === "video") fallasCarga.delete(mid);
  mostrarFallas();
  pedirCuadro();
}

async function vigilarPendientes() {
  if (!datos.pendientes.length) {
    aviso("aviso-preparando", "");
    return;
  }
  if (performance.now() - inicioSondeo > TOPE_SONDEO_MS) {
    rendirsePendientes();
    return;
  }
  aviso("aviso-preparando", `Preparando ${datos.pendientes.length} archivo(s) para que la vista previa sea más liviana. Es gratis; mientras tanto se usan los originales.`);
  let decision = "reintentar";                 // sin red: se vuelve a intentar
  try {
    const r = await fetch(datos.urls.materiales, { headers: { Accept: "application/json" } });
    decision = evaluarRespuesta(r);
    if (decision === "json") {
      const j = await r.json();
      if (!ocupado()) usarListos(j);           // se mira DESPUÉS de leer: pudo empezar a reproducir
    }
  } catch {
    if (decision === "json") decision = "parar";   // decía JSON y no lo era
  }
  if (decision === "parar") {
    rendirsePendientes();
    return;
  }
  if (!datos.pendientes.length) {
    aviso("aviso-preparando", "");
    return;
  }
  setTimeout(vigilarPendientes, INTERVALO_SONDEO_MS);
}

async function iniciar() {
  const sel = $("destino");
  for (const d of datos.destinos) sel.append(new Option(d.replace("_", " · "), d));
  sel.addEventListener("change", () => elegirDestino(sel.value));
  if (datos.aviso_recortes) {
    aviso("aviso-recortes", `Esta edición no se puede producir tal como está: ${datos.aviso_recortes}`, true);
  }
  if (datos.faltantes.length) {
    aviso("aviso-faltan", `Faltan ${datos.faltantes.length} archivo(s) de esta edición (se borraron o no son de este proyecto): esas partes no se verán.`, true);
  }
  try {
    await Promise.all(cfg.fuentes.map((f) => document.fonts.load(`32px "${f}"`)));
  } catch { /* sigue con la fuente de respaldo */ }
  $("reproducir").addEventListener("click", () => (ocupado() ? pausar() : reproducir()));
  $("inicio").addEventListener("click", () => {
    pausar();
    reloj?.ir(0);
    pedirCuadro();
  });
  $("barra").addEventListener("input", (e) => {
    if (ocupado()) pausar();
    reloj?.ir(Number(e.target.value));
    pedirCuadro();
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.closest?.("input, select, textarea, button")) return;
    if (e.code === "Space") {
      e.preventDefault();
      if (ocupado()) pausar();
      else reproducir();
    } else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && reloj) {
      pausar();
      reloj.ir(cuadroVecino(reloj.tiempo(), e.key === "ArrowRight" ? 1 : -1, cfg.fps));
      pedirCuadro();
    }
  });
  elegirDestino(datos.destinos[0]);
  requestAnimationFrame(cuadro);
  vigilarPendientes();
}

iniciar();

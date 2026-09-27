// Página de la vista previa del editor (capa 3, solo lectura): elige el
// destino, resuelve el documento, lleva el reloj y dibuja cada cuadro.
import { dibujarCuadro } from "./lienzo.js";
import { MotorAudio } from "./motor_audio.js";
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
let pedido = true;                  // redibujar en el próximo cuadro
const pedirCuadro = () => { pedido = true; };
let videos = new Videos(materiales, pedirCuadro);
const audio = new MotorAudio(cfg, materiales);
const imagenes = new Map();

const recursos = {
  material: (mid) => materiales[mid] ?? null,
  fuentePrincipal(clip) {
    if (materiales[clip.material_id]?.tipo === "imagen") return recursos.imagen(clip.material_id);
    const el = videos.elementoDe(clip);
    return el && el.readyState >= 2 ? el : null;
  },
  medidas: (f) => (f instanceof HTMLVideoElement ? [f.videoWidth, f.videoHeight] : [f.naturalWidth, f.naturalHeight]),
  imagen(mid) {
    let img = imagenes.get(mid);
    if (!img) {
      const m = materiales[mid];
      if (!m) return null;
      img = new Image();
      img.crossOrigin = "anonymous";
      img.addEventListener("load", pedirCuadro);
      img.src = m.url;
      imagenes.set(mid, img);
    }
    return img.complete && img.naturalWidth ? img : null;
  },
};

function aviso(id, texto, error = false) {
  const el = $(id);
  el.textContent = texto || "";
  el.hidden = !texto;
  el.classList.toggle("error", Boolean(error));
}

function formatoTiempo(ms) {
  const s = Math.max(0, ms) / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}

function elegirDestino(clave) {
  const t = reloj ? reloj.tiempo() : 0;
  if (reloj?.reproduciendo) pausar();
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
  if (!doc || reloj.reproduciendo) return;
  if (reloj.terminado()) reloj.ir(0);
  const miTurno = ++turno;
  $("reproducir").textContent = "⏸";
  $("reproducir").setAttribute("aria-label", "Pausar");
  aviso("aviso-audio", "Cargando el sonido…");
  let inicio;
  try {
    inicio = await audio.reproducir(doc, reloj.tiempo());
    aviso("aviso-audio", audio.fallidos.size
      ? "Parte del sonido no se pudo cargar (el almacenamiento no dio permiso). La imagen sigue." : "", audio.fallidos.size > 0);
  } catch (e) {
    inicio = audio.ahoraMs();
    aviso("aviso-audio", `La vista previa va sin sonido: ${e.message}`, true);
  }
  if (miTurno !== turno) {           // se pausó mientras cargaba
    audio.detener();
    return;
  }
  reloj.reproducir(inicio);
}

function pausar() {
  turno++;
  reloj?.pausar();
  audio.detener();
  videos.pausarTodo();
  $("reproducir").textContent = "▶";
  $("reproducir").setAttribute("aria-label", "Reproducir");
  pedirCuadro();
}

function cuadro() {
  if (doc && reloj) {
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
  }
  requestAnimationFrame(cuadro);
}

async function vigilarPendientes() {
  if (!datos.pendientes.length) {
    aviso("aviso-preparando", "");
    return;
  }
  aviso("aviso-preparando", `Preparando ${datos.pendientes.length} archivo(s) para que la vista previa sea más liviana. Es gratis; mientras tanto se usan los originales.`);
  try {
    const r = await fetch(datos.urls.materiales, { headers: { Accept: "application/json" } });
    if (r.ok && !reloj?.reproduciendo) {
      const j = await r.json();
      datos.pendientes = j.pendientes;
      if (!j.pendientes.length) {
        materiales = j.materiales;
        audio.materiales = materiales;
        videos.vaciar();
        videos = new Videos(materiales, pedirCuadro);
        aviso("aviso-preparando", "");
        pedirCuadro();
        return;
      }
    }
  } catch { /* se reintenta */ }
  setTimeout(vigilarPendientes, 5000);
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
  $("reproducir").addEventListener("click", () => (reloj?.reproduciendo ? pausar() : reproducir()));
  $("inicio").addEventListener("click", () => {
    pausar();
    reloj?.ir(0);
    pedirCuadro();
  });
  $("barra").addEventListener("input", (e) => {
    if (reloj?.reproduciendo) pausar();
    reloj?.ir(Number(e.target.value));
    pedirCuadro();
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.closest?.("input, select, textarea, button")) return;
    if (e.code === "Space") {
      e.preventDefault();
      if (reloj?.reproduciendo) pausar();
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

// Vista previa del editor: elige el destino, resuelve el documento, lleva el
// reloj y dibuja cada cuadro. Nació en la capa 3 (página de solo lectura);
// desde la capa 4a es una clase sin efectos al importar: la arranca
// pagina_editor.js con `iniciar()`, le pasa cada documento editado
// (`setDocumento`, que re-resuelve el MISMO destino conservando el tiempo) y
// escucha el tiempo (`alCambiarTiempo`, para el cabezal de la línea) y los
// materiales que llegan del servidor (`alCambiarMateriales`). Desde la capa 4b
// la página también le suma materiales nuevos (`agregarMateriales`: lo que se
// sube o se trae de la biblioteca), que llegan por el mismo aviso.
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

const $ = (id) => document.getElementById(id);

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

function enumerar(lista) {
  try {
    return new Intl.ListFormat("es", { type: "conjunction" }).format(lista);
  } catch {
    return lista.join(", ");
  }
}

function formatoTiempo(ms) {
  const s = Math.max(0, ms) / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}

// El archivo que la vista previa carga de un material (el video usa su copia
// liviana en cuanto existe): si cambia, lo cargado antes ya no sirve.
const archivoDe = (m) => `${m?.url ?? ""}\n${m?.url_proxy ?? ""}`;

// Capa 4b: suma materiales (la forma de vista_previa.material_para) a los que
// ya hay, en un mapa NUEVO (el de antes no se toca). `recibidos`: los ids que
// entraron; `cambiados`: los nuevos y los que traen otro archivo (llegó su
// copia liviana, otra URL) — esos se vuelven a cargar. Lo demás (picos, tira)
// cambia sin recargar nada.
export function fusionarMateriales(vigentes, mapa) {
  const materiales = { ...vigentes };
  const recibidos = [];
  const cambiados = [];
  for (const [k, m] of Object.entries(mapa ?? {})) {
    const mid = Number(k);
    if (!m || typeof m !== "object" || !Number.isInteger(mid)) continue;
    const previo = vigentes?.[mid];
    materiales[mid] = m;
    recibidos.push(mid);
    if (!previo || archivoDe(previo) !== archivoDe(m)) cambiados.push(mid);
  }
  const orden = (a, b) => a - b;
  return { materiales, recibidos: recibidos.sort(orden), cambiados: cambiados.sort(orden) };
}

// El último argumento de las operaciones (operaciones.js): {id: {duracion_ms,
// tiene_audio}}. Una duración sin medir (null o 0) va como null —
// «desconocida», nunca 0, que las operaciones leerían como un archivo vacío.
export function infoDe(materiales) {
  const out = {};
  for (const [k, m] of Object.entries(materiales ?? {})) {
    if (!m) continue;
    out[k] = { duracion_ms: m.duracion_ms || null, tiene_audio: m.tiene_audio ?? null };
  }
  return out;
}

export class VistaPrevia {
  constructor({ datos, alCambiarTiempo = () => {}, alCambiarMateriales = () => {} }) {
    this.datos = datos;
    this.cfg = datos.config;
    this.documentoOriginal = datos.documento;
    this.alCambiarTiempo = alCambiarTiempo;
    this.alCambiarMateriales = alCambiarMateriales;
    this.lienzo = $("lienzo");
    this.ctx = this.lienzo.getContext("2d");
    [this.lienzo.width, this.lienzo.height] = this.cfg.formatos[datos.documento.formato];

    this.materialesVigentes = datos.materiales;
    this.doc = null;
    this.reloj = null;
    this.destinoActual = null;
    this.turno = 0;                      // invalida un «reproducir» que quedó esperando el audio
    this.cargando = false;               // «reproducir» esperando el sonido: el reloj aún no corre
    this.pedido = true;                  // redibujar en el próximo cuadro
    this.errorDibujo = false;            // el aviso de un error al dibujar sale una sola vez
    this.pedirCuadro = () => { this.pedido = true; };
    this.cuadro = this.cuadro.bind(this);
    this.fallasCarga = new Set();        // material_id cuyo archivo no cargó (video o imagen)
    this.porRenovar = new Set();         // material_id con archivo nuevo, a recargar al pausar
    this.videos = new Videos(this.materialesVigentes, this.pedirCuadro, (mid) => this.avisarFalla(mid));
    this.audio = new MotorAudio(this.cfg, this.materialesVigentes);
    this.imagenes = new Map();
    this.imagenesFallidas = new Set();
    this.inicioSondeo = null;
    this.recursos = this.crearRecursos();
  }

  // ---- API de la página ----

  setDocumento(docOriginal) {
    // la página editó: se re-resuelve el MISMO destino conservando el tiempo
    // (antes de iniciar() todavía no hay destino: iniciar() lo resuelve)
    this.documentoOriginal = docOriginal;
    if (this.destinoActual !== null) this.elegirDestino(this.destinoActual);
  }

  tiempo() {
    return this.reloj ? this.reloj.tiempo() : 0;
  }

  ir(tMs) {
    if (this.ocupado()) this.pausar();
    this.reloj?.ir(tMs);
    this.pedirCuadro();
  }

  // Capa 4b: materiales que llegan sin recargar la página (lo que se sube,
  // una pieza de Crear que se preparó, la copia liviana que terminó). Entran
  // enseguida (las operaciones y los clips nuevos ya los ven); los que traen
  // otro archivo se vuelven a cargar (sus <video>, su imagen, su sonido) y
  // se olvida un fallo anterior — con la vista quieta: como en usarListos, lo
  // que se ve y suena mientras reproduce no se corta (se hace al pausar).
  // Devuelve los ids que entraron.
  agregarMateriales(mapa) {
    const { materiales, recibidos, cambiados } = fusionarMateriales(this.materialesVigentes, mapa);
    if (!recibidos.length) return [];
    this.materialesVigentes = materiales;
    this.audio.materiales = materiales;
    this.videos.materiales = materiales;
    for (const mid of cambiados) this.porRenovar.add(mid);
    if (!this.ocupado()) this.renovarPendientes();
    this.pedirCuadro();
    this.alCambiarMateriales(materiales);        // la línea usa sus tiras y picos
    return recibidos;
  }

  renovarPendientes() {
    if (!this.porRenovar.size) return;
    const ids = [...this.porRenovar].sort((a, b) => a - b);
    this.porRenovar.clear();
    this.videos.renovar(this.materialesVigentes, ids);
    for (const mid of ids) {
      this.audio.buffers?.delete(mid);
      this.audio.fallidos?.delete(mid);
      this.imagenes.delete(mid);
      this.imagenesFallidas.delete(mid);
      this.fallasCarga.delete(mid);
    }
    this.mostrarFallas();
  }

  get materiales() {
    return this.materialesVigentes;
  }

  get destino() {
    return this.destinoActual;
  }

  // ---- Vista previa (capa 3) ----

  ocupado() {
    return Boolean(this.reloj?.reproduciendo || this.cargando);
  }

  crearRecursos() {
    const vista = this;
    const recursos = {
      material: (mid) => vista.materialesVigentes[mid] ?? null,
      fuentePrincipal(clip) {
        if (vista.materialesVigentes[clip.material_id]?.tipo === "imagen") return recursos.imagen(clip.material_id);
        const el = vista.videos.elementoDe(clip);
        return el && el.readyState >= 2 ? el : null;
      },
      // un material que falló no se reintenta ni pide redibujar en cada cuadro
      fallo: (clip) => vista.imagenesFallidas.has(Number(clip.material_id)) || vista.videos.fallo(clip),
      medidas: (f) => (f instanceof HTMLVideoElement ? [f.videoWidth, f.videoHeight] : [f.naturalWidth, f.naturalHeight]),
      imagen(mid) {
        const id = Number(mid);
        if (vista.imagenesFallidas.has(id)) return null;
        let img = vista.imagenes.get(id);
        if (!img) {
          const m = vista.materialesVigentes[id];
          if (!m) return null;
          img = new Image();
          img.addEventListener("load", vista.pedirCuadro);
          img.addEventListener("error", () => {
            vista.imagenesFallidas.add(id);
            vista.avisarFalla(id);
            vista.pedirCuadro();
          });
          img.src = m.url;
          vista.imagenes.set(id, img);
        }
        return img.complete && img.naturalWidth ? img : null;
      },
    };
    return recursos;
  }

  nombreMaterial(mid) {
    const m = this.materialesVigentes[mid];
    const tipo = m?.tipo === "imagen" ? "la imagen" : m?.tipo === "video" ? "el video" : "el archivo";
    let archivo = "";
    try {
      archivo = decodeURIComponent(String(m?.url_proxy || m?.url || "").split("?")[0].split("/").pop() || "");
    } catch { /* nombre raro: solo el tipo */ }
    return archivo ? `${tipo} «${archivo.slice(0, 40)}»` : tipo;
  }

  avisarFalla(mid) {
    this.fallasCarga.add(Number(mid));
    this.mostrarFallas();
  }

  mostrarFallas() {
    const lista = [...this.fallasCarga].map((mid) => this.nombreMaterial(mid));
    const varias = lista.length > 1;
    aviso("aviso-carga", lista.length
      ? `No se ${varias ? "pudieron" : "pudo"} cargar ${enumerar(lista)} (el enlace no respondió o el archivo ya no está): ${varias ? "esas partes quedan vacías" : "esa parte queda vacía"} en la vista previa.`
      : "", true);
  }

  avisoSonido() {
    const n = this.audio.fallidos.size;
    return n
      ? `No se pudo cargar el sonido de ${n} archivo(s) (puede ser la conexión o que el almacenamiento no dé permiso de lectura): la vista previa sigue sin ese sonido.`
      : "";
  }

  elegirDestino(clave) {
    this.destinoActual = clave;
    const t = this.reloj ? this.reloj.tiempo() : 0;
    if (this.ocupado()) this.pausar();
    const [idioma, pais] = clave.split("_");
    try {
      this.doc = resolver(this.documentoOriginal, idioma, pais);
      aviso("aviso-destino", "");
    } catch (e) {
      this.doc = null;
      aviso("aviso-destino", e.name === "VariableSinValor" ? `${e.message} Elige otro destino.`
        : `No se pudo preparar este destino: ${e.message}`, true);
      return;
    }
    const dur = duracionMs(this.doc);
    this.reloj = new Reloj(() => this.audio.ahoraMs(), dur);
    this.reloj.ir(Math.min(t, dur));
    $("barra").max = String(dur);
    this.pedirCuadro();
  }

  async reproducir() {
    if (!this.doc || this.ocupado()) return;
    if (this.reloj.terminado()) this.reloj.ir(0);
    const miTurno = ++this.turno;
    this.cargando = true;
    $("reproducir").textContent = "⏸";
    $("reproducir").setAttribute("aria-label", "Pausar");
    aviso("aviso-audio", "Cargando el sonido…");
    let inicio = null;
    let falla = null;
    try {
      inicio = await this.audio.reproducir(this.doc, this.reloj.tiempo());
    } catch (e) {
      falla = e;
    }
    if (miTurno !== this.turno) return;     // pausar() llegó mientras cargaba: ya dejó todo quieto
    this.cargando = false;
    if (falla) {
      inicio = this.audio.ahoraMs();
      aviso("aviso-audio", `La vista previa va sin sonido: ${falla.message}`, true);
    } else if (inicio === null) {      // MotorAudio la descartó por vieja
      this.pausar();
      return;
    } else {
      aviso("aviso-audio", this.avisoSonido(), this.audio.fallidos.size > 0);
    }
    this.reloj.reproducir(inicio);
  }

  pausar() {
    this.turno++;
    if (this.cargando) aviso("aviso-audio", this.avisoSonido(), this.audio.fallidos.size > 0);
    this.cargando = false;
    this.reloj?.pausar();
    this.audio.detener();
    this.videos.pausarTodo();
    this.renovarPendientes();                    // lo que llegó mientras reproducía
    $("reproducir").textContent = "▶";
    $("reproducir").setAttribute("aria-label", "Reproducir");
    this.pedirCuadro();
  }

  cuadro() {
    // el próximo cuadro se pide primero: un error al dibujar no apaga la vista
    requestAnimationFrame(this.cuadro);
    if (!this.doc || !this.reloj) return;
    try {
      const t = this.reloj.tiempo();
      const rep = this.reloj.reproduciendo;
      this.videos.sincronizar(this.doc, t, rep);
      if (rep || this.pedido) {
        this.pedido = false;
        const r = dibujarCuadro(this.ctx, this.doc, t, this.recursos, this.cfg);
        $("aproximada").hidden = !r.aproximada;
        if (r.faltaCuadro) this.pedido = true;        // el video todavía no tiene ese cuadro
        $("tiempo").textContent = `${formatoTiempo(t)} / ${formatoTiempo(this.reloj.dur)}`;
        if (document.activeElement !== $("barra")) $("barra").value = String(Math.round(t));
        this.alCambiarTiempo(t, rep);              // la línea de tiempo mueve su cabezal
      }
      if (rep && this.reloj.terminado()) this.pausar();
    } catch (e) {
      if (!this.errorDibujo) {
        this.errorDibujo = true;
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
  rendirsePendientes() {
    const n = this.datos.pendientes.length;
    aviso("aviso-preparando", `No se ${n > 1 ? "pudieron" : "pudo"} preparar las copias livianas de ${n} archivo(s): la vista previa sigue con los originales (se ve igual, solo tarda más en cargar).`);
  }

  usarListos(j) {
    const ids = listos(this.datos.pendientes, j);
    this.datos.pendientes = (j.pendientes ?? []).map(Number);
    if (!ids.length) return;
    this.materialesVigentes = { ...this.materialesVigentes };
    for (const mid of ids) this.materialesVigentes[mid] = j.materiales[mid];
    this.audio.materiales = this.materialesVigentes;
    this.videos.renovar(this.materialesVigentes, ids);
    for (const mid of ids) if (this.materialesVigentes[mid]?.tipo === "video") this.fallasCarga.delete(mid);
    this.mostrarFallas();
    this.pedirCuadro();
    this.alCambiarMateriales(this.materiales);   // llegaron proxies o tiras: la línea las usa
  }

  async vigilarPendientes() {
    if (!this.datos.pendientes.length) {
      aviso("aviso-preparando", "");
      return;
    }
    if (performance.now() - this.inicioSondeo > TOPE_SONDEO_MS) {
      this.rendirsePendientes();
      return;
    }
    aviso("aviso-preparando", `Preparando ${this.datos.pendientes.length} archivo(s) para que la vista previa sea más liviana. Es gratis; mientras tanto se usan los originales.`);
    let decision = "reintentar";                 // sin red: se vuelve a intentar
    try {
      const r = await fetch(this.datos.urls.materiales, { headers: { Accept: "application/json" } });
      decision = evaluarRespuesta(r);
      if (decision === "json") {
        const j = await r.json();
        if (!this.ocupado()) this.usarListos(j);   // se mira DESPUÉS de leer: pudo empezar a reproducir
      }
    } catch {
      if (decision === "json") decision = "parar";   // decía JSON y no lo era
    }
    if (decision === "parar") {
      this.rendirsePendientes();
      return;
    }
    if (!this.datos.pendientes.length) {
      aviso("aviso-preparando", "");
      return;
    }
    setTimeout(() => this.vigilarPendientes(), INTERVALO_SONDEO_MS);
  }

  async iniciar() {
    // lo que hacía iniciar() en la capa 3: destinos, avisos, fuentes, botones,
    // teclas (Espacio y flechas; la página agrega las suyas), primer destino,
    // bucle de cuadros y sondeo de pendientes
    this.inicioSondeo = performance.now();
    const datos = this.datos;
    const sel = $("destino");
    for (const d of datos.destinos) sel.append(new Option(d.replace("_", " · "), d));
    sel.addEventListener("change", () => this.elegirDestino(sel.value));
    if (datos.aviso_recortes) {
      aviso("aviso-recortes", `Esta edición no se puede producir tal como está: ${datos.aviso_recortes}`, true);
    }
    if (datos.faltantes.length) {
      aviso("aviso-faltan", `Faltan ${datos.faltantes.length} archivo(s) de esta edición (se borraron o no son de este proyecto): esas partes no se verán.`, true);
    }
    try {
      await Promise.all(this.cfg.fuentes.map((f) => document.fonts.load(`32px "${f}"`)));
    } catch { /* sigue con la fuente de respaldo */ }
    $("reproducir").addEventListener("click", () => (this.ocupado() ? this.pausar() : this.reproducir()));
    $("inicio").addEventListener("click", () => {
      this.pausar();
      this.reloj?.ir(0);
      this.pedirCuadro();
    });
    $("barra").addEventListener("input", (e) => {
      if (this.ocupado()) this.pausar();
      this.reloj?.ir(Number(e.target.value));
      this.pedirCuadro();
    });
    document.addEventListener("keydown", (e) => {
      if (e.target.closest?.("input, select, textarea, button")) return;
      if (e.code === "Space") {
        e.preventDefault();
        if (this.ocupado()) this.pausar();
        else this.reproducir();
      } else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && this.reloj) {
        this.pausar();
        this.reloj.ir(cuadroVecino(this.reloj.tiempo(), e.key === "ArrowRight" ? 1 : -1, this.cfg.fps));
        this.pedirCuadro();
      }
    });
    this.elegirDestino(datos.destinos[0]);
    requestAnimationFrame(this.cuadro);
    this.vigilarPendientes();
  }
}

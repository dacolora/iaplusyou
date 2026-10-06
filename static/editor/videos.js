// Un <video> por clip de la pista principal: el proxy de 540p, sin sonido (el
// audio va por Web Audio). Reproduciendo, cada video corre solo y se corrige
// si se aparta más de TOLERANCIA_S del reloj (nunca mientras todavía busca o
// no tiene datos para seguir: en una red lenta cada corrección reiniciaría la
// búsqueda); parado, se busca el cuadro exacto. El cuadro congelado tras el
// último clip (y el primero antes de que arranque) queda quieto aunque el
// reloj corra. Decodifican a la vez solo los de la transición en curso (dos
// como mucho) y el clip que entra en PRECARGA_MS espera parado en su primer
// cuadro. Un video sin usar hace LIBERAR_MS se suelta. Un material cuyo
// archivo falla se avisa una vez (`alFallar`) y no se vuelve a pedir (salvo
// que `renovar` traiga su copia liviana nueva).
//
// Sin `crossOrigin`: en la capa 3 la vista es de solo lectura y un lienzo
// «contaminado» da igual, así el video se ve aunque el almacenamiento no mande
// CORS. La capa 5 (producir desde el editor lee el lienzo como PNG) tiene que
// volver a poner `crossOrigin = "anonymous"` cuando R2 tenga su regla CORS.
import { activo, principalEn, siguienteClip } from "./tiempo.js";

export const PRECARGA_MS = 500;
const TOLERANCIA_S = 0.15;
const LIBERAR_MS = 5000;
const HAVE_FUTURE_DATA = 3;

export class Videos {
  constructor(materiales, alCambiar, alFallar = () => {}) {
    this.materiales = materiales;
    this.alCambiar = alCambiar;
    this.alFallar = alFallar;
    this.elementos = new Map();          // clip.id → {el, usado, mid}
    this.fallidos = new Set();           // material_id cuyo archivo no cargó
  }

  elementoDe(clip) {
    return this.elementos.get(clip.id)?.el ?? null;
  }

  fallo(clip) {
    return this.fallidos.has(Number(clip.material_id));
  }

  _soltar(id) {
    const e = this.elementos.get(id);
    if (!e) return;
    e.el.removeAttribute("src");
    e.el.load();
    this.elementos.delete(id);
  }

  _obtener(clip, ahora) {
    // D1/D2 (capa 5b): una foto nunca pide un <video> (ni para dibujarla ni
    // al precargar la que sigue) — vista.js la dibuja con su copia liviana.
    if (clip.foto) return null;
    const mid = Number(clip.material_id);
    if (this.fallidos.has(mid)) return null;
    let e = this.elementos.get(clip.id);
    if (!e) {
      const m = this.materiales[mid];
      if (!m || m.tipo !== "video") return null;
      const el = document.createElement("video");
      el.muted = true;
      el.playsInline = true;
      el.preload = "auto";
      el.addEventListener("loadeddata", this.alCambiar);
      el.addEventListener("seeked", this.alCambiar);
      // solo cuenta el error de un video vivo: soltar uno (quitarle el src)
      // no es que el archivo haya fallado
      el.addEventListener("error", () => {
        if (this.elementos.get(clip.id)?.el === el) this._fallo(mid);
      });
      el.src = m.url_proxy || m.url;
      e = { el, usado: ahora, mid };
      this.elementos.set(clip.id, e);
    }
    e.usado = ahora;
    return e.el;
  }

  _fallo(mid) {
    if (this.fallidos.has(mid)) return;
    this.fallidos.add(mid);
    for (const [id, e] of [...this.elementos]) if (e.mid === mid) this._soltar(id);
    this.alFallar(mid);
    this.alCambiar();
  }

  sincronizar(doc, tMs, reproduciendo) {
    const ahora = performance.now();
    const vivos = new Set();
    const { capas } = principalEn(doc, tMs);
    for (const capa of capas) {
      const el = this._obtener(capa.clip, ahora);
      if (!el) continue;
      vivos.add(capa.clip.id);
      const objetivo = Math.max(0, capa.fuenteMs / 1000);
      // Una sola capa fuera de su clip = cuadro congelado (o el primero antes
      // de arrancar); en un fundido la cola de A sí corre aunque A ya terminó.
      const quieto = capas.length === 1 && !activo(capa.clip, tMs);
      if (reproduciendo && !quieto) {
        el.playbackRate = capa.clip.velocidad ?? 1;
        if (el.paused) {
          el.currentTime = objetivo;
          el.play().catch(() => {});
        } else if (!el.seeking && el.readyState >= HAVE_FUTURE_DATA && Math.abs(el.currentTime - objetivo) > TOLERANCIA_S) {
          el.currentTime = objetivo;
        }
      } else {
        if (!el.paused) el.pause();
        if (Math.abs(el.currentTime - objetivo) > 0.5 / 30) el.currentTime = objetivo;
      }
    }
    const sig = siguienteClip(doc, tMs);
    if (sig && sig.inicio_ms - tMs <= PRECARGA_MS && !vivos.has(sig.id)) {
      const el = this._obtener(sig, ahora);
      if (el) {
        vivos.add(sig.id);
        if (!el.paused) el.pause();
        const desde = (sig.recorte?.desde_ms ?? 0) / 1000;
        if (Math.abs(el.currentTime - desde) > 0.05) el.currentTime = desde;
      }
    }
    for (const [id, e] of [...this.elementos]) {
      if (vivos.has(id)) continue;
      if (!e.el.paused) e.el.pause();
      if (ahora - e.usado > LIBERAR_MS) this._soltar(id);
    }
  }

  // Materiales que el servidor terminó de preparar (copia liviana nueva): se
  // sueltan sus <video> para que el próximo cuadro los pida con la URL nueva y
  // se olvida un fallo anterior (el archivo ya es otro). Los demás siguen.
  renovar(materiales, mids) {
    this.materiales = materiales;
    const ids = new Set(mids.map(Number));
    for (const [id, e] of [...this.elementos]) if (ids.has(e.mid)) this._soltar(id);
    for (const mid of ids) this.fallidos.delete(mid);
  }

  pausarTodo() {
    for (const e of this.elementos.values()) e.el.pause();
  }

  vaciar() {
    for (const id of [...this.elementos.keys()]) this._soltar(id);
  }
}

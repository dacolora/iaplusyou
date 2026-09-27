// Un <video> por clip de la pista principal: el proxy de 540p, sin sonido (el
// audio va por Web Audio). Reproduciendo, cada video corre solo y se corrige
// si se aparta más de TOLERANCIA_S del reloj; parado, se busca el cuadro
// exacto. Decodifican a la vez solo los de la transición en curso (dos como
// mucho) y el clip que entra en PRECARGA_MS espera parado en su primer
// cuadro. Un video sin usar hace LIBERAR_MS se suelta.
import { principalEn, siguienteClip } from "./tiempo.js";

export const PRECARGA_MS = 500;
const TOLERANCIA_S = 0.15;
const LIBERAR_MS = 5000;

export class Videos {
  constructor(materiales, alCambiar) {
    this.materiales = materiales;
    this.alCambiar = alCambiar;
    this.elementos = new Map();          // clip.id → {el, usado}
  }

  elementoDe(clip) {
    return this.elementos.get(clip.id)?.el ?? null;
  }

  _obtener(clip, ahora) {
    let e = this.elementos.get(clip.id);
    if (!e) {
      const m = this.materiales[clip.material_id];
      if (!m || m.tipo !== "video") return null;
      const el = document.createElement("video");
      el.crossOrigin = "anonymous";
      el.muted = true;
      el.playsInline = true;
      el.preload = "auto";
      el.addEventListener("loadeddata", this.alCambiar);
      el.addEventListener("seeked", this.alCambiar);
      el.src = m.url_proxy || m.url;
      e = { el, usado: ahora };
      this.elementos.set(clip.id, e);
    }
    e.usado = ahora;
    return e.el;
  }

  sincronizar(doc, tMs, reproduciendo) {
    const ahora = performance.now();
    const vivos = new Set();
    for (const capa of principalEn(doc, tMs).capas) {
      const el = this._obtener(capa.clip, ahora);
      if (!el) continue;
      vivos.add(capa.clip.id);
      const objetivo = Math.max(0, capa.fuenteMs / 1000);
      if (reproduciendo) {
        el.playbackRate = capa.clip.velocidad ?? 1;
        if (el.paused) {
          el.currentTime = objetivo;
          el.play().catch(() => {});
        } else if (Math.abs(el.currentTime - objetivo) > TOLERANCIA_S) {
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
    for (const [id, e] of this.elementos) {
      if (vivos.has(id)) continue;
      if (!e.el.paused) e.el.pause();
      if (ahora - e.usado > LIBERAR_MS) {
        e.el.removeAttribute("src");
        e.el.load();
        this.elementos.delete(id);
      }
    }
  }

  pausarTodo() {
    for (const e of this.elementos.values()) e.el.pause();
  }

  vaciar() {
    for (const e of this.elementos.values()) {
      e.el.removeAttribute("src");
      e.el.load();
    }
    this.elementos.clear();
  }
}

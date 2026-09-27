// Audio de la vista previa con Web Audio (spec editor §3): cada clip es un
// AudioBufferSourceNode programado sobre el reloj del AudioContext, con su
// ganancia (volumen y fundidos) → el grupo de mezcla (voz / sonido / música,
// volúmenes del preset) → el agache por la voz (curva calculada por
// adelantado desde los picos) → la salida. Necesita CORS en el
// almacenamiento: sin él el fetch falla, el material queda en `fallidos` y la
// vista previa sigue sin ese sonido, diciéndolo. No replica loudnorm.
import { curvaDucking, grupoDe, nivelesVoz, parsearDucking, puntosGanancia, volumenesEfectivos, volumenesPara } from "./audio.js";

const LATENCIA_S = 0.05;

export class MotorAudio {
  constructor(cfg, materiales) {
    this.cfg = cfg;
    this.materiales = materiales;
    this.ctx = null;
    this.buffers = new Map();
    this.fuentes = [];
    this.nodos = [];
    this.fallidos = new Set();
  }

  contexto() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") this.ctx.resume();
    return this.ctx;
  }

  ahoraMs() {
    return this.ctx ? this.ctx.currentTime * 1000 : performance.now();
  }

  _clips(doc) {
    const out = [];
    for (const p of doc.pistas ?? []) {
      if (p.tipo !== "audio" || p.silenciada || p.oculta) continue;
      for (const c of p.clips ?? []) out.push(c);
    }
    return out;
  }

  _buffer(mid) {
    if (!this.buffers.has(mid)) {
      const m = this.materiales[mid];
      const url = m ? (m.tipo === "video" ? m.url_proxy || m.url : m.url) : null;
      const promesa = !url ? Promise.resolve(null) : fetch(url, { mode: "cors" })
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.arrayBuffer();
        })
        .then((datos) => this.contexto().decodeAudioData(datos))
        .catch(() => {
          this.fallidos.add(mid);
          return null;
        });
      this.buffers.set(mid, promesa);
    }
    return this.buffers.get(mid);
  }

  // Programa todo lo que suena desde tMs y devuelve el instante (ms del
  // AudioContext) en que arranca: el reloj de la página arranca ahí.
  async reproducir(doc, tMs) {
    const ctx = this.contexto();
    const clips = this._clips(doc);
    const ids = [...new Set(clips.map((c) => c.material_id))];
    const buffers = new Map(await Promise.all(ids.map(async (mid) => [mid, await this._buffer(mid)])));
    this.detener();
    const hay = { voz: false, sonido: false, musica: false };
    for (const c of clips) hay[grupoDe(c.rol_audio ?? "subida")] = true;
    const mz = doc.mezcla ?? {};
    const vol = volumenesEfectivos(this.cfg.mezcla, hay, volumenesPara(this.cfg.mezcla, mz.preset, mz.volumenes));
    const ventana = this.cfg.ventana_picos_ms;
    const picos = Object.fromEntries(Object.entries(this.materiales).map(([k, m]) => [k, m.picos]));
    const niveles = hay.voz ? nivelesVoz(doc, picos, ventana, vol.voz) : null;
    const inicio = ctx.currentTime + LATENCIA_S;
    const grupos = {};
    for (const g of ["voz", "sonido", "musica"]) {
      if (!hay[g]) continue;
      const nodo = ctx.createGain();
      nodo.gain.value = vol[g];
      let salida = nodo;
      if (g !== "voz" && niveles) {
        const agache = ctx.createGain();
        const params = parsearDucking(g === "musica" ? this.cfg.mezcla.ducking_musica : this.cfg.mezcla.ducking_sonido);
        const resto = curvaDucking(niveles, ventana, params).slice(Math.floor(tMs / ventana));
        if (resto.length >= 2) agache.gain.setValueCurveAtTime(Float32Array.from(resto), inicio, (resto.length * ventana) / 1000);
        nodo.connect(agache);
        salida = agache;
        this.nodos.push(agache);
      }
      salida.connect(ctx.destination);
      grupos[g] = nodo;
      this.nodos.push(nodo);
    }
    for (const c of clips) {
      const buf = buffers.get(c.material_id);
      if (!buf || c.inicio_ms + c.duracion_ms <= tMs) continue;
      const rel = Math.max(0, tMs - c.inicio_ms);
      const cuando = inicio + Math.max(0, c.inicio_ms - tMs) / 1000;
      const rol = c.rol_audio ?? "subida";
      const src = ctx.createBufferSource();
      src.buffer = buf;
      let offset = ((c.recorte?.desde_ms ?? 0) + rel) / 1000;
      if (rol === "musica") {
        src.loop = true;                 // la música entra con -stream_loop -1
        offset %= buf.duration;
      }
      const gan = ctx.createGain();
      puntosGanancia(c, rel).forEach((p, i) => {
        const at = cuando + (p.t_ms - rel) / 1000;
        if (i === 0) gan.gain.setValueAtTime(p.valor, at);
        else gan.gain.linearRampToValueAtTime(p.valor, at);
      });
      src.connect(gan);
      gan.connect(grupos[grupoDe(rol)]);
      src.start(cuando, offset, (c.duracion_ms - rel) / 1000);
      this.fuentes.push(src);
      this.nodos.push(gan);
    }
    return inicio * 1000;
  }

  detener() {
    for (const s of this.fuentes) {
      try { s.stop(); } catch { /* ya terminó */ }
    }
    for (const n of this.nodos) n.disconnect();
    this.fuentes = [];
    this.nodos = [];
  }
}

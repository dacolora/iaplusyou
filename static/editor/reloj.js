// Reloj maestro de la vista previa (spec editor §3): todo se dibuja en
// función de su tiempo. La fuente de tiempo se inyecta (en la página, el
// AudioContext, para que imagen y sonido compartan reloj).
export class Reloj {
  constructor(ahoraMs, duracionMs) {
    this.ahora = ahoraMs;
    this.dur = duracionMs;
    this.base = 0;
    this.inicio = null;
  }

  get reproduciendo() {
    return this.inicio !== null;
  }

  tiempo() {
    if (this.inicio === null) return this.base;
    return Math.min(this.dur, this.base + Math.max(0, this.ahora() - this.inicio));
  }

  // `inicioMs`: instante (en la fuente de tiempo) en que arranca de verdad;
  // el audio se programa unos ms en el futuro y el reloj espera con él.
  reproducir(inicioMs = this.ahora()) {
    if (this.inicio !== null) return;
    if (this.base >= this.dur) this.base = 0;
    this.inicio = inicioMs;
  }

  pausar() {
    if (this.inicio === null) return;
    this.base = this.tiempo();
    this.inicio = null;
  }

  ir(tMs) {
    this.base = Math.max(0, Math.min(this.dur, Math.round(tMs)));
    if (this.inicio !== null) this.inicio = this.ahora();
  }

  terminado() {
    return this.tiempo() >= this.dur;
  }
}

// Deshacer / rehacer del editor (spec §5: solo en memoria). Guarda documentos
// enteros (las operaciones ya devuelven copias nuevas); como mucho `limite`.
export class Historial {
  constructor(doc, limite = 100) {
    this.actual = doc;
    this.limite = limite;
    this.pasado = [];
    this.futuro = [];
  }

  aplicar(doc) {
    this.pasado.push(this.actual);
    if (this.pasado.length > this.limite) this.pasado.shift();
    this.actual = doc;
    this.futuro = [];
    return doc;
  }

  deshacer() {
    if (!this.pasado.length) return null;
    this.futuro.push(this.actual);
    this.actual = this.pasado.pop();
    return this.actual;
  }

  rehacer() {
    if (!this.futuro.length) return null;
    this.pasado.push(this.actual);
    this.actual = this.futuro.pop();
    return this.actual;
  }

  get puedeDeshacer() {
    return this.pasado.length > 0;
  }

  get puedeRehacer() {
    return this.futuro.length > 0;
  }
}

// Deshacer / rehacer del editor (spec §5: solo en memoria). Guarda documentos
// enteros (las operaciones ya devuelven copias nuevas); como mucho `limite`.
//
// `aplicar(doc, {clave})`: con `clave` no nula, si el paso anterior se hizo
// con la MISMA clave hace menos de 800 ms, este paso la REEMPLAZA en vez de
// apilar uno nuevo — así arrastrar un deslizador (volumen, opacidad...) deja
// un solo deshacer, no uno por cada evento del arrastre. `deshacer`/`rehacer`
// cortan la racha: el próximo `aplicar`, aunque traiga la misma clave, apila
// un paso nuevo (saltar en el tiempo con deshacer no es "seguir arrastrando").
// `ahora` es inyectable (una función sin argumentos) para que las pruebas
// controlen el reloj sin `setTimeout`.
export class Historial {
  constructor(doc, limite = 100) {
    this.actual = doc;
    this.limite = limite;
    this.pasado = [];
    this.futuro = [];
    this.ahora = () => Date.now();
    this._ultimaClave = null;
    this._ultimoTiempo = 0;
  }

  // ¿Un `aplicar` con esta clave, ahora, se fusionaría con el paso anterior?
  // La página lo pregunta ANTES de operar para derivar un gesto de su base
  // (vinculos.operarGesto, revisión final de la capa 5b).
  fusionaria(clave) {
    return clave !== null && clave === this._ultimaClave && this.ahora() - this._ultimoTiempo < 800;
  }

  aplicar(doc, { clave = null } = {}) {
    const fusiona = this.fusionaria(clave);
    const ahora = this.ahora();
    if (!fusiona) {
      this.pasado.push(this.actual);
      if (this.pasado.length > this.limite) this.pasado.shift();
    }
    this.actual = doc;
    this.futuro = [];
    this._ultimaClave = clave;
    this._ultimoTiempo = ahora;
    return doc;
  }

  deshacer() {
    if (!this.pasado.length) return null;
    this.futuro.push(this.actual);
    this.actual = this.pasado.pop();
    this._ultimaClave = null;
    return this.actual;
  }

  rehacer() {
    if (!this.futuro.length) return null;
    this.pasado.push(this.actual);
    this.actual = this.futuro.pop();
    this._ultimaClave = null;
    return this.actual;
  }

  get puedeDeshacer() {
    return this.pasado.length > 0;
  }

  get puedeRehacer() {
    return this.futuro.length > 0;
  }
}

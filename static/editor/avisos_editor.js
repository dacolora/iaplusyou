// Avisos del editor (capa 4b): cómo pagina_editor.js le cuenta a los módulos
// que se enganchan por `editor.escuchar` (biblioteca, propiedades, tocar sobre
// el video) qué cambió. Puro, sin DOM: lo prueba Node.
//
// Dos reglas:
// - Un aviso que nace MIENTRAS se avisa (un oyente que opera o elige algo al
//   enterarse) no se entrega en medio: espera a que termine la vuelta en
//   curso, en el orden en que se pidió, y una sola vez aunque se pida varias
//   (un aviso pendiente no se repite). Cada oyente ve siempre el estado último
//   (la página ya cambió antes de avisar). Un oyente que vuelve a provocar un
//   aviso cada vez que se entera se corta pasadas `maxVueltas` vueltas seguidas
//   (y se dice por `alFallar`) en vez de colgar la página.
// - «seleccion» sale solo cuando la selección cambió de verdad (también si la
//   cambió una operación, como duplicar, que elige la copia); una operación
//   inválida, rechazada o sin cambio no avisa nada.
export class Avisos {
  constructor({ alFallar = (e) => console.error(e), maxVueltas = 50 } = {}) {
    this.alFallar = alFallar;
    this.maxVueltas = maxVueltas;
    this.oyentes = new Set();
    this.cola = [];
    this.avisando = false;
    this.seleccionAnunciada = null;
  }

  escuchar(fn) {
    this.oyentes.add(fn);
    return () => this.oyentes.delete(fn);
  }

  // Lo que pasa tras cada refresco de la página: `que` ("documento",
  // "materiales", "destino"… o null) y la selección vigente; «seleccion» se
  // suma solo si cambió desde el último aviso.
  cambio(que, seleccion) {
    const nueva = seleccion ?? null;
    const ques = que ? [que] : [];
    if (nueva !== this.seleccionAnunciada) {
      this.seleccionAnunciada = nueva;
      ques.push("seleccion");
    }
    this.notificar(...ques);
  }

  notificar(...ques) {
    for (const q of ques) if (q && !this.cola.includes(q)) this.cola.push(q);
    if (this.avisando || !this.cola.length) return;
    this.avisando = true;
    let vueltas = 0;
    try {
      while (this.cola.length) {
        if (vueltas >= this.maxVueltas) {
          const cortados = this.cola.splice(0);
          this.alFallar(new Error(`Un módulo del editor vuelve a cambiar la edición cada vez que se entera: se cortó el aviso («${cortados.join("», «")}»).`));
          break;
        }
        vueltas += 1;
        const q = this.cola.shift();
        for (const fn of [...this.oyentes]) {
          if (!this.oyentes.has(fn)) continue;     // se fue a mitad de la vuelta
          try {
            fn(q);
          } catch (e) {
            this.alFallar(e);
          }
        }
      }
    } finally {
      this.avisando = false;
    }
  }
}

// Avisos del editor (capa 4b, Task 4 fix 1): la cola con la que
// pagina_editor.js avisa a los módulos (biblioteca, propiedades, tocar sobre
// el video) qué cambió. Un oyente que opera o elige algo MIENTRAS se entera
// no recibe avisos anidados fuera de orden: esperan a que termine la vuelta,
// cada uno una sola vez; «seleccion» solo sale cuando la selección cambió.
import { test } from "node:test";
import assert from "node:assert/strict";
import { Avisos } from "../../static/editor/avisos_editor.js";

// Una página de mentira con la misma forma de avisar que pagina_editor.js:
// operar cambia el documento (y a veces la selección) y avisa
// "documento" + la selección; seleccionar solo avisa si cambió.
function paginaFalsa(avisos) {
  const estado = { doc: 0, seleccion: null };
  const refrescar = (que) => avisos.cambio(que, estado.seleccion);
  return {
    estado,
    operar(cambiaDoc, seleccion = estado.seleccion) {
      if (cambiaDoc) estado.doc += 1;
      estado.seleccion = seleccion;
      refrescar(cambiaDoc ? "documento" : null);
    },
    seleccionar(id) {
      estado.seleccion = id;
      refrescar(null);
    },
  };
}

test("avisa a cada oyente en el orden en que se suscribió; dejar() lo quita", () => {
  const avisos = new Avisos();
  const oido = [];
  avisos.escuchar((q) => oido.push(`A:${q}`));
  const dejarB = avisos.escuchar((q) => oido.push(`B:${q}`));
  avisos.notificar("documento");
  dejarB();
  avisos.notificar("tiempo");
  assert.deepEqual(oido, ["A:documento", "B:documento", "A:tiempo"]);
});

test("lo que un oyente provoca espera a que termine la vuelta, en orden y una sola vez", () => {
  const avisos = new Avisos();
  const pagina = paginaFalsa(avisos);
  const oido = [];
  let yaOpero = false;
  avisos.escuchar((q) => {
    oido.push(`A:${q}:doc${pagina.estado.doc}:${pagina.estado.seleccion}`);
    if (q === "documento" && !yaOpero) {
      yaOpero = true;
      pagina.operar(true, "c1");          // duplicar: otro documento y elige la copia
      pagina.operar(true);                // otro cambio más en la misma vuelta
      pagina.seleccionar("c1");           // ya estaba elegido: nada nuevo
    }
  });
  avisos.escuchar((q) => oido.push(`B:${q}:doc${pagina.estado.doc}:${pagina.estado.seleccion}`));
  pagina.operar(true);
  assert.deepEqual(oido, [
    "A:documento:doc1:null",
    "B:documento:doc3:c1",                // B ya ve el documento y la selección últimos
    "A:documento:doc3:c1",                // los anidados, después de la vuelta: una vez cada uno
    "B:documento:doc3:c1",
    "A:seleccion:doc3:c1",
    "B:seleccion:doc3:c1",
  ]);
});

test("«seleccion» sale solo cuando la selección cambió (también si la cambió una operación)", () => {
  const avisos = new Avisos();
  const pagina = paginaFalsa(avisos);
  const oido = [];
  avisos.escuchar((q) => oido.push(q));
  pagina.seleccionar(null);               // ya era null
  pagina.operar(false);                   // operación sin cambio (o inválida): nada
  pagina.seleccionar("v0");
  pagina.seleccionar("v0");               // la misma otra vez: nada
  pagina.operar(true, "v0_2");            // duplicar elige la copia
  pagina.operar(true);                    // cambia el documento, la selección no
  pagina.seleccionar(null);
  assert.deepEqual(oido, ["seleccion", "documento", "seleccion", "documento", "seleccion"]);
});

test("un oyente que opera cada vez que se entera se corta en vez de colgar la página", () => {
  const fallas = [];
  const avisos = new Avisos({ alFallar: (e) => fallas.push(e), maxVueltas: 20 });
  let veces = 0;
  avisos.escuchar((q) => {
    veces += 1;
    if (q === "documento") avisos.notificar("documento");
  });
  avisos.notificar("documento");
  assert.equal(veces, 20);
  assert.equal(fallas.length, 1);
  assert.match(String(fallas[0].message ?? fallas[0]), /se cortó/);
  // y la cola quedó limpia: el próximo aviso vuelve a funcionar
  veces = 0;
  avisos.escuchar(() => {});
  avisos.notificar("tiempo");
  assert.equal(veces, 1);
});

test("un oyente que falla no deja sin aviso a los demás", () => {
  const fallas = [];
  const avisos = new Avisos({ alFallar: (e) => fallas.push(e) });
  const oido = [];
  avisos.escuchar(() => {
    throw new Error("roto");
  });
  avisos.escuchar((q) => oido.push(q));
  avisos.notificar("documento");
  avisos.notificar("tiempo");
  assert.deepEqual(oido, ["documento", "tiempo"]);
  assert.equal(fallas.length, 2);
});

test("quien se va a mitad de una vuelta no recibe el resto; quien llega, desde el próximo aviso", () => {
  const avisos = new Avisos();
  const oido = [];
  let dejarB = null;
  avisos.escuchar((q) => {
    oido.push(`A:${q}`);
    if (dejarB) {
      dejarB();
      dejarB = null;
      avisos.escuchar((r) => oido.push(`C:${r}`));
    }
  });
  dejarB = avisos.escuchar((q) => oido.push(`B:${q}`));
  avisos.notificar("documento");
  avisos.notificar("tiempo");
  assert.deepEqual(oido, ["A:documento", "A:tiempo", "C:tiempo"]);
});

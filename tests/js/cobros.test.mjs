// Cobros (spec 2026-10-08 §5.4): un 402 «saldo insuficiente» de cualquier fetch
// muestra «Recargar saldo», sin quitarle el cuerpo a quien hizo el fetch.
// static/cobros.js es un script clásico: se corre en un contexto de vm con un
// window mínimo y se prueban las piezas que expone en window.CobrosSaldo.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const FUENTE = readFileSync(new URL("../../static/cobros.js", import.meta.url), "utf8");

function cargar(fetchFalso) {
  const ctx = { Response, Promise, setTimeout, Date, console, document: null, fetch: fetchFalso };
  ctx.window = ctx;
  ctx.addEventListener = () => {};
  vm.createContext(ctx);
  vm.runInContext(FUENTE, ctx);
  return ctx;
}

function json402(cuerpo) {
  return new Response(JSON.stringify(cuerpo), { status: 402, headers: { "content-type": "application/json" } });
}

const SALDO = { ok: false, error: "Saldo insuficiente: esto cuesta ≈ US$ 1,50 y tienes US$ 0,40 disponibles. Recarga para seguir.",
                saldo_insuficiente: true, recargar_url: "/cliente/acme#config-ap-saldo" };

test("un 402 de saldo avisa con el enlace y quien hizo el fetch sigue leyendo su error", async () => {
  const avisos = [];
  const w = cargar(async () => json402(SALDO));
  const envuelto = w.CobrosSaldo.envolver(w.fetch, (d) => avisos.push(d));
  const r = await envuelto("/cliente/acme/creative_flow/generar", { method: "POST" });
  const datos = await r.json();                                  // el cuerpo sigue entero para la pantalla
  assert.equal(datos.error, SALDO.error);
  await new Promise((ok) => setTimeout(ok, 0));
  assert.equal(avisos.length, 1);
  assert.equal(avisos[0].recargar_url, "/cliente/acme#config-ap-saldo");
});

test("otros errores y otros 402 no avisan", async () => {
  for (const respuesta of [
    () => new Response(JSON.stringify({ ok: false, error: "otro" }), { status: 400, headers: { "content-type": "application/json" } }),
    () => json402({ ok: false, error: "sin la marca" }),
    () => new Response("<html>402</html>", { status: 402, headers: { "content-type": "text/html" } }),
    () => new Response("{roto", { status: 402, headers: { "content-type": "application/json" } }),
  ]) {
    const avisos = [];
    const w = cargar(async () => respuesta());
    const envuelto = w.CobrosSaldo.envolver(w.fetch, (d) => avisos.push(d));
    await envuelto("/x");
    await new Promise((ok) => setTimeout(ok, 0));
    assert.equal(avisos.length, 0);
  }
});

test("un fetch que falla sigue fallando igual para quien llama", async () => {
  const w = cargar(async () => { throw new TypeError("sin red"); });
  const envuelto = w.CobrosSaldo.envolver(w.fetch, () => assert.fail("no debe avisar"));
  await assert.rejects(envuelto("/x"), /sin red/);
});

test("al cargar, el fetch de la página queda envuelto una sola vez", () => {
  const w = cargar(async () => json402(SALDO));
  assert.equal(w.fetch.cobros, true);
  const antes = w.fetch;
  vm.runInContext(FUENTE, w);                                   // una segunda carga no lo envuelve otra vez
  assert.equal(w.fetch, antes);
});

test("el enlace solo lleva a una ruta de este sitio", () => {
  const { urlSegura } = cargar(async () => null).CobrosSaldo;
  assert.equal(urlSegura("/cliente/acme#config-ap-saldo"), "/cliente/acme#config-ap-saldo");
  for (const mala of ["javascript:alert(1)", "//otro.com/x", "https://otro.com", "/\\otro.com", "", null]) {
    assert.equal(urlSegura(mala), "");
  }
});

test("la vuelta del pago sondea hasta 60 s y para con el primer estado final", () => {
  const { pasoSondeo, LIMITE_MS, CADA_MS } = cargar(async () => null).CobrosSaldo;
  assert.equal(CADA_MS, 3000);
  assert.equal(pasoSondeo({ estado: "pendiente" }, 3000), "seguir");
  assert.equal(pasoSondeo(null, 3000), "seguir");
  assert.equal(pasoSondeo({ estado: "pendiente" }, LIMITE_MS), "tarde");
  for (const e of ["aprobada", "rechazada", "expirada", "anulada"]) assert.equal(pasoSondeo({ estado: e }, 0), "final");
});

test("el panel del saldo se vuelve a pedir al reabrir el apartado o pasado un minuto", () => {
  const { debePedirPanel } = cargar(async () => null).CobrosSaldo;
  assert.equal(debePedirPanel("nada", true, false, 0), true);          // primera vez que se ve
  assert.equal(debePedirPanel("nada", false, false, 0), false);        // oculto: no paga el libro
  assert.equal(debePedirPanel("pidiendo", true, true, 99999), false);  // ya va uno en camino
  assert.equal(debePedirPanel("listo", true, false, 5000), false);     // sigue abierto y fresco
  assert.equal(debePedirPanel("listo", true, true, 5000), true);       // se volvió a abrir
  assert.equal(debePedirPanel("listo", true, true, 1000), false);      // varios eventos del mismo clic
  assert.equal(debePedirPanel("listo", true, false, 60000), true);     // pasó un minuto
  assert.equal(debePedirPanel("listo", false, true, 60000), false);
});

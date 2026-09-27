import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolver, valorDestino } from "../../static/editor/resolver.js";

const TABLA = JSON.parse(readFileSync(new URL("../fixtures/resolver_casos.json", import.meta.url), "utf8"));

test("resolver da lo mismo que documento.resolver en cada destino", () => {
  for (const c of TABLA.casos) {
    if (c.error) {
      assert.throws(() => resolver(TABLA.doc, c.idioma, c.pais), (e) => e.name === c.error, `${c.idioma}_${c.pais}`);
    } else {
      assert.deepEqual(resolver(TABLA.doc, c.idioma, c.pais), c.esperado, `${c.idioma}_${c.pais}`);
    }
  }
});

test("resolver quita la voz con por_destino null para ese destino exacto (pt_BR)", () => {
  const res = resolver(TABLA.doc, "pt", "BR");
  const pVoz = res.pistas.find((p) => p.id === "p_voz");
  assert.ok(!pVoz.clips.some((c) => c.id === "voz_hook"), "voz_hook debería haberse quitado en pt_BR");
});

test("resolver no toca el documento de entrada", () => {
  const antes = JSON.stringify(TABLA.doc);
  resolver(TABLA.doc, "es", "CO");
  assert.equal(JSON.stringify(TABLA.doc), antes);
});

test("valorDestino: gana idioma_PAIS, luego idioma; vacío es nulo; cadena vacía cuenta", () => {
  assert.equal(valorDestino({ es: "a", es_CO: "b" }, "es", "CO"), "b");
  assert.equal(valorDestino({ es: "a" }, "es", "MX"), "a");
  assert.equal(valorDestino({}, "es", "CO"), null);
  assert.equal(valorDestino(null, "es", "CO"), null);
  assert.equal(valorDestino({ es_CO: "" }, "es", "CO"), "");
});

// Los módulos puros del editor hablan con t() (static/editor/textos.js): sin
// textos de la página, en español (la fuente); con ponerTextos, en el idioma
// de quien mira. Cada archivo de node --test corre en su propio proceso, así
// que ponerTextos no se filtra a las demás pruebas.
import { test } from "node:test";
import assert from "node:assert/strict";
import { listaY, ponerTextos, separadorDecimal, t } from "../../static/editor/textos.js";
import { cabeceraFila, nombreFila, nombreTransicion } from "../../static/editor/escala.js";
import { cortarEn, OperacionInvalida } from "../../static/editor/operaciones.js";
import { textosBiblioteca } from "../../static/editor/biblioteca.js";
import { mensajeConflicto, textoSegundos, textoVelocidad } from "../../static/editor/propiedades_modelo.js";
import { docBase, DURACIONES } from "./doc_base.mjs";

test("sin los textos de la página habla en español", () => {
  assert.equal(t("guardado.ok"), "Guardado");
  assert.equal(t("producir.minutos", { n: 3 }), "unos 3 minutos por destino");
  assert.equal(listaY(["a", "b", "c"]), "a, b y c");
  assert.equal(separadorDecimal(), ",");
});

test("con los textos de la página, los módulos puros hablan en ese idioma", () => {
  ponerTextos({ "fila.voz": "Voice", "op.cabezal_fuera": "Put the playhead inside a clip to split it." }, "en");
  assert.equal(nombreFila({ id: "p_voz", tipo: "audio", clips: [{ rol_audio: "voz" }] }, { pistas: [] }), "Voice");
  assert.throws(() => cortarEn(docBase(), 9000, DURACIONES),
    (e) => e instanceof OperacionInvalida && e.message === "Put the playhead inside a clip to split it.");
  assert.equal(t("guardado.ok"), "Guardado");           // la clave que falta cae al español
  assert.equal(listaY(["a", "b", "c"]), "a, b, and c");
});

test("capa 4b: cabeceras, transiciones, biblioteca y panel en el idioma de la página", () => {
  ponerTextos({
    "fila.texto": "Text", "tr.desenfoque": "Fade to black", "bib.texto_titulo": "Title",
    "prop.conflicto": "This edit changed in another tab: reload the page to keep going.",
  }, "en");
  assert.deepEqual(cabeceraFila({ id: "p_t", tipo: "texto", clips: [] }, docBase()), { icono: "texto", nombre: "Text" });
  assert.equal(nombreTransicion("desenfoque"), "Fade to black");
  assert.equal(textosBiblioteca()[0].nombre, "Title");
  assert.equal(mensajeConflicto(), "This edit changed in another tab: reload the page to keep going.");
  assert.equal(textoSegundos(500), "0.5 s");            // el separador decimal del idioma de la página
  assert.equal(textoVelocidad(0.75), "0.75×");
});

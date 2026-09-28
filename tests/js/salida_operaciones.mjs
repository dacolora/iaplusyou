// Aplica cada operación al documento de prueba e imprime los documentos que
// resultan, para que tests/test_operaciones_editor.py los pase por
// documento.validar y compilador.verificar_recortes (la referencia es Python).
import * as op from "../../static/editor/operaciones.js";
import { docBase, DURACIONES as D } from "./doc_base.mjs";

const casos = [];
const anotar = (nombre, fn, duraciones) => casos.push({ nombre, doc: fn().doc, ...(duraciones ? { duraciones } : {}) });
anotar("cortar", () => op.cortarEn(docBase(), 2000, D));
anotar("cortar_dos_veces", () => op.cortarEn(op.cortarEn(docBase(), 2000, D).doc, 5000, D));
anotar("borrar_principal", () => op.borrar(docBase(), "v0", D));
anotar("borrar_texto", () => op.borrar(docBase(), "t1", D));
anotar("duplicar_principal", () => op.duplicar(docBase(), "v1", D));
anotar("duplicar_texto", () => op.duplicar(docBase(), "t1", D));
anotar("recortar_fin", () => op.recortar(docBase(), "v0", "fin", -1500, D));
anotar("recortar_inicio", () => op.recortar(docBase(), "v1", "inicio", -800, D));
anotar("mover_principal", () => op.moverPrincipal(docBase(), "v1", 0, D));
anotar("mover_texto", () => op.moverA(docBase(), "t1", 5000, D));
anotar("velocidad", () => op.cambiarVelocidad(docBase(), "v1", 0.5, D));
anotar("velocidad_al_borde_del_material", () => op.cambiarVelocidad(docBase(), "v1", 1.5, D));
anotar("transicion_normalizada", () => {
  const d = docBase();
  d.pistas[0].clips[0].transicion = { tipo: "fundido", duracion_ms: 500 };
  return op.recortar(d, "v0", "inicio", 3900, D);
});
// Redondeo (Python redondea a la par, Math.round sube los .5): v1 a cada
// velocidad, alargado hasta el final de un clon de 9 s, cortado en puntos
// impares y recortado desde el inicio por cantidades impares.
// ---- Capa 4b: agregar y cambiar ----
// INFO es el mapa rico {material_id: {duracion_ms, tiene_audio}} que aceptan
// agregarVideo/Audio; material 3 no trae audio nativo.
const INFO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 }, 3: { duracion_ms: 1500, tiene_audio: false } };
anotar("agregar_video_otro_material", () => op.agregarVideo(docBase(), { id: 3 }, { despuesDe: "v0" }, INFO), { ...D, 3: 1500 });
anotar("agregar_imagen", () => op.agregarImagen(docBase(), { id: 4, ancho: 600, alto: 400 }, 1000, {}, INFO));
anotar("agregar_imagen_llenar", () => op.agregarImagen(docBase(), { id: 4, ancho: 600, alto: 400 }, 1000, { llenar: true }, INFO));
anotar("agregar_audio_musica", () => op.agregarAudio(docBase(), { id: 2 }, 4000, { rol: "musica" }, INFO));
anotar("agregar_audio_efecto", () => op.agregarAudio(docBase(), { id: 2 }, 4000, { rol: "efecto" }, INFO));
for (const preset of ["titulo", "subtitulo", "precio", "llamado"]) {
  anotar(`agregar_texto_${preset}`, () => op.agregarTexto(docBase(), 500, preset, INFO));
}
anotar("cortar_audio", () => op.cortarClip(docBase(), "a1", 1000, INFO));
anotar("cortar_imagen", () => {
  const primero = op.agregarImagen(docBase(), { id: 4, ancho: 600, alto: 400 }, 0, { duracionMs: 4000 }, INFO);
  return op.cortarClip(primero.doc, primero.seleccion, 2000, INFO);
});
for (const tipo of op.TRANSICIONES) {
  anotar(`transicion_${tipo}`, () => op.ponerTransicion(docBase(), "v0", tipo, 500, INFO));
}
anotar("editar_texto_literal", () => op.editarTexto(docBase(), "t1", "Nuevo texto", "es", INFO));
anotar("editar_texto_variable", () => {
  const d = docBase();
  d.pistas[1].clips[0].texto = { variable: "gancho" };
  return op.editarTexto(d, "t1", "Oferta", "es_CO", INFO);
});
anotar("cambiar_estilo_y_transform", () => op.cambiar(docBase(), "t1", {
  estilo: { tamano: 60, color: "#112233" },
  transform: { x: 0.3, y: 0.4, escala: 1.2, opacidad: 0.8 },
}, INFO));
anotar("cambiar_ken_burns", () => op.cambiar(docBase(), "v0", { ken_burns: "out" }, INFO));
anotar("volumen_sonido", () => op.volumenSonido(op.normalizar(docBase(), INFO), "v0", 0.3, INFO));

const D9 = { ...D, 1: 9000 };
for (const v of op.VELOCIDADES) {
  const alFinal = op.recortar(op.cambiarVelocidad(docBase(), "v1", v, D9).doc, "v1", "fin", 99999, D9).doc;
  const v1 = alFinal.pistas[0].clips[1];
  for (const dt of [101, 333, 1001, Math.floor(v1.duracion_ms / 2) | 1, v1.duracion_ms - 101]) {
    anotar(`al_final_${v}x_corte_${dt}`, () => op.cortarEn(alFinal, v1.inicio_ms + dt, D9), D9);
  }
  for (const d of [1, 3, 77, 999]) {
    anotar(`al_final_${v}x_inicio_${d}`, () => op.recortar(alFinal, "v1", "inicio", d, D9), D9);
    anotar(`al_final_${v}x_inicio_menos_${d}`, () => op.recortar(alFinal, "v1", "inicio", -d, D9), D9);
  }
  const cortado = op.cortarEn(alFinal, v1.inicio_ms + 1001, D9).doc;
  for (const d of [1, 5, 301]) {
    anotar(`al_final_${v}x_corte_e_inicio_${d}`, () => op.recortar(cortado, "v1_2", "inicio", d, D9), D9);
  }
}
process.stdout.write(JSON.stringify(casos));

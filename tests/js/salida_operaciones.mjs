// Aplica cada operación al documento de prueba e imprime los documentos que
// resultan, para que tests/test_operaciones_editor.py los pase por
// documento.validar y compilador.verificar_recortes (la referencia es Python).
import * as op from "../../static/editor/operaciones.js";
import { docBase, docConVozYPalabras, docVinculos, DURACIONES as D, INFO_PALABRAS } from "./doc_base.mjs";
import * as prop from "../../static/editor/propiedades_modelo.js";
import * as vinc from "../../static/editor/vinculos.js";

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
anotar("agregar_video_al_principio", () => op.agregarVideo(docBase(), { id: 3 }, { indice: 0 }, INFO), { ...D, 3: 1500 });
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
// Fix round 1: un cambio parcial de contorno (solo grosor) tiene que conservar el color que ya tenía.
anotar("cambiar_estilo_parcial", () => {
  const d = docBase();
  d.pistas[1].clips[0].estilo = { ...d.pistas[1].clips[0].estilo, contorno: { color: "#ABCDEF", grosor: 0.01 } };
  return op.cambiar(d, "t1", { estilo: { contorno: { grosor: 0.05 } } }, INFO);
});
anotar("volumen_sonido", () => op.volumenSonido(op.normalizar(docBase(), INFO), "v0", 0.3, INFO));
// Capa 4b (Task 7): lo que pide el panel de propiedades.
anotar("volumen_sonido_espejo_del_borrador", () => op.volumenSonido(docBase(), "v1", 0.3, INFO));
for (const preset of op.MEZCLAS) anotar(`cambiar_mezcla_${preset}`, () => op.cambiarMezcla(docBase(), preset, INFO));
anotar("cambiar_desde_propiedades", () => {
  let d = op.agregarTexto(docBase(), 500, "titulo", INFO).doc;
  const id = "titulo_2";
  for (const cambios of [prop.cambioFondo("pildora", null), prop.cambioFondo("caja", { radio: 1 }), prop.cambioGrosor(12, d.formato),
    prop.cambioSombra(true, d.formato), { estilo: { color: "#FFD60A", alineacion: "izquierda", fuente: "SpaceGrotesk-Bold", tamano: 90 } },
    { animacion: { entrada: "deslizar" } }, { transform: { x: 0.5, y: 0.5 } }]) {
    d = op.cambiar(d, id, cambios, INFO).doc;
  }
  const img = op.agregarImagen(d, { id: 4, ancho: 600, alto: 400 }, 0, {}, INFO);
  const clip = img.doc.pistas.flatMap((p) => p.clips).find((c) => c.id === img.seleccion);
  d = op.cambiar(img.doc, img.seleccion, prop.cambioLlenar(clip, null, img.doc.formato), INFO).doc;
  d = op.cambiar(d, img.seleccion, { transform: { escala: prop.escalaDePorcentaje(40, clip, null, d.formato), opacidad: 0.5 } }, INFO).doc;
  d = op.cambiar(d, "a1", { audio: { volumen: 0, fundido_entrada_ms: 300, fundido_salida_ms: 700 } }, INFO).doc;
  d = op.cambiar(d, "v1", { ken_burns: null }, INFO).doc;
  return op.cambiarMezcla(d, "ambiente_protagonista", INFO);
});
// Fixes finales (1): un borrador sin sonido de la escena (sin p_sonido) sigue
// sin él al editarlo; agregar un video con sonido o mover su volumen lo crea
// solo para ese clip (los demás espejos entran en silencio).
const sinSonido = () => {
  const d = docBase();
  d.pistas = d.pistas.filter((p) => p.id !== "p_sonido");
  return d;
};
const INFO5 = { ...INFO, 5: { duracion_ms: 2000, tiene_audio: true } };
anotar("sin_sonido_mover_texto", () => op.moverA(sinSonido(), "t1", 2500, INFO));
anotar("sin_sonido_cortar", () => op.cortarEn(sinSonido(), 2000, INFO));
anotar("sin_sonido_agregar_video", () => op.agregarVideo(sinSonido(), { id: 5 }, { despuesDe: "v0" }, INFO5), { ...D, 5: 2000 });
anotar("sin_sonido_volumen", () => op.volumenSonido(sinSonido(), "v1", 0.4, INFO));
// Fixes finales (2): lo que se agrega no alarga el video (termina con la principal, 8 s).
const INFO_LARGO = { ...INFO, 6: { duracion_ms: 60000 } };
anotar("agregar_musica_larga_cerca_del_final", () => op.agregarAudio(docBase(), { id: 6 }, 7000, { rol: "musica" }, INFO_LARGO), { ...D, 6: 60000 });
anotar("agregar_musica_larga_al_final", () => op.agregarAudio(docBase(), { id: 6 }, 8000, { rol: "musica" }, INFO_LARGO), { ...D, 6: 60000 });
anotar("agregar_efecto_cerca_del_final", () => op.agregarAudio(docBase(), { id: 2 }, 6000, { rol: "efecto" }, INFO));
anotar("agregar_titulo_al_final", () => op.agregarTexto(docBase(), 8000, "titulo", INFO));
anotar("agregar_imagen_despues_del_final", () => op.agregarImagen(docBase(), { id: 4, ancho: 600, alto: 400 }, 9000, { duracionMs: 12000 }, INFO));
// Fixes finales (8, 10, 12): fondo.ancho automático, escala inicial acotada, la música no cae en la voz.
anotar("cambiar_fondo_ancho_automatico", () => {
  const d = docBase();
  d.pistas[1].clips[0].estilo = { ...d.pistas[1].clips[0].estilo,
    fondo: { color: "#445566", opacidad: 0.5, radio: 0.1, relleno_x: 0.02, relleno_y: 0.02, ancho: 0.4 } };
  return op.cambiar(d, "t1", { estilo: { fondo: { ancho: null } } }, INFO);
});
anotar("agregar_imagen_diminuta", () => op.agregarImagen(docBase(), { id: 4, ancho: 10, alto: 10 }, 1000, {}, INFO));
anotar("agregar_musica_y_efecto_en_sus_pistas", () => {
  const conMusica = op.agregarAudio(docBase(), { id: 2 }, 4000, { rol: "musica" }, INFO).doc;
  return op.agregarAudio(conMusica, { id: 2 }, 0, { rol: "efecto" }, INFO);
});

// Capa 4c (1/10): un audio corto nunca lleva fundidos más largos que él.
const INFO_CORTO = { ...INFO_LARGO, 7: { duracion_ms: 400 } };
anotar("agregar_musica_de_400_ms", () => op.agregarAudio(docBase(), { id: 7 }, 2000, { rol: "musica" }, INFO_CORTO), { ...D, 7: 400 });
anotar("agregar_efecto_corto_al_final", () => op.agregarAudio(docBase(), { id: 7 }, 7900, { rol: "efecto" }, INFO_CORTO), { ...D, 7: 400 });
anotar("cortar_musica_deja_un_pedazo_corto", () => {
  const conMusica = op.agregarAudio(docBase(), { id: 2 }, 0, { rol: "musica" }, INFO);
  return op.cortarClip(conMusica.doc, conMusica.seleccion, 2600, INFO);
});
anotar("cambiar_fundidos_de_mas", () => {
  const conMusica = op.agregarAudio(docBase(), { id: 2 }, 0, { rol: "musica" }, INFO);
  const corto = op.recortar(conMusica.doc, conMusica.seleccion, "fin", -2700, INFO).doc;
  return op.cambiar(corto, conMusica.seleccion, { audio: { fundido_entrada_ms: 900, fundido_salida_ms: 900 } }, INFO);
});
// Capa 4c (2/10): la entrada «deslizar» lleva su duración; «ninguna» la quita.
anotar("animacion_deslizar", () => op.cambiar(docBase(), "t1", { animacion: { entrada: "deslizar" } }, INFO));
anotar("animacion_ninguna", () => {
  const con = op.cambiar(docBase(), "t1", { animacion: { entrada: "deslizar" } }, INFO).doc;
  return op.cambiar(con, "t1", { animacion: { entrada: "ninguna" } }, INFO);
});
// Capa 4c (3/10): mover, alargar o duplicar una capa no alarga el video
// (Python revisa que termine con la principal: prefijo no_alarga_).
anotar("no_alarga_mover_texto", () => op.moverA(docBase(), "t1", 7500, INFO));
anotar("no_alarga_mover_voz", () => op.moverA(docBase(), "a1", 9000, INFO));
anotar("no_alarga_alargar_texto", () => op.recortar(docBase(), "t1", "fin", 99999, INFO));
anotar("no_alarga_alargar_musica", () => {
  const musica = op.agregarAudio(docBase(), { id: 2 }, 1000, { rol: "musica" }, INFO);
  return op.recortar(musica.doc, musica.seleccion, "fin", 99999, INFO);
});
anotar("no_alarga_duplicar_texto_al_final", () => op.duplicar(op.moverA(docBase(), "t1", 5000, INFO).doc, "t1", INFO));
anotar("no_alarga_duplicar_musica_al_final", () => {
  const musica = op.agregarAudio(docBase(), { id: 2 }, 4000, { rol: "musica" }, INFO);
  return op.duplicar(musica.doc, musica.seleccion, INFO);
});
// Arreglo 4: un «deslizar» de la capa 4b guardado sin duración la recibe al normalizar.
anotar("animacion_vieja_sin_duracion", () => {
  const d = docBase();
  d.pistas[1].clips[0].animacion = { entrada: "deslizar" };
  return op.moverA(d, "t1", 2000, INFO);
});

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

// ---- Capa 5a (Tarea 4): subtítulos y voz ----
const PALABRAS_A1 = [{ t_ms: 0, dur_ms: 400, texto: "Hola" }, { t_ms: 500, dur_ms: 300, texto: "mundo" }];
const INFO_SUB = { ...D, 2: { duracion_ms: 3000, palabras: PALABRAS_A1 } };
anotar("poner_fuentes_voz", () => op.ponerFuentesSubtitulos(docBase(), "es", [{ tipo: "voz" }], D));
anotar("poner_fuentes_vacias", () => op.ponerFuentesSubtitulos(docBase(), "en", [], D));
// Fix round 1: el tope (documento.MAX_FUENTES_SUBTITULO) con justo 8 fuentes distintas.
anotar("poner_fuentes_ocho", () => op.ponerFuentesSubtitulos(docBase(), "es", [
  { tipo: "voz" }, { tipo: "sonido" },
  { tipo: "material", material_id: 1 }, { tipo: "material", material_id: 2 }, { tipo: "material", material_id: 3 },
  { tipo: "material", material_id: 4 }, { tipo: "material", material_id: 5 }, { tipo: "material", material_id: 6 },
], D));
anotar("corregir_palabra", () => op.corregirPalabra(docBase(), 2, 0, "  Creatv  ", INFO_SUB));
anotar("quitar_linea", () => op.quitarLinea(docBase(), [{ material_id: 2, indice: 0 }, { material_id: 2, indice: 1 }], INFO_SUB));
anotar("cambiar_subtitulos", () => op.cambiarSubtitulos(docBase(), {
  estilo_id: "minimal", posicion: 0.3, escala: 1.2, resaltado: "#3ddc84", visibles: true,
}, D));
anotar("agregar_voz", () => op.agregarAudio(docBase(), { id: 2 }, 4000, { rol: "voz", idioma: "es" }, INFO));
anotar("cambiar_idioma_audio", () => op.cambiar(docBase(), "a1", { idioma: "en" }, INFO));
casos.push({ nombre: "adoptar_voz", doc: op.adoptarVozComoFuente(docConVozYPalabras(), INFO_PALABRAS) });

// ---- Capa 5b (Tarea 2, D10): «todo sigue a su clip» ----
// Cada caso vincula el resultado de una operación sobre docVinculos() (que
// trae un segundo texto, t2, para forzar una colisión de fila al seguir, y
// una música, m1, que nunca sigue pero sí se recorta por «nada alarga»).
const vincular = (fn, info = D) => {
  const antes = docVinculos();
  return { doc: vinc.seguirPrincipal(antes, fn(antes).doc, info) };
};
anotar("vinculado_borrar_v0", () => vincular((d) => op.borrar(d, "v0", D)));
anotar("vinculado_mover_v1", () => vincular((d) => op.moverPrincipal(d, "v1", 0, D)));
anotar("vinculado_recortar_inicio", () => vincular((d) => op.recortar(d, "v0", "inicio", 1000, D)));
anotar("vinculado_velocidad", () => vincular((d) => op.cambiarVelocidad(d, "v0", 2, D)));
const INFO_VINCULADO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 }, 3: { duracion_ms: 1500, tiene_audio: false } };
anotar("vinculado_agregar_video_al_principio",
  () => vincular((d) => op.agregarVideo(d, { id: 3 }, { indice: 0 }, INFO_VINCULADO), INFO_VINCULADO),
  { ...D, 3: 1500 });
anotar("vinculado_borrar_ultimo", () => vincular((d) => op.borrar(d, "v1", D)));
anotar("vinculado_voces", () => {
  const antes = docVinculos();
  antes.pistas[2].clips.push({
    id: "r1", inicio_ms: 4500, duracion_ms: 2000, material_id: 2, rol_audio: "voz",
    recorte: { desde_ms: 0, hasta_ms: 2000 }, velocidad: 1, audio: { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true },
  });
  return { doc: vinc.seguirPrincipal(antes, op.borrar(antes, "v0", D).doc, D) };
});

process.stdout.write(JSON.stringify(casos));

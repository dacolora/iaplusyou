// Sondeo de los archivos que el servidor todavía prepara para la vista previa
// (la copia liviana de un video y los picos de un sonido: tarea edicion_proxy,
// gratis). Lógica pura, sin DOM: vista.js pregunta cada INTERVALO_SONDEO_MS,
// usa lo que ya esté listo aunque falten otros y deja de preguntar pasado
// TOPE_SONDEO_MS o ante una respuesta que no sirve (sigue con los originales).

export const INTERVALO_SONDEO_MS = 5000;
export const TOPE_SONDEO_MS = 5 * 60 * 1000;

// Qué hacer con la respuesta de `fetch`: "json" = leerla; "reintentar" = una
// falla pasajera del servidor (5xx); "parar" = una redirección (la sesión
// venció y llegaría la página de entrar), algo que no es JSON o un 4xx (la
// edición ya no está): seguir preguntando no cambiaría nada.
export function evaluarRespuesta(r) {
  if (r.redirected) return "parar";
  if (!r.ok) return r.status >= 500 ? "reintentar" : "parar";
  const tipo = r.headers?.get?.("content-type") ?? "";
  return tipo.includes("application/json") ? "json" : "parar";
}

// Los materiales que estaban pendientes y ya no (y que la respuesta trae):
// esos se pueden cambiar ya, sin esperar a los demás.
export function listos(antes, respuesta) {
  const siguen = new Set((respuesta.pendientes ?? []).map(Number));
  const mats = respuesta.materiales ?? {};
  return antes.map(Number).filter((mid) => !siguen.has(mid) && mats[mid]);
}

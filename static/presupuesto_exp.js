/* La cuenta del presupuesto de «Nuevo experimento › Cuánto» (spec 2026-10-02 §5.1–§5.2).
 *
 * Réplica EXACTA de `presupuesto_experimentos.repartir` y `.atajos` (Python): la pantalla pinta al instante, pero el
 * servidor es quien manda (`exp_probar` → `presupuesto_experimentos.validar`). `tests/test_presupuesto_experimentos.py`
 * corre los dos con los mismos casos y exige resultados idénticos: si cambias una cuenta, cambia la otra.
 *
 * Funciones puras, sin DOM: sirven en el navegador (`window.PresupuestoExp`) y en Node (`require`). El mínimo diario de
 * Meta NO vive aquí: lo manda la página (`data-minimo`, de `presupuesto_experimentos.PRESUPUESTO_MINIMO_DIARIO`).
 */
(function (raiz) {
  'use strict';
  // Monedas en que el presupuesto va en pesos enteros: las mismas de presupuesto_experimentos.EN_ENTEROS (una prueba lo exige).
  var EN_ENTEROS = ['ARS', 'CLP', 'COP', 'HUF', 'ISK', 'JPY', 'KRW', 'PYG', 'TWD', 'UGX', 'VND', 'XAF', 'XOF'];
  // Mismos atajos que presupuesto_experimentos.ATAJOS: [veces el mínimo diario por anuncio, días].
  var ATAJOS = [[4, 4], [8, 7], [15, 10]];

  // Pasos por unidad entera de la moneda: 1 si el reparto va en enteros, 100 si lleva centavos.
  function factor(moneda) { return EN_ENTEROS.indexOf(moneda) !== -1 ? 1 : 100; }
  // Quita el ruido binario (1,15 × 100 = 114,99999999999999) sin tocar nada que de verdad tenga decimales.
  function limpio(x) { return Math.round(x * 1e6) / 1e6; }
  function suma(pesos) { return Object.keys(pesos).reduce(function (a, p) { return a + pesos[p]; }, 0); }

  // Reparte `total` en `dias` entre los países según sus anuncios (`pesos` = {pais: n_anuncios}). El diario de cada
  // país va redondeado HACIA ABAJO a la unidad de la moneda, así suma × días nunca pasa del total.
  function repartir(total, dias, pesos, moneda, minimo) {
    var f = factor(moneda), paises = Object.keys(pesos), anuncios = suma(pesos);
    var t = limpio(total * f), diarios = {}, bajos = [], totalMinimo = 0, unidades = 0;
    paises.forEach(function (p) {
      var u = Math.floor(limpio(t * pesos[p] / (anuncios * dias)));
      diarios[p] = u / f;
      unidades += u;
      if (diarios[p] < minimo) bajos.push(p);
      totalMinimo = Math.max(totalMinimo, Math.ceil(limpio(minimo * f * anuncios * dias / pesos[p])) / f);
    });
    return {presupuestos: diarios, bajos: bajos, total_minimo: totalMinimo, total_repartido: unidades * dias / f};
  }

  // «Prueba rápida · Estándar · Fuerte»: diario por anuncio = 4× / 8× / 15× el mínimo de Meta durante 4 / 7 / 10 días,
  // con el total subido a 2 cifras significativas.
  function atajos(pesos, minimo) {
    var anuncios = suma(pesos);
    return ATAJOS.map(function (par) {
      var bruto = anuncios * minimo * par[0] * par[1];
      var paso = Math.pow(10, String(Math.floor(bruto)).length - 2);
      return {total: Math.ceil(bruto / paso) * paso, dias: par[1]};
    });
  }

  var api = {EN_ENTEROS: EN_ENTEROS, ATAJOS: ATAJOS, factor: factor, repartir: repartir, atajos: atajos};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.PresupuestoExp = api;
})(typeof window !== 'undefined' ? window : this);

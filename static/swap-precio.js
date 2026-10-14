/* Crear › Cambiar producto: el precio antes de generar (PND-312, pedido de Daniel 2026-10-13). Un swap de video
   cuesta según cuánto dura el video; la regla de cada modelo llega del servidor ya con el margen
   (#swap-precio-datos, dashboard._precios_swap; misma tabla que providers/swap_video_precio.py). La duración y los
   cuadros por segundo los mide el servidor (/swap/medir) sin guardar el archivo. «Generar» solo se activa con un
   precio a la vista, y ese precio viaja en `precio_visto`: el servidor vuelve a medir y no cobra más que eso. */
(function () {
  // --- precio puro (tests/test_swap_video_precio.py lo compara con el de Python) ---
  function segundosFacturados(t, d, fps, fpsSupuesto) {
    if (t.por_cuadros) d = d * (fps || fpsSupuesto || 30) / t.por_cuadros;
    if (t.redondear) d = Math.ceil(Math.round(d * 1e6) / 1e6);
    d = Math.max(d, t.min_s || 0);
    if (t.max_s != null) d = Math.min(d, t.max_s);
    return d * (t.factor || 1);
  }
  function precioVideo(t, d, fps, fpsSupuesto) {
    if (!t) return null;
    if (t.fijo != null) return t.fijo;
    if (d == null) return null;
    return segundosFacturados(t, d, fps, fpsSupuesto) * t.usd_s;
  }
  function precioFoto(t, nReferencias) {
    if (!t || t.usd == null) return null;
    if (!t.por_referencia) return t.usd;
    if (nReferencias == null) return null;
    return t.usd + t.por_referencia * Math.max(1, Math.min(nReferencias, t.max_referencias || 9));
  }
  window.SwapPrecio = {precioVideo: precioVideo, precioFoto: precioFoto};

  var form = document.getElementById('swap-form');
  var salida = document.getElementById('swap-precio');
  var datosEl = document.getElementById('swap-precio-datos');
  if (!form || !salida || !datosEl) return;
  var config = JSON.parse(datosEl.textContent);
  var P = config.precios, T = config.textos;
  var sep = (config.usdEjemplo || '').indexOf(',') >= 0 ? ',' : '.';
  var input = form.querySelector('input[type="file"][name="foto"]');
  var visto = document.getElementById('swap-precio-visto');
  var boton = document.getElementById('swap-generar');
  var VIDEO = /\.(mp4|mov|webm)$/i;
  var medidas = new Map();   // File -> {d, fps} (o null si el servidor no la pudo leer)
  var turno = 0;

  function fmtUsd(v) { return 'US$ ' + (Math.round(v * 100) / 100).toFixed(2).replace('.', sep); }
  function fmtNum(v) { return (Math.round(v * 10) / 10).toFixed(1).replace('.', sep); }
  function elegido(nombre) { return form.querySelector('input[name="' + nombre + '"]:checked'); }
  function mostrar(texto, precio) {
    salida.textContent = texto;
    visto.value = precio == null ? '' : precio.toFixed(4);
    boton.disabled = precio == null || boton.dataset.sinProductos === '1';
  }

  // La duración y los cuadros los mide el servidor con ffprobe, la misma medida con la que reserva y cobra: así el
  // precio visto y el cobrado coinciden al medio centavo (la del navegador difiere unas centésimas; revisión de
  // guardian-gasto, 2026-10-13). No guarda el archivo.
  // Un error de sesión, de tamaño o de turno se dice con su nombre (y los de turno o sesión no se guardan: al
  // volver a elegir se mide otra vez).
  function medir(archivo) {
    if (medidas.has(archivo)) return Promise.resolve(medidas.get(archivo));
    var datos = new FormData();
    datos.append('video', archivo);
    return fetch(config.urlMedir, {method: 'POST', body: datos, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) {
        if (r.redirected || r.status === 401 || r.status === 403) return {error: 'sesion'};
        if (r.status === 413) return {error: 'grande'};
        if (r.status === 429 || r.status === 503) return {error: 'ocupado'};
        return r.ok ? r.json() : null;
      })
      .then(function (j) {
        if (j && j.error && j.ok === undefined) return j;
        return j && j.ok ? {d: j.duracion_s, fps: j.fps} : null;
      })
      .catch(function () { return {error: 'ocupado'}; })
      .then(function (m) {
        if (!(m && (m.error === 'ocupado' || m.error === 'sesion'))) medidas.set(archivo, m);
        return m;
      });
  }

  function refrescar() {
    var archivos = Array.prototype.slice.call(input.files || []);
    var mio = ++turno;
    if (!archivos.length) return mostrar(T.elegir, null);
    if (!P) return mostrar(T.sinPrecio, null);
    var rVideo = elegido('proveedor_video'), rFoto = elegido('proveedor_foto');
    var tVideo = rVideo ? P.video[rVideo.value] : null, tFoto = rFoto ? P.foto[rFoto.value] : null;
    var producto = elegido('producto_id');
    var nRefs = producto && producto.dataset.nReferencias !== undefined ? parseInt(producto.dataset.nReferencias, 10) : null;
    var hayVideo = archivos.some(function (a) { return VIDEO.test(a.name); });
    if (hayVideo) mostrar(T.midiendo, null);
    Promise.all(archivos.map(function (a) {
      return VIDEO.test(a.name) ? medir(a) : Promise.resolve(undefined);
    })).then(function (ms) {
      if (mio !== turno) return;   // eligió otra cosa mientras medía: gana lo último
      var total = 0, segundos = 0, notas = [];
      for (var i = 0; i < archivos.length; i++) {
        var usd;
        if (VIDEO.test(archivos[i].name)) {
          if (!ms[i]) return mostrar(T.sinDuracion, null);
          if (ms[i].error) return mostrar(T[ms[i].error] || T.sinDuracion, null);
          if (tVideo && tVideo.max_entrada_s && ms[i].d > tVideo.max_entrada_s + 0.05) {
            return mostrar(T.muyLargo.replace('{max}', tVideo.max_entrada_s), null);
          }
          segundos += ms[i].d;
          usd = precioVideo(tVideo, ms[i].d, ms[i].fps, P.fps);
          if (tVideo && tVideo.recorte_s && ms[i].d > tVideo.recorte_s + 0.05) {
            notas.push(T.recorte.replace('{max}', tVideo.recorte_s));
          }
        } else {
          if (tFoto && tFoto.por_referencia && nRefs == null) return mostrar(T.elegirProducto, null);
          usd = precioFoto(tFoto, nRefs);
        }
        if (usd == null) return mostrar(T.sinPrecio, null);
        total += usd;
      }
      var texto = T.aprox + ' ' + fmtUsd(total);
      if (segundos) texto += ' · ' + T.detalleVideos.replace('{segundos}', fmtNum(segundos));
      if (hayVideo && tVideo && tVideo.salida_s) notas.push(T.salidaFija.replace('{segundos}', tVideo.salida_s));
      notas.filter(function (n, j) { return notas.indexOf(n) === j; }).forEach(function (n) { texto += ' · ' + n; });
      mostrar(texto, total);
    });
  }

  input.addEventListener('change', refrescar);
  form.addEventListener('change', function (ev) {
    var n = ev.target.name;
    if (n === 'proveedor_video' || n === 'proveedor_foto' || n === 'producto_id') refrescar();
  });
  refrescar();
})();

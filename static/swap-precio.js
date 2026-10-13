/* Crear › Cambiar producto: el precio antes de generar (PND-312, pedido de Daniel 2026-10-13). Un swap de video
   cuesta según cuánto dura el video; la regla de cada modelo llega del servidor ya con el margen
   (#swap-precio-datos, dashboard._precios_swap; misma tabla que providers/swap_video_precio.py). La duración la
   lee el navegador y, si no puede (un .mov de iPhone en Chrome) o el modelo cobra por cuadros (Wan Animate), la
   mide el servidor sin guardar el archivo. «Generar» solo se activa con un precio a la vista, y ese precio viaja
   en `precio_visto`: el servidor vuelve a medir y no cobra más que eso. */
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
  var medidas = new Map();   // File -> {d, fps} (o null si nadie la pudo leer)
  var turno = 0;

  function fmtUsd(v) { return 'US$ ' + (Math.round(v * 100) / 100).toFixed(2).replace('.', sep); }
  function fmtNum(v) { return (Math.round(v * 10) / 10).toFixed(1).replace('.', sep); }
  function elegido(nombre) { return form.querySelector('input[name="' + nombre + '"]:checked'); }
  function mostrar(texto, precio) {
    salida.textContent = texto;
    visto.value = precio == null ? '' : precio.toFixed(4);
    boton.disabled = precio == null || boton.dataset.sinProductos === '1';
  }

  function enNavegador(archivo) {
    return new Promise(function (listo) {
      var v = document.createElement('video');
      var url = URL.createObjectURL(archivo);
      var hecho = false;
      var fin = function (d) { if (hecho) return; hecho = true; URL.revokeObjectURL(url); listo(d); };
      v.preload = 'metadata';
      v.onloadedmetadata = function () { fin(isFinite(v.duration) && v.duration > 0 ? v.duration : null); };
      v.onerror = function () { fin(null); };
      setTimeout(function () { fin(null); }, 8000);   // sin respuesta: lo mide el servidor
      v.src = url;
    });
  }
  function enServidor(archivo) {
    var datos = new FormData();
    datos.append('video', archivo);
    return fetch(config.urlMedir, {method: 'POST', body: datos, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j && j.ok ? {d: j.duracion_s, fps: j.fps} : null; })
      .catch(function () { return null; });
  }
  function medir(archivo, conFps) {
    var ya = medidas.get(archivo);
    if (ya !== undefined && (!conFps || (ya && ya.fps))) return Promise.resolve(ya);
    var paso = conFps ? enServidor(archivo) : enNavegador(archivo).then(function (d) {
      return d != null ? {d: d, fps: null} : enServidor(archivo);
    });
    return paso.then(function (m) { medidas.set(archivo, m); return m; });
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
    var conFps = !!(rVideo && (P.necesita_fps || []).indexOf(rVideo.value) >= 0);
    var hayVideo = archivos.some(function (a) { return VIDEO.test(a.name); });
    if (hayVideo) mostrar(T.midiendo, null);
    Promise.all(archivos.map(function (a) {
      return VIDEO.test(a.name) ? medir(a, conFps) : Promise.resolve(undefined);
    })).then(function (ms) {
      if (mio !== turno) return;   // eligió otra cosa mientras medía: gana lo último
      var total = 0, segundos = 0, notas = [];
      for (var i = 0; i < archivos.length; i++) {
        var usd;
        if (VIDEO.test(archivos[i].name)) {
          if (!ms[i]) return mostrar(T.sinDuracion, null);
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

/* Crear: audios. Textos y datos del servidor en #crear-audios-datos. */
(function () {
  var raiz = document.getElementById('au');
  if (!raiz) return;
    var config = JSON.parse(document.getElementById('crear-audios-datos').textContent);
    var T = config.textos, D = config.datos;

  // El separador decimal del idioma de quien mira (el filtro usd ya lo sabe).
  var sep = D.usdEjemplo.indexOf(',') >= 0 ? ',' : '.';
  var usdCaracter = parseFloat(raiz.dataset.usdCaracter) || 0;
  var texto = document.getElementById('au-texto'), contador = document.getElementById('au-contador');
  var precio = document.getElementById('au-precio'), crear = document.getElementById('au-crear');
  var crearPrecio = document.getElementById('au-crear-precio');
  var musicaSel = document.getElementById('au-musica'), opciones = document.getElementById('au-musica-opciones');
  var musicaAudio = document.getElementById('au-musica-audio'), inicio = document.getElementById('au-inicio');

  function fmtUsd(v) { return 'US$ ' + (Math.round(v * 100) / 100).toFixed(2).replace('.', sep); }
  var preciosClon = D.preciosClon;
  var preciosDisenar = D.preciosDisenar;
  function refrescarPrecioDisenar() {
    var n = Array.from(document.getElementById('au-vp-nombre-d').value.replace(/\s+/g, ' ').trim()).length;
    var tabla = preciosDisenar[document.getElementById('au-idioma').value];
    document.getElementById('au-vp-disenar-precio').textContent = T.aprox + ' ' + fmtUsd(tabla[Math.min(n, tabla.length - 1)]);
  }
  document.getElementById('au-vp-nombre-d').addEventListener('input', refrescarPrecioDisenar);
  document.getElementById('au-idioma').addEventListener('change', refrescarPrecioDisenar);
  refrescarPrecioDisenar();
  function refrescarPrecioClon() {
    var n = Array.from(document.getElementById('au-vp-nombre-c').value.replace(/\s+/g, ' ').trim()).length;
    var tabla = preciosClon[document.getElementById('au-idioma').value];
    document.getElementById('au-vp-clonar-precio').textContent = T.aprox + ' ' + fmtUsd(tabla[Math.min(n, tabla.length - 1)]);
  }
  document.getElementById('au-vp-nombre-c').addEventListener('input', refrescarPrecioClon);
  document.getElementById('au-idioma').addEventListener('change', refrescarPrecioClon);
  refrescarPrecioClon();
  function refrescarPrecio() {
    var n = texto.value.replace(/\s+/g, ' ').trim().length;
    contador.textContent = n;
    var usd = n * usdCaracter;
    var etiqueta = T.aprox + ' ' + (n && usd < 0.01 ? 'US$ <0' + sep + '01' : fmtUsd(usd));
    precio.textContent = etiqueta;
    crearPrecio.textContent = etiqueta;
    crear.disabled = !n || raiz.dataset.ocupado === '1';
  }
  function mostrarError(msg) {
    var el = document.getElementById('au-error');
    el.textContent = msg || '';
    el.hidden = !msg;
  }
  // Mensaje neutral del resultado de la tarea (nunca el texto de la persona:
  // lo pone la tarea del worker, tareas/audios.py MENSAJES).
  function mostrarAviso(msg) {
    var el = document.getElementById('au-aviso');
    el.textContent = msg || '';
    el.hidden = !msg;
  }
  function ocupado(si) { raiz.dataset.ocupado = si ? '1' : ''; refrescarPrecio(); }
  texto.addEventListener('input', refrescarPrecio);

  // Galería de voces: la tarjeta elige la voz (campo oculto #au-voz) y ▶ pide la
  // muestra de esa voz en el idioma elegido (cacheada en el servidor, la paga
  // Creatv una sola vez) y la reproduce; el botón que suena queda marcado.
  var vozInput = document.getElementById('au-voz'), muestra = document.getElementById('au-muestra');
  var voces = document.getElementById('au-voces'), botonSonando = null;
  function elegirVoz(nombre) {
    vozInput.value = nombre;
    var tarjeta = raiz.querySelector('.au-voz[data-voz="' + nombre + '"] .au-voz-nombre');
    document.getElementById('au-voz-nombre').textContent = tarjeta ? tarjeta.textContent : nombre;
    raiz.querySelectorAll('.au-voz').forEach(function (c) {
      c.setAttribute('aria-checked', c.dataset.voz === nombre ? 'true' : 'false');
    });
  }
  function escucharVoz(boton) {
    var fd = new FormData();
    fd.append('voz', boton.dataset.voz);
    fd.append('idioma', document.getElementById('au-idioma').value);
    boton.disabled = true; boton.textContent = '…'; boton.setAttribute('aria-busy', 'true'); mostrarError('');
    fetch(raiz.dataset.urlMuestra, {method: 'POST', body: fd, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { mostrarError(d.error || T.sinMuestra); return; }
        if (botonSonando) botonSonando.classList.remove('sonando');
        botonSonando = boton; boton.classList.add('sonando');
        muestra.src = d.url;
        muestra.play().catch(function () { muestra.hidden = false; muestra.controls = true; });
        // Oír una voz propia la estrena en el servidor: Mis voces se vuelve a
        // pedir para que se vaya «sin estrenar» (la voz elegida se conserva).
        if (boton.dataset.voz.indexOf('vp:') === 0) refrescarVoces(boton);
      })
      .catch(function () { mostrarError(T.sinConexion); })
      .then(function () { boton.disabled = false; boton.textContent = '▶'; boton.removeAttribute('aria-busy'); });
  }
  muestra.addEventListener('ended', function () {
    if (botonSonando) { botonSonando.classList.remove('sonando'); botonSonando = null; }
  });
  voces.addEventListener('click', function (ev) {
    var play = ev.target.closest('.au-voz-play');
    if (play) { escucharVoz(play); return; }
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta) elegirVoz(tarjeta.dataset.voz);
  });
  voces.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta && ev.target === tarjeta) { ev.preventDefault(); elegirVoz(tarjeta.dataset.voz); }
  });
  document.querySelectorAll('#au .au-voces-filtros .au-filtro').forEach(function (f) {
    f.addEventListener('click', function () {
      document.querySelectorAll('#au .au-voces-filtros .au-filtro').forEach(function (o) { o.classList.toggle('activo', o === f); });
      var g = f.dataset.filtroGenero;
      voces.querySelectorAll('.au-voz').forEach(function (c) { c.hidden = !!g && c.dataset.genero !== g; });
    });
  });

  // Mis voces (spec 2026-09-30): tarjetas re-pintadas por fetch dentro de
  // #au-vp-wrap; los clics van delegados (las tarjetas cambian).
  var vpWrap = document.getElementById('au-vp-wrap'), vpPanel = document.getElementById('au-vp-panel');
  function mostrarErrorVoz(msg) {
    var el = document.getElementById('au-vp-error');
    el.textContent = msg || '';
    el.hidden = !msg;
  }
  function pintarVoces(d, elegirNueva) {
    if (d.html !== undefined) vpWrap.innerHTML = d.html;
    mostrarErrorVoz(d.error);
    if (elegirNueva && d.voces && d.voces.length) {
      elegirVoz(d.voces[0].valor);
    } else if (vozInput.value.indexOf('vp:') === 0 && !raiz.querySelector('.au-voz[data-voz="' + vozInput.value + '"]')) {
      var primera = voces.querySelector('.au-voz');     // la elegida se borró: vuelve a la primera de la galería
      if (primera) elegirVoz(primera.dataset.voz);
    } else {
      elegirVoz(vozInput.value);
    }
    var crearBtn = document.getElementById('au-vp-crear');
    if (crearBtn) crearBtn.setAttribute('aria-expanded', vpPanel.hidden ? 'false' : 'true');
    vigilarVoz();
  }
  // El panel se cierra ANTES de re-pintar, para que aria-expanded del «+ Crear
  // voz propia» nuevo diga la verdad; devuelve d.ok (el clon limpia el archivo
  // solo si salió: un error de la casilla no obliga a elegirlo otra vez).
  function enviarVoz(url, fd) {
    mostrarErrorVoz(''); mostrarAviso('');
    return fetch(url, {method: 'POST', body: fd, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) vpPanel.hidden = true; pintarVoces(d, false); return d.ok; })
      .catch(function () { mostrarErrorVoz(T.sinConexion); });
  }
  // La voz se crea en el worker: se consulta su estado y al terminar se pide
  // solo la sección (recargar borraría lo escrito); la voz nueva queda elegida.
  // Un re-pintado que trae su propia barra de este trabajo trae también su
  // sondeo: el de la barra vieja se calla. Si la barra se fue sin reemplazo (el
  // trabajo terminó justo antes de un re-pintado, p. ej. tras un ▶), este sigue:
  // su próxima consulta ve el final y muestra el aviso o el error. Cinco fallos
  // seguidos (sesión vencida, sin red) también lo paran, en vez de preguntar
  // para siempre.
  function vigilarVoz() {
    var barra = vpWrap.querySelector('.barra-progreso[data-job]');
    if (!barra || barra.dataset.vigilando) return;
    barra.dataset.vigilando = '1';
    var textoBarra = barra.nextElementSibling, fallos = 0;
    var t = setInterval(function () {
      if (!barra.isConnected && vpWrap.querySelector('.barra-progreso[data-job="' + barra.dataset.job + '"]')) { clearInterval(t); return; }
      fetch(barra.dataset.estado).then(function (r) { return r.json(); }).then(function (e) {
        fallos = 0;
        if (e.estado === 'en_progreso') {
          if (textoBarra && e.etapa) textoBarra.textContent = e.etapa;
          return;
        }
        clearInterval(t);
        fetch(raiz.dataset.urlVpLista, {headers: {'X-Requested-With': 'fetch'}})
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (e.estado === 'error') { d.error = e.mensaje || T.noSePudoVoz; pintarVoces(d, false); }
            else { mostrarAviso(e.mensaje || ''); pintarVoces(d, true); }
          })
          .catch(function () { mostrarErrorVoz(T.sinConexion); });
      }).catch(function () {
        if (++fallos >= 5) { clearInterval(t); mostrarErrorVoz(T.sinConexion); }
      });
    }, 4000);
  }
  // Tras el ▶ de una voz propia: la sección re-pintada trae un ▶ nuevo, que
  // queda marcado si la muestra sigue sonando.
  function refrescarVoces(boton) {
    fetch(raiz.dataset.urlVpLista, {headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        pintarVoces(d, false);
        var nuevo = vpWrap.querySelector('.au-voz-play[data-voz="' + boton.dataset.voz + '"]');
        if (nuevo && botonSonando === boton) { botonSonando = nuevo; nuevo.classList.add('sonando'); }
      })
      .catch(function () { mostrarErrorVoz(T.sinConexion); });
  }
  vpWrap.addEventListener('click', function (ev) {
    if (ev.target.closest('#au-vp-crear')) {
      vpPanel.hidden = !vpPanel.hidden;
      ev.target.closest('#au-vp-crear').setAttribute('aria-expanded', vpPanel.hidden ? 'false' : 'true');
      return;
    }
    var borrar = ev.target.closest('.au-vp-borrar');
    if (borrar) {
      if (!confirm(T.confirmarBorrarVoz + ' «' + borrar.dataset.nombre + '»')) return;
      enviarVoz(borrar.dataset.url, new FormData());
      return;
    }
    var play = ev.target.closest('.au-voz-play');
    if (play) { escucharVoz(play); return; }
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta) elegirVoz(tarjeta.dataset.voz);
  });
  vpWrap.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta && ev.target === tarjeta) { ev.preventDefault(); elegirVoz(tarjeta.dataset.voz); }
  });
  vpPanel.querySelectorAll('[data-vp-pestana]').forEach(function (p) {
    p.addEventListener('click', function () {
      vpPanel.querySelectorAll('[data-vp-pestana]').forEach(function (o) {
        o.classList.toggle('activo', o === p);
        o.setAttribute('aria-selected', o === p ? 'true' : 'false');
      });
      vpPanel.querySelectorAll('[data-vp-form]').forEach(function (f) { f.hidden = f.dataset.vpForm !== p.dataset.vpPestana; });
    });
  });
  // El botón queda apagado mientras viaja el pedido (un doble clic no cobra dos
  // veces). Si salió, el formulario queda vacío: reabrir el panel no deja a un
  // clic de pagar otra voz igual y, en un clon, la casilla de permiso vuelve a
  // estar sin marcar — cada clon pide su propio permiso.
  var botonDisenar = document.getElementById('au-vp-disenar'), botonClonar = document.getElementById('au-vp-clonar');
  botonDisenar.addEventListener('click', function () {
    var fd = new FormData();
    fd.append('nombre', document.getElementById('au-vp-nombre-d').value);
    fd.append('descripcion', document.getElementById('au-vp-descripcion').value);
    fd.append('idioma', document.getElementById('au-idioma').value);
    botonDisenar.disabled = true;
    enviarVoz(raiz.dataset.urlVpDisenar, fd).then(function (ok) {
      botonDisenar.disabled = false;
      if (!ok) return;
      document.getElementById('au-vp-nombre-d').value = '';
      document.getElementById('au-vp-descripcion').value = '';
      refrescarPrecioDisenar();
    });
  });
  botonClonar.addEventListener('click', function () {
    var archivo = document.getElementById('au-vp-archivo');
    var fd = new FormData();
    fd.append('nombre', document.getElementById('au-vp-nombre-c').value);
    fd.append('idioma', document.getElementById('au-idioma').value);
    fd.append('consentimiento', document.getElementById('au-vp-permiso').checked ? 'si' : 'no');
    if (archivo.files.length) fd.append('grabacion', archivo.files[0]);
    botonClonar.disabled = true;
    enviarVoz(raiz.dataset.urlVpClonar, fd).then(function (ok) {
      botonClonar.disabled = false;
      if (!ok) return;
      archivo.value = '';
      document.getElementById('au-vp-nombre-c').value = '';
      refrescarPrecioClon();
      document.getElementById('au-vp-permiso').checked = false;
    });
  });
  // El permiso es para ESE archivo: elegir otro (también después de un intento
  // que falló) desmarca la casilla, así nunca pasa de una grabación a otra.
  document.getElementById('au-vp-archivo').addEventListener('change', function () {
    document.getElementById('au-vp-permiso').checked = false;
  });

  // Música: reproductor, segundo de inicio y volumen solo con una canción elegida.
  function mostrarMusica() {
    var o = musicaSel.options[musicaSel.selectedIndex];
    var hay = !!(o && o.value);
    opciones.hidden = !hay;
    if (!hay) { musicaAudio.removeAttribute('src'); return; }
    if (musicaAudio.getAttribute('src') !== o.dataset.url) { musicaAudio.src = o.dataset.url; inicio.value = 0; }
    inicio.max = Math.max(0, Math.floor(parseFloat(o.dataset.duracion || '0')) - 1);
  }
  musicaSel.addEventListener('change', mostrarMusica);
  document.getElementById('au-inicio-usar').addEventListener('click', function () {
    inicio.value = Math.floor(musicaAudio.currentTime || 0);
  });
  function pintarCanciones(canciones, elegir) {
    var actual = musicaSel.value;
    while (musicaSel.options.length > 1) musicaSel.remove(1);
    canciones.forEach(function (c) {
      var o = document.createElement('option');
      o.value = 'mat:' + c.id; o.textContent = c.nombre; o.dataset.url = c.url; o.dataset.duracion = c.duracion_s;
      musicaSel.appendChild(o);
    });
    musicaSel.value = elegir ? ('mat:' + elegir) : actual;
    if (musicaSel.selectedIndex < 0) musicaSel.value = '';
    mostrarMusica();
  }
  document.getElementById('au-archivo').addEventListener('change', function (e) {
    if (!e.target.files.length) return;
    var input = e.target, fd = new FormData();
    fd.append('cancion', input.files[0]);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', raiz.dataset.urlSubir);
    xhr.setRequestHeader('X-Requested-With', 'fetch');
    var aviso = document.getElementById('au-subida');
    aviso.hidden = false; aviso.textContent = T.subiendo + ' 0%';
    xhr.upload.onprogress = function (ev) {
      if (!ev.lengthComputable) return;
      var p = Math.round(ev.loaded * 100 / ev.total);
      aviso.textContent = p < 100 ? (T.subiendo + ' ' + p + '%') : T.revisando;
    };
    xhr.onload = function () {
      var d;
      try { d = JSON.parse(xhr.responseText); } catch (err) { aviso.textContent = T.errorSubir; return; }
      aviso.textContent = d.error || d.mensaje || '';
      if (d.canciones) {
        pintarCanciones(d.canciones, d.nuevo_id);
        try { document.dispatchEvent(new CustomEvent('mi-musica:cambio', {detail: {origen: 'audios', canciones: d.canciones, html: d.html}})); } catch (err) {}
      }
      input.value = '';
    };
    xhr.onerror = function () { aviso.textContent = T.errorRed; };
    xhr.send(fd);
  });
  document.addEventListener('mi-musica:cambio', function (ev) {
    var d = ev.detail || {};
    if (d.origen === 'audios' || !d.canciones) return;
    pintarCanciones(d.canciones, null);
  });

  // Crear: encola en el worker; la lista vuelve pintada y se sondea el trabajo.
  function pintarLista(d) {
    if (d.html !== undefined) document.getElementById('au-lista').innerHTML = d.html;
    mostrarError(d.error);
    vigilar();
  }
  crear.addEventListener('click', function () {
    var fd = new FormData();
    fd.append('texto', texto.value);
    fd.append('voz', document.getElementById('au-voz').value);
    fd.append('idioma', document.getElementById('au-idioma').value);
    fd.append('velocidad', document.getElementById('au-velocidad').value);
    fd.append('musica', musicaSel.value);
    fd.append('inicio_s', inicio.value);
    fd.append('volumen', document.getElementById('au-volumen').value);
    ocupado(true); mostrarError(''); mostrarAviso('');
    fetch(raiz.dataset.urlCrear, {method: 'POST', body: fd, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        pintarLista(d);
        // Un 400 con la barra viva («ya se está creando un audio», desde otra
        // pestaña) deja el botón deshabilitado: la barra manda, no el error.
        if (!d.ok && !document.querySelector('#au-lista .barra-progreso[data-job]')) ocupado(false);
      })
      .catch(function () { mostrarError(T.sinConexion); ocupado(false); });
  });
  // El audio se hace en el worker: se consulta su estado y al terminar se
  // vuelve a pedir SOLO la lista (recargar borraría lo que ya escribiste).
  // Igual que vigilarVoz: solo una lista re-pintada con su propia barra de este
  // trabajo calla el sondeo de la vieja (si la barra se fue sin reemplazo, este
  // sigue y muestra el final), y cinco fallos seguidos lo paran.
  function vigilar() {
    var barra = document.querySelector('#au-lista .barra-progreso[data-job]');
    if (!barra) { ocupado(false); return; }
    if (barra.dataset.vigilando) return;
    barra.dataset.vigilando = '1'; ocupado(true);
    var textoBarra = barra.nextElementSibling, fallos = 0;
    var t = setInterval(function () {
      if (!barra.isConnected && document.querySelector('#au-lista .barra-progreso[data-job="' + barra.dataset.job + '"]')) { clearInterval(t); return; }
      fetch(barra.dataset.estado).then(function (r) { return r.json(); }).then(function (e) {
        fallos = 0;
        if (e.estado === 'en_progreso') {
          if (textoBarra && e.etapa) textoBarra.textContent = e.etapa + (e.progreso ? ' · ' + Math.round(e.progreso) + '%' : '');
          var fill = barra.querySelector('.barra-progreso-fill');
          if (fill && typeof e.progreso === 'number') {
            fill.style.width = Math.max(0, Math.min(100, e.progreso)) + '%';
            fill.classList.remove('barra-progreso-indeterminada');
          }
          return;
        }
        clearInterval(t);
        fetch(raiz.dataset.urlLista, {headers: {'X-Requested-With': 'fetch'}})
          .then(function (r) { return r.json(); })
          .then(function (d) {
            // El mensaje de la tarea (tareas/audios.py MENSAJES, ya traducido
            // por estado_trabajo) llega a la pantalla; si fue error, lo toma
            // el cuadro de error de siempre en vez del aviso neutral.
            if (e.estado === 'error') { d.error = e.mensaje || T.noSePudo; } else { mostrarAviso(e.mensaje || ''); }
            pintarLista(d);
          })
          .catch(function () { mostrarError(T.sinConexion); ocupado(false); });
      }).catch(function () {
        if (++fallos >= 5) { clearInterval(t); mostrarError(T.sinConexion); ocupado(false); }
      });
    }, 4000);
  }
  raiz.addEventListener('click', function (ev) {
    var mas = ev.target.closest('.au-mas');
    if (mas) {
      mas.disabled = true;
      fetch(mas.dataset.url, {headers: {'X-Requested-With': 'fetch'}})
        .then(function (r) { if (!r.ok || r.redirected) throw new Error(); return r.json(); })
        .then(function (d) {
          if (!mas.isConnected) return;
          var fragmento = document.createElement('template');
          fragmento.innerHTML = d.html;
          var lista = document.querySelector('#au-lista .au-items');
          fragmento.content.querySelectorAll('.au-item').forEach(function (item) { lista.appendChild(item); });
          var siguiente = fragmento.content.querySelector('.au-mas');
          if (siguiente) mas.replaceWith(siguiente); else (mas.closest('.acciones') || mas).remove();
        })
        .catch(function () { mas.disabled = false; mostrarError(T.sinConexion); });
      return;
    }
    var b = ev.target.closest('.au-borrar');
    if (b) {
      if (!confirm(T.confirmarBorrar + ' «' + b.dataset.nombre + '»')) return;
      fetch(b.dataset.url, {method: 'POST', body: new FormData(), headers: {'X-Requested-With': 'fetch'}})
        .then(function (r) { return r.json(); }).then(pintarLista)
        .catch(function () { mostrarError(T.sinConexion); });
      return;
    }
    var m = ev.target.closest('[data-crear-modo]');
    if (m) {
      ev.preventDefault();
      var pastilla = document.querySelector('#crear-modos [data-modo="' + m.dataset.crearModo + '"]');
      if (pastilla) pastilla.click();
      window.scrollTo(0, 0);
    }
  });
  // Enter en un campo de una línea no crea nada: solo el botón cobra.
  var form = document.getElementById('au-form');
  form.addEventListener('submit', function (e) { e.preventDefault(); });
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault();
  });
  refrescarPrecio(); mostrarMusica(); vigilar(); vigilarVoz();
})();

/* Crear: compositor. Textos y datos del servidor en #crear-compositor-datos. */
(function () {
    var config = JSON.parse(document.getElementById('crear-compositor-datos').textContent);
    var T = config.textos, D = config.datos;
    // Tipo (video/imagen), modelo elegido y costo en el botón.
    // formatearUSD es global (window.formatearUSD, script de arriba).
    var form = document.getElementById('form-flowplus');
    var comp = document.getElementById('crear-comp');
    var campoModelo = document.getElementById('fp-modelo');
    var botonGenerar = document.getElementById('fp-generar');
    var precio = document.getElementById('fp-precio');
    var calidadWrap = document.getElementById('fp-calidad-wrap');
    var pieLogos = document.getElementById('fp-pie-logos');
    var duracion = document.getElementById('fp-duracion');
    function tipoActual() { return form.querySelector('input[name=tipo]:checked').value; }
    function modeloActual() {
      var n = tipoActual() === 'imagen' ? 'modelo_imagen' : 'modelo_video';
      return form.querySelector('input[name=' + n + ']:checked');
    }
    var formatoVideo = document.getElementById('fp-formato-video');
    var formatoImagen = document.getElementById('fp-formato-imagen');
    var notaFormato = document.getElementById('fp-formato-nota');
    var notaDuracion = document.getElementById('fp-duracion-nota');
    var ta = document.getElementById('fp-texto');
    // Mi música: canción propia (`mat:<id>`) con su segundo de inicio.
    var musicaSel = document.getElementById('fp-musica');
    var inicioWrap = document.getElementById('fp-musica-inicio-wrap');
    var inicioInput = document.getElementById('fp-musica-inicio');
    var audioPrev = document.getElementById('fp-musica-audio');
    var mmWrap = document.getElementById('mm-wrap');
    function esPropia(v) { return !!v && v.indexOf('mat:') === 0; }
    // Referencias y catálogo son opcionales: sin nada adjunto la pieza es de
    // solo texto (y Seedance, sin imagen de arranque, sí elige formato).
    function sinAdjuntos() {
      return !document.querySelector('#fp-bandeja-wrap #fp-bandeja') && !form.querySelector('input[name=productos_catalogo]:checked');
    }

    // "Editar y crear otra a partir de esta": el servidor deja el texto y los
    // ajustes de la pieza original; acá se cargan en el formulario.
    var prefill = D.prefill;
    if (prefill) {
      if (ta && prefill.texto) ta.value = prefill.texto;
      var origenTw = document.getElementById('fp-origen-tw'); if (origenTw && prefill.origen_tw) origenTw.value = prefill.origen_tw;
      var rTipo = form.querySelector('input[name=tipo][value="' + prefill.tipo + '"]');
      if (rTipo) rTipo.checked = true;
      var rModelo = form.querySelector('input[name=modelo_video][value="' + prefill.modelo + '"], input[name=modelo_imagen][value="' + prefill.modelo + '"]');
      if (rModelo) rModelo.checked = true;
      if (duracion && prefill.duracion) duracion.value = String(prefill.duracion);
      var selAr = form.querySelector('select[name=aspect_ratio]');
      if (selAr && prefill.aspect_ratio) selAr.value = prefill.aspect_ratio;
      if (formatoImagen && prefill.tipo === 'imagen' && prefill.aspect_ratio) formatoImagen.value = prefill.aspect_ratio;
      var cs = document.getElementById('fp-check-sonido'); if (cs && typeof prefill.con_sonido === 'boolean') cs.checked = prefill.con_sonido;
      var st = document.getElementById('fp-sonido'); if (st && prefill.sonido_texto) st.value = prefill.sonido_texto;
      var mu = document.getElementById('fp-musica'); if (mu && typeof prefill.musica_estilo === 'string') mu.value = prefill.musica_estilo;
      if (inicioInput && prefill.musica_inicio_s) inicioInput.value = prefill.musica_inicio_s;
      var ca = document.getElementById('fp-calidad'); if (ca && prefill.calidad) ca.checked = prefill.calidad === 'borrador';
      var me = document.getElementById('fp-mejorar'); if (me) me.checked = !!prefill.mejorar_prompt;
      var pl = document.getElementById('fp-plantilla'); if (pl && prefill.plantilla) pl.value = prefill.plantilla;
      setTimeout(function () { form.scrollIntoView({behavior: 'smooth', block: 'start'}); if (ta) ta.focus(); }, 50);
    }
    // Lo que el modelo admite manda: duraciones fuera de su rango y formatos que
    // no soporta se deshabilitan; la selección salta a la opción válida más cercana.
    function limitarSelect(sel, permitido, valorDefecto) {
      var opciones = Array.prototype.slice.call(sel.options);
      opciones.forEach(function (o) { o.disabled = !permitido(o.value); });
      if (sel.selectedOptions.length && sel.selectedOptions[0].disabled) {
        var validas = opciones.filter(function (o) { return !o.disabled; });
        var candidata = validas.filter(function (o) { return o.value === valorDefecto; })[0] || validas[validas.length - 1] || validas[0];
        if (candidata) sel.value = candidata.value;
      }
    }
    function ajustarSegunModelo(m, esImagen) {
      if (!m) return;
      var formatos = ((!esImagen && sinAdjuntos() ? m.dataset.formatosTexto : m.dataset.formatos) || '').split(',').filter(Boolean);
      if (esImagen) {
        if (formatoImagen) limitarSelect(formatoImagen, function (v) { return formatos.indexOf(v) !== -1; }, '9:16');
        // Borrador es solo de Wan 3.0 video: no debe sobrevivir a un cambio a Imagen.
        var calidadImagen = document.getElementById('fp-calidad');
        if (calidadImagen) { calidadImagen.checked = false; calidadImagen.disabled = true; }
        var mejorarImagen = document.getElementById('fp-mejorar');
        if (mejorarImagen) { mejorarImagen.checked = false; mejorarImagen.disabled = true; }
        return;
      }
      var min = parseInt(m.dataset.minDuracion || '2', 10), max = parseInt(m.dataset.maxDuracion || '30', 10);
      limitarSelect(duracion, function (v) { var d = parseInt(v, 10); return d >= min && d <= max; }, '10');
      var sigueImagen = formatos.length === 0;
      if (formatoVideo) {
        formatoVideo.disabled = sigueImagen;
        if (!sigueImagen) limitarSelect(formatoVideo, function (v) { return formatos.indexOf(v) !== -1; }, '9:16');
      }
      if (notaFormato) notaFormato.hidden = !sigueImagen;
      if (notaDuracion) notaDuracion.hidden = m.value !== 'wan3';
      var calidad = document.getElementById('fp-calidad');
      if (calidad) { calidad.disabled = m.value !== 'wan3'; if (calidad.disabled) calidad.checked = false; }
      if (calidadWrap) calidadWrap.hidden = m.value !== 'wan3';
      // «Que Wan mejore mi prompt» solo existe en Wan 3.0; con otro modelo se apaga.
      var mejorar = document.getElementById('fp-mejorar'), mejorarWrap = document.getElementById('fp-mejorar-wrap');
      if (mejorar) { mejorar.disabled = m.value !== 'wan3'; if (mejorar.disabled) mejorar.checked = false; }
      if (mejorarWrap) mejorarWrap.hidden = m.value !== 'wan3';
      var larga = document.getElementById('fp-duracion-larga');
      if (larga) larga.hidden = parseInt(duracion.value, 10) <= 15;
    }
    // Segundos de los videos de la bandeja que el modelo recibe como video
    // (solo Wan 3.0, el único con data-max-total), para su límite y su precio
    // (2026-09-30). Mismas cuentas que flowplus_modelos.segundos_videos y
    // segundos_facturables_referencia.
    function segundosVideosBandeja(m) {
      if (!m || !m.dataset.maxTotal) return [];
      var maxVid = parseInt(m.dataset.maxVideos || '0', 10);
      var segs = [];
      Array.prototype.forEach.call(document.querySelectorAll('#fp-bandeja-wrap #fp-bandeja figure.es-video'), function (fig, i) {
        if (i < maxVid && fig.dataset.duracion) segs.push(parseFloat(fig.dataset.duracion));
      });
      return segs;
    }
    function facturablesEntrada(segs) {
      if (!segs.length) return 0;
      var total = segs.reduce(function (a, d) { return a + Math.min(15, Math.max(1, d)); }, 0);
      return Math.ceil(Math.min(15, total) - 1e-9);
    }
    // Receta de tomas: «Recrear mi video de referencia» necesita un video en la
    // bandeja y Wan 3.0 (el único que recibe el video como video); el servidor
    // lo vuelve a revisar. La descripción de la receta elegida va debajo.
    var receta = document.getElementById('fp-plantilla');
    var recetaDesc = document.getElementById('fp-plantilla-desc');
    function pintarReceta(m, esImagen) {
      if (!receta) return;
      var conVideo = !!(m && m.value === 'wan3' && document.querySelector('#fp-bandeja-wrap #fp-bandeja figure.es-video'));
      Array.prototype.forEach.call(receta.options, function (o) {
        if (o.hasAttribute('data-requiere-video')) o.disabled = !conVideo;
      });
      if (receta.selectedOptions.length && receta.selectedOptions[0].disabled) receta.value = '';
      var o = receta.selectedOptions[0];
      var elegida = !!(o && o.value) && !esImagen;
      recetaDesc.hidden = !elegida;
      recetaDesc.textContent = elegida ? o.dataset.desc + ' ' + T.m01 : '';
    }
    function refrescar() {
      var esImagen = tipoActual() === 'imagen';
      comp.querySelectorAll('[data-solo-video]').forEach(function (el) { el.hidden = esImagen; });
      comp.querySelectorAll('[data-solo-imagen]').forEach(function (el) { el.hidden = !esImagen; });
      var m = modeloActual();
      campoModelo.value = m ? m.value : '';
      ajustarSegunModelo(m, esImagen);
      pintarReceta(m, esImagen);
      var usdMusica = D.tarifaMusica;
      var usd = 0;
      var conSonido = document.getElementById('fp-check-sonido');
      if (m) {
        if (esImagen) {
          usd = parseFloat(m.dataset.usd);
        } else {
          var seg = parseFloat(m.dataset.usdSeg);
          var calidad = document.getElementById('fp-calidad'); if (calidad && calidad.checked && m.value === 'wan3') seg = parseFloat(m.dataset.usdBorrador); // misma tarifa que estimate_video
          if (conSonido && !conSonido.checked) seg -= parseFloat(m.dataset.recargo || '0');
          // Wan 3.0 factura también los segundos de sus videos de referencia (2026-09-30).
          usd = seg * (parseInt(duracion.value, 10) + facturablesEntrada(segundosVideosBandeja(m)))
                + ((musicaSel && musicaSel.value && !esPropia(musicaSel.value)) ? usdMusica : 0);
        }
      }
      // «Generar» (video o imagen) cobra al generar con el texto de la persona;
      // el precio va al lado, con el formato de gastos.formatear: «≈ US$ 1,00».
      // «Crear super prompt» solo existe para video (la imagen nunca pasa por
      // el director): lo oculta [data-solo-video].
      botonGenerar.textContent = esImagen ? T.m02 : T.m03;
      precio.textContent = usd ? '≈ ' + formatearUSD(usd) : '';
      if (pieLogos) pieLogos.hidden = sinAdjuntos();
      pintarFichas(); pintarMusica(); pintarPastillas();
      avisarRefs(m, esImagen);
    }
    form.querySelectorAll('input[name=tipo], input[name=modelo_video], input[name=modelo_imagen]').forEach(function (i) { i.addEventListener('change', refrescar); });
    duracion.addEventListener('change', refrescar);
    form.addEventListener('change', function (e) { if (e.target.name === 'productos_catalogo') refrescar(); });
    ['fp-check-sonido', 'fp-musica', 'fp-calidad', 'fp-mejorar', 'fp-plantilla'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('change', refrescar);
    });
    [formatoVideo, formatoImagen].forEach(function (s) { if (s) s.addEventListener('change', refrescar); });
    document.getElementById('fp-sonido').addEventListener('input', function () { pintarPastillas(); });

    // Duración y formato: los <select> de siempre son la fuente de verdad (el
    // servidor y limitarSelect los leen); el menú dibuja una ficha por opción y
    // la deshabilitada sale tachada.
    // Selector partido: la heurística de idioma confunde el «de» de «data-fichas-de».
    var SEL_FICHAS = '[data-fichas-d' + 'e]';
    function pintarFichas() {
      comp.querySelectorAll(SEL_FICHAS).forEach(function (caja) {
        var sel = document.getElementById(caja.dataset.fichasDe);
        caja.innerHTML = '';
        Array.prototype.forEach.call(sel.options, function (o) {
          var b = document.createElement('button');
          b.type = 'button'; b.className = 'crear-ficha';
          b.textContent = o.textContent.split(' (')[0]; b.title = o.textContent;
          b.dataset.valor = o.value;
          b.disabled = o.disabled || sel.disabled;
          b.setAttribute('aria-pressed', (!sel.disabled && o.value === sel.value) ? 'true' : 'false');
          caja.appendChild(b);
        });
      });
    }
    comp.addEventListener('click', function (e) {
      var ficha = e.target.closest(SEL_FICHAS + ' .crear-ficha');
      if (!ficha || ficha.disabled) return;
      var sel = document.getElementById(ficha.closest(SEL_FICHAS).dataset.fichasDe);
      sel.value = ficha.dataset.valor;
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      cerrarMenus();
    });

    // Música: el <select> #fp-musica sigue siendo la fuente de verdad (lo leen
    // el servidor y mostrarInicio); el menú lo dibuja como «Sin música», fichas
    // de estilos IA y la lista de Mi música.
    function pintarMusica() {
      var caja = document.getElementById('fp-musica-opciones');
      if (!caja) return;
      caja.innerHTML = '';
      function boton(valor, texto, clase) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = clase; b.dataset.musica = valor; b.textContent = texto;
        b.setAttribute('aria-pressed', musicaSel.value === valor ? 'true' : 'false');
        return b;
      }
      caja.appendChild(boton('', T.m04, 'crear-opcion-simple'));
      Array.prototype.forEach.call(musicaSel.querySelectorAll('optgroup'), function (g) {
        var opciones = g.querySelectorAll('option');
        if (g.hidden || !opciones.length) return;
        var propia = g.classList.contains('mm-opciones');
        var t = document.createElement('p');
        t.className = 'crear-menu-titulo';
        t.textContent = propia ? T.m05 : T.m06;
        caja.appendChild(t);
        var lista = document.createElement('div');
        lista.className = propia ? 'crear-opciones' : 'crear-fichas';
        Array.prototype.forEach.call(opciones, function (o) {
          lista.appendChild(boton(o.value, (propia ? '▶ ' : '') + o.textContent, propia ? 'crear-opcion-simple' : 'crear-ficha'));
        });
        caja.appendChild(lista);
      });
    }
    comp.addEventListener('click', function (e) {
      var b = e.target.closest('[data-musica]');
      if (!b) return;
      musicaSel.value = b.dataset.musica;
      musicaSel.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // Cada pastilla dice lo elegido.
    function recortar(t, n) { return t.length > n ? t.slice(0, n - 1) + '…' : t; }
    function pill(id, texto, aviso) {
      var b = document.getElementById(id);
      if (!b) return;
      b.textContent = texto;
      b.classList.toggle('co' + 'n-aviso', !!aviso);  // literal partido: la heurística de idioma confunde "con" en "con-aviso"
    }
    function pintarPastillas() {
      var esImagen = tipoActual() === 'imagen';
      var m = modeloActual();
      var cal = document.getElementById('fp-calidad');
      pill('fp-pill-tipo', esImagen ? T.m07 : T.m08);
      var mej = document.getElementById('fp-mejorar');
      pill('fp-pill-modelo', m ? m.dataset.nombre + (!esImagen && cal && cal.checked ? T.m09 : '')
                               + (!esImagen && mej && mej.checked ? T.m10 : '') : T.m11);
      pill('fp-pill-duracion', '⏱ ' + duracion.value + ' s', parseInt(duracion.value, 10) > 15);
      var selFormato = esImagen ? formatoImagen : formatoVideo;
      pill('fp-pill-formato', (!esImagen && formatoVideo.disabled) ? T.m12 : '▯ ' + selFormato.value);
      var cs = document.getElementById('fp-check-sonido');
      var desc = document.getElementById('fp-sonido').value.trim();
      pill('fp-pill-sonido', !cs.checked ? T.m13 : '🔊 ' + (desc ? recortar(desc, 22) : T.m14));
      var o = musicaSel.selectedOptions[0];
      pill('fp-pill-musica', '🎵 ' + (!musicaSel.value ? T.m04 : recortar(o ? o.textContent : musicaSel.value, 22)));
    }

    // Menús de las pastillas: uno abierto a la vez; se cierran con clic fuera,
    // con Escape o al elegir en los de una sola opción. En el celular suben
    // como hoja desde abajo (CSS) y #crear-velo oscurece el fondo.
    function cerrarMenus() {
      comp.querySelectorAll('.crear-menu').forEach(function (mn) { mn.hidden = true; });
      comp.querySelectorAll('[data-menu]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
      document.body.classList.remove('crear-menu-abierto');
    }
    comp.addEventListener('click', function (e) {
      var b = e.target.closest('[data-menu]');
      if (!b) return;
      var menu = document.getElementById(b.dataset.menu);
      var abrir = menu.hidden;
      cerrarMenus();
      if (!abrir) return;
      menu.hidden = false;
      b.setAttribute('aria-expanded', 'true');
      document.body.classList.add('crear-menu-abierto');
    });
    document.addEventListener('click', function (e) {
      // Un clic que redibujó su propio menú (p. ej. elegir música) deja el
      // target fuera del DOM: eso no es un clic fuera.
      if (!e.target.isConnected || e.target.closest('.crear-pill-zona')) return;
      cerrarMenus();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrarMenus(); });
    form.addEventListener('change', function (e) {
      if (e.target.name === 'tipo' || e.target.name === 'modelo_video' || e.target.name === 'modelo_imagen') cerrarMenus();
    });

    // «+»: pegar link y catálogo.
    document.getElementById('fp-abrir-link').addEventListener('click', function () {
      var caja = document.getElementById('fp-link-caja');
      caja.hidden = !caja.hidden;
      if (!caja.hidden) caja.querySelector('input').focus();
    });
    var dlgCatalogo = document.getElementById('fp-catalogo');
    var catElegidos = document.getElementById('fp-catalogo-elegidos');
    document.getElementById('fp-abrir-catalogo').addEventListener('click', function () {
      cerrarMenus();
      dlgCatalogo.showModal();
      dlgCatalogo.dispatchEvent(new Event('catalogo-abrir'));
    });
    var presionEnFondo = false;
    dlgCatalogo.addEventListener('mousedown', function (e) { presionEnFondo = e.target === dlgCatalogo; });
    dlgCatalogo.addEventListener('click', function (e) {
      if (e.target.closest('[data-cerrar-catalogo]') || (e.target === dlgCatalogo && presionEnFondo)) dlgCatalogo.close();
      presionEnFondo = false;
    });
    dlgCatalogo.addEventListener('close', function () { pintarCatalogo(); refrescar(); });
    // Lo marcado en el catálogo se ve en la tarjeta como las referencias
    // subidas; la × lo desmarca.
    function pintarCatalogo() {
      var marcados = form.querySelectorAll('input[name=productos_catalogo]:checked');
      catElegidos.innerHTML = '';
      marcados.forEach(function (cb) {
        var fig = document.createElement('figure');
        fig.className = 'crear-ref';
        var foto = cb.parentElement.querySelector('img');
        var img = document.createElement('img');
        img.src = foto ? foto.src : ''; img.alt = '';
        var cap = document.createElement('figcaption');
        cap.textContent = cb.dataset.nombre;
        var x = document.createElement('button');
        x.type = 'button'; x.className = 'crear-ref-quitar'; x.textContent = '×';
        x.setAttribute('aria-label', T.m15.replace('__REF__', cb.dataset.nombre));
        x.addEventListener('click', function () {
          cb.checked = false;
          cb.dispatchEvent(new Event('change', { bubbles: true }));
          pintarCatalogo();
        });
        fig.appendChild(img); fig.appendChild(cap); fig.appendChild(x);
        catElegidos.appendChild(fig);
      });
      catElegidos.hidden = !marcados.length;
    }
    form.addEventListener('catalogo-cargado', function () { pintarCatalogo(); refrescar(); });
    pintarCatalogo();
    refrescar();

    // «Crear con este producto» desde el Catálogo: llega el color marcado, en
    // la misma precarga de arriba (una vez y solo en este proyecto, _prefill_para).
    if (prefill && prefill.productos_catalogo) {
      prefill.productos_catalogo.forEach(function (v) {
        var cb = form.querySelector('input[name=productos_catalogo][value="' + String(v).replace(/"/g, '') + '"]');
        if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true})); }
      });
      pintarCatalogo();
      refrescar();
    }

    // Chips @Imagen N / @Video N de la bandeja: insertan la etiqueta en el texto.
    var chips = document.getElementById('fp-etiquetas');
    var texto = document.getElementById('fp-texto');
    // «Sugerir» sonido de la escena: Claude describe qué se oye (centavos, solo texto).
    var btnSugerir = document.getElementById('fp-sugerir-sonido');
    if (btnSugerir) btnSugerir.addEventListener('click', function () {
      var enfoque = form.querySelector('input[name=productos_catalogo][value^="personaje:"]:checked') ? 'persona' : (sinAdjuntos() ? 'libre' : 'producto');
      btnSugerir.disabled = true; btnSugerir.textContent = T.m16;
      fetch(btnSugerir.dataset.url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'},
                                     body: JSON.stringify({escena: texto.value, enfoque: enfoque})})
        .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); })
        .then(function (res) {
          if (res.ok && res.j.sonido) { document.getElementById('fp-sonido').value = res.j.sonido; pintarPastillas(); }
          else alert(res.j.error || T.m17);
        })
        .catch(function () { alert(T.m17); })
        .finally(function () { btnSugerir.disabled = false; btnSugerir.textContent = T.m18; });
    });
    function insertar(etiqueta) {
      var v = texto.value, ini = texto.selectionStart || v.length;
      var sep = (ini > 0 && !/\s$/.test(v.slice(0, ini))) ? ' ' : '';
      texto.value = v.slice(0, ini) + sep + etiqueta + ' ' + v.slice(ini);
      texto.focus();
    }
    function pintarChips(etiquetas) {
      chips.innerHTML = '';
      etiquetas.forEach(function (et) {
        var chip = document.createElement('button');
        chip.type = 'button'; chip.className = 'maniqui-preset'; chip.textContent = et;
        chip.addEventListener('click', function () { insertar(et); });
        chips.appendChild(chip);
      });
    }
    pintarChips(D.etiquetas);

    // --- Bandeja sin recargas: subir con progreso, link, quitar, vaciar ---
    var wrap = document.getElementById('fp-bandeja-wrap');
    var subida = document.getElementById('fp-subida');
    var subidaBarra = document.getElementById('fp-subida-barra');
    var subidaTexto = document.getElementById('fp-subida-texto');
    var pollLink = null;
    function aplicar(d) {
      if (d.html !== undefined) { wrap.innerHTML = d.html; engancharBandeja(); refrescar(); }
      if (d.etiquetas) pintarChips(d.etiquetas);
      if (d.error) { subidaTexto.textContent = d.error; subida.hidden = false; subidaBarra.style.width = '0%'; }
      vigilarLink();
    }
    function enviar(url, body) {
      return fetch(url, { method: 'POST', body: body, headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.json(); }).then(aplicar)
        .catch(function () { subidaTexto.textContent = T.m19; subida.hidden = false; });
    }
    function engancharBandeja() {
      wrap.querySelectorAll('form[data-fp]').forEach(function (f) {
        f.addEventListener('submit', function (e) {
          e.preventDefault();
          if (f.dataset.confirm && !confirm(f.dataset.confirm)) return;
          enviar(f.action, new FormData(f));
        });
      });
      var btn = document.getElementById('fp-describir');
      if (btn) btn.addEventListener('click', describir);
    }
    // Si hay un link descargándose, consultar la bandeja cada 3 s hasta que aparezca.
    function vigilarLink() {
      var marca = wrap.querySelector('.fp-link-descargando');
      if (pollLink) { clearInterval(pollLink); pollLink = null; }
      if (!marca) return;
      pollLink = setInterval(function () {
        fetch(D.urlBandeja, { headers: { 'X-Requested-With': 'fetch' } })
          .then(function (r) { return r.json(); })
          .then(function (d) { if (!/fp-link-descargando/.test(d.html)) { clearInterval(pollLink); pollLink = null; aplicar(d); } })
          .catch(function () {});
      }, 3000);
    }
    var inputArchivos = document.getElementById('fp-input-archivos');
    var formSubir = document.getElementById('fp-form-subir');
    inputArchivos.addEventListener('change', function () {
      if (!inputArchivos.files.length) return;
      cerrarMenus();
      var fd = new FormData(formSubir);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', formSubir.action);
      xhr.setRequestHeader('X-Requested-With', 'fetch');
      subida.hidden = false; subidaBarra.style.width = '0%';
      subidaTexto.textContent = T.m20 + ' ' + inputArchivos.files.length + ' ' + T.m21;
      xhr.upload.onprogress = function (ev) {
        if (!ev.lengthComputable) return;
        var pct = Math.round(ev.loaded * 100 / ev.total);
        subidaBarra.style.width = pct + '%';
        subidaTexto.textContent = pct < 100 ? (T.m22 + ' ' + pct + '%') : T.m23;
      };
      xhr.onload = function () {
        try { var d = JSON.parse(xhr.responseText); aplicar(d); subida.hidden = !d.error; }
        catch (e) { subidaTexto.textContent = T.m24; }
        inputArchivos.value = '';
      };
      xhr.onerror = function () { subidaTexto.textContent = T.m25; };
      xhr.send(fd);
    });
    // Arrastrar archivos sobre la tarjeta = «Subir imágenes o videos».
    function traeArchivos(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') !== -1; }
    ['dragenter', 'dragover'].forEach(function (t) {
      comp.addEventListener(t, function (e) {
        if (!traeArchivos(e)) return;
        e.preventDefault();
        comp.classList.add('soltando');
      });
    });
    comp.addEventListener('dragleave', function (e) {
      if (!comp.contains(e.relatedTarget)) comp.classList.remove('soltando');
    });
    comp.addEventListener('drop', function (e) {
      comp.classList.remove('soltando');
      if (!traeArchivos(e) || !e.dataTransfer.files.length) return;
      e.preventDefault();
      inputArchivos.files = e.dataTransfer.files;
      inputArchivos.dispatchEvent(new Event('change'));
    });
    // El campo del link vive en el menú «+» pero su dueño es #fp-form-link
    // (atributo form=): se lee por form.elements, no por querySelector.
    var formLink = document.getElementById('fp-form-link');
    formLink.addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(formLink);
      formLink.elements.link.value = '';
      document.getElementById('fp-link-caja').hidden = true;
      cerrarMenus();
      enviar(formLink.action, fd);
    });

    // Describir con IA: Claude mira las referencias y propone el texto.
    function describir() {
      var btnDescribir = document.getElementById('fp-describir');
      var estadoDescribir = document.getElementById('fp-describir-estado');
      btnDescribir.disabled = true; estadoDescribir.textContent = T.m26;
      fetch(D.urlDescribir, { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ok) { texto.value = d.texto; texto.focus(); estadoDescribir.textContent = T.m27; }
          else { estadoDescribir.textContent = d.error || T.m28; }
        })
        .catch(function () { estadoDescribir.textContent = T.m29; })
        .finally(function () { btnDescribir.disabled = false; });
    }

    // --- Mi música: elegir, subir, crear con ElevenLabs, borrar (sin recargar) ---
    function mostrarInicio() {
      var o = musicaSel.selectedOptions[0];
      var propia = !!(o && esPropia(o.value));
      inicioWrap.hidden = !propia;
      if (propia) {
        if (audioPrev.dataset.src !== o.dataset.url) { audioPrev.src = o.dataset.url; audioPrev.dataset.src = o.dataset.url; }
        inicioInput.max = Math.max(0, Math.floor(parseFloat(o.dataset.duracion || '0')) - 1);
      } else {
        audioPrev.pause();
      }
    }
    musicaSel.addEventListener('change', function () { inicioInput.value = 0; mostrarInicio(); refrescar(); });
    document.getElementById('fp-musica-usar').addEventListener('click', function () {
      inicioInput.value = Math.floor(audioPrev.currentTime || 0);
    });
    // Los selectores de «Mi música» de toda la página: el de Crear y el de
    // «Producir finales» del detalle abierto en Final edition (el detalle
    // llega por fetch con la lista al día; este repinta el que ya está abierto).
    function pintarCanciones(canciones) {
      var grupos = Array.prototype.slice.call(document.querySelectorAll('optgroup.mm-opciones'));
      document.querySelectorAll('template.generado-detalle').forEach(function (t) {
        grupos = grupos.concat(Array.prototype.slice.call(t.content.querySelectorAll('optgroup.mm-opciones')));
      });
      grupos.forEach(function (g) {
        var sel = g.parentElement, elegido = sel ? sel.value : '';
        g.innerHTML = '';
        canciones.forEach(function (c) {
          var o = document.createElement('option');
          o.value = 'mat:' + c.id; o.textContent = c.nombre; o.dataset.url = c.url; o.dataset.duracion = c.duracion_s;
          g.appendChild(o);
        });
        g.hidden = !canciones.length;
        if (sel && elegido) { sel.value = elegido; if (sel.selectedIndex < 0) sel.value = ''; }
      });
    }
    function aplicarMusica(d, elegirNuevo) {
      if (d.html !== undefined) mmWrap.innerHTML = d.html;
      if (d.canciones) pintarCanciones(d.canciones);
      if (d.canciones && !d.deOtroPanel) {
        try { document.dispatchEvent(new CustomEvent('mi-musica:cambio', {detail: {origen: 'mm', canciones: d.canciones}})); } catch (e) {}
      }
      if (elegirNuevo && d.nuevo_id) { musicaSel.value = 'mat:' + d.nuevo_id; inicioInput.value = 0; }
      mostrarInicio(); refrescar();
      var err = document.getElementById('mm-error');
      if (d.error && err) { err.textContent = d.error; err.hidden = false; }
      var aviso = document.getElementById('mm-subida');
      if (d.mensaje && aviso) { aviso.textContent = d.mensaje; aviso.hidden = false; }
      vigilarCancion();
    }
    function enviarMusica(url, body) {
      return fetch(url, {method: 'POST', body: body, headers: {'X-Requested-With': 'fetch'}})
        .then(function (r) { return r.json(); })
        .then(function (d) { aplicarMusica(d, false); })
        .catch(function () { aplicarMusica({error: T.m19}, false); });
    }
    // La canción de ElevenLabs se crea en el worker: se consulta su estado y al
    // terminar se refresca solo el panel (recargar borraría lo que ya escribiste).
    function vigilarCancion() {
      var barra = document.getElementById('mm-progreso');
      if (!barra || barra.dataset.vigilando) return;
      barra.dataset.vigilando = '1';
      var t = setInterval(function () {
        fetch(barra.dataset.estado).then(function (r) { return r.json(); }).then(function (e) {
          if (e.estado === 'en_progreso') return;
          clearInterval(t);
          fetch(document.getElementById('mm-panel').dataset.urlLista, {headers: {'X-Requested-With': 'fetch'}})
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (e.estado === 'error') d.error = e.mensaje || T.m30;
              else d.mensaje = T.m31;
              aplicarMusica(d, false);
            });
        }).catch(function () {});
      }, 4000);
    }
    mmWrap.addEventListener('change', function (e) {
      if (e.target.id !== 'mm-archivo' || !e.target.files.length) return;
      var fd = new FormData();
      fd.append('cancion', e.target.files[0]);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', document.getElementById('mm-panel').dataset.urlSubir);
      xhr.setRequestHeader('X-Requested-With', 'fetch');
      var aviso = document.getElementById('mm-subida');
      aviso.hidden = false; aviso.textContent = T.m32;
      xhr.upload.onprogress = function (ev) {
        if (!ev.lengthComputable) return;
        var p = Math.round(ev.loaded * 100 / ev.total);
        aviso.textContent = p < 100 ? (T.m22 + ' ' + p + '%') : T.m33;
      };
      xhr.onload = function () {
        try { aplicarMusica(JSON.parse(xhr.responseText), true); }
        catch (err) { aviso.textContent = T.m24; }
      };
      xhr.onerror = function () { aviso.textContent = T.m25; };
      xhr.send(fd);
    });
    mmWrap.addEventListener('click', function (e) {
      if (e.target.id === 'mm-abrir-crear') {
        var caja = document.getElementById('mm-crear');
        caja.hidden = !caja.hidden;
        if (!caja.hidden) document.getElementById('mm-prompt').focus();
        return;
      }
      if (e.target.id === 'mm-crear-btn') {
        var prompt = document.getElementById('mm-prompt');
        if (!prompt.value.trim()) { prompt.focus(); return; }
        var fd = new FormData();
        fd.append('prompt', prompt.value);
        fd.append('instrumental', document.getElementById('mm-instrumental').checked ? 'si' : 'no');
        e.target.disabled = true;
        enviarMusica(document.getElementById('mm-panel').dataset.urlCrear, fd);
        return;
      }
      var borrar = e.target.closest('.mm-borrar');
      var mensajeBorrar = T.m34.replace('__NOMBRE__', borrar ? borrar.dataset.nombre : '');
      if (borrar && confirm(mensajeBorrar)) {
        enviarMusica(borrar.dataset.url, new FormData());
      }
    });
    mostrarInicio();
    vigilarCancion();

    // Una canción subida desde Crear › Audios también entra a este panel.
    document.addEventListener('mi-musica:cambio', function (ev) {
      var d = ev.detail || {};
      if (d.origen === 'mm' || !d.canciones) return;
      aplicarMusica({html: d.html, canciones: d.canciones, deOtroPanel: true}, false);
    });

    // Enter en un campo de una línea NO envía: «Generar» cobra y solo se lanza
    // con su botón (antes, Enter en «Sonido de la escena» generaba el video).
    // El link (#fp-form-link) sí se agrega con Enter: su dueño es otro
    // formulario y no gasta.
    form.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || e.isComposing) return;
      if (e.target.tagName === 'INPUT' && e.target.form === form) e.preventDefault();
    });

    engancharBandeja();

    // Validación en sitio: el error se muestra en rojo junto al cuadro, no arriba.
    // Solo el texto es obligatorio: referencias y catálogo son opcionales.
    var textoError = document.getElementById('fp-texto-error');
    form.addEventListener('submit', function (e) {
      var vacio = !texto.value.trim();
      texto.classList.toggle('co' + 'n-error', vacio);  // literal partido: heurística de idioma confunde "con" en "con-error"
      textoError.hidden = !vacio;
      if (vacio) { e.preventDefault(); texto.scrollIntoView({block: 'center'}); texto.focus(); }
    });
    texto.addEventListener('input', function () {
      if (texto.value.trim()) { texto.classList.remove('co' + 'n-error'); textoError.hidden = true; }
    });

    // --- Referencias que el modelo elegido no usa (incidente 2026-09-28) ---
    // Misma cuenta que providers/flowplus_modelos.referencias_de_mas: Wan
    // recibe imágenes y videos aparte; en los demás el video entra por su
    // fotograma; Seedance usa solo la primera. El servidor vuelve a comprobarlo
    // antes de cobrar; esto solo evita el viaje.
    var avisoRefs = document.getElementById('fp-aviso-refs');
    var AVISO_REFS = T.m35;
    var AVISO_REFS_UNA = T.m36;
    var refsSobrantes = [];
    var bloqueoDuracion = '';
    // Wan 3.0 con videos de referencia (incidente 2026-09-30, Forja): juntos
    // hasta 15 s, y entrada + salida hasta 30 s (flowplus_modelos.problema_duracion).
    var AVISO_VIDEOS_LARGOS = T.m37;
    var AVISO_TOTAL_VIDEOS = T.m38;
    function problemaDuracion(m, esImagen) {
      if (esImagen) return '';
      var segs = segundosVideosBandeja(m);
      if (!segs.length) return '';
      var total = Math.round(segs.reduce(function (a, d) { return a + d; }, 0) * 100) / 100;
      var sTxt = (Math.round(total * 10) / 10).toLocaleString(document.documentElement.lang || undefined);
      var maxVidS = parseFloat(m.dataset.maxVideosS || '0');
      if (maxVidS && total > maxVidS) {
        return AVISO_VIDEOS_LARGOS.replace('__S__', sTxt).replace('__MODELO__', m.dataset.nombre).replace('__MAX__', String(maxVidS));
      }
      var maxTotal = parseFloat(m.dataset.maxTotal);
      var maxima = Math.floor(maxTotal - total);
      if (parseInt(duracion.value, 10) > maxima) {
        return AVISO_TOTAL_VIDEOS.replace('__MODELO__', m.dataset.nombre).replace('__TOTAL__', String(maxTotal))
          .replace('__S__', sTxt).replace('__MAX__', String(maxima));
      }
      return '';
    }
    function etiquetaDe(fig) {
      var cap = fig.querySelector('figcaption');
      return cap ? cap.textContent.split(' · ')[0].trim() : '';
    }
    function refsDeMas(m, esImagen) {
      var maxImg = parseInt(m.dataset.max || '0', 10);
      var maxVid = esImagen ? 0 : parseInt(m.dataset.maxVideos || '0', 10);
      var nImg = 0, nVid = 0, sobran = [], primera = '';
      Array.prototype.forEach.call(document.querySelectorAll('#fp-bandeja-wrap #fp-bandeja figure.crear-ref'), function (fig) {
        var esVideo = fig.classList.contains('es-video') && maxVid > 0;
        var cabe;
        if (esVideo) { nVid++; cabe = nVid <= maxVid; } else { nImg++; cabe = nImg <= maxImg; }
        if (!cabe) sobran.push(etiquetaDe(fig)); else if (!primera) primera = etiquetaDe(fig);
      });
      form.querySelectorAll('input[name=productos_catalogo]:checked').forEach(function (cb) {
        var fotos = /^personaje:/.test(cb.value) ? 3 : 1;   // un personaje entra con hasta 3 fotos
        for (var i = 0; i < fotos; i++) {
          nImg++;
          if (nImg > maxImg) { sobran.push(cb.dataset.nombre || cb.value); break; }
          if (!primera) primera = cb.dataset.nombre || cb.value;
        }
      });
      return { sobran: sobran, primera: primera, maxImg: maxImg };
    }
    function avisarRefs(m, esImagen) {
      refsSobrantes = [];
      bloqueoDuracion = '';
      if (!avisoRefs) return;
      var pillModelo = document.getElementById('fp-pill-modelo');
      if (!m) { avisoRefs.hidden = true; return; }
      var r = refsDeMas(m, esImagen);
      refsSobrantes = r.sobran;
      bloqueoDuracion = problemaDuracion(m, esImagen);
      var mensajes = [];
      if (r.sobran.length) {
        var plantilla = r.maxImg === 1 ? AVISO_REFS_UNA : AVISO_REFS;
        mensajes.push(plantilla.replace('__MODELO__', m.dataset.nombre).replace('__N__', String(r.maxImg))
          .replace('__PRIMERA__', r.primera).replace('__SOBRAN__', r.sobran.join(', ')));
        if (pillModelo) pillModelo.classList.add('co' + 'n-aviso');
      }
      if (bloqueoDuracion) {
        mensajes.push(bloqueoDuracion);
        var pillDuracion = document.getElementById('fp-pill-duracion');
        if (pillDuracion) pillDuracion.classList.add('co' + 'n-aviso');
      }
      avisoRefs.textContent = mensajes.join(' ');
      avisoRefs.hidden = !mensajes.length;
    }
    form.addEventListener('submit', function (e) {
      if (refsSobrantes.length || bloqueoDuracion) { e.preventDefault(); avisoRefs.hidden = false; avisoRefs.scrollIntoView({block: 'center'}); }
    });
    avisarRefs(modeloActual(), tipoActual() === 'imagen');

    // --- «Empezar de cero» (sin variables quemadas, 2026-09-28) ---
    // form.reset() vuelve a lo que pintó el servidor (los valores del
    // proyecto), no a lo que dejó la precarga de «Editar y crear otra».
    var btnEmpezar = document.getElementById('fp-empezar');
    if (btnEmpezar) btnEmpezar.addEventListener('click', function () {
      var hayRefs = !!document.querySelector('#fp-bandeja-wrap #fp-bandeja');
      var hayAlgo = hayRefs || !!texto.value.trim() || !!form.querySelector('input[name=productos_catalogo]:checked');
      if (hayAlgo && !confirm(T.m39)) return;
      form.reset();
      form.querySelectorAll('input[name=productos_catalogo]:checked').forEach(function (cb) { cb.checked = false; });
      form.querySelectorAll('[data-sucio]').forEach(function (el) { delete el.dataset.sucio; });
      texto.classList.remove('co' + 'n-error'); textoError.hidden = true;
      pintarCatalogo(); refrescar();
      if (hayRefs) enviar(D.urlVaciar, new FormData());
      texto.focus();
    });
  })();

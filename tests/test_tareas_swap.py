import pytest


class _Archivo:
    """Sustituto de werkzeug FileStorage: solo filename y save()."""

    def __init__(self, filename, contenido=b"jpg"):
        self.filename = filename
        self._contenido = contenido

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self._contenido)


def test_registro_contiene_swap_generar(base_temporal):
    import tareas
    tareas.cargar_todas()
    import tareas.swap as sw
    assert tareas.REGISTRO["swap_generar"] is sw.ejecutar
    assert sorted(tareas.REGISTRO) == [
        "catalogo_importar",
        "exp_avanzar_todos", "exp_decidir", "exp_decidir_todos", "exp_lanzar", "exp_refrescar", "exp_refrescar_todos",
        "final_guion", "final_producir",
        "flowplus_imagen", "flowplus_video", "meta_publicar", "meta_refrescar", "organico_publicar", "producto_vincular",
        "sprint_analizar_referencia", "sprint_empaquetar", "sprint_proponer_ideas", "sprint_qa_pendientes", "sprint_qa_pieza",
        "sprint_referencia_link", "sprint_sugerir_personas", "swap_generar",
        "tienda_sync_pedidos", "tienda_sync_pedidos_todas", "tienda_sync_productos", "tienda_sync_productos_todas",
    ]


def test_interrumpida_marca_el_swap_en_error(base_temporal, monkeypatch, tmp_path):
    import swaps as swaps_mod
    import tareas
    import tareas.swap as sw
    assert tareas.AL_INTERRUMPIR["swap_generar"] is sw.interrumpida
    monkeypatch.setattr(swaps_mod, "_path", lambda c: str(tmp_path / f"swaps_{c}.json"))
    sid = swaps_mod.crear("acme", str(tmp_path / "foto.jpg"), "p1", "9:16")
    swaps_mod.actualizar("acme", sid, estado="generando")
    sw.interrumpida({"payload": {"cliente": "acme", "swap_id": sid}}, "Se interrumpió.")
    e = swaps_mod.cargar("acme")[sid]
    assert e["estado"] == "error" and e["error"] == "Se interrumpió."


def test_etapas_mismas_que_dashboard():
    import dashboard
    import tareas.swap as sw
    assert dashboard.ETAPAS_SWAP_FOTO is sw.ETAPAS_SWAP_FOTO
    assert dashboard.ETAPAS_SWAP_VIDEO is sw.ETAPAS_SWAP_VIDEO
    assert dashboard.ETAPAS_SWAP_FOTO_MEJORADA is sw.ETAPAS_SWAP_FOTO_MEJORADA
    assert sw.ETAPAS_SWAP_FOTO == [(sw.ETAPA_PREPARAR_FOTO, 10), (sw.ETAPA_MODELO, 70), (sw.ETAPA_GUARDAR, 20)]
    assert sw.ETAPA_MODELO == dashboard.ETAPA_MODELO


def test_lanzar_swap_encola(base_temporal, monkeypatch, tmp_path):
    import dashboard
    monkeypatch.setattr(dashboard, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.aspect_ratio_mod, "detectar_gemini", lambda p: "9:16")
    creado = {}

    def _crear(cliente, foto_local, producto_id, aspect_ratio, proveedor, tipo="foto"):
        creado.update(cliente=cliente, foto_local=foto_local, producto_id=producto_id,
                      aspect_ratio=aspect_ratio, proveedor=proveedor, tipo=tipo)
        return "swap_x"
    monkeypatch.setattr(dashboard.swaps_mod, "crear", _crear)
    capturado = {}

    def _encolar(job_id, tipo, payload, **kw):
        capturado.update(job_id=job_id, tipo=tipo, payload=payload, **kw)
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)

    producto = {"id": "p1", "referencias": [], "descripcion": "zapato"}
    ok = dashboard._lanzar_swap("acme", _Archivo("foto.jpg"), producto, "p1", "nano_banana", "seedance25_edit", False)
    assert ok is True
    assert capturado["tipo"] == "swap_generar"
    assert capturado["job_id"] == "acme__swap_x__swap"
    assert capturado["max_intentos"] == 1
    assert capturado["cliente"] == "acme"
    assert capturado["duracion_estimada"] == 20
    assert capturado["etapas"] == dashboard.ETAPAS_SWAP_FOTO
    assert capturado["payload"] == {
        "cliente": "acme", "swap_id": "swap_x", "producto_id": "p1",
        "proveedor": "nano_banana", "tipo": "foto", "mejorar_calidad": False,
    }
    # el archivo quedó guardado bajo el BASE_DIR parcheado y el swap se creó como antes
    assert creado["aspect_ratio"] == "9:16" and creado["tipo"] == "foto" and creado["proveedor"] == "nano_banana"
    assert creado["foto_local"].startswith(str(tmp_path / "salidas" / "acme" / "swaps_subidas"))
    assert open(creado["foto_local"], "rb").read() == b"jpg"


def test_lanzar_swap_video_etapas_y_sin_mejora(base_temporal, monkeypatch, tmp_path):
    import dashboard
    monkeypatch.setattr(dashboard, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.swaps_mod, "crear", lambda *a, **k: "swap_v")
    capturado = {}
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: capturado.update(payload=payload, **kw) or True)
    producto = {"id": "p1", "referencias": [], "descripcion": "zapato"}
    dashboard._lanzar_swap("acme", _Archivo("clip.mp4"), producto, "p1", "nano_banana", "seedance25_edit", True)
    assert capturado["etapas"] == dashboard.ETAPAS_SWAP_VIDEO
    assert capturado["duracion_estimada"] == 380
    p = capturado["payload"]
    assert p["tipo"] == "video" and p["proveedor"] == "seedance25_edit" and p["mejorar_calidad"] is False


def test_ejecutar_sin_producto_marca_error(base_temporal, monkeypatch):
    import tareas.swap as sw
    monkeypatch.setattr(sw.swaps_mod, "cargar", lambda c: {
        "swap_x": {"foto_original_local": "/no/existe.jpg", "aspect_ratio": "9:16", "tipo": "foto"},
    })
    monkeypatch.setattr(sw.catalogo_productos, "encontrar", lambda c, pid: None)
    capturado = {}
    monkeypatch.setattr(sw.swaps_mod, "actualizar", lambda c, sid, **k: capturado.update(cliente=c, swap_id=sid, **k))
    monkeypatch.setattr(sw.bitacora, "registrar", lambda *a, **k: None)
    msg = sw.ejecutar({"job_id": "acme__swap_x__swap", "payload": {
        "cliente": "acme", "swap_id": "swap_x", "producto_id": "p_borrado",
        "proveedor": "nano_banana", "tipo": "foto", "mejorar_calidad": False,
    }})
    assert capturado["swap_id"] == "swap_x" and capturado["estado"] == "error"
    assert "producto" in capturado["error"].lower()
    assert isinstance(msg, str)


def test_ejecutar_foto_nano_banana_con_proveedor_falso(base_temporal, monkeypatch, tmp_path):
    """Recorrido completo de la rama foto/nano_banana con todo lo externo parcheado."""
    import tareas.swap as sw
    monkeypatch.setattr(sw, "BASE_DIR", str(tmp_path))
    foto = tmp_path / "orig.jpg"
    foto.write_bytes(b"jpg")
    monkeypatch.setattr(sw.swaps_mod, "cargar", lambda c: {
        "swap_x": {"foto_original_local": str(foto), "aspect_ratio": "9:16", "tipo": "foto"},
    })
    monkeypatch.setattr(sw.catalogo_productos, "encontrar",
                        lambda c, pid: {"id": pid, "tipo": "calzado", "mapa_texto": None,
                                        "referencias": ["/r/a.jpg"], "descripcion": "zapato"})
    monkeypatch.setattr(sw.marca_mod, "negative_prompt_efectivo", lambda c: "")
    monkeypatch.setattr(sw.nano_banana_client, "swap_producto", lambda *a, **k: b"png")
    monkeypatch.setattr(sw.nano_banana_client, "estimate_image", lambda: {"credits": None, "usd": 0.04})
    monkeypatch.setattr(sw.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(sw.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(sw.marca_mod, "cargar_root", lambda c: {"invariants": []})
    actualizaciones = []
    monkeypatch.setattr(sw.swaps_mod, "actualizar", lambda c, sid, **k: actualizaciones.append((sid, k)))
    reportes = []
    monkeypatch.setattr(sw.trabajos, "reportar", lambda job_id, **k: reportes.append(k))

    msg = sw.ejecutar({"job_id": "acme__swap_x__swap", "payload": {
        "cliente": "acme", "swap_id": "swap_x", "producto_id": "p1",
        "proveedor": "nano_banana", "tipo": "foto", "mejorar_calidad": False,
    }})
    assert msg == "Swap listo."
    listo = [k for sid, k in actualizaciones if k.get("estado") == "listo"][0]
    assert listo["resultado_url"] == "https://r2/clientes/acme/swaps/swap_x.png"
    assert listo["usd"] == 0.04 and listo["error_storage"] is None
    assert (tmp_path / "salidas" / "acme" / "swaps" / "swap_x.png").read_bytes() == b"png"
    assert [k for sid, k in actualizaciones if k.get("evaluacion_estado")] == [{"evaluacion_estado": "sin_matriz"}]
    assert [r["etapa"] for r in reportes if "etapa" in r] == [sw.ETAPA_PREPARAR_FOTO, sw.ETAPA_MODELO, sw.ETAPA_GUARDAR]

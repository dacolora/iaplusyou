"""PND-295 (2), 2026-10-12: las claves de R2 que no se pudieron borrar al soltar datos de Meta se anotan y se reintentan.

Soltar una cuenta de Meta borra primero las filas y después sus copias en R2 (`creativo.borrar_copias`,
`analisis.borrar_claves`). Si R2 falla en ese momento, las claves ya no salen de ninguna fila: se anotan en kv
`r2:borrar_pendientes` (`storage.r2_pendientes`, único escritor) y la limpieza diaria `meta_rend_limpiar` las reintenta.
R2 nunca se llama de verdad."""
import logging

import pytest

from storage import r2_pendientes, r2_uploader

BASE = "clientes/acme/rendimiento"


def test_anotar_quita_repetidas_y_conserva_el_orden(base_temporal):
    assert r2_pendientes.pendientes() == []
    r2_pendientes.anotar([f"{BASE}/a1_9.jpg", f"{BASE}/a1_9.mp4", f"{BASE}/a1_9.jpg"])
    r2_pendientes.anotar([f"{BASE}/a1_9.mp4", f"{BASE}/a2_9.jpg", "", None])
    assert r2_pendientes.pendientes() == [f"{BASE}/a1_9.jpg", f"{BASE}/a1_9.mp4", f"{BASE}/a2_9.jpg"]
    r2_pendientes.anotar([])                                       # sin claves no toca nada
    assert len(r2_pendientes.pendientes()) == 3


def test_anotar_con_mas_del_tope_guarda_las_mas_nuevas_y_avisa_cuantas_sin_decir_cuales(base_temporal, monkeypatch,
                                                                                          caplog):
    assert r2_pendientes.MAX_PENDIENTES == 5000
    monkeypatch.setattr(r2_pendientes, "MAX_PENDIENTES", 3)
    r2_pendientes.anotar([f"{BASE}/a1_9.jpg", f"{BASE}/a2_9.jpg"])
    with caplog.at_level(logging.WARNING):
        r2_pendientes.anotar([f"{BASE}/a3_9.jpg", f"{BASE}/a4_9.jpg", f"{BASE}/a5_9.jpg"])
    assert r2_pendientes.pendientes() == [f"{BASE}/a3_9.jpg", f"{BASE}/a4_9.jpg", f"{BASE}/a5_9.jpg"]
    assert "2" in caplog.text and "clientes/" not in caplog.text        # cuántas, nunca las claves (cliente y anuncio)


def test_anotar_toma_el_candado_antes_de_leer(base_temporal, escritor_en_medio):
    """Sin el candado, otro proceso que anota entre la lectura y la escritura perdía sus claves."""
    otro = escritor_en_medio("SELECT kv.valor", "insert into kv(clave, valor, actualizado_en) values "
                                                "('r2:borrar_pendientes', '[\"ajena\"]', 'ahora')")
    r2_pendientes.anotar([f"{BASE}/a1_9.jpg"])
    assert otro["resultado"].startswith("bloqueado")
    assert r2_pendientes.pendientes() == [f"{BASE}/a1_9.jpg"]


def test_anotar_nunca_lanza(base_temporal, monkeypatch, caplog):
    """La llaman `borrar_copias` y `borrar_claves`, que prometen no lanzar: con la base caída solo avisa el tipo."""
    def _caida():
        raise RuntimeError(f"no abre {BASE}/a1_9.jpg")
    monkeypatch.setattr(r2_pendientes.db, "conectar", _caida)
    with caplog.at_level(logging.WARNING):
        assert r2_pendientes.anotar([f"{BASE}/a1_9.jpg"]) is False
    assert "RuntimeError" in caplog.text and "clientes/" not in caplog.text


def test_reintentar_deja_solo_las_que_siguen_fallando(base_temporal, monkeypatch):
    r2_pendientes.anotar(["a", "b", "c"])
    pedidas = []

    def _detalle(claves):
        pedidas.append(list(claves))
        return 2, [("b", "EndpointConnectionError")]
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _detalle)
    assert r2_pendientes.reintentar() == (2, 1)
    assert pedidas == [["a", "b", "c"]] and r2_pendientes.pendientes() == ["b"]


def test_reintentar_no_pierde_una_clave_anotada_mientras_borraba(base_temporal, monkeypatch):
    r2_pendientes.anotar(["a", "b"])

    def _detalle(claves):
        r2_pendientes.anotar(["nueva", "a"])         # otro proceso suelta una cuenta y R2 le falla en ese momento
        return len(claves), []
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _detalle)
    assert r2_pendientes.reintentar() == (2, 1)
    assert r2_pendientes.pendientes() == ["nueva"]


def test_reintentar_toma_el_candado_antes_de_releer(base_temporal, monkeypatch, escritor_en_medio):
    r2_pendientes.anotar(["a", "b"])
    otro = {}

    def _detalle(claves):
        # Desde aquí, justo antes de la próxima lectura, otro proceso escribe la lista: tiene que esperar al candado.
        otro["estado"] = escritor_en_medio("SELECT kv.valor", "update kv set valor='[\"a\", \"b\", \"ajena\"]' "
                                                               "where clave='r2:borrar_pendientes'")
        return len(claves), []
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _detalle)
    assert r2_pendientes.reintentar() == (2, 0)
    assert otro["estado"]["resultado"].startswith("bloqueado") and r2_pendientes.pendientes() == []


def test_reintentar_sin_r2_o_con_la_base_caida_no_lanza(base_temporal, monkeypatch, caplog):
    r2_pendientes.anotar(["a"])

    def _sin_r2(claves):
        raise RuntimeError("Faltan R2_ACCOUNT_ID")
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _sin_r2)
    with caplog.at_level(logging.WARNING):
        assert r2_pendientes.reintentar() == (0, 1)
    assert r2_pendientes.pendientes() == ["a"] and "RuntimeError" in caplog.text and "R2_ACCOUNT_ID" not in caplog.text

    def _caida():
        raise RuntimeError("database is locked")
    monkeypatch.setattr(r2_pendientes.db, "conectar", _caida)
    assert r2_pendientes.reintentar() == (0, 0)


def test_reintentar_sin_pendientes_no_abre_r2(base_temporal, monkeypatch):
    monkeypatch.setattr(r2_uploader, "delete_files_lote", lambda claves: pytest.fail("no había nada que borrar"))
    assert r2_pendientes.reintentar() == (0, 0)


def test_delete_files_detalle_dice_que_claves_fallaron_y_delete_files_no_cambia(monkeypatch):
    class Cliente:
        def __init__(self):
            self.borradas = []

        def delete_object(self, Bucket, Key):          # noqa: N803 — la firma de boto3
            if Key.endswith("malo.jpg"):
                raise ConnectionError("tok-llave-de-prueba")          # llave-de-prueba
            self.borradas.append(Key)
    armados = []
    monkeypatch.setattr(r2_uploader, "_client", lambda: armados.append(Cliente()) or armados[-1])
    monkeypatch.setenv("R2_BUCKET_NAME", "bucket")
    assert r2_uploader.delete_files_detalle([]) == (0, []) and armados == []
    assert r2_uploader.delete_files_detalle(["a.jpg", "malo.jpg", "c.jpg"]) == (2, [("malo.jpg", "ConnectionError")])
    assert r2_uploader.delete_files(["a.jpg", "malo.jpg"]) == (1, ["ConnectionError"])       # su contrato de siempre
    assert len(armados) == 2
    monkeypatch.delenv("R2_BUCKET_NAME")
    for funcion in (r2_uploader.delete_files_detalle, r2_uploader.delete_files):
        with pytest.raises(RuntimeError):
            funcion(["a.jpg"])


# ---------------------------------------------------------------------- PND-303: tope por corrida y lotes ---

def test_pnd303_reintentar_pide_como_mucho_el_tope_en_una_tanda_y_las_que_fallan_van_al_final(base_temporal,
                                                                                               monkeypatch):
    """PND-303 (decisión 2026-10-13): la limpieza diaria corre en el único hilo del carril general; con cientos de
    claves y R2 lento lo tenía ocupado. Ahora pide como mucho TOPE_POR_CORRIDA en UNA llamada por lotes, y una clave que
    R2 rechaza siempre pasa al final para que las de atrás también se intenten."""
    assert r2_pendientes.TOPE_POR_CORRIDA == 200
    monkeypatch.setattr(r2_pendientes, "TOPE_POR_CORRIDA", 3)
    r2_pendientes.anotar(["a", "b", "c", "d", "e"])
    pedidas = []

    def _lote(claves):
        pedidas.append(list(claves))
        return len(claves) - 1, [("a", "AccessDenied")]
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _lote)
    monkeypatch.setattr(r2_uploader, "delete_files_detalle", lambda claves: pytest.fail("una por una no"))
    assert r2_pendientes.reintentar() == (2, 3)
    assert pedidas == [["a", "b", "c"]] and r2_pendientes.pendientes() == ["d", "e", "a"]
    assert r2_pendientes.reintentar() == (2, 1)                   # al día siguiente le toca a las de atrás
    assert pedidas[-1] == ["d", "e", "a"] and r2_pendientes.pendientes() == ["a"]


def test_pnd303_con_r2_caido_nada_se_pierde_y_la_cola_rota(base_temporal, monkeypatch):
    monkeypatch.setattr(r2_pendientes, "TOPE_POR_CORRIDA", 2)
    r2_pendientes.anotar(["a", "b", "c"])

    def _caido(claves):
        raise ConnectionError("R2 no contesta")
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _caido)
    assert r2_pendientes.reintentar() == (0, 3)
    assert sorted(r2_pendientes.pendientes()) == ["a", "b", "c"] and r2_pendientes.pendientes()[0] == "c"


class _ClienteLote:
    """Un cliente de R2 falso para DeleteObjects: `errores` = {clave: código} que R2 rechaza; `rechaza` = la tanda entera
    vuelve con ClientError; `cae` = la tanda no llega."""

    def __init__(self, errores=None, rechaza=False, cae=False):
        self.errores, self.rechaza, self.cae = errores or {}, rechaza, cae
        self.tandas, self.sueltas = [], []

    def delete_objects(self, Bucket, Delete):          # noqa: N803 — la firma de boto3
        claves = [o["Key"] for o in Delete["Objects"]]
        self.tandas.append(claves)
        assert Bucket == "bucket" and Delete["Quiet"] is True
        if self.cae:
            raise ConnectionError("tok-llave-de-prueba")          # llave-de-prueba
        if self.rechaza:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "NotImplemented", "Message": "x"}}, "DeleteObjects")
        return {"Errors": [{"Key": k, "Code": c, "Message": "no"} for k, c in self.errores.items() if k in claves]}

    def delete_object(self, Bucket, Key):              # noqa: N803
        self.sueltas.append(Key)


def test_pnd303_delete_files_lote_borra_de_a_1000_y_dice_que_claves_fallaron(monkeypatch):
    monkeypatch.setenv("R2_BUCKET_NAME", "bucket")
    cliente = _ClienteLote(errores={"k5": "AccessDenied", "k1500": "<raro>"})
    armados = []
    monkeypatch.setattr(r2_uploader, "_client", lambda: armados.append(cliente) or cliente)
    assert r2_uploader.delete_files_lote([]) == (0, []) and armados == []
    claves = [f"k{i}" for i in range(2500)]
    assert r2_uploader.delete_files_lote(claves) == (2498, [("k5", "AccessDenied"), ("k1500", "ErrorR2")])
    assert [len(t) for t in cliente.tandas] == [1000, 1000, 500] and len(armados) == 1 and cliente.sueltas == []


def test_pnd303_una_tanda_rechazada_entera_va_una_por_una_y_una_que_no_llega_queda_para_manana(monkeypatch):
    monkeypatch.setenv("R2_BUCKET_NAME", "bucket")
    rechaza = _ClienteLote(rechaza=True)
    monkeypatch.setattr(r2_uploader, "_client", lambda: rechaza)
    assert r2_uploader.delete_files_lote(["a", "b"]) == (2, []) and rechaza.sueltas == ["a", "b"]
    cae = _ClienteLote(cae=True)
    monkeypatch.setattr(r2_uploader, "_client", lambda: cae)
    assert r2_uploader.delete_files_lote(["a", "b"]) == (0, [("a", "ConnectionError"), ("b", "ConnectionError")])
    assert cae.sueltas == []
    monkeypatch.delenv("R2_BUCKET_NAME")
    with pytest.raises(RuntimeError):
        r2_uploader.delete_files_lote(["a"])


# ---------------------------------------------------------------------- quién anota ---

def test_borrar_copias_anota_las_claves_que_fallaron(base_temporal, monkeypatch):
    from meta_rendimiento import creativo
    monkeypatch.setattr(r2_uploader, "delete_files_detalle",
                        lambda claves: (len(claves) - 1, [(claves[0], "ClientError")]))
    assert creativo.borrar_copias("acme", [(7, "123")]) == (1, ["ClientError"])     # lo que devuelve, como siempre
    assert r2_pendientes.pendientes() == [f"{BASE}/a7_123.jpg"]


def test_borrar_copias_sin_r2_configurado_anota_todas(base_temporal, monkeypatch):
    from meta_rendimiento import creativo
    monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
    assert creativo.borrar_copias("acme", [(7, "123")]) == (0, ["RuntimeError", "RuntimeError"])
    assert r2_pendientes.pendientes() == [f"{BASE}/a7_123.jpg", f"{BASE}/a7_123.mp4"]


def test_borrar_copias_sin_fallos_no_anota_nada(base_temporal, monkeypatch):
    from meta_rendimiento import creativo
    monkeypatch.setattr(r2_uploader, "delete_files_detalle", lambda claves: (len(claves), []))
    monkeypatch.setattr(r2_pendientes, "anotar", lambda claves: pytest.fail("nada que anotar"))
    assert creativo.borrar_copias("acme", [(7, "123")]) == (2, [])


def test_borrar_claves_anota_las_miniaturas_que_fallaron(base_temporal, monkeypatch):
    from meta_rendimiento import analisis
    eval_r2 = "clientes/acme/meta_rendimiento"
    monkeypatch.setattr(r2_uploader, "delete_files_detalle",
                        lambda claves: (len(claves) - 1, [(claves[1], "ClientError")]))
    assert analisis.borrar_claves([f"{eval_r2}/eval1_A1.jpg", f"{eval_r2}/eval1_A2.jpg"]) == (1, ["ClientError"])
    assert r2_pendientes.pendientes() == [f"{eval_r2}/eval1_A2.jpg"]


def test_una_clave_anotada_se_borra_en_la_limpieza_diaria(base_temporal, monkeypatch):
    """De punta a punta: R2 cae al soltar la cuenta, la clave queda anotada y `meta_rend_limpiar` la borra al día."""
    from meta_rendimiento import creativo
    from tareas import meta_rendimiento as tareas_mr
    monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
    creativo.borrar_copias("acme", [(7, "123")])
    borradas = []
    monkeypatch.setattr(r2_uploader, "delete_files_lote", lambda claves: (borradas.extend(claves), (len(claves), []))[1])
    tareas_mr.meta_rend_limpiar({"payload": {}})
    assert borradas == [f"{BASE}/a7_123.jpg", f"{BASE}/a7_123.mp4"] and r2_pendientes.pendientes() == []


# ------------------------------------------------- ningún aviso registra claves (M2 de la ronda de arreglos 1) ---

CLAVE = f"{BASE}/a1_123.jpg"      # con el id del proyecto y del anuncio: nunca va a un log


@pytest.mark.parametrize("r2", ["devuelve", "lanza"])
def test_el_aviso_de_reintentar_no_registra_las_claves(base_temporal, monkeypatch, caplog, r2):
    r2_pendientes.anotar([CLAVE, f"{BASE}/a1_123.mp4"])

    def _detalle(claves):
        if r2 == "lanza":
            raise RuntimeError(f"no se pudo borrar {claves[0]}")
        return 1, [(CLAVE, "ClientError")]
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _detalle)
    with caplog.at_level(logging.DEBUG):
        r2_pendientes.reintentar()
    assert caplog.text and "clientes/" not in caplog.text


@pytest.mark.parametrize("r2", ["devuelve", "lanza"])
def test_los_avisos_de_borrar_copias_y_borrar_claves_no_registran_las_claves(base_temporal, monkeypatch, caplog, r2):
    from meta_rendimiento import analisis, creativo

    def _detalle(claves):
        if r2 == "lanza":
            raise RuntimeError(f"no se pudo borrar {claves[0]}")
        return 0, [(c, "ClientError") for c in claves]
    monkeypatch.setattr(r2_uploader, "delete_files_lote", _detalle)
    with caplog.at_level(logging.DEBUG):
        creativo.borrar_copias("acme", [(1, "123")])
        analisis.borrar_claves(["clientes/acme/meta_rendimiento/eval1_A1.jpg"])
    assert "copia(s) de anuncios de Meta" in caplog.text and "miniatura(s) de evaluación" in caplog.text
    assert "clientes/" not in caplog.text
    assert CLAVE in r2_pendientes.pendientes()             # anotadas sí, en la base; en el log, nunca

"""usuarios.por_cliente: las cuentas rol «cliente» de un proyecto (las alertas
de correo sin confirmar de un proyecto las leen de aquí), con su correo y si
está confirmado, y NUNCA con el hash de la contraseña."""
import _json_store


def _sembrar(usuarios):
    """usuarios.json del test con: un admin, dos clientes de acme (uno con el
    correo confirmado y otro sin correo) y uno de otro."""
    _json_store.guardar(usuarios._path(), {
        "jefe": {"password_hash": "hash-secreto-jefe", "rol": "admin", "cliente": None,
                 "correo": "jefe@prueba.local", "correo_verificado": True, "session_version": 1},
        "ana": {"password_hash": "hash-secreto-ana", "rol": "cliente", "cliente": "acme",
                "correo": "ana@acme.test", "correo_verificado": True, "session_version": 1},
        "beto": {"password_hash": "hash-secreto-beto", "rol": "cliente", "cliente": "acme"},   # registro viejo
        "carla": {"password_hash": "hash-secreto-carla", "rol": "cliente", "cliente": "otro",
                  "correo": "carla@otro.test", "correo_verificado": False, "session_version": 1},
    })


def test_devuelve_solo_los_clientes_de_ese_proyecto(usuarios_tmp):
    _sembrar(usuarios_tmp)
    lista = usuarios_tmp.por_cliente("acme")
    assert [u["usuario"] for u in lista] == ["ana", "beto"]
    ana, beto = lista
    assert ana["correo"] == "ana@acme.test" and ana["correo_verificado"] is True
    # Un registro anterior al correo sale con los valores por defecto.
    assert beto["correo"] is None and beto["correo_verificado"] is False
    assert [u["usuario"] for u in usuarios_tmp.por_cliente("otro")] == ["carla"]


def test_el_admin_no_cuenta_ni_un_proyecto_sin_cuentas(usuarios_tmp):
    _sembrar(usuarios_tmp)
    assert "jefe" not in [u["usuario"] for u in usuarios_tmp.por_cliente("acme")]
    assert usuarios_tmp.por_cliente("nadie") == []
    assert usuarios_tmp.por_cliente(None) == []


def test_nunca_expone_el_hash_ni_ninguna_clave_de_la_contrasena(usuarios_tmp):
    _sembrar(usuarios_tmp)
    for proyecto in ("acme", "otro"):
        for u in usuarios_tmp.por_cliente(proyecto):
            assert set(u) == {"usuario", "correo", "correo_verificado"}
            assert not any("hash" in k or "clave" in k or "password" in k for k in u)
    assert "hash-secreto" not in repr(usuarios_tmp.por_cliente("acme") + usuarios_tmp.por_cliente("otro"))


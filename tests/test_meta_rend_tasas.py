"""USD por día (spec §7): BCE por frankfurter, fines de semana con el último día
publicado, USD = 1 sin pedir nada, y sin tasa = None (nunca inventada)."""
import json

from meta_rendimiento import tasas


class _Resp:
    def __init__(self, datos, status=200):
        self.status_code, self._d = status, datos

    def json(self):
        return self._d

    def close(self):
        pass


def test_asegurar_guarda_y_mapa_rellena_fines_de_semana(base_temporal, monkeypatch):
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-02": {"USD": 0.09942}, "2026-10-05": {"USD": 0.09957}}})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["SEK", "USD"], "2026-10-02", "2026-10-05")
    assert len(pedidas) == 1 and "from=SEK" in pedidas[0] and "2026-09-25..2026-10-05" in pedidas[0]
    m = tasas.mapa("SEK", "2026-10-02", "2026-10-05")
    assert m == {"2026-10-02": 0.09942, "2026-10-03": 0.09942, "2026-10-04": 0.09942, "2026-10-05": 0.09957}
    assert tasas.mapa("USD", "2026-10-02", "2026-10-03") == {"2026-10-02": 1.0, "2026-10-03": 1.0}
    # Ya guardadas: no vuelve a pedir.
    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-05")
    assert len(pedidas) == 1


def test_sin_tasa_es_none_y_un_fallo_no_lanza(base_temporal, monkeypatch):
    def abrir(url, **_):
        raise tasas.url_conector.ErrorConector("caído")
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["NOK"], "2026-10-01", "2026-10-02")
    assert tasas.mapa("NOK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}
    assert tasas.usd("NOK", "2026-10-01") is None

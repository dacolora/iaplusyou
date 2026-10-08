"""USD por día (spec §7): BCE por frankfurter, fines de semana con el último día
publicado, USD = 1 sin pedir nada, y sin tasa = None (nunca inventada)."""
from datetime import date

from meta_rendimiento import tasas


class _Resp:
    def __init__(self, datos, status=200):
        self.status_code, self._d = status, datos

    def json(self):
        return self._d

    def close(self):
        pass


def test_asegurar_guarda_y_mapa_rellena_fines_de_semana(base_temporal, monkeypatch):
    tasas._reiniciar_cache()
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
    tasas._reiniciar_cache()
    def abrir(url, **_):
        raise tasas.url_conector.ErrorConector("caído")
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["NOK"], "2026-10-01", "2026-10-02")
    assert tasas.mapa("NOK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}
    assert tasas.usd("NOK", "2026-10-01") is None


def test_holiday_no_refetch_mismo_objetivo(base_temporal, monkeypatch):
    """Festivo dentro del rango → segunda llamada no hace requests."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        # 25 Dec 2026 es festivo, solo retorna 24 Dec (lunes) y 28 Dec (lunes post-holiday)
        return _Resp({"base": "SEK", "rates": {"2026-12-24": {"USD": 0.10}}})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # Primer call: 24-26 Dec, objetivo es 24 (último laborable ≤ 26 cuando hoy=27)
    tasas.asegurar(["SEK"], "2026-12-24", "2026-12-26", hoy=date(2026, 12, 27))
    assert len(pedidas) == 1

    # Segunda call: mismo objetivo, dentro de 6h → no vuelve a pedir
    tasas.asegurar(["SEK"], "2026-12-24", "2026-12-26", hoy=date(2026, 12, 27))
    assert len(pedidas) == 1  # Sin new requests


def test_404_currency_no_refetch_6h(base_temporal, monkeypatch):
    """Moneda 404 → segunda llamada dentro de 6h no hace requests, mapa da None."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({}, status=404)
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # Primer call: 404
    tasas.asegurar(["COP"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert len(pedidas) == 1

    # Segunda call: dentro de 6h → no vuelve a pedir
    tasas.asegurar(["COP"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert len(pedidas) == 1

    # mapa da None
    assert tasas.mapa("COP", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_already_have_all_labor_days(base_temporal, monkeypatch):
    """Con datos cached que cubren primero a objetivo, no re-fetcha."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": 0.10}, "2026-10-02": {"USD": 0.11}}})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # First call: 1-2 Oct, objetivo=2 (Fri)
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 5))
    assert len(pedidas) == 1

    # Second call: 1-3 Oct (3 is Sat), objetivo=2, tenemos datos desde 1 to 2
    # primero=1, objetivo=2, max(cached)=2 >= objetivo ✓
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 5))
    assert len(pedidas) == 1  # No new request


def test_non_dict_body_no_raise(base_temporal, monkeypatch):
    """Body no-dict (rates es lista) no lanza excepción."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"base": "SEK", "rates": []})  # rates es lista, no dict
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # Nunca lanza, solo retorna None para esos días
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert tasas.mapa("SEK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_non_numeric_rate_no_raise(base_temporal, monkeypatch):
    """Tasa no-numérica ("abc") no lanza, skips ese día."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": "abc"}, "2026-10-02": {"USD": 0.10}}})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))

    # 1 Oct: tasa inválida, sin caché → None
    # 2 Oct: tasa válida → 0.10
    m = tasas.mapa("SEK", "2026-10-01", "2026-10-02")
    assert m == {"2026-10-01": None, "2026-10-02": 0.10}


def test_invalid_currency_code_skipped(base_temporal, monkeypatch):
    """Códigos de moneda inválidos (no [A-Z]{3}) se ignoran."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # "XX" (2 chars) y "X1" (no-alfabético) se ignoran
    tasas.asegurar(["XX", "SEK", "X1"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))

    # Solo SEK debe hacer request
    assert len(pedidas) == 1
    assert "from=SEK" in pedidas[0]

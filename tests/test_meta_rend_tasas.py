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


def test_stored_rates_no_exception_no_refetch(base_temporal, monkeypatch, caplog):
    """Dos tasas SEK guardadas, reset cache, llamada otra vez → 0 requests, NO exception."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-02": {"USD": 0.10}, "2026-10-05": {"USD": 0.11}}})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-05", hoy=date(2026, 10, 5))
    assert len(pedidas) == 1

    tasas._reiniciar_cache()
    pedidas.clear()

    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-05", hoy=date(2026, 10, 5))
    assert len(pedidas) == 0
    assert "TypeError" not in caplog.text


def test_holiday_inside_range_no_refetch(base_temporal, monkeypatch, caplog):
    """Festivo dentro: objetivo=30 Dec (Wed), segunda llamada 0 requests."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {
            "2026-12-22": {"USD": 0.10}, "2026-12-23": {"USD": 0.11}, "2026-12-24": {"USD": 0.12},
            "2026-12-29": {"USD": 0.13}, "2026-12-30": {"USD": 0.14}
        }})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-12-22", "2026-12-30", hoy=date(2027, 1, 5))
    assert len(pedidas) == 1

    tasas.asegurar(["SEK"], "2026-12-22", "2026-12-30", hoy=date(2027, 1, 5))
    assert len(pedidas) == 1
    assert "TypeError" not in caplog.text


def test_one_day_range_old_cached_must_fetch(base_temporal, monkeypatch, caplog):
    """Rango un día (lun 5 oct, hoy 8 oct) con solo 1-2 oct cached → fetches."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir_precache(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": 0.10}, "2026-10-02": {"USD": 0.11}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir_precache)
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1

    def abrir_new(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-05": {"USD": 0.12}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir_new)
    tasas.asegurar(["SEK"], "2026-10-05", "2026-10-05", hoy=date(2026, 10, 8))
    assert len(pedidas) == 2
    assert "TypeError" not in caplog.text


def test_past_range_incomplete_data_first_fetch(base_temporal, monkeypatch, caplog):
    """Past range Sat 3 Oct → first fetch (table empty). 
    objetivo properly weekday-adjusted to Fri 2 Oct (not Sat 3)."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": 0.10}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1  # First fetch happens (table empty)
    assert "TypeError" not in caplog.text


def test_past_range_complete_data_cache_independent(base_temporal, monkeypatch, caplog):
    """Prove stored rates drive skip: reset cache between calls so negative cache can't help."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": 0.10}, "2026-10-02": {"USD": 0.11}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 5))
    assert len(pedidas) == 1

    tasas._reiniciar_cache()
    pedidas.clear()

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 5))
    assert len(pedidas) == 0
    assert "TypeError" not in caplog.text


def test_today_only_range_empty_table_must_fetch(base_temporal, monkeypatch, caplog):
    """Rango hoy-only con tabla vacía → fetches."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-07": {"USD": 0.10}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-08", "2026-10-08", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1
    assert "TypeError" not in caplog.text


def test_zero_and_negative_rates_not_stored(base_temporal, monkeypatch):
    """Tasas 0, negativas, NaN, Inf nunca se guardan."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"rates": {
            "2026-10-01": {"USD": 0.0},
            "2026-10-02": {"USD": -0.05},
            "2026-10-03": {"USD": float('nan')},
            "2026-10-04": {"USD": float('inf')},
            "2026-10-05": {"USD": 0.10},
        }})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-05", hoy=date(2026, 10, 5))

    m = tasas.mapa("SEK", "2026-10-01", "2026-10-05")
    assert m == {"2026-10-01": None, "2026-10-02": None, "2026-10-03": None, 
                 "2026-10-04": None, "2026-10-05": 0.10}


def test_none_values_not_raise(base_temporal, monkeypatch):
    """asegurar with None values doesn't raise, just logs warning."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], None, "2026-10-03")
    tasas.asegurar(None, "2026-10-01", "2026-10-03")


def test_non_dict_json_body_no_exception(base_temporal, monkeypatch):
    """Body no-dict (list) no lanza excepción."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp([1, 2])

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert tasas.mapa("SEK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_rates_list_not_dict_no_exception(base_temporal, monkeypatch):
    """rates como lista en lugar de dict no lanza excepción."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"rates": [1, 2]})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert tasas.mapa("SEK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_non_numeric_rate_skips_date(base_temporal, monkeypatch):
    """Tasa no-numérica skips ese día, no lanza excepción."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"rates": {"2026-10-01": {"USD": "abc"}, "2026-10-02": {"USD": 0.10}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    m = tasas.mapa("SEK", "2026-10-01", "2026-10-02")
    assert m == {"2026-10-01": None, "2026-10-02": 0.10}


def test_404_no_refetch_6h(base_temporal, monkeypatch):
    """404 → segunda llamada dentro de 6h hace 0 requests, mapa da None."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({}, status=404)

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["COP"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert len(pedidas) == 1

    tasas.asegurar(["COP"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert len(pedidas) == 1

    assert tasas.mapa("COP", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_usd_always_one(base_temporal, monkeypatch):
    """USD siempre retorna 1.0, sin pedir nada."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["USD"], "2026-10-01", "2026-10-02")
    assert len(pedidas) == 0
    assert tasas.mapa("USD", "2026-10-01", "2026-10-02") == {"2026-10-01": 1.0, "2026-10-02": 1.0}

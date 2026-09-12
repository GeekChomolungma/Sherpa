import pandas as pd
import pytest

from sherpa.data.universe import Universe


class _FakeCHReader:
    def __init__(self, symbols, listing_times):
        self._symbols = symbols
        self._listing_times = listing_times
        self.listing_calls = 0

    def get_all_symbols(self):
        return list(self._symbols)

    def get_listing_times(self):
        self.listing_calls += 1
        return dict(self._listing_times)


def test_static_universe_all_symbols():
    u = Universe(["BTCUSDT", "ETHUSDT"])
    assert u.all_symbols() == ["BTCUSDT", "ETHUSDT"]


def test_static_universe_as_of_requires_ch_reader():
    u = Universe(["BTCUSDT"])
    with pytest.raises(RuntimeError):
        u.as_of("2026-01-01")


def test_universe_from_clickhouse_all_symbols():
    ch = _FakeCHReader(["BTCUSDT", "ETHUSDT"], {})
    u = Universe.from_clickhouse(ch)
    assert u.all_symbols() == ["BTCUSDT", "ETHUSDT"]


def test_point_in_time_universe_filters_unlisted_symbols():
    ch = _FakeCHReader(
        symbols=["BTCUSDT", "ETHUSDT", "NEWCOIN"],
        listing_times={
            "BTCUSDT": pd.Timestamp("2020-01-01", tz="UTC"),
            "ETHUSDT": pd.Timestamp("2020-01-01", tz="UTC"),
            "NEWCOIN": pd.Timestamp("2026-06-01", tz="UTC"),
        },
    )
    u = Universe.from_clickhouse(ch)

    early = u.as_of("2025-01-01")
    assert early == ["BTCUSDT", "ETHUSDT"]

    late = u.as_of("2026-07-01")
    assert late == ["BTCUSDT", "ETHUSDT", "NEWCOIN"]


def test_point_in_time_universe_caches_listing_times():
    ch = _FakeCHReader(["BTCUSDT"], {"BTCUSDT": pd.Timestamp("2020-01-01", tz="UTC")})
    u = Universe.from_clickhouse(ch)

    u.as_of("2025-01-01")
    u.as_of("2025-06-01")

    assert ch.listing_calls == 1  # 只查一次，之后用内存缓存（设计文档 5.3）


def test_point_in_time_universe_symbol_missing_from_listing_times_is_excluded():
    # symbol 存在于 all_symbols() 但查不到上线时间——保守处理为"永远未上线"
    ch = _FakeCHReader(["BTCUSDT", "UNKNOWN"], {"BTCUSDT": pd.Timestamp("2020-01-01", tz="UTC")})
    u = Universe.from_clickhouse(ch)
    assert u.as_of("2030-01-01") == ["BTCUSDT"]

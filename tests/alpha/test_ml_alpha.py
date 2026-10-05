import dataclasses

import numpy as np
import pandas as pd
import pytest

from sherpa.alpha import registry
from sherpa.alpha.custom.ml import LgbmV1, MLAlpha, build_features
from sherpa.alpha.custom.ml.features import FeatureSpec, cross_sectional_rank, market_features
from sherpa.alpha.liquidity import LiquidityFilter, restrict
from sherpa.alpha.custom.ml.manifest import Manifest, ModelEntry, load_manifest, save_manifest
from sherpa.data.schema import BarPanel, build_coverage

from .fixtures import make_panel

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT")


def _panel(n=320):
    return make_panel(n=n, symbols=SYMBOLS, seed=7)


def _with_late_symbol(panel: BarPanel, listed_from: int) -> BarPanel:
    """多一列 `listed_from` 行才上线的币（之前整列 NaN）。"""
    rng = np.random.default_rng(1)
    fields = {}
    for f in dataclasses.fields(BarPanel):
        value = getattr(panel, f.name)
        if isinstance(value, pd.DataFrame):
            extra = pd.Series(rng.uniform(50, 150, len(panel.index)), index=panel.index)
            extra.iloc[:listed_from] = np.nan
            fields[f.name] = value.assign(NEWUSDT=extra)
    symbols = panel.symbols + ("NEWUSDT",)
    return BarPanel(interval=panel.interval, symbols=symbols, coverage=build_coverage(fields["close"], len(symbols)), **fields)


def test_features_follow_spec_order_and_time_sorted_index():
    panel = _panel()
    features = build_features(panel, LgbmV1.spec)
    assert list(features.columns) == list(LgbmV1.spec.feature_names)
    assert features.index.names == ["start_time", "symbol"]
    assert features.index.is_monotonic_increasing or features.index.get_level_values(0).is_monotonic_increasing
    assert len(features) == int(panel.close.notna().sum().sum())
    assert features.dtypes.eq("float32").all()
    # 截面特征在 [-0.5, 0.5]（范围外是 NaN），市场特征同一期所有 symbol 相同
    last = features.xs(panel.index[-1], level="start_time")
    assert last["ret_6"].dropna().between(-0.5, 0.5).all()
    assert last["market:rv_quantile"].nunique() == 1


def test_features_are_point_in_time():
    """截断到第 k 行算出来的特征，跟用完整数据算出来的前 k 行完全相同。"""
    panel = _panel()
    k = 260
    full = build_features(panel, LgbmV1.spec)
    cut = build_features(panel.slice(slice(0, k)), LgbmV1.spec)
    pd.testing.assert_frame_equal(cut, full.loc[: panel.index[k - 1]])


def test_features_ignore_symbols_that_are_not_listed_yet():
    """面板多一列还没上线的币，已有币在它上线之前的特征不变（研究流水线各阶段 universe 截止时间不同）。"""
    panel = _panel()
    listed_from = 280
    wide = _with_late_symbol(panel, listed_from)
    base = build_features(panel, LgbmV1.spec).loc[: panel.index[listed_from - 1]]
    padded = build_features(wide, LgbmV1.spec).loc[: panel.index[listed_from - 1]]
    pd.testing.assert_frame_equal(padded, base)


def test_market_features_use_regime_continuous_values():
    panel = _panel()
    market = market_features(panel, LgbmV1.spec)
    assert market["market_breadth"].dropna().between(0, 1).all()
    assert set(market["benchmark_trend_up"].dropna().unique()) <= {0.0, 1.0}


def test_spec_fingerprint_changes_with_features():
    a = FeatureSpec(name="x", version=1, alphas=("worldquant.alpha040",))
    b = FeatureSpec(name="x", version=1, alphas=("worldquant.alpha044",))
    assert a.fingerprint != b.fingerprint
    assert a.fingerprint == FeatureSpec(name="x", version=1, alphas=("worldquant.alpha040",)).fingerprint


def test_manifest_assigns_rows_to_the_model_serving_them(tmp_path):
    t = pd.date_range("2024-01-01", periods=10, freq="4h", tz="UTC")
    entries = [
        ModelEntry(valid_from=str(t[2]), valid_until=str(t[4]), train_rows_until=str(t[0]), files=[]),
        ModelEntry(valid_from=str(t[4]), valid_until=str(t[6]), train_rows_until=str(t[2]), files=[]),
    ]
    manifest = Manifest(model="m", feature_fingerprint="f", feature_names=[], config_fingerprint="c", entries=entries)
    assert manifest.assign(t).tolist() == [-1, -1, 0, 0, 1, 1, -1, -1, -1, -1]

    save_manifest(tmp_path / "m", manifest)
    loaded = load_manifest(tmp_path / "m")
    assert loaded.assign(t).tolist() == manifest.assign(t).tolist()


def test_ml_alpha_registered_and_fails_clearly_without_models(tmp_path, monkeypatch):
    assert registry.get("custom.ml_lgbm_v1") is LgbmV1
    assert LgbmV1.__module__ == "sherpa.alpha.custom.ml.models"
    assert "custom.ml_alpha" not in registry.all()  # 基类不注册
    monkeypatch.setenv("SHERPA_ML_MODEL_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="run_training"):
        LgbmV1().compute(_panel())


def test_ml_alpha_rejects_models_trained_on_other_features(tmp_path, monkeypatch):
    monkeypatch.setenv("SHERPA_ML_MODEL_ROOT", str(tmp_path))
    save_manifest(tmp_path / LgbmV1.model_name, Manifest(
        model=LgbmV1.model_name, feature_fingerprint="old", feature_names=[], config_fingerprint="c",
    ))
    with pytest.raises(ValueError, match="特征清单变了"):
        LgbmV1().compute(_panel())


def test_ml_alpha_is_a_subclass_not_registered_itself():
    assert issubclass(LgbmV1, MLAlpha)
    assert not any(cls is MLAlpha for cls in registry.all().values())


def test_symbol_features_rank_only_within_liquidity_scope():
    """A 组特征：先在全量数据上算时序，再盖掉范围外，只在范围内排名——范围外 NaN，范围内的排名不受范围外的币挤压。"""
    panel = _panel()
    spec = FeatureSpec(name="scoped", version=1, liquidity=LiquidityFilter(min_percentile=0.5, lookback=20))
    scope = spec.liquidity.mask(panel)
    assert 0 < scope.iloc[-1].sum() < len(SYMBOLS)  # 范围真的排除了一些币

    features = build_features(panel, spec)
    raw = panel.close.pct_change(6, fill_method=None)  # ret_6 的原始值，全量数据上算
    expected = cross_sectional_rank(restrict(raw, scope)).stack()
    got = features["ret_6"].dropna()
    pd.testing.assert_series_equal(
        got.astype("float64"), expected.reindex(got.index).astype("float64"), check_names=False, atol=1e-6
    )
    assert features["ret_6"].notna().sum() == int((scope & raw.notna()).sum().sum())
    # C 组不受范围影响：范围外的行照样有市场特征
    out_of_scope = features.loc[~scope.stack().reindex(features.index).fillna(False).to_numpy()]
    assert out_of_scope["market:rv_quantile"].notna().any()


def test_time_series_features_are_not_broken_by_scope():
    """币掉出范围再回来，回来那一根的时序特征立刻有值（时序在全量数据上算，不会被范围打断）。"""
    panel = _panel()
    spec = FeatureSpec(name="scoped", version=1, liquidity=LiquidityFilter(min_percentile=0.5, lookback=20))
    scope = spec.liquidity.mask(panel)
    back = scope & ~scope.shift(1, fill_value=False)  # 这一根刚回到范围内
    back.iloc[:60] = False                            # 跳过 warm-up
    assert back.any().any(), "合成数据里没有掉出再回来的币，换个 seed"
    features = build_features(panel, spec).loc[:, ["vol_42"]]
    t, s = next((t, s) for t, row in back.iterrows() for s, v in row.items() if v)
    assert np.isfinite(features.loc[(t, s), "vol_42"])


def test_fingerprint_changes_with_liquidity_scope():
    a = FeatureSpec(name="x", version=1, liquidity=LiquidityFilter(min_percentile=0.5))
    b = FeatureSpec(name="x", version=1, liquidity=LiquidityFilter(min_percentile=0.6))
    assert a.fingerprint != b.fingerprint

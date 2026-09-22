import numpy as np
import pandas as pd
import pytest

from sherpa.risk.neutralize import neutralize


def _frame(rows, columns):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(rows, index=index, columns=columns)


def test_neutralize_removes_perfectly_explained_exposure():
    # raw_score 就是 2*beta + 1（外加一个不随 beta 变化的横截面偏移），每期都能被
    # beta 完美线性解释——残差应该趋近于 0，不再残留原来的横截面区分度。
    columns = ["A", "B", "C", "D", "E"]
    beta_row = [0.5, 1.0, 1.5, 2.0, 2.5]
    raw_row = [2 * b + 1.0 for b in beta_row]

    raw_score = _frame([raw_row, raw_row], columns)
    beta = _frame([beta_row, beta_row], columns)

    residual = neutralize(raw_score, {"beta": beta})

    assert residual.abs().to_numpy().max() < 1e-8


def test_neutralize_preserves_information_uncorrelated_with_exposure():
    # raw_score 完全独立于 beta（beta 是常数，横截面里对回归没有解释力），此时残差应该
    # 就是 raw_score 去掉截距（组内均值）后的样子，原有的横截面区分度必须还在。
    columns = ["A", "B", "C", "D"]
    raw_row = [1.0, 2.0, 3.0, 4.0]
    beta_row = [1.0, 1.0, 1.0, 1.0]  # 无横截面方差，回归系数解不出来，退化成只有截距

    raw_score = _frame([raw_row], columns)
    beta = _frame([beta_row], columns)

    residual = neutralize(raw_score, {"beta": beta})

    demeaned = pd.Series(raw_row, index=columns) - np.mean(raw_row)
    pd.testing.assert_series_equal(
        residual.iloc[0].sort_index(), demeaned.sort_index(), check_names=False
    )


def test_neutralize_insufficient_samples_is_nan_row():
    # 2 个 exposure + 截距 = 至少需要 4 个有效 symbol 才能留 1 个自由度，这里只给 3 个。
    columns = ["A", "B", "C"]
    raw_score = _frame([[1.0, 2.0, 3.0]], columns)
    beta = _frame([[0.1, 0.2, 0.3]], columns)
    size = _frame([[10.0, 20.0, 30.0]], columns)

    residual = neutralize(raw_score, {"beta": beta, "size": size})

    assert residual.iloc[0].isna().all()


def test_neutralize_missing_symbol_excluded_from_that_period_only():
    columns = ["A", "B", "C", "D", "E"]
    raw_row = [1.0, 2.0, 3.0, 4.0, float("nan")]
    beta_row = [0.1, 0.2, 0.3, 0.4, 0.5]

    raw_score = _frame([raw_row], columns)
    beta = _frame([beta_row], columns)

    residual = neutralize(raw_score, {"beta": beta})

    assert pd.isna(residual.iloc[0]["E"])
    assert residual.iloc[0][["A", "B", "C", "D"]].notna().all()


def test_neutralize_requires_at_least_one_exposure():
    raw_score = _frame([[1.0, 2.0]], ["A", "B"])

    with pytest.raises(ValueError):
        neutralize(raw_score, {})


def test_neutralize_infinite_exposure_excluded_like_missing_not_crashing():
    # -inf 常见来源：log(0) 算出来的 Size 代理。喂给 lstsq 会在 LAPACK 层直接崩溃，
    # 这里必须跟 NaN 同等对待，把这个 symbol 从当期回归里剔除，而不是让整批任务崩掉。
    columns = ["A", "B", "C", "D", "E"]
    beta_row = [0.5, 1.0, 1.5, 2.0, 2.5]
    raw_row = [2 * b + 1.0 for b in beta_row]
    beta_with_inf = [0.5, 1.0, 1.5, 2.0, float("-inf")]

    raw_score = _frame([raw_row], columns)
    beta = _frame([beta_with_inf], columns)

    residual = neutralize(raw_score, {"beta": beta})

    assert pd.isna(residual.iloc[0]["E"])
    assert residual.iloc[0][["A", "B", "C", "D"]].notna().all()
    assert not np.isinf(residual.to_numpy()[~np.isnan(residual.to_numpy())]).any()


def test_neutralize_skips_period_when_lstsq_fails_to_converge_instead_of_raising():
    # 构造一个会让 np.linalg.lstsq 抛 LinAlgError 的病态设计矩阵（NaN 混进已经通过校验的
    # 数值型 numpy 数组本身不现实——这里直接用 monkeypatch 模拟 LAPACK 报错的场景，验证
    # neutralize() 把这一期当"算不出来"跳过，而不是让调用方拿到未处理的异常。
    import unittest.mock as mock

    columns = ["A", "B", "C", "D", "E"]
    raw_row = [1.0, 2.0, 3.0, 4.0, 5.0]
    beta_row = [0.1, 0.2, 0.3, 0.4, 0.5]

    raw_score = _frame([raw_row, raw_row], columns)
    beta = _frame([beta_row, beta_row], columns)

    with mock.patch("numpy.linalg.lstsq", side_effect=np.linalg.LinAlgError("SVD did not converge")):
        residual = neutralize(raw_score, {"beta": beta})

    assert residual.isna().all().all()

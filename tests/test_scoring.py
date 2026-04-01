"""scoring.py 单元测试"""

from harness.methodology.scoring import Scores, parse_scores


def test_weighted_score():
    s = Scores(completeness=4.0, quality=4.0, regression=2.0, design=4.0)
    # min=2.0 权重 2x, 其余 1x → (4+4+4+4)/5 = 3.2 (2*2 + 4*3) / 5 = 16/5 = 3.2
    # 更准确: (4*1 + 4*1 + 2*2 + 4*1) / (1+1+2+1) = (4+4+4+4)/5 = 16/5 = 3.2
    assert abs(s.weighted - 3.2) < 0.01


def test_weighted_all_equal():
    s = Scores(completeness=4.0, quality=4.0, regression=4.0, design=4.0)
    # 所有相等时，全部权重 2x → 平均还是 4.0
    assert abs(s.weighted - 4.0) < 0.01


def test_verdict_pass():
    s = Scores(completeness=8.0, quality=8.0, regression=8.0, design=8.0)
    assert s.verdict() == "PASS"


def test_verdict_iterate_low_weighted():
    s = Scores(completeness=8.0, quality=8.0, regression=4.0, design=8.0)
    assert s.verdict() == "ITERATE"


def test_verdict_iterate_min_too_low():
    s = Scores(completeness=9.0, quality=9.0, regression=1.0, design=9.0)
    assert s.verdict() == "ITERATE"  # min=1.0 不满足 > 1.0


def test_parse_scores():
    md = """\
| 维度 | 分数 | 说明 |
|------|------|------|
| completeness | 4.5 | 全部完成 |
| quality | 3.8 | 小瑕疵 |
| regression | 4.0 | 测试通过 |
| design | 3.5 | 基本符合 |
"""
    s = parse_scores(md)
    assert s.completeness == 4.5
    assert s.quality == 3.8
    assert s.regression == 4.0
    assert s.design == 3.5

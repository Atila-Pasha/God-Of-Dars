from scripts.normalize_legacy_resources import caps, normalized_amount


def test_only_obvious_resource_outliers_are_normalized() -> None:
    coin_cap, diamond_cap = caps(1)

    assert coin_cap >= 100_000
    assert diamond_cap >= 10_000
    assert normalized_amount(coin_cap * 10, coin_cap) == coin_cap * 10
    assert normalized_amount(coin_cap * 10 + 1, coin_cap) == coin_cap
    assert normalized_amount(diamond_cap * 1000, diamond_cap) == diamond_cap


def test_higher_level_mines_have_higher_resource_caps() -> None:
    assert caps(100)[0] > caps(1)[0]
    assert caps(100)[1] > caps(1)[1]

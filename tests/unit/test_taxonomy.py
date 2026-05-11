from youtube_market_brief.domain.taxonomy import (
    SECTOR_SLUGS,
    THEME_SLUGS,
    is_valid_sector,
    is_valid_theme,
)


def test_sector_slugs_match_vault_2026_05_11():
    expected = {
        "semiconductors",
        "software_ai_services",
        "tech_hardware",
        "financials",
        "power_utilities",
        "industrials_defense",
        "energy",
        "materials",
        "consumer_discretionary",
        "consumer_staples",
    }
    assert set(SECTOR_SLUGS) == expected


def test_theme_slugs_match_vault_2026_05_11():
    expected = {
        "ai_agent_adoption",
        "ai_meltup_bubble",
        "bigtech_ipo_supply",
        "geopolitics_middle_east",
        "hyperscaler_capex",
        "korea_discount",
        "memory_supercycle",
        "tokenization_rwa",
        "us_fiscal_debt",
    }
    assert set(THEME_SLUGS) == expected


def test_is_valid_sector_returns_true_for_known():
    assert is_valid_sector("semiconductors") is True


def test_is_valid_sector_returns_false_for_unknown():
    assert is_valid_sector("crypto") is False
    assert is_valid_sector("") is False


def test_is_valid_theme_returns_true_for_known():
    assert is_valid_theme("hyperscaler_capex") is True


def test_is_valid_theme_returns_false_for_unknown():
    assert is_valid_theme("metaverse") is False

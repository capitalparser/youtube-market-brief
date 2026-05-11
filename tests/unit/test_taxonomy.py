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


def test_validate_taxonomy_alignment_returns_empty_when_aligned(tmp_path):
    from youtube_market_brief.config import _validate_taxonomy_alignment

    sectors_dir = tmp_path / "02_Areas" / "Market_Insights" / "sectors"
    themes_dir = tmp_path / "02_Areas" / "Market_Insights" / "themes"
    sectors_dir.mkdir(parents=True)
    themes_dir.mkdir(parents=True)

    from youtube_market_brief.domain.taxonomy import SECTOR_SLUGS, THEME_SLUGS
    for slug in SECTOR_SLUGS:
        (sectors_dir / f"{slug}.md").write_text("# stub", encoding="utf-8")
    for slug in THEME_SLUGS:
        (themes_dir / f"{slug}.md").write_text("# stub", encoding="utf-8")

    drift = _validate_taxonomy_alignment(vault_root=tmp_path)
    assert drift == []


def test_validate_taxonomy_alignment_detects_extra_vault_sector(tmp_path):
    from youtube_market_brief.config import _validate_taxonomy_alignment

    sectors_dir = tmp_path / "02_Areas" / "Market_Insights" / "sectors"
    themes_dir = tmp_path / "02_Areas" / "Market_Insights" / "themes"
    sectors_dir.mkdir(parents=True)
    themes_dir.mkdir(parents=True)

    from youtube_market_brief.domain.taxonomy import SECTOR_SLUGS, THEME_SLUGS
    for slug in SECTOR_SLUGS:
        (sectors_dir / f"{slug}.md").write_text("# stub", encoding="utf-8")
    (sectors_dir / "new_sector.md").write_text("# stub", encoding="utf-8")
    for slug in THEME_SLUGS:
        (themes_dir / f"{slug}.md").write_text("# stub", encoding="utf-8")

    drift = _validate_taxonomy_alignment(vault_root=tmp_path)
    assert "new_sector" in " ".join(drift)


def test_validate_taxonomy_alignment_detects_missing_vault_sector(tmp_path):
    from youtube_market_brief.config import _validate_taxonomy_alignment

    sectors_dir = tmp_path / "02_Areas" / "Market_Insights" / "sectors"
    themes_dir = tmp_path / "02_Areas" / "Market_Insights" / "themes"
    sectors_dir.mkdir(parents=True)
    themes_dir.mkdir(parents=True)

    from youtube_market_brief.domain.taxonomy import SECTOR_SLUGS, THEME_SLUGS
    # 모든 sector를 *2개 빼고* 작성
    for slug in SECTOR_SLUGS[:-2]:
        (sectors_dir / f"{slug}.md").write_text("# stub", encoding="utf-8")
    for slug in THEME_SLUGS:
        (themes_dir / f"{slug}.md").write_text("# stub", encoding="utf-8")

    drift = _validate_taxonomy_alignment(vault_root=tmp_path)
    drift_str = " ".join(drift)
    assert SECTOR_SLUGS[-1] in drift_str
    assert SECTOR_SLUGS[-2] in drift_str

"""Single source of truth for Market_Insights sector/theme slug enum.

prompt enum과 vault MD slug 간 drift를 막기 위해 본 모듈을 import해서
양쪽이 동일한 tuple을 참조하도록 한다. 신규 sector/theme 추가 시
본 파일 + vault MD를 함께 갱신.
"""

from __future__ import annotations

SECTOR_SLUGS: tuple[str, ...] = (
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
)

THEME_SLUGS: tuple[str, ...] = (
    "ai_agent_adoption",
    "ai_meltup_bubble",
    "bigtech_ipo_supply",
    "geopolitics_middle_east",
    "hyperscaler_capex",
    "korea_discount",
    "memory_supercycle",
    "tokenization_rwa",
    "us_fiscal_debt",
)


def is_valid_sector(slug: str) -> bool:
    return slug in SECTOR_SLUGS


def is_valid_theme(slug: str) -> bool:
    return slug in THEME_SLUGS

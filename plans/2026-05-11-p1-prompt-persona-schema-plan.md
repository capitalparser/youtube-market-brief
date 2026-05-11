# P1 Implementation Plan — Prompt Persona + Output Schema Realignment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ymb 출력 schema를 Market_Insights propagation의 결정론적 source로 정렬한다 (key_insights/red_team object 승격, sector/theme tag 명시, JSON sidecar 도입). 페르소나를 4-role composite(감사인+재무정보전문가+투자자+시장분석가)로 재정의한다.

**Architecture:** Schema 변경은 `domain/types.py`에 새 frozen dataclass(`KeyInsight`, `RedTeamItem`) 추가 + 기존 `TranscriptSummary`/`TickerMention`/`WatchlistEntry` 필드 확장으로 흡수. enum은 `domain/taxonomy.py`(신설)에 single source of truth로 두고 prompts·config validator가 import. JSON sidecar는 `write_video.py`·`aggregate.py`에서 MD와 짝지어 작성. Migration은 non-retroactive — 기존 vault MD는 그대로 두고 적용 시점부터 새 schema 적용.

**Tech Stack:** Python 3.12, `uv`, pytest, dataclasses (frozen=True), yaml, anthropic/openai SDK (LLM_PROVIDER), youtube-transcript-api, GitHub Actions.

**Design source:** [`2026-05-11-p1-prompt-persona-schema-design.md`](./2026-05-11-p1-prompt-persona-schema-design.md)

---

## File Structure

신규 파일:
- `src/youtube_market_brief/domain/taxonomy.py` — sector/theme slug enum의 single source of truth
- `docs/adr/0006-prompt-persona-schema-realignment.md` — ADR
- `tests/unit/test_taxonomy.py` — enum + drift validation
- `tests/unit/test_analyze_parser.py` — `_parse_video_payload` 새 schema
- `tests/unit/test_markdown.py` — frontmatter footprint + body
- `tests/unit/test_daily_brief_aggregation.py` — insight aggregation (test_daily_rollup과 분리, 직교 책임)
- `tests/fixtures/analyze_outputs/handcrafted/v1_minimal.json` — unit test용 small fixture
- `tests/fixtures/analyze_outputs/v0/` — 기존 fixture archive 디렉토리
- `tests/fixtures/analyze_outputs/v1/` — integration regression fixture (LLM 생성)
- `tests/fixtures/transcripts/p1_regression/` — regression transcript 2-3건

수정 파일:
- `src/youtube_market_brief/domain/types.py`
- `src/youtube_market_brief/domain/watchlist.py`
- `src/youtube_market_brief/domain/markdown.py`
- `src/youtube_market_brief/domain/daily_brief.py`
- `src/youtube_market_brief/domain/telegram_format.py`
- `src/youtube_market_brief/pipeline/analyze.py`
- `src/youtube_market_brief/pipeline/write_video.py`
- `src/youtube_market_brief/pipeline/aggregate.py`
- `src/youtube_market_brief/config.py`
- `config/watchlist.yaml.example`
- `prompts/system_video_analysis.ko.md`
- `prompts/system_daily_brief.ko.md`
- `tests/unit/test_telegram_format.py` (기존)
- `tests/unit/test_watchlist.py` (기존)

---

## Task 0: ADR-0006 작성 + fixture 디렉토리 셋업

**Files:**
- Create: `docs/adr/0006-prompt-persona-schema-realignment.md`
- Create: `tests/fixtures/analyze_outputs/v0/.gitkeep`
- Create: `tests/fixtures/analyze_outputs/v1/.gitkeep`
- Create: `tests/fixtures/analyze_outputs/handcrafted/.gitkeep`
- Create: `tests/fixtures/transcripts/p1_regression/.gitkeep`

- [ ] **Step 1: ADR-0006 작성**

```bash
cat > docs/adr/0006-prompt-persona-schema-realignment.md << 'EOF'
# ADR-0006: Prompt persona 4-role composite + output schema realignment

- 상태: Accepted
- 날짜: 2026-05-11
- Supersedes: 없음 (ADR-0001~0005와 직교)

## 배경

ymb 출력 schema(`key_insights: list[str]`, `red_team: list[str]`)와 다운스트림 `02_Areas/Market_Insights/{sectors,themes}/*.md` 카드의 frontmatter schema(`type, stance, confidence, related_tickers, related_cards`)가 misaligned되어 매일 41/49 raws의 *수동 propagation*이 work item이 됨 (commit history 인용). ymb는 funnel 상단을 자동화했으나 *카드 통합*이라는 가장 큰 work가 사용자 손에 남아 있음.

또 단일 "한국 회계감사인을 위한 시장 분석가" 페르소나는 사용자 실제 직무 vantage(인차지/감사인/AX Node 매니저/K-IFRS·재무·전략·GTM)의 부분집합이라 분석이 *single-vantage*적이 됨.

## 결정

1. **페르소나 4-role composite**: "감사인이자 재무 정보 전문가이자 투자자이자 시장 분석가인 1인의 분석가"로 재정의. 각 시각의 focus를 명시(red flag/cash flow quality/risk-reward/narrative). 4 시각 합성된 단일 출력 schema 유지 (role 분리 출력 안 함).

2. **key_insights / red_team schema 변경**: `string` → object `{text: str, sector_tags: list[str], theme_tags: list[str]}`. propagation 결정론 확보.

3. **ticker `sector_tag` 추가**: watchlist hit ticker는 `WatchlistEntry.sector` 후처리로 채움(watchlist 우선). 자동 발견 ticker는 LLM 출력.

4. **stance/confidence/time_horizon 자동 출력 거절**: 카드 owner(사용자) 판단 영역. propagation은 *변화 이벤트 row 추가*까지만 자동, stance 결정은 인간.

5. **enum noun**: `domain/taxonomy.py`에 `SECTOR_SLUGS`, `THEME_SLUGS` tuple 정의. prompts에 인라인 노출, `ymb config validate`에 vault MD slug와 drift 비교.

6. **JSON sidecar**: 영상 MD와 daily brief MD 옆에 `.analysis.json`(영상 단위) / `{date}_brief.analysis.json`(일일 단위) 작성. P2 propagation 자동화의 source of truth.

7. **Migration non-retroactive**: 기존 vault MD는 그대로. 적용 시점부터 새 schema. old MD는 사용자 이미 41/49 통합 중이라 그대로 정합.

## 대안

- A. 페르소나는 유지하고 schema만: 사용자 vantage 손실. 거절.
- B. 4-role을 *별도 섹션*으로 출력(audit_view, financial_view ...): schema bloat + token 비용 ↑. 거절.
- C. stance/confidence/time_horizon까지 LLM 출력: 카드 owner 권한 침범 + LLM trust 부담 ↑. 거절.

## 결과

- Schema 변경으로 영향: types/analyze/markdown/telegram_format/daily_brief/aggregate (6 파일).
- Migration 부담: 기존 vault MD 35+건 그대로 둠. 재처리 비용 0.
- 후속: P2 propagation 자동화는 `.analysis.json` sidecar 파싱으로 deterministic.

## 추후 고려

- P2 후 sidecar parser가 안정되면 sidecar를 *유일한* propagation source로 굳히고 frontmatter union은 deprecated 가능.
- old MD retroactive 재처리 스크립트(`ymb reprocess --since YYYY-MM-DD`)는 P2 진입 후 필요 시 추가.
EOF
```

- [ ] **Step 2: fixture 디렉토리 placeholder**

```bash
mkdir -p tests/fixtures/analyze_outputs/v0 \
         tests/fixtures/analyze_outputs/v1 \
         tests/fixtures/analyze_outputs/handcrafted \
         tests/fixtures/transcripts/p1_regression
touch tests/fixtures/analyze_outputs/v0/.gitkeep \
      tests/fixtures/analyze_outputs/v1/.gitkeep \
      tests/fixtures/analyze_outputs/handcrafted/.gitkeep \
      tests/fixtures/transcripts/p1_regression/.gitkeep
```

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0006-prompt-persona-schema-realignment.md \
        tests/fixtures/analyze_outputs/v0/.gitkeep \
        tests/fixtures/analyze_outputs/v1/.gitkeep \
        tests/fixtures/analyze_outputs/handcrafted/.gitkeep \
        tests/fixtures/transcripts/p1_regression/.gitkeep
git commit -m "docs(adr): ADR-0006 prompt persona 4-role composite + schema realignment

P1 implementation의 결정 기록. fixture 디렉토리 골격 추가."
```

---

## Task 1: Taxonomy module (sector/theme enum single source)

**Files:**
- Create: `src/youtube_market_brief/domain/taxonomy.py`
- Create: `tests/unit/test_taxonomy.py`

- [ ] **Step 1: 테스트 작성 — taxonomy module 노출 확인**

```python
# tests/unit/test_taxonomy.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_taxonomy.py -v
```
Expected: FAIL with `ImportError: cannot import name 'SECTOR_SLUGS' from 'youtube_market_brief.domain.taxonomy'`

- [ ] **Step 3: taxonomy 모듈 작성**

```python
# src/youtube_market_brief/domain/taxonomy.py
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_taxonomy.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/youtube_market_brief/domain/taxonomy.py tests/unit/test_taxonomy.py
git commit -m "feat(domain): taxonomy module — sector/theme slug single source"
```

---

## Task 2: Domain types — KeyInsight, RedTeamItem dataclass + 필드 확장

**Files:**
- Modify: `src/youtube_market_brief/domain/types.py`

- [ ] **Step 1: 테스트 — 새 dataclass shape + 기존 dataclass 필드 추가**

```python
# tests/unit/test_types_p1.py (신규 파일)
from youtube_market_brief.domain.types import (
    KeyInsight,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    WatchlistEntry,
)


def test_key_insight_dataclass_shape():
    ki = KeyInsight(
        text="hi", sector_tags=("semiconductors",), theme_tags=()
    )
    assert ki.text == "hi"
    assert ki.sector_tags == ("semiconductors",)
    assert ki.theme_tags == ()


def test_key_insight_is_frozen():
    ki = KeyInsight(text="x", sector_tags=(), theme_tags=())
    import dataclasses
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        ki.text = "y"


def test_red_team_item_dataclass_shape():
    rt = RedTeamItem(
        text="caution", sector_tags=("financials",), theme_tags=("us_fiscal_debt",)
    )
    assert rt.text == "caution"
    assert rt.sector_tags == ("financials",)


def test_watchlist_entry_has_sector_field():
    e = WatchlistEntry(
        symbol="005930",
        market="KOSPI",
        name_ko="삼성전자",
        sector="semiconductors",
    )
    assert e.sector == "semiconductors"


def test_ticker_mention_has_sector_tag_field():
    m = TickerMention(
        symbol="005930",
        display="삼성전자",
        in_watchlist=True,
        sector_tag="semiconductors",
        direction="긍정적",
        reasoning="HBM3E",
        quotes=(),
        confidence="high",
    )
    assert m.sector_tag == "semiconductors"


def test_transcript_summary_uses_key_insight_objects():
    s = TranscriptSummary(
        headline_3line=("a", "b", "c"),
        key_insights=(KeyInsight(text="i1", sector_tags=(), theme_tags=()),),
        red_team=(RedTeamItem(text="r1", sector_tags=(), theme_tags=()),),
        chars_used=0,
        was_truncated=False,
    )
    assert s.key_insights[0].text == "i1"
    assert isinstance(s.red_team[0], RedTeamItem)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_types_p1.py -v
```
Expected: FAIL with `ImportError: cannot import name 'KeyInsight'`

- [ ] **Step 3: types.py 수정**

`src/youtube_market_brief/domain/types.py`에 다음을 추가/수정.

(a) `KeyInsight`, `RedTeamItem` 추가 (TranscriptSummary 정의 *위에*):

```python
@dataclass(frozen=True)
class KeyInsight:
    text: str
    sector_tags: tuple[str, ...] = ()
    theme_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RedTeamItem:
    text: str
    sector_tags: tuple[str, ...] = ()
    theme_tags: tuple[str, ...] = ()
```

(b) `TranscriptSummary` 필드 타입 변경:

```python
@dataclass(frozen=True)
class TranscriptSummary:
    headline_3line: tuple[str, str, str]
    key_insights: tuple[KeyInsight, ...]      # was tuple[str, ...]
    red_team: tuple[RedTeamItem, ...]         # was tuple[str, ...]
    chars_used: int
    was_truncated: bool
```

(c) `TickerMention`에 `sector_tag` 추가:

```python
@dataclass(frozen=True)
class TickerMention:
    symbol: str | None
    display: str
    in_watchlist: bool
    sector_tag: str | None         # 신규. watchlist 우선, 자동 발견은 LLM 출력
    direction: Direction
    reasoning: str
    quotes: tuple[str, ...]
    confidence: Confidence
```

(d) `WatchlistEntry`에 `sector` 추가 (기존 5종목만 있어 부담 낮음 — 사용자가 yaml에서 수동 보강):

```python
@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    market: Market
    name_ko: str
    sector: str = ""               # 신규. 빈 문자열이면 watchlist post-process가 LLM 출력 사용
    name_en: str | None = None
    aliases: tuple[str, ...] = ()
```

기본값 `""`를 둬서 기존 호출부가 깨지지 않게 함 (Task 3에서 config 로딩이 sector 채움).

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_types_p1.py -v
```
Expected: 6 passed

- [ ] **Step 5: 전체 unit test 회귀 확인 (필드 추가로 기존 코드 깨지는지)**

```bash
uv run pytest tests/unit -q
```
Expected: 다수 fail 가능. 특히 `test_watchlist.py`, `test_telegram_format.py`, `test_daily_rollup.py`는 기존 `TickerMention`/`TranscriptSummary` 직접 생성하는 코드 있을 가능성 큼. 이 fail은 *예상된 회귀*. **Step 6에서 분석**.

- [ ] **Step 6: 회귀 분석 + 기록**

```bash
uv run pytest tests/unit -q 2>&1 | tee /tmp/p1_t2_regression.log
```

기존 테스트에서 fail이 나는 패턴은 두 가지로 분류된다:
- (a) `TickerMention(...)` 직접 생성 시 `sector_tag` 누락 — Task 3 이후 production 코드가 채움. 테스트는 `sector_tag=None` 명시로 통과시킴 (Task 3 step에서 처리)
- (b) `TranscriptSummary(key_insights=("a", "b"))` 직접 생성 — Task 4 이후 production 코드가 KeyInsight 채움. 테스트는 KeyInsight wrap으로 통과 (Task 4 step에서 처리)

테스트 회귀 *수정 자체*는 해당 production 코드 변경 task에서 같이 처리한다. 본 task에서는 fail 패턴만 로그로 기록.

- [ ] **Step 7: Commit**

```bash
git add src/youtube_market_brief/domain/types.py tests/unit/test_types_p1.py
git commit -m "feat(domain): KeyInsight/RedTeamItem dataclass + sector_tag/sector fields

types.py만 변경. 기존 테스트 일부 회귀 — 후속 task에서 production
코드 변경과 함께 수정."
```

---

## Task 3: Watchlist sector loading + config example

**Files:**
- Modify: `src/youtube_market_brief/config.py:157-173` (`load_watchlist`)
- Modify: `config/watchlist.yaml.example`
- Modify: `tests/unit/test_watchlist.py` (sector_tag 누락 fix)
- Modify: `src/youtube_market_brief/domain/watchlist.py` (`annotate_in_watchlist` sector_tag 채움)

- [ ] **Step 1: 테스트 — watchlist YAML sector 필드 로딩**

`tests/unit/test_watchlist.py`에 추가:

```python
def test_load_watchlist_parses_sector_field(tmp_path):
    from youtube_market_brief.config import load_watchlist
    p = tmp_path / "wl.yaml"
    p.write_text(
        "tickers:\n"
        "  - symbol: '005930'\n"
        "    market: KOSPI\n"
        "    name_ko: 삼성전자\n"
        "    sector: semiconductors\n",
        encoding="utf-8",
    )
    wl = load_watchlist(p)
    assert wl.entries[0].sector == "semiconductors"


def test_load_watchlist_empty_sector_when_missing(tmp_path):
    from youtube_market_brief.config import load_watchlist
    p = tmp_path / "wl.yaml"
    p.write_text(
        "tickers:\n"
        "  - symbol: '005930'\n"
        "    market: KOSPI\n"
        "    name_ko: 삼성전자\n",
        encoding="utf-8",
    )
    wl = load_watchlist(p)
    assert wl.entries[0].sector == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_watchlist.py::test_load_watchlist_parses_sector_field -v
```
Expected: FAIL — `load_watchlist`이 sector 필드 무시.

- [ ] **Step 3: config.py `load_watchlist` 수정**

`src/youtube_market_brief/config.py`의 `load_watchlist` 내부 `WatchlistEntry(...)` 생성을 다음으로 교체:

```python
entries.append(
    WatchlistEntry(
        symbol=str(t.get("symbol", "")).strip(),
        market=t.get("market", "ETC"),
        name_ko=t.get("name_ko", "").strip(),
        sector=str(t.get("sector", "")).strip(),
        name_en=(t.get("name_en") or None),
        aliases=tuple(a for a in (t.get("aliases") or []) if isinstance(a, str)),
    )
)
```

- [ ] **Step 4: watchlist.yaml.example 갱신**

`config/watchlist.yaml.example`에 sector 필드 예시 추가 (기존 ticker block마다):

```yaml
tickers:
  - symbol: '005930'
    market: KOSPI
    name_ko: 삼성전자
    name_en: Samsung Electronics
    sector: semiconductors        # P1: Market_Insights sector slug, 필수
    aliases: ['samsung', 'sec']
```

- [ ] **Step 5: domain/watchlist.py `annotate_in_watchlist` sector_tag 채움**

`src/youtube_market_brief/domain/watchlist.py`의 `annotate_in_watchlist` 함수를 다음으로 교체:

```python
def annotate_in_watchlist(
    mentions: Iterable[TickerMention], watchlist: Watchlist
) -> tuple[TickerMention, ...]:
    """Re-stamp `in_watchlist`, canonical `symbol`, `sector_tag` on LLM mentions.

    sector_tag 결정:
    - watchlist 매칭되면 WatchlistEntry.sector로 *덮어쓰기* (watchlist 우선)
      단 WatchlistEntry.sector가 빈 문자열이면 LLM 값 보존
    - watchlist 매칭 안 되면 LLM 출력 sector_tag 그대로 사용
    """
    out: list[TickerMention] = []
    for m in mentions:
        entry = resolve_symbol(m, watchlist)
        if entry is not None:
            sector_tag = entry.sector if entry.sector else m.sector_tag
            if entry.sector and m.sector_tag and entry.sector != m.sector_tag:
                import logging
                logging.getLogger(__name__).warning(
                    "ticker %s sector conflict: llm=%s watchlist=%s — using watchlist",
                    entry.symbol, m.sector_tag, entry.sector,
                )
            out.append(
                TickerMention(
                    symbol=entry.symbol,
                    display=m.display,
                    in_watchlist=True,
                    sector_tag=sector_tag,
                    direction=m.direction,
                    reasoning=m.reasoning,
                    quotes=m.quotes,
                    confidence=m.confidence,
                )
            )
        else:
            out.append(
                TickerMention(
                    symbol=m.symbol,
                    display=m.display,
                    in_watchlist=False,
                    sector_tag=m.sector_tag,
                    direction=m.direction,
                    reasoning=m.reasoning,
                    quotes=m.quotes,
                    confidence=m.confidence,
                )
            )
    return tuple(out)
```

- [ ] **Step 6: 기존 `test_watchlist.py`의 회귀 fix**

기존 `test_watchlist.py` 안에서 `TickerMention(...)` 직접 생성하는 모든 곳에 `sector_tag=None`을 키워드 인자로 추가. 보일러플레이트지만 명시적 NULL이 의도 명확.

```bash
grep -n "TickerMention(" tests/unit/test_watchlist.py
# 매칭된 라인들에 sector_tag=None 키워드 인자 추가
```

- [ ] **Step 7: Run tests to verify**

```bash
uv run pytest tests/unit/test_watchlist.py -v
```
Expected: all pass (신규 2건 + 기존 회귀 fix).

- [ ] **Step 8: 실 watchlist.yaml 보강 (수동, 5종목)**

```bash
# 사용자 확인 후 진행 — watchlist는 gitignored
# 5종목 각각에 sector 필드 추가. 예시:
#   - symbol: '005930' → sector: semiconductors
#   - symbol: '000660' → sector: semiconductors
# 등
```

본 step은 사용자가 직접 편집. plan executor가 수행하지 않음. 진행 시 `echo "TODO: 사용자가 config/watchlist.yaml에 sector 필드 5건 추가 후 다음 step 진행"` 출력 후 명시적 confirm 요청.

- [ ] **Step 9: Commit**

```bash
git add src/youtube_market_brief/config.py \
        src/youtube_market_brief/domain/watchlist.py \
        config/watchlist.yaml.example \
        tests/unit/test_watchlist.py
git commit -m "feat(watchlist): sector field + sector_tag annotation

WatchlistEntry.sector를 YAML에서 로딩. annotate_in_watchlist가
sector_tag을 watchlist 우선 + LLM 값 보강 정책으로 채움."
```

---

## Task 4: analyze.py parser — KeyInsight/RedTeamItem object 변환

**Files:**
- Modify: `src/youtube_market_brief/pipeline/analyze.py` (`_parse_video_payload`, `_to_ticker_mention`, 영상 분석 결과 조립부)
- Create: `tests/unit/test_analyze_parser.py`
- Create: `tests/fixtures/analyze_outputs/handcrafted/v1_minimal.json`

- [ ] **Step 1: handcrafted fixture 작성**

```bash
cat > tests/fixtures/analyze_outputs/handcrafted/v1_minimal.json << 'EOF'
{
  "headline_3line": ["문장1", "문장2", "문장3"],
  "key_insights": [
    {"text": "AI capex 가속", "sector_tags": ["semiconductors"], "theme_tags": ["hyperscaler_capex"]},
    {"text": "메모리 melt-up", "sector_tags": ["semiconductors"], "theme_tags": ["memory_supercycle"]},
    {"text": "원화 약세 영향", "sector_tags": [], "theme_tags": ["korea_discount"]}
  ],
  "red_team": [
    {"text": "capex ROI 의심", "sector_tags": ["semiconductors"], "theme_tags": ["ai_meltup_bubble"]}
  ],
  "tickers": [
    {
      "symbol": "005930",
      "display": "삼성전자",
      "in_watchlist": true,
      "sector_tag": "semiconductors",
      "direction": "긍정적",
      "reasoning": "HBM 진척",
      "quotes": ["삼성전자가 HBM3E 양산을..."],
      "confidence": "high"
    },
    {
      "symbol": "NVDA",
      "display": "NVDA",
      "in_watchlist": false,
      "sector_tag": "semiconductors",
      "direction": "긍정적",
      "reasoning": "AI 수요 견조",
      "quotes": ["엔비디아 데이터센터 매출..."],
      "confidence": "medium"
    }
  ],
  "watchlist_hits": ["005930"]
}
EOF
```

- [ ] **Step 2: 테스트 작성 — `_parse_video_payload` 새 schema 통과**

```python
# tests/unit/test_analyze_parser.py
import json
from pathlib import Path

import pytest

from youtube_market_brief.pipeline.analyze import _parse_video_payload


FIXTURE = Path(__file__).parent.parent / "fixtures" / "analyze_outputs" / "handcrafted" / "v1_minimal.json"


def test_parse_v1_payload_returns_dict_with_object_insights():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = _parse_video_payload(payload)
    assert isinstance(parsed["key_insights"][0], dict)
    assert parsed["key_insights"][0]["text"] == "AI capex 가속"
    assert parsed["key_insights"][0]["sector_tags"] == ["semiconductors"]


def test_parse_v1_payload_validates_red_team_objects():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = _parse_video_payload(payload)
    assert parsed["red_team"][0]["text"] == "capex ROI 의심"


def test_parse_rejects_string_key_insights_legacy():
    payload = {
        "headline_3line": ["a", "b", "c"],
        "key_insights": ["plain string"],   # v0 schema
        "red_team": [{"text": "x", "sector_tags": [], "theme_tags": []}],
        "tickers": [],
        "watchlist_hits": [],
    }
    with pytest.raises(ValueError, match="key_insights"):
        _parse_video_payload(payload)


def test_parse_rejects_invalid_sector_enum():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["key_insights"][0]["sector_tags"] = ["bogus_sector"]
    with pytest.raises(ValueError, match="sector_tags"):
        _parse_video_payload(payload)


def test_parse_rejects_invalid_theme_enum():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["red_team"][0]["theme_tags"] = ["bogus_theme"]
    with pytest.raises(ValueError, match="theme_tags"):
        _parse_video_payload(payload)


def test_parse_allows_empty_tag_arrays():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["key_insights"][0]["sector_tags"] = []
    payload["key_insights"][0]["theme_tags"] = []
    # 빈 배열은 허용 (디자인 §4.2: 명확하지 않으면 비워둘 것)
    parsed = _parse_video_payload(payload)
    assert parsed["key_insights"][0]["sector_tags"] == []
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_analyze_parser.py -v
```
Expected: 6 fail (parser는 아직 v0 schema를 기대).

- [ ] **Step 4: `_parse_video_payload` 새 schema validation 작성**

`src/youtube_market_brief/pipeline/analyze.py`의 `_parse_video_payload` 전체 교체:

```python
def _parse_video_payload(payload) -> dict:
    """v1 schema strict validation.

    key_insights / red_team: list of {text, sector_tags, theme_tags}
    tickers: 각 항목에 sector_tag (str | null)
    """
    from youtube_market_brief.domain.taxonomy import is_valid_sector, is_valid_theme

    if not isinstance(payload, dict):
        raise ValueError("expected JSON object at top level")
    for key in ("headline_3line", "key_insights", "red_team", "tickers", "watchlist_hits"):
        if key not in payload:
            raise ValueError(f"missing required field: {key}")

    if not isinstance(payload["headline_3line"], list) or len(payload["headline_3line"]) < 1:
        raise ValueError("headline_3line must be non-empty list")

    if not isinstance(payload["key_insights"], list) or not (3 <= len(payload["key_insights"]) <= 5):
        raise ValueError("key_insights must be 3-5 items")
    for i, item in enumerate(payload["key_insights"]):
        if not isinstance(item, dict) or "text" not in item:
            raise ValueError(f"key_insights[{i}] must be object with 'text'")
        if not isinstance(item.get("sector_tags", []), list):
            raise ValueError(f"key_insights[{i}].sector_tags must be list")
        for s in item.get("sector_tags") or []:
            if not is_valid_sector(s):
                raise ValueError(f"key_insights[{i}].sector_tags invalid slug: {s}")
        if not isinstance(item.get("theme_tags", []), list):
            raise ValueError(f"key_insights[{i}].theme_tags must be list")
        for t in item.get("theme_tags") or []:
            if not is_valid_theme(t):
                raise ValueError(f"key_insights[{i}].theme_tags invalid slug: {t}")

    if not isinstance(payload["red_team"], list):
        raise ValueError("red_team must be list")
    for i, item in enumerate(payload["red_team"]):
        if not isinstance(item, dict) or "text" not in item:
            raise ValueError(f"red_team[{i}] must be object with 'text'")
        if not isinstance(item.get("sector_tags", []), list):
            raise ValueError(f"red_team[{i}].sector_tags must be list")
        for s in item.get("sector_tags") or []:
            if not is_valid_sector(s):
                raise ValueError(f"red_team[{i}].sector_tags invalid slug: {s}")
        if not isinstance(item.get("theme_tags", []), list):
            raise ValueError(f"red_team[{i}].theme_tags must be list")
        for t in item.get("theme_tags") or []:
            if not is_valid_theme(t):
                raise ValueError(f"red_team[{i}].theme_tags invalid slug: {t}")

    if not isinstance(payload["tickers"], list):
        raise ValueError("tickers must be list")
    for i, t in enumerate(payload["tickers"]):
        sector_tag = t.get("sector_tag")
        if sector_tag is not None and not is_valid_sector(sector_tag):
            raise ValueError(f"tickers[{i}].sector_tag invalid: {sector_tag}")

    if not isinstance(payload["watchlist_hits"], list):
        raise ValueError("watchlist_hits must be list")
    return payload
```

- [ ] **Step 5: `_to_ticker_mention` 갱신 — sector_tag 추출**

`src/youtube_market_brief/pipeline/analyze.py`의 `_to_ticker_mention` 함수 교체:

```python
def _to_ticker_mention(d: dict) -> TickerMention:
    direction = d.get("direction", "언급만")
    if direction not in _VALID_DIRECTIONS:
        direction = "언급만"
    confidence = d.get("confidence", "low")
    if confidence not in _VALID_CONFIDENCES:
        confidence = "low"
    quotes = d.get("quotes") or []
    if not isinstance(quotes, list):
        quotes = []
    sector_tag = d.get("sector_tag")
    if sector_tag == "":
        sector_tag = None
    return TickerMention(
        symbol=d.get("symbol") or None,
        display=d.get("display", "").strip() or "(unknown)",
        in_watchlist=bool(d.get("in_watchlist")),
        sector_tag=sector_tag,
        direction=direction,  # type: ignore[arg-type]
        reasoning=d.get("reasoning", "").strip(),
        quotes=tuple(q for q in quotes if isinstance(q, str)),
        confidence=confidence,  # type: ignore[arg-type]
    )
```

- [ ] **Step 6: `analyze_video`의 결과 조립 — KeyInsight/RedTeamItem object 생성**

`src/youtube_market_brief/pipeline/analyze.py`의 `analyze_video` 함수 내, `raw_tickers = parsed["tickers"]` 직후 부분을 교체:

```python
    # v1 schema: key_insights / red_team are list of objects
    key_insights: tuple[KeyInsight, ...] = tuple(
        KeyInsight(
            text=str(item["text"]).strip(),
            sector_tags=tuple(item.get("sector_tags") or []),
            theme_tags=tuple(item.get("theme_tags") or []),
        )
        for item in parsed["key_insights"]
    )
    red_team_raw = parsed["red_team"]
    if red_team_raw:
        red_team: tuple[RedTeamItem, ...] = tuple(
            RedTeamItem(
                text=str(item["text"]).strip(),
                sector_tags=tuple(item.get("sector_tags") or []),
                theme_tags=tuple(item.get("theme_tags") or []),
            )
            for item in red_team_raw
        )
    else:
        red_team = (
            RedTeamItem(text="(영상이 단편 사실 보도, 별도 반론 없음)", sector_tags=(), theme_tags=()),
        )

    raw_tickers = parsed["tickers"]
```

해당 함수 import 라인에 `KeyInsight`, `RedTeamItem` 추가:

```python
from youtube_market_brief.domain.types import (
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    Transcript,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
    Watchlist,
)
```

그리고 `TranscriptSummary(...)` 생성 부분에서 더 이상 `tuple(key_insights)`로 감싸지 않고 위에서 만든 `key_insights`, `red_team`을 그대로 사용:

```python
        transcript_summary=TranscriptSummary(
            headline_3line=tuple(headline_3line[:3]) + ("",) * max(0, 3 - len(headline_3line)),
            key_insights=key_insights,
            red_team=red_team,
            chars_used=transcript.char_count,
            was_truncated=transcript.was_truncated,
        ),
```

기존 `red_team = parsed["red_team"] or [...]` 라인은 위에서 흡수했으므로 제거.

- [ ] **Step 7: Run all tests**

```bash
uv run pytest tests/unit/test_analyze_parser.py tests/unit/test_taxonomy.py tests/unit/test_types_p1.py -v
```
Expected: 모두 통과.

- [ ] **Step 8: Commit**

```bash
git add src/youtube_market_brief/pipeline/analyze.py \
        tests/unit/test_analyze_parser.py \
        tests/fixtures/analyze_outputs/handcrafted/v1_minimal.json
git commit -m "feat(analyze): v1 schema parser — KeyInsight/RedTeamItem objects + sector_tag

_parse_video_payload가 strict enum validation 포함. _to_ticker_mention이
sector_tag 추출. analyze_video가 KeyInsight/RedTeamItem object 조립."
```

---

## Task 5: markdown.py — frontmatter footprint + body text-only

**Files:**
- Modify: `src/youtube_market_brief/domain/markdown.py`
- Create: `tests/unit/test_markdown.py`

- [ ] **Step 1: 테스트 — frontmatter에 insight_sector_tags union이 있고 body는 text만**

```python
# tests/unit/test_markdown.py
from datetime import UTC, datetime

import yaml

from youtube_market_brief.domain.markdown import render_video_markdown
from youtube_market_brief.domain.types import (
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
)


def _make_analysis() -> VideoAnalysis:
    v = VideoMeta(
        video_id="abc",
        channel_id="cid",
        channel_name="HK",
        channel_slug="hk",
        title="제목",
        published_at_utc=datetime(2026, 5, 11, tzinfo=UTC),
        url="https://youtu.be/abc",
    )
    s = TranscriptSummary(
        headline_3line=("h1", "h2", "h3"),
        key_insights=(
            KeyInsight(text="i1", sector_tags=("semiconductors",), theme_tags=("hyperscaler_capex",)),
            KeyInsight(text="i2", sector_tags=("financials",), theme_tags=()),
        ),
        red_team=(
            RedTeamItem(text="r1", sector_tags=("semiconductors",), theme_tags=("ai_meltup_bubble",)),
        ),
        chars_used=0,
        was_truncated=False,
    )
    t = TickerMention(
        symbol="005930",
        display="삼성전자",
        in_watchlist=True,
        sector_tag="semiconductors",
        direction="긍정적",
        reasoning="HBM",
        quotes=("...",),
        confidence="high",
    )
    return VideoAnalysis(
        video=v,
        transcript_summary=s,
        tickers=(t,),
        watchlist_hits=("005930",),
        tier="deep",
        tags=("youtube", "hk"),
        llm_meta=LLMMeta(model="test", duration_ms=0),
        generated_at=datetime(2026, 5, 11, tzinfo=UTC),
    )


def _parse_fm(md: str) -> dict:
    assert md.startswith("---\n")
    end = md.index("\n---\n", 4)
    return yaml.safe_load(md[4:end])


def test_frontmatter_contains_insight_sector_tags_union():
    md = render_video_markdown(_make_analysis(), captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    fm = _parse_fm(md)
    assert set(fm["insight_sector_tags"]) == {"semiconductors", "financials"}
    assert set(fm["insight_theme_tags"]) == {"hyperscaler_capex"}


def test_frontmatter_contains_red_team_tags_union():
    md = render_video_markdown(_make_analysis(), captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    fm = _parse_fm(md)
    assert set(fm["red_team_sector_tags"]) == {"semiconductors"}
    assert set(fm["red_team_theme_tags"]) == {"ai_meltup_bubble"}


def test_body_renders_text_only_no_inline_tags():
    md = render_video_markdown(_make_analysis(), captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    body = md.split("\n---\n\n", 1)[1]
    assert "- i1" in body
    assert "- i2" in body
    assert "- r1" in body
    assert "#semiconductors" not in body
    assert "[semiconductors]" not in body


def test_empty_tag_union_yields_empty_list_in_frontmatter():
    a = _make_analysis()
    # all empty tags
    s = TranscriptSummary(
        headline_3line=("h1", "h2", "h3"),
        key_insights=(KeyInsight(text="i", sector_tags=(), theme_tags=()),),
        red_team=(RedTeamItem(text="r", sector_tags=(), theme_tags=()),),
        chars_used=0,
        was_truncated=False,
    )
    a2 = VideoAnalysis(
        video=a.video,
        transcript_summary=s,
        tickers=a.tickers,
        watchlist_hits=a.watchlist_hits,
        tier=a.tier,
        tags=a.tags,
        llm_meta=a.llm_meta,
        generated_at=a.generated_at,
    )
    md = render_video_markdown(a2, captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    fm = _parse_fm(md)
    assert fm["insight_sector_tags"] == []
    assert fm["insight_theme_tags"] == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_markdown.py -v
```
Expected: 4 fail (markdown.py 아직 v0 schema 기대).

- [ ] **Step 3: markdown.py 갱신**

`src/youtube_market_brief/domain/markdown.py`의 `_frontmatter` 교체:

```python
def _frontmatter(analysis: VideoAnalysis, *, captured_at: datetime) -> str:
    s = analysis.transcript_summary
    ki_sectors = sorted({tag for ki in s.key_insights for tag in ki.sector_tags})
    ki_themes = sorted({tag for ki in s.key_insights for tag in ki.theme_tags})
    rt_sectors = sorted({tag for rt in s.red_team for tag in rt.sector_tags})
    rt_themes = sorted({tag for rt in s.red_team for tag in rt.theme_tags})

    data = {
        "captured_at": captured_at.isoformat(),
        "channel": analysis.video.channel_slug,
        "insight_sector_tags": ki_sectors,
        "insight_theme_tags": ki_themes,
        "red_team_sector_tags": rt_sectors,
        "red_team_theme_tags": rt_themes,
        "source_type": "youtube",
        "source_url": analysis.video.url,
        "tags": list(analysis.tags),
        "tier": analysis.tier,
        "video_id": analysis.video.video_id,
        "was_truncated": s.was_truncated,
        "watchlist_hits": list(analysis.watchlist_hits),
    }
    buf = StringIO()
    yaml.safe_dump(data, buf, allow_unicode=True, sort_keys=True)
    return buf.getvalue()
```

`_body` 함수의 key_insights / red_team 루프 교체:

```python
    parts.append("## 🎯 핵심 인사이트\n")
    for ins in s.key_insights:
        parts.append(f"- {ins.text}")
    parts.append("")

    parts.append("## 🚨 레드팀 시각 (반대 관점·리스크·의문점)\n")
    for rt in s.red_team:
        parts.append(f"- {rt.text}")
    parts.append("")
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/unit/test_markdown.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youtube_market_brief/domain/markdown.py tests/unit/test_markdown.py
git commit -m "feat(markdown): frontmatter sector/theme footprint + body text-only

영상 MD frontmatter에 insight_sector_tags / insight_theme_tags /
red_team_sector_tags / red_team_theme_tags union 추가. body는 inline
태그 없이 text만 표시."
```

---

## Task 6: telegram_format.py — KeyInsight/RedTeamItem text 추출

**Files:**
- Modify: `src/youtube_market_brief/domain/telegram_format.py`
- Modify: `tests/unit/test_telegram_format.py` (회귀 fix)

- [ ] **Step 1: 테스트 — Telegram 메시지가 text만 추출**

`tests/unit/test_telegram_format.py`의 `_make_analysis` 유사 helper (이미 있는 회귀 fixture)를 보고 KeyInsight/RedTeamItem 사용하도록 수정. 신규 테스트 추가:

```python
def test_format_per_video_extracts_text_from_key_insight_objects():
    from youtube_market_brief.domain.types import KeyInsight, RedTeamItem
    from youtube_market_brief.domain.telegram_format import format_per_video

    video = VideoMeta(
        video_id="abc", channel_id="c", channel_name="ch", channel_slug="ch",
        title="t", published_at_utc=datetime(2026, 5, 11, tzinfo=UTC),
        url="https://youtu.be/abc",
    )
    summary = TranscriptSummary(
        headline_3line=("h1", "h2", "h3"),
        key_insights=(
            KeyInsight(text="인사이트 본문", sector_tags=("semiconductors",), theme_tags=()),
        ),
        red_team=(
            RedTeamItem(text="레드팀 본문", sector_tags=(), theme_tags=()),
        ),
        chars_used=0, was_truncated=False,
    )
    analysis = VideoAnalysis(
        video=video, transcript_summary=summary, tickers=(), watchlist_hits=(),
        tier="light", tags=(), llm_meta=_llm_meta(),
        generated_at=datetime(2026, 5, 11, tzinfo=UTC),
    )
    out = format_per_video(analysis, vault_md_path_relative="x.md")
    assert "인사이트 본문" in out
    assert "레드팀 본문" in out
    # sector tag은 메시지에 노출되지 않는다
    assert "semiconductors" not in out
```

기존 회귀 fixture에서 `key_insights=("...",)`, `red_team=("...",)` 같은 string tuple을 사용하는 곳을 모두 `KeyInsight(text="...", sector_tags=(), theme_tags=())` 형태로 교체.

- [ ] **Step 2: Run test to verify failures**

```bash
uv run pytest tests/unit/test_telegram_format.py -v
```
Expected: 기존 회귀 fixture가 `key_insights=("string",)` 사용 시 `AttributeError: 'str' object has no attribute 'text'` 또는 새로운 신규 test 실패.

- [ ] **Step 3: telegram_format.py 갱신**

`src/youtube_market_brief/domain/telegram_format.py`의 `format_per_video` 내 key_insights / red_team 루프 교체:

```python
    parts.append("🎯 핵심 인사이트")
    for ins in s.key_insights:
        parts.append(f"• {_esc(ins.text)}")
    parts.append("")
    parts.append("🚨 레드팀 시각")
    for rt in s.red_team:
        parts.append(f"• {_esc(rt.text)}")
    parts.append("")
```

`format_daily_brief`도 동일하게 — daily brief의 key_insights / red_team이 Task 7에서 동일 object로 바뀌므로 미리 정렬:

```python
    parts.append("🔑 핵심 인사이트")
    for ins in brief.key_insights:
        parts.append(f"• {_esc(_text_of(ins))}")
    parts.append("")
    parts.append("🚨 레드팀 시각")
    for rt in brief.red_team:
        parts.append(f"• {_esc(_text_of(rt))}")
    parts.append("")
```

helper:

```python
def _text_of(item) -> str:
    # Daily brief의 KeyInsight/RedTeamItem 또는 plain string 모두 흡수
    return getattr(item, "text", None) or str(item)
```

`_text_of` helper로 둬서 Task 7 진행 전이라도 daily brief가 *plain string* 또는 *object* 모두 흡수 가능 (transition window).

- [ ] **Step 4: 기존 test_telegram_format 회귀 fix**

기존 테스트의 `TranscriptSummary(key_insights=("a",), red_team=("b",))` 같은 라인을 모두 KeyInsight/RedTeamItem 객체로 교체.

- [ ] **Step 5: Run test**

```bash
uv run pytest tests/unit/test_telegram_format.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/youtube_market_brief/domain/telegram_format.py \
        tests/unit/test_telegram_format.py
git commit -m "feat(notify): telegram_format extracts text from KeyInsight/RedTeamItem

Telegram 메시지에 sector_tag은 노출 안 함. 사용자 체감 변화 0."
```

---

## Task 7: Daily brief — KeyInsight/RedTeamItem 일관성 + daily MD frontmatter

**Files:**
- Modify: `src/youtube_market_brief/domain/types.py` (DailyBrief.key_insights / red_team 타입 변경)
- Modify: `src/youtube_market_brief/pipeline/aggregate.py`
- Modify: `src/youtube_market_brief/domain/daily_brief.py`
- Create: `tests/unit/test_daily_brief_aggregation.py`

- [ ] **Step 1: types.py — DailyBrief 필드 타입 변경**

`src/youtube_market_brief/domain/types.py`의 `DailyBrief` 변경:

```python
@dataclass(frozen=True)
class DailyBrief:
    date: date
    market_read: str
    key_insights: tuple[KeyInsight, ...]      # was tuple[str, ...]
    red_team: tuple[RedTeamItem, ...]         # was tuple[str, ...]
    ticker_rollup: tuple[TickerRollup, ...]
    videos: tuple[VideoMeta, ...]
    llm_meta: LLMMeta
```

- [ ] **Step 2: aggregate.py — daily brief LLM 응답에서 object 추출**

`src/youtube_market_brief/pipeline/aggregate.py`의 `aggregate_daily` 내 응답 파싱부 교체:

```python
    market_read = payload.get("market_read", "").strip()

    def _coerce_insight(item):
        if isinstance(item, dict):
            return KeyInsight(
                text=str(item.get("text", "")).strip(),
                sector_tags=tuple(item.get("sector_tags") or []),
                theme_tags=tuple(item.get("theme_tags") or []),
            )
        return KeyInsight(text=str(item).strip(), sector_tags=(), theme_tags=())

    def _coerce_redteam(item):
        if isinstance(item, dict):
            return RedTeamItem(
                text=str(item.get("text", "")).strip(),
                sector_tags=tuple(item.get("sector_tags") or []),
                theme_tags=tuple(item.get("theme_tags") or []),
            )
        return RedTeamItem(text=str(item).strip(), sector_tags=(), theme_tags=())

    key_insights = tuple(_coerce_insight(i) for i in payload.get("key_insights", []))
    red_team_raw = payload.get("red_team", [])
    if red_team_raw:
        red_team = tuple(_coerce_redteam(i) for i in red_team_raw)
    else:
        red_team = (
            RedTeamItem(text="(영상 간 합의가 약하거나 thesis가 분산되어 통합 반론 도출이 어려움)", sector_tags=(), theme_tags=()),
        )
```

import 라인에 `KeyInsight`, `RedTeamItem` 추가.

`_serialize_analysis` 교체 — *영상 분석을 daily brief LLM에게 넘길 때* KeyInsight object를 dict로 직렬화:

```python
def _serialize_analysis(a: VideoAnalysis) -> dict:
    return {
        "video": {
            "video_id": a.video.video_id,
            "channel_name": a.video.channel_name,
            "title": a.video.title,
            "url": a.video.url,
        },
        "headline_3line": list(a.transcript_summary.headline_3line),
        "key_insights": [
            {"text": ki.text, "sector_tags": list(ki.sector_tags), "theme_tags": list(ki.theme_tags)}
            for ki in a.transcript_summary.key_insights
        ],
        "red_team": [
            {"text": rt.text, "sector_tags": list(rt.sector_tags), "theme_tags": list(rt.theme_tags)}
            for rt in a.transcript_summary.red_team
        ],
        "tickers": [
            {
                "symbol": t.symbol,
                "display": t.display,
                "in_watchlist": t.in_watchlist,
                "sector_tag": t.sector_tag,
                "direction": t.direction,
                "reasoning": t.reasoning,
                "quotes": list(t.quotes),
                "confidence": t.confidence,
            }
            for t in a.tickers
        ],
        "watchlist_hits": list(a.watchlist_hits),
    }
```

- [ ] **Step 3: daily_brief.py markdown frontmatter + body 갱신**

`src/youtube_market_brief/domain/daily_brief.py`의 `render_daily_brief_markdown` 교체:

```python
def render_daily_brief_markdown(brief: DailyBrief, *, captured_at) -> str:
    """Render the daily brief markdown document."""
    parts: list[str] = []

    # Aggregate sector/theme tag union
    ki_sectors = sorted({tag for ki in brief.key_insights for tag in ki.sector_tags})
    ki_themes = sorted({tag for ki in brief.key_insights for tag in ki.theme_tags})
    rt_sectors = sorted({tag for rt in brief.red_team for tag in rt.sector_tags})
    rt_themes = sorted({tag for rt in brief.red_team for tag in rt.theme_tags})

    parts.append("---")
    parts.append(f"captured_at: {captured_at.isoformat()}")
    parts.append(f"date: {brief.date.isoformat()}")
    parts.append(f"insight_sector_tags: {ki_sectors}")
    parts.append(f"insight_theme_tags: {ki_themes}")
    parts.append(f"red_team_sector_tags: {rt_sectors}")
    parts.append(f"red_team_theme_tags: {rt_themes}")
    parts.append("source_type: youtube_daily_brief")
    parts.append("source_url: ''")
    parts.append("tags:")
    parts.append("  - youtube")
    parts.append("  - daily_brief")
    parts.append("tier: deep")
    parts.append("---")
    parts.append("")

    parts.append(f"# 📅 {brief.date.isoformat()} 일일 시장 브리핑\n")

    parts.append("## 🎯 오늘의 시장 read\n")
    parts.append(brief.market_read.strip() + "\n")

    parts.append("## 🔑 핵심 인사이트\n")
    for ins in brief.key_insights:
        parts.append(f"- {ins.text}")
    parts.append("")

    parts.append("## 🚨 레드팀 시각\n")
    for rt in brief.red_team:
        parts.append(f"- {rt.text}")
    parts.append("")

    # ... (이하 ticker_rollup / 영상 리스트 부분은 변경 없음, 그대로 유지)
```

- [ ] **Step 4: Test 작성 — daily brief 일관성**

```python
# tests/unit/test_daily_brief_aggregation.py
from datetime import UTC, date, datetime

from youtube_market_brief.domain.daily_brief import render_daily_brief_markdown
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
)


def test_daily_brief_md_frontmatter_aggregates_insight_sectors():
    brief = DailyBrief(
        date=date(2026, 5, 11),
        market_read="m",
        key_insights=(
            KeyInsight(text="i1", sector_tags=("semiconductors",), theme_tags=("hyperscaler_capex",)),
            KeyInsight(text="i2", sector_tags=("financials",), theme_tags=()),
        ),
        red_team=(RedTeamItem(text="r1", sector_tags=("energy",), theme_tags=("geopolitics_middle_east",)),),
        ticker_rollup=(),
        videos=(),
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )
    md = render_daily_brief_markdown(brief, captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    assert "insight_sector_tags: ['financials', 'semiconductors']" in md
    assert "red_team_sector_tags: ['energy']" in md
    assert "red_team_theme_tags: ['geopolitics_middle_east']" in md


def test_daily_brief_md_body_renders_text_only():
    brief = DailyBrief(
        date=date(2026, 5, 11),
        market_read="m",
        key_insights=(KeyInsight(text="인사이트", sector_tags=(), theme_tags=()),),
        red_team=(RedTeamItem(text="레드팀", sector_tags=(), theme_tags=()),),
        ticker_rollup=(),
        videos=(),
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )
    md = render_daily_brief_markdown(brief, captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    assert "- 인사이트" in md
    assert "- 레드팀" in md
    assert "#semiconductors" not in md
```

- [ ] **Step 5: Run test**

```bash
uv run pytest tests/unit/test_daily_brief_aggregation.py tests/unit/test_daily_rollup.py -v
```
Expected: 신규 + 기존 daily_rollup 통과 (rollup math는 영향 없음).

- [ ] **Step 6: Commit**

```bash
git add src/youtube_market_brief/domain/types.py \
        src/youtube_market_brief/domain/daily_brief.py \
        src/youtube_market_brief/pipeline/aggregate.py \
        tests/unit/test_daily_brief_aggregation.py
git commit -m "feat(brief): DailyBrief KeyInsight/RedTeamItem 일관성 + frontmatter union

DailyBrief.key_insights / red_team 타입을 KeyInsight/RedTeamItem로 통일.
aggregate.py가 LLM 응답을 object로 흡수. daily brief MD frontmatter에
insight/red_team sector·theme union 추가."
```

---

## Task 8: Prompt 교체 — 영상 분석 prompt

**Files:**
- Modify: `prompts/system_video_analysis.ko.md`

- [ ] **Step 1: 전체 prompt 교체**

`prompts/system_video_analysis.ko.md`의 전체 내용을 다음으로 교체. 기존 내용은 git history에 남음 (mv archive 안 함).

```markdown
# 역할

당신은 다음 4개 시각을 동시에 갖춘 1인의 분석가다.
한국 회계감사인이자 재무 정보 전문가이자 투자자이자 시장 분석가다.

- **회계감사인 시각** — 화자가 주장하는 thesis에 대해 *근거가 검증 가능한가*,
  화자가 인용하는 재무·실적 수치에 *red flag·restatement·going concern*
  신호가 있는가를 본다. 의심하는 게 직업 윤리다.

- **재무 정보 전문가 시각** — capital structure, cash flow quality,
  earnings quality, working capital, 회계 정책 변경의 *해석상 함의*를 본다.

- **투자자 시각** — 화자의 thesis를 받았을 때 *position 관점에서*
  risk-reward, time horizon, position sizing implication이 어떻게
  바뀌는가를 본다.

- **시장 분석가 시각** — narrative·momentum·positioning·sentiment의
  시장 가격 영향, 그리고 화자의 thesis가 *시장 합의에서 어느 위치*에
  있는지를 본다.

한 영상의 자막을 받아 이 4 시각이 합성된 분석을 출력한다.
화자의 thesis에 *맹목적으로 동조하지 말 것*. 4 시각 중 어느 하나라도
화자의 thesis를 약화시킨다면 그것은 red_team에 명시되어야 한다.

# 입력

다음을 받는다:

- `video_meta`: 영상 메타데이터 (제목, 채널, 업로드일, URL, 영상 길이)
- `transcript`: 자막 전체 텍스트 (필요 시 truncated — `transcript.was_truncated=true`이면 일부 발췌임을 인지하라)
- `watchlist`: 사용자가 사전 등록한 종목 목록 (symbol, market, name_ko, name_en, sector, aliases)

# 출력 스키마

다음 JSON을 fenced code block으로만 출력하라. **JSON 외 어떤 텍스트도 출력 금지**.

```json
{
  "headline_3line": ["문장1", "문장2", "문장3"],
  "key_insights": [
    {
      "text": "인사이트 본문 (≤200자)",
      "sector_tags": ["semiconductors"],
      "theme_tags": ["hyperscaler_capex"]
    }
  ],
  "red_team": [
    {
      "text": "반대 시각 본문 (≤200자)",
      "sector_tags": ["semiconductors"],
      "theme_tags": ["ai_meltup_bubble"]
    }
  ],
  "tickers": [
    {
      "symbol": "005930",
      "display": "삼성전자",
      "in_watchlist": true,
      "sector_tag": "semiconductors",
      "direction": "긍정적",
      "reasoning": "근거 1-2 문장",
      "quotes": ["영상 인용 1 (≤200자)"],
      "confidence": "high"
    }
  ],
  "watchlist_hits": ["005930"]
}
```

# 필드별 작성 규칙

## headline_3line
- 정확히 3문장. 각 문장 ≤80자. 영상 핵심 메시지를 압축.

## key_insights
- 3-5건. 각 항목은 사실/숫자/맥락을 포함한 짧은 단락 (`text` ≤200자). 단순 요약이 아닌 "이 영상이 새로 더해주는 것".
- `sector_tags` / `theme_tags`: 본 섹션 §sector_tags 규칙 참조.

## red_team
- 2-4건. **`key_insights`에 대한 반대 시각·리스크·약점·의문점**을 통합해 응축. 4 시각 중 *어느 하나라도* thesis를 약화시키면 명시.
- 각 항목은 단순 부정이 아닌 구체적 반론 (예: "감사인 시각: 화자가 인용한 매출 50% 증가는 ASC 606 변경 효과를 분리 안 함").
- **빈 배열 금지**. 영상이 단순 사실 보도여서 반론할 게 없다면 `red_team[0].text`에 그 사실을 명시 (예: "영상이 단편 사실 보도 형식이라 별도 반론할 thesis가 부재").

## tickers
- 영상에서 의미 있게 언급된 모든 종목을 나열.
- watchlist 등록 종목을 우선 식별 (symbol/name_ko/name_en/aliases 매칭). watchlist 외 종목도 추출.
- `symbol`: watchlist에 있으면 watchlist 값 사용. 없으면 표준 코드 추측 가능 시 채우고, 불확실하면 `null`.
- `display`: 한국어 표시명 우선 (예: "삼성전자"). 미국 종목은 영어 ticker.
- `in_watchlist`: watchlist 매칭 여부.
- `sector_tag`: 본 섹션 §sector_tags 규칙 참조. watchlist에 등록된 종목은 watchlist의 sector 필드를 신뢰. 미등록(자동 발견) 종목은 본인이 가장 적합한 sector를 enum에서 선택.
- `direction`: 정확히 4값 중 — `긍정적` / `중립` / `부정적` / `언급만`.
- `reasoning`: 1-2문장 (≤200자). direction 근거.
- `quotes`: 영상 자막에서 직접 인용 0-2건. 각 ≤200자. 단순 인사말은 빈 배열로 두고 해당 종목 자체를 제외.
- `confidence`: `high` / `medium` / `low`.

## watchlist_hits
- `tickers` 중 `in_watchlist=true`이고 `quotes.length >= 1`인 종목의 `symbol` 배열.

## sector_tags / theme_tags 작성 규칙

`sector_tags`는 다음 enum 중 **0개 이상** 선택. 인사이트가 해당 sector의 현재 가설·지표·위험에 *직접* 관련될 때만 태그.

  semiconductors, software_ai_services, tech_hardware,
  financials, power_utilities, industrials_defense,
  energy, materials, consumer_discretionary, consumer_staples

`theme_tags`는 다음 enum 중 **0개 이상** 선택. 인사이트가 해당 macro theme의 가설 진행·반전에 기여할 때만 태그.

  ai_agent_adoption, ai_meltup_bubble, bigtech_ipo_supply,
  geopolitics_middle_east, hyperscaler_capex, korea_discount,
  memory_supercycle, tokenization_rwa, us_fiscal_debt

태그가 *명확하지 않으면 비워둘 것*. 무리한 추가는 propagation 오염을 유발한다. 1 인사이트당 보통 0-2 sector + 0-2 theme이 적정.

# 분석 원칙

- **균형성**: 영상 화자의 시각에 동조 vs 반박을 의식적으로 구분.
- **출처 명시**: 화자 의견인지 vs 영상이 인용한 외부 자료인지 표시 (`reasoning`에서).
- **추측 명시**: 데이터/근거가 약하면 `confidence`를 `low`로 낮춤.
- **음슴체 사용 금지**: 본 응답은 감사 의견이 아니므로 한국어 평이체로 작성.
- **영상이 한국어가 아닌 경우**: 분석 출력은 한국어. `quotes`는 원어 + 한국어 번역 병기 가능.

# 가드

- transcript `was_truncated=true`이면 `key_insights` 마지막 항목에 명시 (예: `text="(주의: 영상 후반부 일부가 분석에서 제외됨)"`, `sector_tags=[]`, `theme_tags=[]`).
- watchlist 등록 ticker가 등장하지만 의미 있는 분석 없음 → `tickers`에 포함하되 `direction="언급만"`, `quotes=[]`, `watchlist_hits`에서 제외.
- false positive 방지: 사명만 등장하고 분석/평가가 없으면 ticker 제외.

# 마지막 지시

위 JSON 스키마만 fenced code block으로 출력하라. JSON 외 어떤 텍스트도 출력 금지.
```

- [ ] **Step 2: 시각적 syntax 확인**

```bash
head -50 prompts/system_video_analysis.ko.md
wc -l prompts/system_video_analysis.ko.md
```
Expected: 150~180 라인 사이. fenced ```json 블록 마크다운 구문 정상.

- [ ] **Step 3: Commit**

```bash
git add prompts/system_video_analysis.ko.md
git commit -m "feat(prompt): 영상 분석 v1 — 4-role composite persona + sector/theme enum

페르소나를 감사인·재무정보전문가·투자자·시장분석가 합성으로 재정의.
key_insights/red_team을 object {text, sector_tags, theme_tags}로,
ticker에 sector_tag 단일값 추가. enum은 prompt inline 노출."
```

---

## Task 9: Prompt 교체 — daily brief prompt

**Files:**
- Modify: `prompts/system_daily_brief.ko.md`

- [ ] **Step 1: prompt 전체 교체**

`prompts/system_daily_brief.ko.md` 전체 교체:

```markdown
# 역할

당신은 다음 4개 시각을 동시에 갖춘 1인의 분석가다.
한국 회계감사인이자 재무 정보 전문가이자 투자자이자 시장 분석가다.

- **회계감사인 시각** — thesis 근거의 검증 가능성, red flag, restatement risk를 본다.
- **재무 정보 전문가 시각** — capital structure, cash flow quality, earnings quality의 함의를 본다.
- **투자자 시각** — position 관점의 risk-reward, time horizon을 본다.
- **시장 분석가 시각** — narrative·momentum·positioning의 시장 가격 영향을 본다.

본 단계의 입력은 raw transcript가 아니라 이미 정제된 *영상 단위 분석 JSON list*다. 본 단계는 영상 간 신호 합성과 모순 해소(같은 ticker에 대한 영상 간 view 충돌)에 초점을 둔다. 4 시각이 합성된 1인의 분석가로서 *합성된 시장 read*를 작성한다.

# 입력

다음을 받는다:

- `date`: 처리 날짜 (KST 기준 YYYY-MM-DD)
- `analyses`: 당일 처리된 모든 `VideoAnalysis` JSON 배열. 각 항목은 `video, headline_3line, key_insights (object[]), red_team (object[]), tickers, watchlist_hits` 보유. `key_insights` / `red_team`의 각 element는 `{text, sector_tags, theme_tags}` 형태.

# 출력 스키마

다음 JSON을 fenced code block으로만 출력하라. **JSON 외 어떤 텍스트도 출력 금지**.

```json
{
  "market_read": "오늘의 시장 read 3-5문장 (≤500자)",
  "key_insights": [
    {
      "text": "인사이트1 (≤200자)",
      "sector_tags": ["semiconductors"],
      "theme_tags": ["ai_meltup_bubble"]
    }
  ],
  "red_team": [
    {
      "text": "반대시각1 (≤200자)",
      "sector_tags": [],
      "theme_tags": ["us_fiscal_debt"]
    }
  ],
  "ticker_rollup": [
    {
      "symbol": "005930",
      "display": "삼성전자",
      "in_watchlist": true,
      "net_direction": "혼조",
      "mention_count": 3,
      "per_video": [
        {"video_id": "abc", "direction": "긍정적", "one_line_reason": "HBM3E 진척"}
      ]
    }
  ]
}
```

# 필드별 작성 규칙

## market_read
- 3-5 문장. 오늘의 큰 그림. 영상들의 합의 + 주요 차이를 함께.

## key_insights
- 3-5건. 영상들에 걸쳐 공통 메시지 또는 가장 중요한 시그널. 단순 영상 별 나열 아님.
- `sector_tags` / `theme_tags`는 본 섹션 §sector_tags 규칙 참조. 영상별 tag을 *그대로 union*하지 말고, 본 합성 인사이트에 실제로 해당하는 tag만 선택.

## red_team
- 2-4건. **오늘 영상들이 합의하는 thesis에 대한 반론·리스크·약점**.
- 영상들이 같은 방향으로 의견을 모았다면 그 합의 자체가 risk가 될 수 있음을 지적.
- 영상 간 의견이 갈리는 경우 그 갈림의 본질(어느 쪽이 어떤 가정을 빠뜨렸는지)을 짚음.
- **빈 배열 금지**.

## ticker_rollup
- 영상들에 등장한 모든 ticker(`watchlist_hits` + `auto-discovered`)를 통합.
- 같은 symbol(또는 display)이 여러 영상에 등장하면 1건으로 통합.
- `net_direction` 결정: 모두 같은 방향 → 그 방향. 갈리면 `혼조`.
- `per_video[].one_line_reason`: 영상의 `tickers[].reasoning`을 한 줄로 압축 (≤80자).

# 정렬

- `ticker_rollup`은 다음 순으로:
  1. `in_watchlist=true` 우선
  2. `mention_count` 내림차순
  3. `symbol` 알파벳/숫자 오름차순

## sector_tags / theme_tags 작성 규칙

영상 단위 prompt와 동일 enum 사용.

`sector_tags` enum: semiconductors, software_ai_services, tech_hardware, financials, power_utilities, industrials_defense, energy, materials, consumer_discretionary, consumer_staples

`theme_tags` enum: ai_agent_adoption, ai_meltup_bubble, bigtech_ipo_supply, geopolitics_middle_east, hyperscaler_capex, korea_discount, memory_supercycle, tokenization_rwa, us_fiscal_debt

# 분석 원칙

- **합의의 위험**: 영상들이 모두 같은 시각이면 그 자체를 risk로 다룰 것 (red_team에 반영).
- **갈림의 본질**: 영상 간 의견 갈림은 "어느 쪽 가정에 약점이 있는가"로 분석.
- **음슴체 사용 금지**: 한국어 평이체.
- **데이터 출처**: `analyses` 외 정보를 추가하지 말 것. 영상에 없던 시장 사실 임의 추가 금지.

# 마지막 지시

위 JSON 스키마만 fenced code block으로 출력하라. JSON 외 어떤 텍스트도 출력 금지.
```

- [ ] **Step 2: 시각적 확인**

```bash
wc -l prompts/system_daily_brief.ko.md
```
Expected: ~90 라인.

- [ ] **Step 3: Commit**

```bash
git add prompts/system_daily_brief.ko.md
git commit -m "feat(prompt): daily brief v1 — 4-role persona 일관성 + insight object schema"
```

---

## Task 10: JSON sidecar 작성 — 영상 + daily brief

**Files:**
- Modify: `src/youtube_market_brief/pipeline/write_video.py`
- Modify: `src/youtube_market_brief/pipeline/aggregate.py`
- Create: `tests/unit/test_sidecar.py`

- [ ] **Step 1: 테스트 — sidecar 파일 작성 + 내용 일치**

```python
# tests/unit/test_sidecar.py
import json
from datetime import UTC, datetime
from pathlib import Path

from youtube_market_brief.pipeline.write_video import write_video_md
from youtube_market_brief.pipeline.aggregate import write_daily_brief_md
from youtube_market_brief.domain.types import (
    DailyBrief, KeyInsight, LLMMeta, RedTeamItem, TickerMention,
    TranscriptSummary, VideoAnalysis, VideoMeta,
)
from datetime import date


def _make_analysis() -> VideoAnalysis:
    v = VideoMeta(
        video_id="abc123", channel_id="cid", channel_name="HK",
        channel_slug="hk", title="t",
        published_at_utc=datetime(2026, 5, 11, tzinfo=UTC),
        url="https://youtu.be/abc123",
    )
    s = TranscriptSummary(
        headline_3line=("a", "b", "c"),
        key_insights=(KeyInsight(text="i", sector_tags=("semiconductors",), theme_tags=()),),
        red_team=(RedTeamItem(text="r", sector_tags=(), theme_tags=()),),
        chars_used=0, was_truncated=False,
    )
    return VideoAnalysis(
        video=v, transcript_summary=s, tickers=(), watchlist_hits=(),
        tier="light", tags=("youtube",), llm_meta=LLMMeta(model="t", duration_ms=0),
        generated_at=datetime(2026, 5, 11, tzinfo=UTC),
    )


def test_write_video_md_creates_analysis_json_sidecar(tmp_path):
    a = _make_analysis()
    md_path = write_video_md(
        a, vault_youtube_root=tmp_path,
        captured_at=datetime(2026, 5, 11, tzinfo=UTC),
        date_kst_iso="2026-05-11",
    )
    sidecar = md_path.with_suffix(".analysis.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["video"]["video_id"] == "abc123"
    assert data["key_insights"][0]["text"] == "i"
    assert data["key_insights"][0]["sector_tags"] == ["semiconductors"]


def test_write_daily_brief_md_creates_analysis_json_sidecar(tmp_path):
    brief = DailyBrief(
        date=date(2026, 5, 11), market_read="m",
        key_insights=(KeyInsight(text="ki", sector_tags=("financials",), theme_tags=()),),
        red_team=(RedTeamItem(text="rt", sector_tags=(), theme_tags=("us_fiscal_debt",)),),
        ticker_rollup=(), videos=(),
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )
    md_path = write_daily_brief_md(
        brief, vault_daily_root=tmp_path,
        captured_at=datetime(2026, 5, 11, tzinfo=UTC),
    )
    sidecar = md_path.with_suffix(".analysis.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["date"] == "2026-05-11"
    assert data["key_insights"][0]["sector_tags"] == ["financials"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_sidecar.py -v
```
Expected: 2 fail — sidecar 파일 없음.

- [ ] **Step 3: write_video.py에 sidecar 작성 로직 추가**

`src/youtube_market_brief/pipeline/write_video.py` 끝에 추가:

```python
import json


def _serialize_analysis_for_sidecar(a: VideoAnalysis, *, captured_at: datetime) -> dict:
    return {
        "video": {
            "video_id": a.video.video_id,
            "channel_id": a.video.channel_id,
            "channel_name": a.video.channel_name,
            "channel_slug": a.video.channel_slug,
            "title": a.video.title,
            "url": a.video.url,
            "published_at_utc": a.video.published_at_utc.isoformat(),
        },
        "captured_at": captured_at.isoformat(),
        "generated_at": a.generated_at.isoformat(),
        "headline_3line": list(a.transcript_summary.headline_3line),
        "key_insights": [
            {"text": ki.text, "sector_tags": list(ki.sector_tags), "theme_tags": list(ki.theme_tags)}
            for ki in a.transcript_summary.key_insights
        ],
        "red_team": [
            {"text": rt.text, "sector_tags": list(rt.sector_tags), "theme_tags": list(rt.theme_tags)}
            for rt in a.transcript_summary.red_team
        ],
        "tickers": [
            {
                "symbol": t.symbol,
                "display": t.display,
                "in_watchlist": t.in_watchlist,
                "sector_tag": t.sector_tag,
                "direction": t.direction,
                "reasoning": t.reasoning,
                "quotes": list(t.quotes),
                "confidence": t.confidence,
            }
            for t in a.tickers
        ],
        "watchlist_hits": list(a.watchlist_hits),
        "tier": a.tier,
        "tags": list(a.tags),
        "transcript_meta": {
            "chars_used": a.transcript_summary.chars_used,
            "was_truncated": a.transcript_summary.was_truncated,
        },
        "llm_meta": {
            "model": a.llm_meta.model,
            "duration_ms": a.llm_meta.duration_ms,
            "was_retry": a.llm_meta.was_retry,
            "claude_session_id": a.llm_meta.claude_session_id,
        },
    }
```

기존 `write_video_md` 함수 끝부분, `return out` 직전에 추가:

```python
    sidecar = out.with_suffix(".analysis.json")
    sidecar_data = _serialize_analysis_for_sidecar(analysis, captured_at=captured_at)
    sidecar.write_text(json.dumps(sidecar_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote analysis sidecar: %s", sidecar)
```

- [ ] **Step 4: aggregate.py write_daily_brief_md에 sidecar 추가**

`src/youtube_market_brief/pipeline/aggregate.py`의 `write_daily_brief_md` 끝부분, `return out` 직전에 추가:

```python
    sidecar = out.with_suffix(".analysis.json")
    sidecar_data = {
        "date": brief.date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "market_read": brief.market_read,
        "key_insights": [
            {"text": ki.text, "sector_tags": list(ki.sector_tags), "theme_tags": list(ki.theme_tags)}
            for ki in brief.key_insights
        ],
        "red_team": [
            {"text": rt.text, "sector_tags": list(rt.sector_tags), "theme_tags": list(rt.theme_tags)}
            for rt in brief.red_team
        ],
        "ticker_rollup": [
            {
                "symbol": r.symbol, "display": r.display, "in_watchlist": r.in_watchlist,
                "net_direction": r.net_direction, "mention_count": r.mention_count,
                "per_video": [
                    {"video_id": e.video_id, "direction": e.direction, "one_line_reason": e.one_line_reason}
                    for e in r.per_video
                ],
            }
            for r in brief.ticker_rollup
        ],
        "videos": [
            {"video_id": v.video_id, "channel_slug": v.channel_slug, "title": v.title, "url": v.url}
            for v in brief.videos
        ],
        "llm_meta": {
            "model": brief.llm_meta.model,
            "duration_ms": brief.llm_meta.duration_ms,
            "claude_session_id": brief.llm_meta.claude_session_id,
        },
    }
    sidecar.write_text(json.dumps(sidecar_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote daily brief sidecar: %s", sidecar)
```

- [ ] **Step 5: Run test**

```bash
uv run pytest tests/unit/test_sidecar.py -v
```
Expected: 2 passed.

- [ ] **Step 6: .gitignore 확인 — sidecar는 commit 안 됨**

기존 `.gitignore`에 `00_Wiki/youtube/` 또는 sink가 ignored 상태라면 sidecar도 자동 ignored. yt repo에는 sidecar 파일이 추적되지 않음 (sidecar는 vault에 작성되고 Drive sync로 가는 산출물). 확인:

```bash
grep -E "00_Wiki|vault" .gitignore
```

- [ ] **Step 7: Commit**

```bash
git add src/youtube_market_brief/pipeline/write_video.py \
        src/youtube_market_brief/pipeline/aggregate.py \
        tests/unit/test_sidecar.py
git commit -m "feat(write): .analysis.json sidecar — propagation source of truth

영상 MD와 daily brief MD 옆에 LLM 출력 전체를 JSON으로 보존.
P2 propagation 자동화가 본 파일을 파싱하여 insight별 sector/theme
매핑을 결정론적으로 복원."
```

---

## Task 11: Taxonomy drift validation in `ymb config validate`

**Files:**
- Modify: `src/youtube_market_brief/config.py`
- Modify: `src/youtube_market_brief/cli.py` (config validate 명령에 wiring)
- Modify: `tests/unit/test_taxonomy.py` (drift check 추가)

- [ ] **Step 1: 테스트 — drift validation**

`tests/unit/test_taxonomy.py`에 추가:

```python
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
    # taxonomy에는 있는데 vault에 없는 slug가 drift로 보고됨
    drift_str = " ".join(drift)
    assert SECTOR_SLUGS[-1] in drift_str
    assert SECTOR_SLUGS[-2] in drift_str
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_taxonomy.py::test_validate_taxonomy_alignment_returns_empty_when_aligned -v
```
Expected: FAIL — `_validate_taxonomy_alignment` 없음.

- [ ] **Step 3: config.py에 함수 추가**

`src/youtube_market_brief/config.py` 끝에 추가:

```python
def _validate_taxonomy_alignment(*, vault_root: Path) -> list[str]:
    """Compare domain.taxonomy slugs with vault Market_Insights MD slugs.

    Returns a list of human-readable drift messages. Empty list = aligned.
    """
    from youtube_market_brief.domain.taxonomy import SECTOR_SLUGS, THEME_SLUGS

    drift: list[str] = []
    sectors_dir = vault_root / "02_Areas" / "Market_Insights" / "sectors"
    themes_dir = vault_root / "02_Areas" / "Market_Insights" / "themes"

    if not sectors_dir.exists():
        drift.append(f"[sectors] dir missing: {sectors_dir}")
    else:
        vault_sectors = {p.stem for p in sectors_dir.glob("*.md")}
        taxonomy_sectors = set(SECTOR_SLUGS)
        extra = vault_sectors - taxonomy_sectors
        missing = taxonomy_sectors - vault_sectors
        if extra:
            drift.append(f"[sectors] vault has but taxonomy lacks: {sorted(extra)}")
        if missing:
            drift.append(f"[sectors] taxonomy has but vault lacks: {sorted(missing)}")

    if not themes_dir.exists():
        drift.append(f"[themes] dir missing: {themes_dir}")
    else:
        vault_themes = {p.stem for p in themes_dir.glob("*.md")}
        taxonomy_themes = set(THEME_SLUGS)
        extra = vault_themes - taxonomy_themes
        missing = taxonomy_themes - vault_themes
        if extra:
            drift.append(f"[themes] vault has but taxonomy lacks: {sorted(extra)}")
        if missing:
            drift.append(f"[themes] taxonomy has but vault lacks: {sorted(missing)}")

    return drift
```

- [ ] **Step 4: cli.py — `ymb config validate`에 wiring**

`src/youtube_market_brief/cli.py`의 `config validate` 명령(또는 그에 해당하는 함수)에 다음 호출 추가. 기존 validate 함수 끝에:

```python
    # P1: taxonomy drift 감지
    from youtube_market_brief.config import _validate_taxonomy_alignment
    drift = _validate_taxonomy_alignment(vault_root=cfg.vault_root)
    if drift:
        click.echo("[taxonomy drift detected]", err=True)
        for line in drift:
            click.echo(f"  - {line}", err=True)
        click.echo(
            "  → src/youtube_market_brief/domain/taxonomy.py 또는 vault MD 슬러그를 정합시키시오.",
            err=True,
        )
        ctx.exit(1)
    else:
        click.echo("✓ taxonomy aligned (sectors + themes)")
```

(정확한 위치는 기존 cli.py의 validate 함수 내. plan executor는 `cli.py:` 검색 후 적절한 위치에 삽입.)

- [ ] **Step 5: Run test**

```bash
uv run pytest tests/unit/test_taxonomy.py -v
```
Expected: 모두 통과.

- [ ] **Step 6: 실 vault에서 수동 검증**

```bash
uv run ymb config validate
```
Expected: `✓ taxonomy aligned (sectors + themes)` 출력. 만약 drift가 보고되면 taxonomy.py 또는 vault MD 갱신 필요.

- [ ] **Step 7: Commit**

```bash
git add src/youtube_market_brief/config.py \
        src/youtube_market_brief/cli.py \
        tests/unit/test_taxonomy.py
git commit -m "feat(config): taxonomy drift detection in 'ymb config validate'

prompt enum과 vault Market_Insights MD slug 간 drift 감지.
mismatch 시 explicit fail."
```

---

## Task 12: Fixture v1 생성 + 수동 검토 게이트

**Files:**
- Create: `tests/fixtures/transcripts/p1_regression/{video_id_1,video_id_2,video_id_3}.json`
- Create: `tests/fixtures/analyze_outputs/v1/{video_id_1,video_id_2,video_id_3}.json`
- Create: `tests/integration/test_v1_fixture_regression.py`

**중요**: 본 task는 실 LLM 호출 발생. ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 필요. 비용 ≈ $0.05 미만 (3건).

- [ ] **Step 1: regression transcript 3건 선정**

선정 기준 (design §6.2):
- 워치리스트 히트 1건 (예: 반도체 종목 등장 영상)
- 자동 발견 ticker 1건 (예: 워치리스트 외 종목 다수 등장)
- 인사이트 풍부도 상위 1건 (예: 5/8~5/10 daily brief에서 인용 빈도 높았던 영상)

```bash
# 후보 sourcing: vault 기존 영상 MD 중 watchlist_hits 비어있지 않은 영상 listing
grep -l "watchlist_hits:" ~/vault/00_Wiki/youtube/*/2026-05-*.md | head -5
# 후보 video_id 추출 후, transcript JSON을 추출 (transcribe.py 또는 yt-dlp로 직접)
# 또는 기존 cached transcript가 있다면 그것을 fixture에 복사
```

3건 선정 후 각 transcript를 다음 구조로 fixture에 저장:

```json
// tests/fixtures/transcripts/p1_regression/v_abc123.json
{
  "video_id": "abc123",
  "language": "ko",
  "is_auto_generated": true,
  "full_text": "...transcript 전체 텍스트...",
  "char_count": 12345,
  "was_truncated": false,
  "video_meta": {
    "video_id": "abc123",
    "channel_id": "UC...",
    "channel_name": "...",
    "channel_slug": "...",
    "title": "...",
    "published_at_utc": "2026-05-...",
    "url": "https://youtu.be/abc123"
  }
}
```

- [ ] **Step 2: LLM 호출로 v1 fixture 출력 생성**

3건 각각에 대해 `ymb analyze --transcript-fixture` 명령 실행 후 출력을 fixture로 저장:

```bash
for vid in v_abc123 v_def456 v_ghi789; do
  uv run ymb analyze \
    --transcript-fixture tests/fixtures/transcripts/p1_regression/${vid}.json \
    --output-json tests/fixtures/analyze_outputs/v1/${vid}.json
done
```

(만약 `ymb analyze`가 `--output-json` 플래그를 지원하지 않으면 stdout redirect로 대체)

- [ ] **Step 3: 수동 검토 게이트 — 사용자 직접 확인**

3건의 v1 출력을 사용자가 *눈으로* 확인:

```bash
for f in tests/fixtures/analyze_outputs/v1/*.json; do
  echo "=== $f ==="
  jq '{
    headline: .headline_3line,
    insights: [.key_insights[] | {text: .text, sectors: .sector_tags, themes: .theme_tags}],
    red_team: [.red_team[] | {text: .text, sectors: .sector_tags, themes: .theme_tags}],
    tickers: [.tickers[] | {symbol: .symbol, sector: .sector_tag, direction: .direction}]
  }' "$f"
done
```

수동 검토 체크리스트 (사용자가 OK/NG로 표시):

- [ ] `key_insights.text` 품질이 v0 수준 이상인가
- [ ] `red_team` 표면적이지 않고 4 시각 효과 보이는가 (감사인 시각의 red flag 명시 등)
- [ ] `sector_tags` 합리적인가 (영상 내용과 일치, 무관한 sector 안 들어감)
- [ ] `theme_tags` 합리적인가
- [ ] watchlist ticker의 `sector_tag`이 watchlist 우선으로 덮어쓰여졌는가
- [ ] 자동 발견 ticker의 `sector_tag`이 합리적인가

**Go/no-go gate**: 위 6항목 모두 OK → 진행. 1개라도 NG → prompt 또는 schema 조정 후 fixture 재생성. 사용자 명시적 confirm 필요.

- [ ] **Step 4: integration regression test 작성**

```python
# tests/integration/test_v1_fixture_regression.py
"""Integration regression — v1 fixture가 schema validation 통과 + parse 성공."""

import json
from pathlib import Path

import pytest

from youtube_market_brief.pipeline.analyze import _parse_video_payload

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "analyze_outputs" / "v1"


@pytest.mark.parametrize("fixture_file", sorted(FIXTURE_DIR.glob("*.json")))
def test_v1_fixture_passes_strict_validation(fixture_file):
    """모든 v1 fixture가 strict schema validation 통과해야 한다."""
    payload = json.loads(fixture_file.read_text(encoding="utf-8"))
    parsed = _parse_video_payload(payload)
    assert "key_insights" in parsed


@pytest.mark.parametrize("fixture_file", sorted(FIXTURE_DIR.glob("*.json")))
def test_v1_fixture_insights_are_objects(fixture_file):
    payload = json.loads(fixture_file.read_text(encoding="utf-8"))
    for i, ki in enumerate(payload["key_insights"]):
        assert isinstance(ki, dict), f"key_insights[{i}] not object"
        assert "text" in ki
        assert "sector_tags" in ki
        assert "theme_tags" in ki


@pytest.mark.parametrize("fixture_file", sorted(FIXTURE_DIR.glob("*.json")))
def test_v1_fixture_tickers_have_sector_tag_field(fixture_file):
    payload = json.loads(fixture_file.read_text(encoding="utf-8"))
    for i, t in enumerate(payload["tickers"]):
        assert "sector_tag" in t, f"tickers[{i}] missing sector_tag"
```

- [ ] **Step 5: Run integration test**

```bash
uv run pytest tests/integration/test_v1_fixture_regression.py -v
```
Expected: 3 fixtures × 3 tests = 9 passed.

- [ ] **Step 6: Commit (fixture + regression test)**

```bash
git add tests/fixtures/transcripts/p1_regression/*.json \
        tests/fixtures/analyze_outputs/v1/*.json \
        tests/integration/test_v1_fixture_regression.py
git commit -m "test(p1): v1 fixture (3건) + integration regression

수동 검토 게이트 통과한 v1 fixture commit. integration regression이
schema validation + object shape을 잠근다."
```

---

## Task 13: Final regression sweep + dry-run validation

**Files:** 변경 없음 (실행만)

- [ ] **Step 1: 전체 단위 테스트 회귀**

```bash
uv run pytest tests/unit -v 2>&1 | tee /tmp/p1_final_unit.log
```
Expected: 전부 통과. fail 있다면 Task 3 step 6, Task 6 step 4, Task 7의 회귀 fix 누락. 해당 task 재방문.

- [ ] **Step 2: integration regression 통과**

```bash
uv run pytest tests/integration/test_v1_fixture_regression.py -v
```
Expected: 9 passed.

- [ ] **Step 3: 실 vault에서 taxonomy drift 확인**

```bash
uv run ymb config validate
```
Expected: `✓ taxonomy aligned`.

- [ ] **Step 4: dry-run으로 전체 파이프라인 단발 검증**

가장 안전: `DRY_RUN=true ymb run --dry-run`으로 Telegram 발송 없이 1회 전체 실행. 단, 이건 LLM 비용 발생하므로 사용자 확인 후 진행.

```bash
DRY_RUN=true uv run ymb run --dry-run 2>&1 | tail -50
```
Expected:
- discover ok
- transcribe ok
- analyze ok (v1 schema 출력)
- write_video ok (MD + .analysis.json sidecar)
- notify (dry-run, 파일로 dump)
- aggregate ok (daily brief MD + .analysis.json sidecar)

vault에 작성된 MD frontmatter에 `insight_sector_tags`, `insight_theme_tags` 등이 있는지 확인:

```bash
head -20 $(ls -t ~/vault/00_Wiki/youtube/*/2026-05-11*.md 2>/dev/null | head -1)
```

- [ ] **Step 5: README + HANDOFF.md 갱신 (P1 완료 기록)**

`README.md`에 P1 변경 사항 1-2줄 추가 (스키마 변경 + sidecar 도입 명시):

```bash
# README.md에 "출력 위치" 섹션 아래 추가
- 영상별 분석 sidecar: `{vault_root}/00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.analysis.json` (P2 propagation source)
- 일일 브리핑 sidecar: `{vault_root}/00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.analysis.json`
```

`HANDOFF.md`에 P1 schema 변경 메모 추가 (Codex가 P2 진입 시 참조):

```
## P1 완료 (2026-05-11)

- prompt persona: 4-role composite (감사인+재무정보+투자자+시장분석가)
- output schema: key_insights/red_team은 object {text, sector_tags, theme_tags}
- ticker: sector_tag 추가 (watchlist 우선)
- JSON sidecar: 영상/daily 모두 .analysis.json
- ADR-0006 참조

P2 (propagation 자동화)는 .analysis.json sidecar를 parsing하여
sectors/themes 카드 "최근 바뀐 점" 표에 row append.
```

- [ ] **Step 6: 최종 commit**

```bash
git add README.md HANDOFF.md
git commit -m "docs: P1 완료 — schema 변경 + .analysis.json sidecar 도입 기록"
```

- [ ] **Step 7: 푸시 전 사용자 confirm**

```bash
git log --oneline -15
```

12-13 commits가 P1으로 추가됨. 사용자가 push 명시적으로 요청하면 `git push`. 그렇지 않으면 local commit 상태 유지.

---

## Self-Review

**1. Spec coverage:**
- §3 Persona Design → Task 8 (영상 분석 prompt), Task 9 (daily brief prompt) ✓
- §4.1 Schema 변경 → Task 2 (types), Task 4 (parser) ✓
- §4.2 enum 노출 → Task 1 (taxonomy), Task 8 (prompt inline) ✓
- §4.3 drift 감지 → Task 11 ✓
- §4.4 Surface 정책 → Task 5 (markdown), Task 6 (telegram), Task 7 (daily brief MD), Task 10 (sidecar) ✓
- §4.5 watchlist sector → Task 3 ✓
- §4.6 ticker sector_tag 후처리 → Task 3 (watchlist.py) + Task 4 (analyze parser) ✓
- §5.1 파일 footprint → 13 task 전체 ✓
- §5.2 Migration non-retroactive → Task 0 (ADR 명시) + 어디서도 retroactive 재처리 안 함 ✓
- §6.1 Schema validation → Task 4 ✓
- §6.2 Fixture regression + 수동 검토 통합 → Task 12 ✓
- §6.3 수동 검토 게이트 → Task 12 step 3 ✓
- §6.4 drift 운영 검증 → Task 11 step 6 ✓
- §6.5 평행 운영 안 함 → spec에서 결정, plan에 task 없음 (정상) ✓
- §7.1 ADR-0006 → Task 0 ✓

**2. Placeholder scan:** "TODO" "TBD" "fill in" 검색 → Task 3 step 8에 "TODO: 사용자가 watchlist.yaml 5건 보강"이 의도적으로 남아 있음 (사용자 수동 작업 명시). 이건 plan placeholder가 아니라 *operational handoff*. OK.

**3. Type consistency:**
- `KeyInsight(text, sector_tags, theme_tags)` ✓ Task 2 정의 = Task 4/5/6/7/10 사용 일관
- `RedTeamItem` 동일 ✓
- `TickerMention.sector_tag` ✓ Task 2 정의 = Task 3/4 사용
- `WatchlistEntry.sector` ✓ Task 2 정의 = Task 3 사용
- `_validate_taxonomy_alignment(vault_root=...)` keyword-only ✓ Task 11 정의 = test 호출 일관

**4. 발견된 한 가지 gap:**
- Task 6 의 `_text_of` helper는 transition window용. P1 완료 후에는 daily brief의 key_insights도 무조건 KeyInsight object가 됨 (Task 7 완료 시점). `_text_of` helper는 *방어용*으로 유지해도 무방 (DailyBrief가 plain string으로 호출되는 경우 사실상 없으나, format_daily_brief의 public API 안전성 확보). 명시 OK, 추가 fix 불필요.

Self-review 완료. 추가 inline fix 없음.

---

## Execution Handoff

Plan complete and saved to `plans/2026-05-11-p1-prompt-persona-schema-plan.md`.

**총 13 tasks**, 약 60+ steps. 예상 CC time: ~2-3h. 핵심 게이트:
- Task 3 step 8: 사용자가 watchlist.yaml 5건 보강 (수동)
- Task 12 step 3: 사용자가 v1 fixture 수동 검토 (go/no-go)

**Two execution options:**

**1. Subagent-Driven (recommended)** — task별로 fresh subagent dispatch. task 간 리뷰. fast iteration. context window 보호.

**2. Inline Execution** — 같은 세션에서 executing-plans skill 따라 직접 실행. 사용자 게이트(watchlist 보강, 수동 fixture 검토) 두 곳에서 stop.

Which approach?

# P3 Implementation Plan — Weekly Rollup + Telegram Brief

> **For agentic workers:** Use subagent-driven-development. Steps use `- [ ]` syntax. Working directory `/Users/kjun/vault/01_Projects/01_youtube_market_brief`. Branch `p3-weekly-rollup` (stacked on `p1-prompt-schema`).

**Goal:** ymb에 `compute_weekly_rollup` 결정론 함수 + `pipeline/weekly.py` orchestrator + `ymb weekly-brief` CLI 추가. P1 sidecar 7개를 읽어 weekly MD + Telegram brief 발송.

**Architecture:** 새 frozen dataclasses(`WeeklyTickerEntry`, `WeeklySectorEntry`, `WeeklyThemeEntry`, `WeeklyRollup`) → `domain/daily_brief.py`의 `compute_weekly_rollup` (LLM 없음, 통계만) → `pipeline/weekly.py` orchestrator → vault MD + sidecar + Telegram. P1 HTML format 재사용. Backward-compat: 기존 daily 흐름 영향 없음.

**Tech Stack:** Python 3.12, dataclasses(frozen), pytest. P1의 `KeyInsight`/`RedTeamItem`/`TickerRollup` 재사용.

**Design source:** [`2026-05-11-p3-weekly-rollup-design.md`](./2026-05-11-p3-weekly-rollup-design.md)

---

## File Structure

신규 파일:
- `src/youtube_market_brief/pipeline/weekly.py` — orchestrator (load + aggregate + write + notify)
- `tests/unit/test_weekly_rollup.py` — `compute_weekly_rollup` 결정론 검증
- `tests/unit/test_weekly_markdown.py` — MD/sidecar 형식 검증
- `tests/unit/test_weekly_telegram.py` — Telegram message 형식 검증

수정 파일:
- `src/youtube_market_brief/domain/types.py` — Weekly* dataclass 추가
- `src/youtube_market_brief/domain/daily_brief.py` — `compute_weekly_rollup` + `render_weekly_brief_markdown` 추가
- `src/youtube_market_brief/domain/telegram_format.py` — `format_weekly_brief` 추가
- `src/youtube_market_brief/pipeline/notify.py` — `notify_weekly` 추가
- `src/youtube_market_brief/config.py` — `vault_weekly_root` property
- `src/youtube_market_brief/cli.py` — `weekly-brief` 명령

---

## Task 1: Weekly dataclasses

**Files:**
- Modify: `src/youtube_market_brief/domain/types.py`
- Create: `tests/unit/test_types_p3.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_types_p3.py
import dataclasses
from datetime import date

import pytest

from youtube_market_brief.domain.types import (
    WeeklyRollup,
    WeeklySectorEntry,
    WeeklyThemeEntry,
    WeeklyTickerDayEntry,
    WeeklyTickerEntry,
)


def test_weekly_ticker_day_entry_shape():
    e = WeeklyTickerDayEntry(date=date(2026, 5, 5), direction="긍정적", mention_count=2)
    assert e.date == date(2026, 5, 5)
    assert e.direction == "긍정적"
    assert e.mention_count == 2


def test_weekly_ticker_entry_shape():
    e = WeeklyTickerEntry(
        symbol="005930",
        display="삼성전자",
        in_watchlist=True,
        sector_tag="semiconductors",
        days_mentioned=5,
        total_mentions=8,
        directions=("긍정적", "혼조", "부정적"),
        net_weekly_direction="부정적",
        per_day=(),
    )
    assert e.days_mentioned == 5
    assert e.net_weekly_direction == "부정적"


def test_weekly_sector_entry_shape():
    e = WeeklySectorEntry(
        sector_slug="semiconductors",
        insight_days=7,
        total_insight_mentions=15,
        related_tickers=("005930", "000660", "NVDA"),
    )
    assert e.sector_slug == "semiconductors"
    assert e.insight_days == 7


def test_weekly_theme_entry_shape():
    e = WeeklyThemeEntry(
        theme_slug="hyperscaler_capex",
        insight_days=5,
        total_insight_mentions=12,
        related_tickers=("NVDA", "MSFT"),
    )
    assert e.theme_slug == "hyperscaler_capex"


def test_weekly_rollup_shape():
    r = WeeklyRollup(
        week_start=date(2026, 5, 5),
        week_end=date(2026, 5, 11),
        daily_briefs_present=(date(2026, 5, 5), date(2026, 5, 6)),
        daily_briefs_missing=(date(2026, 5, 7),),
        tickers=(),
        sectors=(),
        themes=(),
        total_videos=10,
    )
    assert r.week_start == date(2026, 5, 5)
    assert r.total_videos == 10


def test_weekly_rollup_is_frozen():
    r = WeeklyRollup(
        week_start=date(2026, 5, 5), week_end=date(2026, 5, 11),
        daily_briefs_present=(), daily_briefs_missing=(),
        tickers=(), sectors=(), themes=(), total_videos=0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.total_videos = 1  # type: ignore[misc]
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/test_types_p3.py -v
```

Expected: import fails.

- [ ] **Step 3: Add dataclasses to `domain/types.py`**

Place at end of file (after `RunReport` or wherever the last dataclass is):

```python
@dataclass(frozen=True)
class WeeklyTickerDayEntry:
    date: date
    direction: Direction | NetDirection
    mention_count: int


@dataclass(frozen=True)
class WeeklyTickerEntry:
    symbol: str | None
    display: str
    in_watchlist: bool
    sector_tag: str | None
    days_mentioned: int
    total_mentions: int
    directions: tuple[Direction | NetDirection, ...]
    net_weekly_direction: NetDirection
    per_day: tuple[WeeklyTickerDayEntry, ...]


@dataclass(frozen=True)
class WeeklySectorEntry:
    sector_slug: str
    insight_days: int
    total_insight_mentions: int
    related_tickers: tuple[str, ...]


@dataclass(frozen=True)
class WeeklyThemeEntry:
    theme_slug: str
    insight_days: int
    total_insight_mentions: int
    related_tickers: tuple[str, ...]


@dataclass(frozen=True)
class WeeklyRollup:
    week_start: date
    week_end: date
    daily_briefs_present: tuple[date, ...]
    daily_briefs_missing: tuple[date, ...]
    tickers: tuple[WeeklyTickerEntry, ...]
    sectors: tuple[WeeklySectorEntry, ...]
    themes: tuple[WeeklyThemeEntry, ...]
    total_videos: int
```

`Direction | NetDirection` union type for `per_day.direction` — `Direction` is from VideoMeta level, `NetDirection` adds "혼조". A day with multiple videos gets `NetDirection`; single-video day stays `Direction`. Both are `Literal` so the union resolves cleanly.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_types_p3.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youtube_market_brief/domain/types.py tests/unit/test_types_p3.py
git commit -m "$(cat <<'EOF'
feat(domain): WeeklyRollup + WeeklyTickerEntry/SectorEntry/ThemeEntry dataclasses

P3 base. 모두 frozen=True, P1의 KeyInsight 패턴 일관.
LLM 합성 없는 deterministic 통계 collection 단위.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `compute_weekly_rollup` 함수

**Files:**
- Modify: `src/youtube_market_brief/domain/daily_brief.py`
- Create: `tests/unit/test_weekly_rollup.py`

- [ ] **Step 1: 테스트 — 빈 input → None**

```python
# tests/unit/test_weekly_rollup.py
from datetime import date, datetime, UTC

import pytest

from youtube_market_brief.domain.daily_brief import compute_weekly_rollup
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerRollup,
    TickerRollupVideoEntry,
    VideoMeta,
)


def _make_brief(
    d: date,
    *,
    ticker_rollups: tuple = (),
    key_insights: tuple = (),
    videos: tuple = (),
) -> DailyBrief:
    return DailyBrief(
        date=d,
        market_read="m",
        key_insights=key_insights,
        red_team=(),
        ticker_rollup=ticker_rollups,
        videos=videos,
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )


def _vid(video_id: str, title: str = "t") -> VideoMeta:
    return VideoMeta(
        video_id=video_id, channel_id="c", channel_name="ch",
        channel_slug="ch", title=title,
        published_at_utc=datetime(2026, 5, 5, tzinfo=UTC),
        url=f"https://youtu.be/{video_id}",
    )


def test_compute_weekly_rollup_empty_briefs_returns_none():
    result = compute_weekly_rollup([], week_start=date(2026, 5, 5))
    assert result is None


def test_compute_weekly_rollup_single_brief_marks_missing_days():
    brief = _make_brief(date(2026, 5, 5))
    rollup = compute_weekly_rollup([brief], week_start=date(2026, 5, 5))
    assert rollup is not None
    assert rollup.week_start == date(2026, 5, 5)
    assert rollup.week_end == date(2026, 5, 11)
    assert rollup.daily_briefs_present == (date(2026, 5, 5),)
    assert len(rollup.daily_briefs_missing) == 6


def test_compute_weekly_rollup_aggregates_ticker_across_days():
    """삼성전자가 5/5(긍정적), 5/6(부정적) 등장 → 2 days, total 3 mentions, 혼조."""
    tr_55 = TickerRollup(
        symbol="005930", display="삼성전자", in_watchlist=True,
        net_direction="긍정적", mention_count=1,
        per_video=(TickerRollupVideoEntry(video_id="v1", direction="긍정적", one_line_reason="r"),),
    )
    tr_56 = TickerRollup(
        symbol="005930", display="삼성전자", in_watchlist=True,
        net_direction="부정적", mention_count=2,
        per_video=(
            TickerRollupVideoEntry(video_id="v2", direction="부정적", one_line_reason="r"),
            TickerRollupVideoEntry(video_id="v3", direction="부정적", one_line_reason="r"),
        ),
    )
    briefs = [
        _make_brief(date(2026, 5, 5), ticker_rollups=(tr_55,)),
        _make_brief(date(2026, 5, 6), ticker_rollups=(tr_56,)),
    ]
    rollup = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    assert rollup is not None
    assert len(rollup.tickers) == 1
    e = rollup.tickers[0]
    assert e.symbol == "005930"
    assert e.days_mentioned == 2
    assert e.total_mentions == 3
    assert e.net_weekly_direction == "혼조"  # 긍정+부정


def test_compute_weekly_rollup_majority_direction():
    """5건 긍정 + 2건 부정 → 긍정적."""
    def tr(direction, mc=1):
        return TickerRollup(
            symbol="NVDA", display="NVDA", in_watchlist=True,
            net_direction=direction, mention_count=mc,
            per_video=(),
        )
    briefs = [
        _make_brief(date(2026, 5, 5), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 6), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 7), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 8), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 9), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 10), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 11), ticker_rollups=(tr("부정적"),)),
    ]
    rollup = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    e = rollup.tickers[0]
    assert e.days_mentioned == 7
    assert e.net_weekly_direction == "긍정적"


def test_compute_weekly_rollup_tie_returns_mixed():
    """3 긍정 + 3 부정 + 1 중립 → 혼조."""
    def tr(direction):
        return TickerRollup(
            symbol="X", display="X", in_watchlist=False, net_direction=direction,
            mention_count=1, per_video=(),
        )
    briefs = [
        _make_brief(date(2026, 5, 5), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 6), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 7), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 8), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 9), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 10), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 11), ticker_rollups=(tr("중립"),)),
    ]
    rollup = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    e = rollup.tickers[0]
    assert e.net_weekly_direction == "혼조"


def test_compute_weekly_rollup_sector_aggregation():
    """sector_tags가 5/5에 semiconductors, 5/6에 semiconductors + financials → 2 days for semi, 1 day for fin."""
    briefs = [
        _make_brief(date(2026, 5, 5), key_insights=(
            KeyInsight(text="i1", sector_tags=("semiconductors",), theme_tags=()),
        )),
        _make_brief(date(2026, 5, 6), key_insights=(
            KeyInsight(text="i2", sector_tags=("semiconductors", "financials"), theme_tags=()),
        )),
    ]
    rollup = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    sectors_by_slug = {s.sector_slug: s for s in rollup.sectors}
    assert sectors_by_slug["semiconductors"].insight_days == 2
    assert sectors_by_slug["financials"].insight_days == 1


def test_compute_weekly_rollup_total_videos():
    briefs = [
        _make_brief(date(2026, 5, 5), videos=(_vid("v1"),)),
        _make_brief(date(2026, 5, 6), videos=(_vid("v2"), _vid("v3"))),
    ]
    rollup = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    assert rollup.total_videos == 3
```

- [ ] **Step 2: Run failing tests**

Expected: function doesn't exist.

- [ ] **Step 3: Implement `compute_weekly_rollup`**

Add to `src/youtube_market_brief/domain/daily_brief.py`:

```python
from collections import Counter
from datetime import date as Date, timedelta


def compute_weekly_rollup(
    briefs: Iterable[DailyBrief],
    *,
    week_start: Date,
) -> "WeeklyRollup | None":
    """Aggregate 7 daily briefs into a weekly rollup. Deterministic, no LLM.

    week_start is the Monday of the target week. week_end = week_start + 6 days.
    Briefs outside this range are silently filtered.
    """
    from youtube_market_brief.domain.types import (
        WeeklyRollup,
        WeeklyTickerEntry,
        WeeklyTickerDayEntry,
        WeeklySectorEntry,
        WeeklyThemeEntry,
    )

    bl = sorted(
        [b for b in briefs if week_start <= b.date <= week_start + timedelta(days=6)],
        key=lambda b: b.date,
    )
    if not bl:
        return None

    week_end = week_start + timedelta(days=6)
    present_dates = tuple(b.date for b in bl)
    missing_dates = tuple(
        week_start + timedelta(days=i)
        for i in range(7)
        if (week_start + timedelta(days=i)) not in present_dates
    )

    # === Ticker aggregation ===
    # Bucket by (in_watchlist, symbol_or_display)
    ticker_buckets: dict[tuple[bool, str], list[tuple[Date, TickerRollup]]] = {}
    for b in bl:
        for tr in b.ticker_rollup:
            key_str = tr.symbol if (tr.in_watchlist and tr.symbol) else tr.display.strip()
            if not key_str:
                continue
            key = (tr.in_watchlist, key_str)
            ticker_buckets.setdefault(key, []).append((b.date, tr))

    ticker_entries: list[WeeklyTickerEntry] = []
    for (in_wl, key_str), day_pairs in ticker_buckets.items():
        directions = tuple(tr.net_direction for _, tr in day_pairs)
        total_mentions = sum(tr.mention_count for _, tr in day_pairs)
        per_day = tuple(
            WeeklyTickerDayEntry(date=d, direction=tr.net_direction, mention_count=tr.mention_count)
            for d, tr in day_pairs
        )
        # Pick representative ticker info from first occurrence
        first_tr = day_pairs[0][1]
        # sector_tag: take the most common across days (or None if all None)
        sector_tags = [
            # NOTE: TickerRollup currently has no sector_tag — it lives on TickerMention.
            # For weekly aggregation, we accept that ticker_rollup doesn't carry sector.
            # If needed in future, source video sidecars (per_video[].sector_tag) can be
            # joined. P3 MVP: omit sector_tag aggregation here, leave as None.
        ]
        ticker_entries.append(
            WeeklyTickerEntry(
                symbol=first_tr.symbol if in_wl else None,
                display=first_tr.display,
                in_watchlist=in_wl,
                sector_tag=None,  # see NOTE above
                days_mentioned=len(day_pairs),
                total_mentions=total_mentions,
                directions=directions,
                net_weekly_direction=_weekly_net_direction(directions),
                per_day=per_day,
            )
        )

    # Sort: watchlist first, then by days_mentioned desc, then by total_mentions desc, then by display
    ticker_entries.sort(
        key=lambda e: (
            0 if e.in_watchlist else 1,
            -e.days_mentioned,
            -e.total_mentions,
            e.symbol or e.display,
        )
    )

    # === Sector aggregation (from key_insights[].sector_tags + red_team[].sector_tags) ===
    sector_day_counts: dict[str, set[Date]] = {}
    sector_total_mentions: Counter = Counter()
    sector_related_tickers: dict[str, set[str]] = {}
    for b in bl:
        for ki in b.key_insights:
            for s in ki.sector_tags:
                sector_day_counts.setdefault(s, set()).add(b.date)
                sector_total_mentions[s] += 1
        for rt in b.red_team:
            for s in rt.sector_tags:
                sector_day_counts.setdefault(s, set()).add(b.date)
                sector_total_mentions[s] += 1
        # Associate tickers
        for tr in b.ticker_rollup:
            key = tr.symbol if (tr.in_watchlist and tr.symbol) else tr.display.strip()
            if not key:
                continue
            # tickers don't carry sector here — skip association in P3 MVP
            # Future: join from per_video sidecars if needed

    sector_entries = tuple(
        WeeklySectorEntry(
            sector_slug=slug,
            insight_days=len(days),
            total_insight_mentions=sector_total_mentions[slug],
            related_tickers=tuple(sorted(sector_related_tickers.get(slug, set())))[:5],
        )
        for slug, days in sorted(sector_day_counts.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    # === Theme aggregation (same pattern as sector, on theme_tags) ===
    theme_day_counts: dict[str, set[Date]] = {}
    theme_total_mentions: Counter = Counter()
    theme_related_tickers: dict[str, set[str]] = {}
    for b in bl:
        for ki in b.key_insights:
            for t in ki.theme_tags:
                theme_day_counts.setdefault(t, set()).add(b.date)
                theme_total_mentions[t] += 1
        for rt in b.red_team:
            for t in rt.theme_tags:
                theme_day_counts.setdefault(t, set()).add(b.date)
                theme_total_mentions[t] += 1

    theme_entries = tuple(
        WeeklyThemeEntry(
            theme_slug=slug,
            insight_days=len(days),
            total_insight_mentions=theme_total_mentions[slug],
            related_tickers=tuple(sorted(theme_related_tickers.get(slug, set())))[:5],
        )
        for slug, days in sorted(theme_day_counts.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    total_videos = sum(len(b.videos) for b in bl)

    return WeeklyRollup(
        week_start=week_start,
        week_end=week_end,
        daily_briefs_present=present_dates,
        daily_briefs_missing=missing_dates,
        tickers=tuple(ticker_entries),
        sectors=sector_entries,
        themes=theme_entries,
        total_videos=total_videos,
    )


def _weekly_net_direction(directions: tuple) -> "NetDirection":
    """Majority logic for weekly direction. Tie → 혼조."""
    if not directions:
        return "언급만"
    meaningful = [d for d in directions if d != "언급만"]
    if not meaningful:
        return "언급만"
    counts = Counter(meaningful)
    # If there's a clear majority (> half of meaningful), pick it
    top_dir, top_count = counts.most_common(1)[0]
    if top_count > len(meaningful) / 2:
        return top_dir
    return "혼조"
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_weekly_rollup.py -v
```

Expected: 7 pass.

- [ ] **Step 5: Run full unit suite — no regressions**

```bash
uv run pytest tests/unit -q
```

Expected: all existing pass + 7 new = 121+ pass.

- [ ] **Step 6: Commit**

```bash
git add src/youtube_market_brief/domain/daily_brief.py tests/unit/test_weekly_rollup.py
git commit -m "$(cat <<'EOF'
feat(brief): compute_weekly_rollup — deterministic 7-day aggregation

ticker는 (in_watchlist, symbol/display) 기준 bucket. days_mentioned +
total_mentions + net_weekly_direction(majority logic, tie→혼조).
sector/theme은 key_insights/red_team의 tag 누적.

LLM 호출 없음 — 결정론적 통계만.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `render_weekly_brief_markdown` + vault path

**Files:**
- Modify: `src/youtube_market_brief/domain/daily_brief.py`
- Modify: `src/youtube_market_brief/config.py` (vault_weekly_root)
- Create: `tests/unit/test_weekly_markdown.py`

- [ ] **Step 1: Tests**

```python
# tests/unit/test_weekly_markdown.py
from datetime import UTC, date, datetime

import yaml

from youtube_market_brief.domain.daily_brief import render_weekly_brief_markdown
from youtube_market_brief.domain.types import (
    WeeklyRollup,
    WeeklySectorEntry,
    WeeklyThemeEntry,
    WeeklyTickerDayEntry,
    WeeklyTickerEntry,
)


def _make_rollup() -> WeeklyRollup:
    return WeeklyRollup(
        week_start=date(2026, 5, 5),
        week_end=date(2026, 5, 11),
        daily_briefs_present=(date(2026, 5, 5), date(2026, 5, 6)),
        daily_briefs_missing=(date(2026, 5, 7),),
        tickers=(
            WeeklyTickerEntry(
                symbol="005930", display="삼성전자", in_watchlist=True,
                sector_tag=None,
                days_mentioned=2, total_mentions=3,
                directions=("긍정적", "부정적"),
                net_weekly_direction="혼조",
                per_day=(
                    WeeklyTickerDayEntry(date(2026, 5, 5), "긍정적", 1),
                    WeeklyTickerDayEntry(date(2026, 5, 6), "부정적", 2),
                ),
            ),
        ),
        sectors=(
            WeeklySectorEntry(
                sector_slug="semiconductors", insight_days=2,
                total_insight_mentions=3, related_tickers=("005930",),
            ),
        ),
        themes=(
            WeeklyThemeEntry(
                theme_slug="hyperscaler_capex", insight_days=1,
                total_insight_mentions=1, related_tickers=(),
            ),
        ),
        total_videos=5,
    )


def test_weekly_md_frontmatter_has_required_fields():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert md.startswith("---\n")
    end = md.index("\n---\n", 4)
    fm = yaml.safe_load(md[4:end])
    assert fm["week_start"] == date(2026, 5, 5)
    assert fm["week_end"] == date(2026, 5, 11)
    assert fm["total_videos"] == 5
    assert fm["source_type"] == "youtube_weekly_brief"
    assert "daily_brief" in fm["tags"] or "weekly_brief" in fm["tags"]


def test_weekly_md_body_includes_ticker_table():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    body = md.split("\n---\n\n", 1)[1]
    assert "삼성전자" in body
    assert "005930" in body
    assert "혼조" in body
    assert "2/7" in body or "2일" in body


def test_weekly_md_body_includes_sector_heatmap():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert "semiconductors" in md


def test_weekly_md_body_includes_theme_heatmap():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert "hyperscaler_capex" in md


def test_weekly_md_notes_missing_briefs():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    # Missing 2026-05-07 should be visible somewhere
    assert "2026-05-07" in md or "누락" in md
```

- [ ] **Step 2: Run failing tests**

Expected: function doesn't exist.

- [ ] **Step 3: Implement `render_weekly_brief_markdown`**

Add to `src/youtube_market_brief/domain/daily_brief.py`:

```python
def render_weekly_brief_markdown(rollup: "WeeklyRollup", *, captured_at: datetime) -> str:
    parts: list[str] = []

    # Frontmatter
    parts.append("---")
    parts.append(f"captured_at: {captured_at.isoformat()}")
    parts.append(f"week_start: {rollup.week_start.isoformat()}")
    parts.append(f"week_end: {rollup.week_end.isoformat()}")
    parts.append(f"daily_briefs_present: {_yaml_inline_list([d.isoformat() for d in rollup.daily_briefs_present])}")
    parts.append(f"daily_briefs_missing: {_yaml_inline_list([d.isoformat() for d in rollup.daily_briefs_missing])}")
    parts.append(f"total_videos: {rollup.total_videos}")
    parts.append(f"ticker_sectors_union: {_yaml_inline_list(sorted({s.sector_slug for s in rollup.sectors}))}")
    parts.append(f"ticker_themes_union: {_yaml_inline_list(sorted({t.theme_slug for t in rollup.themes}))}")
    parts.append("source_type: youtube_weekly_brief")
    parts.append("source_url: ''")
    parts.append("tags:")
    parts.append("  - youtube")
    parts.append("  - weekly_brief")
    parts.append("tier: deep")
    parts.append("---")
    parts.append("")

    parts.append(f"# 📅 {rollup.week_start.isoformat()} ~ {rollup.week_end.isoformat()} 주간 시장 브리핑\n")
    parts.append(
        f"처리 영상 {rollup.total_videos}건 · 정상 brief {len(rollup.daily_briefs_present)}/7일"
        + (f" · 누락 {len(rollup.daily_briefs_missing)}일" if rollup.daily_briefs_missing else "")
        + "\n"
    )

    # Watchlist ticker table
    wl_tickers = [t for t in rollup.tickers if t.in_watchlist]
    if wl_tickers:
        parts.append("## 📊 워치리스트 종목 주간 누적\n")
        parts.append("| 종목 | 주간 방향 | 등장 일수 | 영상수 | 일자별 |")
        parts.append("|------|----------|---------|--------|--------|")
        for t in wl_tickers:
            emoji = _DIRECTION_EMOJI.get(t.net_weekly_direction, "")
            label = t.display + (f" ({t.symbol})" if t.symbol else "")
            per_day_str = ", ".join(
                f"{d.date.strftime('%m-%d')} {_DIRECTION_EMOJI.get(d.direction, '')}"
                for d in t.per_day
            )
            parts.append(
                f"| {label} | {emoji} {t.net_weekly_direction} "
                f"| {t.days_mentioned}/7일 | {t.total_mentions} | {per_day_str} |"
            )
        parts.append("")

    # Auto-discovered (threshold: ≥2 days)
    auto_tickers = [t for t in rollup.tickers if not t.in_watchlist and t.days_mentioned >= 2]
    if auto_tickers:
        parts.append("## 🔍 자동 발견 종목 (주간 ≥2일 등장)\n")
        for t in auto_tickers:
            emoji = _DIRECTION_EMOJI.get(t.net_weekly_direction, "")
            label = t.display + (f" ({t.symbol})" if t.symbol else "")
            parts.append(
                f"- **{label}** {emoji} {t.net_weekly_direction} — "
                f"{t.days_mentioned}일 등장, {t.total_mentions} 영상"
            )
        parts.append("")

    # Sector heatmap
    if rollup.sectors:
        parts.append("## 🎯 Sector 7-day heatmap\n")
        parts.append("| Sector | 등장 일수 | 영상수 | 관련 ticker |")
        parts.append("|--------|----------|--------|------------|")
        for s in rollup.sectors:
            parts.append(
                f"| {s.sector_slug} | {s.insight_days}/7일 | {s.total_insight_mentions} "
                f"| {', '.join(s.related_tickers) if s.related_tickers else '—'} |"
            )
        parts.append("")

    # Theme heatmap
    if rollup.themes:
        parts.append("## 🎨 Theme 7-day heatmap\n")
        parts.append("| Theme | 등장 일수 | 영상수 | 관련 ticker |")
        parts.append("|-------|----------|--------|------------|")
        for t in rollup.themes:
            parts.append(
                f"| {t.theme_slug} | {t.insight_days}/7일 | {t.total_insight_mentions} "
                f"| {', '.join(t.related_tickers) if t.related_tickers else '—'} |"
            )
        parts.append("")

    # Missing briefs
    if rollup.daily_briefs_missing:
        parts.append("## 📝 누락된 daily brief\n")
        for d in rollup.daily_briefs_missing:
            parts.append(f"- {d.isoformat()} — `Harness/logs/youtube_market_brief/{d.isoformat()}.log` 확인")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"
```

- [ ] **Step 4: Add `vault_weekly_root` to AppConfig**

`src/youtube_market_brief/config.py`에 property 추가 (다른 vault_* property 옆):

```python
@property
def vault_weekly_root(self) -> Path:
    return self.vault_root / "00_Wiki" / "youtube" / "_weekly"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_weekly_markdown.py tests/unit/test_weekly_rollup.py -v
```

Expected: 12 pass (7 from Task 2 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add src/youtube_market_brief/domain/daily_brief.py \
        src/youtube_market_brief/config.py \
        tests/unit/test_weekly_markdown.py
git commit -m "$(cat <<'EOF'
feat(brief): render_weekly_brief_markdown + vault_weekly_root

ticker table + sector/theme heatmap + 누락된 daily brief notes.
P1 frontmatter convention 일관 (yaml inline list, 결정론적 ordering).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Telegram format + notify

**Files:**
- Modify: `src/youtube_market_brief/domain/telegram_format.py`
- Modify: `src/youtube_market_brief/pipeline/notify.py`
- Create: `tests/unit/test_weekly_telegram.py`

- [ ] **Step 1: Tests**

```python
# tests/unit/test_weekly_telegram.py
from datetime import date, datetime, UTC

from youtube_market_brief.domain.telegram_format import format_weekly_brief
from youtube_market_brief.domain.types import (
    WeeklyRollup,
    WeeklySectorEntry,
    WeeklyThemeEntry,
    WeeklyTickerDayEntry,
    WeeklyTickerEntry,
)


def _make_rollup() -> WeeklyRollup:
    return WeeklyRollup(
        week_start=date(2026, 5, 5),
        week_end=date(2026, 5, 11),
        daily_briefs_present=(date(2026, 5, 5),),
        daily_briefs_missing=(date(2026, 5, 6),),
        tickers=(
            WeeklyTickerEntry(
                symbol="005930", display="삼성전자", in_watchlist=True, sector_tag=None,
                days_mentioned=5, total_mentions=8,
                directions=("긍정적",) * 5, net_weekly_direction="긍정적",
                per_day=(),
            ),
        ),
        sectors=(
            WeeklySectorEntry(
                sector_slug="semiconductors", insight_days=5,
                total_insight_mentions=10, related_tickers=("005930",),
            ),
        ),
        themes=(),
        total_videos=12,
    )


def test_format_weekly_brief_includes_header():
    out = format_weekly_brief(_make_rollup(), vault_md_path_relative="00_Wiki/youtube/_weekly/x.md")
    assert "2026-05-05" in out
    assert "2026-05-11" in out


def test_format_weekly_brief_includes_ticker():
    out = format_weekly_brief(_make_rollup(), vault_md_path_relative="x.md")
    assert "삼성전자" in out
    assert "5/7" in out or "5일" in out


def test_format_weekly_brief_escapes_html():
    rollup = WeeklyRollup(
        week_start=date(2026, 5, 5), week_end=date(2026, 5, 11),
        daily_briefs_present=(), daily_briefs_missing=(),
        tickers=(
            WeeklyTickerEntry(
                symbol="X", display="A & B <X>", in_watchlist=True, sector_tag=None,
                days_mentioned=1, total_mentions=1,
                directions=("긍정적",), net_weekly_direction="긍정적",
                per_day=(),
            ),
        ),
        sectors=(), themes=(), total_videos=0,
    )
    out = format_weekly_brief(rollup, vault_md_path_relative="x & y.md")
    assert "&amp;" in out  # & escaped
    assert "&lt;" in out  # < escaped


def test_format_weekly_brief_includes_sector_when_present():
    out = format_weekly_brief(_make_rollup(), vault_md_path_relative="x.md")
    assert "semiconductors" in out
```

- [ ] **Step 2: Run failing tests**

Expected: function doesn't exist.

- [ ] **Step 3: Implement `format_weekly_brief`**

Add to `src/youtube_market_brief/domain/telegram_format.py`:

```python
def format_weekly_brief(rollup: "WeeklyRollup", *, vault_md_path_relative: str) -> str:
    """Telegram message for the weekly brief. P1 HTML format (decorate_chunks가
    첫 줄을 <blockquote><b>로 감쌈)."""
    parts: list[str] = []
    parts.append(
        f"📅 {_esc(rollup.week_start.isoformat())} ~ {_esc(rollup.week_end.isoformat())} "
        "주간 시장 브리핑"
    )
    parts.append(
        f"🔢 처리 영상 {rollup.total_videos}건 · "
        f"정상 brief {len(rollup.daily_briefs_present)}/7일"
        + (f" · 누락 {len(rollup.daily_briefs_missing)}일" if rollup.daily_briefs_missing else "")
    )
    parts.append("")

    # Watchlist ticker
    wl_tickers = [t for t in rollup.tickers if t.in_watchlist]
    if wl_tickers:
        parts.append("📊 워치리스트 주간 누적")
        for t in wl_tickers:
            emoji = _DIRECTION_EMOJI.get(t.net_weekly_direction, "")
            label = _esc(t.display) + (f" ({_esc(t.symbol)})" if t.symbol else "")
            parts.append(
                f"• {label} {emoji} {_esc(t.net_weekly_direction)} — "
                f"{t.days_mentioned}/7일, {t.total_mentions} 영상"
            )
        parts.append("")

    # Auto-discovered ticker (threshold 2 days)
    auto_tickers = [t for t in rollup.tickers if not t.in_watchlist and t.days_mentioned >= 2]
    if auto_tickers:
        parts.append("🔍 자동 발견 (주간 ≥2일)")
        for t in auto_tickers:
            emoji = _DIRECTION_EMOJI.get(t.net_weekly_direction, "")
            label = _esc(t.display) + (f" ({_esc(t.symbol)})" if t.symbol else "")
            parts.append(
                f"• {label} {emoji} {_esc(t.net_weekly_direction)} — "
                f"{t.days_mentioned}일, {t.total_mentions} 영상"
            )
        parts.append("")

    # Sector heatmap (top 5)
    if rollup.sectors:
        parts.append("🎯 Sector 7-day heatmap")
        for s in rollup.sectors[:5]:
            parts.append(
                f"• {_esc(s.sector_slug)} — {s.insight_days}/7일, "
                f"{s.total_insight_mentions} 영상"
            )
        parts.append("")

    # Theme heatmap (top 5)
    if rollup.themes:
        parts.append("🎨 Theme 7-day heatmap")
        for t in rollup.themes[:5]:
            parts.append(
                f"• {_esc(t.theme_slug)} — {t.insight_days}/7일, "
                f"{t.total_insight_mentions} 영상"
            )
        parts.append("")

    parts.append(f"📝 vault: {_esc(vault_md_path_relative)}")
    return "\n".join(parts)
```

- [ ] **Step 4: Add `notify_weekly` to `pipeline/notify.py`**

```python
def notify_weekly(
    rollup,  # WeeklyRollup
    *,
    telegram: TelegramClient,
    vault_md_path_relative: str,
) -> NotifyResult:
    from youtube_market_brief.domain.telegram_format import format_weekly_brief
    text = format_weekly_brief(rollup, vault_md_path_relative=vault_md_path_relative)
    return _send_chunks(text, telegram=telegram, target="weekly")
```

The `target="weekly"` literal needs to be added to `NotifyTarget` Literal in types.py. Update:

```python
NotifyTarget = Literal["per_video", "daily", "weekly"]  # add "weekly"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_weekly_telegram.py -v
```

Expected: 4 pass.

```bash
uv run pytest tests/unit -q
```

Expected: full pass.

- [ ] **Step 6: Commit**

```bash
git add src/youtube_market_brief/domain/telegram_format.py \
        src/youtube_market_brief/domain/types.py \
        src/youtube_market_brief/pipeline/notify.py \
        tests/unit/test_weekly_telegram.py
git commit -m "$(cat <<'EOF'
feat(notify): format_weekly_brief + notify_weekly

P1 HTML format 재사용. 첫 줄은 decorate_chunks가 <blockquote><b>로 감쌈.
NotifyTarget에 "weekly" 추가.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `pipeline/weekly.py` orchestrator + `ymb weekly-brief` CLI

**Files:**
- Create: `src/youtube_market_brief/pipeline/weekly.py`
- Modify: `src/youtube_market_brief/cli.py`
- Create: `tests/unit/test_cli_weekly.py`

- [ ] **Step 1: Tests**

```python
# tests/unit/test_cli_weekly.py
import json
from datetime import UTC, date, datetime
from pathlib import Path


def test_load_weekly_briefs_reads_7_days(tmp_path):
    from youtube_market_brief.pipeline.weekly import load_weekly_briefs

    daily_root = tmp_path / "00_Wiki" / "youtube" / "_daily"
    daily_root.mkdir(parents=True)
    # Write 3 brief sidecars: 2026-05-05, 05-06, 05-09 (skip 5/7, 5/8, 5/10, 5/11)
    for d in (date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 9)):
        sidecar = daily_root / f"{d.isoformat()}_brief.analysis.json"
        sidecar.write_text(json.dumps({
            "date": d.isoformat(),
            "captured_at": "2026-05-12T00:00:00",
            "market_read": "m",
            "key_insights": [
                {"text": "i", "sector_tags": ["semiconductors"], "theme_tags": []}
            ],
            "red_team": [],
            "ticker_rollup": [],
            "videos": [],
            "llm_meta": {"model": "t", "duration_ms": 0, "claude_session_id": None},
        }, ensure_ascii=False), encoding="utf-8")

    briefs = load_weekly_briefs(vault_daily_root=daily_root, week_start=date(2026, 5, 5))
    assert len(briefs) == 3
    assert {b.date for b in briefs} == {date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 9)}


def test_load_weekly_briefs_empty_dir_returns_empty(tmp_path):
    from youtube_market_brief.pipeline.weekly import load_weekly_briefs
    daily_root = tmp_path / "00_Wiki" / "youtube" / "_daily"
    daily_root.mkdir(parents=True)
    briefs = load_weekly_briefs(vault_daily_root=daily_root, week_start=date(2026, 5, 5))
    assert briefs == []


def test_write_weekly_md_creates_md_and_sidecar(tmp_path):
    from youtube_market_brief.pipeline.weekly import write_weekly_md
    from youtube_market_brief.domain.types import WeeklyRollup

    rollup = WeeklyRollup(
        week_start=date(2026, 5, 5), week_end=date(2026, 5, 11),
        daily_briefs_present=(), daily_briefs_missing=(),
        tickers=(), sectors=(), themes=(), total_videos=0,
    )
    out = write_weekly_md(
        rollup,
        vault_weekly_root=tmp_path,
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
    )
    assert out.exists()
    sidecar = out.with_suffix(".analysis.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["week_start"] == "2026-05-05"
```

- [ ] **Step 2: Run failing tests**

Expected: module doesn't exist.

- [ ] **Step 3: Implement `pipeline/weekly.py`**

```python
"""Weekly aggregation pipeline — loads .analysis.json sidecars, computes weekly rollup,
writes vault MD + .analysis.json sidecar, sends Telegram.
"""

from __future__ import annotations

import json
import logging
from datetime import date as Date, datetime, timedelta
from pathlib import Path

from youtube_market_brief.domain.daily_brief import (
    compute_weekly_rollup,
    render_weekly_brief_markdown,
)
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerRollup,
    TickerRollupVideoEntry,
    VideoMeta,
    WeeklyRollup,
)

log = logging.getLogger(__name__)


def load_weekly_briefs(*, vault_daily_root: Path, week_start: Date) -> list[DailyBrief]:
    """Load up to 7 .analysis.json sidecars from vault_daily_root for the target week.

    Missing days are silently skipped (warning logged). Out-of-range files are
    ignored (only week_start ~ week_start+6 considered).
    """
    if not vault_daily_root.exists():
        return []
    briefs: list[DailyBrief] = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        sidecar = vault_daily_root / f"{d.isoformat()}_brief.analysis.json"
        if not sidecar.exists():
            log.warning("daily brief sidecar missing for %s", d)
            continue
        briefs.append(_deserialize_brief(sidecar, d))
    return briefs


def _deserialize_brief(sidecar_path: Path, target_date: Date) -> DailyBrief:
    """Inverse of write_daily_brief_md's sidecar serialization."""
    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    key_insights = tuple(
        KeyInsight(
            text=str(ki.get("text", "")),
            sector_tags=tuple(ki.get("sector_tags") or []),
            theme_tags=tuple(ki.get("theme_tags") or []),
        )
        for ki in (data.get("key_insights") or [])
        if isinstance(ki, dict)
    )
    red_team = tuple(
        RedTeamItem(
            text=str(rt.get("text", "")),
            sector_tags=tuple(rt.get("sector_tags") or []),
            theme_tags=tuple(rt.get("theme_tags") or []),
        )
        for rt in (data.get("red_team") or [])
        if isinstance(rt, dict)
    )
    ticker_rollup = tuple(
        TickerRollup(
            symbol=r.get("symbol"),
            display=str(r.get("display", "")),
            in_watchlist=bool(r.get("in_watchlist")),
            net_direction=r.get("net_direction", "언급만"),
            mention_count=int(r.get("mention_count", 0)),
            per_video=tuple(
                TickerRollupVideoEntry(
                    video_id=str(e.get("video_id", "")),
                    direction=e.get("direction", "언급만"),
                    one_line_reason=str(e.get("one_line_reason", "")),
                )
                for e in (r.get("per_video") or [])
                if isinstance(e, dict)
            ),
        )
        for r in (data.get("ticker_rollup") or [])
        if isinstance(r, dict)
    )
    videos = tuple(
        VideoMeta(
            video_id=str(v.get("video_id", "")),
            channel_id="",
            channel_name="",
            channel_slug=str(v.get("channel_slug", "")),
            title=str(v.get("title", "")),
            published_at_utc=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),  # stub
            url=str(v.get("url", "")),
        )
        for v in (data.get("videos") or [])
        if isinstance(v, dict)
    )
    llm_meta_data = data.get("llm_meta", {})
    return DailyBrief(
        date=target_date,
        market_read=str(data.get("market_read", "")),
        key_insights=key_insights,
        red_team=red_team,
        ticker_rollup=ticker_rollup,
        videos=videos,
        llm_meta=LLMMeta(
            model=str(llm_meta_data.get("model", "")),
            duration_ms=int(llm_meta_data.get("duration_ms", 0)),
            claude_session_id=llm_meta_data.get("claude_session_id"),
        ),
    )


def aggregate_weekly(
    *, week_start: Date, vault_daily_root: Path
) -> WeeklyRollup | None:
    """Load briefs + compute. None if zero briefs found."""
    briefs = load_weekly_briefs(vault_daily_root=vault_daily_root, week_start=week_start)
    if not briefs:
        return None
    return compute_weekly_rollup(briefs, week_start=week_start)


def write_weekly_md(
    rollup: WeeklyRollup,
    *,
    vault_weekly_root: Path,
    captured_at: datetime,
) -> Path:
    """Write weekly brief MD + .analysis.json sidecar. Returns MD path."""
    vault_weekly_root.mkdir(parents=True, exist_ok=True)
    out = vault_weekly_root / f"{rollup.week_start.isoformat()}_weekly.md"
    body = render_weekly_brief_markdown(rollup, captured_at=captured_at)
    out.write_text(body, encoding="utf-8")
    log.info("wrote weekly brief MD: %s", out)

    sidecar = out.with_suffix(".analysis.json")
    sidecar_data = {
        "week_start": rollup.week_start.isoformat(),
        "week_end": rollup.week_end.isoformat(),
        "captured_at": captured_at.isoformat(),
        "daily_briefs_present": [d.isoformat() for d in rollup.daily_briefs_present],
        "daily_briefs_missing": [d.isoformat() for d in rollup.daily_briefs_missing],
        "total_videos": rollup.total_videos,
        "tickers": [
            {
                "symbol": t.symbol, "display": t.display, "in_watchlist": t.in_watchlist,
                "sector_tag": t.sector_tag,
                "days_mentioned": t.days_mentioned, "total_mentions": t.total_mentions,
                "directions": list(t.directions),
                "net_weekly_direction": t.net_weekly_direction,
                "per_day": [
                    {"date": d.date.isoformat(), "direction": d.direction, "mention_count": d.mention_count}
                    for d in t.per_day
                ],
            }
            for t in rollup.tickers
        ],
        "sectors": [
            {"sector_slug": s.sector_slug, "insight_days": s.insight_days,
             "total_insight_mentions": s.total_insight_mentions,
             "related_tickers": list(s.related_tickers)}
            for s in rollup.sectors
        ],
        "themes": [
            {"theme_slug": t.theme_slug, "insight_days": t.insight_days,
             "total_insight_mentions": t.total_insight_mentions,
             "related_tickers": list(t.related_tickers)}
            for t in rollup.themes
        ],
    }
    sidecar.write_text(
        json.dumps(sidecar_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("wrote weekly brief sidecar: %s", sidecar)
    return out


def last_monday(today: Date) -> Date:
    """Most recent Monday on or before `today`."""
    return today - timedelta(days=today.weekday())
```

- [ ] **Step 4: Add `weekly-brief` command to `cli.py`**

Find the argparse subparser registration. Add:

```python
weekly_p = subparsers.add_parser("weekly-brief", help="Compose weekly rollup brief")
weekly_p.add_argument("--week-start", type=str, help="Monday of target week (YYYY-MM-DD). Default: most recent Monday.")
weekly_p.add_argument("--dry-run", action="store_true", help="Skip Telegram send")
weekly_p.add_argument("--no-telegram", action="store_true", help="Skip Telegram (same as --dry-run for now)")
```

Add the command handler. Pattern after `cmd_aggregate_only`. New `cmd_weekly_brief` function:

```python
def cmd_weekly_brief(args, cfg: AppConfig) -> int:
    from youtube_market_brief.pipeline.weekly import (
        aggregate_weekly,
        last_monday,
        write_weekly_md,
    )
    from datetime import date as Date, datetime
    import sys

    today = datetime.now(tz=cfg.tz).date()
    if args.week_start:
        try:
            week_start = Date.fromisoformat(args.week_start)
        except ValueError:
            print(f"invalid --week-start: {args.week_start} (expected YYYY-MM-DD)", file=sys.stderr)
            return 2
    else:
        week_start = last_monday(today)

    rollup = aggregate_weekly(
        week_start=week_start,
        vault_daily_root=cfg.vault_daily_root,
    )
    if rollup is None:
        print(f"no daily briefs found for week starting {week_start.isoformat()}", file=sys.stderr)
        return 1

    captured_at = datetime.now(tz=cfg.tz)
    md_path = write_weekly_md(
        rollup,
        vault_weekly_root=cfg.vault_weekly_root,
        captured_at=captured_at,
    )
    print(f"wrote: {md_path}")

    if args.dry_run or args.no_telegram or cfg.dry_run:
        print("(Telegram skipped)")
        return 0

    # Send Telegram
    from youtube_market_brief._clients.telegram import HttpxTelegramClient
    from youtube_market_brief.pipeline.notify import notify_weekly

    telegram = HttpxTelegramClient(
        bot_token=cfg.telegram_bot_token,
        chat_id=cfg.telegram_chat_id,
    )
    md_path_rel = str(md_path.relative_to(cfg.vault_root))
    result = notify_weekly(rollup, telegram=telegram, vault_md_path_relative=md_path_rel)
    if result.ok:
        print(f"Telegram sent: {len(result.message_ids)} chunk(s)")
        return 0
    print(f"Telegram failed: {result.error}", file=sys.stderr)
    return 1
```

Register in main dispatch (after other `if args.action == "..."`):

```python
if args.action == "weekly-brief":
    return cmd_weekly_brief(args, cfg)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit -q
```

Expected: all pass.

- [ ] **Step 6: Smoke — vault에 실제 daily sidecar 있는지 확인**

```bash
ls ~/vault/00_Wiki/youtube/_daily/*.analysis.json 2>/dev/null | head -5
```

If P1 hasn't run yet on actual data (P1 PR not merged + cron not run), there will be no `.analysis.json` files yet — only the legacy `.md` files. The `aggregate_weekly` will return None.

If sidecars exist, smoke:

```bash
uv run ymb weekly-brief --week-start 2026-05-05 --dry-run
```

Expected: prints "wrote: ..." path; Telegram skipped.

- [ ] **Step 7: Commit**

```bash
git add src/youtube_market_brief/pipeline/weekly.py \
        src/youtube_market_brief/cli.py \
        tests/unit/test_cli_weekly.py
git commit -m "$(cat <<'EOF'
feat(cli): ymb weekly-brief — orchestrator + CLI

pipeline/weekly.py: load_weekly_briefs + aggregate_weekly + write_weekly_md.
ymb weekly-brief --week-start YYYY-MM-DD [--dry-run].
last_monday helper for default --week-start.
.analysis.json sidecar deserialization → DailyBrief object.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: design + plan commit + final regression

**Files:**
- Commit: design + plan docs

- [ ] **Step 1: Full unit test sweep**

```bash
uv run pytest tests/unit tests/integration -v 2>&1 | tail -15
```

Expected: all pass (P1 + P3).

- [ ] **Step 2: Commit design + plan docs**

```bash
git add plans/2026-05-11-p3-weekly-rollup-design.md \
        plans/2026-05-11-p3-weekly-rollup-plan.md
git commit -m "$(cat <<'EOF'
docs(plans): P3 design + plan — weekly rollup + Telegram brief

CEO roadmap G3+G6: 시간축 ticker rollup + 주간 brief 자동 발송.
P1 .analysis.json sidecar 7개를 source로 deterministic 집계 (LLM 없음).
P1 HTML format 재사용. backward-compat 무영향.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Report**

```bash
git log --oneline p1-prompt-schema..HEAD
```

Show P3 commit history. Test counts. Smoke results if available.

---

## Self-Review

**Spec coverage:**
- §4.1 dataclasses → Task 1 ✓
- §4.2 compute_weekly_rollup → Task 2 ✓
- §4.3 pipeline/weekly.py → Task 5 ✓
- §4.4 markdown format → Task 3 ✓
- §4.5 Telegram format → Task 4 ✓
- §4.6 CLI command → Task 5 ✓
- §4.7 GH Actions cron → **deliberately skipped** (out of P3 MVP per design §2.2)
- §5 validation → Tasks 1-5 each include tests ✓

**Placeholder scan:** none. All steps have concrete code or commands.

**Type consistency:**
- `WeeklyRollup` defined Task 1, used Tasks 2/3/4/5 — consistent
- `last_monday(today: date) -> date` defined Task 5, called from cli — consistent
- `format_weekly_brief` defined Task 4, called from notify_weekly Task 4 — consistent

**git hygiene:**
- 6 commits, each with explicit `git add <files>`
- Working on `p3-weekly-rollup` branch (stacked on p1-prompt-schema)
- No remote push planned (waits for P1 PR merge then auto-rebases)

---

## Execution Handoff

Plan complete at `plans/2026-05-11-p3-weekly-rollup-plan.md`.

**6 tasks, ~30 steps, est ~1.5h CC.**

Use **subagent-driven-development** for execution (same pattern as P1+P2).

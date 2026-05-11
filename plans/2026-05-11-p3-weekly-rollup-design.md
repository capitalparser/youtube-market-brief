---
status: APPROVED-FOR-PLAN
type: design
phase: P3
date: 2026-05-11
project: 01_youtube_market_brief
related_plans:
  - plans/2026-05-11-p1-prompt-persona-schema-design.md (P1 base — KeyInsight/RedTeamItem + .analysis.json sidecar)
  - PAS plans/2026-05-11-p2-propagation-sidecar-integration-design.md (P2, parallel)
supersedes: none
---

# P3 Design — Weekly Ticker/Sector Rollup + Telegram Brief

## 1. Problem Statement

ymb는 매일 영상별 + 일일 단위로만 분석을 발송한다. 사용자가 *시간축으로 trend를 보려면* 매일 받은 daily brief 7개를 머릿속에서 합성해야 한다. CEO review에서 정리된 G3 + G6 갭의 본질:

- **G3 (시간축 rollup)**: 동일 ticker가 *지난주 7건 중 5건 부정* 같은 누적 view 부재. ymb의 ticker_rollup은 *당일 rollup*뿐.
- **G6 (주간 brief)**: 매주 monday 아침에 지난주 합성된 시장 read를 받으면 사용자가 *결정에 쓸 자산*이 됨. 현재 매일 daily brief가 *기억 단기 자산*에 머무름.

두 갭이 같은 wedge — *시간축으로 합성된 cumulative view*가 vault MD + Telegram에 한 번에 발송되면 G3와 G6이 동시에 충족.

## 2. Scope

### 2.1 In scope

- `domain/daily_brief.py`에 `compute_weekly_rollup(briefs: Iterable[DailyBrief], week_start: date) -> WeeklyRollup` 추가
- 새 dataclass `WeeklyRollup` (in `domain/types.py`) + 관련 dataclass (`WeeklyTickerEntry`, `WeeklySectorEntry`, `WeeklyThemeEntry`)
- `pipeline/weekly.py` (신규) — vault `_daily/*.analysis.json` sidecar 7개를 로드하여 `aggregate_weekly`
- `cli.py`에 새 명령 `ymb weekly-brief --week-start YYYY-MM-DD [--dry-run]`
- vault MD 출력: `00_Wiki/youtube/_weekly/{YYYY-MM-DD}_weekly.md` + `.analysis.json` sidecar (propagation source)
- Telegram 발송: 주간 brief를 `notify_weekly` 경로로 (P1 HTML format 재사용)
- (선택적) GH Actions cron 추가 — 월요일 08:00 KST `ymb weekly-brief` (or 사용자가 수동)
- 회귀 fixture + 테스트

### 2.2 Not in scope

- **Monthly rollup** — P3에서는 weekly만. monthly는 향후 (운영 검증 후)
- **인입 채널 다양화** — P4 (G5) 영역. RSS/Twitter feed는 별도 작업
- **Sector/theme 누적 카드 자동 업데이트** — P2 propagation의 영역. P3은 *읽기 표면(read surface)*만 추가
- **LLM 호출** — P3은 *결정론적* (deterministic). 영상별 + daily brief의 누적된 .analysis.json을 통계적으로 집계. 추가 LLM 합성은 옵션 — MVP는 통계만, narrative 합성은 향후 추가 가능
- **장기 트렌드 분석** (월간/분기) — 향후 작업

## 3. Decision — vault sidecar 누적 input

데이터 source 결정:
- **선택**: `00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.analysis.json` 7개 로드 (P1 sidecar)
- **거절**: 영상별 sidecar 각각 로드 — 중복 cost. brief가 이미 영상별 합성. brief sidecar가 정합한 source

이유:
- P1이 만든 brief sidecar에 `ticker_rollup`, `key_insights[].sector_tags`, `red_team[].theme_tags`가 모두 결정론적으로 존재
- weekly = `daily_rollup × 7`. brief가 합성 단위로 이미 안정화됨
- 영상 단위 데이터가 필요하면 brief의 `videos[]` 필드 + 영상 sidecar 별도 로드로 drill-down 가능 (P3 MVP에서는 불필요)

## 4. Design

### 4.1 New dataclasses (`domain/types.py`)

```python
@dataclass(frozen=True)
class WeeklyTickerEntry:
    symbol: str | None
    display: str
    in_watchlist: bool
    sector_tag: str | None
    # 시간축 통계
    days_mentioned: int  # 지난주 등장 day 수 (max 7)
    total_mentions: int  # 영상 수 누적 (per_video count의 합)
    directions: tuple[Direction, ...]  # 각 daily rollup의 net_direction 시퀀스
    net_weekly_direction: NetDirection  # 통합 방향 (majority logic)
    # 일자별 daily mention 매핑
    per_day: tuple[WeeklyTickerDayEntry, ...]


@dataclass(frozen=True)
class WeeklyTickerDayEntry:
    date: date
    direction: Direction | NetDirection  # daily rollup의 net_direction
    mention_count: int  # 그 날 영상 수


@dataclass(frozen=True)
class WeeklySectorEntry:
    sector_slug: str  # taxonomy slug
    insight_days: int  # 지난주 인사이트에 등장한 day 수
    total_insight_mentions: int  # 누적
    # 관련 ticker들
    related_tickers: tuple[str, ...]  # symbol or display list


@dataclass(frozen=True)
class WeeklyThemeEntry:
    theme_slug: str
    insight_days: int
    total_insight_mentions: int
    related_tickers: tuple[str, ...]


@dataclass(frozen=True)
class WeeklyRollup:
    week_start: date  # 월요일
    week_end: date    # 일요일 (week_start + 6 days)
    daily_briefs_present: tuple[date, ...]  # 실제 로드된 brief의 날짜들 (7개 중 일부 빠질 수도)
    daily_briefs_missing: tuple[date, ...]  # 누락된 날짜들 (운영 가시성)
    tickers: tuple[WeeklyTickerEntry, ...]
    sectors: tuple[WeeklySectorEntry, ...]
    themes: tuple[WeeklyThemeEntry, ...]
    total_videos: int  # 지난주 처리 영상 총합 (= sum of len(brief.videos))
```

### 4.2 `compute_weekly_rollup` (`domain/daily_brief.py` 확장)

```python
def compute_weekly_rollup(
    briefs: Iterable[DailyBrief],
    week_start: date,
) -> WeeklyRollup:
    """주간 합성. briefs는 week_start ~ week_start+6 범위만 로드되어야 함.

    Idempotent + deterministic. LLM 호출 없음. brief sidecar 통계만.
    """
    # ticker 단위 합성 — daily ticker_rollup × 7 → WeeklyTickerEntry
    # sector/theme 단위 — daily key_insights/red_team의 sector_tags/theme_tags union
    # majority direction logic
```

### 4.3 `pipeline/weekly.py` (신규)

```python
def load_weekly_briefs(
    *,
    vault_daily_root: Path,
    week_start: date,
) -> list[DailyBrief]:
    """{week_start} ~ {week_start+6} 범위의 .analysis.json sidecar 로드.
    누락된 날짜는 skip (warning log)."""

def aggregate_weekly(
    *,
    week_start: date,
    config: AppConfig,
) -> WeeklyRollup | None:
    """주간 rollup 생성. 7일 sidecar 0건이면 None 반환."""

def write_weekly_md(
    rollup: WeeklyRollup,
    *,
    vault_weekly_root: Path,
    captured_at: datetime,
) -> Path:
    """주간 brief MD + .analysis.json sidecar 작성. 경로:
    {vault_weekly_root}/{YYYY-MM-DD}_weekly.md
    {vault_weekly_root}/{YYYY-MM-DD}_weekly.analysis.json
    """
```

### 4.4 Markdown 출력 형식

```markdown
---
captured_at: 2026-05-12T08:00:00+09:00
week_start: 2026-05-05
week_end: 2026-05-11
daily_briefs_present: [2026-05-05, 2026-05-06, ...]
daily_briefs_missing: [2026-05-08]
total_videos: 23
ticker_sector_tags_union: [semiconductors, financials, ...]
insight_theme_tags_union: [hyperscaler_capex, memory_supercycle, ...]
source_type: youtube_weekly_brief
tags: [youtube, weekly_brief]
tier: deep
---

# 📅 2026-05-05 ~ 2026-05-11 주간 시장 브리핑

## 📊 워치리스트 종목별 주간 누적

| 종목 | 주간 방향 | 등장 일수 | 영상수 | 일자별 |
|------|----------|---------|--------|--------|
| 삼성전자 (005930) | 🔴 부정적 | 5/7일 | 8 | 05-05 🔴, 05-06 🟡, ... |
| SK하이닉스 (000660) | 🟢 긍정적 | 6/7일 | 11 | ... |
| NVDA | 🟢 긍정적 | 7/7일 | 12 | ... |

## 🔍 자동 발견 종목 (주간 등장 ≥2일)

- MSFT — 🟢 긍정적, 4일 등장, 6 영상
- TSM — ⚪ 중립, 2일 등장, 2 영상

## 🎯 주간 sector heatmap

| Sector | 등장 일수 | 영상수 | 관련 ticker |
|--------|----------|--------|------------|
| semiconductors | 7/7일 | 23 | 005930, 000660, NVDA, MU, ... |
| hyperscaler_capex (theme) | 5/7일 | 12 | NVDA, MSFT, GOOGL |

## 📺 지난주 영상 (23건)

(영상 목록 — channel별 그룹화 또는 일자별)

## 📝 누락된 daily brief

- 2026-05-08 (cron 실패 또는 미실행) — Harness/logs/youtube_market_brief/2026-05-08.log 확인

```

### 4.5 Telegram 발송 형식

기존 P1 HTML format 재사용 (`<blockquote><b>` 첫 줄 강조). 메시지 구조:

```
<blockquote><b>📅 2026-05-05 ~ 2026-05-11 주간 시장 브리핑</b></blockquote>
🔢 처리 영상 23건 (7/7일 brief 정상, 누락 0)

📊 워치리스트 주간 누적
• 삼성전자 (005930) 🔴 부정적 — 5/7일, 8 영상
• SK하이닉스 (000660) 🟢 긍정적 — 6/7일, 11 영상
• NVDA 🟢 긍정적 — 7/7일, 12 영상

🔍 자동 발견 (주간 ≥2일)
• MSFT 🟢 긍정적 — 4일, 6 영상
• TSM ⚪ 중립 — 2일, 2 영상

🎯 Sector 7-day heatmap
• semiconductors — 7/7일, 23 영상
• financials — 3/7일, 5 영상

🎨 Theme 7-day heatmap
• hyperscaler_capex — 5/7일, 12 영상
• memory_supercycle — 4/7일, 9 영상

📝 vault: 00_Wiki/youtube/_weekly/2026-05-05_weekly.md
```

긴 메시지면 P1의 `decorate_chunks` + `split_message`가 자동 분할 + `<blockquote><b>` 헤더.

### 4.6 CLI 명령

```bash
# 수동 실행
ymb weekly-brief --week-start 2026-05-05

# Dry-run (Telegram 발송 없음, 파일만 생성)
ymb weekly-brief --week-start 2026-05-05 --dry-run

# vault MD만 (Telegram skip)
ymb weekly-brief --week-start 2026-05-05 --no-telegram

# 기본값: 가장 최근 월요일 자동 계산
ymb weekly-brief  # week_start=last_monday
```

### 4.7 GH Actions cron (선택적 — P3 MVP에서는 미포함)

월요일 08:00 KST 자동 실행은 *향후*. P3 MVP는 수동 호출만. 운영 검증 후 cron 추가.

## 5. Validation Strategy

### 5.1 Unit tests
- `compute_weekly_rollup`: 빈 brief list → None
- `compute_weekly_rollup`: 1 brief만 → `daily_briefs_missing` 6개, ticker rollup 단순
- `compute_weekly_rollup`: 3 brief (e.g. 5/5, 5/6, 5/9) → 같은 ticker의 day-aggregation 정확성
- `compute_weekly_rollup`: 7 brief 모두 → 누적 mention_count 정확
- net_weekly_direction logic (majority): 5 긍정 + 2 부정 → "긍정적", 3+3+1 → "혼조"
- `load_weekly_briefs`: 누락 sidecar warning + skip
- `write_weekly_md`: MD frontmatter 필드 + body table 형식

### 5.2 Integration smoke (수동)
P1의 vault `00_Wiki/youtube/_daily/2026-05-06_brief.analysis.json` ~ `2026-05-10_brief.analysis.json` 사용 (5건 존재):
```bash
ymb weekly-brief --week-start 2026-05-05 --dry-run
```
출력 검증:
- 누락된 5/11 (P3 시작 시점) 표시
- ticker rollup이 5건 brief 합산 정확
- Telegram dry-run dump 형식 OK

### 5.3 Backward compat
기존 daily 흐름 (compute_rollup, aggregate_daily, notify_daily, write_daily_brief_md) 무영향. 전부 기존 테스트 그대로 통과.

## 6. Migration / Operational

- **Non-retroactive**: 기존 daily brief sidecar는 그대로. P3 적용 시점부터 weekly aggregation 사용
- **GH secrets**: 추가 없음 (기존 TELEGRAM_*, etc. 재사용)
- **Vault 디렉토리 신규**: `00_Wiki/youtube/_weekly/` (`vault_weekly_root` property)
- **State.json 영향 없음**: weekly는 영상 idempotency와 직교

## 7. Open Questions (plan 단계 lock)

- Q1: `net_weekly_direction` majority logic — tie-breaker? 1순위: tie면 "혼조" (보수적)
- Q2: sector/theme heatmap의 "관련 ticker" 한계 — top N=5? 1순위: 5
- Q3: 자동 발견 ticker 노출 임계 — *주간 ≥2일* (당일 hint 1건은 노이즈)? 1순위: 2일
- Q4: Telegram 메시지가 4000자 cap 초과 시? 1순위: P1 split_message + decorate_chunks 그대로 사용
- Q5: `last_monday` 계산은 KST 기준? 1순위: Yes (config.timezone)

## 8. 결정 요약

| 항목 | 결정 |
|---|---|
| 데이터 source | `_daily/*.analysis.json` × 7 (P1 sidecar 누적) |
| 시간 granularity | weekly only (monthly 향후) |
| LLM 합성 | 없음 (deterministic stats only) |
| Trigger | 수동 (`ymb weekly-brief`); cron은 P3 후 |
| 출력 surface | vault MD + `.analysis.json` sidecar + Telegram |
| Telegram format | P1 HTML 재사용 (`decorate_chunks`) |
| Backward compat | 기존 daily 흐름 무영향 |
| Migration | non-retroactive |

---

_다음 단계: writing-plans → subagent-driven-development._

---
status: APPROVED-FOR-PLAN
type: design
phase: P1
date: 2026-05-11
project: 01_youtube_market_brief
related_adr: docs/adr/0006-prompt-persona-schema-realignment.md  # 신설 예정
supersedes: none
---

# P1 Design — Prompt Persona Re-articulation + Output Schema Alignment

## 1. 배경

### 1.1 Problem statement

`ymb`는 매일 4회 cron으로 YouTube 채널의 신규 영상을 분석하여 `00_Wiki/youtube/{channel}/...` 영상 카드 + `_daily/*_brief.md` 일일 브리핑 MD를 생성한다. 코드 파이프라인 자체는 안정적으로 동작 중 (5/6~5/10 daily brief 6건 정상 생성, GH Actions cloud cron 4x/day).

그러나 **사용자 outcome 기준 funnel의 끝은 `02_Areas/Market_Insights/{sectors,themes}/*.md` 카드**이며, ymb의 raw 산출물 → Market_Insights 카드로의 통합(propagation)이 *매일 수동*으로 일어난다. 최근 commit history 인용:

```
feat(market-insights): integrate 5/8 + 5/9 raws — 8 videos + 5/9 daily brief (41/49 raws)
feat(market-insights): integrate 5/6 raws — 4 videos across 11 cards (33/49 raws)
```

즉 49건의 raw 중 41건 통합 완료, 11개 카드에 수동으로 한 줄씩 추가하는 작업이 매일 발생. ymb funnel 최상단의 자동화가 풀의 가장 큰 work item을 줄이지 못하고 있음.

### 1.2 진단 — propagation 자동화의 *전제* 부족

근본 원인은 **ymb output schema와 Market_Insights 카드 frontmatter schema의 misalignment**다. 현재 ymb 출력 `key_insights: [str, str, ...]`은 plain string list라 LLM 재호출 없이는 *어떤 sector·theme 카드의 어느 row에 propagation할지 결정할 수 없음*. 사용자가 매번 *mental mapping*으로 raw → 카드를 연결.

### 1.3 본 design의 위치

P1은 **propagation 자동화(P2)의 전제 작업**. P1 = prompt persona 재정의 + output schema 구조화. P2 = `_propagate` skill v1 (schema 기반 deterministic propagation). P1이 안 끝나면 P2가 *LLM 재추론*에 의존하여 결정론을 잃음.

## 2. Scope

### 2.1 In scope

- `prompts/system_video_analysis.ko.md` 페르소나 + schema 갱신
- `prompts/system_daily_brief.ko.md` 페르소나 일관성 적용
- `domain/types.py` dataclass 변경 + 새 dataclass 추가
- `pipeline/analyze.py` 스키마 검증 + watchlist sector 후처리
- `domain/watchlist.py`·`config/watchlist.yaml.example` sector 필드 추가
- `domain/markdown.py`·`domain/telegram_format.py`·`domain/daily_brief.py` schema 변경 흡수
- `config.py` taxonomy drift validation 추가
- `docs/adr/0006-...` ADR 신설
- fixture v0 archive + v1 신규 생성
- 영향 받는 unit/integration test 갱신

### 2.2 Not in scope (이번 P1)

- **propagation 자동화 자체** — P2의 책임. P1은 schema·prompt만 잠금
- **기존 vault MD retroactive 재처리** — non-retroactive migration. P2 단계에서 별도 one-off 스크립트로 검토
- **stance / confidence / time_horizon 자동 출력** — 카드 owner(사용자)의 판단 영역. LLM 결정 위임 거절
- **A/B 평행 운영** — 개인 운영자 규모상 over-engineering. fixture regression + 수동 1-2건 검토로 충분
- **CI 자동 검증** — GH Actions cron의 fail-fast로 충분. 별도 CI step 추가 보류

## 3. Persona Design (4-role composite)

### 3.1 결정 — 페르소나 자체를 재정의

사용자의 *실제 직무 정체성*(`CLAUDE.md` §1.1: 인차지/감사인, AX Node 매니저, K-IFRS 감사·재무·전략·GTM Korea Focus)을 그대로 LLM에 노출. 단일 "시장 분석가" 페르소나는 사용자 vantage의 *부분집합*에 불과.

**Trade-off 평가**:
- ✅ 분석 입체성 ↑ (4 시각이 합성된 분석)
- ✅ red team 품질이 *부수적으로* 강화 (감사인 시각이 red flag 명시 강제)
- ⚠️ output token 약간 ↑ (관점 다양화) — ADR-0005 월 $5 cap 안에서 무시 가능
- ⚠️ 서술 톤 변화 위험 → 4.3 수동 검토 게이트로 방어

### 3.2 `system_video_analysis.ko.md` 「역할」 섹션 — 신규 wording

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
```

### 3.3 `system_daily_brief.ko.md` 페르소나 일관성

동일 4-role composite 페르소나 유지. 추가 directive:

```markdown
당신은 위 4 시각이 합성된 1인의 분석가이며, 오늘 N개 영상의 영상별
분석 JSON list를 받아 *합성된 시장 read*를 작성한다. 입력은 raw transcript가
아니라 이미 정제된 영상 단위 분석이며, 본 단계는 영상 간 신호 합성과
모순 해소(같은 ticker에 대한 영상 간 view 충돌)에 초점을 둔다.
```

## 4. Schema Design

### 4.1 출력 JSON schema 변경

```diff
 {
   "headline_3line": ["문장1", "문장2", "문장3"],

-  "key_insights": ["인사이트1", "인사이트2", "인사이트3"],
+  "key_insights": [
+    {
+      "text": "인사이트1",
+      "sector_tags": ["semiconductors", "hyperscaler_capex"],
+      "theme_tags": ["ai_meltup_bubble"]
+    }
+  ],

-  "red_team": ["반대시각1", "반대시각2"],
+  "red_team": [
+    { "text": "반대시각1", "sector_tags": [...], "theme_tags": [...] }
+  ],

   "tickers": [
     {
       "symbol": "005930",
       "display": "삼성전자",
       "in_watchlist": true,
+      "sector_tag": "semiconductors",
       "direction": "긍정적",
       "reasoning": "근거 1-2 문장",
       "quotes": ["..."],
       "confidence": "high"
     }
   ],
   "watchlist_hits": ["005930"]
 }
```

### 4.2 enum 노출 방식 — prompt inline

외부 file 동적 주입 안 함 (`domain/` client-free 원칙 유지). prompt에 enum 인라인:

```markdown
## 2.x sector_tags / theme_tags 작성 규칙

sector_tags는 다음 enum 중 0개 이상 선택. 인사이트가 해당 sector의
현재 가설·지표·위험에 *직접* 관련될 때만 태그.

  semiconductors, software_ai_services, tech_hardware,
  financials, power_utilities, industrials_defense,
  energy, materials, consumer_discretionary, consumer_staples

theme_tags는 다음 enum 중 0개 이상 선택. 인사이트가 해당 macro
theme의 가설 진행·반전에 기여할 때만 태그.

  ai_agent_adoption, ai_meltup_bubble, bigtech_ipo_supply,
  geopolitics_middle_east, hyperscaler_capex, korea_discount,
  memory_supercycle, tokenization_rwa, us_fiscal_debt

태그가 *명확하지 않으면 비워둘 것*. 무리한 추가는 propagation
오염을 유발한다.
```

### 4.3 Taxonomy drift 감지

`config.py`에 `_validate_taxonomy_alignment(prompt_path, vault_root)` 추가, `ymb config validate` path에 wiring. prompt 내 enum과 `02_Areas/Market_Insights/{sectors,themes}/*.md` slug 비교, mismatch 시 explicit fail.

```python
# config.py 추가 함수 시그니처 (이번 design 잠금)
def _validate_taxonomy_alignment(
    prompt_path: Path, vault_root: Path
) -> list[str]:
    """
    prompt 내 sector/theme enum과 vault MD slug를 비교.
    return: drift된 slug list (empty면 정상). caller는 비어있지 않으면 raise.
    """
```

### 4.4 Surface 노출 정책

| Surface | 노출 방식 | 비고 |
|---|---|---|
| Telegram 메시지 | `text`만 추출 | 사용자 체감 변화 0 |
| 영상 MD frontmatter | `insight_sector_tags`, `insight_theme_tags` (union of all insights), `red_team_sector_tags`, `red_team_theme_tags` 추가 | *summary 인덱스 용도*. drill-down은 body |
| 영상 MD body | `text`만 표시. inline `#tag` 노이즈 없음 | 가독성 유지 |
| 영상 MD JSON sidecar | `{video_id}.analysis.json` — LLM 출력 전체(insight·red_team object 구조 그대로)를 동일 디렉토리에 보존 | **propagation source of truth**. P2가 이 파일을 파싱하여 insight별 sector/theme 매핑 복원 |
| Daily brief MD frontmatter | aggregated tag (당일 영상 union) | summary 인덱스 |
| Daily brief MD body | `text`만 표시 | 가독성 유지 |
| Daily brief JSON sidecar | `{date}_brief.analysis.json` | propagation source |

**Propagation 자동화 분담** — frontmatter union은 "어떤 카드를 update할지 빠르게 찾는 인덱스"용이고, **insight별 sector·theme 정확 매핑은 JSON sidecar에서 복원**된다. P2의 책임은 sidecar parsing → 카드 row append 매핑. body는 사용자 읽기 surface로만 유지 (markdown body parser 안 만들어도 됨).

### 4.5 watchlist sector 필드

`config/watchlist.yaml`:

```yaml
tickers:
  - symbol: '005930'
    market: KOSPI
    name_ko: 삼성전자
    sector: semiconductors   # 신규 enum 필수
    aliases: ['samsung', 'sec']
```

기존 watchlist는 5종목뿐이라 수동 보강 부담 낮음. `WatchlistEntry.sector: str` 필수 필드로 type 정의. config 로딩 시 enum 검증.

### 4.6 ticker `sector_tag` 후처리

- watchlist hit ticker(`in_watchlist=True`): post-process가 `WatchlistEntry.sector`로 *덮어쓰기*. LLM 출력값과 conflict 시 watchlist 우선 + `log.warning(f"ticker {symbol} sector conflict: llm={llm}, watchlist={wl}")`
- 자동 발견 ticker(`in_watchlist=False`): LLM 출력값 그대로 사용. enum 위반 시 strict fail (per-video try/except로 격리됨)

## 5. Downstream Impact + Migration

### 5.1 파일별 변경 footprint

| 파일 | 변경 내용 |
|---|---|
| `prompts/system_video_analysis.ko.md` | 페르소나 + schema + enum 섹션 갱신 (3.2 + 4.1 + 4.2) |
| `prompts/system_daily_brief.ko.md` | 페르소나 일관성 directive 추가 (3.3) |
| `domain/types.py` | `KeyInsight` / `RedTeamItem` dataclass 신규. `TranscriptSummary.key_insights: tuple[KeyInsight, ...]`, `red_team: tuple[RedTeamItem, ...]`. `TickerMention.sector_tag: str`. `WatchlistEntry.sector: str` 추가 |
| `pipeline/analyze.py` | JSON parse 후 strict schema validation (enum check 포함). watchlist ticker sector post-process |
| `domain/watchlist.py` | matcher 시그니처 영향 없음. WatchlistEntry sector 필드만 추가됨 |
| `domain/markdown.py` | frontmatter footprint 추가, body는 text만 |
| `domain/telegram_format.py` | `KeyInsight.text` / `RedTeamItem.text` 추출 helper. blockquote/bold (5/11 변경) 영향 없음 |
| `domain/daily_brief.py` | insight tag aggregation (union) |
| `config.py` | `_validate_taxonomy_alignment` 추가 |
| `config/watchlist.yaml.example` | sector 필드 예시 추가. 실 `watchlist.yaml`은 사용자 수동 보강 |
| `docs/adr/0006-prompt-persona-schema-realignment.md` | ADR 신설 |

### 5.2 Migration — non-retroactive

- 기존 vault MD는 그대로. 재처리 없음
- state.json idempotency 유지. 기존 영상 자동 재처리 발생 안 함
- new schema는 적용 시점부터 처리되는 영상에 적용
- P2 propagation 자동화는 *new schema MD만* 대상. old MD는 사용자가 이미 41/49 수동 통합 진행 중이므로 그대로 두는 게 정합

이유: retroactive 재처리는 (a) LLM 비용 증가 (b) idempotency state 충돌 (c) 사용자 이미 수동 통합한 부분과 충돌 가능. *clean cut*이 가장 안전.

## 6. Validation Strategy

### 6.1 Schema validation
`analyze.py`에서 JSON parse 후 strict validation. enum 위반·필수 필드 missing은 fail-fast (기존 per-video try/except로 격리). LLM이 enum 위반 시 1회 retry, 2회 fail 시 영상 skip + RunReport에 명시.

### 6.2 Fixture regression + 수동 검토 (통합)

fixture 생성과 수동 검토는 **동일 transcript 세트**를 공유. 효율 + 검증 일관성 확보:

1. 기존 fixture → `tests/fixtures/analyze_outputs/v0/` archive
2. vault 기존 영상 **2-3건** 선정 (선정 기준: 워치리스트 히트 1건 + 자동 발견 ticker 1건 + 인사이트 풍부도 상위 1건). transcript JSON을 `tests/fixtures/transcripts/p1_regression/`에 저장
3. v1 prompt로 LLM 호출 → 출력을 `tests/fixtures/analyze_outputs/v1/`에 저장
4. 영향 받는 통합 테스트(`test_analyze.py`, `test_aggregate.py`, `test_markdown.py`, `test_telegram_format.py`)는 v1 fixture로 회귀 검증
5. **수동 검토 게이트**: 동일 출력에 대해 사용자가 *눈으로* 확인 — `key_insights.text` 품질, `red_team` 입체성(4 시각 효과), `sector_tags`/`theme_tags` 합리성

**Go/no-go**: 수동 검토 통과 시 prompt 교체 + fixture v1 commit. fail 시 페르소나·schema 조정 후 fixture 재생성·재검토 (LLM 비용 영향: 2-3건 × 재시도 횟수, 무시 가능).

### 6.4 Drift 운영 검증
`ymb config validate`가 새 taxonomy check 포함. 명시적 invocation으로 갱신 누락 방지. CI 자동화는 보류 (GH Actions cron의 fail-fast로 충분).

### 6.5 평행 운영 — 안 함 (YAGNI)
v0/v1 동시 호출, A/B 비교는 개인 운영자 규모상 over-engineering.

## 7. ADR + Open Questions

### 7.1 ADR-0006 작성 시점
P1 implementation plan(writing-plans 다음 단계) 작성 직후, code change 시작 전. ADR-0006 핵심 내용:
- 4-role composite 페르소나 채택 이유 (단일 페르소나는 사용자 vantage의 부분집합)
- key_insights/red_team의 object 승격 이유 (propagation deterministic화)
- stance/confidence/time_horizon LLM 위임 거절 이유 (카드 owner 영역)
- non-retroactive migration 이유 (clean cut)

### 7.2 Open questions (plan 단계에서 해결)
- `KeyInsight` dataclass를 `frozen=True`로 둘 것인지 (현재 모든 domain dataclass가 frozen → 일관성 이유로 frozen=True 1순위)
- `red_team_sector_tags` frontmatter 필드 이름 (`red_team_sector_tags` vs `redteam_sector_tags` vs `risk_sector_tags`) — bikeshed, 1순위 `red_team_sector_tags` (snake_case 일관성)
- JSON sidecar 위치를 영상 MD와 동일 디렉토리에 둘지(현재 design) vs `analyses/` 별도 디렉토리 분리할지 — vault clutter 우려 시 후자, 단 P2가 file 페어링 처리 필요. 1순위 동일 디렉토리(`{slug}/{date}__{title}-{hash}.analysis.json`)

## 8. 결정 요약

| 항목 | 결정 | 근거 |
|---|---|---|
| 페르소나 | 4-role composite | 사용자 실제 직무 정체성 반영, 분석 입체성 ↑ |
| key_insights / red_team | string → object `{text, sector_tags, theme_tags}` | propagation deterministic, mental mapping 제거 |
| ticker | `sector_tag` 단일값 추가, watchlist 우선 | 자동 propagation enabled |
| enum 노출 | prompt inline | client-free 유지, drift 감지로 보강 |
| stance/confidence/time_horizon | **LLM 위임 거절** | 카드 owner 판단 영역 |
| migration | non-retroactive clean cut | 사용자 수동 통합과 충돌 방지 |
| 검증 | fixture v0 archive + v1 생성 + 수동 1-2건 게이트 | 개인 운영자 규모상 적정 |
| 평행 운영 | 안 함 | YAGNI |

---

_본 design은 `01_Projects/CLAUDE.md` Tier 3 권장 호출 순서의 3번째 단계 산출물.
다음 단계는 `/superpowers:writing-plans`로 `plans/2026-05-11-p1-prompt-persona-schema-plan.md` 작성._

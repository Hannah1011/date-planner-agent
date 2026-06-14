# 서울 데이트 코스 플래너 — 멀티 AI 에이전트

날짜, 시간대, 지역, 무드, 음식 취향, 예산을 입력하면 대중교통 이동 시간과 날씨까지 고려한 서울 데이트 코스를 자동으로 생성해 주는 멀티 에이전트 시스템입니다.
사용자가 코스를 거절하면 이유를 분석해 조건을 반영한 리플랜을 수행하고, 승인된 코스는 취향 DB에 기록해 다음 추천에 활용합니다.

---

## 주요 기능

- 서울 25개 구 지도(Folium)에서 클릭으로 지역 선택
- 시간대 / 무드 / 음식 취향 / 카페 스타일 / 예산 기반 장소 탐색
- 네이버 검색 + Google Places 병렬 조회로 후보 장소 수집
- Google Directions(대중교통) 기반 이동 시간 최적화, 30분 초과 구간 자동 제외
- OpenWeatherMap 날씨 반영 — 강수 확률 30% 이상 시 우산 알림
- 브레이크타임 크롤링으로 영업 시간 외 장소 필터
- HITL 체크포인트 — 승인/거절 버튼, 거절 이유 분석 후 리플랜 (최대 3회)
- SQLite 취향 DB — 방문 기록 / 피드백 / 선호 태그 영속 저장 및 다음 추천 반영

---

## 화면 예시

> 추후 GIF 업로드 예정

---

## 에이전트 종류와 역할

| 에이전트 | 역할 |
|---|---|
| **Input Collector** | 사용자 입력(구, 날짜, 시간대, 무드 등) 파싱 및 유효성 검증 → `UserRequest` 구조체 생성 |
| **Search Agent** | 무드별 카테고리 쿼리를 `ThreadPoolExecutor`로 병렬 검색, Google Places로 상세 정보 보강 |
| **Route Planner** | 대중교통 이동 시간 기반 최적 순서 구성, 날씨 안내 문구 생성, 예산 초과 여부 확인 |
| **Memory Agent** | SQLite에서 취향 맥락 로드 → LLM 프롬프트 주입, 승인 코스의 방문지·선호 태그 저장 |
| **Feedback & Replan** | 사용자 승인/거절 처리, 거절 이유에서 비선호 키워드 추출 후 후보 재필터 및 리플랜 실행 |

---

## 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI / CLI                       │
│   지도 구 선택 → 조건 입력 폼 → 코스 출력 → 승인/거절 버튼      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ UserRequest
            ┌───────────────▼───────────────┐
            │      Input Collector Agent     │  gpt-4o-mini
            │  입력 파싱 + Guardrails 검증   │
            └───────────────┬───────────────┘
                            │
            ┌───────────────▼───────────────┐
            │        Memory Agent           │  text-embedding-3-small
            │   SQLite 취향 맥락 로드        │
            └───────────────┬───────────────┘
                            │ 취향 컨텍스트
            ┌───────────────▼───────────────┐
            │        Search Agent           │  gpt-4o
            │  ┌──────┬──────┬──────┐       │
            │  │카테고리A│카테고리B│카테고리C│  ← ThreadPoolExecutor
            │  └──┬───┴──┬───┴──┬───┘       │
            │  Naver  Naver  Naver           │
            │   ↓      ↓      ↓              │
            │  Google Places (상세 보강)      │
            └───────────────┬───────────────┘
                            │ PlaceCandidate[]
            ┌───────────────▼───────────────┐
            │      Route Planner Agent      │  gpt-4o
            │  Google Directions (이동시간)  │
            │  OpenWeatherMap (날씨)         │
            │  30분 초과 구간 자동 제외      │
            └───────────────┬───────────────┘
                            │ DateCourse
            ┌───────────────▼───────────────┐
            │    Feedback & Replan Agent    │  gpt-4o
            │  승인 → Memory Agent에 저장   │
            │  거절 → 키워드 추출 → 리플랜  │
            └───────────────────────────────┘

외부 API          도구 레이어              저장소
─────────         ──────────              ──────
Naver Search  →  naver_search.py     ┐
Google Places →  google_places.py    │   SQLite
Google Dir.   →  directions.py       ├→  preference_store.py
OpenWeatherMap→  weather.py          │   (취향/방문/피드백)
(크롤러)      →  crawler.py          ┘
```

---

## 실행 흐름

```
1. 사용자  → 지도에서 구 선택, 날짜/시간대/무드/음식 취향/예산 입력
2. Input Collector → 입력 파싱 및 Guardrails 검증 (과거 날짜·예산 0원 거부)
3. Memory Agent → DB에서 최근 취향 20건 로드, 요약 문자열 생성
4. Search Agent → 무드에 맞는 카테고리 3개 병렬 검색
                  Naver 결과 → Google Places 상세 보강 → 영업 중 필터
5. Route Planner → 별점 순 정렬 → 대중교통 이동 시간 체크
                   30분 이하 구간만 선택 → 날씨 안내 문구 추가 → DateCourse 생성
6. HITL 체크포인트
   ├─ 승인 → Memory Agent: 방문지 + 긍정 취향 태그 DB 저장 → 종료
   └─ 거절 → 이유 텍스트 입력
              ↓
              거절 이유 분석 → 비선호 키워드 추출 → 후보 재필터
              리플랜 횟수 +1 → 4번으로 돌아가 코스 재생성
              (3회 초과 시 "날짜/지역 변경" 안내 후 종료)
```

---

## Agentic Pattern 적용 현황

| Pattern | 구현 위치 및 설명 |
|---|---|
| **Prompt Chaining** | `main.py` — Input Collector → Memory → Search → Route Planner → Feedback 순서로 이전 Agent 출력이 다음 Agent 입력으로 연결 |
| **Tool Use** | `search_agent.py` — Naver Search + Google Places 호출, `route_planner.py` — Google Directions + OpenWeatherMap 호출, `crawler.py` — 브레이크타임 크롤링 |
| **Planning** | `route_planner.py` — `_TIME_SLOT_PLACE_COUNT`로 시간대별 목표 장소 수 결정, 이동 시간 제약을 고려한 순서 최적화 |
| **Multi-Agent System** | 5개 독립 Agent(Input Collector / Search / Route Planner / Memory / Feedback)가 역할 분리 후 순차 파이프라인으로 연결 |
| **Guardrails** | `guardrails/validators.py` — 과거 날짜 거부, 예산 0원 거부, 이동 시간 30분 상한, 코스 장소 수 2~5개 제한, 리플랜 3회 상한 |
| **HITL (Human-in-the-Loop)** | `streamlit_app.py` — 코스 출력 후 승인/거절 버튼 제공, 거절 시 이유 텍스트 입력받아 리플랜에 반영 |
| **Resource-Aware Optimization** | `search_agent.py` — `ThreadPoolExecutor(max_workers=3)`로 카테고리 병렬 검색, `model_config.py` — 단순 파싱엔 gpt-4o-mini, 추론이 필요한 검색·라우팅엔 gpt-4o |
| **Goal Setting & Monitoring** | `feedback_replan.py` — `check_replan_limit()`으로 3회 초과 시 조건 변경 유도, `logger`로 전 단계 처리 결과 기록 |
| **Exception Handling** | 모든 외부 API 래퍼에 `try-except requests.RequestException` 적용, 에러 시 빈 리스트/dict 반환 후 로깅 — 시스템 중단 없음 |
| **Evaluation** | `feedback_replan.py` — 사용자 승인/거절이 코스 품질의 평가 신호, 거절 횟수와 이유를 DB에 기록해 추후 분석 가능 |
| **Memory Management** | `memory/preference_store.py` — SQLite 3테이블(취향/방문/피드백) 영속 저장, `memory_agent.py` — 최근 20건 취향 요약을 LLM 컨텍스트로 주입 |

---

## 기술 스택

| 분류 | 내용 |
|---|---|
| **언어** | Python 3.9+ |
| **LLM** | OpenAI GPT-4o, GPT-4o-mini |
| **UI** | Streamlit, streamlit-folium |
| **지도** | Folium + 서울 행정구역 GeoJSON |
| **외부 API** | Naver Local Search, Google Places, Google Directions, OpenWeatherMap |
| **크롤링** | BeautifulSoup4 (브레이크타임 파싱) |
| **DB** | SQLite (python 내장 `sqlite3`) |
| **병렬 처리** | `concurrent.futures.ThreadPoolExecutor` |
| **테스트** | pytest, pytest-mock |
| **환경 관리** | python-dotenv |

---

## 실행 가이드

### 준비 사항

- Python 3.9 이상
- Git

### 저장소 클론

```bash
git clone https://github.com/HannahKim/date-planner-agent.git
cd date-planner-agent
```

### 가상환경 · 패키지 설치 및 DB 초기화 (자동 스크립트)

```bash
bash setup.sh
```

`setup.sh`가 순서대로 실행합니다:
1. Python 버전 확인
2. `.venv` 가상환경 생성
3. `requirements.txt` 패키지 설치
4. `.env.example` → `.env` 복사
5. SQLite DB 초기화 + 샘플 취향 데이터 삽입

### 수동 설치 (스크립트 사용이 어려운 환경)

```bash
# 1. 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt

# 3. 환경 변수 파일 준비
cp .env.example .env

# 4. DB 초기화
python -c "from date_planner.memory.preference_store import init_db; init_db()"

# 5. 샘플 취향 데이터 삽입 (선택)
python -m date_planner.data.seed_data
```

### API 키 발급

| API | 발급 경로 |
|---|---|
| **OpenAI** | [platform.openai.com](https://platform.openai.com) → API Keys → Create new secret key |
| **Naver Search** | [developers.naver.com](https://developers.naver.com) → 애플리케이션 등록 → 서비스 환경: **WEB** → 검색 API 선택 |
| **Google Places / Directions** | [console.cloud.google.com](https://console.cloud.google.com) → API 및 서비스 → 사용자 인증 정보 → API 키 생성 → Places API · Directions API 활성화 → API 제한사항 설정 |
| **OpenWeatherMap** | [openweathermap.org](https://openweathermap.org) → 회원가입 → My API Keys |

### .env 설정

```env
OPENAI_API_KEY=sk-...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
GOOGLE_PLACES_API_KEY=...
GOOGLE_DIRECTIONS_API_KEY=...
OPENWEATHERMAP_API_KEY=...
```

### 앱 실행

```bash
# Streamlit UI (권장)
bash run.sh --ui
# → 브라우저에서 http://localhost:8501 열림

# CLI 모드 (샘플 입력 자동 실행)
bash run.sh

# 샘플 취향 데이터 재삽입 후 CLI 실행
bash run.sh --seed

# 전체 테스트 실행
bash run.sh --test
```

---

## 실행 확인용 예제

아래는 `bash run.sh` (CLI 모드) 실행 시 출력 예시입니다.

**입력 조건**
- 지역: 마포구
- 날짜: 내일
- 시간대: 오후 (AFTERNOON)
- 무드: 맛있는 거 탐방 (FOOD_EXPLORATION)
- 음식 취향: 파스타, 카페
- 예산: 60,000원

**출력 예시**

```
[취향 맥락]
최근 선호: 이탈리안(긍정), 감성카페(긍정) / 최근 방문: 연남동 파스타집, 상수 카페

==================================================
추천 데이트 코스
==================================================
날씨: 맑음 22.5°C

1. 연남동 ○○ 파스타
   주소: 서울 마포구 연남동 123-4
   카테고리: 음식점>이탈리안 | 별점: 4.5
   예상 비용: 25,000원

2. 홍대 감성 카페  (이전 장소에서 12분)
   주소: 서울 마포구 서교동 56-7
   카테고리: 카페>커피전문점 | 별점: 4.2
   예상 비용: 15,000원

3. 합정 디저트 카페  (이전 장소에서 8분)
   주소: 서울 마포구 합정동 89-1
   카테고리: 카페>디저트 | 별점: 4.3
   예상 비용: 15,000원

총 이동 시간: 20분
총 예상 비용: 55,000원
==================================================

코스가 저장되었습니다.
```

**테스트 실행 확인**

```bash
bash run.sh --test
# → 131 passed
```

# 서울 데이트 코스 플래너

사용자가 선택한 서울 지역, 날짜, 시간대, 무드, 음식 취향을 바탕으로 데이트 코스를 추천하는 멀티 에이전트 프로젝트입니다.

선택한 무드마다 관련 장소를 최소 한 곳씩 코스에 포함하도록 검색하고, 이동 시간과 날씨를 반영합니다. 승인한 코스는 취향 DB에 저장되며 다음 추천의 Course Narrator 인사이트에 활용됩니다.

## 주요 기능

- 서울 25개 구 지도 선택
- 복수 시간대와 복수 무드 선택
- 선택 무드별 전용 장소 검색
  - 맛있는 거 탐방: 맛집, 레스토랑
  - 새로운 액티비티: 팝업스토어, 전시회
  - 쇼핑 & 거리 탐방: 편집샵, 쇼핑몰
  - 자연 & 힐링: 공원, 한강
  - 느긋한 카페 투어: 디저트카페, 베이커리카페
- 선택 무드별 장소 최소 1개 우선 포함
- Google Directions 이동 시간 및 OpenWeatherMap 날씨 반영
- 장소 주소와 Google Maps 검색 링크 제공
- 코스 승인 시 장소 취향 학습
- 거절 이유를 반영한 리플랜
- Google Places 검색 결과에서 새 취향 장소 선택

## 핵심 에이전트

현재 핵심 에이전트는 5개입니다.

| 에이전트 | 역할 |
|---|---|
| **Memory Agent** | SQLite에서 저장된 선호·비선호 취향을 읽고, 승인한 코스의 장소를 취향으로 저장 |
| **Search Agent** | Naver Local Search를 선택 무드별로 병렬 호출하고 Google Places로 좌표·영업 정보를 보강 |
| **Route Planner Agent** | 선택 무드별 후보를 최소 한 곳씩 우선 확보하고 이동 시간과 날씨를 반영해 코스 구성 |
| **Course Narrator Agent** | 저장된 취향과 이번 선택 조건을 분석해 커플 취향 인사이트와 코스 구성 이유를 자연어로 생성 |
| **Feedback & Replan Agent** | 승인·거절을 처리하고 거절 이유의 비선호 키워드로 후보를 재필터링 |

`Input Collector`는 핵심 에이전트 목록에서 제외했습니다. 현재 구현은 LLM을 호출하는 에이전트가 아니라 사용자 입력을 검증하고 `UserRequest`로 변환하는 전처리 컴포넌트입니다.

현재 실제 OpenAI 모델 호출은 **Course Narrator Agent**에서 수행합니다. Search, Route Planner, Memory, Feedback은 각각 도구 호출과 규칙 기반 로직을 담당합니다.

## 실행 흐름

```text
Streamlit 입력 폼
  ↓
Input Parser
  입력 검증 → UserRequest 생성
  ↓
Memory Agent
  저장된 취향 맥락 로드
  ↓
Search Agent
  선택 무드별 Naver 검색 병렬 실행
  Google Places 좌표·영업 정보 보강
  ↓
Route Planner Agent
  선택 무드별 장소 최소 1개 우선 선택
  이동 시간·날씨 반영
  ↓
Course Narrator Agent
  저장된 취향 + 이번 선택 조건 분석
  커플 취향 인사이트와 코스 구성 이유 생성
  ↓
HITL 승인 / 거절
  ├─ 승인: Memory Agent가 장소 취향 저장
  └─ 거절: Feedback & Replan Agent가 후보 재필터링 후 코스 재구성
```

초기 추천의 UI 실행 로그에는 다음 4개 에이전트가 표시됩니다.

```text
Memory → Search → Route Planner → Course Narrator
```

`Feedback & Replan`은 사용자가 코스를 거절했을 때만 조건부로 실행 로그에 추가됩니다.

## 후보 장소 선택 기준

1. Search Agent가 기본 음식점·카페 검색과 선택 무드별 전용 검색을 병렬 실행합니다.
2. 각 검색 결과에 어떤 무드에서 발견된 후보인지 `mood_tags`를 기록합니다.
3. Route Planner가 선택한 각 무드에 해당하는 장소를 최소 한 곳씩 먼저 선택합니다.
4. 음식점과 카페는 각각 최대 한 곳만 포함하고, 남은 자리는 액티비티 후보로 보충합니다.
5. 보충 장소는 이전 장소와의 이동 시간이 30분을 초과하면 제외합니다.
6. 무드 필수 장소는 무드 반영을 우선하기 위해 이동 시간이 30분을 넘어도 포함할 수 있습니다.
7. 특정 무드의 검색 결과가 전혀 없으면 UI에 포함하지 못한 무드를 경고합니다.

예를 들어 `맛있는 거 탐방 + 쇼핑 & 거리 탐방 + 새로운 액티비티`를 선택하면 맛집, 편집샵·쇼핑몰, 팝업스토어·전시회 검색 후보를 각각 최소 한 곳씩 우선 구성합니다.
쇼핑·액티비티 검색 결과에 음식점이나 카페가 섞여 나오면 후보 단계에서 제외하므로 여러 음식점을 연속 방문하는 코스로 빈자리를 채우지 않습니다.

## Course Narrator 동작

Course Narrator는 다음 정보를 함께 사용합니다.

- Memory Agent가 읽은 저장 취향
- 이번에 선택한 무드와 음식 취향
- 최종 코스 장소와 순서

출력은 다음 흐름을 따릅니다.

```text
저장된 취향과 이번 선택을 분석해보니 두 분은 새로운 경험과 맛집 탐방을 좋아하는 것 같아요.
그래서 이번 코스는 팝업스토어에서 새로운 분위기를 즐기고, 식사 후 카페에서 여유롭게 마무리하도록 구성했습니다.
```

저장된 취향이 없으면 이번 선택 조건만 근거로 분석하며, 없는 취향을 지어내지 않도록 프롬프트에 명시되어 있습니다. OpenAI 호출이 실패하거나 출력이 길이 제한으로 잘리면 완결된 템플릿 설명으로 대체합니다.

## 외부 API와 저장소

| 구성 | 용도 |
|---|---|
| Naver Local Search | 음식점, 카페, 팝업, 전시, 쇼핑 등 장소 후보 검색 |
| Google Places | 장소 좌표·영업 정보 보강, 새 취향 장소 검색 |
| Google Directions | 장소 간 대중교통 이동 시간 조회 |
| OpenWeatherMap | 선택 지역과 날짜의 날씨 안내 |
| OpenAI | Course Narrator 취향 기반 코스 인사이트 생성 |
| SQLite | 사용자 취향, 방문 기록, 피드백 저장 |

## 설치

### 1. 저장소 클론

```bash
git clone https://github.com/HannahKim/date-planner-agent.git
cd date-planner-agent
```

### 2. 초기 설정

```bash
bash setup.sh
```

`setup.sh`는 다음 작업을 자동으로 수행합니다.

- Python 가상환경 생성
- 필요한 패키지 설치
- `.env.example`을 복사해 `.env` 생성
- 비어 있는 SQLite 취향 DB 준비

처음 클론해서 실행하면 저장된 취향이 없는 상태로 시작합니다. 샘플 취향 데이터는 자동으로 추가되지 않습니다.

## API 키 발급

앱의 모든 기능을 사용하려면 아래 API 키를 발급한 뒤 `.env` 파일에 입력해야 합니다.

### OpenAI API 키

Course Narrator가 커플 취향과 코스 구성 이유를 생성할 때 사용합니다.

1. [OpenAI API Keys](https://platform.openai.com/api-keys)에 로그인합니다.
2. `Create new secret key`를 선택합니다.
3. 생성된 키를 복사해 `OPENAI_API_KEY`에 입력합니다.

OpenAI API 사용을 위해 결제 설정이나 사용 가능한 크레딧이 필요할 수 있습니다.

### Naver Local Search API 키

음식점, 카페, 팝업스토어, 전시회, 편집샵 등의 장소 후보를 검색할 때 사용합니다.

1. [NAVER Developers 애플리케이션](https://developers.naver.com/apps/)에 로그인합니다.
2. `애플리케이션 등록`을 선택합니다.
3. 사용 API에서 `검색`을 선택합니다.
4. 비로그인 오픈 API 서비스 환경을 등록합니다.
5. 발급된 `Client ID`와 `Client Secret`을 각각 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`에 입력합니다.

### Google Places 및 Directions API 키

Google Places는 장소 좌표·영업 정보와 취향 추가 장소 검색에 사용하고, Google Directions는 장소 간 이동 시간 조회에 사용합니다.

1. [Google Cloud Console](https://console.cloud.google.com/)에 로그인합니다.
2. 새 프로젝트를 생성하거나 기존 프로젝트를 선택합니다.
3. 프로젝트에 결제 계정을 연결합니다.
4. `API 및 서비스 → 라이브러리`에서 다음 API를 활성화합니다.
   - Places API
   - Directions API
5. `API 및 서비스 → 사용자 인증 정보`에서 API 키를 생성합니다.
6. API 키 제한 설정에서 사용할 API와 환경을 제한하는 것을 권장합니다.
7. 생성한 키를 `GOOGLE_PLACES_API_KEY`, `GOOGLE_DIRECTIONS_API_KEY`에 입력합니다.

같은 Google API 키를 두 환경 변수에 입력해도 되지만, 운영 환경에서는 API별로 키를 분리하고 제한하는 편이 안전합니다.

### OpenWeatherMap API 키

선택한 지역과 날짜의 날씨 안내를 생성할 때 사용합니다.

1. [OpenWeatherMap](https://openweathermap.org/)에서 계정을 생성합니다.
2. 로그인 후 [API Keys](https://home.openweathermap.org/api_keys) 페이지로 이동합니다.
3. API 키를 생성하거나 기본 발급 키를 확인합니다.
4. 키를 `OPENWEATHERMAP_API_KEY`에 입력합니다.

새 API 키가 활성화되기까지 잠시 시간이 걸릴 수 있습니다.

## 환경 변수 설정

프로젝트 루트의 `.env` 파일을 열어 발급받은 키를 입력합니다.

```env
OPENAI_API_KEY=sk-...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
GOOGLE_PLACES_API_KEY=...
GOOGLE_DIRECTIONS_API_KEY=...
OPENWEATHERMAP_API_KEY=...
```

## 실행

```bash
# Streamlit UI
bash run.sh --ui
```

실행하면 브라우저에서 Streamlit 화면이 열립니다.

## 처음 사용하는 방법

처음 실행하면 저장된 취향이 없는 상태입니다. 취향 등록은 선택 사항이며, 등록하지 않고 바로 코스를 생성해도 됩니다.

1. 원하는 경우 화면 하단의 `취향 관리 → 새 취향 추가`를 엽니다.
2. `약수`, `성수`, `연남동 파스타`처럼 장소명 일부나 지역 키워드를 입력하고 `장소 검색`을 누릅니다.
3. 스크롤 가능한 검색 결과에서 장소명과 주소를 확인한 뒤 정확한 장소를 선택합니다.
4. Google Places 검색 권한이 없거나 결과가 없으면 Naver Local Search 결과가 자동으로 표시됩니다.
5. 좋아하는 장소인지 별로인 장소인지 선택해 취향으로 저장합니다.
6. 지도에서 데이트할 서울 지역을 선택합니다.
7. 날짜, 시간대, 무드, 먹고 싶은 것, 카페 스타일을 선택합니다.
8. `코스 생성`을 누릅니다.
9. 추천 코스와 Course Narrator의 취향 기반 설명을 확인합니다.
10. 코스가 마음에 들면 승인해 다음 추천을 위한 취향으로 저장합니다.
11. 마음에 들지 않으면 거절 이유를 입력해 코스를 다시 구성합니다.

취향을 먼저 등록하면 Course Narrator가 저장된 취향과 이번 선택 조건을 함께 분석합니다. 취향을 등록하지 않은 첫 실행에서는 이번에 선택한 무드와 음식 취향을 기준으로 코스를 설명합니다.

## Agentic Design Patterns

이 프로젝트는 에이전트 역할을 분리하고, 사용자 입력과 피드백에 따라 정해진 파이프라인을 실행합니다. 아래 표는 현재 코드에 실제로 적용된 패턴과 적용 목적을 정리한 것입니다.

### 적용된 패턴

| 패턴 | 적용 목적과 구현 |
|---|---|
| **Prompt Chaining** | `Memory → Search → Route Planner → Course Narrator` 순서로 이전 단계의 결과를 다음 단계 입력으로 전달합니다. 저장 취향, 장소 후보, 완성 코스가 순차적으로 연결됩니다. |
| **Routing** | 선택한 무드에 따라 맛집, 팝업스토어, 전시회, 편집샵 등 서로 다른 검색 쿼리로 라우팅합니다. 승인·거절 여부에 따라서도 저장 또는 리플랜 흐름으로 분기합니다. |
| **Parallelization** | Search Agent가 `ThreadPoolExecutor`를 사용해 선택 무드별 Naver 장소 검색을 병렬 실행하여 검색 대기 시간을 줄입니다. |
| **Tool Use** | Naver Local Search, Google Places, Google Directions, OpenWeatherMap, SQLite를 각 에이전트가 목적에 맞게 호출합니다. |
| **Planning** | Route Planner가 시간대별 목표 장소 수, 선택 무드, 음식점·카페 개수 제한, 이동 시간 제약을 바탕으로 코스를 구성합니다. |
| **Multi-Agent System** | Memory, Search, Route Planner, Course Narrator, Feedback & Replan의 역할과 책임을 분리해 하나의 추천 흐름으로 연결합니다. |
| **Memory Management** | 승인 코스, 직접 등록한 선호·비선호, 피드백을 SQLite에 저장하고 최근 취향을 Course Narrator 입력 맥락으로 불러옵니다. |
| **HITL (Human-in-the-Loop)** | 사용자가 추천 코스를 승인하거나 거절하고, 승인 이유와 거절 이유를 직접 입력해 저장 및 리플랜 결과에 영향을 줍니다. |
| **Guardrails** | 지역·날짜 입력 검증, 최대 코스 장소 수, 장소 간 이동 시간 기준, 음식점·카페 최대 개수, 최대 리플랜 횟수를 제한합니다. |
| **Exception Handling** | 외부 API와 DB 작업 실패를 `try-except`로 처리하고 빈 결과나 기본값으로 폴백하여 앱 전체가 중단되지 않도록 합니다. |
| **Resource-Aware Optimization** | 장소 검색은 병렬 처리하고, 실제 LLM 호출은 자연어 인사이트가 필요한 Course Narrator에만 사용합니다. Narrator 출력이 잘리거나 호출에 실패하면 템플릿으로 폴백합니다. |

### 부분 적용된 패턴

| 패턴 | 현재 적용 범위와 한계 |
|---|---|
| **Reflection** | 사용자의 거절 이유에서 비선호 키워드를 추출해 후보를 제외하고 코스를 다시 구성합니다. 다만 에이전트가 자신의 결과를 스스로 평가하거나 LLM으로 원인을 깊게 분석하는 형태의 완전한 self-reflection은 아닙니다. |
| **Learning and Adaptation** | 승인 코스와 직접 등록한 취향을 저장하고 이후 Course Narrator의 취향 분석에 반영합니다. 현재 Search Agent와 Route Planner의 장소 선택 자체가 저장 취향에 따라 자동 변화하지는 않습니다. |
| **Goal Setting & Monitoring** | 선택 무드별 최소 한 곳 포함, 이동 시간 제한, 리플랜 최대 3회 등의 목표와 진행 상태를 로그로 확인합니다. 동적으로 목표를 생성하거나 우선순위를 재설정하는 별도 Goal Manager는 없습니다. |
| **Evaluation & Monitoring** | 사용자 승인·거절을 평가 신호로 저장하고 에이전트 실행 로그, 무드 반영 수, 리플랜 횟수를 표시합니다. 자동 품질 점수, 회귀 평가 대시보드, 운영 지표 모니터링은 구현되어 있지 않습니다. |

### 현재 적용되지 않은 패턴

| 패턴 | 미적용 이유 |
|---|---|
| **RAG** | 저장 취향을 프롬프트에 넣지만, 문서 임베딩이나 벡터 검색을 사용하는 Retrieval-Augmented Generation 구조는 아닙니다. 현재는 SQLite 기반 구조화 메모리 조회입니다. |
| **MCP** | Model Context Protocol 서버나 MCP 도구를 연결하지 않고 Python API 래퍼를 직접 호출합니다. |
| **A2A** | 에이전트 간 메시지 프로토콜이나 독립 서비스 통신 없이 동일 Python 프로세스에서 함수 호출로 연결합니다. |

따라서 이 프로젝트를 설명할 때는 `Prompt Chaining`, `Routing`, `Parallelization`, `Tool Use`, `Planning`, `Multi-Agent System`, `Memory Management`, `HITL`, `Guardrails`, `Exception Handling`, `Resource-Aware Optimization`을 주요 적용 패턴으로 소개하는 것이 가장 정확합니다.

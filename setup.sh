#!/usr/bin/env bash
# 프로젝트 초기 환경 세팅 스크립트
# 사용법: bash setup.sh

set -e  # 에러 발생 시 즉시 중단

PYTHON=${PYTHON:-python3}
VENV_DIR=".venv"

echo "=== Date Planner Agent 초기 설정 시작 ==="

# 1. Python 버전 확인
echo ""
echo "[1/5] Python 버전 확인..."
if ! command -v "$PYTHON" &>/dev/null; then
    echo "오류: python3를 찾을 수 없습니다. Python 3.9 이상을 설치해 주세요."
    exit 1
fi
PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "    Python $PYTHON_VERSION 감지됨"
if [[ $(echo "$PYTHON_VERSION < 3.9" | bc) -eq 1 ]]; then
    echo "오류: Python 3.9 이상이 필요합니다. 현재 버전: $PYTHON_VERSION"
    exit 1
fi

# 2. 가상환경 생성
echo ""
echo "[2/5] 가상환경 설정..."
if [ -d "$VENV_DIR" ]; then
    echo "    기존 가상환경 발견: $VENV_DIR (재사용)"
else
    "$PYTHON" -m venv "$VENV_DIR"
    echo "    가상환경 생성 완료: $VENV_DIR"
fi

# 3. 의존성 설치
echo ""
echo "[3/5] 패키지 설치 중..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r requirements.txt --quiet
echo "    패키지 설치 완료"

# 4. .env 파일 생성
echo ""
echo "[4/5] 환경 변수 파일 설정..."
if [ -f ".env" ]; then
    echo "    기존 .env 파일이 존재합니다. 덮어쓰지 않습니다."
else
    cp .env.example .env
    echo "    .env 파일 생성 완료"
    echo ""
    echo "    >>> .env 파일에 API 키를 입력해 주세요 (run.sh --help 참고) <<<"
fi

# 5. DB 초기화 및 시드 데이터 삽입
echo ""
echo "[5/5] DB 초기화 및 시드 데이터 삽입..."
"$VENV_DIR/bin/python" -c "
from date_planner.memory.preference_store import init_db
from date_planner.data.seed_data import insert_seed_data
init_db()
insert_seed_data()
"
echo "    DB 초기화 및 샘플 취향 데이터 삽입 완료"

echo ""
echo "=== 설정 완료! ==="
echo ""
echo "다음 명령어로 실행하세요:"
echo "  CLI 모드:  bash run.sh"
echo "  UI  모드:  bash run.sh --ui"
echo "  테스트:    bash run.sh --test"
echo ""

#!/usr/bin/env bash
# 프로젝트 실행 스크립트
#
# 사용법:
#   bash run.sh           # Streamlit UI 실행 (기본)
#   bash run.sh --cli     # CLI 모드로 코스 생성
#   bash run.sh --test    # 전체 테스트 실행
#   bash run.sh --seed    # 시드 데이터 재삽입 후 CLI 실행
#   bash run.sh --help    # 도움말 출력

set -e

VENV_DIR=".venv"
PYTHON="$VENV_DIR/bin/python"
STREAMLIT="$VENV_DIR/bin/streamlit"
PYTEST="$VENV_DIR/bin/pytest"

# 가상환경 존재 여부 확인
if [ ! -f "$PYTHON" ]; then
    echo "오류: 가상환경이 없습니다. 먼저 setup.sh를 실행해 주세요."
    echo "  bash setup.sh"
    exit 1
fi

# .env 로드 (있을 경우)
if [ -f ".env" ]; then
    set -o allexport
    source .env
    set +o allexport
fi


_print_help() {
    echo ""
    echo "Date Planner Agent 실행 스크립트"
    echo ""
    echo "사용법:"
    echo "  bash run.sh           Streamlit UI 실행 (기본, 브라우저 자동 열림)"
    echo "  bash run.sh --cli     CLI 모드 (콘솔에서 코스 확인)"
    echo "  bash run.sh --test    전체 pytest 실행"
    echo "  bash run.sh --seed    시드 데이터 재삽입 후 CLI 실행"
    echo "  bash run.sh --help    이 도움말 출력"
    echo ""
    echo "API 키: .env 파일에 키 입력 후 실행"
    echo ""
}

_run_cli() {
    echo "=== CLI 모드 실행 ==="
    "$PYTHON" main.py "$@"
}

_run_ui() {
    echo "=== Streamlit UI 실행 ==="
    echo "브라우저에서 http://localhost:8501 이 열립니다."
    echo "종료하려면 Ctrl+C 를 누르세요."
    echo ""
    "$STREAMLIT" run date_planner/ui/streamlit_app.py \
        --server.headless false \
        --browser.gatherUsageStats false
}

_run_tests() {
    echo "=== 전체 테스트 실행 ==="
    "$PYTEST" date_planner/tests/ -v
}

_run_seed() {
    echo "=== 시드 데이터 재삽입 ==="
    "$PYTHON" -c "
from date_planner.data.seed_data import insert_seed_data
insert_seed_data()
print('완료')
"
    _run_cli
}

# 인수 처리 (기본: UI)
case "${1:-}" in
    ""|--ui)  _run_ui ;;
    --cli)    _run_cli ;;
    --test)   _run_tests ;;
    --seed)   _run_seed ;;
    --help)   _print_help ;;
    *)
        echo "알 수 없는 옵션: $1"
        _print_help
        exit 1
        ;;
esac

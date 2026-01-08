#!/bin/bash

# ===============================================
# PhotoX v4 启动脚本
# ===============================================

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# 显示帮助
show_help() {
    echo "==============================================="
    echo "         PhotoX v4 - 照片整理工具"
    echo "==============================================="
    echo ""
    echo "用法:"
    echo "  $0 <命令> [--source <目录>]"
    echo ""
    echo "命令:"
    echo "  init          初始化环境（创建虚拟环境、安装依赖）"
    echo "  run           运行照片整理（正常模式）"
    echo "  dry-run       预演模式（只显示操作，不移动文件）"
    echo "  build-index   仅建立目标目录的 MD5 索引"
    echo "  status        显示当前状态和统计"
    echo "  help          显示此帮助信息"
    echo ""
    echo "选项:"
    echo "  --source, -s  指定源目录（覆盖 config.yaml 中的 source）"
    echo ""
    echo "示例:"
    echo "  $0 init                              # 首次使用：初始化环境"
    echo "  $0 build-index                       # 首次使用：建立 MD5 索引"
    echo "  $0 dry-run                           # 预演模式（使用配置文件中的 source）"
    echo "  $0 run                               # 正式运行"
    echo "  $0 run --source ~/Photos/2024        # 指定源目录运行"
    echo "  $0 dry-run -s /path/to/photos        # 预演指定目录"
    echo ""
    echo "配置文件: $SCRIPT_DIR/config.yaml"
    echo "==============================================="
}

# 检查/初始化虚拟环境
init_env() {
    log_info "初始化 PhotoX 环境..."
    
    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        log_error "未找到 python3，请先安装 Python 3.9+"
        exit 1
    fi
    
    # 检查 exiftool
    if ! command -v exiftool &> /dev/null; then
        log_warning "未找到 exiftool，正在安装..."
        if command -v brew &> /dev/null; then
            brew install exiftool
        else
            log_error "请手动安装 exiftool: brew install exiftool"
            exit 1
        fi
    fi
    
    # 创建虚拟环境
    if [ ! -d ".venv" ]; then
        log_info "创建 Python 虚拟环境..."
        python3 -m venv .venv
    fi
    
    # 激活并安装依赖
    source .venv/bin/activate
    log_info "安装 Python 依赖..."
    pip install -q -r requirements.txt
    
    # 检查配置文件
    if [ ! -f "config.yaml" ]; then
        log_info "创建配置文件..."
        cp config.example.yaml config.yaml
        log_warning "请编辑 config.yaml 设置你的路径"
    fi
    
    log_success "环境初始化完成！"
    echo ""
    echo "下一步："
    echo "  1. 编辑 config.yaml 设置 source 和 dest 路径"
    echo "  2. 运行: $0 build-index   # 建立 MD5 索引"
    echo "  3. 运行: $0 dry-run       # 预演模式"
}

# 激活虚拟环境
activate_venv() {
    if [ ! -d ".venv" ]; then
        log_error "虚拟环境不存在，请先运行: $0 init"
        exit 1
    fi
    source .venv/bin/activate
}

# 检查配置文件
check_config() {
    if [ ! -f "config.yaml" ]; then
        log_error "配置文件不存在，请先运行: $0 init"
        exit 1
    fi
}

# 运行 Python 主程序
run_python() {
    activate_venv
    check_config
    python main.py "$@"
}

# 显示状态
show_status() {
    activate_venv
    check_config
    
    # 获取配置中的 dest 目录
    DEST=$(python -c "import yaml; print(yaml.safe_load(open('config.yaml'))['paths']['dest'])")
    DATA_DIR="$DEST/.photox"
    
    echo "==============================================="
    echo "         PhotoX v4 状态"
    echo "==============================================="
    echo ""
    
    # 数据库统计
    if [ -f "$DATA_DIR/photo_md5.sqlite3" ]; then
        log_info "数据库: $DATA_DIR/photo_md5.sqlite3"
        HASH_COUNT=$(sqlite3 "$DATA_DIR/photo_md5.sqlite3" "SELECT COUNT(*) FROM hash_lib;" 2>/dev/null || echo "0")
        echo "  已索引文件数: $HASH_COUNT"
    else
        log_warning "数据库不存在，请先运行: $0 build-index"
    fi
    
    # 运行历史
    if [ -f "$DATA_DIR/run_history.json" ]; then
        echo ""
        log_info "最近运行记录:"
        python -c "
import json
with open('$DATA_DIR/run_history.json') as f:
    history = json.load(f)
for run in history[-3:]:
    print(f\"  {run['run_id']}: moved={run['counts']['moved']}, dup={run['counts']['duplicate']}, dest_dup={run['counts']['dest_duplicate']}\")
"
    fi
    
    echo ""
}

# 解析 --source 参数
parse_source_arg() {
    SOURCE_ARG=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source|-s)
                if [ -n "$2" ]; then
                    SOURCE_ARG="--source $2"
                    shift 2
                else
                    log_error "--source 需要指定目录"
                    exit 1
                fi
                ;;
            *)
                shift
                ;;
        esac
    done
}

# 主逻辑
CMD="${1:-help}"
shift 2>/dev/null || true

# 解析剩余参数中的 --source
parse_source_arg "$@"

case "$CMD" in
    init)
        init_env
        ;;
    run)
        log_info "运行照片整理（正常模式）..."
        if [ -n "$SOURCE_ARG" ]; then
            log_info "源目录: $(echo $SOURCE_ARG | cut -d' ' -f2)"
        fi
        run_python $SOURCE_ARG
        ;;
    dry-run|dryrun)
        log_info "运行照片整理（预演模式）..."
        if [ -n "$SOURCE_ARG" ]; then
            log_info "源目录: $(echo $SOURCE_ARG | cut -d' ' -f2)"
        fi
        run_python --dry-run $SOURCE_ARG
        ;;
    build-index|index)
        log_info "建立目标目录 MD5 索引..."
        run_python --include-dest
        ;;
    status|stats)
        show_status
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        log_error "未知命令: $CMD"
        echo ""
        show_help
        exit 1
        ;;
esac


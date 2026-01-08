#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PhotoX v4 - macOS 照片整理与去重系统

用法:
    python main.py [--source <目录>] [--dry-run] [--include-dest]

依赖:
    - Python 3.9+
    - exiftool (brew install exiftool)
    - pyyaml (pip install pyyaml)
"""

import argparse
import sys
from pathlib import Path

# 脚本所在目录
SCRIPT_DIR = Path(__file__).parent.resolve()

# 默认配置文件路径（固定为脚本目录下的 config.yaml）
DEFAULT_CONFIG = SCRIPT_DIR / "config.yaml"

# 添加包路径
sys.path.insert(0, str(SCRIPT_DIR))

from photo_organizer.config import Config
from photo_organizer.organizer import PhotoOrganizer


def main():
    ap = argparse.ArgumentParser(
        description="PhotoX v4 - macOS 照片整理与去重系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
配置文件: {DEFAULT_CONFIG}

示例:
  # 预演模式（不实际移动文件）
  python main.py --dry-run

  # 正式运行
  python main.py

  # 指定源目录（覆盖配置文件）
  python main.py --source /path/to/photos

  # 首次运行时将 dest 已有文件入库
  python main.py --include-dest
        """
    )
    
    ap.add_argument(
        "--source", "-s",
        help="源目录路径（覆盖配置文件中的 source）"
    )
    
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="预演模式：只打印动作，不实际移动文件"
    )
    
    ap.add_argument(
        "--include-dest",
        action="store_true",
        help="将 dest 目录已有文件入库（首次运行建议开启）"
    )
    
    args = ap.parse_args()
    
    # 加载配置（固定路径）
    config_path = DEFAULT_CONFIG
    if not config_path.exists():
        print(f"[ERROR] 配置文件不存在: {config_path}", file=sys.stderr)
        print(f"[提示] 请先创建配置文件: cp config.example.yaml config.yaml", file=sys.stderr)
        sys.exit(1)
    
    try:
        config = Config.from_yaml(config_path)
    except Exception as e:
        print(f"[ERROR] 配置文件解析失败: {e}", file=sys.stderr)
        sys.exit(1)
    
    # CLI 参数覆盖配置
    if args.source:
        source_path = Path(args.source).expanduser().resolve()
        config.paths.source = source_path
    if args.dry_run:
        config.dry_run = True
    if args.include_dest:
        config.include_dest = True
    
    # 运行整理器
    organizer = PhotoOrganizer(config)
    organizer.run()


if __name__ == "__main__":
    main()


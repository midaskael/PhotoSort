#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将目录中的文件移动到二次确认目录（递归扫描，保持目录结构）

用法:
    python check_files.py <目录>             # 直接移动
    python check_files.py <目录> --dry-run   # 预览（不移动）

示例:
    python check_files.py ~/Documents/Photo/整理前 --dry-run
    python check_files.py ~/Documents/Photo/整理前
"""

import argparse
import shutil
import sys
from pathlib import Path
from collections import Counter

# 脚本所在目录
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = SCRIPT_DIR / "config.yaml"


def load_second_check_dir():
    """从配置文件加载二次确认目录"""
    try:
        import yaml
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config.get('paths', {}).get('second_check_dir')
    except Exception as e:
        print(f"[ERROR] 读取配置文件失败: {e}", file=sys.stderr)
        return None


def process_directory(directory: Path, move_to: Path, dry_run: bool = False):
    """处理目录中的文件"""
    
    all_files = []
    ext_counter = Counter()
    
    # 递归扫描
    for p in directory.rglob('*'):
        if p.is_file() and not p.name.startswith('.'):
            all_files.append(p)
            ext = p.suffix.lower() if p.suffix else '(无扩展名)'
            ext_counter[ext] += 1
    
    total = len(all_files)
    
    print(f"[INFO] 源目录: {directory}")
    print(f"[INFO] 目标目录: {move_to}")
    print(f"[INFO] 文件总数: {total}")
    
    if dry_run:
        print("[INFO] 预览模式，不实际移动")
    print()
    
    if total == 0:
        print("[INFO] 目录为空，无需处理 ✅")
        return
    
    # 按扩展名统计
    print("[INFO] 按扩展名统计:")
    for ext, count in ext_counter.most_common(20):
        print(f"  {ext}: {count}")
    print()
    
    # 移动文件
    moved_count = 0
    error_count = 0
    
    for p in all_files:
        # 保持相对路径结构
        rel_path = p.relative_to(directory)
        target = move_to / rel_path
        
        if dry_run:
            print(f"[DRY] {rel_path}")
        else:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(target))
                moved_count += 1
            except Exception as e:
                print(f"[ERR] {rel_path}: {e}")
                error_count += 1
    
    print()
    print(f"[INFO] === 完成 ===")
    if dry_run:
        print(f"[INFO] 待移动文件: {total}")
        print(f"[提示] 去掉 --dry-run 参数执行实际移动")
    else:
        print(f"[INFO] 成功移动: {moved_count}")
        if error_count > 0:
            print(f"[WARN] 失败: {error_count}")


def main():
    parser = argparse.ArgumentParser(description="将目录中的文件移动到二次确认目录")
    parser.add_argument("directory", help="要处理的目录路径")
    parser.add_argument("--dry-run", "-n", action="store_true", help="预演模式，不实际移动")
    
    args = parser.parse_args()
    
    directory = Path(args.directory).expanduser().resolve()
    
    if not directory.exists():
        print(f"[ERROR] 目录不存在: {directory}", file=sys.stderr)
        sys.exit(1)
    
    if not directory.is_dir():
        print(f"[ERROR] 路径不是目录: {directory}", file=sys.stderr)
        sys.exit(1)
    
    # 读取配置
    second_check_dir = load_second_check_dir()
    if not second_check_dir:
        print(f"[ERROR] 配置文件中未设置 second_check_dir", file=sys.stderr)
        print(f"[提示] 请在 {CONFIG_FILE} 中添加 paths.second_check_dir", file=sys.stderr)
        sys.exit(1)
    
    move_to = Path(second_check_dir).expanduser().resolve()
    
    process_directory(directory, move_to, args.dry_run)


if __name__ == "__main__":
    main()

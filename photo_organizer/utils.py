# -*- coding: utf-8 -*-
"""通用工具函数模块"""

import secrets
import shutil
from datetime import datetime
from pathlib import Path


def now_run_id() -> str:
    """生成运行 ID"""
    t = datetime.now().strftime("%Y%m%d-%H%M%S")
    rnd = secrets.token_hex(3)
    return f"{t}-{rnd}"


def safe_move(src: Path, dst: Path) -> Path:
    """
    安全移动文件（处理同名冲突）
    
    Args:
        src: 源文件
        dst: 目标路径
        
    Returns:
        实际移动到的路径
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    
    if not dst.exists():
        shutil.move(str(src), str(dst))
        return dst
    
    # 处理冲突：添加序号后缀
    stem = dst.stem
    suffix = dst.suffix
    
    for i in range(1, 1000000):
        candidate = dst.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            shutil.move(str(src), str(candidate))
            return candidate
    
    raise RuntimeError(f"Too many name conflicts for {dst}")


def make_unique_newname(target_dir: Path, yyyymmdd: str, ext: str) -> str:
    """
    生成唯一文件名
    
    格式: IMG_YYYYMMDD_XXXXXX.ext (XXXXXX 为 6 位随机数)
    
    Args:
        target_dir: 目标目录
        yyyymmdd: 日期字符串
        ext: 文件扩展名
        
    Returns:
        文件名（不含目录）
    """
    ext = ext if ext.startswith(".") else ("." + ext)
    ext = ext.lower()
    
    for _ in range(2000):
        rnd = secrets.randbelow(1_000_000)
        stem = f"IMG_{yyyymmdd}_{rnd:06d}"
        cand_main = target_dir / f"{stem}{ext}"
        cand_aae = target_dir / f"{stem}.aae"
        cand_mov = target_dir / f"{stem}.mov"
        
        # 确保主文件、AAE、Live Video 都不冲突
        if not cand_main.exists() and not cand_aae.exists() and not cand_mov.exists():
            return f"{stem}{ext}"
    
    # fallback: 使用更长的随机 token
    stem = f"IMG_{yyyymmdd}_{secrets.token_hex(4)}"
    return f"{stem}{ext}"


def print_progress(done: int, total: int, last_percent: int, prefix: str = "") -> int:
    """
    打印横向进度条（原地更新）
    
    Args:
        done: 已完成数量
        total: 总数量
        last_percent: 上次打印的百分比
        prefix: 前缀文字
        
    Returns:
        当前百分比
    """
    import sys
    
    if total <= 0:
        return last_percent
    
    percent = int(done * 100 / total)
    
    # 只在百分比变化时更新
    if percent > last_percent or done == total:
        bar_width = 40
        filled = int(bar_width * done / total)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        prefix_str = f"{prefix} " if prefix else ""
        line = f"\r{prefix_str}[{bar}] {percent:3d}% ({done}/{total})"
        
        sys.stdout.write(line)
        sys.stdout.flush()
        
        # 完成时换行
        if done == total:
            print()
        
        return percent
    
    return last_percent


def check_exiftool() -> bool:
    """检查 exiftool 是否可用"""
    return shutil.which("exiftool") is not None

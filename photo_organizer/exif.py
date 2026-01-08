# -*- coding: utf-8 -*-
"""EXIF 时间提取模块"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# EXIF 时间字段优先级
DATETIME_FIELDS = [
    "DateTimeOriginal",
    "CreateDate", 
    "MediaCreateDate",
    "CreationDate",
    "TrackCreateDate",
    "ModifyDate",
]


def parse_exif_datetime(s: str) -> Optional[datetime]:
    """
    解析 EXIF 时间字符串
    
    支持格式：
    - 2017:02:05 12:34:56
    - 2017-02-05 12:34:56
    - 2017-02-05T12:34:56
    - 2017-02-05 12:34:56+08:00
    - 2017-02-05 12:34:56Z
    - 2017-02-05 12:34:56.123456
    
    Args:
        s: 时间字符串
        
    Returns:
        datetime 对象（本地时间），解析失败返回 None
    """
    if not s:
        return None
    
    s = str(s).strip()
    
    # 标准化 YYYY:MM:DD -> YYYY-MM-DD
    if len(s) >= 10 and s[4] == ":" and s[7] == ":":
        s = s[:10].replace(":", "-") + s[10:]
    
    # 处理 Z 时区
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    
    # 处理 +0800 -> +08:00 格式
    s = re.sub(r'([+-])(\d{2})(\d{2})$', r'\1\2:\3', s)
    
    # 尝试多种格式
    formats = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S.%f",
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            # 转换为本地时间
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    
    return None


def exiftool_batch_datetime(
    paths: List[Path], 
    chunk_size: int = 800
) -> Dict[Path, Optional[datetime]]:
    """
    批量读取文件的 EXIF 拍摄时间
    
    Args:
        paths: 文件路径列表
        chunk_size: 每批处理的文件数
        
    Returns:
        {path: datetime} 字典，无法获取时间时值为 None
    """
    import sys
    
    result: Dict[Path, Optional[datetime]] = {p: None for p in paths}
    
    if not paths:
        return result
    
    total = len(paths)
    last_percent = -1
    
    # 分批处理
    for i in range(0, len(paths), chunk_size):
        batch = paths[i:i + chunk_size]
        batch_result = _exiftool_batch(batch)
        result.update(batch_result)
        
        # 显示进度条
        done = min(i + chunk_size, total)
        percent = int(done * 100 / total)
        if percent > last_percent or done == total:
            bar_width = 40
            filled = int(bar_width * done / total)
            bar = "█" * filled + "░" * (bar_width - filled)
            line = f"\r[EXIF] [{bar}] {percent:3d}% ({done}/{total})"
            sys.stdout.write(line)
            sys.stdout.flush()
            if done == total:
                print()
            last_percent = percent
    
    return result


def _exiftool_batch(paths: List[Path]) -> Dict[Path, Optional[datetime]]:
    """单批次 ExifTool 调用"""
    out: Dict[Path, Optional[datetime]] = {p: None for p in paths}
    
    if not paths:
        return out
    
    # 构建命令
    cmd = ["exiftool", "-json", "-n"]
    cmd.extend([f"-{f}" for f in DATETIME_FIELDS])
    cmd.extend([str(p) for p in paths])
    
    try:
        r = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=300  # 5分钟超时
        )
    except subprocess.TimeoutExpired:
        return out
    except Exception:
        return out
    
    if r.returncode != 0 or not r.stdout.strip():
        return out
    
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return out
    
    # 构建路径查找表
    lookup: Dict[str, Path] = {}
    for p in paths:
        lookup[str(p)] = p
        try:
            lookup[str(p.resolve())] = p
        except Exception:
            pass
    
    # 解析结果
    for item in data:
        sf = item.get("SourceFile")
        if not sf:
            continue
        
        # 查找对应的 Path
        p = lookup.get(sf)
        if not p:
            try:
                p = lookup.get(str(Path(sf).resolve()))
            except Exception:
                continue
        
        if not p:
            continue
        
        # 按优先级尝试获取时间
        dt = None
        for field in DATETIME_FIELDS:
            v = item.get(field)
            if v:
                dt = parse_exif_datetime(str(v))
                if dt:
                    break
        
        out[p] = dt
    
    return out


def chunked(lst: List[Path], n: int):
    """将列表分块"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

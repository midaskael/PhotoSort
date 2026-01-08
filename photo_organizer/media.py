# -*- coding: utf-8 -*-
"""媒体文件扫描与绑定模块"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .config import Config


@dataclass
class MediaItem:
    """媒体文件项"""
    master: Path                          # 主文件
    sidecar_aae: Optional[Path] = None    # AAE sidecar
    live_video: Optional[Path] = None     # Live Photo 视频


# AAE 主文件选择优先级
AAE_MASTER_PRIORITY = [
    ".heic", ".heif", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
    ".mov", ".mp4", ".m4v", ".avi", ".mkv", ".3gp",
    ".dng", ".cr2", ".nef", ".arw",
]


class MediaScanner:
    """媒体文件扫描器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.extensions = config.extensions
        self.live_config = config.live_photo
    
    def iter_files(self, root: Path):
        """遍历目录下所有文件"""
        for p in root.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    yield p
            except (FileNotFoundError, PermissionError, OSError):
                continue
    
    def scan(self, source: Path) -> Tuple[List[MediaItem], List[Path], List[Path]]:
        """
        扫描并构建媒体项列表
        
        Args:
            source: 源目录
            
        Returns:
            (items, orphan_aaes, unrecognized) - 媒体项列表、孤立 AAE 列表、未识别文件列表
        """
        # 确定要扫描的扩展名（排除 Live Video 扩展名，它们会单独处理）
        live_video_exts: Set[str] = set()
        if self.live_config.enabled:
            live_video_exts = {self.live_config.video_ext.lower()}
        
        scan_exts = self.extensions - live_video_exts
        
        # 构建主文件索引: dir -> stem -> [masters]
        master_idx: Dict[Path, Dict[str, List[Path]]] = {}
        
        # 收集 AAE 和 Live Video
        aaes: List[Path] = []
        mov_by_dir: Dict[Path, Dict[str, Path]] = {}
        
        # 未识别的文件
        unrecognized: List[Path] = []
        
        # 单次遍历收集所有文件
        for p in self.iter_files(source):
            # 跳过隐藏文件
            if p.name.startswith('.'):
                continue
            
            suf = p.suffix.lower()
            
            if suf == ".aae":
                aaes.append(p)
            elif self.live_config.enabled and suf in live_video_exts:
                mov_by_dir.setdefault(p.parent, {})[p.stem] = p
            elif suf in scan_exts:
                master_idx.setdefault(p.parent, {}).setdefault(p.stem, []).append(p)
            else:
                # 未识别的文件
                unrecognized.append(p)
        
        # 绑定 Live Video 到主图
        master_to_live: Dict[Path, Path] = {}
        bound_movs: Set[Path] = set()
        
        if self.live_config.enabled:
            for d, stems in master_idx.items():
                dir_movs = mov_by_dir.get(d, {})
                for stem, masters in stems.items():
                    if stem in dir_movs:
                        # 只绑定到可能是 Live Photo 主图的文件
                        for m in masters:
                            if m.suffix.lower() in self.live_config.master_exts:
                                master_to_live[m] = dir_movs[stem]
                                bound_movs.add(dir_movs[stem])
                                break
        
        # 未绑定的 MOV 作为普通视频文件处理
        for d, stem_movs in mov_by_dir.items():
            for stem, mov in stem_movs.items():
                if mov not in bound_movs:
                    master_idx.setdefault(d, {}).setdefault(stem, []).append(mov)
        
        # 绑定 AAE 到主文件
        aae_binding: Dict[Path, Optional[Path]] = {}
        orphan_aaes: List[Path] = []
        
        for aae in aaes:
            d = aae.parent
            stem = aae.stem
            candidates = master_idx.get(d, {}).get(stem, [])
            
            if not candidates:
                aae_binding[aae] = None
                orphan_aaes.append(aae)
            elif len(candidates) == 1:
                aae_binding[aae] = candidates[0]
            else:
                # 多候选时按优先级选择
                aae_binding[aae] = self._choose_master(candidates)
        
        # 构建 master -> aae 映射（一个主文件只绑定一个 AAE）
        master_to_aae: Dict[Path, Path] = {}
        for aae, m in aae_binding.items():
            if m is not None:
                master_to_aae.setdefault(m, aae)
        
        # 构建 MediaItem 列表
        items: List[MediaItem] = []
        for d, stems in master_idx.items():
            for stem, masters in stems.items():
                for m in masters:
                    items.append(MediaItem(
                        master=m,
                        sidecar_aae=master_to_aae.get(m),
                        live_video=master_to_live.get(m),
                    ))
        
        return items, orphan_aaes, unrecognized
    
    def _choose_master(self, candidates: List[Path]) -> Path:
        """
        多候选时选择主文件
        
        优先级：
        1. 按扩展名优先级（HEIC > JPG > ...）
        2. 同优先级选择文件更大的
        """
        pri = {ext: i for i, ext in enumerate(AAE_MASTER_PRIORITY)}
        
        def key(p: Path):
            try:
                size = p.stat().st_size
            except Exception:
                size = 0
            return (pri.get(p.suffix.lower(), 10_000), -size)
        
        return sorted(candidates, key=key)[0]

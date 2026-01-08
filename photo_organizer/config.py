# -*- coding: utf-8 -*-
"""配置加载与管理模块"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set
import yaml


@dataclass
class PathsConfig:
    """路径配置"""
    source: Path
    dest: Path
    data_dir: Optional[Path] = None  # 统一数据目录
    dup_dir: Optional[Path] = None
    orphan_aae_dir: Optional[Path] = None
    second_check_dir: Optional[Path] = None  # 二次确认目录
    db_path: Optional[Path] = None
    
    def __post_init__(self):
        self.source = Path(self.source).expanduser().resolve()
        self.dest = Path(self.dest).expanduser().resolve()
        
        # 统一数据目录（默认 <dest>/.photox/）
        if self.data_dir is None:
            self.data_dir = self.dest / ".photox"
        else:
            self.data_dir = Path(self.data_dir).expanduser().resolve()
        
        # 默认值
        if self.dup_dir is None:
            self.dup_dir = self.dest / "待删除"
        else:
            self.dup_dir = Path(self.dup_dir).expanduser().resolve()
            
        if self.orphan_aae_dir is None:
            self.orphan_aae_dir = self.dest / "AAE_孤立"
        else:
            self.orphan_aae_dir = Path(self.orphan_aae_dir).expanduser().resolve()
        
        if self.second_check_dir is None:
            self.second_check_dir = self.dest / "二次确认"
        else:
            self.second_check_dir = Path(self.second_check_dir).expanduser().resolve()
            
        if self.db_path is None:
            self.db_path = self.data_dir / "photo_md5.sqlite3"
        else:
            self.db_path = Path(self.db_path).expanduser().resolve()
    
    @property
    def reports_dir(self) -> Path:
        """报告目录"""
        return self.data_dir / "reports"
    
    @property
    def history_file(self) -> Path:
        """运行历史文件"""
        return self.data_dir / "run_history.json"


@dataclass
class LivePhotoConfig:
    """Live Photo 配置"""
    enabled: bool = True
    video_ext: str = ".mov"
    master_exts: Set[str] = field(default_factory=lambda: {".heic", ".heif", ".jpg", ".jpeg"})
    
    def __post_init__(self):
        # 确保是 set 类型
        if isinstance(self.master_exts, list):
            self.master_exts = set(self.master_exts)


@dataclass
class PerformanceConfig:
    """性能配置"""
    exiftool_chunk_size: int = 800
    hash_workers: int = 4
    hash_threshold_mb: int = 10


@dataclass
class DedupConfig:
    """去重配置"""
    verify_tail_collision: bool = True


@dataclass
class Config:
    """主配置类"""
    paths: PathsConfig
    extensions: Set[str]
    live_photo: LivePhotoConfig
    performance: PerformanceConfig
    dedup: DedupConfig
    dry_run: bool = False
    include_dest: bool = False
    
    @classmethod
    def from_yaml(cls, config_path: Path) -> "Config":
        """从 YAML 文件加载配置"""
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        # 解析路径配置
        paths_data = data.get("paths", {})
        paths = PathsConfig(
            source=paths_data.get("source", "."),
            dest=paths_data.get("dest", "./照片整理"),
            data_dir=paths_data.get("data_dir"),
            dup_dir=paths_data.get("dup_dir"),
            orphan_aae_dir=paths_data.get("orphan_aae_dir"),
            second_check_dir=paths_data.get("second_check_dir"),
            db_path=paths_data.get("db_path"),
        )
        
        # 解析扩展名
        ext_data = data.get("extensions", {})
        extensions = set()
        for category, exts in ext_data.items():
            if isinstance(exts, list):
                for e in exts:
                    e = e.strip().lower()
                    if not e.startswith("."):
                        e = "." + e
                    extensions.add(e)
        
        # 默认扩展名
        if not extensions:
            extensions = {
                ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", 
                ".gif", ".bmp", ".webp", ".mp4", ".mov", ".m4v", ".avi", 
                ".mkv", ".3gp", ".dng", ".cr2", ".nef", ".arw"
            }
        
        # 解析 Live Photo 配置
        live_data = data.get("live_photo", {})
        live_photo = LivePhotoConfig(
            enabled=live_data.get("enabled", True),
            video_ext=live_data.get("video_ext", ".mov"),
            master_exts=set(live_data.get("master_exts", [".heic", ".heif", ".jpg", ".jpeg"])),
        )
        
        # 解析性能配置
        perf_data = data.get("performance", {})
        performance = PerformanceConfig(
            exiftool_chunk_size=perf_data.get("exiftool_chunk_size", 800),
            hash_workers=perf_data.get("hash_workers", 4),
            hash_threshold_mb=perf_data.get("hash_threshold_mb", 10),
        )
        
        # 解析去重配置
        dedup_data = data.get("dedup", {})
        dedup = DedupConfig(
            verify_tail_collision=dedup_data.get("verify_tail_collision", True),
        )
        
        # 解析运行选项
        options = data.get("options", {})
        
        return cls(
            paths=paths,
            extensions=extensions,
            live_photo=live_photo,
            performance=performance,
            dedup=dedup,
            dry_run=options.get("dry_run", False),
            include_dest=options.get("include_dest", False),
        )
    
    def validate(self, check_source: bool = True) -> None:
        """验证配置有效性"""
        if check_source:
            if not self.paths.source.exists():
                raise ValueError(f"源目录不存在: {self.paths.source}")
            if not self.paths.source.is_dir():
                raise ValueError(f"源路径不是目录: {self.paths.source}")

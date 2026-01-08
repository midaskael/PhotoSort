# -*- coding: utf-8 -*-
"""Hash 计算模块（支持并行）"""

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Hasher:
    """Hash 计算器"""
    
    def __init__(self, threshold_mb: int = 10, workers: int = 4):
        """
        初始化 Hasher
        
        Args:
            threshold_mb: 大于此值(MB)的文件使用 tail10m 方法
            workers: 并行计算线程数
        """
        self.threshold = threshold_mb * 1024 * 1024
        self.tail_size = 10 * 1024 * 1024  # 固定 10MB
        self.workers = workers
    
    def compute_md5(self, path: Path) -> Tuple[str, str]:
        """
        计算文件 MD5
        
        Args:
            path: 文件路径
            
        Returns:
            (md5, method) - method 为 'full' 或 'tail10m'
        """
        size = path.stat().st_size
        h = hashlib.md5()
        
        with path.open("rb") as f:
            if size <= self.threshold:
                # 小文件：全量计算
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
                return h.hexdigest(), "full"
            else:
                # 大文件：只计算末尾 10MB
                if size > self.tail_size:
                    f.seek(size - self.tail_size)
                data = f.read(self.tail_size)
                h.update(data)
                return h.hexdigest(), "tail10m"
    
    def compute_full_md5(self, path: Path) -> str:
        """
        强制计算全量 MD5（用于二次确认）
        
        Args:
            path: 文件路径
            
        Returns:
            md5 字符串
        """
        h = hashlib.md5()
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    
    def compute_batch(
        self, 
        paths: List[Path]
    ) -> Dict[Path, Tuple[Optional[str], Optional[str]]]:
        """
        并行计算多个文件的 MD5
        
        Args:
            paths: 文件路径列表
            
        Returns:
            {path: (md5, method)} 字典，失败时值为 (None, None)
        """
        results: Dict[Path, Tuple[Optional[str], Optional[str]]] = {}
        
        if not paths:
            return results
        
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_path = {
                executor.submit(self._safe_compute, p): p 
                for p in paths
            }
            
            for future in as_completed(future_to_path):
                p = future_to_path[future]
                try:
                    results[p] = future.result()
                except Exception:
                    results[p] = (None, None)
        
        return results
    
    def _safe_compute(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        """安全计算 MD5，捕获异常"""
        try:
            return self.compute_md5(path)
        except Exception:
            return (None, None)

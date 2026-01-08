# -*- coding: utf-8 -*-
"""报告生成模块"""

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ReportData:
    """报告数据容器"""
    moved: List[dict] = field(default_factory=list)
    duplicate: List[dict] = field(default_factory=list)
    error: List[dict] = field(default_factory=list)
    orphan_aae: List[dict] = field(default_factory=list)
    dest_duplicate: List[dict] = field(default_factory=list)  # 建库时发现的重复


class ReportWriter:
    """报告写入器"""
    
    def __init__(self, report_dir: Path):
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)
    
    def write_summary(
        self,
        run_id: str,
        start_ts: int,
        end_ts: int,
        args: dict,
        data: ReportData,
        total_candidates: int
    ):
        """写入汇总 JSON"""
        summary = {
            "run_id": run_id,
            "started_at": start_ts,
            "finished_at": end_ts,
            "duration_sec": end_ts - start_ts,
            "args": args,
            "counts": {
                "candidate_masters": total_candidates,
                "moved": len(data.moved),
                "duplicate": len(data.duplicate),
                "error": len(data.error),
                "orphan_aae": len(data.orphan_aae),
                "dest_duplicate": len(data.dest_duplicate),
            }
        }
        
        path = self.report_dir / "summary.json"
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), 
            encoding="utf-8"
        )
    
    def write_moved_csv(self, rows: List[dict]):
        """写入归档明细 CSV"""
        header = [
            "src_path", "dest_path", "dest_aae_path", "dest_live_path",
            "capture_time", "year", "month", "md5", "method", "size"
        ]
        self._write_csv("moved.csv", header, rows)
    
    def write_duplicate_csv(self, rows: List[dict]):
        """写入重复文件明细 CSV"""
        header = [
            "src_path", "dup_path", "dup_aae_path", "dup_live_path",
            "capture_time", "md5", "method", "size"
        ]
        self._write_csv("duplicate.csv", header, rows)
    
    def write_error_csv(self, rows: List[dict]):
        """写入错误明细 CSV"""
        header = ["src_path", "error", "stage", "size", "mtime"]
        self._write_csv("error.csv", header, rows)
    
    def write_orphan_aae_csv(self, rows: List[dict]):
        """写入孤立 AAE 明细 CSV"""
        header = ["aae_src_path", "orphan_dest_path", "inferred_time", "reason"]
        self._write_csv("orphan_aae.csv", header, rows)
    
    def write_all(
        self,
        run_id: str,
        start_ts: int,
        end_ts: int,
        args: dict,
        data: ReportData,
        total_candidates: int
    ):
        """写入所有报告"""
        self.write_summary(run_id, start_ts, end_ts, args, data, total_candidates)
        self.write_moved_csv(data.moved)
        self.write_duplicate_csv(data.duplicate)
        self.write_error_csv(data.error)
        self.write_orphan_aae_csv(data.orphan_aae)
        self.write_dest_duplicate_csv(data.dest_duplicate)
    
    def write_dest_duplicate_csv(self, rows: List[dict]):
        """写入建库时发现的重复文件明细 CSV"""
        header = ["dup_path", "existing_path", "md5", "method", "size"]
        self._write_csv("dest_duplicate.csv", header, rows)
    
    def _write_csv(self, filename: str, header: List[str], rows: List[dict]):
        """写入 CSV 文件"""
        path = self.report_dir / filename
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

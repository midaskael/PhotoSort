# -*- coding: utf-8 -*-
"""照片整理核心逻辑模块"""

import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config
from .database import Database
from .exif import exiftool_batch_datetime
from .hasher import Hasher
from .media import MediaItem, MediaScanner
from .report import ReportData, ReportWriter
from .utils import (
    check_exiftool,
    make_unique_newname,
    now_run_id,
    print_progress,
    safe_move,
)


class PhotoOrganizer:
    """照片整理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.run_id = now_run_id()
        
        # 确保数据目录存在
        config.paths.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化组件
        self.db = Database(config.paths.db_path)
        self.hasher = Hasher(
            threshold_mb=config.performance.hash_threshold_mb,
            workers=config.performance.hash_workers,
        )
        self.scanner = MediaScanner(config)
        
        # 报告目录（使用统一数据目录）
        self.report_dir = config.paths.reports_dir / f"run-{self.run_id}"
        self.report_writer = ReportWriter(self.report_dir)
        self.report_data = ReportData()
        
        # dry-run 模式下的内存 hash 集合（避免同轮处理中的重复判断）
        self._dry_run_hashes: set = set()
    
    def run(self):
        """执行照片整理"""
        config = self.config
        paths = config.paths
        
        # 检查环境
        if not check_exiftool():
            print("[ERROR] 找不到 exiftool。请先运行：brew install exiftool", file=sys.stderr)
            sys.exit(2)
        
        # 检查 source 是否存在（include-dest 模式下可选）
        source_exists = paths.source.exists() and paths.source.is_dir()
        
        # 如果没有 source 且也没有 include-dest，则报错
        if not source_exists and not config.include_dest:
            print(f"[ERROR] 源目录不存在: {paths.source}", file=sys.stderr)
            sys.exit(1)
        
        # 创建必要目录
        paths.dest.mkdir(parents=True, exist_ok=True)
        paths.dup_dir.mkdir(parents=True, exist_ok=True)
        paths.orphan_aae_dir.mkdir(parents=True, exist_ok=True)
        
        start_ts = int(time.time())
        
        print(f"[INFO] 运行 ID: {self.run_id}")
        print(f"[INFO] 源目录: {paths.source}")
        print(f"[INFO] 目标目录: {paths.dest}")
        print(f"[INFO] Dry-run: {config.dry_run}")
        
        # 可选：将 dest 已有文件建库
        if config.include_dest:
            self._build_dest_index()
        
        # 如果 source 不存在，只做建库后退出
        if not source_exists:
            print(f"[INFO] 源目录不存在，仅完成 dest 建库。")
            end_ts = int(time.time())
            self._write_reports(start_ts, end_ts, 0)
            print(f"[INFO] 完成。报告目录: {self.report_dir}")
            self.db.close()
            return
        
        # 扫描源目录
        print("[INFO] 扫描 source 并进行文件绑定...")
        items, orphan_aaes, unrecognized = self.scanner.scan(paths.source)
        
        # 统计扫描结果
        total_items = len(items)
        live_photo_count = sum(1 for it in items if it.live_video)
        bound_aae_count = sum(1 for it in items if it.sidecar_aae)
        
        # 计算文件总数 = 主文件 + Live Video + 绑定AAE + 孤立AAE + 未识别
        total_files = total_items + live_photo_count + bound_aae_count + len(orphan_aaes) + len(unrecognized)
        
        # 过滤已处理文件
        candidates = self._filter_candidates(items)
        total = len(candidates)
        
        # 显示扫描统计
        print(f"[INFO] 文件总数: {total_files}")
        print(f"[INFO] 扫描统计: 主文件 {total_items}, Live Photo {live_photo_count}, AAE 绑定 {bound_aae_count}, AAE 孤立 {len(orphan_aaes)}, 未识别 {len(unrecognized)}")
        print(f"[INFO] 待处理主文件数: {total}")
        
        # 批量读取 EXIF 时间
        dt_map: Dict[Path, Optional[datetime]] = {}
        if total > 0:
            masters = [it.master for it in candidates]
            print(f"[INFO] 批量读取 EXIF 时间 (chunk={config.performance.exiftool_chunk_size})...")
            dt_map = exiftool_batch_datetime(masters, config.performance.exiftool_chunk_size)
        
        # 处理主文件
        self._process_candidates(candidates, dt_map, total)
        
        # 处理孤立 AAE
        if orphan_aaes:
            self._process_orphan_aaes(orphan_aaes)
        
        # 处理未识别文件（移动到二次确认目录）
        unrecognized_moved = 0
        if unrecognized:
            unrecognized_moved = self._process_unrecognized(unrecognized)
        
        # 输出处理统计
        moved_count = len(self.report_data.moved)
        dup_count = len(self.report_data.duplicate)
        error_count = len(self.report_data.error)
        orphan_count = len(self.report_data.orphan_aae)
        
        # 计算 Live Photo 和 AAE 跟随数量
        live_moved = sum(1 for m in self.report_data.moved if m.get("dest_live_path"))
        aae_moved = sum(1 for m in self.report_data.moved if m.get("dest_aae_path"))
        
        print()
        print(f"[INFO] === 处理统计 ===")
        print(f"[INFO] 文件总数:       {total_files}")
        print(f"[INFO] 待处理主文件:   {total}")
        print(f"[INFO] 已归档移动:     {moved_count}")
        if live_moved > 0:
            print(f"[INFO]   └ Live Photo: {live_moved}")
        if aae_moved > 0:
            print(f"[INFO]   └ AAE 跟随:   {aae_moved}")
        print(f"[INFO] 重复文件:       {dup_count}")
        if error_count > 0:
            print(f"[WARN] 处理错误:       {error_count}")
        if orphan_count > 0:
            print(f"[INFO] 孤立 AAE:       {orphan_count}")
        if unrecognized_moved > 0:
            print(f"[INFO] 未识别文件:     {unrecognized_moved} (已移至二次确认)")
        
        # 写入报告
        end_ts = int(time.time())
        self._write_reports(start_ts, end_ts, total)
        
        print(f"[INFO] 完成。报告目录: {self.report_dir}")
        
        # 关闭数据库
        self.db.close()
    
    def _build_dest_index(self):
        """将 dest 目录已有文件建库（使用并行 hash）"""
        paths = self.config.paths
        print(f"[INFO] 建库：扫描 dest = {paths.dest}")
        print(f"[INFO] 数据库路径: {paths.db_path}")
        print(f"[INFO] 并行线程数: {self.config.performance.hash_workers}")
        
        # 收集所有文件
        all_files = list(self.scanner.iter_files(paths.dest))
        
        # 过滤掉不需要处理的文件
        dest_files = []
        skipped_count = 0
        for p in all_files:
            try:
                if p == paths.db_path:
                    skipped_count += 1
                    continue
                if paths.dup_dir in p.parents:
                    skipped_count += 1
                    continue
                if paths.orphan_aae_dir in p.parents:
                    skipped_count += 1
                    continue
                if "_reports" in str(p) or ".photox" in str(p):
                    skipped_count += 1
                    continue
                dest_files.append(p)
            except Exception:
                dest_files.append(p)
        
        dest_total = len(dest_files)
        print(f"[INFO] 发现文件总数: {len(all_files)}")
        print(f"[INFO] 待处理文件: {dest_total}（跳过 {skipped_count} 个系统文件）")
        
        if dest_total == 0:
            print("[INFO] 无需建库")
            return
        indexed_count = 0
        dup_count = 0
        error_count = 0
        last_percent = -1
        
        # 分批并行处理
        batch_size = self.config.performance.exiftool_chunk_size
        total_batches = (dest_total + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, dest_total)
            batch = dest_files[start:end]
            
            # 显示进度条
            last_percent = print_progress(end, dest_total, last_percent, "[建库]")
            
            # 并行计算 hash
            hash_results = self.hasher.compute_batch(batch)
            
            # 处理结果
            for p in batch:
                result = hash_results.get(p)
                if result is None or result[0] is None:
                    error_count += 1
                    continue
                
                md5, method = result
                try:
                    size = p.stat().st_size
                    
                    # 检查是否已存在（重复文件）
                    existing_path = self.db.get_hash_path(md5, size, method)
                    if existing_path and existing_path != str(p):
                        # 只有当 existing_path 不是当前文件时才算重复
                        dup_count += 1
                        self.report_data.dest_duplicate.append({
                            "dup_path": str(p),
                            "existing_path": existing_path,
                            "md5": md5,
                            "method": method,
                            "size": size,
                        })
                    elif not existing_path:
                        # 新文件，入库
                        self.db.add_hash(md5, size, method, str(p))
                        indexed_count += 1
                    # else: existing_path == str(p)，说明已入库，跳过
                except Exception as e:
                    error_count += 1
        
        # 打印统计信息
        print(f"\n[INFO] === 建库统计 ===")
        print(f"[INFO] 扫描文件总数: {len(all_files)}")
        print(f"[INFO] 成功入库数量: {indexed_count}")
        print(f"[INFO] 发现重复文件: {dup_count}")
        print(f"[INFO] 跳过文件数量: {skipped_count}")
        if error_count > 0:
            print(f"[WARN] 失败文件数量: {error_count}")
        print(f"[INFO] 数据库位置: {paths.db_path}")
        if dup_count > 0:
            print(f"[INFO] 重复文件明细将保存到报告目录的 dest_duplicate.csv")
    
    def _filter_candidates(self, items: List[MediaItem]) -> List[MediaItem]:
        """过滤已处理的文件"""
        config = self.config
        paths = config.paths
        candidates = []
        
        for it in items:
            sp = str(it.master)
            
            # 跳过已处理（dry-run 模式下不跳过，每次都重新处理）
            if not config.dry_run and self.db.is_processed(sp):
                continue
            
            # 跳过目标目录内的文件（避免回环）
            try:
                if paths.dest in it.master.parents:
                    continue
                if paths.dup_dir in it.master.parents:
                    continue
                if paths.orphan_aae_dir in it.master.parents:
                    continue
            except Exception:
                pass
            
            candidates.append(it)
        
        return candidates
    
    def _process_candidates(
        self,
        candidates: List[MediaItem],
        dt_map: Dict[Path, Optional[datetime]],
        total: int
    ):
        """处理候选文件"""
        config = self.config
        paths = config.paths
        
        done = 0
        last_percent = -1
        
        try:
            for it in candidates:
                done += 1
                last_percent = print_progress(done, total, last_percent)
                
                self._process_single_item(it, dt_map)
                
        except KeyboardInterrupt:
            print("\n[INFO] 已中断。你可以用同样参数再次运行以继续。")
    
    def _process_single_item(
        self,
        it: MediaItem,
        dt_map: Dict[Path, Optional[datetime]]
    ):
        """处理单个媒体项"""
        config = self.config
        paths = config.paths
        p = it.master
        sp = str(p)
        
        try:
            st = p.stat()
            size = st.st_size
            mtime = int(st.st_mtime)
            
            # 获取拍摄时间
            dt = dt_map.get(p)
            if dt is None:
                dt = datetime.fromtimestamp(mtime)
            
            capture_time = int(dt.timestamp())
            year = f"{dt.year:04d}"
            month = f"{dt.month:02d}"
            yyyymmdd = f"{dt.year:04d}{dt.month:02d}{dt.day:02d}"
            target_dir = paths.dest / year / month
            
            # 计算 hash
            md5, method = self.hasher.compute_md5(p)
            
            # 检查是否重复（含二次确认）
            is_dup, final_md5, final_method = self._check_duplicate(p, md5, size, method)
            
            if is_dup:
                self._handle_duplicate(it, sp, size, mtime, capture_time, final_md5, final_method)
            else:
                self._handle_new_file(
                    it, sp, size, mtime, capture_time, final_md5, final_method,
                    target_dir, yyyymmdd, year, month
                )
                
        except Exception as e:
            self._handle_error(p, sp, str(e), "process_master")
    
    def _check_duplicate(
        self,
        p: Path,
        md5: str,
        size: int,
        method: str
    ) -> tuple:
        """
        检查是否重复（含二次确认）
        
        Returns:
            (is_duplicate, final_md5, final_method)
        """
        config = self.config
        
        # dry-run 模式下，也检查内存中的 hash（同轮处理）
        if config.dry_run and (md5, size, method) in self._dry_run_hashes:
            return True, md5, method
        
        if method == "full":
            # 全量 hash 无需二次确认
            is_dup = self.db.hash_exists(md5, size, method)
            return is_dup, md5, method
        
        # tail10m 方法：检查是否命中
        if not self.db.hash_exists(md5, size, method):
            return False, md5, method
        
        # tail10m 命中，是否进行二次确认？
        if not config.dedup.verify_tail_collision:
            return True, md5, method
        
        # 二次确认：计算全量 hash
        full_md5 = self.hasher.compute_full_md5(p)
        
        # 检查全量 hash 是否在库中
        if self.db.hash_exists(full_md5, size, "full"):
            return True, full_md5, "full"
        else:
            # tail10m 碰撞但 full hash 不同 → 非重复
            return False, full_md5, "full"
    
    def _handle_duplicate(
        self,
        it: MediaItem,
        sp: str,
        size: int,
        mtime: int,
        capture_time: int,
        md5: str,
        method: str
    ):
        """处理重复文件"""
        config = self.config
        paths = config.paths
        p = it.master
        
        dup_master = paths.dup_dir / p.name
        dup_aae = paths.dup_dir / it.sidecar_aae.name if it.sidecar_aae else None
        dup_live = paths.dup_dir / it.live_video.name if it.live_video else None
        
        if config.dry_run:
            # 预演模式：不输出每个文件，只记录
            final_master = dup_master
            final_aae = str(dup_aae) if dup_aae else ""
            final_live = str(dup_live) if dup_live else ""
        else:
            final_master = safe_move(p, dup_master)
            
            final_aae = ""
            if it.sidecar_aae and it.sidecar_aae.exists():
                final_aae = str(safe_move(it.sidecar_aae, dup_aae))
            
            final_live = ""
            if it.live_video and it.live_video.exists():
                final_live = str(safe_move(it.live_video, dup_live))
        
        # 更新数据库（仅正式运行时）
        if not config.dry_run:
            self.db.upsert_state(
                sp, size, mtime, capture_time, md5, method, "duplicate",
                str(final_master), final_aae or None, final_live or None,
                None, self.run_id
            )
        
        # 记录报告
        self.report_data.duplicate.append({
            "src_path": sp,
            "dup_path": str(final_master),
            "dup_aae_path": final_aae,
            "dup_live_path": final_live,
            "capture_time": capture_time,
            "md5": md5,
            "method": method,
            "size": size,
        })
    
    def _handle_new_file(
        self,
        it: MediaItem,
        sp: str,
        size: int,
        mtime: int,
        capture_time: int,
        md5: str,
        method: str,
        target_dir: Path,
        yyyymmdd: str,
        year: str,
        month: str
    ):
        """处理新文件（归档）"""
        config = self.config
        p = it.master
        
        # 生成新文件名
        new_filename = make_unique_newname(target_dir, yyyymmdd, p.suffix)
        new_path = target_dir / new_filename
        new_stem = Path(new_filename).stem
        
        # AAE 路径
        new_aae_path = target_dir / f"{new_stem}.aae" if it.sidecar_aae else None
        
        # Live Video 路径
        new_live_path = target_dir / f"{new_stem}.mov" if it.live_video else None
        
        if config.dry_run:
            # 预演模式：不写入数据库，用内存 Set 避免同轮误判
            self._dry_run_hashes.add((md5, size, method))
            
            final_master = new_path
            final_aae = str(new_aae_path) if new_aae_path else ""
            final_live = str(new_live_path) if new_live_path else ""
        else:
            final_master = safe_move(p, new_path)
            
            final_aae = ""
            if it.sidecar_aae and it.sidecar_aae.exists():
                final_aae = str(safe_move(it.sidecar_aae, new_aae_path))
            
            final_live = ""
            if it.live_video and it.live_video.exists():
                final_live = str(safe_move(it.live_video, new_live_path))
            
            # 入库
            self.db.add_hash(md5, size, method, str(final_master))
        
        # 更新数据库（仅正式运行时）
        if not config.dry_run:
            self.db.upsert_state(
                sp, size, mtime, capture_time, md5, method, "moved",
                str(final_master), final_aae or None, final_live or None,
                None, self.run_id
            )
        
        # 记录报告
        self.report_data.moved.append({
            "src_path": sp,
            "dest_path": str(final_master),
            "dest_aae_path": final_aae,
            "dest_live_path": final_live,
            "capture_time": capture_time,
            "year": year,
            "month": month,
            "md5": md5,
            "method": method,
            "size": size,
        })
    
    def _handle_error(self, p: Path, sp: str, error: str, stage: str):
        """处理错误"""
        print(f"[ERROR] 处理失败: {p} -> {error}")
        
        try:
            st = p.stat()
            size = st.st_size
            mtime = int(st.st_mtime)
        except Exception:
            size = 0
            mtime = 0
        
        try:
            self.db.upsert_state(
                sp, size, mtime, mtime, None, None, "error",
                None, None, None, error, self.run_id
            )
        except Exception:
            pass
        
        self.report_data.error.append({
            "src_path": sp,
            "error": error,
            "stage": stage,
            "size": str(size),
            "mtime": str(mtime),
        })
    
    def _process_orphan_aaes(self, orphan_aaes: List[Path]):
        """处理孤立 AAE"""
        config = self.config
        paths = config.paths
        
        print(f"[INFO] 处理 orphan AAE: {len(orphan_aaes)}")
        
        # 批量读取时间
        aae_dt_map = exiftool_batch_datetime(
            orphan_aaes, 
            config.performance.exiftool_chunk_size
        )
        
        for aae in orphan_aaes:
            try:
                if not aae.exists():
                    continue
                
                st = aae.stat()
                mtime = int(st.st_mtime)
                dt = aae_dt_map.get(aae) or datetime.fromtimestamp(mtime)
                
                year = f"{dt.year:04d}"
                month = f"{dt.month:02d}"
                bucket = paths.orphan_aae_dir / year / month
                target = bucket / aae.name
                
                if config.dry_run:
                    # 预演模式：不输出每个文件，只记录
                    final = target
                else:
                    final = safe_move(aae, target)
                
                self.report_data.orphan_aae.append({
                    "aae_src_path": str(aae),
                    "orphan_dest_path": str(final),
                    "inferred_time": int(dt.timestamp()),
                    "reason": "no_master_in_same_dir_same_stem",
                })
                
            except Exception as e:
                self.report_data.error.append({
                    "src_path": str(aae),
                    "error": str(e),
                    "stage": "move_orphan_aae",
                    "size": "",
                    "mtime": "",
                })
    
    def _process_unrecognized(self, unrecognized: List[Path]) -> int:
        """处理未识别文件（移动到二次确认目录）"""
        config = self.config
        paths = config.paths
        
        print(f"[INFO] 处理未识别文件: {len(unrecognized)}")
        
        moved_count = 0
        
        for p in unrecognized:
            try:
                if not p.exists():
                    continue
                
                target = paths.second_check_dir / p.name
                
                if config.dry_run:
                    # 预演模式：不实际移动
                    moved_count += 1
                else:
                    # 处理重名：加随机数
                    if target.exists():
                        import secrets
                        stem = target.stem
                        suffix = target.suffix
                        rnd = secrets.token_hex(3)
                        target = paths.second_check_dir / f"{stem}_{rnd}{suffix}"
                    
                    target.parent.mkdir(parents=True, exist_ok=True)
                    p.rename(target)
                    moved_count += 1
                    
            except Exception as e:
                self.report_data.error.append({
                    "src_path": str(p),
                    "error": str(e),
                    "stage": "move_unrecognized",
                    "size": "",
                    "mtime": "",
                })
        
        return moved_count
    
    def _write_reports(self, start_ts: int, end_ts: int, total: int):
        """写入报告"""
        config = self.config
        paths = config.paths
        
        args = {
            "source": str(paths.source),
            "dest": str(paths.dest),
            "dup": str(paths.dup_dir),
            "db": str(paths.db_path),
            "orphan_aae_dir": str(paths.orphan_aae_dir),
            "chunk_size": config.performance.exiftool_chunk_size,
            "hash_workers": config.performance.hash_workers,
            "exts": sorted(list(config.extensions)),
            "live_photo_enabled": config.live_photo.enabled,
            "verify_tail_collision": config.dedup.verify_tail_collision,
            "dry_run": config.dry_run,
            "include_dest": config.include_dest,
        }
        
        self.report_writer.write_all(
            self.run_id, start_ts, end_ts, args,
            self.report_data, total
        )
        
        # 更新运行历史
        self._update_run_history(start_ts, end_ts, total)
    
    def _update_run_history(self, start_ts: int, end_ts: int, total: int):
        """更新运行历史文件"""
        import json
        
        paths = self.config.paths
        history_file = paths.history_file
        
        # 读取现有历史
        history = []
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
        
        # 添加本次运行记录
        run_record = {
            "run_id": self.run_id,
            "started_at": start_ts,
            "finished_at": end_ts,
            "duration_sec": end_ts - start_ts,
            "dry_run": self.config.dry_run,
            "include_dest": self.config.include_dest,
            "counts": {
                "candidate_masters": total,
                "moved": len(self.report_data.moved),
                "duplicate": len(self.report_data.duplicate),
                "dest_duplicate": len(self.report_data.dest_duplicate),
                "error": len(self.report_data.error),
                "orphan_aae": len(self.report_data.orphan_aae),
            },
            "report_dir": str(self.report_dir),
        }
        
        history.append(run_record)
        
        # 写入历史文件
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] 更新运行历史失败: {e}")

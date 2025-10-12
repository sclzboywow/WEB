#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone shard mover for /共享图集

- Moves files directly under root into shard subdirectories: batch_001, batch_002, ...
- Each shard holds at most 1000 files
- Total under root limited to 100000
"""

import os
import sys
import json
import argparse
import asyncio
from typing import Dict, Any, List, Tuple


# Ensure repo root on sys.path
CURR_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURR_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.db import get_db_connection, init_sync_db  # type: ignore
from api.netdisk import ensure_directory, move_files  # type: ignore


def path_key(path: str) -> str:
    return path if path and path.startswith('/') else f"/{path or ''}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Rebalance /共享图集 into shard subdirectories')
    p.add_argument('--root', default=os.getenv('SHARED_GALLERY_ROOT', '/共享图集'), help='Root directory to rebalance')
    p.add_argument('--bucket-size', type=int, default=int(os.getenv('SHARED_GALLERY_BUCKET_SIZE', '1000')), help='Max files per shard')
    p.add_argument('--max-files', type=int, default=int(os.getenv('SHARED_GALLERY_MAX_FILES', '100000')), help='Max total files under root')
    p.add_argument('--prefix', default=os.getenv('SHARED_GALLERY_SHARD_PREFIX', 'batch_'), help='Shard name prefix')
    p.add_argument('--submit-batch', type=int, default=50, help='Move operations per submit')
    p.add_argument('--limit', type=int, default=0, help='Max files to move this run (0 for unlimited)')
    p.add_argument('--dry-run', action='store_true', help='Do not perform moves, only print plan')
    return p.parse_args()


def list_direct_files_under_root(root: str) -> List[Tuple[int, str, str]]:
    """Return list of (rowid, file_path, file_name) for files directly under root.
    We fetch candidates via LIKE and filter in Python for exact direct children.
    """
    root = path_key(root)
    prefix = root + '/'
    rows_out: List[Tuple[int, str, str]] = []
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, file_path, file_name FROM file_records WHERE isdir=0 AND file_path LIKE ?", (f"{prefix}%",))
        for rid, fp, fn in cur.fetchall():
            if not fp or not fp.startswith(prefix):
                continue
            rest = fp[len(prefix):]
            if '/' in rest:
                continue
            rows_out.append((int(rid), fp, fn or os.path.basename(fp)))
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return rows_out


def list_files_from_oversized_shards(root: str, bucket_size: int, prefix: str) -> List[Tuple[int, str, str]]:
    """Return list of (rowid, file_path, file_name) for files from shards that exceed bucket_size."""
    root = path_key(root)
    prefix_path = root + '/'
    rows_out: List[Tuple[int, str, str]] = []
    
    conn = get_db_connection(); cur = conn.cursor()
    try:
        # Find shards that exceed bucket_size
        cur.execute("""
            SELECT 
                CASE 
                    WHEN file_path LIKE ? AND file_path NOT LIKE ? THEN 
                        SUBSTR(file_path, 1, LENGTH(?) + INSTR(SUBSTR(file_path, LENGTH(?) + 1), '/') - 1)
                    WHEN file_path LIKE ? THEN 
                        SUBSTR(file_path, 1, LENGTH(?) + INSTR(SUBSTR(file_path, LENGTH(?) + 1), '/') - 1)
                    ELSE file_path
                END as parent_dir,
                COUNT(*) as file_count
            FROM file_records 
            WHERE file_path LIKE ? AND isdir = 0
            GROUP BY parent_dir
            HAVING COUNT(*) > ?
        """, (f"{prefix_path}%", f"{prefix_path}%/%", prefix_path, prefix_path, f"{prefix_path}%/%", prefix_path, prefix_path, f"{prefix_path}%", bucket_size))
        
        oversized_shards = cur.fetchall()
        if not oversized_shards:
            return rows_out
            
        # Get files from oversized shards, taking excess files
        for shard_path, file_count in oversized_shards:
            excess = file_count - bucket_size
            cur.execute("""
                SELECT id, file_path, file_name 
                FROM file_records 
                WHERE file_path LIKE ? AND isdir = 0
                ORDER BY id
                LIMIT ?
            """, (f"{shard_path}/%", excess))
            
            for rid, fp, fn in cur.fetchall():
                rows_out.append((int(rid), fp, fn or os.path.basename(fp)))
                
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return rows_out


def count_and_shards(root: str, prefix: str) -> Tuple[int, Dict[str, int]]:
    """Return (total_files_under_root, shard_counts_by_name)."""
    root = path_key(root)
    pfx = root + '/'
    total = 0
    shard_counts: Dict[str, int] = {}
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT file_path FROM file_records WHERE isdir=0 AND file_path LIKE ?", (f"{pfx}%",))
        for (fp,) in cur.fetchall():
            total += 1
            try:
                rel = fp[len(pfx):]
                first = rel.split('/', 1)[0]
                if first and first.startswith(prefix):
                    shard_counts[first] = shard_counts.get(first, 0) + 1
            except Exception:
                continue
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return total, shard_counts


def next_shard_name(shard_counts: Dict[str, int], bucket: int, prefix: str, max_files: int) -> str:
    max_shards = max(1, max_files // bucket)
    def fmt(i: int) -> str:
        return f"{prefix}{i:03d}"
    
    # 优先选择文件数最少的现有分片目录（但必须小于bucket）
    available_shards = []
    for i in range(1, max_shards + 1):
        name = fmt(i)
        count = shard_counts.get(name, 0)
        if count < bucket:
            available_shards.append((count, name))
    
    if available_shards:
        # 选择文件数最少的目录
        available_shards.sort()
        return available_shards[0][1]
    
    # 如果没有可用分片，创建新的
    existing = len([k for k in shard_counts.keys() if k.startswith(prefix)])
    if existing >= max_shards:
        return ''
    return fmt(existing + 1)


async def ensure_dir(path: str) -> None:
    try:
        await ensure_directory(path)
    except Exception:
        # Ignore ensure errors (exist / transient)
        pass


async def perform_moves(root: str, bucket: int, max_files: int, prefix: str, submit_batch: int, limit: int, dry_run: bool) -> Dict[str, Any]:
    root = path_key(root)
    direct = list_direct_files_under_root(root)
    oversized = list_files_from_oversized_shards(root, bucket, prefix)
    total, shards = count_and_shards(root, prefix)
    result = {
        'root': root,
        'direct_candidates': len(direct),
        'oversized_candidates': len(oversized),
        'total_under_root': total,
        'shards': dict(shards),
        'moved': 0,
        'planned': 0,
        'dry_run': dry_run,
    }
    if total >= max_files:
        print(f"limit-hit total={total} max={max_files}")
        return result
    
    # Combine both direct files and oversized shard files
    all_candidates = direct + oversized
    if not all_candidates:
        print("no files to move; nothing to do")
        return result

    # prepare ops
    to_plan: List[Tuple[str, str, str]] = []  # (src, dest_dir, final_name)
    for _, src, name in all_candidates:
        # normalize filename (avoid accidental subdir creation if name contains '/')
        safe_name = os.path.basename(name).replace('/', '_')
        shard = next_shard_name(shards, bucket, prefix, max_files)
        if not shard:
            print("no available shard slot; stop planning")
            break
        target_dir = f"{root}/{shard}"
        to_plan.append((src, target_dir, safe_name))
        # account occupancy in memory
        shards[shard] = shards.get(shard, 0) + 1
        total += 1
        if limit and len(to_plan) >= limit:
            break
        if total >= max_files:
            print("reached max-files while planning; stop")
            break

    result['planned'] = len(to_plan)
    if dry_run or not to_plan:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    # ensure target shard directories exist
    shard_dirs = sorted({dest_dir for _, dest_dir, _ in to_plan})
    await asyncio.gather(*(ensure_dir(d) for d in shard_dirs))

    # submit moves in batches
    moved = 0
    i = 0
    while i < len(to_plan):
        batch = to_plan[i:i+submit_batch]
        # IMPORTANT: pass destination as directory, letting API keep filename
        ops = [{'path': src, 'dest': dest_dir} for src, dest_dir, _ in batch]
        # basic retry with rate-limit backoff
        attempts = 0
        while True:
            try:
                await move_files(ops, ondup='fail')
                break
            except Exception as e:
                msg = str(e)
                print(f"shard-move submit failed size={len(batch)} err={msg}")
                attempts += 1
                if '429' in msg or '频率' in msg or 'rate' in msg:
                    # sleep ~45s then retry
                    try:
                        await asyncio.sleep(45)
                    except Exception:
                        pass
                    if attempts <= 3:
                        continue
                # give up this batch after 3 attempts
                if attempts >= 3:
                    # skip this batch and move on
                    i += len(batch)
                    break
        else:
            # should not reach here
            i += len(batch)
            continue

        # successful submission
        moved += len(batch)
        # update DB
        conn = get_db_connection(); cur = conn.cursor()
        try:
            for src, dest_dir, fname in batch:
                dst = f"{dest_dir}/{fname}"
                cur.execute(
                    "UPDATE file_records SET file_path=?, file_name=? WHERE file_path=? AND isdir=0",
                    (dst, fname, src)
                )
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        print(f"shard-move submit ok moved={moved}/{len(to_plan)} last_batch={len(batch)}")
        i += len(batch)

    result['moved'] = moved
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    args = parse_args()
    init_sync_db()
    
    total_moved = 0
    batch_count = 0
    
    while True:
        batch_count += 1
        print(f"\n=== 开始第 {batch_count} 批处理 ===")
        
        res = asyncio.run(perform_moves(
            root=args.root,
            bucket=args.bucket_size,
            max_files=args.max_files,
            prefix=args.prefix,
            submit_batch=args.submit_batch,
            limit=args.limit,
            dry_run=args.dry_run,
        ))
        
        moved_this_batch = res.get('moved', 0)
        total_moved += moved_this_batch
        
        print(f"第 {batch_count} 批处理完成，本批移动了 {moved_this_batch} 个文件")
        print(f"累计移动了 {total_moved} 个文件")
        
        # 如果本批没有移动任何文件，说明没有更多工作需要做
        if moved_this_batch == 0:
            print("✅ 所有文件处理完成！")
            break
            
        # 如果达到了限制，也停止
        if args.limit > 0 and total_moved >= args.limit:
            print(f"✅ 达到处理限制 {args.limit}，停止处理")
            break
            
        print(f"继续处理下一批...")
    
    print(f"\n🎉 分片任务全部完成！总共处理了 {total_moved} 个文件")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())



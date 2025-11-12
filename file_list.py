#!/usr/bin/env python3
"""
recurse_to_csv.py
폴더를 재귀 탐색하여 모든 파일 정보를 CSV로 저장하는 스크립트
사용법:
    python file_list.py /path/to/search output.csv
"""

import os
import sys
import csv
import argparse
from pathlib import Path
from datetime import datetime

def file_info_rows(root_dir: Path, include_hidden=False):
    """
    root_dir 내부를 재귀 순회하여 각 파일의 정보(딕셔너리)를 yield 함.
    include_hidden: 숨김 파일/폴더를 포함할지 여부
    """
    root_dir = root_dir.resolve()
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 숨김 폴더/파일 걸러내기 (원하면 주석 처리 가능)
        if not include_hidden:
            # dirnames를 제자리 수정하면 하위 탐색에서 숨김 폴더를 건너뜀
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            filenames = [f for f in filenames if not f.startswith('.')]

        for fname in filenames:
            full_path = Path(dirpath) / fname
            try:
                st = full_path.stat()
            except (PermissionError, FileNotFoundError):
                # 접근 불가 파일은 건너뜀
                continue

            yield {
                "full_path": str(full_path),
                "name": fname,
                "parent_dir": str(Path(dirpath)),
                "ext": full_path.suffix.lower(),
                "size_bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(sep=' '),
                "ctime": datetime.fromtimestamp(st.st_ctime).isoformat(sep=' ')
            }

def write_csv(rows, out_path: Path):
    fieldnames = ["full_path", "parent_dir", "name", "ext", "size_bytes", "mtime", "ctime"]
    out_path = out_path.resolve()
    # ensure parent exists
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def main():
    parser = argparse.ArgumentParser(description="디렉토리 하위까지 뒤져 파일 목록을 CSV로 저장")
    parser.add_argument("root", help="탐색할 루트 폴더 경로")
    parser.add_argument("out", help="출력 CSV 파일 경로")
    parser.add_argument("--hidden", action="store_true", help="숨김 파일/폴더 포함")
    args = parser.parse_args()

    root = Path(args.root)
    out = Path(args.out)

    if not root.exists() or not root.is_dir():
        print(f"오류: {root} 가 존재하지 않거나 폴더가 아닙니다.", file=sys.stderr)
        sys.exit(1)

    print(f"탐색 시작: {root}")
    rows_generator = file_info_rows(root, include_hidden=args.hidden)
    write_csv(rows_generator, out)
    print(f"완료: {out}")

if __name__ == "__main__":
    main()

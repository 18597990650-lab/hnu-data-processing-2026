"""
递归扫描 公司年报 目录下所有子文件夹中的 PDF 文件，转换为 TXT 文本文件。
输出到 公司年报_txt 目录，按公司（子文件夹）分类保持目录结构。
使用多进程并行转换，自动跳过已存在的 TXT。
"""

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import fitz  # PyMuPDF


def _convert_one(args):
    """单个 PDF → TXT 转换（独立函数，供子进程调用）。返回 (ok, pages_or_error)。"""
    pdf_path_str, txt_path_str = args
    pdf_path = Path(pdf_path_str)
    txt_path = Path(txt_path_str)

    # 已存在则跳过
    if txt_path.exists():
        return (True, "已跳过")

    try:
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)
        lines = []
        for page_num in range(page_count):
            text = doc[page_num].get_text()
            if text.strip():
                lines.append(text)
        doc.close()

        txt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(lines))

        return (True, f"{page_count}页")
    except Exception as e:
        return (False, str(e))


def main():
    base_dir = Path(__file__).resolve().parent.parent
    pdf_dir = base_dir / "公司年报"
    out_dir = base_dir / "公司年报_txt"

    if not pdf_dir.exists():
        print(f"[错误] 目录不存在: {pdf_dir}")
        sys.exit(1)

    pdf_files = sorted(pdf_dir.rglob("*.pdf"))
    if not pdf_files:
        print(f"[提示] {pdf_dir} 下（含子文件夹）未找到任何 PDF 文件，请放入 PDF 后重新运行。")
        sys.exit(0)

    total = len(pdf_files)

    # 构建任务列表：只处理尚未转换的
    tasks = []
    skip_count = 0
    for pdf_path in pdf_files:
        relative = pdf_path.relative_to(pdf_dir)
        txt_path = out_dir / relative.with_suffix(".txt")
        if txt_path.exists():
            skip_count += 1
        tasks.append((str(pdf_path), str(txt_path)))

    workers = min(os.cpu_count() or 4, 16)  # 限制最大16进程，避免IO竞争
    pending = len(tasks)
    print(f"共发现 {total} 个 PDF 文件，{skip_count} 个已有 TXT（跳过），待处理 {pending} 个")
    print(f"使用 {workers} 个进程并行转换...\n")
    sys.stdout.flush()

    start_time = time.time()
    total_pages = 0
    success = 0
    fail = 0
    last_report = start_time

    with ProcessPoolExecutor(max_workers=workers) as executor:
        # chunksize 减少 IPC 开销
        chunksize = max(1, pending // (workers * 50))
        results = executor.map(_convert_one, tasks, chunksize=chunksize)

        for idx, (ok, detail) in enumerate(results, start=1):
            # 从 tasks 中取出对应的 relative 路径
            pdf_path_str = tasks[idx - 1][0]
            relative = Path(pdf_path_str).relative_to(pdf_dir)

            if ok:
                if detail == "已跳过":
                    skip_count += 1
                    # 跳过的静默处理，只定期报告
                else:
                    success += 1
                    try:
                        total_pages += int(detail.replace("页", ""))
                    except ValueError:
                        pass
                    print(f"[{idx}/{pending}] {relative}  OK ({detail})", flush=True)
            else:
                fail += 1
                print(f"[{idx}/{pending}] {relative}  FAIL {detail}", flush=True)

            # 每 5% 或每 30 秒报告进度
            now = time.time()
            if idx % max(1, pending // 20) == 0 or now - last_report > 30:
                elapsed = now - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                eta = (pending - idx) / rate if rate > 0 else 0
                msg = (f">>> 进度: {idx}/{pending} ({100*idx//pending}%)  "
                       f"成功:{success} 跳过:{skip_count} 失败:{fail}  "
                       f"速度:{rate:.1f}/s ETA:{eta:.0f}s")
                print(msg, flush=True)
                # 同步写入进度文件，方便外部查看
                (base_dir / "代码" / "progress.txt").write_text(msg, encoding="utf-8")
                last_report = now

    elapsed = time.time() - start_time
    summary = (f"\n{'='*50}\n"
               f"完成! 成功: {success}  跳过: {skip_count}  失败: {fail}  "
               f"总页数: {total_pages}  耗时: {elapsed:.1f}s\n"
               f"输出目录: {out_dir}")
    print(summary)
    (base_dir / "代码" / "progress.txt").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()

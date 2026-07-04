import json
import os
import re
import time
import requests
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

BASE_DIR = Path(r"c:\Users\Administrator\Desktop\数据库作业")
EXCEL_PATH = BASE_DIR / "A股上市公司名单.xlsx"
OUTPUT_DIR = BASE_DIR / "公司年报"
STOCK_JSON_PATH = BASE_DIR / "szse_stock.network-response"
PROGRESS_FILE = BASE_DIR / "download_progress.txt"
API_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE_URL = "https://static.cninfo.com.cn/"
MAX_WORKERS = 12         # 并发线程数
REQUEST_DELAY = 0.3      # API请求间隔（秒）
PDF_DELAY = 0.2          # PDF下载间隔（秒）
RETRY_TIMES = 3
YEARS_BACK = 10
CATEGORY_NDBG = "category_ndbg_szsh"


def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    return session


def load_stock_mapping():
    with open(STOCK_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["code"]: item for item in data.get("stockList", [])}


def get_column(code):
    if code.startswith(("00", "20", "30")):
        return "szse"
    elif code.startswith(("60", "68")):
        return "sse"
    elif code.startswith(("8", "9", "4")):
        return "bj"
    return "szse"


def clean_filename(name):
    """去除HTML标签和非法文件名字符"""
    name = re.sub(r"<[^>]+>", "", name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name.strip()


def fetch_announcements(session, code, org_id, page_num=1, page_size=50):
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = f"{datetime.now().year - YEARS_BACK}-01-01"
    params = {
        "pageNum": page_num, "pageSize": page_size,
        "column": get_column(code), "tabName": "fulltext", "plate": "",
        "stock": f"{code},{org_id}", "searchkey": "", "secid": "",
        "category": CATEGORY_NDBG, "trade": "",
        "seDate": f"{start_date}~{end_date}",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    for attempt in range(RETRY_TIMES):
        try:
            resp = session.post(API_URL, data=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = (attempt + 1) * 10
                time.sleep(wait)
            else:
                time.sleep(3)
        except Exception:
            time.sleep(3)
    return None


def download_pdf(session, url, save_path):
    if save_path.exists():
        return "skipped"
    for attempt in range(RETRY_TIMES):
        try:
            resp = session.get(url, timeout=60, stream=True)
            if resp.status_code == 200:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                content = resp.content
                with open(save_path, "wb") as f:
                    f.write(content)
                return "ok"
            elif resp.status_code == 404:
                return "missing"
            time.sleep(2)
        except Exception:
            time.sleep(3)
    return "failed"


def process_company(session, company_name, stock_code, stock_mapping, output_dir):
    code = str(stock_code).strip().zfill(6)
    stock_info = stock_mapping.get(code)
    if not stock_info:
        return f"[FAIL] {company_name}({code}): 未找到orgId"

    org_id = stock_info["orgId"]
    company_dir = output_dir / clean_filename(f"{company_name}_{code}")
    company_dir.mkdir(parents=True, exist_ok=True)

    # 查询API
    data = fetch_announcements(session, code, org_id, page_num=1, page_size=50)
    if not data:
        return f"[FAIL] {company_name}({code}): API查询失败"

    total = data.get("totalAnnouncement", 0) or 0
    announcements = data.get("announcements") or []

    if total == 0:
        return f"[EMPTY] {company_name}({code}): 近{YEARS_BACK}年无年报"

    # 分页
    while len(announcements) < total:
        page_num = len(announcements) // 50 + 1
        time.sleep(REQUEST_DELAY)
        page_data = fetch_announcements(session, code, org_id, page_num=page_num, page_size=50)
        if page_data and page_data.get("announcements"):
            announcements.extend(page_data["announcements"])
        else:
            break

    # 下载PDF
    downloaded, skipped, failed = 0, 0, 0
    for ann in announcements:
        pdf_url = ann.get("adjunctUrl", "")
        if not pdf_url:
            continue

        title = clean_filename(ann.get("announcementTitle", "unknown"))
        # 跳过含"摘要"的公告（仅保留完整年报）
        if "摘要" in title:
            continue
        # 跳过2015年、2016年年报
        if "2015年" in title:
            continue
        if "2016年" in title:
            continue
        ann_time = ann.get("announcementTime", 0)
        date_str = datetime.fromtimestamp(ann_time / 1000).strftime("%Y%m%d") if ann_time else "unknown"

        full_url = PDF_BASE_URL + pdf_url
        save_path = company_dir / f"{date_str}_{title}.pdf"

        time.sleep(PDF_DELAY)
        result = download_pdf(session, full_url, save_path)
        if result == "ok":
            downloaded += 1
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    return f"[OK] {company_name}({code}): 总{total}篇, 下载{downloaded}, 跳过{skipped}, 失败{failed}"


def save_progress(index):
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(index))


def load_progress():
    if PROGRESS_FILE.exists():
        return int(PROGRESS_FILE.read_text().strip())
    return 0


def main():
    print("=" * 60)
    print("A股上市公司年报爬虫 (支持断点续爬)")
    print("=" * 60)

    # 1. 加载映射
    print("\n[1/4] 加载股票映射...")
    stock_mapping = load_stock_mapping()
    print(f"已加载 {len(stock_mapping)} 条映射")

    # 2. 读取Excel
    print("\n[2/4] 读取公司名单...")
    df = pd.read_excel(EXCEL_PATH)
    companies = list(zip(df["公司名称"], df["股票代码"]))
    total_count = len(companies)
    print(f"共 {total_count} 家公司")

    # 3. 加载进度
    start_idx = load_progress()
    if start_idx > 0:
        print(f"\n从第 {start_idx + 1} 家公司继续 (已处理 {start_idx} 家)")
    companies = companies[start_idx:]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = get_session()

    # 4. 开始爬取
    print(f"\n[4/4] 开始爬取 ({MAX_WORKERS}线程, {len(companies)}家待处理)...\n")
    print(f"预计耗时较长，可随时 Ctrl+C 中断，下次运行自动续爬\n")
    print("-" * 60)

    # 预扫描：跳过已有PDF的公司
    pending = []
    skip_count = 0
    for name, code in companies:
        company_dir = OUTPUT_DIR / clean_filename(f"{name}_{str(code).strip().zfill(6)}")
        if company_dir.exists() and any(company_dir.iterdir()):
            skip_count += 1
        else:
            pending.append((name, code))
    
    print(f"  {skip_count} 家已有文件跳过，{len(pending)} 家待处理")

    if len(pending) == 0:
        print("\n所有公司已处理完毕！")
        return

    success_count = empty_count = fail_count = 0

    # 全部提交到线程池
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for i, (name, code) in enumerate(pending):
            future = executor.submit(process_company, session, name, code, stock_mapping, OUTPUT_DIR)
            futures[future] = (i, name, code)

        for future in as_completed(futures):
            i, name, code = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = f"[FAIL] {name}({code}): 异常 - {e}"

            overall_idx = i + 1
            print(f"[{overall_idx}/{len(pending)}] {result}")

            if result.startswith("[OK]"):
                success_count += 1
            elif result.startswith("[EMPTY]"):
                empty_count += 1
            else:
                fail_count += 1

            save_progress(start_idx + skip_count + overall_idx)

    # 5. 统计
    print("\n" + "=" * 60)
    print(f"完成!")
    print(f"  成功下载: {success_count}")
    print(f"  已有文件跳过: {skip_count}")
    print(f"  无年报: {empty_count}")
    print(f"  失败: {fail_count}")
    print(f"  年报路径: {OUTPUT_DIR}")
    
    # 清理进度文件
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
    print("=" * 60)


if __name__ == "__main__":
    main()

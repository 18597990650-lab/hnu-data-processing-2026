"""
年报AI战略信息批量提取 — 高性能版
用法: python batch_extract.py
特性: 多线程并发 | 断点续跑 | 进度监控 | 多Provider多Key池 | 自动重试
"""

import os, re, json, csv, time, threading, traceback, sys, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = r"C:\Users\Administrator\Desktop\数据库作业\公司年报_txt"
OUTPUT_CSV = r"C:\Users\Administrator\Desktop\数据库作业\年报AI提取结果.csv"
PROGRESS_FILE = r"C:\Users\Administrator\Desktop\数据库作业\extract_progress.json"
LOG_FILE = r"C:\Users\Administrator\Desktop\数据库作业\extract_errors.log"

# ====== 多Provider多Key池（每个Key携带自己的URL和模型）====== #
# 格式: (api_url, model_name, api_key)
API_ENDPOINTS = [
    # SiliconFlow x3
    ("https://api.siliconflow.cn/v1/chat/completions", "Qwen/Qwen3.5-35B-A3B",
     "sk-kansfqppqoumgmsweogtxmkxbfehluaqmzacxvtbnkzdrqfw"),
    ("https://api.siliconflow.cn/v1/chat/completions", "Qwen/Qwen3.5-35B-A3B",
     "sk-ebsxegrzdpjgismfutjzstfaociyvxqvcyvtirhooeqgawjc"),
    ("https://api.siliconflow.cn/v1/chat/completions", "Qwen/Qwen3.5-35B-A3B",
     "sk-tpeopktxdytryuxhuffxisgzlixrwpsbnfayvestasrlecsw"),
]

# ====== 并发与重试配置 ====== #
MAX_WORKERS = 50
RETRY_TIMES = 3
TIMEOUT = 90
RATE_LIMIT_SLEEP = 0.2
MAX_TEXT_CHARS = 20000

# ====== AI关键词词典 ====== #
# 来源1: 姚加权(2024),《管理世界》 — "人工种子词+机器学习扩展+人工筛选"73词
AI_DICT_YAO_2024 = [
    "人工智能", "机器学习", "深度学习", "神经网络", "深度神经网络",
    "卷积神经网络", "循环神经网络", "长短期记忆", "LSTM",
    "自然语言处理", "计算机视觉", "图像识别", "语音识别",
    "声纹识别", "人脸识别", "生物识别", "特征识别", "特征提取",
    "模式识别", "知识图谱", "知识表示", "问答系统",
    "强化学习", "支持向量机", "SVM",
    "机器翻译", "语音合成", "语音交互",
    "人机交互", "人机对话", "人机协同",
    "数据挖掘", "大数据分析", "大数据处理", "大数据管理",
    "大数据平台", "大数据运营", "大数据营销", "大数据风控",
    "云计算", "边缘计算", "分布式计算", "智能计算",
    "智能芯片", "AI芯片", "智能传感器",
    "物联网", "可穿戴产品", "虚拟现实", "增强现实",
    "自动驾驶", "无人驾驶", "智能驾驶",
    "智能家居", "智能音箱", "智能客服",
    "智能医疗", "智能教育", "智能养老",
    "智能农业", "智能零售", "智能政务",
    "智能监管", "智能投顾", "智能保险",
    "智能环保", "智能运输", "智能搜索",
    "AI产品", "商业智能", "增强智能",
    "智慧银行", "智慧金融",
    "机器人流程自动化", "RPA",
]

# 来源2: 补充2024年后新兴AI术语（大模型、AIGC等）
AI_DICT_2024PLUS = [
    "大模型", "大语言模型", "LLM",
    "AIGC", "生成式人工智能", "生成式AI",
    "智能体", "AI Agent",
    "数字孪生", "智能制造", "智慧制造",
    "智能工厂", "智慧工厂",
    "工业互联网", "工业智能",
    "具身智能", "多模态", "扩散模型",
    "预训练", "微调", "提示工程",
    "检索增强生成", "RAG",
    "智能运维", "AI运维",
    "智能座舱", "车路协同",
    "具身机器人", "人形机器人",
]

AI_KEYWORDS = AI_DICT_YAO_2024 + AI_DICT_2024PLUS

# ====== API端点池（轮转调度）====== #
class EndpointPool:
    def __init__(self, endpoints):
        self.endpoints = endpoints
        self.lock = threading.Lock()
        self.idx = 0
    def get(self):
        with self.lock:
            ep = self.endpoints[self.idx % len(self.endpoints)]
            self.idx += 1
            return ep

ep_pool = EndpointPool(API_ENDPOINTS)
stats_lock = threading.Lock()
stats = {"done": 0, "fail": 0, "skip": 0, "total": 0}

# ====== 核心函数 ====== #
def filter_ai_paragraphs(full_text):
    paragraphs = [p.strip() for p in full_text.split("\n") if len(p.strip()) > 20]
    ai_paras = []
    for p in paragraphs:
        for kw in AI_KEYWORDS:
            if kw in ["AI", "RPA", "LLM", "RAG", "SVM", "LSTM", "AIGC"]:
                if re.search(r'\b' + re.escape(kw) + r'\b', p, re.IGNORECASE):
                    ai_paras.append(p)
                    break
            elif re.search(re.escape(kw), p, re.IGNORECASE):
                ai_paras.append(p)
                break
    return ai_paras

def call_api(text):
    prompt = f"""你是一位专业财经分析师。请从以下上市公司年度报告的AI相关段落中提取结构化信息，严格按JSON格式输出。

输出格式：
{{
  "ai_mention_count": 整数,
  "ai_strategy": "一句话概括AI战略定位，如'核心战略'/'重点方向'/'初步探索'/'未提及'",
  "ai_investment": "AI研发投入描述，如金额或占比，未提及填null",
  "ai_products": "AI相关产品/服务名称列表，逗号分隔，未提及填null",
  "has_ai_section": true/false,
  "ai_cooperation": "AI产学研合作信息，未提及填null",
  "ai_team": "AI研发团队规模描述，未提及填null",
  "ai_scenarios": "AI在主营业务中的应用场景，未提及填null",
  "ai_overall_level": "评级：'高'/'中'/'低'/'无'"
}}

报告AI相关段落：
{text}

只输出JSON，不要任何其他文字。"""

    for attempt in range(RETRY_TIMES):
        url, model, api_key = ep_pool.get()
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.1, "max_tokens": 2048,
                   "response_format": {"type": "json_object"}}
        try:
            time.sleep(RATE_LIMIT_SLEEP)
            resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 429:
                wait = min((attempt + 1) * 30, 120)
                print(f"  [429限流] {model[:12]} 等待{wait}s重试...")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                if attempt < RETRY_TIMES - 1:
                    time.sleep(2)
                    continue
                return {"error": f"HTTP {resp.status_code}: {resp.text[:150]}"}
            content = resp.json()["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                m = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
                if m:
                    return json.loads(m.group(1))
                return {"raw": content, "error": "JSON parse"}
        except Exception as e:
            if attempt < RETRY_TIMES - 1:
                time.sleep(2)
                continue
            return {"error": str(e)}
    return {"error": "max retries exceeded"}

def process_one_file(dir_name, dir_path, txt_file):
    company_code = dir_name.rsplit("_", 1)
    company_short = company_code[0]
    stock_code = company_code[1] if len(company_code) > 1 else ""
    m = re.search(r'(\d{4})年年度', txt_file)
    year = m.group(1) if m else txt_file[:4]

    file_path = os.path.join(dir_path, txt_file)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            full_text = f.read()
    except Exception:
        return {"company_short": company_short, "stock_code": stock_code,
                "year": year, "file": txt_file, "error": "read failed"}

    ai_paras = filter_ai_paragraphs(full_text)
    if not ai_paras:
        return {"company_short": company_short, "stock_code": stock_code,
                "year": year, "ai_mention_count": 0, "has_ai_section": False,
                "ai_overall_level": "无", "ai_signal": "无AI关键词", "ai_para_count": 0}

    combined = "\n\n".join(ai_paras)
    if len(combined) > MAX_TEXT_CHARS:
        combined = combined[:MAX_TEXT_CHARS]

    result = call_api(combined)
    result["company_short"] = company_short
    result["stock_code"] = stock_code
    result["year"] = year
    result["ai_para_count"] = len(ai_paras)
    return result

# ====== 进度管理 ====== #
def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_progress(done_set):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(list(done_set), f)

# ====== 主流程 ====== #
def main():
    done = load_progress()
    tasks = []
    all_dirs = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    print(f"共 {len(all_dirs)} 个公司目录")
    print(f"AI关键词: {len(AI_KEYWORDS)}个 (姚加权2024-73词 + 补充{len(AI_DICT_2024PLUS)}词)")
    print(f"API端点: {len(API_ENDPOINTS)}个 (SiliconFlow x3 + DeepSeek官方x1)")

    for dir_name in sorted(all_dirs):
        dir_path = os.path.join(BASE_DIR, dir_name)
        for txt_file in os.listdir(dir_path):
            if not txt_file.endswith(".txt"):
                continue
            task_id = f"{dir_name}|{txt_file}"
            if task_id in done:
                stats["skip"] += 1
                continue
            tasks.append((dir_name, dir_path, txt_file))

    stats["total"] = len(tasks)
    print(f"待处理: {stats['total']} 个文件 (已跳过: {stats['skip']})\n")

    fieldnames = ["company_short", "stock_code", "year", "ai_mention_count",
                  "ai_strategy", "ai_investment", "ai_products", "has_ai_section",
                  "ai_cooperation", "ai_team", "ai_scenarios", "ai_overall_level",
                  "ai_para_count", "ai_signal", "error"]
    file_exists = os.path.exists(OUTPUT_CSV)

    start_time = time.time()
    completed_set = set(done)
    batch_results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(process_one_file, d, p, f): (d, f)
                      for d, p, f in tasks}
        completed_count = 0

        for future in as_completed(future_map):
            dir_name, txt_file = future_map[future]
            task_id = f"{dir_name}|{txt_file}"
            try:
                result = future.result()
                batch_results.append(result)
                completed_set.add(task_id)
                with stats_lock:
                    stats["done"] += 1
            except Exception as e:
                with stats_lock:
                    stats["fail"] += 1
                with open(LOG_FILE, "a", encoding="utf-8") as lf:
                    lf.write(f"FAIL {task_id}: {e}\n{traceback.format_exc()}\n")
                completed_set.add(task_id)

            completed_count += 1
            if completed_count % 200 == 0:
                elapsed = time.time() - start_time
                rate = completed_count / elapsed if elapsed > 0 else 0
                remaining = (stats["total"] - completed_count) / rate if rate > 0 else 0
                print(f"[{time.strftime('%H:%M:%S')}] "
                      f"{completed_count}/{stats['total']} "
                      f"√{stats['done']} ✗{stats['fail']} "
                      f"{rate:.1f}条/s 剩余{remaining/60:.0f}min")

                with open(OUTPUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    if not file_exists:
                        writer.writeheader()
                        file_exists = True
                    for r in batch_results:
                        writer.writerow(r)
                batch_results = []
                save_progress(completed_set)

    if batch_results:
        with open(OUTPUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            if not file_exists:
                writer.writeheader()
            for r in batch_results:
                writer.writerow(r)
    save_progress(completed_set)

    total_time = time.time() - start_time
    print(f"\n ALL DONE! 耗时: {total_time/60:.0f}min")
    print(f"成功: {stats['done']} | 失败: {stats['fail']} | 跳过: {stats['skip']}")
    print(f"输出: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()

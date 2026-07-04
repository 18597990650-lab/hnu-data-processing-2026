#!/usr/bin/env python3
"""
天眼查 A股上市公司信息爬虫 v2
- 支持手动登录后保存Cookie（storage_state）
- 断点续爬
- 代理池轮换
- 随机延迟 + 仿人类行为
"""

import csv
import json
import os
import random
import sys
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth


# ========== 配置 ==========
BASE_DIR = Path(__file__).parent
INPUT_CSV = BASE_DIR / "A股上市公司.csv"
OUTPUT_CSV = BASE_DIR / "天眼查_公司基本信息.csv"
PROXY_FILE = BASE_DIR / "proxies.txt"
PROGRESS_FILE = BASE_DIR / "progress.json"
AUTH_STATE_FILE = BASE_DIR / "auth_state.json"

# 反爬参数
MIN_DELAY = 8
MAX_DELAY = 15
MIN_BATCH_DELAY = 60
MAX_BATCH_DELAY = 90
BATCH_SIZE = 10

PAGE_TIMEOUT = 30000

OUTPUT_FIELDS = [
    "股票代码", "公司全称", "公司简称",
    "企业名称", "曾用名", "法定代表人", "登记状态", "天眼评分",
    "成立日期", "统一社会信用代码", "注册资本", "实缴资本",
    "工商注册号", "纳税人识别号", "组织机构代码",
    "营业期限", "纳税人资质", "核准日期", "企业类型",
    "国标行业", "人员规模", "参保人数", "英文名称",
    "分支机构参保人数", "登记机关", "注册地址", "经营范围",
    "电话", "邮箱", "网址", "企业规模", "员工人数",
    "营业收入", "简介", "天眼查URL",
]


def load_input_companies():
    companies = []
    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            companies.append({
                "股票代码": row["股票代码"].strip(),
                "公司全称": row["公司全称"].strip(),
                "公司简称": row["公司简称"].strip(),
            })
    return companies


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_progress(completed_codes):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(completed_codes), f, ensure_ascii=False)


def init_output_csv():
    if not OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=OUTPUT_FIELDS).writeheader()


def append_result(data):
    with open(OUTPUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=OUTPUT_FIELDS).writerow(data)


def human_delay():
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    print(f"  ⏳ 等待 {delay:.1f} 秒...")
    time.sleep(delay)


def random_scroll(page):
    try:
        page.evaluate(f"window.scrollBy(0, {random.randint(100, 500)})")
        time.sleep(random.uniform(0.3, 1.0))
        if random.random() > 0.5:
            page.evaluate(f"window.scrollBy(0, -{random.randint(50, 200)})")
    except Exception:
        pass


def get_auth_context(browser):
    """获取浏览器上下文，如果有保存的登录态则加载"""
    context_kwargs = {
        "viewport": {"width": 1366, "height": 768},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "locale": "zh-CN",
    }

    if AUTH_STATE_FILE.exists():
        print("✅ 加载已保存的登录态")
        context_kwargs["storage_state"] = str(AUTH_STATE_FILE)

    return browser.new_context(**context_kwargs)


def ensure_logged_in(page, context):
    """加载已保存的登录态（如果有），不强制登录"""
    # 如果之前保存了登录态，加载它
    if AUTH_STATE_FILE.exists():
        print("✅ 加载已保存的登录态")
        return True

    # 否则直接访问首页预热会话
    print("🔄 预热浏览器会话（无需登录也可搜索）...")
    page.goto("https://www.tianyancha.com/", timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
    time.sleep(random.uniform(3, 5))

    # 检查是否有安全验证
    if check_security_verification(page):
        print("  ⚠ 遇到安全验证，等待自动通过...")
        time.sleep(10)

    return True


def check_security_verification(page):
    try:
        if "security" in page.url or "验证" in page.title():
            return True
        if page.locator('text=安全验证').count() > 0:
            return True
        if page.locator('text=滑块验证').count() > 0:
            return True
    except Exception:
        pass
    return False


def wait_for_security_check(page, timeout=60):
    """等待用户手动完成安全验证，自动轮询"""
    print("  ⛔ 安全验证！请在浏览器中完成验证...")
    for i in range(timeout // 2):
        time.sleep(2)
        if not check_security_verification(page):
            print("  ✅ 验证已通过")
            return True
        if i % 5 == 4:
            print(f"   等待验证通过... ({ (i+1)*2 }秒)")
    print("  ⚠ 验证等待超时")
    return False


def extract_company_data(page, company):
    """从公司详情页提取数据"""

    # 等待页面加载
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except PlaywrightTimeout:
        pass

    # 等待关键元素
    try:
        page.wait_for_selector('.index_detail-content__RCnTr', timeout=30000)
    except PlaywrightTimeout:
        if check_security_verification(page):
            wait_for_security_check(page)
            try:
                page.wait_for_selector('.index_detail-content__RCnTr', timeout=15000)
            except PlaywrightTimeout:
                pass
        else:
            print(f"  ⚠ 选择器超时，URL: {page.url[:80]}")

    # JS 提取 Section1 + Section2
    js = """
    () => {
        function getEl(xpath) {
            return document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        }

        const result = {};

        // Section 1
        const s1 = getEl('/html/body/div[1]/div/div[2]/div/div[1]/div[1]/div[2]/div[1]/div[2]');
        if (s1) {
            const content = s1.querySelector('.index_detail-content__RCnTr');
            if (content) {
                function getValue(label) {
                    const items = content.querySelectorAll('.index_detail-info-item__oAOqL');
                    for (const item of items) {
                        const labelEl = item.querySelector('.index_detail-label__oRf2J');
                        if (labelEl && labelEl.textContent.includes(label)) {
                            const valEl = item.querySelector('.index_detail-text__Ac9Py');
                            if (valEl) return valEl.textContent.trim();
                            const phoneEl = item.querySelector('.link-hover-click');
                            if (phoneEl) return phoneEl.textContent.trim();
                            return item.textContent.replace(label, '').trim();
                        }
                    }
                    return '';
                }
                const creditEl = content.querySelector('.index_detail-credit-code__fH1Ny span');
                result['统一社会信用代码_s1'] = creditEl ? creditEl.textContent.trim() : '';
                const legalEl = content.querySelector('.index_legal-person-root__THrdz .index_copy-val__Qdkxu');
                result['法定代表人_s1'] = legalEl ? legalEl.textContent.trim() : '';
                result['注册资本_s1'] = getValue('注册资本');
                result['成立日期_s1'] = getValue('成立日期');
                result['电话'] = getValue('电话');
                const emailEl = content.querySelector('.index_detail-email__B_1Tq');
                result['邮箱'] = emailEl ? emailEl.textContent.trim() : '';
                const webEl = content.querySelector('.index_detail-website__n2yst');
                result['网址'] = webEl ? webEl.textContent.trim() : '';
                const addrEl = content.querySelector('.index_detail-address-moretext__9R_Z1 span');
                result['地址'] = addrEl ? addrEl.textContent.trim() : '';
                const industryEl = content.querySelector('.index_industry-content__htK_G .index_label__5wqGJ');
                result['国标行业_s1'] = industryEl ? industryEl.textContent.trim() : '';
                result['企业规模'] = getValue('企业规模');
                result['员工人数'] = getValue('员工人数');
                result['营业收入'] = getValue('营业收入');
                const introEl = s1.querySelector('.index_-intro__ma3Qd');
                if (introEl) result['简介'] = introEl.textContent.replace(/^基本信息/, '').trim();
            }
        }

        // Section 2
        const s2 = getEl('/html/body/div[1]/div/div[2]/div[1]/div[4]/div/div[3]/div[2]/div[2]/div[1]/div/div[2]');
        if (s2) {
            const table = s2.querySelector('table');
            if (table) {
                const rows = table.querySelectorAll('tr');
                for (const row of rows) {
                    const tds = row.querySelectorAll('td');
                    for (let i = 0; i < tds.length - 1; i++) {
                        const labelText = tds[i].textContent.trim();
                        const valueTd = tds[i + 1];
                        if (tds[i].getAttribute('rowspan') && i > 0 && tds[i].textContent.trim().length > 15) continue;
                        let value = valueTd.textContent.trim().replace(/\\s+/g, ' ');
                        if (labelText === '企业名称') {
                            const nameDiv = valueTd.querySelector('.index_copy-text__ri7W6');
                            result['企业名称'] = nameDiv ? nameDiv.textContent.trim() : value.split('曾用名')[0].trim();
                            const histDiv = valueTd.querySelector('.index_history-gray-text__ecmGl .index_copy-text__ri7W6');
                            if (histDiv) result['曾用名'] = histDiv.textContent.trim();
                        } else if (labelText === '法定代表人') {
                            const nameLink = valueTd.querySelector('a.link-click');
                            result['法定代表人'] = nameLink ? nameLink.textContent.trim() : value.split('关联企业')[0].trim();
                        } else if (labelText === '天眼评分') {
                            const scoreEl = valueTd.querySelector('.index_sort-score-value__72dxg');
                            const descEl = valueTd.querySelector('.index_sort-score-desc__JcKD2');
                            result['天眼评分'] = scoreEl ? scoreEl.textContent.trim() + (descEl||'') : value;
                        } else if (labelText === '注册资本') {
                            result['注册资本'] = value.split(/(?:关联|查看)/)[0].trim();
                        } else if (labelText === '参保人数') {
                            result['参保人数'] = (value.match(/^(\\d+)/) || [''])[0];
                        } else if (labelText === '分支机构参保人数') {
                            result['分支机构参保人数'] = (value.match(/^(\\d+)/) || [''])[0];
                        } else if (labelText === '注册地址') {
                            result['注册地址'] = value.split('附近公司')[0].trim();
                        } else if (labelText === '国标行业') {
                            const label = valueTd.querySelector('.index_label__5wqGJ');
                            result['国标行业'] = label ? label.textContent.trim() : value;
                        } else if (labelText === '核准日期') {
                            result['核准日期'] = value.replace('核准日期', '').trim();
                        } else if (labelText === '营业期限') {
                            result['营业期限'] = value.replace('营业期限', '').trim();
                        } else if (labelText === '英文名称') {
                            const enName = valueTd.querySelector('.index_copy-text__ri7W6');
                            result['英文名称'] = enName ? enName.textContent.trim() : value;
                        } else if (labelText === '经营范围') {
                            result['经营范围'] = value.replace('经营范围', '').trim();
                        } else if (labelText === '登记机关') {
                            result['登记机关'] = value.replace('登记机关', '').trim();
                        } else if (labelText === '成立日期') {
                            result['成立日期'] = value;
                        } else if (['统一社会信用代码', '实缴资本', '工商注册号', '纳税人识别号',
                                    '组织机构代码', '纳税人资质', '企业类型', '人员规模', '登记状态'].includes(labelText)) {
                            result[labelText] = value;
                        }
                    }
                }
            }
        }

        return result;
    }
    """

    try:
        data = page.evaluate(js)
    except Exception as e:
        print(f"  ⚠ JS提取错误: {e}")
        data = {}

    result = {
        "股票代码": company["股票代码"],
        "公司全称": company["公司全称"],
        "公司简称": company["公司简称"],
        "企业名称": data.get("企业名称", ""),
        "曾用名": data.get("曾用名", ""),
        "法定代表人": data.get("法定代表人", data.get("法定代表人_s1", "")),
        "登记状态": data.get("登记状态", ""),
        "天眼评分": data.get("天眼评分", ""),
        "成立日期": data.get("成立日期", data.get("成立日期_s1", "")),
        "统一社会信用代码": data.get("统一社会信用代码", data.get("统一社会信用代码_s1", "")),
        "注册资本": data.get("注册资本", data.get("注册资本_s1", "")),
        "实缴资本": data.get("实缴资本", ""),
        "工商注册号": data.get("工商注册号", ""),
        "纳税人识别号": data.get("纳税人识别号", ""),
        "组织机构代码": data.get("组织机构代码", ""),
        "营业期限": data.get("营业期限", ""),
        "纳税人资质": data.get("纳税人资质", ""),
        "核准日期": data.get("核准日期", ""),
        "企业类型": data.get("企业类型", ""),
        "国标行业": data.get("国标行业", data.get("国标行业_s1", "")),
        "人员规模": data.get("人员规模", ""),
        "参保人数": data.get("参保人数", ""),
        "英文名称": data.get("英文名称", ""),
        "分支机构参保人数": data.get("分支机构参保人数", ""),
        "登记机关": data.get("登记机关", ""),
        "注册地址": data.get("注册地址", data.get("地址", "")),
        "经营范围": data.get("经营范围", ""),
        "电话": data.get("电话", ""),
        "邮箱": data.get("邮箱", ""),
        "网址": data.get("网址", ""),
        "企业规模": data.get("企业规模", ""),
        "员工人数": data.get("员工人数", ""),
        "营业收入": data.get("营业收入", ""),
        "简介": data.get("简介", ""),
        "天眼查URL": page.url,
    }

    return result


def scrape_company(page, company):
    """爬取单个公司"""
    name = company["公司全称"]
    code = company["股票代码"]

    search_url = f"https://www.tianyancha.com/search?key={urllib.parse.quote(name)}"
    print(f"\n[{code}] {name}")

    try:
        page.goto(search_url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        time.sleep(random.uniform(3, 5))

        if check_security_verification(page):
            wait_for_security_check(page)
            page.goto(search_url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
            time.sleep(random.uniform(3, 5))

        random_scroll(page)

        # 查找第一个搜索结果
        detail_url = None

        # 等待搜索结果容器出现
        try:
            page.wait_for_selector('a[href*="/company/"]', timeout=10000)
        except PlaywrightTimeout:
            pass

        # 优先用精确选择器
        first_result = page.locator('a.index_alink__Qq_O9.link-click').first
        if first_result.count() > 0:
            detail_url = first_result.get_attribute("href")
        else:
            # Fallback: 直接用公司名链接
            first_result = page.locator(f'a[href*="/company/"]:has-text("{name[:4]}")').first
            if first_result.count() > 0:
                detail_url = first_result.get_attribute("href")
            else:
                first_result = page.locator('a[href*="/company/"]').first
                if first_result.count() > 0:
                    detail_url = first_result.get_attribute("href")

        if not detail_url:
            print("  ⚠ 未找到搜索结果")
            return None

        # 直接导航到详情页
        page.goto(detail_url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        time.sleep(random.uniform(3, 6))

        if check_security_verification(page):
            wait_for_security_check(page)

        random_scroll(page)
        result = extract_company_data(page, company)

        if result:
            print(f"  ✅ 法人={result.get('法定代表人','')}, "
                  f"注册资本={result.get('注册资本','')}, "
                  f"行业={result.get('国标行业','')}")
        return result

    except PlaywrightTimeout as e:
        print(f"  ⚠ 超时: {e}")
        return None
    except Exception as e:
        print(f"  ⚠ 错误: {type(e).__name__}: {e}")
        return None


def main():
    print("=" * 60)
    print("  天眼查 A股上市公司信息爬虫 v2")
    print("=" * 60)

    companies = load_input_companies()
    print(f"待爬取: {len(companies)} 家公司")

    completed = load_progress()
    pending = [c for c in companies if c["股票代码"] not in completed]
    print(f"已完成: {len(completed)}, 剩余: {len(pending)}")

    if not pending:
        print("全部已完成！")
        return

    init_output_csv()
    screenshot_dir = BASE_DIR / "debug_screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = get_auth_context(browser)
        page = context.new_page()

        try:
            Stealth().apply_stealth_sync(page)
        except Exception:
            pass

        # 确保登录
        ensure_logged_in(page, context)

        success = 0
        fail = 0
        batch = 0

        for i, company in enumerate(pending):
            result = scrape_company(page, company)

            if result:
                append_result(result)
                completed.add(company["股票代码"])
                save_progress(completed)
                success += 1
            else:
                fail += 1

            batch += 1
            total = success + fail
            print(f"\n📊 进度: {total}/{len(pending)} (成功:{success} 失败:{fail})")

            if batch >= BATCH_SIZE:
                delay = random.uniform(MIN_BATCH_DELAY, MAX_BATCH_DELAY)
                print(f"\n🛌 批次休息 {delay:.0f} 秒...")
                time.sleep(delay)
                batch = 0
            else:
                human_delay()

        browser.close()

    print(f"\n🎉 完成！成功:{success} 失败:{fail}")
    print(f"结果: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()

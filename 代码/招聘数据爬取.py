# 导入自动化模块
from DrissionPage import ChromiumOptions, ChromiumPage
# 只有第一次使用的时候需要进行配置，后续如果不更改浏览器可执行文件位置，就不需要配置了
path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ChromiumOptions().set_browser_path(path).save()
# 导入时间模块、csv模块
import time
import csv
import os
import json

COOKIE_FILE = 'boss_cookies.json'

def ensure_login(dp):
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        for cookie in cookies:
            dp.set.cookies(cookie)

    dp.get('https://www.zhipin.com')
    time.sleep(2)

    print('\n========================================')
    print('  请在浏览器中确认是否已登录')
    print('  如果未登录，请手动完成登录')
    print('  （手机号 → 验证码 → 登录）')
    print('  确认登录成功后，回到终端按 Enter 键继续...')
    print('========================================')
    input()

    print('正在保存登录状态...')
    cookies = dp.cookies()
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False)
    print('登录状态已保存，下次无需再登录\n')

def crawl_zhipin(dp, keyword):
    """根据关键词爬取BOSS直聘岗位数据"""
    print(f'\n=====================================')
    print(f'      开始爬取关键词：{keyword}')
    print(f'=====================================\n')
    # 监听数据包
    dp.listen.start('joblist')
    # 访问网站（动态传入关键词）
    url = f'https://www.zhipin.com/web/geek/jobs?city=100010000&position=100109&query={keyword}'
    dp.get(url)
    # 死循环翻页 + 连续3次无数据包则退出
    max_fail_count = 3  # 最多连续失败3次
    fail_count = 0  # 当前连续失败次数
    page = 1  # 页码计数
    while True:
        print(f'[{keyword}] 正在采集第{page}页的数据')
        try:
            # 等待数据包加载（超时5秒）
            resp = dp.listen.wait(timeout=5)
            json_data = resp.response.body
            # 成功拿到数据 → 重置失败计数
            fail_count = 0
            # 字典取值，提取职位信息所在列表
            jobList = json_data['zpData']['jobList']
            # for循环遍历，提取列表里面的元素
            for job in jobList:
                # 在循环中提取每个岗位的具体信息
                dit = {
                    '搜索关键词': keyword,  # 把当前关键词存入
                    'securityId': job['securityId'],
                    '招聘人头像': job['bossAvatar'],
                    'bossCert': job['bossCert'],
                    'encryptBossId': job['encryptBossId'],
                    '招聘人姓名': job['bossName'],
                    'bossTitle': job['bossTitle'],
                    'goldHunter': job['goldHunter'],
                    'bossOnline': job['bossOnline'],
                    '职位ID': job['encryptJobId'],
                    '职位类别ID': job['expectId'],
                    '岗位名称': job['jobName'],
                    '薪资描述': job['salaryDesc'],
                    '岗位标签': job['jobLabels'],
                    'jobValidStatus': job['jobValidStatus'],
                    '岗位技能': job['skills'],
                    '岗位经验要求': job['jobExperience'],
                    '岗位学历要求': job['jobDegree'],
                    '城市': job['cityName'],
                    '区域': job['areaDistrict'],
                    '商圈': job['businessDistrict'],
                    '城市ID': job['city'],
                    '纬度': job['gps']['latitude'],
                    '经度': job['gps']['longitude'],
                    '公司ID': job['encryptBrandId'],
                    '公司名称': job['brandName'],
                    '公司Logo': job['brandLogo'],
                    '公司融资情况': job['brandStageName'],
                    '公司领域': job['brandIndustry'],
                    '公司规模': job['brandScaleName'],
                    '福利标签': job['welfareList'],
                    '行业ID': job['industry'],
                }
                print(dit)
                # 写入数据
                csv_writer.writerow(dit)

            # 点击"下一页"按钮翻页
            next_btn = dp.ele('.options-pages a:last-child', timeout=3)
            if next_btn is None:
                print(f'[{keyword}] 未找到翻页按钮，数据采集完毕')
                break
            class_name = next_btn.attr('class') or ''
            if 'disable' in class_name:
                print(f'[{keyword}] 已到最后一页，共{page}页')
                break
            next_btn.click()
            page += 1
            time.sleep(3)  # 等待新页面数据包触发

        # 捕获超时/无数据包异常
        except Exception as e:
            fail_count += 1
            print(f'[{keyword}] 第{page}页获取数据失败，当前连续失败次数：{fail_count}/{max_fail_count}')

            if fail_count >= max_fail_count:
                print(f'[{keyword}] 连续{max_fail_count}次未获取到数据包，已无更多数据！')
                break

            # 失败后尝试下滑翻页作为备用
            dp.scroll.to_bottom()
            time.sleep(3)


# ===================== 主函数入口（多关键词输入） =====================
if __name__ == '__main__':
    print("=" * 50)
    print("          BOSS直聘爬虫启动（多关键词版）")
    print("=" * 50)
    print("请输入要爬取的关键词，多个关键词用 **英文逗号** 分隔")
    print("示例：python,java,前端,测试\n")

    # 固定关键词列表（如需手动输入，取消下面注释并把 keyword_list 那行注释掉）
    # keyword_input = input("请输入关键词：").strip()
    # keyword_list = [k.strip() for k in keyword_input.split(',') if k.strip()]
    keyword_list = [
        '人工智能', '机器学习', '自然语言处理', '强化学习', '深度学习',
        '大数据', '数据挖掘', '云计算', 'AI芯片', '自动驾驶',
        '计算机视觉', 'Python', '神经网络', '风控算法', '知识图谱',
        'AI产品', '机器人', '智能体', '图像算法', '全栈工程师'
    ]

    if not keyword_list:
        print("未输入有效关键词，程序退出！")
        exit()

    # 全局只打开一次CSV文件，所有关键词数据写入同一个文件
    f = open('jobdata.csv', 'w', newline='', encoding='utf-8-sig')
    csv_writer = csv.DictWriter(f, fieldnames=[
        '搜索关键词',
        'securityId', '招聘人头像', 'bossCert', 'encryptBossId', '招聘人姓名',
        'bossTitle', 'goldHunter', 'bossOnline', '职位ID', '职位类别ID',
        '岗位名称', '薪资描述', '岗位标签', 'jobValidStatus', '岗位技能',
        '岗位经验要求', '岗位学历要求', '城市', '区域', '商圈', '城市ID',
        '纬度', '经度', '公司ID', '公司名称', '公司Logo', '公司融资情况',
        '公司领域', '公司规模', '福利标签', '行业ID'
    ])
    csv_writer.writeheader()

    dp = ChromiumPage()
    ensure_login(dp)

    for kw in keyword_list:
        crawl_zhipin(dp, kw)

    dp.quit()
    f.close()
    print("\n所有关键词爬取完毕！程序已安全退出")
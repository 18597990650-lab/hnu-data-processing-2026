import os
import re
import csv
import pandas as pd

年报文件夹 = r'c:\Users\dell\Desktop\公司年报_txt'
AI数据文件 = r'c:\Users\dell\.trae-cn\attachments\6a47c77ed3e35782e2c323e1\370662fa-9baa-4c70-bce8-d7bd27d8fb7e_07d0cf3e-5046-493a-a8d3-c8f3774d4c31_年报AI提取结果.csv'
输出文件 = os.path.join(年报文件夹, '上市公司年报数据表.xlsx')

非法字符 = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
年报后缀 = re.compile(r'\d{4}\s*年\s*年度报告.*$|\d{4}\s*年度.*$|年度报告.*$')


def 清洗文本(文本):
    if isinstance(文本, str):
        return 非法字符.sub('', 文本)
    return 文本


def 读取文件头(路径, 长度=8000):
    for 编码 in ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'gb2312']:
        try:
            with open(路径, 'r', encoding=编码, errors='replace') as f:
                return f.read(长度)
        except Exception:
            continue
    return ''


def 去掉年报后缀(原始名称):
    return 年报后缀.sub('', 原始名称).strip()


def 从头部提取公司信息(头部, 文件夹简称, 文件夹代码):
    代码匹配 = re.search(r'公司代码[：:]\s*(\S+)', 头部)
    简称匹配 = re.search(r'公司简称[：:]\s*(\S+)', 头部)
    股票代码 = 代码匹配.group(1).strip() if 代码匹配 else 文件夹代码
    公司简称 = 简称匹配.group(1).strip() if 简称匹配 else 文件夹简称

    行列表 = 头部.split('\n')
    全称 = ''

    for i, 行 in enumerate(行列表):
        if '公司代码' in 行 and '公司简称' in 行:
            for j in range(i + 1, min(i + 15, len(行列表))):
                候选 = 行列表[j].strip()
                候选 = 去掉年报后缀(候选)
                if 候选 and len(候选) > 6 and '公司' in 候选 and '年' not in 候选[-3:]:
                    全称 = 候选
                    break
            break

    if not 全称:
        for 行 in 行列表:
            候选 = 去掉年报后缀(行.strip())
            if re.match(r'^.{4,}股份', 候选) and '公司' in 候选 and len(候选) > 6:
                全称 = 候选
                break

    if not 全称:
        for 行 in 行列表:
            候选 = 去掉年报后缀(行.strip())
            if 候选 and len(候选) > 6 and '公司' in 候选:
                全称 = 候选
                break

    return 全称, 公司简称, 股票代码


def 推断简称(全称):
    简称 = 全称
    for 后缀 in ['股份有限公司', '有限责任公司', '集团有限公司', '有限公司']:
        简称 = 简称.replace(后缀, '')
    return 简称.strip()


def 从文件头补充全称(头部):
    行列表 = 头部.split('\n')
    全称 = ''

    for i, 行 in enumerate(行列表):
        if '公司代码' in 行:
            for j in range(i + 1, min(i + 20, len(行列表))):
                候选 = 去掉年报后缀(行列表[j].strip())
                if 候选 and len(候选) > 8 and '公司' in 候选:
                    全称 = 候选
                    break
            break

    if not 全称:
        for 行 in 行列表[:30]:
            候选 = 去掉年报后缀(行.strip())
            if re.search(r'股份(有限|集团)', 候选) and len(候选) > 8:
                全称 = 候选
                break
            if re.search(r'有限(责任)?公司$', 候选) and len(候选) > 8:
                全称 = 候选
                break

    if not 全称:
        匹配 = re.search(r'([\u4e00-\u9fff]{4,}股份(?:有限|集团)公司)', 头部[:5000])
        if 匹配:
            全称 = 匹配.group(1)
        else:
            匹配 = re.search(r'([\u4e00-\u9fff]{4,}有限公司)', 头部[:5000])
            if 匹配 and len(匹配.group(1)) > 8:
                全称 = 匹配.group(1)

    return 全称


AI字段列表 = ['ai_mention_count', 'ai_strategy', 'ai_investment', 'ai_products',
             'has_ai_section', 'ai_cooperation', 'ai_team', 'ai_scenarios',
             'ai_overall_level', 'ai_para_count', 'ai_signal', 'error']


def 主营():
    print("读取AI提取结果...")
    索引 = {}
    with open(AI数据文件, 'r', encoding='utf-8-sig') as f:
        for 行 in csv.DictReader(f):
            键 = (行['stock_code'].strip(), int(行['year']) if 行['year'].strip().isdigit() else 0)
            索引[键] = 行
    print(f"  {len(索引)} 条AI数据已加载")

    公司文件夹列表 = sorted([d for d in os.listdir(年报文件夹)
                        if os.path.isdir(os.path.join(年报文件夹, d)) and '_' in d])
    print(f"  共 {len(公司文件夹列表)} 个公司文件夹")

    print("从TXT文件中提取信息...")
    记录列表 = []

    for 序号, 文件夹名 in enumerate(公司文件夹列表, 1):
        文件夹路径 = os.path.join(年报文件夹, 文件夹名)
        拆分 = 文件夹名.split('_')
        默认简称 = 拆分[0]
        默认代码 = 拆分[-1]

        for 文件名 in sorted(os.listdir(文件夹路径)):
            if not 文件名.endswith('.txt'):
                continue

            年份匹配 = re.search(r'(\d{4})年', 文件名)
            if not 年份匹配:
                continue
            年份 = int(年份匹配.group(1))

            文件路径 = os.path.join(文件夹路径, 文件名)
            文件大小 = os.path.getsize(文件路径)
            文本状态 = 1 if 文件大小 > 500 else 0

            try:
                头部 = 读取文件头(文件路径)
                全称, 简称, 代码 = 从头部提取公司信息(头部, 默认简称, 默认代码)
            except Exception:
                全称 = ''
                简称 = 默认简称
                代码 = 默认代码

            键 = (代码.strip(), 年份)
            AI行 = 索引.get(键, {})

            记录 = {
                '上市公司全称': 清洗文本(全称),
                '上市公司简称': 清洗文本(简称),
                '股票代码': 清洗文本(代码),
                '年份': 年份,
                '年度报告全文': 文本状态,
            }
            for 字段名 in AI字段列表:
                值 = AI行.get(字段名, '')
                if 值 == 'True':
                    值 = True
                elif 值 == 'False':
                    值 = False
                记录[字段名] = 值

            记录列表.append(记录)

        if 序号 % 500 == 0:
            print(f"  已处理 {序号}/{len(公司文件夹列表)} 家公司, {len(记录列表)} 条记录...")

    print(f"  共提取 {len(记录列表)} 条记录")

    数据框 = pd.DataFrame(记录列表)

    print("\n检查并修复前三列缺失值...")
    缺失计数 = {
        '全称': 数据框['上市公司全称'].isna().sum() + (数据框['上市公司全称'].astype(str).str.strip() == '').sum(),
        '简称': 数据框['上市公司简称'].isna().sum() + (数据框['上市公司简称'].astype(str).str.strip() == '').sum(),
        '代码': 数据框['股票代码'].isna().sum() + (数据框['股票代码'].astype(str).str.strip() == '').sum(),
    }
    print(f"  修复前 - 全称缺失: {缺失计数['全称']}, 简称缺失: {缺失计数['简称']}, 代码缺失: {缺失计数['代码']}")

    代码到文件夹 = {}
    for 文件夹名 in 公司文件夹列表:
        拆分 = 文件夹名.split('_')
        c = 拆分[-1]
        代码到文件夹.setdefault(c, []).append(文件夹名)

    修复全称 = 0
    修复简称 = 0
    修复代码 = 0

    for 序号 in 数据框.index:
        全称缺失 = pd.isna(数据框.at[序号, '上市公司全称']) or (isinstance(数据框.at[序号, '上市公司全称'], str) and 数据框.at[序号, '上市公司全称'].strip() == '')
        简称缺失 = pd.isna(数据框.at[序号, '上市公司简称']) or (isinstance(数据框.at[序号, '上市公司简称'], str) and 数据框.at[序号, '上市公司简称'].strip() == '')
        代码缺失 = pd.isna(数据框.at[序号, '股票代码']) or (isinstance(数据框.at[序号, '股票代码'], str) and 数据框.at[序号, '股票代码'].strip() == '')

        if not (全称缺失 or 简称缺失 or 代码缺失):
            continue

        代码 = str(数据框.at[序号, '股票代码']).strip() if not 代码缺失 else ''
        年份 = 数据框.at[序号, '年份']

        文件路径 = None
        if 代码 in 代码到文件夹:
            for 文件夹 in 代码到文件夹[代码]:
                路径 = os.path.join(年报文件夹, 文件夹)
                for f in os.listdir(路径):
                    if f.endswith('.txt') and str(年份) in f:
                        文件路径 = os.path.join(路径, f)
                        break
                if 文件路径:
                    break

        头部 = ''
        if 文件路径:
            头部 = 读取文件头(文件路径, 10000)

        if 全称缺失:
            if 头部:
                新全称 = 从文件头补充全称(头部)
                if 新全称:
                    数据框.at[序号, '上市公司全称'] = 清洗文本(新全称)
                    修复全称 += 1
                elif 全称缺失:
                    sn = 数据框.at[序号, '上市公司简称']
                    if sn and isinstance(sn, str) and sn.strip():
                        数据框.at[序号, '上市公司全称'] = sn.strip()
                        修复全称 += 1

        if 简称缺失:
            if 头部:
                匹配 = re.search(r'公司简称[：:]\s*(\S+)', 头部)
                if 匹配:
                    数据框.at[序号, '上市公司简称'] = 清洗文本(匹配.group(1).strip())
                    修复简称 += 1
            if 简称缺失:
                fn = 数据框.at[序号, '上市公司全称']
                if fn and isinstance(fn, str) and fn.strip():
                    数据框.at[序号, '上市公司简称'] = 推断简称(fn.strip())
                    修复简称 += 1
            if 简称缺失:
                if 代码 and 代码 in 代码到文件夹:
                    fallback = 代码到文件夹[代码][0].split('_')[0]
                    数据框.at[序号, '上市公司简称'] = fallback
                    修复简称 += 1

        if 代码缺失:
            if 文件路径:
                folder = os.path.basename(os.path.dirname(文件路径))
                parts = folder.split('_')
                if len(parts) > 1:
                    数据框.at[序号, '股票代码'] = parts[-1]
                    修复代码 += 1

    print(f"  修复后 - 全称: {修复全称}, 简称: {修复简称}, 代码: {修复代码}")

    print("\n写入Excel...")
    数据框.to_excel(输出文件, index=False, sheet_name='上市公司年报数据')
    print(f"  完成! 文件已保存: {输出文件}")


if __name__ == '__main__':
    主营()

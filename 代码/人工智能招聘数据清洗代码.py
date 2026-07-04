import pandas as pd
import numpy as np
import os
import datetime

原始文件路径 = r'c:\Users\dell\Desktop\数据\人工智能招聘大数据.csv'
输出文件路径 = r'c:\Users\dell\Desktop\数据\人工智能招聘大数据_已清洗.csv'
日志文件路径 = r'c:\Users\dell\Desktop\数据\数据清洗日志.txt'

清洗日志 = []

def 记录日志(消息):
    清洗日志.append(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {消息}")
    print(消息)

记录日志("=" * 60)
记录日志("数据清洗任务开始")
记录日志("=" * 60)

文件大小MB = os.path.getsize(原始文件路径) / (1024 * 1024)
记录日志(f"正在读取原始文件: {原始文件路径}")
记录日志(f"文件大小: {文件大小MB:.2f} MB")

分块大小 = 200000
数据块列表 = []
总行数 = 0

for 块 in pd.read_csv(原始文件路径, chunksize=分块大小, dtype=str, low_memory=False):
    数据块列表.append(块)
    总行数 += len(块)
    记录日志(f"已读取第{len(数据块列表)}块, 累计{总行数}行")

记录日志(f"原始数据总行数: {总行数}")

记录日志("正在合并所有数据块...")
原始数据 = pd.concat(数据块列表, ignore_index=True)
del 数据块列表
记录日志(f"合并后数据行数: {len(原始数据)}")

原始行数 = len(原始数据)
去除后行数 = 原始数据.drop_duplicates().shape[0]
重复行数 = 原始行数 - 去除后行数
记录日志(f"去除完全重复行: 删除{重复行数}行 ({重复行数/原始行数*100:.4f}%)")
原始数据 = 原始数据.drop_duplicates()

字符串列 = ['人工智能关键词', '企业名称', '招聘岗位', '工作城市', '工作区域',
            '职位描述', '学历要求', '要求经验', '招聘人数', '招聘类别', '初级分类',
            '公司地点', '工作地点', '招聘发布日期', '招聘结束日期']
for 列名 in 字符串列:
    if 列名 in 原始数据.columns:
        原始数据[列名] = 原始数据[列名].astype(str).str.strip()
        原始数据[列名] = 原始数据[列名].replace(['nan', 'None', 'NaN', '', 'none'], np.nan)
记录日志("已完成所有字符串列去除前后空格")

关键字段 = ['企业名称', '招聘岗位', '工作城市']
删除前 = len(原始数据)
原始数据 = 原始数据.dropna(subset=关键字段, how='all')
删除后 = len(原始数据)
记录日志(f"删除关键列全空行: 删除{删除前 - 删除后}行")

薪资逻辑错误数 = 0

def 处理薪资列(数据):
    global 薪资逻辑错误数
    最低 = pd.to_numeric(数据['最低月薪'], errors='coerce')
    最高 = pd.to_numeric(数据['最高月薪'], errors='coerce')
    逻辑错误掩码 = (最低 > 最高) & 最低.notna() & 最高.notna()
    薪资逻辑错误数 = 逻辑错误掩码.sum()
    交换临时 = 最低.copy()
    最低[逻辑错误掩码] = 最高[逻辑错误掩码]
    最高[逻辑错误掩码] = 交换临时[逻辑错误掩码]
    数据['最低月薪'] = 最低
    数据['最高月薪'] = 最高
    return 数据

原始数据 = 处理薪资列(原始数据)
记录日志(f"薪资逻辑修正: 交换{薪资逻辑错误数}行的最低/最高月薪")

for 年份列 in ['招聘发布年份', '招聘结束年份']:
    if 年份列 in 原始数据.columns:
        原始数据[年份列] = pd.to_numeric(原始数据[年份列], errors='coerce')
        原始数据[年份列] = 原始数据[年份列].astype('Int64')
记录日志("年份列已去除小数点并转为整数类型")

日期格式修正数 = 0

def 统一日期格式(值):
    global 日期格式修正数
    if pd.isna(值) or str(值).strip() in ['', 'nan', 'None']:
        return np.nan
    值 = str(值).strip()
    尝试解析 = pd.to_datetime(值, errors='coerce', format='mixed')
    if pd.notna(尝试解析):
        return 尝试解析.strftime('%Y-%m-%d')
    else:
        日期格式修正数 += 1
        return np.nan

for 日期列 in ['招聘发布日期', '招聘结束日期']:
    if 日期列 in 原始数据.columns:
        日期格式修正数 = 0
        原始数据[日期列] = 原始数据[日期列].apply(统一日期格式)
        记录日志(f"{日期列}: 修正{日期格式修正数}行日期格式, 无法解析的设为空值")

原始数据['最低月薪'] = 原始数据['最低月薪'].astype('Float64')
原始数据['最高月薪'] = 原始数据['最高月薪'].astype('Float64')
记录日志("薪资列已转为可空浮点数类型(Float64)")

记录日志(f"正在保存清洗后数据到: {输出文件路径}")
原始数据.to_csv(输出文件路径, index=False, encoding='utf-8-sig')
记录日志(f"清洗后数据已保存, 共{len(原始数据)}行")

清洗日志.append("")
清洗日志.append("=" * 60)
清洗日志.append("数据清洗摘要")
清洗日志.append("=" * 60)
清洗日志.append(f"原始文件: {原始文件路径}")
清洗日志.append(f"原始行数: {总行数}")
清洗日志.append(f"完全重复行删除: {重复行数}")
清洗日志.append(f"关键列全空行删除: {删除前 - 删除后}")
清洗日志.append(f"薪资逻辑修正: {薪资逻辑错误数}")
清洗日志.append(f"清洗后行数: {len(原始数据)}")
清洗日志.append(f"清洗后文件: {输出文件路径}")

with open(日志文件路径, 'w', encoding='utf-8') as f:
    f.write('\n'.join(清洗日志))
记录日志(f"清洗日志已保存到: {日志文件路径}")

记录日志("=" * 60)
记录日志("数据清洗任务完成!")
记录日志("=" * 60)

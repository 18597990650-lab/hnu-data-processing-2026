# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import re
from datetime import datetime

原始文件路径 = r"c:\Users\dell\.trae-cn\work\6a44a52c4bd6e6e419550cbe\专利数据2\专利数据.csv"
清洗后文件路径 = r"c:\Users\dell\Desktop\专利数据_清洗后.csv"
清洗报告路径 = r"c:\Users\dell\Desktop\专利数据清洗报告.txt"

df = pd.read_csv(原始文件路径, encoding="utf-8", low_memory=False)
原始行数 = len(df)
清洗记录 = []
清洗记录.append(f"原始数据行数: {原始行数}")
清洗记录.append(f"原始数据列数: {len(df.columns)}")

清洗记录.append("\n【一、完整性清洗】")

核心字段缺失 = df["申请号/专利号"].isna() | df["发明名称"].isna() | df["申请日"].isna() | df["主分类号"].isna()
核心字段缺失数 = 核心字段缺失.sum()
清洗记录.append(f"核心字段缺失记录: {核心字段缺失数} 条")
df = df[~核心字段缺失].copy()

空字符串字段 = ["发明名称", "申请日", "主分类号", "案件状态", "法律状态", "申请人姓名或名称",
             "国籍或总部所在地", "发明人姓名", "代理机构名称", "第一代理人"]
for 字段 in 空字符串字段:
    if 字段 in df.columns:
        空值数 = (df[字段].astype(str).str.strip() == "--").sum()
        if 空值数 > 0:
            df.loc[df[字段].astype(str).str.strip() == "--", 字段] = np.nan
            清洗记录.append(f"字段'{字段}'中'--'转为null: {空值数} 条")

清洗记录.append(f"删除低价值列（邮政编码、详细地址）")
df = df.drop(columns=["邮政编码", "详细地址"], errors="ignore")

案件状态填充前 = df["案件状态"].isna().sum()
df["案件状态"] = df["案件状态"].fillna("未知")
清洗记录.append(f"案件状态缺失填充: {案件状态填充前} 条")

法律状态映射 = {
    "专利权维持": "专利权维持",
    "驳回失效": "驳回失效",
    "等待实审提案": "审查中",
    "未缴年费终止失效": "专利权终止",
    "逾期视撤失效": "撤回失效",
    "驳回等复审请求": "复审中",
    "一通出案待答复": "审查中",
    "撤回专利申请": "撤回",
    "一通回案实审": "审查中",
    "复审程序中": "复审中",
}
法律状态缺失数 = df["法律状态"].isna().sum()
if 法律状态缺失数 > 0:
    缺失掩码 = df["法律状态"].isna()
    df.loc[缺失掩码, "法律状态"] = df.loc[缺失掩码, "案件状态"].map(法律状态映射)
    法律状态仍缺失 = df["法律状态"].isna().sum()
    df["法律状态"] = df["法律状态"].fillna("未知")
    清洗记录.append(f"法律状态缺失处理: 原缺失{法律状态缺失数}条，映射填充{法律状态缺失数-法律状态仍缺失}条，剩余填充为'未知'")

国籍缺失 = df["国籍或总部所在地"].isna().sum()
df["国籍或总部所在地"] = df["国籍或总部所在地"].fillna("中国")
清洗记录.append(f"国籍填充: {国籍缺失} 条")

清洗记录.append("\n【二、准确性清洗】")

申请号列 = df["申请号/专利号"].astype(str)
非标准申请号 = (~申请号列.str.match(r'^\d{9,14}$')).sum()
清洗记录.append(f"非标准格式申请号: {非标准申请号} 条")

def 标准化日期(日期值):
    日期字符串 = str(日期值).strip()
    if 日期字符串 == "nan" or 日期字符串 == "":
        return None
    匹配 = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', 日期字符串)
    if 匹配:
        年, 月, 日 = int(匹配.group(1)), int(匹配.group(2)), int(匹配.group(3))
        if 1 <= 月 <= 12 and 1 <= 日 <= 31:
            return f"{年:04d}-{月:02d}-{日:02d}"
    return None

df["申请日_标准化"] = df["申请日"].apply(标准化日期)
日期无效数 = df["申请日_标准化"].isna().sum()
清洗记录.append(f"申请日格式标准化: 无效日期 {日期无效数} 条")

主分类号列 = df["主分类号"].astype(str)
IPC格式正确 = 主分类号列.str.match(r'^[A-Z]\d{2}[A-Z]?\d+/').sum()
清洗记录.append(f"主分类号IPC格式正确: {IPC格式正确} / {len(df)} 条")

清洗记录.append("\n【三、一致性清洗】")

企业去空格前 = df["企业"].nunique()
df["企业"] = df["企业"].astype(str).str.strip().str.replace(r'\s+', '', regex=True)
企业去空格后 = df["企业"].nunique()
清洗记录.append(f"企业名称去空格: {企业去空格前} -> {企业去空格后} 个")

df["发明名称"] = df["发明名称"].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
清洗记录.append("发明名称空格规范化")

def 统一法律状态(状态值):
    if pd.isna(状态值):
        return "未知"
    状态值 = str(状态值).strip()
    状态映射 = {
        "专利权维持": "专利权维持",
        "驳回失效": "驳回失效",
        "专利权终止": "专利权终止",
        "专利权有效": "专利权有效",
        "专利权无效": "专利权无效",
        "撤回": "撤回",
    }
    for 键, 值 in 状态映射.items():
        if 键 in 状态值:
            return 值
    return 状态值

法律状态统一前 = df["法律状态"].nunique()
df["法律状态"] = df["法律状态"].apply(统一法律状态)
法律状态统一后 = df["法律状态"].nunique()
清洗记录.append(f"法律状态统一: {法律状态统一前} -> {法律状态统一后} 个")

df["主分类号"] = df["主分类号"].astype(str).str.strip().str.upper()
df["副分类号"] = df["副分类号"].astype(str).str.strip().str.upper().replace("NAN", "")
清洗记录.append("分类号统一为大写")

清洗记录.append("\n【四、唯一性清洗】")

完全重复数 = df.duplicated().sum()
df = df.drop_duplicates()
清洗记录.append(f"删除完全重复行: {完全重复数} 条")

申请号重复总数 = df["申请号/专利号"].duplicated().sum()
清洗记录.append(f"申请号重复记录: {申请号重复总数} 条")

df["完整度"] = df.notna().sum(axis=1) / len(df.columns)
df = df.sort_values("完整度", ascending=False).drop_duplicates(subset=["申请号/专利号"], keep="first")
去重后行数 = len(df)
清洗记录.append(f"申请号去重后保留: {去重后行数} 条")
df = df.drop(columns=["完整度"])

清洗记录.append("\n【五、时效性清洗】")

当前年份 = datetime.now().year

def 提取年份(日期字符串):
    日期字符串 = str(日期字符串)
    匹配 = re.search(r"(\d{4})", 日期字符串)
    if 匹配:
        return int(匹配.group(1))
    return None

df["申请年份"] = df["申请日"].apply(提取年份)

未来年份数 = (df["申请年份"] > 当前年份 + 1).sum()
if 未来年份数 > 0:
    df = df[df["申请年份"] <= 当前年份 + 1]
    清洗记录.append(f"剔除未来年份: {未来年份数} 条")

过早年份数 = (df["申请年份"] < 1980).sum()
if 过早年份数 > 0:
    df = df[df["申请年份"] >= 1980]
    清洗记录.append(f"剔除过早年份: {过早年份数} 条")

年份范围 = f"{df['申请年份'].min()} - {df['申请年份'].max()}"
清洗记录.append(f"申请年份范围: {年份范围}")

清洗记录.append("\n【六、标准化清洗】")

字段映射 = {
    "申请号/专利号": "申请号",
    "申请人姓名或名称": "申请人",
    "国籍或总部所在地": "国籍",
    "代理机构名称": "代理机构",
    "第一代理人": "代理人",
}
df = df.rename(columns=字段映射)
清洗记录.append(f"字段重命名: {字段映射}")

字符串列 = df.select_dtypes(include=["object"]).columns
for 列 in 字符串列:
    df[列] = df[列].astype(str).str.strip().replace("nan", "")
清洗记录.append(f"字符串列规范化: {len(字符串列)} 列")

df["主分类号"] = df["主分类号"].str.replace(r'\s+', '', regex=True)
df["副分类号"] = df["副分类号"].str.replace(r'\s+', '', regex=True)
清洗记录.append("分类号去除内部空格")

df = df.sort_values(["企业", "申请年份", "申请号"]).reset_index(drop=True)
清洗记录.append("按企业、申请年份、申请号排序")

最终行数 = len(df)
清洗记录.append(f"\n【清洗汇总】")
清洗记录.append(f"原始数据: {原始行数} 条")
清洗记录.append(f"清洗后数据: {最终行数} 条")
清洗记录.append(f"删除记录: {原始行数 - 最终行数} 条 ({(原始行数-最终行数)/原始行数*100:.2f}%)")
清洗记录.append(f"保留列: {list(df.columns)}")

df.to_csv(清洗后文件路径, index=False, encoding="utf-8-sig")
清洗记录.append(f"\n清洗后数据已保存至: {清洗后文件路径}")

with open(清洗报告路径, "w", encoding="utf-8") as f:
    f.write("\n".join(清洗记录))

print("\n".join(清洗记录))

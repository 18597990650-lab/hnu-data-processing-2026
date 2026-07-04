def load_data(INPUT_FILE):
    import pandas as pd
    return pd.read_excel(INPUT_FILE)

def check_completeness(df):
    import pandas as pd
    results = {}
    results['null_counts'] = df.isnull().sum()
    pseudo_missing = {}
    for col in df.columns:
        if df[col].dtype == object:
            pm = df[col].isin(['-', '无', '暂无', 'null', 'NULL', 'None', '', ' ']).sum()
            if pm > 0:
                pseudo_missing[col] = pm
    results['pseudo_missing'] = pseudo_missing
    return results

def handle_completeness(df):
    mask = df['登记机关'].isnull() | df['登记机关'].isin(['-', '无', '暂无', ''])
    if mask.sum() > 0:
        df.loc[mask, '登记机关'] = df.loc[mask, '所属省份'].fillna('') + '市场监督管理局'
    mask = df['官网'].isnull() | df['官网'].isin(['-', '无', '暂无', ''])
    if mask.sum() > 0:
        df.loc[mask, '官网'] = '未披露'
    mask = df['国标行业小类'] == '-'
    if mask.sum() > 0:
        df.loc[mask, '国标行业小类'] = df.loc[mask, '国标行业中类']
    mask = df['英文名'].isnull() | df['英文名'].isin(['-', '无', '暂无', ''])
    if mask.sum() > 0:
        df.loc[mask, '英文名'] = '未披露'
    return df

def check_accuracy(df):
    import pandas as pd
    import re
    results = {}
    credit_code_pattern = r'^[0-9A-Z]{18}$'
    results['credit_code_error'] = df[~df['统一社会信用代码'].astype(str).str.match(credit_code_pattern, na=False)].shape[0]
    results['tax_id_mismatch'] = df[df['纳税人识别号'].astype(str) != df['统一社会信用代码'].astype(str)].shape[0]
    results['reg_cap_no_digit'] = df[~df['注册资本'].astype(str).str.contains(r'\d+', regex=True, na=False)].shape[0]
    results['est_date_error'] = pd.to_datetime(df['成立日期'], errors='coerce').isnull().sum()
    results['app_date_error'] = pd.to_datetime(df['核准日期'], errors='coerce').isnull().sum()
    results['score_not_int'] = df[~df['天眼评分'].astype(str).str.match(r'^\d+$', na=False)].shape[0]
    results['kc_not_int'] = df[~df['科创分'].astype(str).str.match(r'^\d+$', na=False)].shape[0]
    results['insured_not_int'] = df[~df['参保人数'].astype(str).str.match(r'^\d+$', na=False)].shape[0]
    results['revenue_no_digit'] = df[~df['最新年报营业收入'].astype(str).str.contains(r'\d', regex=True, na=False)].shape[0]
    return results

def handle_accuracy(df):
    import pandas as pd
    import re
    df['统一社会信用代码'] = df['统一社会信用代码'].astype(str).str.upper().str.strip()
    mismatch_mask = df['纳税人识别号'].astype(str) != df['统一社会信用代码']
    if mismatch_mask.sum() > 0:
        df.loc[mismatch_mask, '纳税人识别号'] = df.loc[mismatch_mask, '统一社会信用代码']
    def standardize_capital(val):
        if pd.isnull(val) or val in ['-', '无', '暂无', '']:
            return val
        s = str(val).strip()
        nums = re.findall(r'[\d.,]+', s)
        if not nums:
            return val
        num = nums[0].replace(',', '')
        if '万人民币' in s:
            return f"{num}万人民币"
        elif '万美元' in s:
            return f"{num}万美元"
        elif '亿元' in s:
            return f"{num}亿元"
        elif '万' in s:
            return f"{num}万人民币"
        else:
            return s
    df['注册资本'] = df['注册资本'].apply(standardize_capital)
    df['实缴资本'] = df['实缴资本'].apply(standardize_capital)
    df['成立日期'] = pd.to_datetime(df['成立日期'], errors='coerce')
    df['核准日期'] = pd.to_datetime(df['核准日期'], errors='coerce')
    df['天眼评分'] = pd.to_numeric(df['天眼评分'], errors='coerce').clip(0, 100)
    df['科创分'] = pd.to_numeric(df['科创分'], errors='coerce').clip(0, 100)
    df['参保人数'] = pd.to_numeric(df['参保人数'], errors='coerce')
    def standardize_revenue(val):
        if pd.isnull(val) or val in ['-', '无', '暂无', '']:
            return val
        s = str(val).strip()
        nums = re.findall(r'[\d.]+', s)
        if not nums:
            return val
        num = nums[0]
        if '亿' in s:
            return f"{num}亿"
        elif '万' in s:
            return f"{num}万"
        else:
            return s
    df['最新年报营业收入'] = df['最新年报营业收入'].apply(standardize_revenue)
    return df

def check_consistency(df):
    results = {}
    results['登记状态分布'] = df['登记状态'].value_counts().to_dict()
    results['企业类型种类数'] = df['企业(机构)类型'].nunique()
    results['纳税人资质分布'] = df['纳税人资质'].value_counts().to_dict()
    results['企业规模分布'] = df['企业规模'].value_counts().to_dict()
    results['科创等级分布'] = df['科创等级'].value_counts().to_dict()
    results['省份空城市非空'] = df[df['所属省份'].isnull() & df['所属城市'].notnull()].shape[0]
    results['营业期限格式分布'] = df['营业期限'].apply(lambda x: '无固定期限' if '无固定期限' in str(x) else ('至' if '至' in str(x) else '其他')).value_counts().to_dict()
    return results

def handle_consistency(df):
    status_map = {
        '存续（在营、开业、在册）': '存续', '在营（开业）': '存续',
        '在业': '存续', '开业': '存续',
        '吊销，未注销': '吊销', '吊销，已注销': '注销',
    }
    df['登记状态'] = df['登记状态'].astype(str).str.strip()
    for old, new in status_map.items():
        df['登记状态'] = df['登记状态'].replace(old, new)
    df.loc[df['登记状态'].str.startswith('注销'), '登记状态'] = '注销'
    df.loc[df['登记状态'].str.startswith('吊销'), '登记状态'] = '吊销'
    df['纳税人资质'] = df['纳税人资质'].astype(str).str.strip().replace('增值税一般纳税人', '一般纳税人')
    df['企业规模'] = df['企业规模'].astype(str).str.strip()
    df['科创等级'] = df['科创等级'].astype(str).str.strip()
    return df

def check_uniqueness(df):
    results = {}
    results['统一社会信用代码重复'] = df['统一社会信用代码'].duplicated().sum()
    results['上市公司全称重复'] = df['上市公司全称'].duplicated().sum()
    results['上市公司简称重复'] = df['上市公司简称'].duplicated().sum()
    results['注册号重复'] = df['注册号'].duplicated().sum()
    results['组织机构代码重复'] = df['组织机构代码'].duplicated().sum()
    return results

def handle_uniqueness(df):
    df = df.drop_duplicates(subset=['统一社会信用代码'], keep='first')
    return df

def check_timeliness(df):
    import pandas as pd
    import re
    from datetime import datetime
    results = {}
    current_date = datetime.now()
    results['成立日期晚于当前'] = (df['成立日期'] > current_date).sum()
    results['核准日期晚于当前'] = (df['核准日期'] > current_date).sum()
    valid_report_year = pd.to_numeric(df['最新年报年份'], errors='coerce')
    results['年报年份过旧'] = (valid_report_year < (current_date.year - 3)).sum()
    def check_expired(term):
        if pd.isnull(term) or '无固定期限' in str(term) or '9999' in str(term):
            return False
        match = re.search(r'\d{4}-\d{2}-\d{2}', str(term))
        if match:
            end_date = pd.to_datetime(match.group(), errors='coerce')
            if pd.notnull(end_date):
                return end_date < current_date
        return False
    results['营业期限已过期'] = df['营业期限'].apply(check_expired).sum()
    return results

def handle_timeliness(df):
    import pandas as pd
    from datetime import datetime
    current_date = datetime.now()
    future_est = df['成立日期'] > current_date
    if future_est.sum() > 0:
        df.loc[future_est, '成立日期'] = pd.NaT
    future_app = df['核准日期'] > current_date
    if future_app.sum() > 0:
        df.loc[future_app, '核准日期'] = pd.NaT
    valid_report_year = pd.to_numeric(df['最新年报年份'], errors='coerce')
    old_report = valid_report_year < (current_date.year - 3)
    if old_report.sum() > 0:
        df.loc[old_report, '最新年报年份'] = df.loc[old_report, '最新年报年份'].astype(str) + '(需更新)'
    import re
    def check_expired(term):
        if pd.isnull(term) or '无固定期限' in str(term) or '9999' in str(term):
            return False
        match = re.search(r'\d{4}-\d{2}-\d{2}', str(term))
        if match:
            end_date = pd.to_datetime(match.group(), errors='coerce')
            if pd.notnull(end_date):
                return end_date < current_date
        return False
    expired = df['营业期限'].apply(check_expired)
    if expired.sum() > 0:
        df.loc[expired, '登记状态'] = '已过期'
    return df

def check_standardization(df):
    results = {}
    phone_pattern = r'^\d{3,4}-\d{7,8}$|^1[3-9]\d{9}$|^\d{7,8}$'
    results['电话格式不规范'] = df[~df['电话'].astype(str).str.match(phone_pattern, na=False)].shape[0]
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    results['邮箱格式不规范'] = df[~df['邮箱'].astype(str).str.match(email_pattern, na=False)].shape[0]
    url_pattern = r'^https?://'
    results['官网格式不规范'] = df[(~df['官网'].astype(str).str.match(url_pattern, na=False)) & (df['官网'] != '未披露')].shape[0]
    results['地址不含省市区县'] = df[~df['企业地址'].astype(str).str.contains(r'省|市|区|县', regex=True, na=False)].shape[0]
    return results

def handle_standardization(df):
    df['电话'] = df['电话'].astype(str).str.strip().str.replace(' ', '').str.replace('；', ';')
    df['更多电话'] = df['更多电话'].astype(str).str.strip().str.replace(' ', '').str.replace('；', ';')
    df['邮箱'] = df['邮箱'].astype(str).str.lower().str.strip()
    df['更多邮箱'] = df['更多邮箱'].astype(str).str.lower().str.strip().str.replace(' ', '').str.replace('；', ';')
    def normalize_url(url):
        import pandas as pd
        if pd.isnull(url) or url in ['未披露', '-', '无', '']:
            return url
        s = str(url).strip()
        if not s.startswith('http://') and not s.startswith('https://'):
            s = 'http://' + s
        return s
    df['官网'] = df['官网'].apply(normalize_url)
    df['企业地址'] = df['企业地址'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    df['通信地址'] = df['通信地址'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    df['法定代表人'] = df['法定代表人'].astype(str).str.strip()
    df['经营范围'] = df['经营范围'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    df['企业简介'] = df['企业简介'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    df['英文名'] = df['英文名'].astype(str).str.strip()
    return df

def save_data(df, OUTPUT_FILE):
    df.to_excel(OUTPUT_FILE, index=False)

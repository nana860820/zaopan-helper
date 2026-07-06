"""
早盘助手 - 云端版（GitHub Actions 用）
每天 9:26 / 11:31 / 15:01 自动运行，抓取 4 项指标写入云端 Supabase

特性：
  - 重试机制：每个接口最多重试 3 次，间隔 30 秒
  - 新股过滤：排除上市不足 5 个交易日的股票
  - 20cm/30cm/5cm 自动排除
  - 节假日自动跳过
"""
import requests
import json
import re
import time
from datetime import datetime, date, timedelta


# ============================================================
# 配置
# ============================================================
SUPABASE_URL = "https://au7f2dhyaiv4.meoo.zone/sb-api/rest/v1/daily_data"
SUPABASE_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJhbm9uIiwiaWF0IjoxNzgyODk1Mzc1LCJleHAiOjEzMjkzNTM1Mzc1fQ.LsWoyeGCwcQxNxTRLudvjBHWyk4lfHbQbDpN0-NV020"

MAX_RETRIES = 3
RETRY_DELAY = 30

# 时间窗口（UTC）：北京时间 9:26 / 11:31 / 15:01
TIME_SLOTS = {
    "09:26": (1 * 60 + 26, 1 * 60 + 33),    # UTC 01:26-01:33
    "11:31": (3 * 60 + 31, 3 * 60 + 37),    # UTC 03:31-03:37
    "15:01": (7 * 60 + 1, 7 * 60 + 7),      # UTC 07:01-07:07
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


# ============================================================
# 工具函数
# ============================================================
def retry_fetch(fn, name):
    """带重试的数据抓取，最多重试 MAX_RETRIES 次"""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = fn()
            if result != "抓取失败" and result != ("抓取失败", "抓取失败"):
                return result
            if attempt < MAX_RETRIES:
                print(f"  [{name}] 第 {attempt} 次返回空，{RETRY_DELAY}秒后重试...")
                time.sleep(RETRY_DELAY)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                print(f"  [{name}] 第 {attempt} 次失败({e})，{RETRY_DELAY}秒后重试...")
                time.sleep(RETRY_DELAY)

    print(f"  [{name}] {MAX_RETRIES} 次重试均失败: {last_error}")
    return "抓取失败"


def is_trading_day(check_date=None):
    if check_date is None:
        check_date = date.today()
    if check_date.weekday() >= 5:
        return False
    try:
        from chinese_calendar import is_workday
        return is_workday(check_date)
    except ImportError:
        pass
    holidays = {
        date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
        date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
        date(2026, 2, 19), date(2026, 2, 20), date(2026, 2, 21), date(2026, 2, 22),
        date(2026, 4, 5), date(2026, 4, 6),
        date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3),
        date(2026, 5, 4), date(2026, 5, 5),
        date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21),
        date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27),
        date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3),
        date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 6),
        date(2026, 10, 7), date(2026, 10, 8),
    }
    return check_date not in holidays


# ============================================================
# 指标1：总成交额（新浪财经）
# ============================================================
def get_total_turnover():
    total = 0
    codes = ["s_sh000001", "s_sz399001"]
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    headers = {"Referer": "https://finance.sina.com.cn/"}
    r = requests.get(url, headers=headers, timeout=10)
    r.encoding = "gbk"
    for line in r.text.strip().split("\n"):
        if not line.strip():
            continue
        match = re.search(r'"([^"]*)"', line)
        if match:
            parts = match.group(1).split(",")
            if len(parts) >= 6:
                total += float(parts[-1]) / 10000
    return round(total, 2) if total > 0 else "抓取失败"


# ============================================================
# 指标2：上证上涨家数
# ============================================================
def get_sh_rising_count():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": "1", "pz": "1", "po": "0", "np": "1", "fltt": "2", "invt": "2",
              "fs": "m:1+t:2,m:0+t:6,m:0+t:80", "fields": "f3", "fid": "f3"}
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    data = r.json()
    if data.get("data"):
        return data["data"].get("total", "抓取失败")
    return "抓取失败"


# ============================================================
# 新股过滤
# ============================================================
def is_new_stock(code):
    """
    判断是否为上市不足 5 个交易日的新股
    通过东方财富个股接口获取上市日期
    """
    try:
        url = f"https://push2.eastmoney.com/api/qt/stock/basic/get"
        params = {"fields": "f12,f26", "secid": f"1.{code}" if code.startswith("60") else f"0.{code}"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=5)
        data = r.json()
        if data.get("data"):
            listing_date_str = data["data"].get("f26", "")
            if listing_date_str:
                listing_date = datetime.strptime(str(listing_date_str)[:10], "%Y-%m-%d").date()
                trading_days = count_trading_days(listing_date, date.today())
                return trading_days < 5
    except Exception:
        pass
    return False


def count_trading_days(start, end):
    """计算两个日期之间的交易日天数"""
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


# ============================================================
# 过滤函数：主板 10cm
# ============================================================
def is_main_board_10cm(code, name):
    code_str = str(code)
    name_str = str(name).upper() if name else ""
    if code_str.startswith("8"):
        return False
    if code_str.startswith("300") or code_str.startswith("301"):
        return False
    if code_str.startswith("688"):
        return False
    if "ST" in name_str:
        return False
    if code_str.startswith("60") or code_str.startswith("00"):
        return True
    return False


# ============================================================
# 指标3 & 4：涨停数 + 炸板数（含新股过滤 + 20%二次校验）
# ============================================================
def get_limit_up_and_broken():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": "1", "pz": "200", "po": "1", "np": "1", "fltt": "2", "invt": "2",
              "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
              "fields": "f2,f3,f12,f14,f8", "fid": "f3"}
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    data = r.json()
    limit_up, broken = 0, 0
    if data.get("data") and data["data"].get("diff"):
        for stock in data["data"]["diff"]:
            code = stock.get("f12", "")
            name = stock.get("f14", "")
            pct = stock.get("f3", 0)
            if pct == "-" or pct is None:
                continue
            pct = float(pct)

            # 第一层：代码前缀过滤（主板 10cm）
            if not is_main_board_10cm(code, name):
                continue

            # 第二层：20% 二次校验（排除涨 9.5%-10.5% 但实际是 20cm 的票）
            if pct >= 19.0:
                continue

            # 第三层：新股过滤（上市不足 5 个交易日）
            if is_new_stock(code):
                continue

            if pct >= 9.5:
                limit_up += 1
            elif pct >= 3.0:
                broken += 1

    return limit_up, broken


# ============================================================
# 云端写入
# ============================================================
def write_to_cloud(time_point, turnover, rising, limit_up, broken):
    today_str = date.today().strftime("%Y-%m-%d")
    cloud_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    row = {
        "trade_date": today_str,
        "time_point": time_point,
        "total_turnover": str(turnover),
        "rising_count": str(rising),
        "limit_up_count": str(limit_up),
        "broken_count": str(broken) if time_point != "09:26" else "—",
    }
    try:
        check = requests.get(SUPABASE_URL, headers=cloud_headers,
                             params={"trade_date": f"eq.{today_str}", "time_point": f"eq.{time_point}"}, timeout=10)
        existing = check.json() if check.status_code == 200 else []
        if existing:
            rid = existing[0]["id"]
            r = requests.patch(f"{SUPABASE_URL}?id=eq.{rid}", headers=cloud_headers, json=row, timeout=10)
        else:
            r = requests.post(SUPABASE_URL, headers=cloud_headers, json=row, timeout=10)
        return r.status_code in (200, 201, 204)
    except Exception as e:
        print(f"云端写入失败: {e}")
        return False


# ============================================================
# 主程序
# ============================================================
def main():
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute

    # 匹配当前时间窗口
    time_point = None
    for tp, (start, end) in TIME_SLOTS.items():
        if start <= current_minutes <= end:
            time_point = tp
            break

    if time_point is None:
        print(f"[{now.strftime('%H:%M')} UTC] 不在预设时间窗口内，跳过")
        return

    print(f"[{now.strftime('%H:%M')} UTC] 早盘助手启动，时间点：{time_point} (北京时间)")

    if not is_trading_day():
        print("[跳过] 今天不是交易日")
        return

    print(f"[1/4] 抓取总成交额...")
    turnover = retry_fetch(get_total_turnover, "总成交额")
    print(f"      总成交额：{turnover}")

    print(f"[2/4] 抓取上证上涨数...")
    rising = retry_fetch(get_sh_rising_count, "上证上涨数")
    print(f"      上证上涨数：{rising}")

    print(f"[3/4] 抓取涨停/炸板数据（含新股过滤 + 20%校验）...")
    limit_up, broken = retry_fetch(get_limit_up_and_broken, "涨停炸板")
    print(f"      涨停：{limit_up}，炸板：{broken}")

    print(f"[4/4] 写入云端数据库...")
    if write_to_cloud(time_point, turnover, rising, limit_up, broken):
        print(f"[完成] 数据已更新 → https://au7f2dhyaiv4.meoo.zone")
    else:
        print(f"[失败] 云端写入出错")

    print(f"{'='*40}")
    print(f"  时间点：{time_point}")
    print(f"  总成交额：{turnover}")
    print(f"  上证上涨数：{rising}")
    print(f"  10cm涨停数：{limit_up}")
    print(f"  10cm炸板数：{broken}")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()

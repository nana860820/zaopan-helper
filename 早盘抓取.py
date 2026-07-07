"""
早盘助手 v2 — 云端版（GitHub Actions）
新增：昨日对比 + 市场情绪评分
"""
import requests
import json
import re
import time
from datetime import datetime, date, timedelta

SUPABASE_URL = "https://au7f2dhyaiv4.meoo.zone/sb-api/rest/v1/daily_data"
SUPABASE_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJhbm9uIiwiaWF0IjoxNzgyODk1Mzc1LCJleHAiOjEzMjkzNTM1Mzc1fQ.LsWoyeGCwcQxNxTRLudvjBHWyk4lfHbQbDpN0-NV020"
MAX_RETRIES = 3
RETRY_DELAY = 30

TIME_SLOTS = {
    "09:20": (1*60+20, 1*60+25),   # 09:20-09:25 集合竞价
    "11:30": (3*60+30, 3*60+59),   # 11:30-11:59 上午收盘
    "15:00": (7*60+0,  7*60+59),   # 15:00-15:59 全天收盘
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
}


def retry_fetch(fn, name):
    for attempt in range(1, MAX_RETRIES+1):
        try:
            result = fn()
            if result != "fail" and result != ("fail","fail"):
                return result
            if attempt < MAX_RETRIES:
                print(f"  [{name}] retry {attempt}/{MAX_RETRIES}...")
                time.sleep(RETRY_DELAY)
        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"  [{name}] error, retry {attempt}/{MAX_RETRIES}...")
                time.sleep(RETRY_DELAY)
    print(f"  [{name}] all retries failed")
    return "fail"


def prev_trading_day(check_date=None):
    """获取上一个交易日"""
    if check_date is None:
        check_date = date.today()
    d = check_date - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def is_trading_day(check_date=None):
    if check_date is None:
        check_date = date.today()
    if check_date.weekday() >= 5:
        return False
    holidays = {
        date(2026,1,1),date(2026,1,2),date(2026,1,3),
        date(2026,2,16),date(2026,2,17),date(2026,2,18),date(2026,2,19),date(2026,2,20),date(2026,2,21),date(2026,2,22),
        date(2026,4,5),date(2026,4,6),
        date(2026,5,1),date(2026,5,2),date(2026,5,3),date(2026,5,4),date(2026,5,5),
        date(2026,6,19),date(2026,6,20),date(2026,6,21),
        date(2026,9,25),date(2026,9,26),date(2026,9,27),
        date(2026,10,1),date(2026,10,2),date(2026,10,3),date(2026,10,4),date(2026,10,5),date(2026,10,6),date(2026,10,7),date(2026,10,8),
    }
    return check_date not in holidays


def get_total_turnover():
    total = 0
    url = "https://hq.sinajs.cn/list=s_sh000001,s_sz399001"
    r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn/"}, timeout=10)
    r.encoding = "gbk"
    for line in r.text.strip().split("\n"):
        if not line.strip(): continue
        match = re.search(r'"([^"]*)"', line)
        if match:
            parts = match.group(1).split(",")
            if len(parts) >= 6:
                total += float(parts[-1]) / 10000
    return round(total, 2) if total > 0 else "fail"


def get_sh_rising_count():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn":"1","pz":"1","po":"0","np":"1","fltt":"2","invt":"2",
        "fs":"m:1+t:2",           # 仅上证A股
        "fields":"f3","fid":"f3",
        "f3":"0.01,20.0"          # 仅上涨的（涨幅>0）
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    data = r.json()
    return data["data"].get("total","fail") if data.get("data") else "fail"


def is_main_board_10cm(code, name):
    c = str(code)
    n = str(name).upper() if name else ""
    if c.startswith("8"): return False
    if c.startswith("300") or c.startswith("301"): return False
    if c.startswith("688"): return False
    if "ST" in n: return False
    return c.startswith("60") or c.startswith("00")


def is_new_stock(code):
    try:
        prefix = "1" if str(code).startswith("60") else "0"
        r = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/basic/get",
            params={"fields":"f12,f26","secid":f"{prefix}.{code}"},
            headers=HEADERS, timeout=5
        )
        data = r.json()
        if data.get("data") and data["data"].get("f26"):
            ld = datetime.strptime(str(data["data"]["f26"])[:10],"%Y-%m-%d").date()
            count = 0
            d = ld
            while d <= date.today():
                if d.weekday() < 5: count += 1
                d += timedelta(days=1)
            return count < 5
    except: pass
    return False


def get_limit_up_and_broken():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn":"1","pz":"200","po":"1","np":"1","fltt":"2","invt":"2",
        "fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields":"f2,f3,f12,f14,f8","fid":"f3"
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    data = r.json()
    lu, br = 0, 0
    if data.get("data") and data["data"].get("diff"):
        for s in data["data"]["diff"]:
            code = s.get("f12","")
            name = s.get("f14","")
            pct = s.get("f3",0)
            if pct == "-" or pct is None: continue
            pct = float(pct)
            if not is_main_board_10cm(code, name): continue
            if pct >= 19.0: continue
            if is_new_stock(code): continue
            if pct >= 9.5: lu += 1
            elif pct >= 3.0: br += 1
    return lu, br


def calc_pct(new_val, old_val):
    """计算百分比变化"""
    try:
        n = float(new_val)
        o = float(old_val)
        if o and o > 0:
            return round((n - o) / o * 100, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return None


def calc_sentiment(turnover_change_pct, rising_count, limit_up, broken):
    """
    市场情绪评分 (1-10)
    加权公式：
      - 成交额变化趋势 (0-3分)
      - 上涨家数占比  (0-3分)
      - 涨停强度      (0-2分)
      - 封板质量      (0-2分)
    """
    score = 5.0  # 中性起点

    # 1. 成交额趋势 (权重3)
    if turnover_change_pct is not None:
        if turnover_change_pct > 20: score += 3
        elif turnover_change_pct > 10: score += 2
        elif turnover_change_pct > 0: score += 1
        elif turnover_change_pct > -10: score -= 0.5
        elif turnover_change_pct > -20: score -= 1
        else: score -= 2

    # 2. 上涨家数 (权重3) — 上证约2200只票
    try:
        r = float(rising_count)
        ratio = r / 2200.0
        if ratio > 0.75: score += 3
        elif ratio > 0.6: score += 2
        elif ratio > 0.5: score += 1
        elif ratio > 0.35: score -= 0.5
        elif ratio > 0.25: score -= 1
        else: score -= 2
    except (ValueError, TypeError):
        pass

    # 3. 涨停强度 (权重2)
    try:
        lu = float(limit_up)
        if lu > 80: score += 2
        elif lu > 50: score += 1.5
        elif lu > 30: score += 1
        elif lu > 15: score += 0.5
        elif lu < 10: score -= 0.5
    except (ValueError, TypeError):
        pass

    # 4. 封板质量 = 涨停/(涨停+炸板)  (权重2)
    try:
        lu_f = float(limit_up)
        br_f = float(broken)
        total_lu = lu_f + br_f
        if total_lu > 0:
            seal_rate = lu_f / total_lu
            if seal_rate > 0.9: score += 2
            elif seal_rate > 0.8: score += 1.5
            elif seal_rate > 0.7: score += 1
            elif seal_rate > 0.6: score += 0.5
            elif seal_rate < 0.5: score -= 1
    except (ValueError, TypeError, ZeroDivisionError):
        pass

    return max(1, min(10, round(score)))


def query_yesterday(tp):
    """从 Supabase 查询昨日同期数据"""
    prev = prev_trading_day()
    prev_str = prev.strftime("%Y-%m-%d")
    h = {"apikey":SUPABASE_KEY, "Authorization":f"Bearer {SUPABASE_KEY}"}
    try:
        r = requests.get(SUPABASE_URL, headers=h,
            params={"trade_date":f"eq.{prev_str}","time_point":f"eq.{tp}"}, timeout=10)
        rows = r.json()
        if rows:
            return rows[0]
    except Exception as e:
        print(f"  Query yesterday failed: {e}")
    return None


def write_to_cloud(time_point, data):
    today_str = date.today().strftime("%Y-%m-%d")
    h = {
        "apikey":SUPABASE_KEY,
        "Authorization":f"Bearer {SUPABASE_KEY}",
        "Content-Type":"application/json",
        "Prefer":"resolution=merge-duplicates"
    }
    row = {
        "trade_date": today_str,
        "time_point": time_point,
        "total_turnover": str(data["turnover"]),
        "rising_count": str(data["rising"]),
        "limit_up_count": str(data["limit_up"]),
        "broken_count": str(data["broken"]) if time_point != "09:20" else "N/A",
        "sentiment_score": data.get("sentiment", None),
        "turnover_change": str(data.get("turnover_change","")) if data.get("turnover_change") is not None else None,
        "rising_change": str(data.get("rising_change","")) if data.get("rising_change") is not None else None,
    }
    try:
        check = requests.get(SUPABASE_URL, headers=h,
            params={"trade_date":f"eq.{today_str}","time_point":f"eq.{time_point}"}, timeout=10)
        existing = check.json() if check.status_code==200 else []
        if existing:
            resp = requests.patch(f"{SUPABASE_URL}?id=eq.{existing[0]['id']}", headers=h, json=row, timeout=10)
        else:
            resp = requests.post(SUPABASE_URL, headers=h, json=row, timeout=10)
        return resp.status_code in (200,201,204)
    except Exception as e:
        print(f"Write failed: {e}")
        return False


def main():
    now = datetime.now()
    cm = now.hour*60 + now.minute
    tp = None
    for t, (s, e) in TIME_SLOTS.items():
        if s <= cm <= e:
            tp = t
            break
    if not tp:
        print(f"[{now.strftime('%H:%M')}] Not in time window, skip")
        return
    print(f"Time: {tp} Beijing")
    if not is_trading_day():
        print("Not a trading day, skip")
        return

    print("[1/4] Turnover...")
    turnover = retry_fetch(get_total_turnover, "Turnover")
    print(f"  {turnover}")

    print("[2/4] Rising...")
    rising = retry_fetch(get_sh_rising_count, "Rising")
    print(f"  {rising}")

    print("[3/4] Limit-up/Broken...")
    lu, br = retry_fetch(get_limit_up_and_broken, "LimitUp")
    print(f"  LU={lu} BR={br}")

    # 查询昨日同期数据
    print("[4/5] Yesterday comparison...")
    yesterday = query_yesterday(tp)
    t_change = None
    r_change = None
    if yesterday:
        t_change = calc_pct(turnover, yesterday.get("total_turnover"))
        r_change = calc_pct(rising, yesterday.get("rising_count"))
        print(f"  Turnover change: {t_change}%")
        print(f"  Rising change: {r_change}%")
    else:
        print("  No yesterday data")

    # 计算情绪评分
    print("[5/5] Sentiment score...")
    sentiment = calc_sentiment(t_change, rising, lu, br)
    print(f"  Score: {sentiment}/10")

    # 写入云端
    print("[Write] Writing to cloud...")
    data = {
        "turnover": turnover,
        "rising": rising,
        "limit_up": lu,
        "broken": br,
        "sentiment": sentiment,
        "turnover_change": t_change,
        "rising_change": r_change,
    }
    ok = write_to_cloud(tp, data)
    print(f"  {'OK' if ok else 'FAIL'}")
    print(f"{'='*50}")
    print(f"  {tp} | T={turnover}({t_change}%) | R={rising}({r_change}%) | LU={lu} BR={br} | {sentiment}/10")


if __name__ == "__main__":
    main()

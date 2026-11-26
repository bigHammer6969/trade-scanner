# 收盤後跑：抓大盤與個股歷史，算大盤燈號（歐尼爾出貨日／追蹤日）、個股前高與均量、收盤訊號。
import json, os, time, datetime as dt
import pandas as pd
from common import *

DATA = "data"
KEEP_DAYS = 30
os.makedirs(DATA, exist_ok=True)


def market_history(months=6):
    rows, today = [], now_tw().date()
    for i in range(months, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            y, m = y - 1, m + 12
        js = get_json("https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK",
                      {"date": f"{y}{m:02d}01", "response": "json"})
        time.sleep(SLEEP)
        if not js or js.get("stat") != "OK":
            continue
        f, d = find_table(js, ["日期", "成交金額", "發行量加權股價指數"])
        if not f:
            continue
        for r in d:
            rows.append({"date": roc_to_date(r[f.index("日期")]).isoformat(),
                         "close": num(r[f.index("發行量加權股價指數")]),
                         "amt": num(r[f.index("成交金額")])})
    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date").reset_index(drop=True)


def market_light(m, start="green"):
    """歐尼爾：綠燈時數出貨日，6 個轉紅燈；紅燈時從新低起數，第 4 天起漲 1.5% 以上且量增＝追蹤日，轉綠燈。"""
    mode, green_start, dist, low, rally, notes = start, 0, [], None, 0, []
    for i in range(len(m)):
        c = m.close[i]
        pct = (c / m.close[i - 1] - 1) * 100 if i else None
        vol_up = bool(m.amt[i] > m.amt[i - 1]) if i else None
        tag = []
        if mode == "green":
            if pct is not None and pct <= -0.2 and vol_up:
                dist.append(i); tag.append("出貨日")
            if len([j for j in dist if j > i - 25 and j >= green_start]) >= 6:
                mode, low, rally = "red", c, 0; tag.append("轉紅燈")
        else:
            if low is None or c < low:
                low, rally = c, 0; tag.append("新低")
            elif rally == 0:
                if pct is not None and pct > 0:
                    rally = 1; tag.append("反彈第1天")
            else:
                rally += 1; tag.append(f"反彈第{rally}天")
            if rally >= 4 and pct is not None and pct >= 1.5 and vol_up:
                tag += ["追蹤日", "轉綠燈"]
                mode, green_start, dist, rally, low = "green", i, [], 0, None
        notes.append({"date": m.date[i], "close": round(c, 2), "amt": round(m.amt[i] / 1e8), "pct": None if pct is None else round(pct, 2),
                      "vol_up": vol_up, "tags": tag})
    n = len(m) - 1
    dcount = len([j for j in dist if j > n - 25 and j >= green_start]) if mode == "green" else None
    early = mode == "green" and green_start > 0 and n - green_start < 10
    mult = 0 if mode == "red" else 0.5 if (dcount >= 4 or early) else 1
    return {"mode": mode, "dist": dcount, "rally": rally if mode == "red" else None, "mult": mult,
            "days": notes[-30:]}


def stocks_day(d):
    js = get_json("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
                  {"date": d.replace("-", ""), "type": "ALLBUT0999", "response": "json"})
    time.sleep(SLEEP)
    if not js or js.get("stat") != "OK":
        return None
    f, data = find_table(js, ["證券代號", "收盤價", "最高價", "最低價", "成交金額"])
    if not f:
        return None
    ix = {k: f.index(k) for k in ["證券代號", "證券名稱", "成交股數", "成交金額", "最高價", "最低價", "收盤價"]}
    out = []
    for r in data:
        code = str(r[ix["證券代號"]]).strip()
        if len(code) != 4 or not code.isdigit() or code.startswith("0"):
            continue
        out.append({"date": d, "mkt": "tse", "code": code, "name": str(r[ix["證券名稱"]]).strip(),
                    "vol": num(r[ix["成交股數"]]) / 1000, "amt": num(r[ix["成交金額"]]),
                    "high": num(r[ix["最高價"]]), "low": num(r[ix["最低價"]]), "close": num(r[ix["收盤價"]])})
    return pd.DataFrame(out)


def otc_day(d):
    """上櫃：櫃買中心每日收盤行情。"""
    js = get_json("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes",
                  {"date": d.replace("-", "/"), "type": "EW", "response": "json"})
    time.sleep(SLEEP)
    if not js or str(js.get("stat", "")).lower() != "ok":
        return None
    f, data = find_table(js, ["代號", "名稱", "收盤", "最高", "最低", "成交股數", "成交金額(元)"])
    if not f:
        return None
    ix = {k: f.index(k) for k in ["代號", "名稱", "成交股數", "成交金額(元)", "最高", "最低", "收盤"]}
    out = []
    for r in data:
        code = str(r[ix["代號"]]).strip()
        if len(code) != 4 or not code.isdigit() or code.startswith("0"):
            continue
        out.append({"date": d, "mkt": "otc", "code": code, "name": str(r[ix["名稱"]]).strip(),
                    "vol": num(r[ix["成交股數"]]) / 1000, "amt": num(r[ix["成交金額(元)"]]),
                    "high": num(r[ix["最高"]]), "low": num(r[ix["最低"]]), "close": num(r[ix["收盤"]])})
    return pd.DataFrame(out)


print("抓大盤…")
m = market_history()
if m.empty:
    raise SystemExit("抓不到大盤資料，可能被證交所擋，或今天資料還沒出來。")
mk = market_light(m)
trade_days = list(m.date.iloc[-KEEP_DAYS:])

hist_path = f"{DATA}/history.csv"
hist = pd.read_csv(hist_path, dtype={"code": str}) if os.path.exists(hist_path) else pd.DataFrame()
if len(hist) and "mkt" not in hist.columns:
    hist["mkt"] = "tse"  # 舊資料只有上市
have = set(zip(hist.date, hist.mkt)) if len(hist) else set()
for d in trade_days:
    for mkt, fetch in (("tse", stocks_day), ("otc", otc_day)):
        if (d, mkt) in have:
            continue
        print("抓個股", mkt, d)
        df = fetch(d)
        if df is not None and len(df):
            hist = pd.concat([hist, df], ignore_index=True)
hist = hist[hist.date.isin(trade_days)].sort_values(["code", "date"])
hist.to_csv(hist_path, index=False)

asof = hist.date.max()
stats, eod = {}, []
for code, g in hist.groupby("code"):
    g = g.dropna(subset=["close", "high", "low"]).sort_values("date")
    if len(g) < 22 or g.date.iloc[-1] != asof:
        continue
    c = g.close.iloc[-1]
    tr = pd.concat([g.high - g.low, (g.high - g.close.shift()).abs(), (g.low - g.close.shift()).abs()], axis=1).max(axis=1)
    atr_pct = tr.iloc[-20:].mean() / c * 100
    amt20 = g.amt.iloc[-20:].mean()
    if amt20 < 3e8 or atr_pct < 3:
        continue
    name = g["name"].iloc[-1]
    mkt = g["mkt"].iloc[-1]
    chart = {"mkt": mkt, "vols": [0 if v != v else round(v) for v in g.vol.iloc[-20:]],
             "closes": [round(float(x), 2) for x in g.close.iloc[-20:]]}
    # 給明天盤中用：前 20 天最高收盤＝到今天為止的 20 天
    H_next = g.close.iloc[-20:].max()
    if c >= H_next / 1.1:
        stats[code] = {"name": name, "H": round(H_next, 2), "v5": round(g.vol.iloc[-5:].mean(), 1),
                       "sum19": round(g.close.iloc[-19:].sum(), 4), "prev": c,
                       "amt20": round(amt20 / 1e8, 1), "atr": round(atr_pct, 1), **chart}
    # 今天收盤的訊號（收盤版本）
    H = g.close.iloc[-21:-1].max()
    prev = g.close.iloc[-2]
    vol_r = g.vol.iloc[-1] / g.vol.iloc[-6:-1].mean()
    dev = (c / g.close.iloc[-20:].mean() - 1) * 100
    limit_up = c >= floor_tick(prev * 1.1)
    if c > H and vol_r >= 1.5 and dev <= 15 and not limit_up:
        p = plan(c, H)
        if p["size"] > 0:
            eod.append({"code": code, "name": name, "price": c, "H": round(H, 2), "vol_r": round(vol_r, 2),
                        "dev": round(dev, 1), "atr": round(atr_pct, 1), "amt20": round(amt20 / 1e8, 1), **chart, **p})

stamp = now_tw().strftime("%Y-%m-%d %H:%M")
json.dump({"updated": stamp, "asof": asof, **mk}, open(f"{DATA}/market.json", "w"), ensure_ascii=False)
json.dump({"asof": asof, "stocks": stats}, open(f"{DATA}/stats.json", "w"), ensure_ascii=False)
json.dump({"updated": stamp, "asof": asof, "signals": sorted(eod, key=lambda x: -x["vol_r"])},
          open(f"{DATA}/eod.json", "w"), ensure_ascii=False)
n_otc = sum(1 for v in stats.values() if v["mkt"] == "otc")
print(f"完成：{asof}，大盤 {mk['mode']}，候選 {len(stats)} 檔（上櫃 {n_otc}），收盤訊號 {len(eod)} 檔")

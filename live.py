# 盤中每 5 分鐘跑：只看昨天收盤後挑出的候選股，比對即時價和前高。
import json, os, datetime as dt, requests
from common import *

DATA = "data"
t = now_tw()
if t.weekday() >= 5 or not (dt.time(9, 0) <= t.time() <= dt.time(13, 35)):
    raise SystemExit("非盤中時間，不跑。")

stats = json.load(open(f"{DATA}/stats.json"))["stocks"]
market = json.load(open(f"{DATA}/market.json")) if os.path.exists(f"{DATA}/market.json") else {}
mult = market.get("mult", 1)
codes = list(stats)

s = requests.Session()
try:
    s.get("https://mis.twse.com.tw/stock/index.jsp", headers=HEADERS, timeout=20)
except Exception as e:
    print("即時報價網站連不上：", e)

quotes = {}
for i in range(0, len(codes), 40):
    batch = codes[i:i + 40]
    ex = "|".join(f"{stats[c].get('mkt', 'tse')}_{c}.tw" for c in batch)
    js = get_json("https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                  {"ex_ch": ex, "json": "1", "delay": "0"}, session=s)
    for q in (js or {}).get("msgArray", []):
        quotes[q.get("c")] = q

elapsed = max(1, min(270, (t.hour * 60 + t.minute) - 9 * 60))
rows = []
for code, st in stats.items():
    q = quotes.get(code)
    if not q:
        continue
    p = num(q.get("z"))
    if p != p:  # 沒有成交價時用買一價
        p = num(str(q.get("b", "")).split("_")[0])
    if p != p or p <= 0:
        continue
    v = num(q.get("v"))
    H = st["H"]
    vol_now = v / st["v5"] if st["v5"] else 0
    vol_pace = vol_now / (elapsed / 270)
    ma20 = (st["sum19"] + p) / 20
    dev = (p / ma20 - 1) * 100
    limit_up = p >= num(q.get("u", "inf"))
    above = p > H
    if above and vol_now >= 1.5 and dev <= 15 and not limit_up and (p / H - 1) * 100 <= 6:
        status, rank = "條件到了", 0
    elif above:
        why = "漲停" if limit_up else "乖離太大" if dev > 15 else "離前高太遠" if (p / H - 1) * 100 > 6 else "量還不夠"
        status, rank = f"價過前高，{why}", 1
    elif p >= H * 0.98:
        status, rank = "離前高 2% 內", 2
    else:
        continue
    pl = plan(p, H)
    rows.append({"code": code, "name": st["name"], "mkt": st.get("mkt", "tse"), "price": p, "H": H, "status": status, "rank": rank,
                 "vol_now": round(vol_now, 2), "vol_pace": round(vol_pace, 2), "dev": round(dev, 1),
                 "atr": st["atr"], "amt20": st["amt20"], **pl, "size_final": pl["size"] * mult})

rows.sort(key=lambda r: (r["rank"], -r["vol_pace"]))
json.dump({"updated": t.strftime("%Y-%m-%d %H:%M"), "quotes": len(quotes), "candidates": len(stats),
           "rows": rows}, open(f"{DATA}/live.json", "w"), ensure_ascii=False)
print(f"{t:%H:%M} 拿到 {len(quotes)}/{len(stats)} 檔報價，列出 {len(rows)} 檔")
if not quotes:
    raise SystemExit("一檔報價都沒拿到，可能被即時報價網站擋了。")

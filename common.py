import math, time, datetime as dt, requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SLEEP = 3.5
TW = dt.timezone(dt.timedelta(hours=8))


def now_tw():
    return dt.datetime.now(TW)


def num(x):
    s = str(x).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def get_json(url, params=None, session=None):
    s = session or requests
    for _ in range(3):
        try:
            r = s.get(url, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print("連線失敗：", url, e)
        time.sleep(SLEEP * 2)
    return None


def find_table(js, must):
    cands = []
    for t in js.get("tables", []) or []:
        if t.get("fields") and t.get("data"):
            cands.append((t["fields"], t["data"]))
    for k, v in js.items():
        if k.startswith("fields") and isinstance(v, list) and ("data" + k[6:]) in js:
            cands.append((v, js["data" + k[6:]]))
    for f, d in cands:
        if all(m in f for m in must):
            return f, d
    return None, None


def roc_to_date(s):
    y, m, d = s.strip().split("/")
    return dt.date(int(y) + 1911, int(m), int(d))


def tick(p):
    return 0.01 if p < 10 else 0.05 if p < 50 else 0.1 if p < 100 else 0.5 if p < 500 else 1 if p < 1000 else 5


def floor_tick(x):
    t = tick(x)
    return round(math.floor(x / t + 1e-9) * t, 2)


def ceil_tick(x):
    t = tick(x)
    return round(math.ceil(x / t - 1e-9) * t, 2)


def plan(price, prior_high):
    """停損、保本點、停利、部位比例（依收盤離前高）。"""
    stop_raw = prior_high * 0.98
    stop_x = floor_tick(stop_raw)
    if abs(stop_x - stop_raw) < 1e-9:
        stop_x = round(stop_x - tick(stop_raw), 2)
    dist = price - stop_raw
    gap = (price / prior_high - 1) * 100
    size = 1 if gap <= 1 else 0.5 if gap <= 2 else 0.25 if gap <= 6 else 0
    return {
        "stop": stop_x,
        "breakeven": ceil_tick(price + dist),
        "target": floor_tick(max(price + 2 * dist, price * 1.05)),
        "gap": round(gap, 2),
        "size": size,
    }

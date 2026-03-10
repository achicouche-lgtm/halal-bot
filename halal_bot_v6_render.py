"""
╔══════════════════════════════════════════════════════════════╗
║   🕌 بوت التداول الحلال التلقائي v6.0                      ║
║   🔍 نظام مسح السوق الذكي — يختار العملات تلقائياً         ║
╚══════════════════════════════════════════════════════════════╝

الجديد في v6.0:
  ✅ مسح السوق تلقائياً كل دقيقة
  ✅ يختار أفضل العملات بناءً على 7 معايير
  ✅ نظام نقاط لتصنيف كل عملة (0-100)
  ✅ يدخل الصفقات تلقائياً عند اكتشاف فرصة
  ✅ يخرج تلقائياً عند انتهاء الفرصة
  ✅ تقرير يومي بأفضل العملات
  ✅ Stop Loss / Take Profit تلقائي لكل صفقة
"""

import os
import random
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from collections import deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

# ── Web Server لإرضاء Render ──────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *args):
        pass

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════
#  ⚙️  إعدادات البوت
# ════════════════════════════════════════════════════════
TELEGRAM_TOKEN     = "8678707346:AAFHKDUsYYlN3oI95U5iqsi6fmy8u4F01Vw"
BINANCE_API_KEY    = ""
BINANCE_API_SECRET = ""
USE_BINANCE        = bool(BINANCE_API_KEY and BINANCE_API_SECRET)

DEFAULT_CAPITAL    = 10_000.0
PRICE_UPDATE_SEC   = 15       # تحديث الأسعار
MONITOR_SEC        = 20       # فحص SL/TP
SCAN_SEC           = 60       # مسح السوق
MAX_POSITIONS      = 5        # أقصى عدد صفقات مفتوحة في نفس الوقت
MIN_SCORE          = 60       # الحد الأدنى للنقاط للدخول في صفقة (0-100)
RISK_PER_TRADE     = 0.05     # نسبة رأس المال لكل صفقة (5%)
DEFAULT_SL         = 4.0      # Stop Loss الافتراضي %
DEFAULT_TP         = 10.0     # Take Profit الافتراضي %

# ════════════════════════════════════════════════════════
#  🔌  Binance
# ════════════════════════════════════════════════════════
binance_client = None

def init_binance():
    global binance_client
    if not USE_BINANCE:
        return False
    try:
        from binance.client import Client
        binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        binance_client.ping()
        logger.info("✅ Binance متصل")
        return True
    except ImportError:
        logger.warning("pip install python-binance")
        return False
    except Exception as e:
        logger.error(f"Binance error: {e}")
        return False

def binance_price(sym: str) -> float:
    try:
        t = binance_client.get_symbol_ticker(symbol=sym + "USDT")
        return float(t["price"])
    except:
        return ASSETS[sym]["price"]

def binance_balance(asset: str = "USDT") -> float:
    try:
        info = binance_client.get_asset_balance(asset=asset)
        return float(info["free"]) if info else 0.0
    except:
        return 0.0

def binance_order(sym: str, side: str, qty: float) -> dict:
    try:
        from binance.enums import SIDE_BUY, SIDE_SELL
        order = binance_client.order_market(
            symbol=sym + "USDT",
            side=SIDE_BUY if side == "BUY" else SIDE_SELL,
            quantity=qty,
        )
        px = float(order["fills"][0]["price"]) if order.get("fills") else 0.0
        return {"ok": True, "price": px}
    except Exception as e:
        return {"ok": False, "msg": str(e)}

# ════════════════════════════════════════════════════════
#  🕌  العملات الحلال
# ════════════════════════════════════════════════════════
ASSETS: dict[str, dict] = {
    "BTC":   {"name": "Bitcoin",      "halal": True,  "vol": 0.015, "price": 67000.0, "min_qty": 0.00001,
               "reason": "عملة رقمية لا مركزية"},
    "ETH":   {"name": "Ethereum",     "halal": True,  "vol": 0.020, "price": 3500.0,  "min_qty": 0.0001,
               "reason": "منصة عقود ذكية"},
    "BNB":   {"name": "BNB",          "halal": True,  "vol": 0.018, "price": 580.0,   "min_qty": 0.001,
               "reason": "رمز منصة Binance"},
    "XRP":   {"name": "Ripple",       "halal": True,  "vol": 0.025, "price": 0.62,    "min_qty": 1.0,
               "reason": "نظام دفع رقمي"},
    "ADA":   {"name": "Cardano",      "halal": True,  "vol": 0.028, "price": 0.45,    "min_qty": 1.0,
               "reason": "منصة blockchain"},
    "SOL":   {"name": "Solana",       "halal": True,  "vol": 0.028, "price": 165.0,   "min_qty": 0.001,
               "reason": "blockchain عالي الأداء"},
    "DOT":   {"name": "Polkadot",     "halal": True,  "vol": 0.030, "price": 7.5,     "min_qty": 0.01,
               "reason": "بروتوكول تشبيك"},
    "LINK":  {"name": "Chainlink",    "halal": True,  "vol": 0.025, "price": 15.0,    "min_qty": 0.01,
               "reason": "خدمات Oracle"},
    "AVAX":  {"name": "Avalanche",    "halal": True,  "vol": 0.030, "price": 38.0,    "min_qty": 0.01,
               "reason": "blockchain سريعة"},
    "MATIC": {"name": "Polygon",      "halal": True,  "vol": 0.032, "price": 0.85,    "min_qty": 1.0,
               "reason": "حل Layer 2"},
    "ATOM":  {"name": "Cosmos",       "halal": True,  "vol": 0.028, "price": 9.5,     "min_qty": 0.1,
               "reason": "شبكة blockchain"},
    "ALGO":  {"name": "Algorand",     "halal": True,  "vol": 0.030, "price": 0.18,    "min_qty": 1.0,
               "reason": "منصة blockchain"},
    "DOGE":  {"name": "Dogecoin",     "halal": False, "vol": 0.050, "price": 0.16,    "min_qty": 1.0,
               "reason": "⚠️ عملة مضاربية"},
    "USDT":  {"name": "Tether",       "halal": False, "vol": 0.000, "price": 1.0,     "min_qty": 1.0,
               "reason": "⚠️ شبهة ربا"},
}

HALAL_LIST = [s for s, d in ASSETS.items() if d["halal"]]

# سجل الأسعار التاريخية
HISTORY: dict[str, deque] = {
    s: deque([d["price"]] * 100, maxlen=100)
    for s, d in ASSETS.items()
}

# ════════════════════════════════════════════════════════
#  📊  محرك الأسعار
# ════════════════════════════════════════════════════════
def tick_prices():
    for sym, data in ASSETS.items():
        if USE_BINANCE and binance_client and data["halal"]:
            p = binance_price(sym)
            if p > 0:
                HISTORY[sym].append(p)
                ASSETS[sym]["price"] = p
                continue
        last  = HISTORY[sym][-1]
        move  = random.gauss(0.00015, data["vol"])
        new_p = round(max(last * (1 + move), 0.000001), 8)
        HISTORY[sym].append(new_p)
        ASSETS[sym]["price"] = new_p

def price(sym: str) -> float:
    return ASSETS[sym]["price"]

def hist(sym: str) -> list:
    return list(HISTORY[sym])

# ════════════════════════════════════════════════════════
#  📐  المؤشرات الفنية
# ════════════════════════════════════════════════════════
def sma(sym: str, n: int) -> float:
    h = hist(sym)
    s = h[-n:] if len(h) >= n else h
    return round(sum(s) / len(s), 8)

def ema(sym: str, n: int) -> float:
    h = hist(sym)
    if len(h) < n:
        return h[-1]
    k, v = 2 / (n + 1), h[-n]
    for p in h[-n+1:]:
        v = p * k + v * (1 - k)
    return round(v, 8)

def rsi(sym: str, n: int = 14) -> float:
    h = hist(sym)
    if len(h) < n + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, n + 1):
        d = h[-i] - h[-i-1]
        (gains if d > 0 else losses).append(abs(d))
    ag = sum(gains) / n if gains else 0
    al = sum(losses) / n if losses else 1e-9
    return round(100 - 100 / (1 + ag / al), 2)

def macd(sym: str) -> float:
    return round(ema(sym, 12) - ema(sym, 26), 8)

def bollinger(sym: str, n: int = 20) -> tuple:
    """Bollinger Bands — يُرجع (upper, middle, lower)"""
    h  = hist(sym)
    sl = h[-n:] if len(h) >= n else h
    mid  = sum(sl) / len(sl)
    std  = (sum((x - mid) ** 2 for x in sl) / len(sl)) ** 0.5
    return round(mid + 2 * std, 8), round(mid, 8), round(mid - 2 * std, 8)

def momentum(sym: str, n: int = 10) -> float:
    """نسبة التغير خلال N فترة"""
    h = hist(sym)
    if len(h) < n + 1:
        return 0.0
    return round((h[-1] - h[-n]) / h[-n] * 100, 4)

def volume_trend(sym: str) -> str:
    """محاكاة اتجاه الحجم"""
    h = hist(sym)
    if len(h) < 20:
        return "NEUTRAL"
    recent_vol  = abs(h[-1] - h[-5])  / h[-5]
    older_vol   = abs(h[-10] - h[-20]) / h[-20]
    if recent_vol > older_vol * 1.5:
        return "HIGH"
    elif recent_vol < older_vol * 0.5:
        return "LOW"
    return "NEUTRAL"

def fmt_p(sym: str, p: float) -> str:
    if p >= 100:   return f"${p:,.2f}"
    elif p >= 1:   return f"${p:.4f}"
    else:          return f"${p:.6f}"

def fmt(v: float) -> str:
    return f"${v:,.2f}"

def pnl_e(v: float) -> str:
    return "📈" if v >= 0 else "📉"

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

# ════════════════════════════════════════════════════════
#  🔍  نظام مسح السوق الذكي — قلب البوت
# ════════════════════════════════════════════════════════
def score_coin(sym: str) -> dict:
    """
    يحسب نقاط كل عملة من 0 إلى 100
    بناءً على 7 معايير فنية
    يُرجع: {score, signals, recommendation, details}
    """
    cur    = price(sym)
    r      = rsi(sym)
    m      = macd(sym)
    s10    = sma(sym, 10)
    s30    = sma(sym, 30)
    s50    = sma(sym, 50)
    mom10  = momentum(sym, 10)
    mom20  = momentum(sym, 20)
    bb_up, bb_mid, bb_low = bollinger(sym)
    vol_tr = volume_trend(sym)

    score   = 50  # نقطة البداية المحايدة
    signals = []
    details = []

    # ── 1. RSI (0-25 نقطة) ──────────────────────────────
    if r < 25:
        score  += 25
        signals.append("BUY")
        details.append(f"⚡ RSI={r:.0f} تشبع بيع قوي جداً (+25)")
    elif r < 35:
        score  += 15
        signals.append("BUY")
        details.append(f"⚡ RSI={r:.0f} تشبع بيع (+15)")
    elif r > 75:
        score  -= 25
        signals.append("SELL")
        details.append(f"⚡ RSI={r:.0f} تشبع شراء قوي (-25)")
    elif r > 65:
        score  -= 15
        signals.append("SELL")
        details.append(f"⚡ RSI={r:.0f} تشبع شراء (-15)")
    else:
        details.append(f"⚡ RSI={r:.0f} محايد")

    # ── 2. MACD (0-20 نقطة) ─────────────────────────────
    if m > 0 and m > abs(m) * 0.1:
        score  += 20
        signals.append("BUY")
        details.append(f"🔀 MACD إيجابي قوي (+20)")
    elif m > 0:
        score  += 10
        signals.append("BUY")
        details.append(f"🔀 MACD إيجابي (+10)")
    elif m < 0 and abs(m) > abs(m) * 0.1:
        score  -= 20
        signals.append("SELL")
        details.append(f"🔀 MACD سلبي قوي (-20)")
    elif m < 0:
        score  -= 10
        signals.append("SELL")
        details.append(f"🔀 MACD سلبي (-10)")

    # ── 3. تقاطع المتوسطات SMA (0-15 نقطة) ─────────────
    if s10 > s30 > s50:
        score  += 15
        signals.append("BUY")
        details.append(f"📊 SMA10>SMA30>SMA50 اتجاه صاعد (+15)")
    elif s10 > s30:
        score  += 8
        signals.append("BUY")
        details.append(f"📊 SMA10>SMA30 (+8)")
    elif s10 < s30 < s50:
        score  -= 15
        signals.append("SELL")
        details.append(f"📊 SMA10<SMA30<SMA50 اتجاه هابط (-15)")
    elif s10 < s30:
        score  -= 8
        signals.append("SELL")
        details.append(f"📊 SMA10<SMA30 (-8)")

    # ── 4. Bollinger Bands (0-15 نقطة) ──────────────────
    if cur < bb_low:
        score  += 15
        signals.append("BUY")
        details.append(f"📉 تحت Bollinger السفلي — ارتداد محتمل (+15)")
    elif cur > bb_up:
        score  -= 15
        signals.append("SELL")
        details.append(f"📈 فوق Bollinger العلوي — تصحيح محتمل (-15)")
    elif cur < bb_mid:
        score  += 5
        details.append(f"📊 تحت منتصف Bollinger (+5)")
    else:
        details.append(f"📊 فوق منتصف Bollinger")

    # ── 5. الزخم Momentum (0-10 نقطة) ───────────────────
    if mom10 > 3:
        score  += 10
        signals.append("BUY")
        details.append(f"💨 زخم قوي {mom10:+.2f}% (+10)")
    elif mom10 > 1:
        score  += 5
        signals.append("BUY")
        details.append(f"💨 زخم إيجابي {mom10:+.2f}% (+5)")
    elif mom10 < -3:
        score  -= 10
        signals.append("SELL")
        details.append(f"💨 زخم سلبي قوي {mom10:+.2f}% (-10)")
    elif mom10 < -1:
        score  -= 5
        signals.append("SELL")
        details.append(f"💨 زخم سلبي {mom10:+.2f}% (-5)")

    # ── 6. الحجم Volume (0-10 نقطة) ─────────────────────
    if vol_tr == "HIGH":
        if "BUY" in signals:
            score += 10
            details.append(f"📊 حجم مرتفع يدعم الصعود (+10)")
        else:
            score -= 5
            details.append(f"📊 حجم مرتفع يدعم الهبوط (-5)")
    elif vol_tr == "LOW":
        score -= 5
        details.append(f"📊 حجم منخفض — إشارة ضعيفة (-5)")

    # ── 7. الاتجاه العام (0-5 نقطة) ─────────────────────
    if mom20 > 5:
        score += 5
        details.append(f"📈 اتجاه شهري إيجابي {mom20:+.2f}% (+5)")
    elif mom20 < -5:
        score -= 5
        details.append(f"📉 اتجاه شهري سلبي {mom20:+.2f}% (-5)")

    # ── تحديد التوصية ────────────────────────────────────
    score = max(0, min(100, score))
    buy_count  = signals.count("BUY")
    sell_count = signals.count("SELL")

    if score >= 75:
        recommendation = "🟢🟢 شراء قوي"
        action         = "STRONG_BUY"
    elif score >= MIN_SCORE:
        recommendation = "🟢 شراء"
        action         = "BUY"
    elif score <= 25:
        recommendation = "🔴🔴 بيع قوي"
        action         = "STRONG_SELL"
    elif score <= 40:
        recommendation = "🔴 بيع"
        action         = "SELL"
    else:
        recommendation = "🟡 انتظار"
        action         = "HOLD"

    return {
        "sym":            sym,
        "score":          score,
        "action":         action,
        "recommendation": recommendation,
        "rsi":            r,
        "macd":           m,
        "momentum":       mom10,
        "volume":         vol_tr,
        "signals_buy":    buy_count,
        "signals_sell":   sell_count,
        "details":        details,
        "price":          cur,
    }

def scan_market() -> list:
    """
    يمسح كل العملات الحلال ويرتبها حسب النقاط
    يُرجع قائمة مرتبة من الأفضل للأسوأ
    """
    results = []
    for sym in HALAL_LIST:
        try:
            result = score_coin(sym)
            results.append(result)
        except Exception as e:
            logger.warning(f"خطأ في تحليل {sym}: {e}")
    # ترتيب تنازلي حسب النقاط
    results.sort(key=lambda x: x["score"], reverse=True)
    return results

def get_best_opportunities(results: list, max_count: int = 5) -> list:
    """يُرجع أفضل فرص الشراء"""
    return [r for r in results if r["score"] >= MIN_SCORE and r["action"] in ("BUY", "STRONG_BUY")][:max_count]

# ════════════════════════════════════════════════════════
#  💾  بيانات المستخدمين
# ════════════════════════════════════════════════════════
def new_user() -> dict:
    return {
        "mode":         "sim",
        "cash":         DEFAULT_CAPITAL,
        "holdings":     {},
        "transactions": [],
        "orders":       {},
        # إعدادات المسح الذكي
        "smart_scan": {
            "active":       False,   # هل المسح الذكي مُفعَّل؟
            "sl_pct":       DEFAULT_SL,
            "tp_pct":       DEFAULT_TP,
            "max_positions": MAX_POSITIONS,
            "min_score":    MIN_SCORE,
            "risk_pct":     RISK_PER_TRADE,
            "last_scan":    None,
            "scan_count":   0,
        },
        # آخر نتائج المسح
        "last_scan_results": [],
        # التداول المتعدد اليدوي
        "multi_auto":   {},
        "stats": {
            "total_trades": 0, "wins": 0,
            "losses": 0, "total_pnl": 0.0,
            "per_sym": {},
            "scan_trades": 0,
        },
    }

USERS: dict[int, dict] = {}

def get_user(uid: int) -> dict:
    if uid not in USERS:
        USERS[uid] = new_user()
    return USERS[uid]

def portfolio_value(uid: int) -> float:
    u   = get_user(uid)
    val = u["cash"]
    for sym, d in u["holdings"].items():
        if sym in ASSETS:
            val += price(sym) * d["qty"]
    return round(val, 2)

def mode_lbl(uid: int) -> str:
    u = get_user(uid)
    return "🟢 *Binance حقيقي*" if (u["mode"] == "live" and USE_BINANCE) else "🔵 *محاكاة*"

def open_positions(uid: int) -> int:
    return len(get_user(uid)["holdings"])

# ════════════════════════════════════════════════════════
#  🛒  منطق التداول
# ════════════════════════════════════════════════════════
def halal_ok(sym: str) -> bool:
    return sym in ASSETS and ASSETS[sym]["halal"]

def do_buy(uid: int, sym: str, qty: float,
           auto: bool = False, sl_pct: float = None, tp_pct: float = None,
           scan_trade: bool = False) -> dict:
    if not halal_ok(sym):
        return {"ok": False, "msg": f"🚫 `{sym}` غير حلال"}

    u    = get_user(uid)
    px   = price(sym)
    cost = round(px * qty, 4)

    if u["mode"] == "live" and USE_BINANCE and binance_client:
        bal = binance_balance("USDT")
        if bal < cost:
            return {"ok": False, "msg": f"❌ رصيد غير كافٍ ({fmt(bal)})"}
        res = binance_order(sym, "BUY", qty)
        if not res["ok"]:
            return {"ok": False, "msg": f"❌ {res['msg']}"}
        px   = res["price"]
        cost = round(px * qty, 4)
    else:
        if u["cash"] < cost:
            return {"ok": False, "msg": f"❌ رصيد غير كافٍ\nالمتاح: {fmt(u['cash'])}\nالمطلوب: {fmt(cost)}"}
        u["cash"] -= cost

    h = u["holdings"]
    if sym in h:
        total = h[sym]["qty"] + qty
        h[sym]["avg_price"] = (h[sym]["avg_price"] * h[sym]["qty"] + px * qty) / total
        h[sym]["qty"]       = round(total, 8)
    else:
        h[sym] = {"qty": qty, "avg_price": px, "name": ASSETS[sym]["name"]}

    # تعيين SL/TP تلقائياً
    if sl_pct or tp_pct:
        order = {"entry_price": px}
        if sl_pct:
            order["sl_pct"]   = sl_pct
            order["sl_price"] = round(px * (1 - sl_pct / 100), 8)
        if tp_pct:
            order["tp_pct"]   = tp_pct
            order["tp_price"] = round(px * (1 + tp_pct / 100), 8)
        u["orders"][sym] = order

    label = "🔍 مسح ذكي" if scan_trade else ("🤖 تلقائي" if auto else "👤 يدوي")
    u["transactions"].append({
        "type": label, "dir": "شراء",
        "sym": sym, "qty": qty, "price": px, "total": cost,
        "mode": u["mode"], "date": now(),
    })
    u["stats"]["total_trades"] += 1
    if scan_trade:
        u["stats"]["scan_trades"] += 1
    if sym not in u["stats"]["per_sym"]:
        u["stats"]["per_sym"][sym] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
    u["stats"]["per_sym"][sym]["trades"] += 1
    return {"ok": True, "price": px, "cost": cost}

def do_sell(uid: int, sym: str, qty: float,
            auto: bool = False, reason: str = "بيع") -> dict:
    u = get_user(uid)
    h = u["holdings"]
    if sym not in h or h[sym]["qty"] < qty - 1e-9:
        return {"ok": False, "msg": f"❌ لا تملك كمية كافية من `{sym}`"}

    px      = price(sym)
    revenue = round(px * qty, 4)
    avg     = h[sym]["avg_price"]
    pnl     = round((px - avg) * qty, 4)
    pnl_pct = round((px - avg) / avg * 100, 2)

    if u["mode"] == "live" and USE_BINANCE and binance_client:
        res = binance_order(sym, "SELL", qty)
        if not res["ok"]:
            return {"ok": False, "msg": f"❌ {res['msg']}"}
        px      = res["price"]
        revenue = round(px * qty, 4)
        pnl     = round((px - avg) * qty, 4)
        pnl_pct = round((px - avg) / avg * 100, 2)
    else:
        u["cash"] += revenue

    h[sym]["qty"] = round(h[sym]["qty"] - qty, 8)
    if h[sym]["qty"] <= 1e-9:
        del h[sym]
        u["orders"].pop(sym, None)

    u["transactions"].append({
        "type": "🤖" if auto else "👤", "dir": reason,
        "sym": sym, "qty": qty, "price": px,
        "total": revenue, "pnl": pnl,
        "mode": u["mode"], "date": now(),
    })
    u["stats"]["total_trades"] += 1
    u["stats"]["total_pnl"]   += pnl
    if pnl >= 0:
        u["stats"]["wins"] += 1
    else:
        u["stats"]["losses"] += 1

    st = u["stats"]["per_sym"].setdefault(sym, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    st["trades"] += 1
    st["pnl"]    += pnl
    if pnl >= 0: st["wins"]   += 1
    else:         st["losses"] += 1

    return {"ok": True, "price": px, "revenue": revenue, "pnl": pnl, "pnl_pct": pnl_pct}

# ════════════════════════════════════════════════════════
#  ⏱️  مهام الخلفية
# ════════════════════════════════════════════════════════
async def job_prices(ctx: ContextTypes.DEFAULT_TYPE):
    tick_prices()

async def job_monitor_sl_tp(ctx: ContextTypes.DEFAULT_TYPE):
    """مراقبة Stop Loss / Take Profit"""
    for uid, u in list(USERS.items()):
        for sym, order in list(u["orders"].items()):
            if sym not in u["holdings"]:
                u["orders"].pop(sym, None)
                continue
            cur = price(sym)
            qty = u["holdings"][sym]["qty"]
            triggered = None
            if "sl_price" in order and cur <= order["sl_price"]:
                triggered = ("sl", order["sl_price"], order.get("sl_pct", 0))
            elif "tp_price" in order and cur >= order["tp_price"]:
                triggered = ("tp", order["tp_price"], order.get("tp_pct", 0))
            if not triggered:
                continue
            kind, level, pct = triggered
            label  = "🛑 Stop Loss" if kind == "sl" else "🎯 Take Profit"
            reason = "وقف خسارة" if kind == "sl" else "جني ربح"
            res    = do_sell(uid, sym, qty, auto=True, reason=reason)
            if res["ok"]:
                color = "🔴" if kind == "sl" else "🟢"
                try:
                    await ctx.bot.send_message(uid,
                        f"{color} *{label} — `{sym}`*\n{'─'*22}\n"
                        f"📊 النسبة: {pct:.1f}%\n"
                        f"💰 سعر التنفيذ: {fmt_p(sym, res['price'])}\n"
                        f"{pnl_e(res['pnl'])} ${res['pnl']:+.4f} ({res['pnl_pct']:+.2f}%)\n"
                        f"💵 الرصيد: {fmt(get_user(uid)['cash'])}",
                        parse_mode="Markdown")
                except Exception:
                    pass

async def job_smart_scan(ctx: ContextTypes.DEFAULT_TYPE):
    """
    ★ قلب البوت — المسح الذكي التلقائي
    يعمل كل SCAN_SEC ثانية
    1. يمسح السوق ويحسب نقاط كل عملة
    2. يدخل الصفقات عند اكتشاف فرص
    3. يخرج عند ضعف الفرصة
    """
    # تحديث سجل المسح
    scan_results = scan_market()

    for uid, u in list(USERS.items()):
        cfg = u["smart_scan"]
        if not cfg["active"]:
            continue

        cfg["last_scan"]  = now()
        cfg["scan_count"] = cfg.get("scan_count", 0) + 1
        u["last_scan_results"] = scan_results

        sl_pct       = cfg["sl_pct"]
        tp_pct       = cfg["tp_pct"]
        max_pos      = cfg["max_positions"]
        min_score    = cfg["min_score"]
        risk_pct     = cfg["risk_pct"]
        current_pos  = open_positions(uid)

        # ── الجزء 1: الخروج من الصفقات الضعيفة ──────────
        for sym in list(u["holdings"].keys()):
            # لا تتدخل في الأوامر اليدوية أو المتعددة
            if sym in u["multi_auto"]:
                continue
            result = next((r for r in scan_results if r["sym"] == sym), None)
            if result and result["score"] <= 35:
                qty = u["holdings"][sym]["qty"]
                res = do_sell(uid, sym, qty, auto=True, reason="خروج تلقائي")
                if res["ok"]:
                    try:
                        await ctx.bot.send_message(uid,
                            f"🔍 *مسح ذكي — خروج تلقائي*\n{'─'*22}\n"
                            f"📌 `{sym}` | نقاط: {result['score']}/100\n"
                            f"⚠️ الفرصة ضعفت — تم الخروج\n"
                            f"💰 {fmt_p(sym, res['price'])}\n"
                            f"{pnl_e(res['pnl'])} ${res['pnl']:+.4f} ({res['pnl_pct']:+.2f}%)\n"
                            f"💵 {fmt(get_user(uid)['cash'])}",
                            parse_mode="Markdown")
                    except Exception:
                        pass

        # ── الجزء 2: الدخول في فرص جديدة ────────────────
        if current_pos >= max_pos:
            continue  # وصلنا للحد الأقصى

        opportunities = get_best_opportunities(scan_results, max_pos - current_pos)
        for opp in opportunities:
            sym = opp["sym"]
            # تجاهل ما هو مملوك مسبقاً
            if sym in u["holdings"]:
                continue
            # تجاهل ما في التداول اليدوي المتعدد
            if sym in u["multi_auto"] and u["multi_auto"][sym]["active"]:
                continue

            # حساب الكمية بناءً على نسبة المخاطرة
            budget  = u["cash"] * risk_pct
            px      = price(sym)
            min_qty = ASSETS[sym]["min_qty"]
            qty     = max(round(budget / px, 6), min_qty)
            cost    = round(px * qty, 4)

            if u["cash"] < cost:
                continue

            res = do_buy(uid, sym, qty, auto=True,
                         sl_pct=sl_pct, tp_pct=tp_pct, scan_trade=True)
            if res["ok"]:
                score_bar = "🟩" * (opp["score"] // 10) + "⬜" * (10 - opp["score"] // 10)
                try:
                    await ctx.bot.send_message(uid,
                        f"🔍 *مسح ذكي — فرصة مكتشفة!*\n{'─'*26}\n"
                        f"📌 العملة: `{sym}` — {ASSETS[sym]['name']}\n"
                        f"⭐ النقاط: *{opp['score']}/100*\n"
                        f"{score_bar}\n"
                        f"📊 {opp['recommendation']}\n"
                        f"✅ إشارات شراء: {opp['signals_buy']}\n\n"
                        f"💰 سعر الدخول: {fmt_p(sym, res['price'])}\n"
                        f"📦 الكمية: {qty}\n"
                        f"💵 التكلفة: {fmt(res['cost'])}\n\n"
                        f"🛑 Stop Loss: {sl_pct:.1f}%\n"
                        f"🎯 Take Profit: {tp_pct:.1f}%\n"
                        f"🕌 حلال ✅ | {mode_lbl(uid)}",
                        parse_mode="Markdown")
                except Exception:
                    pass

# ════════════════════════════════════════════════════════
#  🎛️  لوحة التحكم
# ════════════════════════════════════════════════════════
def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 مسح ذكي ★ NEW",      callback_data="smart_menu"),
         InlineKeyboardButton("📊 نتائج المسح",         callback_data="scan_results")],
        [InlineKeyboardButton("🔀 تداول متعدد يدوي",   callback_data="multi_menu"),
         InlineKeyboardButton("📈 تداول يدوي",          callback_data="trade_menu")],
        [InlineKeyboardButton("🛑 Stop Loss / 🎯 TP",   callback_data="sl_tp_menu")],
        [InlineKeyboardButton("💼 المحفظة",             callback_data="portfolio"),
         InlineKeyboardButton("💹 الأسعار",             callback_data="prices")],
        [InlineKeyboardButton("📉 الإحصائيات",          callback_data="stats"),
         InlineKeyboardButton("📋 السجل",               callback_data="history")],
        [InlineKeyboardButton("🔌 وضع التشغيل",         callback_data="mode_menu"),
         InlineKeyboardButton("❓ مساعدة",              callback_data="help")],
    ])

back = [[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]]

# ════════════════════════════════════════════════════════
#  📨  معالجات الأوامر
# ════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_user(uid)
    scan = u["smart_scan"]
    scan_status = f"🟢 نشط ({scan['scan_count']} مسح)" if scan["active"] else "⚪ غير نشط"
    pos  = open_positions(uid)

    await update.message.reply_text(
        f"🕌 *بوت التداول الحلال v6.0*\n{'─'*30}\n\n"
        f"👤 {update.effective_user.first_name}\n"
        f"🔌 {mode_lbl(uid)}\n"
        f"💵 الرصيد: {fmt(u['cash'])}\n"
        f"💼 المحفظة: {fmt(portfolio_value(uid))}\n"
        f"📊 الصفقات المفتوحة: {pos}/{scan['max_positions']}\n\n"
        f"*🔍 المسح الذكي:*\n"
        f"الحالة: {scan_status}\n"
        f"📡 يمسح {len(HALAL_LIST)} عملة حلال كل {SCAN_SEC}ث\n\n"
        f"*🚀 الأمر الأسرع للبدء:*\n"
        f"`/smartstart` — تشغيل المسح الذكي\n"
        f"`/smartstart 5 12` — SL 5% / TP 12%\n",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الأوامر الكامل*\n\n"
        "*── 🔍 المسح الذكي (الأهم) ──*\n"
        "`/smartstart` — تشغيل بإعدادات افتراضية\n"
        "`/smartstart 5 12` — SL 5% / TP 12%\n"
        "`/smartstart 3 8 3` — SL/TP/أقصى صفقات\n"
        "`/smartstop` — إيقاف المسح الذكي\n"
        "`/smartstatus` — حالة المسح الذكي\n"
        "`/scan` — مسح فوري وعرض النتائج\n"
        "`/scanreport` — تقرير مفصل للسوق\n"
        "`/score BTC` — نقاط وتحليل عملة\n\n"
        "*── 🔀 تداول متعدد يدوي ──*\n"
        "`/multiadd BTC sma 0.001 3 8`\n"
        "`/multistatus`  `/multistop`\n\n"
        "*── تداول يدوي ──*\n"
        "`/buy BTC 0.001`  `/sell BTC 0.001`\n"
        "`/portfolio`  `/prices`\n\n"
        "*── Stop Loss / Take Profit ──*\n"
        "`/sltp BTC 5 10`  `/orders`\n\n"
        "*── تحليل ──*\n"
        "`/analyze BTC`  `/signal BTC rsi`\n"
        "`/halal BTC`\n\n"
        "*── Binance ──*\n"
        "`/setbinance KEY SECRET`\n"
        "`/livemode`  `/simmode`  `/balance`\n\n"
        "*── أخرى ──*\n"
        "`/history`  `/stats`  `/reset`\n",
        parse_mode="Markdown",
    )

# ════════════════════════════════════════════════════════
#  🔍  أوامر المسح الذكي
# ════════════════════════════════════════════════════════
async def cmd_smartstart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    تشغيل المسح الذكي
    /smartstart [sl%] [tp%] [max_positions]
    مثال: /smartstart 5 12 4
    """
    uid  = update.effective_user.id
    u    = get_user(uid)
    scan = u["smart_scan"]

    # الإعدادات
    try:
        sl_pct   = float(ctx.args[0]) if len(ctx.args) > 0 else DEFAULT_SL
        tp_pct   = float(ctx.args[1]) if len(ctx.args) > 1 else DEFAULT_TP
        max_pos  = int(ctx.args[2])   if len(ctx.args) > 2 else MAX_POSITIONS
        assert 0 < sl_pct < 50 and 0 < tp_pct < 200 and 1 <= max_pos <= 10
    except:
        await update.message.reply_text(
            "❌ إعدادات غير صالحة\n"
            "مثال: `/smartstart 5 12 4`\n"
            "SL=5% TP=12% أقصى=4 صفقات",
            parse_mode="Markdown"
        ); return

    scan["active"]        = True
    scan["sl_pct"]        = sl_pct
    scan["tp_pct"]        = tp_pct
    scan["max_positions"] = max_pos
    scan["scan_count"]    = 0
    scan["last_scan"]     = now()

    rr = round(tp_pct / sl_pct, 2)

    await update.message.reply_text(
        f"🔍 *تم تشغيل المسح الذكي!*\n{'─'*28}\n\n"
        f"🤖 *كيف يعمل:*\n"
        f"1️⃣ يمسح {len(HALAL_LIST)} عملة حلال كل {SCAN_SEC}ث\n"
        f"2️⃣ يحلل كل عملة بـ 7 مؤشرات فنية\n"
        f"3️⃣ يعطي كل عملة نقاطاً (0-100)\n"
        f"4️⃣ يشتري تلقائياً عند نقاط ≥ {MIN_SCORE}\n"
        f"5️⃣ يخرج تلقائياً عند ضعف الفرصة\n\n"
        f"*⚙️ إعداداتك:*\n"
        f"🛑 Stop Loss: *{sl_pct:.1f}%*\n"
        f"🎯 Take Profit: *{tp_pct:.1f}%*\n"
        f"📊 أقصى صفقات: *{max_pos}*\n"
        f"💰 مخاطرة/صفقة: *{RISK_PER_TRADE*100:.0f}%* من الرصيد\n"
        f"⚖️ نسبة المكافأة/المخاطرة: *1:{rr}*\n\n"
        f"📡 أول مسح سيبدأ خلال {SCAN_SEC}ث...\n\n"
        f"_`/smartstop` لإيقاف المسح_",
        parse_mode="Markdown",
    )

async def cmd_smartstop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_user(uid)
    scan = u["smart_scan"]
    if scan["active"]:
        scan["active"] = False
        await update.message.reply_text(
            f"⏹️ *تم إيقاف المسح الذكي*\n\n"
            f"إجمالي عمليات المسح: {scan['scan_count']}\n"
            f"صفقات المسح الذكي: {u['stats']['scan_trades']}\n"
            f"الصفقات المفتوحة: {open_positions(uid)}\n\n"
            f"_الصفقات المفتوحة لا تزال مراقبة بواسطة SL/TP_",
            parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ المسح الذكي غير نشط\n`/smartstart` لتشغيله",
                                        parse_mode="Markdown")

async def cmd_smartstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_user(uid)
    scan = u["smart_scan"]
    pos  = open_positions(uid)

    status = "🟢 نشط" if scan["active"] else "⚪ موقوف"
    text   = (
        f"🔍 *حالة المسح الذكي*\n{'─'*26}\n\n"
        f"الحالة: {status}\n"
        f"عمليات المسح: {scan['scan_count']}\n"
        f"آخر مسح: {scan['last_scan'] or 'لم يبدأ بعد'}\n\n"
        f"*⚙️ الإعدادات الحالية:*\n"
        f"🛑 Stop Loss: {scan['sl_pct']:.1f}%\n"
        f"🎯 Take Profit: {scan['tp_pct']:.1f}%\n"
        f"📊 أقصى صفقات: {scan['max_positions']}\n"
        f"⭐ الحد الأدنى للنقاط: {scan['min_score']}/100\n"
        f"💰 مخاطرة/صفقة: {scan['risk_pct']*100:.0f}%\n\n"
        f"*📊 الصفقات:*\n"
        f"مفتوحة: {pos}/{scan['max_positions']}\n"
        f"صفقات المسح الذكي: {u['stats']['scan_trades']}\n"
        f"💵 الرصيد: {fmt(u['cash'])}\n"
        f"💼 المحفظة: {fmt(portfolio_value(uid))}"
    )

    kb = [
        [InlineKeyboardButton("⏹️ إيقاف" if scan["active"] else "▶️ تشغيل",
                               callback_data="smart_toggle")],
        back[0],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb),
                                    parse_mode="Markdown")

async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """مسح فوري وعرض أفضل الفرص"""
    await update.message.reply_text("🔍 *جاري مسح السوق...*", parse_mode="Markdown")

    results = scan_market()
    uid     = update.effective_user.id
    get_user(uid)["last_scan_results"] = results

    top5    = results[:5]
    opps    = get_best_opportunities(results)

    text = f"🔍 *نتائج مسح السوق*\n{'─'*26}\n"
    text += f"📡 تم فحص {len(results)} عملة حلال\n"
    text += f"⭐ فرص جيدة: {len(opps)}\n"
    text += f"🕐 {now()}\n\n"

    text += f"*🏆 أفضل 5 عملات:*\n"
    for i, r in enumerate(top5, 1):
        bar   = "🟩" * (r["score"] // 20) + "⬜" * (5 - r["score"] // 20)
        medal = ["🥇","🥈","🥉","4️⃣","5️⃣"][i-1]
        text += (
            f"\n{medal} `{r['sym']}` — {ASSETS[r['sym']]['name']}\n"
            f"   ⭐ {r['score']}/100 {bar}\n"
            f"   {r['recommendation']}\n"
            f"   💰 {fmt_p(r['sym'], r['price'])}  "
            f"RSI:{r['rsi']:.0f}  Mom:{r['momentum']:+.1f}%\n"
        )

    if opps:
        text += f"\n{'─'*26}\n"
        text += f"✅ *فرص جاهزة للشراء:*\n"
        for o in opps:
            text += f"  🟢 `{o['sym']}` — {o['score']}/100\n"
    else:
        text += f"\n⚠️ لا توجد فرص واضحة الآن\nالسوق يحتاج تصحيحاً أو انتظر"

    kb = [
        [InlineKeyboardButton("🔄 مسح جديد",   callback_data="do_scan"),
         InlineKeyboardButton("📋 تقرير كامل", callback_data="scan_report")],
        back[0],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb),
                                    parse_mode="Markdown")

async def cmd_scanreport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تقرير مفصل لكل العملات"""
    await update.message.reply_text("📊 *جاري إعداد التقرير الكامل...*", parse_mode="Markdown")
    results = scan_market()

    text = f"📊 *تقرير السوق الكامل*\n{'─'*28}\n{now()}\n\n"

    # تصنيف حسب التوصية
    strong_buy = [r for r in results if r["action"] == "STRONG_BUY"]
    buy        = [r for r in results if r["action"] == "BUY"]
    hold       = [r for r in results if r["action"] == "HOLD"]
    sell       = [r for r in results if r["action"] in ("SELL", "STRONG_SELL")]

    if strong_buy:
        text += f"🟢🟢 *شراء قوي ({len(strong_buy)}):*\n"
        for r in strong_buy:
            text += f"  `{r['sym']}` {r['score']}/100 | RSI:{r['rsi']:.0f}\n"

    if buy:
        text += f"\n🟢 *شراء ({len(buy)}):*\n"
        for r in buy:
            text += f"  `{r['sym']}` {r['score']}/100 | {fmt_p(r['sym'], r['price'])}\n"

    if hold:
        text += f"\n🟡 *انتظار ({len(hold)}):*\n"
        for r in hold:
            text += f"  `{r['sym']}` {r['score']}/100\n"

    if sell:
        text += f"\n🔴 *بيع/تجنب ({len(sell)}):*\n"
        for r in sell:
            text += f"  `{r['sym']}` {r['score']}/100\n"

    text += (
        f"\n{'─'*28}\n"
        f"📈 فرص شراء: {len(strong_buy) + len(buy)}\n"
        f"🟡 محايدة: {len(hold)}\n"
        f"📉 تجنب: {len(sell)}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تحليل نقاط عملة محددة"""
    if not ctx.args:
        await update.message.reply_text("📝 `/score <رمز>`\nمثال: `/score BTC`",
                                        parse_mode="Markdown"); return
    sym = ctx.args[0].upper()
    if sym not in ASSETS:
        await update.message.reply_text(f"❌ `{sym}` غير موجود", parse_mode="Markdown"); return

    r    = score_coin(sym)
    bar  = "🟩" * (r["score"] // 10) + "⬜" * (10 - r["score"] // 10)

    text = (
        f"⭐ *تحليل نقاط `{sym}`*\n{'─'*26}\n\n"
        f"🏢 {ASSETS[sym]['name']}\n"
        f"💰 السعر: {fmt_p(sym, r['price'])}\n\n"
        f"*النقاط الإجمالية:*\n"
        f"⭐ *{r['score']}/100*\n"
        f"{bar}\n\n"
        f"*التوصية:* {r['recommendation']}\n\n"
        f"*📊 تفاصيل التحليل:*\n"
    )
    for detail in r["details"]:
        text += f"  {detail}\n"

    text += (
        f"\n{'─'*26}\n"
        f"✅ إشارات شراء: {r['signals_buy']}\n"
        f"❌ إشارات بيع: {r['signals_sell']}\n"
        f"⚡ RSI: {r['rsi']:.1f}\n"
        f"💨 الزخم: {r['momentum']:+.2f}%\n"
        f"📊 الحجم: {r['volume']}\n\n"
    )

    if r["score"] >= MIN_SCORE:
        text += f"✅ *مؤهل للشراء التلقائي* (≥{MIN_SCORE} نقطة)"
    else:
        text += f"⚠️ *غير مؤهل للآن* (أقل من {MIN_SCORE} نقطة)"

    await update.message.reply_text(text, parse_mode="Markdown")

# ════════════════════════════════════════════════════════
#  📨  باقي الأوامر
# ════════════════════════════════════════════════════════
async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("📝 `/buy <رمز> <كمية>`\nمثال: `/buy BTC 0.001`", parse_mode="Markdown"); return
    sym = args[0].upper()
    try:
        qty = float(args[1]); assert qty > 0
    except:
        await update.message.reply_text("❌ الكمية غير صالحة"); return
    uid = update.effective_user.id
    res = do_buy(uid, sym, qty)
    if not res["ok"]:
        await update.message.reply_text(res["msg"], parse_mode="Markdown"); return
    await update.message.reply_text(
        f"✅ *تم الشراء*\n📌 `{sym}` × {qty}\n"
        f"💰 {fmt_p(sym, res['price'])} | 💵 {fmt(res['cost'])}\n"
        f"💳 {fmt(get_user(uid)['cash'])} | 🕌 حلال ✅\n"
        f"💡 `/sltp {sym} 5 10`",
        parse_mode="Markdown")

async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("📝 `/sell <رمز> <كمية>`", parse_mode="Markdown"); return
    sym = args[0].upper()
    try:
        qty = float(args[1]); assert qty > 0
    except:
        await update.message.reply_text("❌ الكمية غير صالحة"); return
    uid = update.effective_user.id
    res = do_sell(uid, sym, qty)
    if not res["ok"]:
        await update.message.reply_text(res["msg"], parse_mode="Markdown"); return
    await update.message.reply_text(
        f"✅ *تم البيع*\n📌 `{sym}` × {qty}\n"
        f"💰 {fmt_p(sym, res['price'])} | 💵 {fmt(res['revenue'])}\n"
        f"{pnl_e(res['pnl'])} ${res['pnl']:+.4f} ({res['pnl_pct']:+.2f}%)",
        parse_mode="Markdown")

async def cmd_sltp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 3:
        await update.message.reply_text("📝 `/sltp <رمز> <sl%> <tp%>`\nمثال: `/sltp BTC 5 10`", parse_mode="Markdown"); return
    sym = args[0].upper()
    try:
        sl_pct = float(args[1]); tp_pct = float(args[2])
    except:
        await update.message.reply_text("❌ النسب غير صالحة"); return
    uid = update.effective_user.id
    u   = get_user(uid)
    if sym not in u["holdings"]:
        await update.message.reply_text(f"❌ لا تملك `{sym}`", parse_mode="Markdown"); return
    avg = u["holdings"][sym]["avg_price"]
    u["orders"][sym] = {
        "sl_pct": sl_pct, "sl_price": round(avg * (1 - sl_pct / 100), 8),
        "tp_pct": tp_pct, "tp_price": round(avg * (1 + tp_pct / 100), 8),
        "entry_price": avg,
    }
    await update.message.reply_text(
        f"⚙️ *SL/TP — `{sym}`*\n"
        f"🛑 SL: {sl_pct:.1f}% | 🎯 TP: {tp_pct:.1f}%\n"
        f"⚖️ نسبة: 1:{round(tp_pct/sl_pct,2)}",
        parse_mode="Markdown")

async def cmd_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    orders = get_user(uid)["orders"]
    if not orders:
        await update.message.reply_text("📋 لا توجد أوامر معلقة"); return
    text = f"📋 *أوامر SL/TP*\n{'─'*20}\n"
    for sym, o in orders.items():
        cur  = price(sym)
        text += f"\n`{sym}` {fmt_p(sym, cur)}\n"
        if "sl_price" in o:
            text += f"  🛑 SL {o['sl_pct']:.1f}%: {fmt_p(sym, o['sl_price'])}\n"
        if "tp_price" in o:
            text += f"  🎯 TP {o['tp_pct']:.1f}%: {fmt_p(sym, o['tp_price'])}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_multiadd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 3:
        await update.message.reply_text(
            "📝 `/multiadd <رمز> <استراتيجية> <كمية> [sl%] [tp%]`\n"
            "مثال: `/multiadd BTC sma 0.001 3 8`\n"
            "الاستراتيجيات: `sma` | `rsi` | `macd` | `break`",
            parse_mode="Markdown"); return
    sym      = args[0].upper()
    strategy = args[1].lower()
    try:
        qty = float(args[2]); assert qty > 0
    except:
        await update.message.reply_text("❌ الكمية غير صالحة"); return

    if not halal_ok(sym):
        await update.message.reply_text(f"🚫 `{sym}` غير حلال", parse_mode="Markdown"); return
    if strategy not in ("sma", "rsi", "macd", "break"):
        await update.message.reply_text("❌ استراتيجية غير موجودة", parse_mode="Markdown"); return

    sl_pct = tp_pct = None
    try:
        if len(args) >= 4: sl_pct = float(args[3])
        if len(args) >= 5: tp_pct = float(args[4])
    except: pass

    uid = update.effective_user.id
    u   = get_user(uid)
    u["multi_auto"][sym] = {
        "active": True, "strategy": strategy,
        "qty": qty, "sl_pct": sl_pct, "tp_pct": tp_pct,
        "added_at": now(),
    }
    cur    = price(sym)
    r_coin = score_coin(sym)
    await update.message.reply_text(
        f"✅ *تمت إضافة `{sym}` للتداول المتعدد*\n"
        f"⭐ نقاط السوق: {r_coin['score']}/100\n"
        f"📦 كمية/صفقة: {qty}\n"
        f"{'🛑 SL: '+str(sl_pct)+'%' if sl_pct else ''}"
        f"{'  🎯 TP: '+str(tp_pct)+'%' if tp_pct else ''}\n\n"
        f"💡 للمسح الذكي التلقائي: `/smartstart`",
        parse_mode="Markdown")

async def cmd_multistop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    multi = get_user(uid)["multi_auto"]
    if ctx.args:
        sym = ctx.args[0].upper()
        if sym in multi:
            multi[sym]["active"] = False
            await update.message.reply_text(f"⏸️ تم إيقاف `{sym}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ `{sym}` غير موجود", parse_mode="Markdown")
    else:
        for cfg in multi.values(): cfg["active"] = False
        await update.message.reply_text("⏹️ تم إيقاف جميع العملات")

async def cmd_multistatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    multi = get_user(uid)["multi_auto"]
    if not multi:
        await update.message.reply_text("🔀 لا توجد عملات. أضف: `/multiadd BTC sma 0.001`",
                                        parse_mode="Markdown"); return
    text  = f"🔀 *التداول المتعدد*\n{'─'*22}\n"
    for sym, cfg in multi.items():
        cur  = price(sym)
        stat = "✅" if cfg["active"] else "⏸️"
        sc   = score_coin(sym)
        text += f"\n{stat} `{sym}` ⭐{sc['score']}/100\n"
        text += f"  {fmt_p(sym, cur)} | {cfg['strategy'].upper()}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u   = get_user(uid)
    h   = u["holdings"]
    if not h:
        await update.message.reply_text(
            f"💼 *المحفظة فارغة*\n💵 {fmt(u['cash'])}\n\n"
            f"🔍 `/smartstart` للتداول التلقائي",
            parse_mode="Markdown"); return
    total = u["cash"]
    text  = f"💼 *محفظتك*\n{'─'*22}\n{mode_lbl(uid)}\n"
    for sym, d in h.items():
        cur  = price(sym)
        val  = cur * d["qty"]
        pnl  = (cur - d["avg_price"]) * d["qty"]
        ppct = (cur - d["avg_price"]) / d["avg_price"] * 100
        total += val
        o     = u["orders"].get(sym, {})
        sl_s  = f" 🛑{o['sl_pct']:.0f}%" if "sl_pct" in o else ""
        tp_s  = f" 🎯{o['tp_pct']:.0f}%" if "tp_pct" in o else ""
        sc    = score_coin(sym)
        text += (
            f"\n🔖 `{sym}` ⭐{sc['score']}/100\n"
            f"  {d['qty']} × {fmt_p(sym, cur)} = {fmt(val)}\n"
            f"  {pnl_e(pnl)} ${pnl:+.4f} ({ppct:+.2f}%){sl_s}{tp_s}\n"
        )
    ov = total - DEFAULT_CAPITAL
    text += (
        f"\n{'─'*22}\n"
        f"💵 النقد: {fmt(u['cash'])}\n"
        f"💼 *{fmt(total)}*\n"
        f"{pnl_e(ov)} ${ov:+,.2f} ({ov/DEFAULT_CAPITAL*100:+.2f}%)"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_prices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    results = scan_market()
    src  = "📡 Binance" if (USE_BINANCE and binance_client) else "🔵 محاكاة"
    text = f"💹 *الأسعار + النقاط* ({src})\n{'─'*24}\n"
    for r in results:
        trnd = "📈" if r["momentum"] > 0 else "📉"
        text += f"{trnd} `{r['sym']:6}` {fmt_p(r['sym'], r['price']):>12}  ⭐{r['score']:3}/100\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_analyze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📝 `/analyze <رمز>`", parse_mode="Markdown"); return
    sym = ctx.args[0].upper()
    if sym not in ASSETS:
        await update.message.reply_text(f"❌ `{sym}` غير موجود", parse_mode="Markdown"); return
    r    = score_coin(sym)
    bar  = "🟩" * (r["score"] // 10) + "⬜" * (10 - r["score"] // 10)
    text = (
        f"📊 *تحليل — `{sym}`*\n{'─'*22}\n"
        f"🏢 {ASSETS[sym]['name']}\n"
        f"💰 {fmt_p(sym, r['price'])}\n\n"
        f"⭐ *{r['score']}/100* {bar}\n"
        f"{r['recommendation']}\n\n"
        f"⚡ RSI: {r['rsi']:.1f}  💨 Mom: {r['momentum']:+.1f}%\n\n"
    )
    for d in r["details"]:
        text += f"  {d}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_halal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📝 `/halal <رمز>`", parse_mode="Markdown"); return
    sym = ctx.args[0].upper()
    if sym not in ASSETS:
        await update.message.reply_text(f"❌ `{sym}` غير موجود", parse_mode="Markdown"); return
    d      = ASSETS[sym]
    status = "✅ حلال" if d["halal"] else "⚠️ محل خلاف"
    await update.message.reply_text(
        f"🕌 *الفحص الشرعي — `{sym}`*\n"
        f"🏢 {d['name']}\n💰 {fmt_p(sym, price(sym))}\n"
        f"⚖️ {status}\n📝 {d['reason']}",
        parse_mode="Markdown")

async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txs = get_user(uid)["transactions"]
    if not txs:
        await update.message.reply_text("📋 لا توجد صفقات بعد"); return
    text = f"📋 *آخر 10 صفقات*\n{'─'*22}\n"
    for t in txs[-10:][::-1]:
        pnl_s = f" {pnl_e(t.get('pnl',0))}${t['pnl']:+.4f}" if "pnl" in t else ""
        text += f"\n{t['type']} {t['dir']} `{t['sym']}` ×{t['qty']}{pnl_s}\n  🕐 {t['date']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_user(uid)
    st   = u["stats"]
    pv   = portfolio_value(uid)
    tt   = st["total_trades"]
    wr   = round(st["wins"] / tt * 100, 1) if tt > 0 else 0
    scan = u["smart_scan"]

    text = (
        f"📉 *إحصائياتك*\n{'─'*22}\n"
        f"{mode_lbl(uid)}\n\n"
        f"💼 المحفظة: {fmt(pv)}\n"
        f"{pnl_e(pv-DEFAULT_CAPITAL)} العائد: ${pv-DEFAULT_CAPITAL:+,.2f} ({(pv-DEFAULT_CAPITAL)/DEFAULT_CAPITAL*100:+.2f}%)\n\n"
        f"📊 إجمالي الصفقات: {tt}\n"
        f"  🔍 مسح ذكي: {st['scan_trades']}\n"
        f"  👤 يدوية: {tt - st['scan_trades']}\n"
        f"✅ رابحة: {st['wins']}  ❌ خاسرة: {st['losses']}\n"
        f"🎯 نسبة الفوز: {wr:.1f}%\n"
        f"💵 صافي PnL: ${st['total_pnl']:+.4f}\n\n"
        f"🔍 المسح الذكي: {'🟢 نشط' if scan['active'] else '⚪ موقوف'}\n"
        f"  عمليات مسح: {scan['scan_count']}"
    )
    if st["per_sym"]:
        text += f"\n\n📊 *أداء العملات:*\n"
        sorted_syms = sorted(st["per_sym"].items(), key=lambda x: x[1]["pnl"], reverse=True)
        for sym, s in sorted_syms[:5]:
            wr2 = round(s["wins"] / s["trades"] * 100, 0) if s["trades"] > 0 else 0
            text += f"  {pnl_e(s['pnl'])} `{sym}` {s['trades']} صفقة | ${s['pnl']:+.4f} | {wr2:.0f}%\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    USERS[uid] = new_user()
    await update.message.reply_text(f"♻️ *تمت إعادة الضبط*\n💵 {fmt(DEFAULT_CAPITAL)}",
                                    parse_mode="Markdown")

async def cmd_setbinance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "📝 `/setbinance <API_KEY> <SECRET_KEY>`",
            parse_mode="Markdown"); return
    global BINANCE_API_KEY, BINANCE_API_SECRET, USE_BINANCE, binance_client
    try:
        from binance.client import Client
        tc = Client(args[0], args[1])
        tc.ping()
        BINANCE_API_KEY = args[0]; BINANCE_API_SECRET = args[1]
        USE_BINANCE = True; binance_client = tc
        bal = binance_balance("USDT")
        await update.message.reply_text(
            f"✅ *Binance متصل*\n💵 USDT: {fmt(bal)}\n`/livemode` للتداول الحقيقي",
            parse_mode="Markdown")
    except ImportError:
        await update.message.reply_text("❌ `pip install python-binance`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل: `{str(e)[:100]}`", parse_mode="Markdown")

async def cmd_livemode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not USE_BINANCE or not binance_client:
        await update.message.reply_text("❌ اربط Binance: `/setbinance KEY SECRET`",
                                        parse_mode="Markdown"); return
    get_user(uid)["mode"] = "live"
    await update.message.reply_text(
        f"🟢 *وضع Binance الحقيقي*\n⚠️ أموال حقيقية!\nابدأ بمسح ذكي: `/smartstart`",
        parse_mode="Markdown")

async def cmd_simmode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user(uid)["mode"] = "sim"
    await update.message.reply_text(f"🔵 *وضع المحاكاة*\n💵 {fmt(get_user(uid)['cash'])}",
                                    parse_mode="Markdown")

async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not USE_BINANCE or not binance_client:
        await update.message.reply_text("❌ Binance غير مرتبط"); return
    text = f"💰 *رصيد Binance*\n{'─'*18}\n"
    for a in ["USDT","BTC","ETH","BNB","XRP","SOL","ADA"]:
        b = binance_balance(a)
        if b > 0:
            text += f"  {a}: {b:.6f}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ════════════════════════════════════════════════════════
#  🔘  معالج الأزرار
# ════════════════════════════════════════════════════════
async def btn_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    uid  = q.from_user.id
    u    = get_user(uid)

    async def edit(text, kb=None):
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb or back),
                                  parse_mode="Markdown")

    if data == "main_menu":
        scan   = u["smart_scan"]
        status = "🟢 نشط" if scan["active"] else "⚪ موقوف"
        await q.edit_message_text(
            f"🕌 *بوت التداول الحلال v6.0*\n"
            f"{mode_lbl(uid)} | 🔍 {status}\n"
            f"💵 {fmt(u['cash'])} | 💼 {fmt(portfolio_value(uid))}",
            reply_markup=main_kb(), parse_mode="Markdown")

    elif data == "smart_menu":
        scan = u["smart_scan"]
        s    = "🟢 نشط" if scan["active"] else "⚪ موقوف"
        await edit(
            f"🔍 *المسح الذكي للسوق*\n\n"
            f"الحالة: {s}\n\n"
            f"*كيف يعمل:*\n"
            f"• يمسح {len(HALAL_LIST)} عملة حلال كل {SCAN_SEC}ث\n"
            f"• يحلل 7 مؤشرات فنية لكل عملة\n"
            f"• يعطي نقاطاً من 0 إلى 100\n"
            f"• يشتري تلقائياً عند نقاط ≥ {MIN_SCORE}\n"
            f"• يخرج تلقائياً عند ضعف الفرصة\n\n"
            f"*أوامر:*\n"
            f"`/smartstart` — تشغيل\n"
            f"`/smartstart 5 12 4` — مع إعدادات\n"
            f"`/smartstop` — إيقاف\n"
            f"`/scan` — مسح فوري\n"
            f"`/score BTC` — نقاط عملة\n"
            f"`/scanreport` — تقرير كامل"
        )

    elif data == "scan_results":
        results = scan_market()
        u["last_scan_results"] = results
        top5   = results[:5]
        text   = f"🔍 *نتائج المسح* — {now()}\n{'─'*24}\n"
        for i, r in enumerate(top5, 1):
            bar = "🟩" * (r["score"] // 20) + "⬜" * (5 - r["score"] // 20)
            text += f"\n{i}. `{r['sym']}` ⭐{r['score']}/100 {bar}\n   {r['recommendation']}\n"
        opps = get_best_opportunities(results)
        text += f"\n✅ فرص جاهزة: {len(opps)}\n"
        kb = [
            [InlineKeyboardButton("🔄 تحديث", callback_data="scan_results")],
            back[0],
        ]
        await edit(text, kb)

    elif data == "do_scan":
        results = scan_market()
        u["last_scan_results"] = results
        top3    = results[:3]
        text    = f"🔍 *مسح جديد* — {now()}\n{'─'*22}\n"
        for r in top3:
            text += f"\n`{r['sym']}` ⭐{r['score']}/100 {r['recommendation']}\n"
        await edit(text)

    elif data == "scan_report":
        results = scan_market()
        buy_syms = [r["sym"] for r in results if r["score"] >= MIN_SCORE]
        sell_syms = [r["sym"] for r in results if r["score"] <= 35]
        text = (
            f"📊 *تقرير السوق*\n{'─'*22}\n\n"
            f"✅ فرص شراء: {', '.join(f'`{s}`' for s in buy_syms) or 'لا يوجد'}\n\n"
            f"🔴 تجنب: {', '.join(f'`{s}`' for s in sell_syms) or 'لا يوجد'}\n\n"
            f"🕐 {now()}"
        )
        await edit(text)

    elif data == "smart_toggle":
        scan = u["smart_scan"]
        scan["active"] = not scan["active"]
        status = "🟢 نشط" if scan["active"] else "⚪ موقوف"
        await edit(f"🔍 المسح الذكي: {status}\n\n"
                   f"{'`/smartstop` لإيقافه' if scan['active'] else '`/smartstart` لتشغيله'}")

    elif data == "multi_menu":
        await edit(
            "🔀 *تداول متعدد يدوي*\n\n"
            "`/multiadd BTC sma 0.001 3 8`\n"
            "`/multistatus` — الحالة\n"
            "`/multistop` — إيقاف\n\n"
            "💡 للتداول الذكي الكامل: `/smartstart`"
        )

    elif data == "trade_menu":
        await edit(
            "📈 *التداول اليدوي*\n\n"
            "`/buy BTC 0.001`\n"
            "`/sell BTC 0.001`\n"
            "`/portfolio`  `/prices`\n\n"
            "🕌 فحص شرعي تلقائي"
        )

    elif data == "sl_tp_menu":
        await edit(
            f"🛑🎯 *Stop Loss & Take Profit*\n\n"
            f"`/sltp BTC 5 10` — SL 5% / TP 10%\n"
            f"`/orders` — الأوامر المعلقة\n\n"
            f"_مراقبة كل {MONITOR_SEC}ث_"
        )

    elif data == "portfolio":
        h = u["holdings"]
        if not h:
            await edit(f"💼 *فارغة*\n💵 {fmt(u['cash'])}\n\n🔍 `/smartstart`")
            return
        total = u["cash"]
        text  = f"💼 *محفظتك*\n{'─'*20}\n"
        for sym, d in h.items():
            cur  = price(sym)
            val  = cur * d["qty"]
            pnl  = (cur - d["avg_price"]) * d["qty"]
            total += val
            sc   = score_coin(sym)
            text += f"\n`{sym}` ⭐{sc['score']} {d['qty']}={fmt(val)} {pnl_e(pnl)}${pnl:+.4f}\n"
        text += f"\n{'─'*20}\n💵{fmt(u['cash'])} | 💼*{fmt(total)}*"
        await edit(text)

    elif data == "prices":
        results = scan_market()
        src  = "📡 Binance" if (USE_BINANCE and binance_client) else "🔵 محاكاة"
        text = f"💹 *الأسعار + النقاط* ({src})\n{'─'*22}\n"
        for r in results:
            trnd = "📈" if r["momentum"] > 0 else "📉"
            text += f"{trnd} `{r['sym']:6}` ⭐{r['score']:3}  {fmt_p(r['sym'], r['price']):>12}\n"
        kb = [[InlineKeyboardButton("🔄 تحديث", callback_data="prices")], back[0]]
        await edit(text, kb)

    elif data == "stats":
        st  = u["stats"]
        pv  = portfolio_value(uid)
        tt  = st["total_trades"]
        wr  = round(st["wins"] / tt * 100, 1) if tt > 0 else 0
        scan = u["smart_scan"]
        await edit(
            f"📉 *إحصائياتك*\n{'─'*20}\n"
            f"{mode_lbl(uid)}\n\n"
            f"💼 {fmt(pv)}\n"
            f"{pnl_e(pv-DEFAULT_CAPITAL)} ${pv-DEFAULT_CAPITAL:+,.2f}\n\n"
            f"📊 {tt} صفقة (🔍{st['scan_trades']} ذكي)\n"
            f"✅{st['wins']} ❌{st['losses']} | {wr:.1f}%\n"
            f"💵 PnL: ${st['total_pnl']:+.4f}\n\n"
            f"🔍 {'🟢 نشط' if scan['active'] else '⚪ موقوف'} | {scan['scan_count']} مسح"
        )

    elif data == "history":
        txs = u["transactions"][-8:][::-1]
        if not txs:
            await edit("📋 لا توجد صفقات بعد"); return
        text = f"📋 *آخر الصفقات*\n{'─'*20}\n"
        for t in txs:
            p = f" {pnl_e(t.get('pnl',0))}${t['pnl']:+.4f}" if "pnl" in t else ""
            text += f"\n{t['type']} {t['dir']} `{t['sym']}` ×{t['qty']}{p}\n"
        await edit(text)

    elif data == "mode_menu":
        b_stat = "🟢 متصل" if (USE_BINANCE and binance_client) else "⚪ غير مرتبط"
        await edit(
            f"🔌 *وضع التشغيل*\n\n"
            f"الحالي: {mode_lbl(uid)}\nBinance: {b_stat}\n\n"
            f"`/setbinance KEY SECRET`\n"
            f"`/livemode`  `/simmode`\n`/balance`"
        )

    elif data == "help":
        await edit(
            "📖 *الأوامر الرئيسية*\n\n"
            "*★ المسح الذكي:*\n"
            "`/smartstart 5 12`\n"
            "`/scan`  `/score BTC`\n\n"
            "*تداول:*\n"
            "`/buy BTC 0.001`\n"
            "`/sltp BTC 5 10`\n\n"
            "اكتب `/help` لشرح كامل"
        )

async def txt_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t   = update.message.text.upper().strip()
    uid = update.effective_user.id
    if t in ASSETS:
        r   = score_coin(t)
        bar = "🟩" * (r["score"] // 10) + "⬜" * (10 - r["score"] // 10)
        await update.message.reply_text(
            f"🔖 `{t}` — {ASSETS[t]['name']}\n"
            f"💰 {fmt_p(t, r['price'])}\n"
            f"⭐ *{r['score']}/100* {bar}\n"
            f"{r['recommendation']}\n"
            f"⚡ RSI:{r['rsi']:.0f}  💨 {r['momentum']:+.1f}%",
            parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "❓ أرسل رمز عملة مثل `BTC` أو `/help`",
            parse_mode="Markdown")

# ════════════════════════════════════════════════════════
#  🚀  تشغيل البوت
# ════════════════════════════════════════════════════════
def main():
    if BINANCE_API_KEY and BINANCE_API_SECRET:
        init_binance()
    else:
        logger.info("🔵 وضع المحاكاة")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    cmds = [
        ("start",          cmd_start),
        ("help",           cmd_help),
        # ★ المسح الذكي
        ("smartstart",     cmd_smartstart),
        ("smartstop",      cmd_smartstop),
        ("smartstatus",    cmd_smartstatus),
        ("scan",           cmd_scan),
        ("scanreport",     cmd_scanreport),
        ("score",          cmd_score),
        # تداول متعدد
        ("multiadd",       cmd_multiadd),
        ("multistatus",    cmd_multistatus),
        ("multistop",      cmd_multistop),
        # تداول يدوي
        ("buy",            cmd_buy),
        ("sell",           cmd_sell),
        ("portfolio",      cmd_portfolio),
        # SL/TP
        ("sltp",           cmd_sltp),
        ("orders",         cmd_orders),
        # تحليل
        ("analyze",        cmd_analyze),
        ("halal",          cmd_halal),
        ("prices",         cmd_prices),
        # أخرى
        ("history",        cmd_history),
        ("stats",          cmd_stats),
        ("reset",          cmd_reset),
        # Binance
        ("setbinance",     cmd_setbinance),
        ("livemode",       cmd_livemode),
        ("simmode",        cmd_simmode),
        ("balance",        cmd_balance),
    ]
    for name, handler in cmds:
        app.add_handler(CommandHandler(name, handler))

    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))

    jq = app.job_queue
    jq.run_repeating(job_prices,       interval=PRICE_UPDATE_SEC, first=3)
    jq.run_repeating(job_monitor_sl_tp, interval=MONITOR_SEC,     first=5)
    jq.run_repeating(job_smart_scan,   interval=SCAN_SEC,         first=15)

    print("🕌 بوت التداول الحلال v6.0 يعمل!")
    print(f"   🔍 مسح ذكي:    كل {SCAN_SEC}ث")
    print(f"   🛑 SL/TP:      كل {MONITOR_SEC}ث")
    print(f"   💹 الأسعار:    كل {PRICE_UPDATE_SEC}ث")
    print(f"   📊 عملات حلال: {len(HALAL_LIST)}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

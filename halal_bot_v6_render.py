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
import urllib.request
import urllib.error
import json
import asyncio
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

# ════════════════════════════════════════════════════════
#  🌐  جلب الأسعار الحقيقية مجاناً — CoinGecko API
# ════════════════════════════════════════════════════════

# ربط رموز العملات بمعرفات CoinGecko
COINGECKO_IDS = {
    "BTC":   "bitcoin",
    "ETH":   "ethereum",
    "BNB":   "binancecoin",
    "XRP":   "ripple",
    "ADA":   "cardano",
    "SOL":   "solana",
    "DOT":   "polkadot",
    "LINK":  "chainlink",
    "AVAX":  "avalanche-2",
    "MATIC": "matic-network",
    "ATOM":  "cosmos",
    "ALGO":  "algorand",
}

# حالة جلب الأسعار
LIVE_SIM_PRICES: dict = {}   # آخر أسعار حقيقية تم جلبها
LAST_FETCH_TIME: str  = "لم يتم بعد"
FETCH_SUCCESS:   bool = False

LAST_FETCH_EPOCH: float = 0.0  # وقت آخر جلب

def fetch_real_prices() -> bool:
    """
    يجلب الأسعار الحقيقية من CoinGecko مجاناً
    ويبني تاريخاً واقعياً للمؤشرات الفنية
    """
    global LIVE_SIM_PRICES, LAST_FETCH_TIME, FETCH_SUCCESS, LAST_FETCH_EPOCH
    import time

    # حماية من الطلبات المتكررة
    if time.time() - LAST_FETCH_EPOCH < 10:
        return FETCH_SUCCESS

    try:
        ids = ",".join(COINGECKO_IDS.values())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "HalalBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        for sym, cg_id in COINGECKO_IDS.items():
            if cg_id not in data or "usd" not in data[cg_id]:
                continue
            px = float(data[cg_id]["usd"])
            if px <= 0:
                continue

            # نسبة التغير في 24 ساعة
            change_24h = float(data[cg_id].get("usd_24h_change", 0) or 0)

            LIVE_SIM_PRICES[sym] = px
            ASSETS[sym]["price"] = px

            # ── بناء تاريخ واقعي ──────────────────────────
            # نستنتج سعر الأمس من نسبة التغير الحقيقية
            # ثم نملأ 100 نقطة بتدرج واقعي بينهما
            prev_px = px / (1 + change_24h / 100) if change_24h != -100 else px
            hist_prices = []
            for i in range(100):
                # تدرج خطي من سعر الأمس لسعر الآن
                # مع تذبذب صغير جداً 0.05% لتوليد إشارات فنية
                t     = i / 99
                base  = prev_px + (px - prev_px) * t
                noise = random.gauss(0, base * 0.0005)
                hist_prices.append(round(max(base + noise, 0.000001), 8)
)

            # تحديث التاريخ بالكامل
            HISTORY[sym] = deque(hist_prices, maxlen=100)

        LAST_FETCH_TIME  = datetime.now().strftime("%H:%M:%S")
        LAST_FETCH_EPOCH = time.time()
        FETCH_SUCCESS    = True
        logger.info(f"✅ أسعار حقيقية + تاريخ واقعي: {len(LIVE_SIM_PRICES)} عملة — {LAST_FETCH_TIME}")
        return True

    except Exception as e:
        FETCH_SUCCESS = False
        logger.warning(f"⚠️ فشل جلب الأسعار الحقيقية: {e}")
        return False

# جلب الأسعار عند بدء التشغيل
threading.Thread(target=fetch_real_prices, daemon=True).start()

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

# ─── عملة التداول الأساسية ───────────────────────────────
# غيّرها إلى "USDC" إذا أردت التداول بـ USDC
QUOTE_CURRENCY     = "USDT"   # USDT أو USDC
PRICE_UPDATE_SEC   = 15       # تحديث الأسعار
MONITOR_SEC        = 20       # فحص SL/TP
SCAN_SEC           = 30       # مسح السوق
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
        t = binance_client.get_symbol_ticker(symbol=sym + QUOTE_CURRENCY)
        return float(t["price"])
    except:
        return ASSETS[sym]["price"]

def binance_balance(asset: str = None) -> float:
    if asset is None:
        asset = QUOTE_CURRENCY
    try:
        info = binance_client.get_asset_balance(asset=asset)
        return float(info["free"]) if info else 0.0
    except:
        return 0.0

def binance_order(sym: str, side: str, qty: float) -> dict:
    try:
        from binance.enums import SIDE_BUY, SIDE_SELL
        order = binance_client.order_market(
            symbol=sym + QUOTE_CURRENCY,
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
        # ── وضع Binance الحقيقي ──────────────────────────
        if USE_BINANCE and binance_client and data["halal"]:
            p = binance_price(sym)
            if p > 0:
                HISTORY[sym].append(p)
                ASSETS[sym]["price"] = p
            continue

        # ── وضع المحاكاة — أسعار حقيقية 100% ────────────
        if sym in LIVE_SIM_PRICES and LIVE_SIM_PRICES[sym] > 0:
            px = LIVE_SIM_PRICES[sym]
            # أضف السعر الحقيقي للتاريخ (التاريخ يتحرك مع الوقت)
            HISTORY[sym].append(px)
            ASSETS[sym]["price"] = px
        else:
            # احتياطي — ثبّت آخر سعر معروف
            HISTORY[sym].append(HISTORY[sym][-1])
            ASSETS[sym]["price"] = HISTORY[sym][-1]

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
        # سجّل وقت الخروج لمنع الدخول مجدداً لمدة 5 دقائق
        import time as _t
        u.setdefault("recent_exits", {})[sym] = _t.time()

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

async def job_fetch_real_prices(ctx: ContextTypes.DEFAULT_TYPE):
    """تحديث الأسعار الحقيقية من CoinGecko كل 5 دقائق"""
    threading.Thread(target=fetch_real_prices, daemon=True).start()

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
            if sym in u["multi_auto"]:
                continue

            # ⏱️ حماية — لا تخرج قبل مرور 3 دورات مسح على الأقل
            holding = u["holdings"][sym]
            holding.setdefault("scan_count", 0)
            holding["scan_count"] += 1
            if holding["scan_count"] < 3:
                continue

            result = next((r for r in scan_results if r["sym"] == sym), None)

            # الخروج فقط إذا كانت النقاط ضعيفة في دورتين متتاليتين
            holding.setdefault("weak_count", 0)
            if result and result["score"] <= 30:
                holding["weak_count"] += 1
            else:
                holding["weak_count"] = 0  # إعادة العداد إذا تحسنت النقاط

            if holding["weak_count"] < 2:
                continue  # انتظر دورة أخرى للتأكيد

            qty = holding["qty"]
            res = do_sell(uid, sym, qty, auto=True, reason="خروج تلقائي")
            if res["ok"]:
                try:
                    await ctx.bot.send_message(uid,
                        f"🔍 *مسح ذكي — خروج تلقائي*\n{'─'*22}\n"
                        f"📌 `{sym}` | نقاط: {result['score']}/100\n"
                        f"⚠️ الفرصة ضعفت (دورتان متتاليتان) — تم الخروج\n"
                        f"💰 {fmt_p(sym, res['price'])}\n"
                        f"{pnl_e(res['pnl'])} ${res['pnl']:+.4f} ({res['pnl_pct']:+.2f}%)\n"
                        f"💵 {fmt(get_user(uid)['cash'])}",
                        parse_mode="Markdown")
                except Exception:
                    pass

        # ── الجزء 2: الدخول في فرص جديدة ────────────────
        # ⏱️ حماية — لا تدخل في عملة خرجت منها مؤخراً
        recent_exits = u.setdefault("recent_exits", {})
        import time as _time
        now_ts = _time.time()
        # امسح الخروجات القديمة (أكثر من 5 دقائق)
        recent_exits = {s: t for s, t in recent_exits.items() if now_ts - t < 300}
        u["recent_exits"] = recent_exits

        if current_pos >= max_pos:
            continue

        opportunities = get_best_opportunities(scan_results, max_pos - current_pos)
        for opp in opportunities:
            sym = opp["sym"]
            if sym in u["holdings"]:
                continue
            if sym in u["multi_auto"] and u["multi_auto"][sym]["active"]:
                continue
            # تجاهل العملات التي خرجنا منها مؤخراً
            if sym in recent_exits:
                continue

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
        [InlineKeyboardButton("🔍 مسح ذكي ★",           callback_data="smart_menu"),
         InlineKeyboardButton("📊 نتائج المسح",          callback_data="scan_results")],
        [InlineKeyboardButton("⚙️ إعدادات الصفقات",     callback_data="cfg_menu"),
         InlineKeyboardButton("💰 المخاطرة",             callback_data="risk_menu")],
        [InlineKeyboardButton("📈 تداول يدوي",           callback_data="trade_menu"),
         InlineKeyboardButton("🛑 Stop Loss / 🎯 TP",    callback_data="sl_tp_menu")],
        [InlineKeyboardButton("💼 المحفظة",              callback_data="portfolio"),
         InlineKeyboardButton("💹 الأسعار",              callback_data="prices")],
        [InlineKeyboardButton("📉 الإحصائيات",           callback_data="stats"),
         InlineKeyboardButton("📋 السجل",                callback_data="history")],
        [InlineKeyboardButton("🔴 بيع الكل طارئ",        callback_data="sellall_confirm")],
        [InlineKeyboardButton("🔌 الإعدادات العامة",     callback_data="mode_menu"),
         InlineKeyboardButton("❓ مساعدة",               callback_data="help")],
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

async def cmd_setrisk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    تعديل نسبة المخاطرة لكل صفقة تلقائية
    /setrisk        ← عرض الإعداد الحالي
    /setrisk 10     ← تعيين 10% لكل صفقة
    /setrisk 5 3    ← 5% لكل صفقة + أقصى 3 صفقات
    """
    uid  = update.effective_user.id
    u    = get_user(uid)
    scan = u["smart_scan"]

    # عرض الإعداد الحالي فقط
    if not ctx.args:
        cur_risk = scan["risk_pct"] * 100
        cur_max  = scan["max_positions"]
        cash     = u["cash"]
        per_trade = cash * scan["risk_pct"]

        text = (
            f"💰 *إعداد المخاطرة الحالي*\n{'─'*26}\n\n"
            f"📊 نسبة كل صفقة: *{cur_risk:.1f}%*\n"
            f"📦 أقصى صفقات: *{cur_max}*\n"
            f"💵 رصيدك الحالي: {fmt(cash)}\n"
            f"💸 مبلغ كل صفقة: *{fmt(per_trade)}*\n"
            f"📉 أقصى خسارة ممكنة: *{fmt(per_trade * scan['sl_pct'] / 100)}*\n\n"
            f"*لتغيير النسبة:*\n"
            f"`/setrisk 5`  ← 5% لكل صفقة\n"
            f"`/setrisk 10` ← 10% لكل صفقة\n"
            f"`/setrisk 3 5` ← 3% × أقصى 5 صفقات\n\n"
            f"*نسب مقترحة:*\n"
            f"🟢 متحفظ: 2-5%\n"
            f"🟡 معتدل: 5-10%\n"
            f"🔴 مغامر: 10-20%\n"
            f"⚠️ لا تتجاوز 20% لكل صفقة"
        )
        kb = [
            [InlineKeyboardButton("2%  متحفظ",  callback_data="risk_2"),
             InlineKeyboardButton("5%  معتدل",   callback_data="risk_5")],
            [InlineKeyboardButton("10% نشط",     callback_data="risk_10"),
             InlineKeyboardButton("15% مغامر",   callback_data="risk_15")],
            [InlineKeyboardButton("🔢 نسبة مخصصة — أرسل /setrisk <نسبة>", callback_data="noop")],
            back[0],
        ]
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    # تعيين نسبة جديدة
    try:
        new_risk = float(ctx.args[0])
        assert 0.5 <= new_risk <= 50, "النسبة يجب بين 0.5% و 50%"
    except (ValueError, AssertionError) as e:
        await update.message.reply_text(
            f"❌ نسبة غير صالحة\n{e}\n\nمثال: `/setrisk 5`",
            parse_mode="Markdown"); return

    new_max = scan["max_positions"]
    if len(ctx.args) >= 2:
        try:
            new_max = int(ctx.args[1])
            assert 1 <= new_max <= 10
        except:
            await update.message.reply_text("❌ أقصى الصفقات يجب بين 1 و 10"); return

    # تطبيق الإعدادات
    old_risk          = scan["risk_pct"] * 100
    scan["risk_pct"]  = new_risk / 100
    scan["max_positions"] = new_max

    cash      = u["cash"]
    per_trade = cash * scan["risk_pct"]
    max_risk  = per_trade * new_max
    max_risk_pct = max_risk / cash * 100

    # تحديد مستوى المخاطرة
    if new_risk <= 5:
        level = "🟢 متحفظ — آمن"
    elif new_risk <= 10:
        level = "🟡 معتدل — مقبول"
    elif new_risk <= 20:
        level = "🟠 مغامر — انتبه"
    else:
        level = "🔴 عالي جداً — خطر!"

    await update.message.reply_text(
        f"✅ *تم تحديث إعدادات المخاطرة*\n{'─'*26}\n\n"
        f"📊 النسبة القديمة: {old_risk:.1f}%\n"
        f"📊 النسبة الجديدة: *{new_risk:.1f}%*\n"
        f"📦 أقصى صفقات: *{new_max}*\n\n"
        f"*📐 الحسابات:*\n"
        f"💵 رصيدك: {fmt(cash)}\n"
        f"💸 مبلغ كل صفقة: *{fmt(per_trade)}*\n"
        f"📉 أقصى خسارة/صفقة ({scan['sl_pct']:.0f}%): "
        f"*{fmt(per_trade * scan['sl_pct'] / 100)}*\n"
        f"📊 أقصى رصيد في خطر: *{fmt(max_risk)} ({max_risk_pct:.1f}%)*\n\n"
        f"⚖️ مستوى المخاطرة: {level}\n\n"
        f"_سيُطبَّق على الصفقات الجديدة فقط_",
        parse_mode="Markdown",
    )

async def cmd_smartstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_user(uid)
    scan = u["smart_scan"]
    pos  = open_positions(uid)

    status = "🟢 نشط" if scan["active"] else "⚪ موقوف"
    cash   = u["cash"]
    per_trade = cash * scan["risk_pct"]

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
        f"💰 مخاطرة/صفقة: *{scan['risk_pct']*100:.1f}%* ({fmt(per_trade)})\n\n"
        f"*📊 الصفقات:*\n"
        f"مفتوحة: {pos}/{scan['max_positions']}\n"
        f"صفقات المسح الذكي: {u['stats']['scan_trades']}\n"
        f"💵 الرصيد: {fmt(cash)}\n"
        f"💼 المحفظة: {fmt(portfolio_value(uid))}"
    )

    kb = [
        [InlineKeyboardButton("⏹️ إيقاف" if scan["active"] else "▶️ تشغيل",
                               callback_data="smart_toggle"),
         InlineKeyboardButton("💰 تعديل المخاطرة", callback_data="risk_menu")],
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

async def cmd_editor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    لوحة تعديل الصفقات التفاعلية
    /editor          ← فتح اللوحة
    /editor BTC      ← تعديل صفقة BTC مباشرة
    """
    uid = update.effective_user.id
    u   = get_user(uid)
    h   = u["holdings"]

    # إذا طُلب تعديل عملة محددة
    if ctx.args:
        sym = ctx.args[0].upper()
        if sym not in h:
            await update.message.reply_text(
                f"❌ لا تملك `{sym}` حالياً\n\n"
                f"💼 عملاتك: {', '.join(f'`{s}`' for s in h) or 'لا شيء'}",
                parse_mode="Markdown"); return
        await _show_trade_editor(update.message, uid, sym)
        return

    # عرض لوحة المحفظة الكاملة
    pv    = portfolio_value(uid)
    ov    = pv - DEFAULT_CAPITAL
    text  = (
        f"✏️ *لوحة تعديل الصفقات*\n{'─'*28}\n\n"
        f"💵 الرصيد النقدي: *{fmt(u['cash'])}*\n"
        f"💼 إجمالي المحفظة: *{fmt(pv)}*\n"
        f"{pnl_e(ov)} العائد: *${ov:+,.2f}* ({ov/DEFAULT_CAPITAL*100:+.2f}%)\n\n"
    )

    if not h:
        text += "📭 لا توجد صفقات مفتوحة\n\n`/smartstart` للبدء تلقائياً"
        await update.message.reply_text(text, parse_mode="Markdown"); return

    # أزرار لكل عملة مفتوحة
    text += f"*اختر صفقة للتعديل:*\n"
    for sym, d in h.items():
        cur  = price(sym)
        pnl  = (cur - d["avg_price"]) * d["qty"]
        pct  = (cur - d["avg_price"]) / d["avg_price"] * 100
        text += f"\n{pnl_e(pnl)} `{sym}` {d['qty']} × {fmt_p(sym, cur)} → {pnl_e(pnl)}${pnl:+.4f} ({pct:+.2f}%)\n"

    kb = []
    row = []
    for i, sym in enumerate(h.keys()):
        cur = price(sym)
        pnl = (cur - h[sym]["avg_price"]) * h[sym]["qty"]
        icon = "📈" if pnl >= 0 else "📉"
        row.append(InlineKeyboardButton(f"{icon} {sym}", callback_data=f"edit_trade_{sym}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("💰 تعديل الرصيد النقدي", callback_data="edit_cash")])
    kb.append([InlineKeyboardButton("🔴 بيع الكل",            callback_data="sellall_confirm")])
    kb.append(back[0])

    await update.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def _show_trade_editor(msg_obj, uid: int, sym: str, edit_msg=False):
    """عرض لوحة تعديل صفقة محددة"""
    u   = get_user(uid)
    h   = u["holdings"]
    if sym not in h:
        return
    d    = h[sym]
    cur  = price(sym)
    val  = cur * d["qty"]
    pnl  = (cur - d["avg_price"]) * d["qty"]
    pct  = (cur - d["avg_price"]) / d["avg_price"] * 100
    o    = u["orders"].get(sym, {})
    sc   = score_coin(sym)

    sl_info = f"{o['sl_pct']:.1f}% (${fmt_p(sym, o['sl_price'])})" if "sl_pct" in o else "غير محدد"
    tp_info = f"{o['tp_pct']:.1f}% (${fmt_p(sym, o['tp_price'])})" if "tp_pct" in o else "غير محدد"

    text = (
        f"✏️ *تعديل صفقة `{sym}`*\n{'─'*28}\n\n"
        f"🏢 {ASSETS[sym]['name']}\n"
        f"⭐ النقاط: {sc['score']}/100 | {sc['recommendation']}\n\n"
        f"*📊 تفاصيل الصفقة:*\n"
        f"📦 الكمية: *{d['qty']}*\n"
        f"💰 سعر الدخول: *{fmt_p(sym, d['avg_price'])}*\n"
        f"💹 السعر الحالي: *{fmt_p(sym, cur)}*\n"
        f"💵 القيمة الحالية: *{fmt(val)}*\n"
        f"{pnl_e(pnl)} الربح/الخسارة: *${pnl:+.4f}* ({pct:+.2f}%)\n\n"
        f"*🛡️ أوامر الحماية:*\n"
        f"🛑 Stop Loss: *{sl_info}*\n"
        f"🎯 Take Profit: *{tp_info}*\n\n"
        f"*ماذا تريد أن تفعل؟*"
    )
    kb = [
        [InlineKeyboardButton("📦 تعديل الكمية",        callback_data=f"ed_qty_{sym}"),
         InlineKeyboardButton("💰 تعديل سعر الدخول",    callback_data=f"ed_entry_{sym}")],
        [InlineKeyboardButton("🛑 تعديل Stop Loss",      callback_data=f"ed_sl_{sym}"),
         InlineKeyboardButton("🎯 تعديل Take Profit",    callback_data=f"ed_tp_{sym}")],
        [InlineKeyboardButton("➕ إضافة كمية",           callback_data=f"ed_addqty_{sym}"),
         InlineKeyboardButton("➖ بيع جزء",              callback_data=f"ed_sellpart_{sym}")],
        [InlineKeyboardButton("🗑️ حذف الصفقة كاملاً",   callback_data=f"ed_delete_{sym}"),
         InlineKeyboardButton("🔴 بيع الكل",             callback_data=f"ed_sellall_{sym}")],
        [InlineKeyboardButton("◀️ رجوع للمحفظة",        callback_data="editor_main")],
    ]
    if edit_msg:
        await msg_obj.edit_text(text, reply_markup=InlineKeyboardMarkup(kb),
                                parse_mode="Markdown")
    else:
        await msg_obj.reply_text(text, reply_markup=InlineKeyboardMarkup(kb),
                                 parse_mode="Markdown")

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
    """لوحة إحصائيات شاملة — تعرض كل المعلومات"""
    uid  = update.effective_user.id
    u    = get_user(uid)
    st   = u["stats"]
    scan = u["smart_scan"]
    pv   = portfolio_value(uid)
    tt   = st["total_trades"]
    wr   = round(st["wins"] / tt * 100, 1) if tt > 0 else 0
    pos  = open_positions(uid)

    kb = [
        [InlineKeyboardButton("📡 حالة الأسعار",      callback_data="stats_prices"),
         InlineKeyboardButton("🔍 إحصائيات المسح",    callback_data="stats_scan")],
        [InlineKeyboardButton("💼 تفاصيل الصفقات",    callback_data="stats_trades"),
         InlineKeyboardButton("📊 أداء العملات",      callback_data="stats_symbols")],
        [InlineKeyboardButton("⚙️ الإعدادات المطبقة", callback_data="stats_settings"),
         InlineKeyboardButton("🔄 تحديث الكل",        callback_data="stats_main")],
        back[0],
    ]

    ov = pv - DEFAULT_CAPITAL
    await update.message.reply_text(
        f"📊 *لوحة الإحصائيات الشاملة*\n{'─'*28}\n\n"
        f"👤 وضع التشغيل: {mode_lbl(uid)}\n"
        f"📡 مصدر الأسعار: {'🟢 CoinGecko حقيقي' if FETCH_SUCCESS else '🔵 محاكاة عشوائية'}\n"
        f"🔍 المسح الذكي: {'🟢 نشط' if scan['active'] else '⚪ موقوف'}\n\n"
        f"💵 الرصيد: *{fmt(u['cash'])}*\n"
        f"💼 المحفظة: *{fmt(pv)}*\n"
        f"{pnl_e(ov)} العائد الإجمالي: *${ov:+,.2f}* ({ov/DEFAULT_CAPITAL*100:+.2f}%)\n\n"
        f"📈 الصفقات: {tt} | ✅{st['wins']} ❌{st['losses']} | 🎯{wr:.1f}%\n"
        f"📌 صفقات مفتوحة: {pos}/{scan['max_positions']}\n\n"
        f"_اختر قسماً للتفاصيل 👇_",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def cmd_dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """نفس /stats — اختصار"""
    await cmd_stats(update, ctx)

async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """لوحة إعدادات الصفقات الشاملة"""
    uid  = update.effective_user.id
    u    = get_user(uid)
    scan = u["smart_scan"]
    await update.message.reply_text(
        f"⚙️ *لوحة إعدادات الصفقات*\n{'─'*28}\n\n"
        f"اختر القسم الذي تريد تعديله:",
        reply_markup=_cfg_kb(scan),
        parse_mode="Markdown"
    )

def _cfg_kb(scan: dict) -> InlineKeyboardMarkup:
    """لوحة مفاتيح إعدادات الصفقات"""
    active = "🟢" if scan["active"] else "⚪"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛑 Stop Loss: {scan['sl_pct']:.1f}%",   callback_data="cfg_sl"),
         InlineKeyboardButton(f"🎯 Take Profit: {scan['tp_pct']:.1f}%", callback_data="cfg_tp")],
        [InlineKeyboardButton(f"💰 مخاطرة/صفقة: {scan['risk_pct']*100:.1f}%", callback_data="cfg_risk"),
         InlineKeyboardButton(f"📦 أقصى صفقات: {scan['max_positions']}", callback_data="cfg_maxpos")],
        [InlineKeyboardButton(f"⭐ حد النقاط: {scan['min_score']}/100",  callback_data="cfg_minscore"),
         InlineKeyboardButton(f"🔍 تكرار المسح: {SCAN_SEC}ث",           callback_data="cfg_scan_interval")],
        [InlineKeyboardButton(f"🛑 وقت SL/TP: {MONITOR_SEC}ث",         callback_data="cfg_monitor_interval"),
         InlineKeyboardButton(f"💹 وقت الأسعار: {PRICE_UPDATE_SEC}ث",  callback_data="cfg_prices_interval")],
        [InlineKeyboardButton(f"💱 العملة: {QUOTE_CURRENCY}",            callback_data="cfg_currency"),
         InlineKeyboardButton(f"{active} المسح الذكي",                   callback_data="cfg_toggle_scan")],
        [InlineKeyboardButton("📋 عرض الكل",    callback_data="cfg_show_all"),
         InlineKeyboardButton("♻️ إعادة الضبط", callback_data="cfg_reset_confirm")],
        back[0],
    ])

async def cmd_sellall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    بيع جميع العملات دفعة واحدة وإيقاف كل التداول التلقائي
    /sellall         ← يطلب تأكيداً أولاً
    /sellall confirm ← ينفذ مباشرة
    """
    uid  = update.effective_user.id
    u    = get_user(uid)
    h    = u["holdings"]

    if not h:
        await update.message.reply_text(
            "💼 *المحفظة فارغة*\nلا توجد عملات للبيع.",
            parse_mode="Markdown"); return

    # ── طلب تأكيد قبل التنفيذ ────────────────────────────
    if not ctx.args or ctx.args[0].lower() != "confirm":
        total_val = sum(price(s) * d["qty"] for s, d in h.items())
        text = (
            f"⚠️ *تأكيد بيع الكل*\n{'─'*26}\n\n"
            f"سيتم بيع *{len(h)} عملة* فوراً:\n\n"
        )
        for sym, d in h.items():
            cur  = price(sym)
            val  = cur * d["qty"]
            pnl  = (cur - d["avg_price"]) * d["qty"]
            text += f"  🔖 `{sym}` {d['qty']} = {fmt(val)} {pnl_e(pnl)}${pnl:+.4f}\n"
        text += (
            f"\n{'─'*26}\n"
            f"💵 إجمالي العائد المتوقع: *{fmt(total_val)}*\n\n"
            f"⚠️ سيتم أيضاً:\n"
            f"• إيقاف المسح الذكي\n"
            f"• إيقاف التداول المتعدد\n"
            f"• حذف جميع أوامر SL/TP\n\n"
            f"للتأكيد اضغط الزر أدناه أو أرسل:\n"
            f"`/sellall confirm`"
        )
        kb = [
            [InlineKeyboardButton("🔴 بيع الكل — تأكيد", callback_data="sellall_confirm")],
            [InlineKeyboardButton("❌ إلغاء",             callback_data="main_menu")],
        ]
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    # ── تنفيذ البيع ──────────────────────────────────────
    await _execute_sellall(uid, update.message)

async def _execute_sellall(uid: int, msg_obj):
    """دالة مساعدة تنفذ بيع الكل وترسل التقرير"""
    u      = get_user(uid)
    h      = u["holdings"]
    results = []
    total_revenue = 0.0
    total_pnl     = 0.0

    # إيقاف كل التداول التلقائي أولاً
    u["smart_scan"]["active"] = False
    for cfg in u["multi_auto"].values():
        cfg["active"] = False

    # بيع كل عملة
    for sym in list(h.keys()):
        qty = h[sym]["qty"]
        res = do_sell(uid, sym, qty, auto=True, reason="بيع الكل")
        if res["ok"]:
            results.append({
                "sym": sym, "qty": qty,
                "price": res["price"],
                "pnl": res["pnl"],
                "pnl_pct": res["pnl_pct"],
            })
            total_revenue += res["revenue"]
            total_pnl     += res["pnl"]

    # حذف جميع الأوامر
    u["orders"].clear()

    # إعداد التقرير
    if not results:
        text = "❌ لم يتم تنفيذ أي بيع"
    else:
        winners = [r for r in results if r["pnl"] >= 0]
        losers  = [r for r in results if r["pnl"] < 0]
        text = (
            f"✅ *تم بيع الكل بنجاح!*\n{'─'*26}\n\n"
            f"📊 *تفاصيل الصفقات:*\n"
        )
        for r in results:
            pe   = pnl_e(r["pnl"])
            text += (
                f"\n{pe} `{r['sym']}`\n"
                f"   {r['qty']} @ {fmt_p(r['sym'], r['price'])}\n"
                f"   ${r['pnl']:+.4f} ({r['pnl_pct']:+.2f}%)\n"
            )
        text += (
            f"\n{'─'*26}\n"
            f"💵 إجمالي العائد: *{fmt(total_revenue)}*\n"
            f"{pnl_e(total_pnl)} صافي الربح/الخسارة: *${total_pnl:+.4f}*\n\n"
            f"📈 رابحة: {len(winners)}  📉 خاسرة: {len(losers)}\n\n"
            f"💳 الرصيد الجديد: *{fmt(u['cash'])}*\n"
            f"⏹️ تم إيقاف التداول التلقائي\n"
            f"🗑️ تم حذف جميع أوامر SL/TP"
        )

    try:
        await msg_obj.reply_text(text, parse_mode="Markdown")
    except:
        await msg_obj.edit_text(text, parse_mode="Markdown")

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

async def cmd_setcurrency(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    تغيير عملة التداول الأساسية
    /setcurrency       ← عرض العملة الحالية
    /setcurrency usdt  ← التداول بـ USDT
    /setcurrency usdc  ← التداول بـ USDC
    """
    global QUOTE_CURRENCY

    if not ctx.args:
        kb = [
            [InlineKeyboardButton("💵 USDT — تيثر",    callback_data="currency_USDT"),
             InlineKeyboardButton("💵 USDC — يو إس دي سي", callback_data="currency_USDC")],
            back[0],
        ]
        await update.message.reply_text(
            f"💱 *عملة التداول الحالية: `{QUOTE_CURRENCY}`*\n{'─'*26}\n\n"
            f"*الفرق بين USDT و USDC:*\n\n"
            f"💵 *USDT (Tether)*\n"
            f"  • الأكثر سيولة في السوق\n"
            f"  • متاح في جميع أزواج العملات\n"
            f"  • الافتراضي في معظم المنصات\n\n"
            f"💵 *USDC (USD Coin)*\n"
            f"  • أكثر شفافية وتنظيماً\n"
            f"  • صادر عن Circle & Coinbase\n"
            f"  • سيولة أقل من USDT\n"
            f"  • بعض الأزواج غير متاحة\n\n"
            f"*لتغيير العملة:*\n"
            f"`/setcurrency usdt`\n"
            f"`/setcurrency usdc`",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return

    new_currency = ctx.args[0].upper()
    if new_currency not in ("USDT", "USDC"):
        await update.message.reply_text(
            "❌ عملة غير مدعومة\nاستخدم: `USDT` أو `USDC`",
            parse_mode="Markdown"); return

    old_currency   = QUOTE_CURRENCY
    QUOTE_CURRENCY = new_currency

    if new_currency == "USDC":
        note = (
            "⚠️ *ملاحظة USDC:*\n"
            "بعض الأزواج قد لا تكون متاحة على Binance\n"
            "مثال: BTCUSDC ✅  XRPUSDC ❌\n"
            "البوت سيتجاوز الأزواج غير المتاحة تلقائياً"
        )
    else:
        note = "✅ USDT متاح لجميع الأزواج"

    await update.message.reply_text(
        f"✅ *تم تغيير عملة التداول*\n{'─'*24}\n\n"
        f"من: `{old_currency}` ← إلى: `{new_currency}`\n\n"
        f"{note}\n\n"
        f"_جميع الصفقات الجديدة ستستخدم {new_currency}_",
        parse_mode="Markdown"
    )

async def cmd_setinterval(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    تعديل أوقات المسح والتنفيذ
    /setinterval              ← عرض الإعدادات الحالية
    /setinterval scan 30      ← مسح كل 30 ثانية
    /setinterval monitor 15   ← فحص SL/TP كل 15 ثانية
    /setinterval prices 10    ← تحديث الأسعار كل 10 ثواني
    """
    global SCAN_SEC, MONITOR_SEC, PRICE_UPDATE_SEC

    # ── عرض الإعدادات الحالية ────────────────────────────
    if not ctx.args:
        await update.message.reply_text(
            f"⏱️ *إعدادات التوقيت الحالية*\n{'─'*26}\n\n"
            f"🔍 وقت المسح:        *{SCAN_SEC}ث*\n"
            f"🛑 فحص SL/TP:       *{MONITOR_SEC}ث*\n"
            f"💹 تحديث الأسعار:   *{PRICE_UPDATE_SEC}ث*\n\n"
            f"*لتغيير الأوقات:*\n"
            f"`/setinterval scan <ثواني>`\n"
            f"`/setinterval monitor <ثواني>`\n"
            f"`/setinterval prices <ثواني>`\n\n"
            f"*أمثلة:*\n"
            f"`/setinterval scan 30` ← مسح كل 30ث\n"
            f"`/setinterval scan 60` ← مسح كل دقيقة\n"
            f"`/setinterval monitor 15` ← SL/TP كل 15ث\n\n"
            f"*حدود مسموحة:*\n"
            f"🔍 المسح: 10ث — 300ث\n"
            f"🛑 SL/TP: 5ث — 60ث\n"
            f"💹 الأسعار: 5ث — 60ث",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏱️ إعداد المسح",      callback_data="interval_scan_menu"),
                 InlineKeyboardButton("🛑 إعداد SL/TP",      callback_data="interval_monitor_menu")],
                [InlineKeyboardButton("💹 إعداد الأسعار",    callback_data="interval_prices_menu")],
                back[0],
            ]),
            parse_mode="Markdown"
        )
        return

    # ── تغيير وقت محدد ───────────────────────────────────
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "📝 `/setinterval <نوع> <ثواني>`\n"
            "الأنواع: `scan` | `monitor` | `prices`",
            parse_mode="Markdown"); return

    kind = ctx.args[0].lower()
    try:
        secs = int(ctx.args[1])
    except:
        await update.message.reply_text("❌ الثواني يجب أن تكون رقماً صحيحاً"); return

    if kind == "scan":
        if not 10 <= secs <= 300:
            await update.message.reply_text("❌ وقت المسح يجب بين *10* و *300* ثانية",
                                            parse_mode="Markdown"); return
        old = SCAN_SEC
        SCAN_SEC = secs
        label = "🔍 وقت المسح"

    elif kind == "monitor":
        if not 5 <= secs <= 60:
            await update.message.reply_text("❌ وقت SL/TP يجب بين *5* و *60* ثانية",
                                            parse_mode="Markdown"); return
        old = MONITOR_SEC
        MONITOR_SEC = secs
        label = "🛑 فحص SL/TP"

    elif kind == "prices":
        if not 5 <= secs <= 60:
            await update.message.reply_text("❌ وقت تحديث الأسعار يجب بين *5* و *60* ثانية",
                                            parse_mode="Markdown"); return
        old = PRICE_UPDATE_SEC
        PRICE_UPDATE_SEC = secs
        label = "💹 تحديث الأسعار"

    else:
        await update.message.reply_text(
            "❌ نوع غير معروف\nاستخدم: `scan` | `monitor` | `prices`",
            parse_mode="Markdown"); return

    # تحديد مستوى السرعة
    if secs <= 15:   speed = "⚡ سريع جداً"
    elif secs <= 30: speed = "🟢 سريع"
    elif secs <= 60: speed = "🟡 معتدل"
    else:            speed = "🔵 بطيء — موفر للموارد"

    await update.message.reply_text(
        f"✅ *تم تحديث التوقيت*\n{'─'*24}\n\n"
        f"{label}\n"
        f"من: *{old}ث* ← إلى: *{secs}ث*\n"
        f"⚡ {speed}\n\n"
        f"*الإعدادات الحالية:*\n"
        f"🔍 المسح: *{SCAN_SEC}ث*\n"
        f"🛑 SL/TP: *{MONITOR_SEC}ث*\n"
        f"💹 الأسعار: *{PRICE_UPDATE_SEC}ث*\n\n"
        f"⚠️ _التغيير يسري على الجلسة الحالية فقط\n"
        f"عند إعادة التشغيل تعود القيم الافتراضية_",
        parse_mode="Markdown"
    )

async def cmd_simstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض حالة الأسعار الحقيقية في المحاكاة"""
    status = "✅ متصل — أسعار حقيقية 100%" if FETCH_SUCCESS else "⚠️ غير متصل — انتظار الاتصال"
    text   = (
        f"📡 *حالة أسعار المحاكاة*\n{'─'*26}\n\n"
        f"المصدر: *CoinGecko* (مجاني)\n"
        f"الحالة: {status}\n"
        f"آخر تحديث: *{LAST_FETCH_TIME}*\n"
        f"تكرار التحديث: *كل 15 ثانية*\n"
        f"التذبذب: *❌ لا يوجد — أسعار حقيقية فقط*\n"
        f"عملات مُحدَّثة: *{len(LIVE_SIM_PRICES)}/{len(HALAL_LIST)}*\n\n"
    )
    if LIVE_SIM_PRICES:
        text += f"*الأسعار الحقيقية الحالية:*\n"
        for sym in HALAL_LIST:
            if sym in LIVE_SIM_PRICES:
                text += f"  `{sym}`: {fmt_p(sym, LIVE_SIM_PRICES[sym])}\n"
    else:
        text += "⏳ جاري جلب الأسعار...\nجرب مجدداً بعد 15 ثانية"

    kb = [[InlineKeyboardButton("🔄 تحديث فوري", callback_data="refresh_prices")],
          back[0]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb),
                                    parse_mode="Markdown")

async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not USE_BINANCE or not binance_client:
        await update.message.reply_text("❌ Binance غير مرتبط"); return
    text = f"💰 *رصيد Binance*\n{'─'*18}\n"
    text += f"💱 عملة التداول: `{QUOTE_CURRENCY}`\n\n"
    for a in [QUOTE_CURRENCY, "USDT", "USDC", "BTC", "ETH", "BNB", "XRP", "SOL", "ADA"]:
        b = binance_balance(a)
        if b > 0:
            marker = " ←" if a == QUOTE_CURRENCY else ""
            text += f"  {a}: {b:.6f}{marker}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ════════════════════════════════════════════════════════
#  🔘  معالج الأزرار
# ════════════════════════════════════════════════════════
async def btn_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global QUOTE_CURRENCY, SCAN_SEC, MONITOR_SEC, PRICE_UPDATE_SEC
    q    = update.callback_query
    await q.answer()
    data = q.data
    uid  = q.from_user.id
    u    = get_user(uid)

    async def edit(text, kb=None):
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb or back),
                                  parse_mode="Markdown")

    if data == "sellall_confirm":
        h = u["holdings"]
        if not h:
            await q.edit_message_text("💼 المحفظة فارغة الآن", parse_mode="Markdown")
            return
        await q.edit_message_text("⏳ *جاري بيع جميع العملات...*", parse_mode="Markdown")
        await _execute_sellall(uid, q.message)

    elif data == "main_menu":
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

    elif data == "risk_menu":
        scan      = u["smart_scan"]
        cash      = u["cash"]
        per_trade = cash * scan["risk_pct"]
        await edit(
            f"💰 *إعداد المخاطرة*\n{'─'*24}\n\n"
            f"النسبة الحالية: *{scan['risk_pct']*100:.1f}%*\n"
            f"مبلغ كل صفقة: *{fmt(per_trade)}*\n"
            f"رصيدك: {fmt(cash)}\n\n"
            f"*اختر النسبة:*",
            kb=[
                [InlineKeyboardButton("🟢 2% — متحفظ جداً",  callback_data="risk_2"),
                 InlineKeyboardButton("🟢 5% — متحفظ",       callback_data="risk_5")],
                [InlineKeyboardButton("🟡 10% — معتدل",      callback_data="risk_10"),
                 InlineKeyboardButton("🟠 15% — نشط",        callback_data="risk_15")],
                [InlineKeyboardButton("🔴 20% — مغامر",      callback_data="risk_20")],
                [InlineKeyboardButton("🔢 نسبة مخصصة: /setrisk <نسبة>", callback_data="noop")],
                back[0],
            ]
        )

    elif data.startswith("risk_"):
        pct  = int(data.split("_")[1])
        scan = u["smart_scan"]
        cash = u["cash"]
        old  = scan["risk_pct"] * 100
        scan["risk_pct"] = pct / 100
        per_trade = cash * scan["risk_pct"]
        max_loss  = per_trade * scan["sl_pct"] / 100

        if pct <= 5:   level = "🟢 متحفظ"
        elif pct <= 10: level = "🟡 معتدل"
        elif pct <= 15: level = "🟠 نشط"
        else:           level = "🔴 مغامر"

        await edit(
            f"✅ *تم تحديث المخاطرة*\n{'─'*24}\n\n"
            f"من: {old:.1f}%  ←  إلى: *{pct}%*\n\n"
            f"💵 رصيدك: {fmt(cash)}\n"
            f"💸 مبلغ كل صفقة: *{fmt(per_trade)}*\n"
            f"📉 أقصى خسارة/صفقة: *{fmt(max_loss)}*\n\n"
            f"⚖️ {level}\n\n"
            f"_يُطبَّق على الصفقات الجديدة فقط_"
        )

    elif data == "noop":
        pass

    # ══════════════════════════════════════════════════════
    #  ⚙️  لوحة إعدادات الصفقات
    # ══════════════════════════════════════════════════════
    elif data == "cfg_menu":
        scan = u["smart_scan"]
        await edit(
            f"⚙️ *لوحة إعدادات الصفقات*\n{'─'*28}\n\n"
            f"اضغط على أي إعداد لتعديله مباشرة 👇",
            kb=_cfg_kb(scan).inline_keyboard
        )

    elif data == "cfg_show_all":
        scan = u["smart_scan"]
        cash = u["cash"]
        per  = cash * scan["risk_pct"]
        rr   = round(scan["tp_pct"] / scan["sl_pct"], 2)
        await edit(
            f"⚙️ *جميع الإعدادات الحالية*\n{'─'*28}\n\n"
            f"*🔍 المسح الذكي:*\n"
            f"  الحالة: {'🟢 نشط' if scan['active'] else '⚪ موقوف'}\n"
            f"  ⭐ الحد الأدنى للنقاط: *{scan['min_score']}/100*\n"
            f"  📦 أقصى صفقات: *{scan['max_positions']}*\n\n"
            f"*💰 إدارة المخاطر:*\n"
            f"  🛑 Stop Loss: *{scan['sl_pct']:.1f}%*\n"
            f"  🎯 Take Profit: *{scan['tp_pct']:.1f}%*\n"
            f"  ⚖️ نسبة المكافأة/المخاطرة: *1:{rr}*\n"
            f"  💰 مخاطرة/صفقة: *{scan['risk_pct']*100:.1f}%*\n"
            f"  💸 مبلغ/صفقة: *{fmt(per)}*\n\n"
            f"*⏱️ التوقيت:*\n"
            f"  🔍 تكرار المسح: *{SCAN_SEC}ث*\n"
            f"  🛑 فحص SL/TP: *{MONITOR_SEC}ث*\n"
            f"  💹 تحديث الأسعار: *{PRICE_UPDATE_SEC}ث*\n\n"
            f"*🔌 التشغيل:*\n"
            f"  العملة: `{QUOTE_CURRENCY}`\n"
            f"  الوضع: {mode_lbl(uid)}\n"
            f"  مصدر: {'🟢 CoinGecko' if FETCH_SUCCESS else '🔵 محاكاة'}",
            kb=[
                [InlineKeyboardButton("✏️ تعديل الإعدادات", callback_data="cfg_menu")],
                back[0],
            ]
        )

    elif data == "cfg_sl":
        scan = u["smart_scan"]
        await edit(
            f"🛑 *تعديل Stop Loss*\n{'─'*24}\n\n"
            f"الحالي: *{scan['sl_pct']:.1f}%*\n\n"
            f"اختر نسبة جديدة:",
            kb=[
                [InlineKeyboardButton("1%",  callback_data="setcfg_sl_1"),
                 InlineKeyboardButton("2%",  callback_data="setcfg_sl_2"),
                 InlineKeyboardButton("3%",  callback_data="setcfg_sl_3")],
                [InlineKeyboardButton("4%",  callback_data="setcfg_sl_4"),
                 InlineKeyboardButton("5%",  callback_data="setcfg_sl_5"),
                 InlineKeyboardButton("7%",  callback_data="setcfg_sl_7")],
                [InlineKeyboardButton("10%", callback_data="setcfg_sl_10"),
                 InlineKeyboardButton("15%", callback_data="setcfg_sl_15"),
                 InlineKeyboardButton("20%", callback_data="setcfg_sl_20")],
                [InlineKeyboardButton("🔢 مخصص: /smartstart <sl> <tp>", callback_data="noop")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_tp":
        scan = u["smart_scan"]
        await edit(
            f"🎯 *تعديل Take Profit*\n{'─'*24}\n\n"
            f"الحالي: *{scan['tp_pct']:.1f}%*\n\n"
            f"اختر نسبة جديدة:",
            kb=[
                [InlineKeyboardButton("5%",  callback_data="setcfg_tp_5"),
                 InlineKeyboardButton("8%",  callback_data="setcfg_tp_8"),
                 InlineKeyboardButton("10%", callback_data="setcfg_tp_10")],
                [InlineKeyboardButton("12%", callback_data="setcfg_tp_12"),
                 InlineKeyboardButton("15%", callback_data="setcfg_tp_15"),
                 InlineKeyboardButton("20%", callback_data="setcfg_tp_20")],
                [InlineKeyboardButton("25%", callback_data="setcfg_tp_25"),
                 InlineKeyboardButton("30%", callback_data="setcfg_tp_30"),
                 InlineKeyboardButton("50%", callback_data="setcfg_tp_50")],
                [InlineKeyboardButton("🔢 مخصص: /smartstart <sl> <tp>", callback_data="noop")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_risk":
        scan = u["smart_scan"]
        await edit(
            f"💰 *تعديل المخاطرة/صفقة*\n{'─'*24}\n\n"
            f"الحالي: *{scan['risk_pct']*100:.1f}%*\n"
            f"مبلغ/صفقة: *{fmt(u['cash']*scan['risk_pct'])}*\n\n"
            f"اختر نسبة:",
            kb=[
                [InlineKeyboardButton("🟢 2%",  callback_data="setcfg_risk_2"),
                 InlineKeyboardButton("🟢 3%",  callback_data="setcfg_risk_3"),
                 InlineKeyboardButton("🟢 5%",  callback_data="setcfg_risk_5")],
                [InlineKeyboardButton("🟡 7%",  callback_data="setcfg_risk_7"),
                 InlineKeyboardButton("🟡 10%", callback_data="setcfg_risk_10"),
                 InlineKeyboardButton("🟠 15%", callback_data="setcfg_risk_15")],
                [InlineKeyboardButton("🔴 20%", callback_data="setcfg_risk_20"),
                 InlineKeyboardButton("🔴 25%", callback_data="setcfg_risk_25")],
                [InlineKeyboardButton("🔢 مخصص: /setrisk <نسبة>", callback_data="noop")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_maxpos":
        scan = u["smart_scan"]
        await edit(
            f"📦 *أقصى عدد صفقات مفتوحة*\n{'─'*24}\n\n"
            f"الحالي: *{scan['max_positions']}*\n\n"
            f"اختر العدد:",
            kb=[
                [InlineKeyboardButton("1",  callback_data="setcfg_maxpos_1"),
                 InlineKeyboardButton("2",  callback_data="setcfg_maxpos_2"),
                 InlineKeyboardButton("3",  callback_data="setcfg_maxpos_3")],
                [InlineKeyboardButton("4",  callback_data="setcfg_maxpos_4"),
                 InlineKeyboardButton("5",  callback_data="setcfg_maxpos_5"),
                 InlineKeyboardButton("6",  callback_data="setcfg_maxpos_6")],
                [InlineKeyboardButton("7",  callback_data="setcfg_maxpos_7"),
                 InlineKeyboardButton("8",  callback_data="setcfg_maxpos_8"),
                 InlineKeyboardButton("10", callback_data="setcfg_maxpos_10")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_minscore":
        scan = u["smart_scan"]
        await edit(
            f"⭐ *الحد الأدنى لنقاط الدخول*\n{'─'*24}\n\n"
            f"الحالي: *{scan['min_score']}/100*\n\n"
            f"كلما زادت النقاط قلّت الصفقات لكن زادت جودتها:",
            kb=[
                [InlineKeyboardButton("50 — كثير",   callback_data="setcfg_score_50"),
                 InlineKeyboardButton("55",            callback_data="setcfg_score_55"),
                 InlineKeyboardButton("60 — مناسب",  callback_data="setcfg_score_60")],
                [InlineKeyboardButton("65",            callback_data="setcfg_score_65"),
                 InlineKeyboardButton("70 — انتقائي", callback_data="setcfg_score_70"),
                 InlineKeyboardButton("75",            callback_data="setcfg_score_75")],
                [InlineKeyboardButton("80 — صارم",    callback_data="setcfg_score_80"),
                 InlineKeyboardButton("85",            callback_data="setcfg_score_85"),
                 InlineKeyboardButton("90 — نادر",    callback_data="setcfg_score_90")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_scan_interval":
        await edit(
            f"🔍 *تكرار المسح الذكي*\n{'─'*24}\n\n"
            f"الحالي: *{SCAN_SEC}ث*\n\n"
            f"اختر التوقيت:",
            kb=[
                [InlineKeyboardButton("⚡ 10ث",  callback_data="setcfg_scan_10"),
                 InlineKeyboardButton("⚡ 20ث",  callback_data="setcfg_scan_20"),
                 InlineKeyboardButton("🟢 30ث",  callback_data="setcfg_scan_30")],
                [InlineKeyboardButton("🟡 60ث",  callback_data="setcfg_scan_60"),
                 InlineKeyboardButton("🔵 120ث", callback_data="setcfg_scan_120"),
                 InlineKeyboardButton("🔵 300ث", callback_data="setcfg_scan_300")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_monitor_interval":
        await edit(
            f"🛑 *تكرار فحص SL/TP*\n{'─'*24}\n\n"
            f"الحالي: *{MONITOR_SEC}ث*\n\n"
            f"اختر التوقيت:",
            kb=[
                [InlineKeyboardButton("⚡ 5ث",  callback_data="setcfg_monitor_5"),
                 InlineKeyboardButton("⚡ 10ث", callback_data="setcfg_monitor_10"),
                 InlineKeyboardButton("🟢 15ث", callback_data="setcfg_monitor_15")],
                [InlineKeyboardButton("🟡 20ث", callback_data="setcfg_monitor_20"),
                 InlineKeyboardButton("🔵 30ث", callback_data="setcfg_monitor_30"),
                 InlineKeyboardButton("🔵 60ث", callback_data="setcfg_monitor_60")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_prices_interval":
        await edit(
            f"💹 *تكرار تحديث الأسعار*\n{'─'*24}\n\n"
            f"الحالي: *{PRICE_UPDATE_SEC}ث*\n\n"
            f"اختر التوقيت:",
            kb=[
                [InlineKeyboardButton("⚡ 5ث",  callback_data="setcfg_prices_5"),
                 InlineKeyboardButton("⚡ 10ث", callback_data="setcfg_prices_10"),
                 InlineKeyboardButton("🟢 15ث", callback_data="setcfg_prices_15")],
                [InlineKeyboardButton("🟡 30ث", callback_data="setcfg_prices_30"),
                 InlineKeyboardButton("🔵 60ث", callback_data="setcfg_prices_60")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_currency":
        await edit(
            f"💱 *عملة التداول*\n{'─'*22}\n\n"
            f"الحالية: `{QUOTE_CURRENCY}`\n\n"
            f"اختر العملة:",
            kb=[
                [InlineKeyboardButton("💵 USDT", callback_data="currency_USDT"),
                 InlineKeyboardButton("💵 USDC", callback_data="currency_USDC")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_toggle_scan":
        scan = u["smart_scan"]
        scan["active"] = not scan["active"]
        status = "🟢 تم التشغيل!" if scan["active"] else "⚪ تم الإيقاف"
        await edit(
            f"🔍 *المسح الذكي — {status}*\n\n"
            f"الحالة الجديدة: {'🟢 نشط' if scan['active'] else '⚪ موقوف'}\n\n"
            f"_اضغط رجوع للعودة للإعدادات_",
            kb=[
                [InlineKeyboardButton("◀️ رجوع للإعدادات", callback_data="cfg_menu")],
                back[0],
            ]
        )

    elif data == "cfg_reset_confirm":
        await edit(
            f"♻️ *تأكيد إعادة ضبط الإعدادات*\n{'─'*28}\n\n"
            f"سيتم إعادة جميع الإعدادات للقيم الافتراضية:\n\n"
            f"🛑 SL: {DEFAULT_SL}%\n"
            f"🎯 TP: {DEFAULT_TP}%\n"
            f"💰 مخاطرة: {RISK_PER_TRADE*100:.0f}%\n"
            f"📦 أقصى صفقات: {MAX_POSITIONS}\n"
            f"⭐ حد النقاط: {MIN_SCORE}\n"
            f"🔍 المسح: 30ث | 🛑 SL/TP: 20ث | 💹 الأسعار: 15ث\n\n"
            f"⚠️ لن تُحذف الصفقات المفتوحة",
            kb=[
                [InlineKeyboardButton("✅ تأكيد إعادة الضبط", callback_data="cfg_reset_do")],
                [InlineKeyboardButton("❌ إلغاء",              callback_data="cfg_menu")],
            ]
        )

    elif data == "cfg_reset_do":
        scan = u["smart_scan"]
        scan["sl_pct"]        = DEFAULT_SL
        scan["tp_pct"]        = DEFAULT_TP
        scan["risk_pct"]      = RISK_PER_TRADE
        scan["max_positions"] = MAX_POSITIONS
        scan["min_score"]     = MIN_SCORE
        SCAN_SEC          = 30
        MONITOR_SEC       = 20
        PRICE_UPDATE_SEC  = 15
        await edit(
            f"✅ *تمت إعادة الضبط*\n{'─'*22}\n\n"
            f"🛑 SL: *{DEFAULT_SL}%*\n"
            f"🎯 TP: *{DEFAULT_TP}%*\n"
            f"💰 مخاطرة: *{RISK_PER_TRADE*100:.0f}%*\n"
            f"📦 أقصى صفقات: *{MAX_POSITIONS}*\n"
            f"⭐ حد النقاط: *{MIN_SCORE}*\n"
            f"⏱️ المسح: *30ث* | SL/TP: *20ث* | أسعار: *15ث*",
            kb=[
                [InlineKeyboardButton("⚙️ الإعدادات", callback_data="cfg_menu")],
                back[0],
            ]
        )

    # ── معالجات setcfg العامة ────────────────────────────
    elif data.startswith("setcfg_"):
        parts  = data.split("_")   # setcfg_sl_5 → ["setcfg","sl","5"]
        kind   = parts[1]
        val    = parts[2]
        scan   = u["smart_scan"]

        if kind == "sl":
            scan["sl_pct"] = float(val)
            rr = round(scan["tp_pct"] / scan["sl_pct"], 2)
            msg = f"🛑 Stop Loss → *{val}%*\n⚖️ نسبة المكافأة/المخاطرة: 1:{rr}"
            back_cb = "cfg_sl"

        elif kind == "tp":
            scan["tp_pct"] = float(val)
            rr = round(scan["tp_pct"] / scan["sl_pct"], 2)
            msg = f"🎯 Take Profit → *{val}%*\n⚖️ نسبة المكافأة/المخاطرة: 1:{rr}"
            back_cb = "cfg_tp"

        elif kind == "risk":
            scan["risk_pct"] = float(val) / 100
            per = u["cash"] * scan["risk_pct"]
            msg = f"💰 مخاطرة/صفقة → *{val}%*\n💸 مبلغ/صفقة: *{fmt(per)}*"
            back_cb = "cfg_risk"

        elif kind == "maxpos":
            scan["max_positions"] = int(val)
            msg = f"📦 أقصى صفقات → *{val}*"
            back_cb = "cfg_maxpos"

        elif kind == "score":
            scan["min_score"] = int(val)
            msg = f"⭐ حد النقاط → *{val}/100*"
            back_cb = "cfg_minscore"

        elif kind == "scan":
            SCAN_SEC = int(val)
            msg = f"🔍 تكرار المسح → *{val}ث*"
            back_cb = "cfg_scan_interval"

        elif kind == "monitor":
            MONITOR_SEC = int(val)
            msg = f"🛑 فحص SL/TP → *{val}ث*"
            back_cb = "cfg_monitor_interval"

        elif kind == "prices":
            PRICE_UPDATE_SEC = int(val)
            msg = f"💹 تحديث الأسعار → *{val}ث*"
            back_cb = "cfg_prices_interval"

        else:
            msg = "❓ إعداد غير معروف"
            back_cb = "cfg_menu"

        await edit(
            f"✅ *تم التحديث*\n\n{msg}\n\n_جميع الصفقات الجديدة ستستخدم هذا الإعداد_",
            kb=[
                [InlineKeyboardButton("◀️ رجوع",          callback_data=back_cb),
                 InlineKeyboardButton("⚙️ كل الإعدادات",  callback_data="cfg_menu")],
                back[0],
            ]
        )

    elif data.startswith("currency_"):
        new_cur        = data.split("_")[1]
        old_cur        = QUOTE_CURRENCY
        QUOTE_CURRENCY = new_cur
        note = "✅ متاح لجميع الأزواج" if new_cur == "USDT" else "⚠️ بعض الأزواج قد لا تكون متاحة"
        await edit(
            f"✅ *تم تغيير عملة التداول*\n\n"
            f"من: `{old_cur}` ← إلى: `{new_cur}`\n\n"
            f"{note}\n\n"
            f"_الصفقات الجديدة ستستخدم {new_cur}_"
        )

    elif data == "interval_scan_menu":
        await edit(
            f"🔍 *وقت المسح الحالي: {SCAN_SEC}ث*\n\n"
            f"اختر وقتاً جديداً:",
            kb=[
                [InlineKeyboardButton("⚡ 10ث — سريع جداً",  callback_data="iscan_10"),
                 InlineKeyboardButton("⚡ 20ث — سريع",       callback_data="iscan_20")],
                [InlineKeyboardButton("🟢 30ث — مناسب",      callback_data="iscan_30"),
                 InlineKeyboardButton("🟡 60ث — معتدل",      callback_data="iscan_60")],
                [InlineKeyboardButton("🔵 120ث — بطيء",      callback_data="iscan_120"),
                 InlineKeyboardButton("🔵 300ث — اقتصادي",   callback_data="iscan_300")],
                [InlineKeyboardButton("🔢 مخصص: /setinterval scan <ثواني>", callback_data="noop")],
                back[0],
            ]
        )

    elif data == "interval_monitor_menu":
        await edit(
            f"🛑 *وقت فحص SL/TP الحالي: {MONITOR_SEC}ث*\n\n"
            f"اختر وقتاً جديداً:",
            kb=[
                [InlineKeyboardButton("⚡ 5ث",   callback_data="imonitor_5"),
                 InlineKeyboardButton("⚡ 10ث",  callback_data="imonitor_10")],
                [InlineKeyboardButton("🟢 15ث",  callback_data="imonitor_15"),
                 InlineKeyboardButton("🟡 20ث",  callback_data="imonitor_20")],
                [InlineKeyboardButton("🔵 30ث",  callback_data="imonitor_30"),
                 InlineKeyboardButton("🔵 60ث",  callback_data="imonitor_60")],
                [InlineKeyboardButton("🔢 مخصص: /setinterval monitor <ثواني>", callback_data="noop")],
                back[0],
            ]
        )

    elif data == "interval_prices_menu":
        await edit(
            f"💹 *وقت تحديث الأسعار الحالي: {PRICE_UPDATE_SEC}ث*\n\n"
            f"اختر وقتاً جديداً:",
            kb=[
                [InlineKeyboardButton("⚡ 5ث",   callback_data="iprices_5"),
                 InlineKeyboardButton("⚡ 10ث",  callback_data="iprices_10")],
                [InlineKeyboardButton("🟢 15ث",  callback_data="iprices_15"),
                 InlineKeyboardButton("🟡 30ث",  callback_data="iprices_30")],
                [InlineKeyboardButton("🔵 60ث",  callback_data="iprices_60")],
                [InlineKeyboardButton("🔢 مخصص: /setinterval prices <ثواني>", callback_data="noop")],
                back[0],
            ]
        )

    elif data.startswith("iscan_"):
        secs = int(data.split("_")[1])
        old  = SCAN_SEC
        SCAN_SEC = secs
        speed = "⚡ سريع جداً" if secs<=15 else ("🟢 سريع" if secs<=30 else ("🟡 معتدل" if secs<=60 else "🔵 اقتصادي"))
        await edit(
            f"✅ *وقت المسح تم تحديثه*\n\n"
            f"من: *{old}ث* ← إلى: *{secs}ث*\n"
            f"{speed}\n\n"
            f"🔍 المسح: *{SCAN_SEC}ث*\n"
            f"🛑 SL/TP: *{MONITOR_SEC}ث*\n"
            f"💹 الأسعار: *{PRICE_UPDATE_SEC}ث*"
        )

    elif data.startswith("imonitor_"):
        secs = int(data.split("_")[1])
        old  = MONITOR_SEC
        MONITOR_SEC = secs
        speed = "⚡ سريع جداً" if secs<=10 else ("🟢 سريع" if secs<=20 else "🟡 معتدل")
        await edit(
            f"✅ *وقت SL/TP تم تحديثه*\n\n"
            f"من: *{old}ث* ← إلى: *{secs}ث*\n"
            f"{speed}\n\n"
            f"🔍 المسح: *{SCAN_SEC}ث*\n"
            f"🛑 SL/TP: *{MONITOR_SEC}ث*\n"
            f"💹 الأسعار: *{PRICE_UPDATE_SEC}ث*"
        )

    elif data.startswith("iprices_"):
        secs = int(data.split("_")[1])
        old  = PRICE_UPDATE_SEC
        PRICE_UPDATE_SEC = secs
        speed = "⚡ سريع جداً" if secs<=10 else ("🟢 سريع" if secs<=15 else "🟡 معتدل")
        await edit(
            f"✅ *وقت تحديث الأسعار تم تحديثه*\n\n"
            f"من: *{old}ث* ← إلى: *{secs}ث*\n"
            f"{speed}\n\n"
            f"🔍 المسح: *{SCAN_SEC}ث*\n"
            f"🛑 SL/TP: *{MONITOR_SEC}ث*\n"
            f"💹 الأسعار: *{PRICE_UPDATE_SEC}ث*"
        )

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

    elif data in ("stats", "stats_main"):
        st   = u["stats"]
        pv   = portfolio_value(uid)
        tt   = st["total_trades"]
        wr   = round(st["wins"] / tt * 100, 1) if tt > 0 else 0
        scan = u["smart_scan"]
        pos  = open_positions(uid)
        ov   = pv - DEFAULT_CAPITAL
        kb_s = [
            [InlineKeyboardButton("📡 حالة الأسعار",      callback_data="stats_prices"),
             InlineKeyboardButton("🔍 إحصائيات المسح",    callback_data="stats_scan")],
            [InlineKeyboardButton("💼 تفاصيل الصفقات",    callback_data="stats_trades"),
             InlineKeyboardButton("📊 أداء العملات",      callback_data="stats_symbols")],
            [InlineKeyboardButton("⚙️ الإعدادات المطبقة", callback_data="stats_settings"),
             InlineKeyboardButton("🔄 تحديث",             callback_data="stats_main")],
            back[0],
        ]
        await edit(
            f"📊 *لوحة الإحصائيات الشاملة*\n{'─'*28}\n\n"
            f"🔌 {mode_lbl(uid)}\n"
            f"📡 الأسعار: {'🟢 حقيقية' if FETCH_SUCCESS else '🔵 محاكاة'}\n"
            f"🔍 المسح: {'🟢 نشط' if scan['active'] else '⚪ موقوف'}\n\n"
            f"💵 *{fmt(u['cash'])}* نقد\n"
            f"💼 *{fmt(pv)}* إجمالي\n"
            f"{pnl_e(ov)} *${ov:+,.2f}* ({ov/DEFAULT_CAPITAL*100:+.2f}%)\n\n"
            f"📈 {tt} صفقة | ✅{st['wins']} ❌{st['losses']} | 🎯{wr:.1f}%\n"
            f"📌 مفتوحة: {pos}/{scan['max_positions']}\n\n"
            f"_اختر قسماً 👇_",
            kb=kb_s
        )

    elif data == "stats_prices":
        src    = "🟢 CoinGecko (أسعار حقيقية مجانية)" if FETCH_SUCCESS else "🔵 محاكاة عشوائية"
        count  = len(LIVE_SIM_PRICES)
        text   = (
            f"📡 *حالة الأسعار*\n{'─'*26}\n\n"
            f"المصدر: *{src}*\n"
            f"آخر تحديث: *{LAST_FETCH_TIME}*\n"
            f"عملات مُحدَّثة: *{count}/{len(HALAL_LIST)}*\n"
            f"تكرار التحديث: *كل 15 ثانية*\n\n"
        )
        if LIVE_SIM_PRICES:
            text += f"*الأسعار الحالية:*\n"
            results = scan_market()
            for r in results:
                sym = r["sym"]
                px  = LIVE_SIM_PRICES.get(sym, price(sym))
                bar = "🟩" * (r["score"] // 20) + "⬜" * (5 - r["score"] // 20)
                text += f"  `{sym:6}` {fmt_p(sym, px):>12}  ⭐{r['score']:3} {bar}\n"
        else:
            text += "⏳ جاري جلب الأسعار الحقيقية..."
        await edit(text, kb=[
            [InlineKeyboardButton("🔄 جلب فوري", callback_data="refresh_prices")],
            [InlineKeyboardButton("◀️ رجوع",     callback_data="stats_main")],
        ])

    elif data == "stats_scan":
        scan  = u["smart_scan"]
        pos   = open_positions(uid)
        st    = u["stats"]
        text  = (
            f"🔍 *إحصائيات المسح الذكي*\n{'─'*28}\n\n"
            f"الحالة: {'🟢 نشط' if scan['active'] else '⚪ موقوف'}\n"
            f"إجمالي عمليات المسح: *{scan['scan_count']}*\n"
            f"آخر مسح: *{scan['last_scan'] or 'لم يبدأ'}*\n"
            f"صفقات المسح الذكي: *{st['scan_trades']}*\n\n"
            f"*📐 معايير الدخول:*\n"
            f"⭐ الحد الأدنى للنقاط: *{scan['min_score']}/100*\n"
            f"📊 أقصى صفقات مفتوحة: *{scan['max_positions']}*\n"
            f"📌 مفتوحة الآن: *{pos}*\n\n"
            f"*📐 معايير الخروج:*\n"
            f"⭐ الخروج عند نقاط ≤ *35/100*\n"
            f"🛑 Stop Loss: *{scan['sl_pct']:.1f}%*\n"
            f"🎯 Take Profit: *{scan['tp_pct']:.1f}%*\n\n"
            f"*💰 إدارة رأس المال:*\n"
            f"مخاطرة/صفقة: *{scan['risk_pct']*100:.1f}%*\n"
            f"مبلغ/صفقة: *{fmt(u['cash'] * scan['risk_pct'])}*\n"
            f"⚖️ نسبة المكافأة/المخاطرة: *1:{round(scan['tp_pct']/scan['sl_pct'],2)}*\n\n"
            f"*⏱️ التوقيت:*\n"
            f"🔍 تكرار المسح: *{SCAN_SEC}ث*\n"
            f"🛑 فحص SL/TP: *{MONITOR_SEC}ث*\n"
            f"💹 تحديث الأسعار: *{PRICE_UPDATE_SEC}ث*"
        )
        await edit(text, kb=[[InlineKeyboardButton("◀️ رجوع", callback_data="stats_main")]])

    elif data == "stats_trades":
        st  = u["stats"]
        h   = u["holdings"]
        tt  = st["total_trades"]
        wr  = round(st["wins"] / tt * 100, 1) if tt > 0 else 0
        text = (
            f"💼 *تفاصيل الصفقات*\n{'─'*26}\n\n"
            f"*📊 ملخص الصفقات:*\n"
            f"إجمالي: *{tt}*\n"
            f"  🔍 مسح ذكي: *{st['scan_trades']}*\n"
            f"  👤 يدوية: *{tt - st['scan_trades']}*\n"
            f"✅ رابحة: *{st['wins']}*\n"
            f"❌ خاسرة: *{st['losses']}*\n"
            f"🎯 نسبة الفوز: *{wr:.1f}%*\n"
            f"💵 صافي PnL: *${st['total_pnl']:+.4f}*\n\n"
        )
        if h:
            text += f"*📌 الصفقات المفتوحة ({len(h)}):*\n"
            for sym, d in h.items():
                cur     = price(sym)
                val     = cur * d["qty"]
                pnl     = (cur - d["avg_price"]) * d["qty"]
                pnl_pct = (cur - d["avg_price"]) / d["avg_price"] * 100
                sc      = score_coin(sym)
                o       = u["orders"].get(sym, {})
                sl_s    = f"🛑{o['sl_pct']:.0f}%" if "sl_pct" in o else "🛑—"
                tp_s    = f"🎯{o['tp_pct']:.0f}%" if "tp_pct" in o else "🎯—"
                text += (
                    f"\n`{sym}` ⭐{sc['score']}/100\n"
                    f"  📦 {d['qty']} × {fmt_p(sym, cur)}\n"
                    f"  💵 {fmt(val)}  {pnl_e(pnl)}${pnl:+.4f} ({pnl_pct:+.2f}%)\n"
                    f"  دخول: {fmt_p(sym, d['avg_price'])}  {sl_s} {tp_s}\n"
                )
        else:
            text += "📌 لا توجد صفقات مفتوحة حالياً\n"

        if st["per_sym"]:
            text += f"\n*📋 آخر 5 عمليات:*\n"
            for t in u["transactions"][-5:][::-1]:
                p_s = f" {pnl_e(t.get('pnl',0))}${t['pnl']:+.4f}" if "pnl" in t else ""
                text += f"  {t['type']} {t['dir']} `{t['sym']}`{p_s}\n"

        await edit(text, kb=[[InlineKeyboardButton("◀️ رجوع", callback_data="stats_main")]])

    elif data == "stats_symbols":
        st = u["stats"]
        if not st["per_sym"]:
            await edit("📊 لا توجد بيانات بعد\nابدأ بـ `/smartstart`",
                       kb=[[InlineKeyboardButton("◀️ رجوع", callback_data="stats_main")]])
            return
        sorted_syms = sorted(st["per_sym"].items(), key=lambda x: x[1]["pnl"], reverse=True)
        text = f"📊 *أداء كل عملة*\n{'─'*26}\n\n"
        total_pnl = 0
        for sym, s in sorted_syms:
            wr2   = round(s["wins"] / s["trades"] * 100, 0) if s["trades"] > 0 else 0
            total_pnl += s["pnl"]
            cur   = price(sym) if sym in ASSETS else 0
            sc    = score_coin(sym)["score"] if sym in ASSETS else 0
            bar   = "🟩" * (wr2 // 20) + "⬜" * (5 - wr2 // 20)
            text += (
                f"{pnl_e(s['pnl'])} `{sym}` ⭐{sc}/100\n"
                f"  صفقات: {s['trades']} | فوز: {wr2:.0f}% {bar}\n"
                f"  PnL: *${s['pnl']:+.4f}*\n\n"
            )
        text += f"{'─'*26}\n💵 إجمالي PnL: *${total_pnl:+.4f}*"
        await edit(text, kb=[[InlineKeyboardButton("◀️ رجوع", callback_data="stats_main")]])

    elif data == "stats_settings":
        scan = u["smart_scan"]
        text = (
            f"⚙️ *جميع الإعدادات المطبقة*\n{'─'*28}\n\n"
            f"*🔌 وضع التشغيل:*\n"
            f"  الوضع: {mode_lbl(uid)}\n"
            f"  Binance: {'🟢 متصل' if (USE_BINANCE and binance_client) else '⚪ غير متصل'}\n"
            f"  عملة التداول: `{QUOTE_CURRENCY}`\n\n"
            f"*📡 مصدر الأسعار:*\n"
            f"  {'🟢 CoinGecko — أسعار حقيقية' if FETCH_SUCCESS else '🔵 محاكاة عشوائية'}\n"
            f"  آخر تحديث: *{LAST_FETCH_TIME}*\n"
            f"  عملات مُحدَّثة: *{len(LIVE_SIM_PRICES)}*\n\n"
            f"*🔍 إعدادات المسح:*\n"
            f"  الحالة: {'🟢 نشط' if scan['active'] else '⚪ موقوف'}\n"
            f"  الحد الأدنى للنقاط: *{scan['min_score']}/100*\n"
            f"  أقصى صفقات: *{scan['max_positions']}*\n\n"
            f"*💰 إدارة المخاطر:*\n"
            f"  مخاطرة/صفقة: *{scan['risk_pct']*100:.1f}%*\n"
            f"  مبلغ/صفقة: *{fmt(u['cash'] * scan['risk_pct'])}*\n"
            f"  🛑 Stop Loss: *{scan['sl_pct']:.1f}%*\n"
            f"  🎯 Take Profit: *{scan['tp_pct']:.1f}%*\n"
            f"  ⚖️ نسبة المكافأة/المخاطرة: *1:{round(scan['tp_pct']/scan['sl_pct'],2)}*\n\n"
            f"*⏱️ التوقيت:*\n"
            f"  🔍 تكرار المسح: *{SCAN_SEC}ث*\n"
            f"  🛑 فحص SL/TP: *{MONITOR_SEC}ث*\n"
            f"  💹 تحديث الأسعار: *{PRICE_UPDATE_SEC}ث*\n\n"
            f"*📊 المؤشرات الفنية المستخدمة:*\n"
            f"  ⚡ RSI(14)  🔀 MACD(12,26)  📊 SMA(10,30,50)\n"
            f"  📉 Bollinger(20)  💨 Momentum(10,20)  📊 Volume\n\n"
            f"*🕌 الفلتر الشرعي:*\n"
            f"  ✅ {len(HALAL_LIST)} عملة حلال مُفعَّلة\n"
            f"  ❌ بيع على المكشوف — محظور\n"
            f"  ❌ تداول بالهامش — محظور\n"
            f"  ❌ المشتقات — محظورة"
        )
        await edit(text, kb=[[InlineKeyboardButton("◀️ رجوع", callback_data="stats_main")]])

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
            f"🔌 *الإعدادات العامة*\n\n"
            f"الوضع: {mode_lbl(uid)} | Binance: {b_stat}\n"
            f"💱 العملة: `{QUOTE_CURRENCY}`\n\n"
            f"⏱️ *التوقيت الحالي:*\n"
            f"🔍 المسح: *{SCAN_SEC}ث*\n"
            f"🛑 SL/TP: *{MONITOR_SEC}ث*\n"
            f"💹 الأسعار: *{PRICE_UPDATE_SEC}ث*\n\n"
            f"`/setbinance KEY SECRET`\n"
            f"`/livemode` / `/simmode`\n"
            f"`/setcurrency` — العملة\n"
            f"`/setinterval` — أوقات المسح",
            kb=[
                [InlineKeyboardButton("⏱️ وقت المسح",       callback_data="interval_scan_menu"),
                 InlineKeyboardButton("🛑 وقت SL/TP",       callback_data="interval_monitor_menu")],
                [InlineKeyboardButton("💹 وقت الأسعار",     callback_data="interval_prices_menu"),
                 InlineKeyboardButton("💱 العملة",           callback_data="currency_menu")],
                back[0],
            ]
        )

    elif data == "currency_menu":
        await edit(
            f"💱 *عملة التداول الحالية: `{QUOTE_CURRENCY}`*\n\n"
            f"اختر العملة:",
            kb=[
                [InlineKeyboardButton("💵 USDT", callback_data="currency_USDT"),
                 InlineKeyboardButton("💵 USDC", callback_data="currency_USDC")],
                back[0],
            ]
        )

    elif data == "refresh_prices":
        await edit("⏳ *جاري جلب الأسعار الحقيقية...*")
        success = await asyncio.get_event_loop().run_in_executor(None, fetch_real_prices)
        status  = "✅ تم التحديث بنجاح!" if success else "⚠️ فشل الاتصال — جرب لاحقاً"
        count   = len(LIVE_SIM_PRICES)
        await edit(
            f"📡 *تحديث الأسعار*\n\n"
            f"{status}\n"
            f"عملات مُحدَّثة: *{count}*\n"
            f"آخر تحديث: *{LAST_FETCH_TIME}*\n\n"
            f"_اكتب /simstatus لعرض الأسعار كاملاً_"
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
        ("setrisk",        cmd_setrisk),
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
        ("settings",       cmd_settings),
        ("dashboard",      cmd_dashboard),
        ("sellall",         cmd_sellall),
        ("reset",          cmd_reset),
        # Binance
        ("setbinance",     cmd_setbinance),
        ("livemode",       cmd_livemode),
        ("simmode",        cmd_simmode),
        ("simstatus",      cmd_simstatus),
        ("setinterval",    cmd_setinterval),
        ("setcurrency",    cmd_setcurrency),
        ("balance",        cmd_balance),
    ]
    for name, handler in cmds:
        app.add_handler(CommandHandler(name, handler))

    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))

    jq = app.job_queue
    jq.run_repeating(job_prices,            interval=PRICE_UPDATE_SEC, first=3)
    jq.run_repeating(job_monitor_sl_tp,     interval=MONITOR_SEC,     first=5)
    jq.run_repeating(job_smart_scan,        interval=SCAN_SEC,        first=15)
    jq.run_repeating(job_fetch_real_prices, interval=15,              first=20)  # كل 15 ثانية

    print("🕌 بوت التداول الحلال v6.0 يعمل!")
    print(f"   🔍 مسح ذكي:    كل {SCAN_SEC}ث")
    print(f"   🛑 SL/TP:      كل {MONITOR_SEC}ث")
    print(f"   💹 الأسعار:    كل {PRICE_UPDATE_SEC}ث")
    print(f"   📊 عملات حلال: {len(HALAL_LIST)}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

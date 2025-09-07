
import os, logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Telegram application
application = Application.builder().token(BOT_TOKEN).build()

# Original bot code
# Advance Telegram bot for CPA Master (Modified for Webhook, MESSAGE_ID_LINK, improved Back behavior, admin invite)
import json
import os
import logging
from typing import Dict, Any, List, Optional, Set

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG (Modify here) ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_CHAT_ID = -1002565129037  # integer (negative for supergroups)
GROUP_LINK = "https://t.me/cpamastaer7383"
MESSAGE_ID_LINK = "t.me/mostakim_21"   # NEW: central link for reports
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")   # Vercel server URL (your provided link)

ADMIN_PASSWORD_FB = "@2009@MOHAMMAD#"
ADMIN_PASSWORD_GMAIL = "password"

DEFAULT_ADMIN = {
    "id": 7152410095,
    "username": "mostakim_21",
    "name": "Mostakim",
}
DATA_FILE = "data.json"
# -----------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- In-memory structures (loaded/saved) ----------------
ADMINS: Dict[str, Dict[str, Any]] = {}  # key: str(user_id)
MEMBERS: Dict[str, Dict[str, Any]] = {}  # key: member_code
TEAMS: Dict[str, Dict[str, Any]] = {}
VERIFIED_TG_USERS: Set[int] = set()
CLAIMS_BY_TG: Dict[int, str] = {}  # tg_id -> code
PENDING_ADMINS: List[Dict[str, Any]] = []  # username/name pending

# ---------------- Persistence ----------------
def load_data():
    global ADMINS, MEMBERS, TEAMS, VERIFIED_TG_USERS, CLAIMS_BY_TG, PENDING_ADMINS
    if not os.path.exists(DATA_FILE):
        # initialize with default admin
        ADMINS = {
            str(DEFAULT_ADMIN["id"]): {
                "id": DEFAULT_ADMIN["id"],
                "username": DEFAULT_ADMIN["username"],
                "name": DEFAULT_ADMIN["name"],
                "is_default": True,
            }
        }
        MEMBERS = {}
        TEAMS = {}
        VERIFIED_TG_USERS = set()
        CLAIMS_BY_TG = {}
        PENDING_ADMINS = []
        save_data()
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.exception("Failed to load data.json: %s", e)
        # fallback to defaults
        ADMINS = {
            str(DEFAULT_ADMIN["id"]): {
                "id": DEFAULT_ADMIN["id"],
                "username": DEFAULT_ADMIN["username"],
                "name": DEFAULT_ADMIN["name"],
                "is_default": True,
            }
        }
        MEMBERS = {}
        TEAMS = {}
        VERIFIED_TG_USERS = set()
        CLAIMS_BY_TG = {}
        PENDING_ADMINS = []
        save_data()
        return

    # load admins
    ADMINS = {}
    for k, v in (data.get("admins") or {}).items():
        ADMINS[str(k)] = {
            "id": int(v.get("id", int(k))),
            "username": v.get("username", ""),
            "name": v.get("name", ""),
            "is_default": bool(v.get("is_default", False)),
        }
    # ensure default admin exists
    if str(DEFAULT_ADMIN["id"]) not in ADMINS:
        ADMINS[str(DEFAULT_ADMIN["id"])] = {
            "id": DEFAULT_ADMIN["id"],
            "username": DEFAULT_ADMIN["username"],
            "name": DEFAULT_ADMIN["name"],
            "is_default": True,
        }

    MEMBERS = data.get("members", {}) or {}
    TEAMS = data.get("teams", {}) or {}
    VERIFIED_TG_USERS = set(int(x) for x in (data.get("verified", []) or []))
    CLAIMS_BY_TG = {int(k): v for k, v in (data.get("claims") or {}).items()}
    PENDING_ADMINS = data.get("pending_admins", []) or []


def save_data():
    try:
        data = {
            "admins": {k: v for k, v in ADMINS.items()},
            "members": MEMBERS,
            "teams": TEAMS,
            "verified": list(VERIFIED_TG_USERS),
            "claims": {str(k): v for k, v in CLAIMS_BY_TG.items()},
            "pending_admins": PENDING_ADMINS,
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("Failed to save data.json: %s", e)


# ---------------- Helpers ----------------
def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMINS


def is_default_admin(user_id: int) -> bool:
    return is_admin(user_id) and ADMINS.get(str(user_id), {}).get("is_default", False)


def ensure_admin_entry_for_id(user_id: int, username: Optional[str], name: str, default=False):
    ADMINS[str(user_id)] = {
        "id": user_id,
        "username": username or "",
        "name": name,
        "is_default": default,
    }
    save_data()


def html_bold(s: str) -> str:
    return f"<b>{s}</b>"


# Button labels (visible)
LABEL = {
    "send_report": "📊Send Report",
    "send_message": "📤 Send Message 📤",
    "members": "👤 Members 👤",
    "team": "☸️ Team ☸️",
    "admin": "🪪 Admin",
    "everyone": "👥 Everyone 👥",
    "selected_member": "➰Selected Member➰",
    "member_list": "📝 Member List",
    "add_member": "➕ Add Member ➕",
    "remove_member": "⛔ Remove Member ⛔",
    "add_team": "➕ Add Team ➕",
    "remove_team": "⛔ Remove Team ⛔",
    "add_admin": "➕ Add Admin ➕",
    "remove_admin": "⛔ Remove Admin ⛂",
    "yes": "🆗 Yes",
    "no": "🚫 No",
    "back": "↪️ Back",
    "cancel": "🚫 Cancel",
    "empty": "🆑 Empty",
}

# ---------------- Keyboards builders ----------------
def build_admin_menu():
    kb = [
        [InlineKeyboardButton(LABEL["send_report"], callback_data="send_report")],
        [InlineKeyboardButton(LABEL["send_message"], callback_data="send_message")],
        [InlineKeyboardButton(LABEL["members"], callback_data="members")],
        [InlineKeyboardButton(LABEL["team"], callback_data="team")],
        [InlineKeyboardButton(LABEL["admin"], callback_data="admin")],
    ]
    return InlineKeyboardMarkup(kb)


def build_send_message_kb():
    kb = [
        [InlineKeyboardButton(LABEL["everyone"], callback_data="broadcast_everyone")],
        [InlineKeyboardButton(LABEL["selected_member"], callback_data="broadcast_selected")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ]
    return InlineKeyboardMarkup(kb)


def build_members_kb():
    kb = [
        [InlineKeyboardButton(LABEL["member_list"], callback_data="members_list")],
        [InlineKeyboardButton(LABEL["add_member"], callback_data="members_add")],
        [InlineKeyboardButton(LABEL["remove_member"], callback_data="members_remove")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ]
    return InlineKeyboardMarkup(kb)


def build_team_kb():
    kb = [
        [InlineKeyboardButton(LABEL["add_team"], callback_data="team_add")],
        [InlineKeyboardButton(LABEL["remove_team"], callback_data="team_remove")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ]
    return InlineKeyboardMarkup(kb)


def build_admin_kb():
    kb = [
        [InlineKeyboardButton(LABEL["add_admin"], callback_data="admin_add")],
        [InlineKeyboardButton(LABEL["remove_admin"], callback_data="admin_remove")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ]
    return InlineKeyboardMarkup(kb)


def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(LABEL["cancel"], callback_data="cancel")]])


def yes_no_kb(prefix: str):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(LABEL["no"], callback_data=f"{prefix}_no"),
                InlineKeyboardButton(LABEL["yes"], callback_data=f"{prefix}_yes"),
            ]
        ]
    )


# ---------------- per-user last bot message management ----------------
# We'll keep last bot message id per user to delete previous bot message when navigating
def store_last_bot_message(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, message_id: int):
    key = f"last_msg:{user_id}"
    context.bot_data[key] = {"chat_id": chat_id, "message_id": message_id}


async def try_delete_last_bot_message(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    key = f"last_msg:{user_id}"
    info = context.bot_data.get(key)
    if not info:
        return
    try:
        await context.bot.delete_message(chat_id=info["chat_id"], message_id=info["message_id"])
    except Exception:
        # ignore errors (message may be already deleted or permission issues)
        pass
    context.bot_data.pop(key, None)


# ---------------- Navigation stack helpers ----------------
def push_flow(context: ContextTypes.DEFAULT_TYPE, user_id: int, previous_flow: Optional[str]):
    if previous_flow is None:
        return
    key = f"flow_stack:{user_id}"
    stack = context.user_data.get("flow_stack", [])
    stack.append(previous_flow)
    context.user_data["flow_stack"] = stack


def pop_flow(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Optional[str]:
    stack = context.user_data.get("flow_stack", [])
    if not stack:
        return None
    prev = stack.pop()
    context.user_data["flow_stack"] = stack
    return prev


async def render_flow_for_user(user, context: ContextTypes.DEFAULT_TYPE, flow: Optional[str]):
    # Render a simple representation of the previous flow/menu for 'back' functionality.
    # We implement common flows - if unknown, show admin menu.
    try:
        await try_delete_last_bot_message(context, user.id)
    except:
        pass
    if flow == "mainadmin_password":
        msg = await context.bot.send_message(chat_id=user.id, text="আপনার ফেসবুক আইডির পাসওয়ার্ড দিন।", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if flow == "report":
        msg = await context.bot.send_message(chat_id=user.id, text="User ID..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data["flow"] = "report"
        context.user_data["report"] = {"step": 1}
        return
    if flow == "members":
        msg = await context.bot.send_message(chat_id=user.id, text="📋 Members", reply_markup=build_members_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if flow == "team":
        text = list_teams_text()
        msg = await context.bot.send_message(chat_id=user.id, text=text, reply_markup=build_team_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if flow == "admin":
        text = list_admins_text()
        msg = await context.bot.send_message(chat_id=user.id, text=text, reply_markup=build_admin_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    # default -> admin menu
    msg = await context.bot.send_message(chat_id=user.id, text="WELCOME", reply_markup=build_admin_menu())
    store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
    context.user_data.clear()


# ---------------- /start handler ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    context.user_data.clear()

    # If admin -> show admin menu
    if is_admin(user.id):
        # delete user's /start message if possible
        try:
            if update.message:
                await update.message.delete()
        except:
            pass
        msg = await context.bot.send_message(chat_id=chat.id, text="WELCOME", reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    # Normal user flow -> ask for member code
    if user.id in VERIFIED_TG_USERS:
        await context.bot.send_message(chat_id=chat.id, text=html_bold("আপনি ইতিমধ্যে ভেরিফাইড।"), parse_mode=ParseMode.HTML)
        return

    context.user_data["flow"] = "user_verify"
    msg = await context.bot.send_message(chat_id=chat.id, text=html_bold("আপনার ইউজার আইডি দিন।"), parse_mode=ParseMode.HTML)
    store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)


# ---------------- /mainadmin handler ----------------
async def mainadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="শুধু অ্যাডমিনরাই এই কমান্ড ব্যবহার করতে পারবেন।")
        return
    # push previous flow then set new
    push_flow(context, user.id, context.user_data.get("flow"))
    context.user_data["flow"] = "mainadmin_password"
    msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="আপনার ফেসবুক আইডির পাসওয়ার্ড দিন।", reply_markup=cancel_kb())
    store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)


# ---------------- Callback router ----------------
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data_cb = query.data
    user = query.from_user

    # delete previous bot message for this user when navigating to new menu/prompt
    await try_delete_last_bot_message(context, user.id)

    # BACK: pop previous flow and render it
    if data_cb == "back" or data_cb == "back_admin" or data_cb == "back_menu":
        prev = pop_flow(context, user.id)
        await render_flow_for_user(user, context, prev)
        return

    if data_cb == "cancel":
        # cancel current flow
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল করা হলো।", reply_markup=build_admin_menu() if is_admin(user.id) else None)
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    # ---------- Send Report ----------
    if data_cb == "send_report":
        if not is_admin(user.id):
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "report"
        context.user_data["report"] = {"step": 1}
        msg = await context.bot.send_message(chat_id=user.id, text="User ID..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "report_country_empty":
        # used during report step2
        if context.user_data.get("flow") == "report" and context.user_data.get("report", {}).get("step") == 2:
            context.user_data["report"]["country"] = None
            context.user_data["report"]["step"] = 3
            msg = await context.bot.send_message(chat_id=user.id, text="Revenue..⁉️", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    # ---------- Send Message ----------
    if data_cb == "send_message":
        if not is_admin(user.id):
            return
        # push previous flow and show send message kb
        push_flow(context, user.id, context.user_data.get("flow"))
        msg = await context.bot.send_message(chat_id=user.id, text="কাকে পাঠাবেন?", reply_markup=build_send_message_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "broadcast_everyone":
        if not is_admin(user.id):
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "broadcast_everyone"
        msg = await context.bot.send_message(chat_id=user.id, text="কি জানাতে চান..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "broadcast_selected":
        if not is_admin(user.id):
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "broadcast_selected_ids"
        msg = await context.bot.send_message(chat_id=user.id, text="ইউজার আইডি দিন..\n(একাধিক হলে নতুন লাইনে আলাদা করে লিখুন)", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    # ---------- Members ----------
    if data_cb == "members":
        if not is_admin(user.id):
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        msg = await context.bot.send_message(chat_id=user.id, text="📋 Members", reply_markup=build_members_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "members_list":
        if not is_admin(user.id):
            return
        text = list_members_text()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(LABEL["back"], callback_data="back")]])
        msg = await context.bot.send_message(chat_id=user.id, text=text, reply_markup=kb)
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "members_add":
        if not is_admin(user.id):
            return
        if not TEAMS:
            msg = await context.bot.send_message(chat_id=user.id, text="কোনো টিম নেই। আগে Team > Add Team দিয়ে একটি টিম যোগ করুন।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "members_add"
        context.user_data["members_add"] = {"step": 1}
        msg = await context.bot.send_message(chat_id=user.id, text="সদস্যের নাম..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "members_remove":
        if not is_admin(user.id):
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "members_remove"
        msg = await context.bot.send_message(chat_id=user.id, text="যেই সদস্যকে বের করতে চান তার ইউজার আইডি দিন।", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    # members_add pick team (inline)
    if data_cb.startswith("members_add_pickteam:"):
        if not is_admin(user.id):
            return
        if context.user_data.get("flow") != "members_add":
            msg = await context.bot.send_message(chat_id=user.id, text="স্টেপ টাইমআউট বা বাতিল হয়েছে।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        tname = data_cb.split(":", 1)[1]
        if tname not in TEAMS:
            msg = await context.bot.send_message(chat_id=user.id, text="টিম পাওয়া যায়নি।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        context.user_data["members_add"]["team"] = tname
        context.user_data["members_add"]["step"] = 3
        msg = await context.bot.send_message(chat_id=user.id, text="মেম্বার এর আইডি দিন।", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    # members_remove confirmation button callbacks
    if data_cb == "members_remove_no":
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল হয়েছে।", reply_markup=build_members_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    if data_cb == "members_remove_yes":
        code = context.user_data.get("members_remove_code")
        if not code or code not in MEMBERS:
            msg = await context.bot.send_message(chat_id=user.id, text="পাওয়া যায়নি।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return
        bound_tg = MEMBERS[code].get("tg_id")
        if bound_tg and is_default_admin(bound_tg):
            msg = await context.bot.send_message(chat_id=user.id, text="ডিফল্ট অ্যাডমিনকে মেম্বার থেকে বের করা যাবে না।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return
        if bound_tg and CLAIMS_BY_TG.get(bound_tg) == code:
            CLAIMS_BY_TG.pop(bound_tg, None)
            VERIFIED_TG_USERS.discard(bound_tg)
        MEMBERS.pop(code, None)
        save_data()
        msg = await context.bot.send_message(chat_id=user.id, text="✅ সদস্য রিমুভ হয়েছে।", reply_markup=build_members_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    # ---------- Team ----------
    if data_cb == "team":
        if not is_admin(user.id):
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        text = list_teams_text()
        msg = await context.bot.send_message(chat_id=user.id, text=text, reply_markup=build_team_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "team_add":
        if not is_default_admin(user.id):
            msg = await context.bot.send_message(chat_id=user.id, text="শুধু ডিফল্ট অ্যাডমিন টিম যোগ করতে পারবেন।", reply_markup=build_team_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "team_add"
        context.user_data["team_add"] = {"step": 1}
        msg = await context.bot.send_message(chat_id=user.id, text="টিমের নাম কি..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "team_remove":
        if not is_default_admin(user.id):
            msg = await context.bot.send_message(chat_id=user.id, text="শুধু ডিফল্ট অ্যাডমিন টিম ডিলিট করতে পারবেন।", reply_markup=build_team_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        if not TEAMS:
            msg = await context.bot.send_message(chat_id=user.id, text="কোনো টিম নেই।", reply_markup=build_team_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        kb = []
        for tname in TEAMS.keys():
            kb.append([InlineKeyboardButton(tname, callback_data=f"team_remove_pick:{tname}")])
        kb.append([InlineKeyboardButton(LABEL["back"], callback_data="back")])
        msg = await context.bot.send_message(chat_id=user.id, text="কোন টিম ডিলিট করবেন?", reply_markup=InlineKeyboardMarkup(kb))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb.startswith("team_remove_pick:"):
        if not is_default_admin(user.id):
            return
        tname = data_cb.split(":", 1)[1]
        if tname not in TEAMS:
            msg = await context.bot.send_message(chat_id=user.id, text="টিম পাওয়া যায়নি।", reply_markup=build_team_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data["flow"] = "team_remove_confirm"
        context.user_data["team_remove"] = {"name": tname}
        msg = await context.bot.send_message(chat_id=user.id, text=f"আপনি কি {tname} -কে ডিলিট করতে চান..⁉️", reply_markup=yes_no_kb("team_remove"))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "team_remove_no":
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল হয়েছে।", reply_markup=build_team_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    if data_cb == "team_remove_yes":
        tname = context.user_data.get("team_remove", {}).get("name")
        if not tname:
            msg = await context.bot.send_message(chat_id=user.id, text="কিছু ভুল হয়েছে।", reply_markup=build_team_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return
        TEAMS.pop(tname, None)
        save_data()
        msg = await context.bot.send_message(chat_id=user.id, text=f"✅ টিম '{tname}' ডিলিট করা হয়েছে।", reply_markup=build_team_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    # ---------- Admin ----------
    if data_cb == "admin":
        if not is_admin(user.id):
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        text = list_admins_text()
        msg = await context.bot.send_message(chat_id=user.id, text=text, reply_markup=build_admin_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "admin_add":
        if not is_default_admin(user.id):
            msg = await context.bot.send_message(chat_id=user.id, text="শুধু ডিফল্ট অ্যাডমিন নতুন অ্যাডমিন যুক্ত করতে পারবেন।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "admin_add"
        context.user_data["admin_add"] = {"step": 1}
        msg = await context.bot.send_message(chat_id=user.id, text="অ্যাডমিন এর নাম..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "admin_remove":
        if not is_default_admin(user.id):
            msg = await context.bot.send_message(chat_id=user.id, text="শুধু ডিফল্ট অ্যাডমিন অ্যাডমিন রিমুভ করতে পারবেন।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        # list removable admins (exclude default)
        buttons = []
        for aid, info in ADMINS.items():
            if info.get("is_default"):
                continue
            buttons.append([InlineKeyboardButton(info["name"], callback_data=f"admin_remove_pick:{aid}")])
        # include default admins too so they can be targeted (will ask gmail password)
        for aid, info in ADMINS.items():
            if info.get("is_default"):
                buttons.append([InlineKeyboardButton(info["name"]+" (Default)", callback_data=f"admin_remove_pick:{aid}")])
        if not buttons:
            msg = await context.bot.send_message(chat_id=user.id, text="রিমুভ করার মতো অ্যাডমিন নেই।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        buttons.append([InlineKeyboardButton(LABEL["back"], callback_data="back")])
        msg = await context.bot.send_message(chat_id=user.id, text="আপনি কাকে অ্যাডমিন থেকে বের করে দিতে চাইছেন..⁉️", reply_markup=InlineKeyboardMarkup(buttons))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb.startswith("admin_remove_pick:"):
        if not is_default_admin(user.id):
            return
        target_id = data_cb.split(":", 1)[1]
        target = ADMINS.get(target_id)
        if not target:
            msg = await context.bot.send_message(chat_id=user.id, text="পাওয়া যায়নি।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data["flow"] = "admin_remove_confirm"
        context.user_data["admin_remove"] = {"target_id": target_id}
        name = target["name"]
        msg = await context.bot.send_message(chat_id=user.id, text=f"আপনি কি {name} -কে অ্যাডমিনিস্ট্রেশন থেকে বের করতে চান..⁉️", reply_markup=yes_no_kb("admin_remove"))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if data_cb == "admin_remove_no":
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল হয়েছে।", reply_markup=build_admin_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    if data_cb == "admin_remove_yes":
        # If removing selected admin -> ask password based on whether target is default
        target_id = context.user_data.get("admin_remove", {}).get("target_id")
        if not target_id:
            msg = await context.bot.send_message(chat_id=user.id, text="কোনো টার্গেট সিলেক্ট করা নেই।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        # Check if target is default admin
        if ADMINS.get(target_id, {}).get("is_default"):
            push_flow(context, user.id, context.user_data.get("flow"))
            context.user_data["flow"] = "admin_remove_password_gmail"
            msg = await context.bot.send_message(chat_id=user.id, text="আপনার জিমেইল এর পাসওয়ার্ড দিন।", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        else:
            push_flow(context, user.id, context.user_data.get("flow"))
            context.user_data["flow"] = "admin_remove_password_fb"
            msg = await context.bot.send_message(chat_id=user.id, text="আপনার ফেসবুক আইডির পাসওয়ার্ড দিন।", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return

    # ---------- Accept admin callback (from invite) ----------
    if data_cb == "accept_admin":
        # grant admin to the clicking user
        ensure_admin_entry_for_id(user.id, user.username or "", user.full_name or user.first_name or "Admin", default=False)
        # remove from pending if any matches username
        keep = []
        for pa in PENDING_ADMINS:
            pa_uname = pa.get("username","").lstrip("@") if pa.get("username") else ""
            if user.username and pa_uname == user.username:
                continue
            keep.append(pa)
        PENDING_ADMINS.clear()
        PENDING_ADMINS.extend(keep)
        save_data()
        await context.bot.send_message(chat_id=user.id, text="✅ আপনি এখন CPA Master এর একজন অ্যাডমিন।")
        return

    # fallback: unknown callback
    return


# ---------------- Message handler ----------------
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text if update.message else ""
    flow = context.user_data.get("flow")

    # cancel shortcut
    if text and text.strip().lower() in ["/cancel", "cancel", "বাতিল"]:
        context.user_data.clear()
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল করা হলো।", reply_markup=build_admin_menu() if is_admin(user.id) else None)
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    # mainadmin password flow
    if flow == "mainadmin_password":
        if text == ADMIN_PASSWORD_FB:
            ensure_admin_entry_for_id(user.id, user.username, user.full_name or user.first_name or "Admin", default=True)
            await update.message.reply_text("আপনি এখন একজন ডিফল্ট অ্যাডমিন। ✅")
        else:
            await update.message.reply_text("🖕")
        context.user_data.clear()
        return

    # admin remove password flows
    if flow == "admin_remove_password_gmail":
        if text == ADMIN_PASSWORD_GMAIL:
            target_id = context.user_data.get("admin_remove", {}).get("target_id")
            if target_id:
                ADMINS.pop(str(target_id), None)
                save_data()
                await update.message.reply_text("✅ ডিফল্ট অ্যাডমিন রিমুভ করা হয়েছে।", reply_markup=build_admin_kb())
            else:
                await update.message.reply_text("কিছু ভুল হয়েছে।", reply_markup=build_admin_kb())
        else:
            await update.message.reply_text("পাসওয়ার্ড ভুল। অপারেশন বাতিল।", reply_markup=build_admin_kb())
        context.user_data.clear()
        return

    if flow == "admin_remove_password_fb":
        if text == ADMIN_PASSWORD_FB:
            target_id = context.user_data.get("admin_remove", {}).get("target_id")
            if target_id:
                ADMINS.pop(str(target_id), None)
                save_data()
                await update.message.reply_text("✅ অ্যাডমিন রিমুভ করা হয়েছে।", reply_markup=build_admin_kb())
            else:
                await update.message.reply_text("কিছু ভুল হয়েছে।", reply_markup=build_admin_kb())
        else:
            await update.message.reply_text("পাসওয়ার্ড ভুল। অপারেশন বাতিল।", reply_markup=build_admin_kb())
        context.user_data.clear()
        return

    # REPORT flow steps
    if flow == "report":
        step = context.user_data["report"].get("step", 0)
        if step == 1:
            code = text.strip()
            m = MEMBERS.get(code)
            if not m:
                await update.message.reply_text("এই ইউজার আইডি পাওয়া যায়নি। আগে Members > Add Member দিয়ে সদস্য যুক্ত করুন।")
                return
            context.user_data["report"]["code"] = code
            context.user_data["report"]["step"] = 2
            msg = await context.bot.send_message(chat_id=user.id, text="Country..⁉️", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(LABEL["empty"], callback_data="report_country_empty")],[InlineKeyboardButton(LABEL["cancel"], callback_data="cancel")]]))
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        elif step == 2:
            context.user_data["report"]["country"] = text.strip()
            context.user_data["report"]["step"] = 3
            msg = await context.bot.send_message(chat_id=user.id, text="Revenue..⁉️", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        elif step == 3:
            context.user_data["report"]["revenue"] = text.strip()
            code = context.user_data["report"]["code"]
            country = context.user_data["report"].get("country")
            revenue = context.user_data["report"]["revenue"]
            member = MEMBERS[code]
            member_name = member["name"]
            team_name = member.get("team", "—")
            target_tg_id = member.get("tg_id")

            # Group message
            group_lines = []
            group_lines.append("Congratulations Everyone💌")
            group_lines.append("")
            group_lines.append(f"©️ Name : {member_name}")
            group_lines.append(f"ℹ️ Use id : <code>`{code}`</code>")
            group_lines.append(f"♻️ Team™ : {team_name}")
            if country:
                group_lines.append(f"🌐 Country : {country}")
            group_lines.append(f"💸 Revenue : {revenue}$")
            group_lines.append("")
            group_lines.append("🔃 সবাই এই ভাবেই কাজ চালিয়ে যাও 🔃")
            group_lines.append("যেকোনো সমস্যায় মেসেজ কর👇👇")
            # USE MESSAGE_ID_LINK here so it's easy to change later
            group_lines.append(f"{MESSAGE_ID_LINK}")
            group_msg = "\n".join(group_lines)
            group_msg = f"<b>{group_msg}</b>"

            try:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=group_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e:
                logger.exception(e)
                await update.message.reply_text("গ্রুপে পাঠানো গেল না (GROUP_CHAT_ID ঠিক আছে কি না দেখুন)।")

            # User message
            user_lines = []
            user_lines.append(f"Congratulation {member_name}💌")
            user_lines.append("")
            user_lines.append(f"ℹ️ Use id : <code>`{code}`</code>")
            user_lines.append(f"♻️ Team™ : {team_name}")
            if country:
                user_lines.append(f"🌐 Country : {country}")
            user_lines.append(f"💸 Revenue : {revenue} $")
            user_lines.append("")
            user_lines.append("🔃 এই ভাবেই কাজ চালিয়ে যাও 🔃")
            user_lines.append("যেকোনো সমস্যায় মেসেজ কর👇👇")
            user_lines.append(f"{MESSAGE_ID_LINK}")
            user_msg = "\n".join(user_lines)
            user_msg = f"<b>{user_msg}</b>"

            if target_tg_id:
                try:
                    await context.bot.send_message(chat_id=target_tg_id, text=user_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception as e:
                    logger.exception(e)
                    await update.message.reply_text("ব্যবহারকারীর ইনবক্সে পাঠানো জায়নি (সে কি বট /start করেছে?).")
            else:
                await update.message.reply_text("সদস্যটি এখনও বট ভেরিফাই করেনি, তাই ইনবক্সে পাঠানো সম্ভব হয়নি।")

            msg = await context.bot.send_message(chat_id=user.id, text="✅ Report পাঠানো হয়েছে।", reply_markup=build_admin_menu())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return

    # Broadcast everyone
    if flow == "broadcast_everyone":
        msg_text = text
        sent, failed = 0, 0
        for tg_id in list(VERIFIED_TG_USERS):
            try:
                await context.bot.send_message(chat_id=tg_id, text=msg_text)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to {tg_id}: {e}")
                failed += 1
        msg = await update.message.reply_text(f"Everyone ব্রডকাস্ট সম্পন্ন। ✅\nসফল: {sent}, ব্যর্থ: {failed}", reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    # Broadcast selected: collect codes in previous step
    if flow == "broadcast_selected_ids":
        codes = [line.strip() for line in text.splitlines() if line.strip()]
        context.user_data["broadcast_selected"] = {"codes": codes}
        context.user_data["flow"] = "broadcast_selected_message"
        msg = await context.bot.send_message(chat_id=user.id, text="কি জানাতে চান..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if flow == "broadcast_selected_message":
        msg_text = text
        data_bs = context.user_data.get("broadcast_selected", {})
        codes: List[str] = data_bs.get("codes", [])
        targets: List[int] = []
        not_found = []
        not_verified = []
        for c in codes:
            m = MEMBERS.get(c)
            if not m:
                not_found.append(c)
                continue
            tg = m.get("tg_id")
            if not tg:
                not_verified.append(c)
                continue
            targets.append(tg)
        sent, failed = 0, 0
        for tg_id in targets:
            try:
                await context.bot.send_message(chat_id=tg_id, text=msg_text)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to {tg_id}: {e}")
                failed += 1
        reply = f"Selected Member ব্রডকাস্ট সম্পন্ন। ✅\nসফল: {sent}, ব্যর্থ: {failed}"
        if not_found:
            reply += f"\n\nনিচের ইউজার কোডগুলো পাওয়া যায়নি: {', '.join(not_found)}"
        if not_verified:
            reply += f"\n\nনিচের ইউজার কোডগুলো ভেরিফাই করা নেই (তাদের ইনবক্সে পাঠানো যায়নি): {', '.join(not_verified)}"
        msg = await update.message.reply_text(reply, reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    # Members add flow (text)
    if flow == "members_add":
        step = context.user_data["members_add"].get("step", 0)
        if step == 1:
            context.user_data["members_add"]["name"] = text.strip()
            # ask to pick team via inline buttons
            kb = []
            for tname in TEAMS.keys():
                kb.append([InlineKeyboardButton(tname, callback_data=f"members_add_pickteam:{tname}")])
            kb.append([InlineKeyboardButton(LABEL["cancel"], callback_data="cancel")])
            msg = await update.message.reply_text("টিম নির্বাচন করুন। (ইনলাইন বাটন থেকে বেছে নিন)", reply_markup=InlineKeyboardMarkup(kb))
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data["members_add"]["step"] = 2
            return
        elif step == 3:
            code = text.strip()
            if code in MEMBERS:
                msg = await update.message.reply_text("এই ইউজার কোড আগে থেকেই আছে। অন্যটি দিন।", reply_markup=cancel_kb())
                store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
                return
            name = context.user_data["members_add"]["name"]
            team = context.user_data["members_add"]["team"]
            MEMBERS[code] = {"code": code, "name": name, "team": team, "tg_id": None, "username": None}
            save_data()
            msg = await update.message.reply_text("✅ সদস্য যুক্ত হয়েছে।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return

    # Members remove flow (admin types code then confirm)
    if flow == "members_remove":
        code = text.strip()
        if code not in MEMBERS:
            msg = await update.message.reply_text("এই ইউজার আইডিটি পাওয়া যায়নি।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return
        context.user_data["members_remove_code"] = code
        msg = await update.message.reply_text("আপনি কি নিশ্চিত..⁉️", reply_markup=yes_no_kb("members_remove"))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data["flow"] = "members_remove_confirm_pending"
        return

    # Team add flow (text)
    if flow == "team_add":
        step = context.user_data["team_add"].get("step", 0)
        if step == 1:
            tname = text.strip()
            if tname in TEAMS:
                msg = await update.message.reply_text("এই নামে একটি টিম আছে, অন্য নাম দিন।", reply_markup=cancel_kb())
                store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
                return
            context.user_data["team_add"]["name"] = tname
            context.user_data["team_add"]["step"] = 2
            msg = await context.bot.send_message(chat_id=user.id, text="টিমের লিডার কে..⁉️\\n(লিডারের টেলিগ্রাম ইউজারনেম দিন, যেমন: @username বা তার একটি মেসেজ ফরওয়ার্ড করুন)", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        elif step == 2:
            leader_username = text.strip()
            if leader_username.startswith("@"):
                TEAMS[context.user_data["team_add"]["name"]] = {
                    "name": context.user_data["team_add"]["name"],
                    "leader_code": None,
                    "leader_tg_id": None,
                    "leader_username": leader_username,
                }
                save_data()
                msg = await update.message.reply_text("✅ টিম যুক্ত হয়েছে।", reply_markup=build_team_kb())
                store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
                context.user_data.clear()
            else:
                msg = await update.message.reply_text("সঠিক ফরম্যাট দিন (যেমন @username) অথবা লিডারের একটি মেসেজ ফরওয়ার্ড করুন।", reply_markup=cancel_kb())
                store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return

    # Admin add flow (text)
    if flow == "admin_add":
        step = context.user_data["admin_add"].get("step", 0)
        if step == 1:
            context.user_data["admin_add"]["name"] = text.strip()
            context.user_data["admin_add"]["step"] = 2
            msg = await update.message.reply_text("অ্যাডমিন এর টেলিগ্রাম ইউজার নাম দিন অথবা তার একটি মেসেজ ফরওয়ার্ড করুন।", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        elif step == 2:
            uname = text.strip()
            if not uname.startswith("@"):
                msg = await update.message.reply_text("ইউজারনেম দিন (যেমন @username) অথবা তার ফরওয়ার্ড করা মেসেজ দিন।", reply_markup=cancel_kb())
                store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
                return
            new_admin = {
                "id": None,
                "username": uname.lstrip("@"),
                "name": context.user_data["admin_add"]["name"],
                "is_default": False,
            }
            PENDING_ADMINS.append(new_admin)
            save_data()
            # Try to send invite message to the username (if possible)
            try:
                chat = await context.bot.get_chat(uname)  # uname like @username
                invite_kb = InlineKeyboardMarkup([[InlineKeyboardButton("Accept", callback_data="accept_admin")]])
                await context.bot.send_message(chat_id=chat.id, text="আপনাকে CPA Master এর একজন অ্যাডমিন হিসেবে আমন্ত্রণ জানানো হয়েছে।", reply_markup=invite_kb)
            except Exception as e:
                # unable to send (user not started bot / privacy) - we keep pending
                logger.info("Could not send invite to %s: %s", uname, e)
            msg = await update.message.reply_text("✅ নতুন অ্যাডমিন পেন্ডিং হিসেবে যোগ হয়েছে (সে Accept করলে অ্যাডমিন হবে)।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return

    # User verification flow (users give their member code)
    if flow == "user_verify":
        code = text.strip()
        member = MEMBERS.get(code)
        if not member:
            await update.message.reply_text("ভুল ইউজার আইডি। অ্যাডমিন থেকে সঠিক আইডি নিন।")
            return
        # check if this code already claimed by other tg user
        for tg_id, claimed_code in CLAIMS_BY_TG.items():
            if claimed_code == code and tg_id != user.id:
                await update.message.reply_text("এই ইউজার আইডি দিয়ে ইতিমধ্যে আরেকজন ভেরিফাইড।")
                context.user_data.clear()
                return
        # bind this tg user with code
        member["tg_id"] = user.id
        member["username"] = user.username or member.get("username")
        VERIFIED_TG_USERS.add(user.id)
        CLAIMS_BY_TG[user.id] = code
        # bind pending admin if username matches
        keep = []
        for pa in PENDING_ADMINS:
            if pa.get("username") and user.username and pa["username"].lstrip("@") == user.username:
                ensure_admin_entry_for_id(user.id, user.username, pa.get("name") or user.full_name or user.first_name or "Admin", default=False)
            else:
                keep.append(pa)
        PENDING_ADMINS.clear()
        PENDING_ADMINS.extend(keep)
        save_data()
        # welcome with join group
        welcome_text = f"{member['name']} Welcome to SM IT FORCE\n\nআমাদের গ্রুপে যুক্ত হও সবকিছুর আপডেট পেতে।"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("Join Group", url=GROUP_LINK)]])
        await update.message.reply_text(welcome_text, reply_markup=btn)
        context.user_data.clear()
        return

    # fallback for admins: show menu
    if is_admin(user.id):
        msg = await update.message.reply_text("মেনু:", reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return


# ---------------- Forwards handler (capture leader/admin via forwarded msg) ----------------
async def on_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    if not is_admin(user.id):
        return
    fwd_from = update.message.forward_from
    if context.user_data.get("flow") == "team_add" and context.user_data["team_add"].get("step") == 2:
        if not fwd_from:
            await update.message.reply_text("একটি ফরওয়ার্ড করা মেসেজ দিন অথবা @username লিখে পাঠান।")
            return
        tname = context.user_data["team_add"]["name"]
        TEAMS[tname] = {
            "name": tname,
            "leader_code": None,
            "leader_tg_id": fwd_from.id,
            "leader_username": f"@{fwd_from.username}" if fwd_from.username else "",
        }
        save_data()
        msg = await update.message.reply_text("✅ টিম যুক্ত হয়েছে।", reply_markup=build_team_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    if context.user_data.get("flow") == "admin_add" and context.user_data["admin_add"].get("step") == 2:
        if not fwd_from:
            await update.message.reply_text("একটি ফরওয়ার্ড করা মেসেজ দিন অথবা @username লিখে পাঠান।")
            return
        name = context.user_data["admin_add"]["name"]
        ensure_admin_entry_for_id(fwd_from.id, fwd_from.username or "", name, default=False)
        # try to send invite message
        try:
            invite_kb = InlineKeyboardMarkup([[InlineKeyboardButton("Accept", callback_data="accept_admin")]])
            await context.bot.send_message(chat_id=fwd_from.id, text="আপনাকে CPA Master এর একজন অ্যাডমিন হিসেবে আমন্ত্রণ জানানো হয়েছে।", reply_markup=invite_kb)
        except Exception as e:
            logger.info("Could not send invite to forwarded user id %s: %s", fwd_from.id, e)
        msg = await update.message.reply_text("✅ নতুন অ্যাডমিন যুক্ত হয়েছে।", reply_markup=build_admin_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return


# ---------------- Listing helper functions ----------------
def list_members_text() -> str:
    if not MEMBERS:
        return "কোনো সদস্য যুক্ত করা নেই।"
    lines = []
    for code, m in MEMBERS.items():
        uname = f"@{m['username']}" if m.get("username") else "—"
        uid = m.get("tg_id")
        uid_txt = f"{uid}" if uid else "—"
        lines.append(f"• নাম: {m['name']}\n   টিম: {m.get('team','—')}\n   টেলিগ্রাম: {uname}\n   ইউজার কোড: {code}\n   TG ID: {uid_txt}")
    return "\n\n".join(lines)


def list_teams_text() -> str:
    if not TEAMS:
        return "কোনো টিম নেই।"
    lines = []
    for tname, t in TEAMS.items():
        leader_line = "—"
        if t.get("leader_tg_id") and t.get("leader_username"):
            leader_line = f"{t.get('leader_username')} (ID: {t.get('leader_tg_id')})"
        elif t.get("leader_tg_id"):
            leader_line = f"ID: {t.get('leader_tg_id')}"
        elif t.get("leader_username"):
            leader_line = t.get("leader_username")
        lines.append(f"• টিম: {tname}\n   লিডার: {leader_line}")
    return "\n\n".join(lines)


def list_admins_text() -> str:
    if not ADMINS:
        return "কোনো অ্যাডমিন নেই।"
    lines = []
    for aid, info in ADMINS.items():
        tag = " (Default)" if info.get("is_default") else ""
        uline = f"@{info.get('username')}" if info.get("username") else "—"
        lines.append(f"• {info.get('name')}{tag}\n   ইউজারনেম: {uline}\n   ID: {aid}")
    return "\n\n".join(lines)


# ---------------- App bootstrap ----------------
def main():
    load_data()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mainadmin", mainadmin))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.FORWARDED, on_forward))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("Bot is running with webhook...")
    # Run webhook for Vercel: listen on port from env, url_path is BOT_TOKEN for simple routing
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )


if __name__ == "__main__":
    main()


# Flask app
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    application.update_queue.put_nowait(update)
    return "ok"

@app.route("/", methods=["GET"])
def home():
    return "Bot is running on Vercel!"

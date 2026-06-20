import os
import json
import logging
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_CHAT_ID = -1002565129037  
GROUP_LINK = "https://t.me/cpamastaer7383"
MESSAGE_ID_LINK = "t.me/mostakim_21"   

ADMIN_PASSWORD_FB = "@2009@MOHAMMAD#"
ADMIN_PASSWORD_GMAIL = "password"

DEFAULT_ADMIN = {
    "id": 7152410095,
    "username": "mostakim_21",
    "name": "Mostakim",
}
# Vercel-এ রাইট পারমিশন পেতে /tmp ফোল্ডার ব্যবহার করা নিরাপদ
DATA_FILE = "/tmp/data.json" 
# ----------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Telegram Application (Without starting it globally)
ptb_application = Application.builder().token(BOT_TOKEN).build()

# In-memory structures
ADMINS = {}
MEMBERS = {}
TEAMS = {}
VERIFIED_TG_USERS = set()
CLAIMS_BY_TG = {}
PENDING_ADMINS = []

def load_data():
    global ADMINS, MEMBERS, TEAMS, VERIFIED_TG_USERS, CLAIMS_BY_TG, PENDING_ADMINS
    if not os.path.exists(DATA_FILE):
        ADMINS = {str(DEFAULT_ADMIN["id"]): {"id": DEFAULT_ADMIN["id"], "username": DEFAULT_ADMIN["username"], "name": DEFAULT_ADMIN["name"], "is_default": True}}
        MEMBERS, TEAMS, PENDING_ADMINS = {}, {}, []
        VERIFIED_TG_USERS, CLAIMS_BY_TG = set(), {}
        save_data()
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.exception("Failed to load data.json: %s", e)
        ADMINS = {str(DEFAULT_ADMIN["id"]): {"id": DEFAULT_ADMIN["id"], "username": DEFAULT_ADMIN["username"], "name": DEFAULT_ADMIN["name"], "is_default": True}}
        MEMBERS, TEAMS, PENDING_ADMINS = {}, {}, []
        VERIFIED_TG_USERS, CLAIMS_BY_TG = set(), {}
        save_data()
        return

    ADMINS = {}
    for k, v in (data.get("admins") or {}).items():
        ADMINS[str(k)] = {"id": int(v.get("id", int(k))), "username": v.get("username", ""), "name": v.get("name", ""), "is_default": bool(v.get("is_default", False))}
    if str(DEFAULT_ADMIN["id"]) not in ADMINS:
        ADMINS[str(DEFAULT_ADMIN["id"])] = {"id": DEFAULT_ADMIN["id"], "username": DEFAULT_ADMIN["username"], "name": DEFAULT_ADMIN["name"], "is_default": True}

    MEMBERS = data.get("members", {}) or {}
    TEAMS = data.get("teams", {}) or {}
    VERIFIED_TG_USERS = set(int(x) for x in (data.get("verified", []) or []))
    CLAIMS_BY_TG = {int(k): v for k, v in (data.get("claims") or {}).items()}
    PENDING_ADMINS = data.get("pending_admins", []) or []

def save_data():
    try:
        data = {
            "admins": ADMINS,
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

def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMINS

def is_default_admin(user_id: int) -> bool:
    return is_admin(user_id) and ADMINS.get(str(user_id), {}).get("is_default", False)

def ensure_admin_entry_for_id(user_id: int, username: str, name: str, default=False):
    ADMINS[str(user_id)] = {"id": user_id, "username": username or "", "name": name, "is_default": default}
    save_data()

def html_bold(s: str) -> str:
    return f"<b>{s}</b>"

LABEL = {
    "send_report": "📊Send Report", "send_message": "📤 Send Message 📤", "members": "👤 Members 👤",
    "team": "☸️ Team ☸️", "admin": "🪪 Admin", "everyone": "👥 Everyone 👥", "selected_member": "➰Selected Member➰",
    "member_list": "📝 Member List", "add_member": "➕ Add Member ➕", "remove_member": "⛔ Remove Member ⛔",
    "add_team": "➕ Add Team ➕", "remove_team": "⛔ Remove Team ⛔", "add_admin": "➕ Add Admin ➕",
    "remove_admin": "⛔ Remove Admin ⛂", "yes": "🆗 Yes", "no": "🚫 No", "back": "↪️ Back", "cancel": "🚫 Cancel", "empty": "🆑 Empty",
}

def build_admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(LABEL["send_report"], callback_data="send_report")],
        [InlineKeyboardButton(LABEL["send_message"], callback_data="send_message")],
        [InlineKeyboardButton(LABEL["members"], callback_data="members")],
        [InlineKeyboardButton(LABEL["team"], callback_data="team")],
        [InlineKeyboardButton(LABEL["admin"], callback_data="admin")],
    ])

def build_send_message_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(LABEL["everyone"], callback_data="broadcast_everyone")],
        [InlineKeyboardButton(LABEL["selected_member"], callback_data="broadcast_selected")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ])

def build_members_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(LABEL["member_list"], callback_data="members_list")],
        [InlineKeyboardButton(LABEL["add_member"], callback_data="members_add")],
        [InlineKeyboardButton(LABEL["remove_member"], callback_data="members_remove")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ])

def build_team_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(LABEL["add_team"], callback_data="team_add")],
        [InlineKeyboardButton(LABEL["remove_team"], callback_data="team_remove")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ])

def build_admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(LABEL["add_admin"], callback_data="admin_add")],
        [InlineKeyboardButton(LABEL["remove_admin"], callback_data="admin_remove")],
        [InlineKeyboardButton(LABEL["back"], callback_data="back")],
    ])

def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(LABEL["cancel"], callback_data="cancel")]])

def yes_no_kb(prefix: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton(LABEL["no"], callback_data=f"{prefix}_no"), InlineKeyboardButton(LABEL["yes"], callback_data=f"{prefix}_yes")]])

def store_last_bot_message(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, message_id: int):
    context.bot_data[f"last_msg:{user_id}"] = {"chat_id": chat_id, "message_id": message_id}

async def try_delete_last_bot_message(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    info = context.bot_data.get(f"last_msg:{user_id}")
    if not info: return
    try: await context.bot.delete_message(chat_id=info["chat_id"], message_id=info["message_id"])
    except: pass
    context.bot_data.pop(f"last_msg:{user_id}", None)

def push_flow(context: ContextTypes.DEFAULT_TYPE, user_id: int, previous_flow: str):
    if previous_flow is None: return
    stack = context.user_data.get("flow_stack", [])
    stack.append(previous_flow)
    context.user_data["flow_stack"] = stack

def pop_flow(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    stack = context.user_data.get("flow_stack", [])
    if not stack: return None
    prev = stack.pop()
    context.user_data["flow_stack"] = stack
    return prev

async def render_flow_for_user(user, context: ContextTypes.DEFAULT_TYPE, flow: str):
    try: await try_delete_last_bot_message(context, user.id)
    except: pass
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
        msg = await context.bot.send_message(chat_id=user.id, text=list_teams_text(), reply_markup=build_team_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if flow == "admin":
        msg = await context.bot.send_message(chat_id=user.id, text=list_admins_text(), reply_markup=build_admin_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    msg = await context.bot.send_message(chat_id=user.id, text="WELCOME", reply_markup=build_admin_menu())
    store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
    context.user_data.clear()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat = update.effective_user, update.effective_chat
    context.user_data.clear()
    if is_admin(user.id):
        try:
            if update.message: await update.message.delete()
        except: pass
        msg = await context.bot.send_message(chat_id=chat.id, text="WELCOME", reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if user.id in VERIFIED_TG_USERS:
        await context.bot.send_message(chat_id=chat.id, text=html_bold("আপনি ইতিমধ্যে ভেরিফাইড।"), parse_mode=ParseMode.HTML)
        return
    context.user_data["flow"] = "user_verify"
    msg = await context.bot.send_message(chat_id=chat.id, text=html_bold("আপনার ইউজার আইডি দিন।"), parse_mode=ParseMode.HTML)
    store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)

async def mainadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="শুধু অ্যাডমিনরাই এই কমান্ড ব্যবহার করতে পারবেন।")
        return
    push_flow(context, user.id, context.user_data.get("flow"))
    context.user_data["flow"] = "mainadmin_password"
    msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="আপনার ফেসবুক আইডির পাসওয়ার্ড দিন।", reply_markup=cancel_kb())
    store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()
    data_cb, user = query.data, query.from_user
    await try_delete_last_bot_message(context, user.id)

    if data_cb in ["back", "back_admin", "back_menu"]:
        prev = pop_flow(context, user.id)
        await render_flow_for_user(user, context, prev)
        return
    if data_cb == "cancel":
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল করা হলো।", reply_markup=build_admin_menu() if is_admin(user.id) else None)
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return
    if data_cb == "send_report":
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "report"
        context.user_data["report"] = {"step": 1}
        msg = await context.bot.send_message(chat_id=user.id, text="User ID..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "report_country_empty":
        if context.user_data.get("flow") == "report" and context.user_data.get("report", {}).get("step") == 2:
            context.user_data["report"]["country"] = None
            context.user_data["report"]["step"] = 3
            msg = await context.bot.send_message(chat_id=user.id, text="Revenue..⁉️", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "send_message":
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        msg = await context.bot.send_message(chat_id=user.id, text="কাকে পাঠাবেন?", reply_markup=build_send_message_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "broadcast_everyone":
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "broadcast_everyone"
        msg = await context.bot.send_message(chat_id=user.id, text="কি জানাতে চান..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "broadcast_selected":
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "broadcast_selected_ids"
        msg = await context.bot.send_message(chat_id=user.id, text="ইউজার আইডি দিন..\n(একাধিক হলে নতুন লাইনে আলাদা করে লিখুন)", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "members":
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        msg = await context.bot.send_message(chat_id=user.id, text="📋 Members", reply_markup=build_members_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "members_list":
        if not is_admin(user.id): return
        msg = await context.bot.send_message(chat_id=user.id, text=list_members_text(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(LABEL["back"], callback_data="back")]]))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "members_add":
        if not is_admin(user.id): return
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
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data.clear()
        context.user_data["flow"] = "members_remove"
        msg = await context.bot.send_message(chat_id=user.id, text="যেই সদস্যকে বের করতে চান তার ইউজার আইডি দিন।", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb.startswith("members_add_pickteam:"):
        if not is_admin(user.id): return
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
    if data_cb == "team":
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        msg = await context.bot.send_message(chat_id=user.id, text=list_teams_text(), reply_markup=build_team_kb())
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
        kb = [[InlineKeyboardButton(tname, callback_data=f"team_remove_pick:{tname}")] for tname in TEAMS.keys()]
        kb.append([InlineKeyboardButton(LABEL["back"], callback_data="back")])
        msg = await context.bot.send_message(chat_id=user.id, text="কোন টিম ডিলিট করবেন?", reply_markup=InlineKeyboardMarkup(kb))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb.startswith("team_remove_pick:"):
        if not is_default_admin(user.id): return
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
    if data_cb == "admin":
        if not is_admin(user.id): return
        push_flow(context, user.id, context.user_data.get("flow"))
        msg = await context.bot.send_message(chat_id=user.id, text=list_admins_text(), reply_markup=build_admin_kb())
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
        buttons = []
        for aid, info in ADMINS.items():
            if info.get("is_default"): continue
            buttons.append([InlineKeyboardButton(info["name"], callback_data=f"admin_remove_pick:{aid}")])
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
        if not is_default_admin(user.id): return
        target_id = data_cb.split(":", 1)[1]
        target = ADMINS.get(target_id)
        if not target:
            msg = await context.bot.send_message(chat_id=user.id, text="পাওয়া যায়নি।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        push_flow(context, user.id, context.user_data.get("flow"))
        context.user_data["flow"] = "admin_remove_confirm"
        context.user_data["admin_remove"] = {"target_id": target_id}
        msg = await context.bot.send_message(chat_id=user.id, text=f"আপনি কি {target['name']} -কে অ্যাডমিনিস্ট্রেশন থেকে বের করতে চান..⁉️", reply_markup=yes_no_kb("admin_remove"))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return
    if data_cb == "admin_remove_no":
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল হয়েছে।", reply_markup=build_admin_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return
    if data_cb == "admin_remove_yes":
        target_id = context.user_data.get("admin_remove", {}).get("target_id")
        if not target_id:
            msg = await context.bot.send_message(chat_id=user.id, text="কোনো টার্গেট সিলেক্ট করা নেই।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
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
    if data_cb == "accept_admin":
        ensure_admin_entry_for_id(user.id, user.username or "", user.full_name or user.first_name or "Admin", default=False)
        PENDING_ADMINS[:] = [pa for pa in PENDING_ADMINS if not (user.username and pa.get("username", "").lstrip("@") == user.username)]
        save_data()
        await context.bot.send_message(chat_id=user.id, text="✅ আপনি এখন CPA Master এর একজন অ্যাডমিন।")
        return

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text if update.message else ""
    flow = context.user_data.get("flow")

    if text and text.strip().lower() in ["/cancel", "cancel", "বাতিল"]:
        context.user_data.clear()
        msg = await context.bot.send_message(chat_id=user.id, text="বাতিল করা হলো।", reply_markup=build_admin_menu() if is_admin(user.id) else None)
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if flow == "mainadmin_password":
        if text == ADMIN_PASSWORD_FB:
            ensure_admin_entry_for_id(user.id, user.username, user.full_name or user.first_name or "Admin", default=True)
            await update.message.reply_text("আপনি এখন একজন ডিফল্ট অ্যাডমিন। ✅")
        else:
            await update.message.reply_text("🖕")
        context.user_data.clear()
        return

    if flow == "admin_remove_password_gmail":
        if text == ADMIN_PASSWORD_GMAIL:
            target_id = context.user_data.get("admin_remove", {}).get("target_id")
            if target_id:
                ADMINS.pop(str(target_id), None)
                save_data()
                await update.message.reply_text("✅ ডিফল্ট অ্যাডমিন রিমুভ করা হয়েছে।", reply_markup=build_admin_kb())
            else: await update.message.reply_text("কিছু ভুল হয়েছে।", reply_markup=build_admin_kb())
        else: await update.message.reply_text("পাসওয়ার্ড ভুল। অপারেশন বাতিল।", reply_markup=build_admin_kb())
        context.user_data.clear()
        return

    if flow == "admin_remove_password_fb":
        if text == ADMIN_PASSWORD_FB:
            target_id = context.user_data.get("admin_remove", {}).get("target_id")
            if target_id:
                ADMINS.pop(str(target_id), None)
                save_data()
                await update.message.reply_text("✅ অ্যাডমিন রিমুভ করা হয়েছে।", reply_markup=build_admin_kb())
            else: await update.message.reply_text("কিছু ভুল হয়েছে।", reply_markup=build_admin_kb())
        else: await update.message.reply_text("পাসওয়ার্ড ভুল। অপারেশন বাতিল।", reply_markup=build_admin_kb())
        context.user_data.clear()
        return

    if flow == "report":
        step = context.user_data["report"].get("step", 0)
        if step == 1:
            code = text.strip()
            if code not in MEMBERS:
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
            
            group_msg = f"<b>Congratulations Everyone💌\n\n©️ Name : {member['name']}\nℹ️ Use id : <code>`{code}`</code>\n♻️ Team™ : {member.get('team', '—')}\n"
            if country: group_msg += f"🌐 Country : {country}\n"
            group_msg += f"💸 Revenue : {revenue}$\n\n🔃 সবাই এই ভাবেই কাজ চালিয়ে যাও 🔃\nযেকোনো সমস্যায় মেসেজ কর👇👇\n{MESSAGE_ID_LINK}</b>"

            try: await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=group_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e: logger.exception(e); await update.message.reply_text("গ্রুপে পাঠানো গেল না।")

            user_msg = f"<b>Congratulation {member['name']}💌\n\nℹ️ Use id : <code>`{code}`</code>\n♻️ Team™ : {member.get('team', '—')}\n"
            if country: user_msg += f"🌐 Country : {country}\n"
            user_msg += f"💸 Revenue : {revenue} $\n\n🔃 এই ভাবেই কাজ চালিয়ে যাও 🔃\nযেকোনো সমস্যায় মেসেজ কর👇👇\n{MESSAGE_ID_LINK}</b>"

            if member.get("tg_id"):
                try: await context.bot.send_message(chat_id=member["tg_id"], text=user_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except: await update.message.reply_text("ব্যবহারকারীর ইনবক্সে পাঠানো যায়নি।")
            else: await update.message.reply_text("সদস্যটি এখনও বট ভেরিফাই করেনি।")

            msg = await context.bot.send_message(chat_id=user.id, text="✅ Report পাঠানো হয়েছে।", reply_markup=build_admin_menu())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return

    if flow == "broadcast_everyone":
        sent, failed = 0, 0
        for tg_id in list(VERIFIED_TG_USERS):
            try: await context.bot.send_message(chat_id=tg_id, text=text); sent += 1
            except: failed += 1
        msg = await update.message.reply_text(f"Everyone ব্রডকাস্ট সম্পন্ন। ✅\nসফল: {sent}, ব্যর্থ: {failed}", reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    if flow == "broadcast_selected_ids":
        codes = [line.strip() for line in text.splitlines() if line.strip()]
        context.user_data["broadcast_selected"] = {"codes": codes}
        context.user_data["flow"] = "broadcast_selected_message"
        msg = await context.bot.send_message(chat_id=user.id, text="কি জানাতে চান..⁉️", reply_markup=cancel_kb())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        return

    if flow == "broadcast_selected_message":
        codes = context.user_data.get("broadcast_selected", {}).get("codes", [])
        sent, failed, not_found, not_verified = 0, 0, [], []
        for c in codes:
            m = MEMBERS.get(c)
            if not m: not_found.append(c); continue
            if not m.get("tg_id"): not_verified.append(c); continue
            try: await context.bot.send_message(chat_id=m["tg_id"], text=text); sent += 1
            except: failed += 1
        reply = f"Selected Member ব্রডকাস্ট সম্পন্ন। ✅\nসফল: {sent}, ব্যর্থ: {failed}"
        if not_found: reply += f"\n\nকোড পাওয়া যায়নি: {', '.join(not_found)}"
        if not_verified: reply += f"\n\nভেরিফাই করা নেই: {', '.join(not_verified)}"
        msg = await update.message.reply_text(reply, reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
        return

    if flow == "members_add":
        step = context.user_data["members_add"].get("step", 0)
        if step == 1:
            context.user_data["members_add"]["name"] = text.strip()
            kb = [[InlineKeyboardButton(tname, callback_data=f"members_add_pickteam:{tname}")] for tname in TEAMS.keys()]
            kb.append([InlineKeyboardButton(LABEL["cancel"], callback_data="cancel")])
            msg = await update.message.reply_text("টিম নির্বাচন করুন।", reply_markup=InlineKeyboardMarkup(kb))
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data["members_add"]["step"] = 2
            return
        elif step == 3:
            code = text.strip()
            if code in MEMBERS:
                await update.message.reply_text("এই ইউজার কোড আগে থেকেই আছে।", reply_markup=cancel_kb())
                return
            MEMBERS[code] = {"code": code, "name": context.user_data["members_add"]["name"], "team": context.user_data["members_add"]["team"], "tg_id": None, "username": None}
            save_data()
            msg = await update.message.reply_text("✅ সদস্য যুক্ত হয়েছে।", reply_markup=build_members_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return

    if flow == "members_remove":
        code = text.strip()
        if code not in MEMBERS:
            await update.message.reply_text("ইউজার আইডিটি পাওয়া যায়নি।", reply_markup=build_members_kb())
            context.user_data.clear()
            return
        context.user_data["members_remove_code"] = code
        msg = await update.message.reply_text("আপনি কি নিশ্চিত..⁉️", reply_markup=yes_no_kb("members_remove"))
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
        context.user_data["flow"] = "members_remove_confirm_pending"
        return

    if flow == "team_add":
        step = context.user_data["team_add"].get("step", 0)
        if step == 1:
            tname = text.strip()
            if tname in TEAMS:
                await update.message.reply_text("এই নামে একটি টিম আছে।")
                return
            context.user_data["team_add"]["name"] = tname
            context.user_data["team_add"]["step"] = 2
            msg = await context.bot.send_message(chat_id=user.id, text="টিমের লিডারের ইউজারনেম দিন (@username ফরম্যাটে)।", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        elif step == 2:
            leader_username = text.strip()
            if leader_username.startswith("@"):
                TEAMS[context.user_data["team_add"]["name"]] = {"name": context.user_data["team_add"]["name"], "leader_code": None, "leader_tg_id": None, "leader_username": leader_username}
                save_data()
                msg = await update.message.reply_text("✅ টিম যুক্ত হয়েছে।", reply_markup=build_team_kb())
                store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
                context.user_data.clear()
            else: await update.message.reply_text("সঠিক ফরম্যাট দিন (যেমন @username)")
            return

    if flow == "admin_add":
        step = context.user_data["admin_add"].get("step", 0)
        if step == 1:
            context.user_data["admin_add"]["name"] = text.strip()
            context.user_data["admin_add"]["step"] = 2
            msg = await update.message.reply_text("অ্যাডমিন এর টেলিগ্রাম ইউজার নাম দিন (@username ফরম্যাটে)।", reply_markup=cancel_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            return
        elif step == 2:
            uname = text.strip()
            if not uname.startswith("@"):
                await update.message.reply_text("ইউজারনেম দিন (যেমন @username)")
                return
            PENDING_ADMINS.append({"id": None, "username": uname.lstrip("@"), "name": context.user_data["admin_add"]["name"], "is_default": False})
            save_data()
            try:
                chat = await context.bot.get_chat(uname)
                await context.bot.send_message(chat_id=chat.id, text="CPA Master এডমিন আমন্ত্রণ পাঠানো হয়েছে।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Accept", callback_data="accept_admin")]]))
            except: pass
            msg = await update.message.reply_text("✅ নতুন অ্যাডমিন পেন্ডিং হিসেবে যোগ হয়েছে।", reply_markup=build_admin_kb())
            store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)
            context.user_data.clear()
            return

    if flow == "user_verify":
        code = text.strip()
        if code not in MEMBERS:
            await update.message.reply_text("ভুল ইউজার আইডি। অ্যাডমিন থেকে সঠিক আইডি নিন।")
            return
        for tg_id, claimed_code in CLAIMS_BY_TG.items():
            if claimed_code == code and tg_id != user.id:
                await update.message.reply_text("এই ইউজার আইডি দিয়ে ইতিমধ্যে আরেকজন ভেরিফাইড।")
                context.user_data.clear()
                return
        MEMBERS[code].update({"tg_id": user.id, "username": user.username or MEMBERS[code].get("username")})
        VERIFIED_TG_USERS.add(user.id)
        CLAIMS_BY_TG[user.id] = code
        for pa in PENDING_ADMINS:
            if pa.get("username") and user.username and pa["username"].lstrip("@") == user.username:
                ensure_admin_entry_for_id(user.id, user.username, pa.get("name") or "Admin", default=False)
        PENDING_ADMINS[:] = [pa for pa in PENDING_ADMINS if not (user.username and pa.get("username", "").lstrip("@") == user.username)]
        save_data()
        await update.message.reply_text(f"{MEMBERS[code]['name']} Welcome to SM IT FORCE\n\nআমাদের গ্রুপে যুক্ত হও সবকিছুর আপডেট পেতে।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Group", url=GROUP_LINK)]]))
        context.user_data.clear()
        return

    if is_admin(user.id):
        msg = await update.message.reply_text("মেনু:", reply_markup=build_admin_menu())
        store_last_bot_message(context, user.id, msg.chat_id, msg.message_id)

async def on_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not is_admin(update.effective_user.id): return
    fwd_from = update.message.forward_from
    if not fwd_from: return
    
    flow = context.user_data.get("flow")
    if flow == "team_add" and context.user_data["team_add"].get("step") == 2:
        TEAMS[context.user_data["team_add"]["name"]] = {"name": context.user_data["team_add"]["name"], "leader_code": None, "leader_tg_id": fwd_from.id, "leader_username": f"@{fwd_from.username}" if fwd_from.username else ""}
        save_data()
        msg = await update.message.reply_text("✅ টিম যুক্ত হয়েছে।", reply_markup=build_team_kb())
        store_last_bot_message(context, update.effective_user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()
    elif flow == "admin_add" and context.user_data["admin_add"].get("step") == 2:
        ensure_admin_entry_for_id(fwd_from.id, fwd_from.username or "", context.user_data["admin_add"]["name"], default=False)
        msg = await update.message.reply_text("✅ নতুন অ্যাডমিন যুক্ত হয়েছে।", reply_markup=build_admin_kb())
        store_last_bot_message(context, update.effective_user.id, msg.chat_id, msg.message_id)
        context.user_data.clear()

def list_members_text() -> str:
    if not MEMBERS: return "কোনো সদস্য যুক্ত করা নেই।"
    return "\n\n".join([f"• নাম: {m['name']}\n   টিম: {m.get('team','—')}\n   টেলিগ্রাম: @{m.get('username') or '—'}\n   ইউজার কোড: {code}\n   TG ID: {m.get('tg_id') or '—'}" for code, m in MEMBERS.items()])

def list_teams_text() -> str:
    if not TEAMS: return "কোনো টিম নেই।"
    return "\n\n".join([f"• টিম: {tname}\n   লিডার: {t.get('leader_username') or t.get('leader_tg_id') or '—'}" for tname, t in TEAMS.items()])

def list_admins_text() -> str:
    if not ADMINS: return "কোনো অ্যাডমিন নেই।"
    return "\n\n".join([f"• {info.get('name')}{' (Default)' if info.get('is_default') else ''}\n   ইউজারনেম: @{info.get('username') or '—'}\n   ID: {aid}" for aid, info in ADMINS.items()])


# --- REGISTER HANDLERS TO APPLICATION ---
load_data()
ptb_application.add_handler(CommandHandler("start", start))
ptb_application.add_handler(CommandHandler("mainadmin", mainadmin))
ptb_application.add_handler(CallbackQueryHandler(callback_router))
ptb_application.add_handler(MessageHandler(filters.FORWARDED, on_forward))
ptb_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))


# ---------------- Flask App for Vercel ----------------
app = Flask(__name__)

@app.route("/api/webhook", methods=["POST"])
def telegram_webhook():
    """ এই এন্ডপয়েন্টটি টেলিগ্রাম থেকে রিকোয়েস্ট রিসিভ করবে """
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, ptb_application.bot)
        
        # Vercel-এ অ্যাসিনক্রোনাসলি রিকোয়েস্ট হ্যান্ডেল করার সঠিক উপায়
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ptb_application.process_update(update))
        loop.close()
        
        return "OK", 200
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return "Internal Error", 500

@app.route("/", methods=["GET"])
def home():
    return "CPA Master Bot is active on Vercel!"
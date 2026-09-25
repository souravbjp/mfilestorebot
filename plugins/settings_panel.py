from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.enums import ParseMode  
from config import Config
from utils.database import db
from script import Script

def get_settings_keyboard(settings):
    sl_status = "🟢 ON" if settings.get('shortlink_status') else "🔴 OFF"
    sl_type = "⏳ Time" if settings.get('shortlink_type') == 'time' else "💳 Credit"
    verify_time = settings.get('verify_duration', 24)
    bypass_cred = settings.get('bypass_credits', 3)
    bypass_time = settings.get('bypass_time', 15)
    guard_status = "🟢 ON" if settings.get('web_guard', False) else "🔴 OFF"
    protect_status = "🟢 ON" if settings.get('protect_content', False) else "🔴 OFF"
    
    keyboard = [
        [InlineKeyboardButton(Script.BTN_SL_STATUS.format(status=sl_status), callback_data="set_sl_status"),
         InlineKeyboardButton(Script.BTN_SL_MODE.format(mode=sl_type), callback_data="set_sl_type")]
    ]
    
    if settings.get('shortlink_type') == 'time':
        keyboard.append([InlineKeyboardButton(Script.BTN_SL_TIME.format(time=verify_time), callback_data="set_sl_time")])
    else:
        keyboard.append([InlineKeyboardButton(Script.BTN_SL_CREDIT.format(creds=bypass_cred), callback_data="set_sl_cred")])
        
    keyboard.append([InlineKeyboardButton(Script.BTN_BYPASS_TIME.format(time=bypass_time), callback_data="set_bypass_time")])
    keyboard.append([InlineKeyboardButton(Script.BTN_WEB_GUARD.format(status=guard_status), callback_data="set_web_guard")])
    keyboard.append([InlineKeyboardButton(Script.BTN_PROTECT_CONTENT.format(status=protect_status), callback_data="set_protect")])
    
    keyboard.append([InlineKeyboardButton(Script.BTN_PREMIUM_SETTINGS, callback_data="prem_settings_menu")])
        
    keyboard.append([InlineKeyboardButton(Script.BTN_CLOSE_PANEL, callback_data="close_settings")])
    return InlineKeyboardMarkup(keyboard)

@Client.on_message(filters.command("settings") & filters.private)
async def settings_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID:
        return # 🚀 SILENT IGNORE
        
    settings = await db.get_settings()
    await message.reply_text(Script.SETTINGS_MSG, reply_markup=get_settings_keyboard(settings))

@Client.on_callback_query(filters.regex(r"^set_sl_|^set_bypass_|^set_web_|^set_protect|^prem_settings_menu|^back_to_main_settings|^set_pay_help"))
async def settings_callbacks(client: Client, query: CallbackQuery):
    if query.from_user.id != Config.OWNER_ID:
        return await query.answer() # 🚀 SILENT IGNORE
        
    settings = await db.get_settings()
    action = query.data
    
    if action == "prem_settings_menu":
        kb = [[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_to_main_settings")]]
        
        # 🚀 FIX: Used strict HTML parsing to prevent EntityBoundsInvalid crashes
        text = (
            "💎 <b>ᴘʀᴇᴍɪᴜᴍ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ</b>\n\n"
            "<b>1. Button Links:</b>\n"
            "• <code>/set_owner_link https://t.me/xx</code>\n"
            "• <code>/set_group_link https://t.me/xx</code>\n\n"
            "<b>2. Global Free Limit:</b>\n"
            "• <code>/set_free_limit 5</code> <i>(0 to turn off)</i>\n\n"
            "<b>3. Manage Users:</b>\n"
            "• <code>/add_prem UserID Days Limit</code>\n"
            "• <code>/del_prem UserID</code>"
        )
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return await query.answer()
        
    elif action == "back_to_main_settings":
        await query.message.edit_text(Script.SETTINGS_MSG, reply_markup=get_settings_keyboard(settings))
        return await query.answer()
        
    elif action == "set_pay_help":
        return await query.answer("Type /set_pay followed by your Bkash/Nagad details in normal message to update!", show_alert=True)

    if action == "set_sl_status":
        new_status = not settings.get('shortlink_status', False)
        await db.update_settings('shortlink_status', new_status)
        
    elif action == "set_sl_type":
        current_type = settings.get('shortlink_type', 'time')
        new_type = 'credit' if current_type == 'time' else 'time'
        await db.update_settings('shortlink_type', new_type)
        
    elif action == "set_sl_time":
        times = [1, 4, 8, 16, 24]
        current = settings.get('verify_duration', 24)
        next_idx = (times.index(current) + 1) % len(times) if current in times else 0
        await db.update_settings('verify_duration', times[next_idx])
        
    elif action == "set_sl_cred":
        # 🚀 FIX: 0 যুক্ত করা হয়েছে যাতে প্রতি ক্লিকে ভেরিফাই করানো যায়
        creds = [0, 1, 2, 3, 5, 10, 20]
        current = settings.get('bypass_credits', 3)
        next_idx = (creds.index(current) + 1) % len(creds) if current in creds else 0
        await db.update_settings('bypass_credits', creds[next_idx])
        
    elif action == "set_bypass_time":
        times = [0, 5, 10, 15, 20, 30, 45, 60]
        current = settings.get('bypass_time', 15)
        next_idx = (times.index(current) + 1) % len(times) if current in times else 0
        await db.update_settings('bypass_time', times[next_idx])
        
    elif action == "set_web_guard":
        new_status = not settings.get('web_guard', False)
        await db.update_settings('web_guard', new_status)
        
    elif action == "set_protect":
        new_status = not settings.get('protect_content', False)
        await db.update_settings('protect_content', new_status)
        
    updated_settings = await db.get_settings()
    await query.message.edit_reply_markup(get_settings_keyboard(updated_settings))
    await query.answer(Script.SETTINGS_UPDATED_ALERT)

@Client.on_callback_query(filters.regex("close_settings"))
async def close_settings(client: Client, query: CallbackQuery):
    if query.from_user.id != Config.OWNER_ID:
        return await query.answer() # 🚀 SILENT IGNORE
    await query.message.delete()

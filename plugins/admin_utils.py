import os
import time
import asyncio
import base64
import re
import json
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import Config
from utils.database import db
from script import Script

bot_start_time = time.time()

def get_ram_usage():
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        total_mem = free_mem = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                total_mem = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                free_mem = int(line.split()[1]) * 1024
        if total_mem > 0:
            used_mem = total_mem - free_mem
            return used_mem, total_mem
    except Exception:
        pass
    return 0, 0

def format_size(size_in_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return "0 B"

@Client.on_message(filters.command("status") & filters.private)
async def bot_status_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
    
    wait_msg = await message.reply_text("⏳ **Fetching Server & DB Status...**")
    
    used_ram, total_ram = get_ram_usage()
    ram_text = f"{format_size(used_ram)} / {format_size(total_ram)}" if total_ram > 0 else "Unknown"
    
    db_stats = await db.get_db_stats()
    db_text = ""
    for i in range(1, 4):
        db_key = f"db{i}"
        if db_key in db_stats:
            used_mb = db_stats[db_key]['dataSize'] / (1024 * 1024)
            free_mb = 512.0 - used_mb
            db_text += f"🗄 **DB{i}:** `{used_mb:.2f} MB Used` (Free: `{free_mb:.2f} MB`)\n"
    
    if not db_text:
        db_text = "No Database Connected!"
        
    text = f"🖥 **Server RAM Usage:**\n`{ram_text}`\n\n📊 **Database Storage (MongoDB Free Tier 512MB):**\n{db_text}\n*(Note: You can store ~1.5M to 2M files in 512MB)*"
    await wait_msg.edit_text(text)

@Client.on_message(filters.command("delete") & filters.private)
async def delete_file_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
    
    if len(message.command) < 2:
        return await message.reply_text("❌ **সঠিক নিয়ম:** `/delete link1, link2` অথবা `/delete id1 id2`")
    
    input_text = message.text.split(None, 1)[1]
    input_text = input_text.replace(",", " ").replace("\n", " ")
    items = [item.strip() for item in input_text.split() if item.strip()]
    
    if not items:
        return await message.reply_text("❌ **কোনো আইডি বা লিংক পাওয়া যায়নি!**")
        
    wait_msg = await message.reply_text(f"⏳ **Deleting {len(items)} items...**")
    
    success = 0
    failed = 0
    
    for item in items:
        unique_id = item.split("start=")[-1] if "start=" in item else item
        deleted = await db.delete_file(unique_id)
        if deleted:
            success += 1
        else:
            failed += 1
            
    text = f"🗑 **ডিলিট প্রসেস সম্পন্ন!**\n\n✅ **সফলভাবে ডিলিট হয়েছে:** `{success}`\n❌ **পাওয়া যায়নি/ফেইল:** `{failed}`"
    await wait_msg.edit_text(text)

@Client.on_message(filters.command("stats") & filters.private)
async def bot_statistics(client: Client, message: Message):
    if not await db.is_admin(message.from_user.id): 
        return # 🚀 SILENT IGNORE
        
    wait_msg = await message.reply_text(Script.FETCHING_STATS)
    total_users = await db.total_users()
    total_files = await db.total_files()
    total_banned = await db.total_banned_users()
    
    uptime_seconds = int(time.time() - bot_start_time)
    uptime = str(timedelta(seconds=uptime_seconds))
    multi_db_status = "Active 🟢" if Config.MONGO_URI_2 else "Inactive 🔴"
    
    settings = await db.get_settings()
    sl_status = "ON" if settings.get('shortlink_status') else "OFF"
    sl_type = settings.get('shortlink_type', 'time').capitalize()
    
    guard_status = "🟢 ON" if settings.get('web_guard', False) else "🔴 OFF"
    
    text = Script.STATS_MSG.format(
        uptime=uptime, total_users=total_users, total_banned=total_banned,
        total_files=total_files, multi_db_status=multi_db_status,
        sl_status=sl_status, sl_type=sl_type, guard_status=guard_status
    )
    await wait_msg.edit_text(text)

async def delete_broadcast_after_delay(client, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass

async def send_msg(user_id, b_msg, mins, client, is_dbroadcast):
    try:
        sent_m = await b_msg.copy(chat_id=user_id)
        if is_dbroadcast:
            asyncio.create_task(delete_broadcast_after_delay(client, user_id, sent_m.id, mins * 60))
        return 200
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        sent_m = await b_msg.copy(chat_id=user_id)
        if is_dbroadcast:
            asyncio.create_task(delete_broadcast_after_delay(client, user_id, sent_m.id, mins * 60))
        return 200
    except Exception:
        return 400

@Client.on_message(filters.command("dbroadcast") & filters.private)
async def dbroadcast_message(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID:
        return # 🚀 SILENT IGNORE
        
    if len(message.command) < 2 or not message.reply_to_message:
        return await message.reply_text(Script.REPLY_DBROADCAST)
        
    try:
        mins = int(message.command[1])
    except ValueError:
        return await message.reply_text(Script.MINUTES_NUMBER_ERROR)
        
    wait_msg = await message.reply_text(Script.DBROADCAST_START.format(mins=mins))
    b_msg = message.reply_to_message
    
    users_cursor = await db.get_all_users()
    users_list = await users_cursor.to_list(length=None)
    
    sent = 0
    failed = 0
    
    for i in range(0, len(users_list), 50):
        batch = users_list[i:i+50]
        tasks = [send_msg(user['_id'], b_msg, mins, client, True) for user in batch]
        # 🚀 FIX: return_exceptions=True prevents one blocked user from crashing the whole broadcast loop
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sent += results.count(200)
        failed += results.count(400)
        await asyncio.sleep(1) 
            
    await wait_msg.edit_text(Script.DBROADCAST_DONE.format(sent=sent, failed=failed, mins=mins))

@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_message(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    if not message.reply_to_message:
        return await message.reply_text(Script.REPLY_BROADCAST)
        
    wait_msg = await message.reply_text(Script.BROADCAST_START)
    b_msg = message.reply_to_message
    
    users_cursor = await db.get_all_users()
    users_list = await users_cursor.to_list(length=None)
    
    sent = 0
    failed = 0
    
    for i in range(0, len(users_list), 50):
        batch = users_list[i:i+50]
        tasks = [send_msg(user['_id'], b_msg, 0, client, False) for user in batch]
        # 🚀 FIX: return_exceptions=True prevents one blocked user from crashing the whole broadcast loop
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sent += results.count(200)
        failed += results.count(400)
        await asyncio.sleep(1)
            
    await wait_msg.edit_text(Script.BROADCAST_DONE.format(sent=sent, failed=failed))

@Client.on_message(filters.command("ban") & filters.private)
async def ban_user_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    if len(message.command) < 2:
        return await message.reply_text(Script.BAN_USAGE)
    try:
        user_id = int(message.command[1])
        if user_id == Config.OWNER_ID:
            return await message.reply_text(Script.BAN_SELF)
        await db.ban_user(user_id)
        await message.reply_text(Script.BAN_SUCCESS.format(user_id=user_id))
    except ValueError:
        await message.reply_text(Script.ID_NUMBER_ERROR)

@Client.on_message(filters.command("unban") & filters.private)
async def unban_user_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    if len(message.command) < 2:
        return await message.reply_text(Script.UNBAN_USAGE)
    try:
        user_id = int(message.command[1])
        await db.unban_user(user_id)
        await message.reply_text(Script.UNBAN_SUCCESS.format(user_id=user_id))
    except ValueError:
        await message.reply_text(Script.ID_NUMBER_ERROR)

@Client.on_message(filters.command("unban_all") & filters.private)
async def unban_all_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    count = await db.unban_all_users()
    await message.reply_text(Script.UNBAN_ALL_SUCCESS.format(count=count))

@Client.on_message(filters.command("add_credit") & filters.private)
async def manual_add_credit(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    if len(message.command) < 3:
        return await message.reply_text(Script.ADD_CREDIT_USAGE)
    try:
        user_id = int(message.command[1])
        amount = int(message.command[2])
        await db.add_credits(user_id, amount)
        await message.reply_text(Script.ADD_CREDIT_SUCCESS.format(amount=amount, user_id=user_id))
    except ValueError:
        await message.reply_text(Script.ID_AMOUNT_ERROR)

@Client.on_message(filters.command("set_shortlink") & filters.private)
async def set_shortlink_api(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    if len(message.command) < 3:
        return await message.reply_text(Script.SET_SL_USAGE)
        
    url = message.command[1].strip("<>[]()\"' ")
    api = message.command[2].strip("<>[]()\"' ")
    
    await db.update_settings('shortener_url', url)
    await db.update_settings('shortener_api', api)
    await message.reply_text(Script.SET_SL_SUCCESS.format(url=url, api=api))

@Client.on_message(filters.command("set_tutorial") & filters.private)
async def set_tutorial_link(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    if len(message.command) < 2:
        return await message.reply_text(Script.SET_TUTORIAL_USAGE)
        
    link = message.command[1].strip("<>[]()\"' ")
    
    if link.lower() == "off":
        await db.update_settings('tutorial_link', "")
        await message.reply_text(Script.TUTORIAL_REMOVED)
    else:
        await db.update_settings('tutorial_link', link)
        await message.reply_text(Script.TUTORIAL_SUCCESS.format(link=link))

@Client.on_message(filters.command("remove_credit") & filters.private)
async def manual_remove_credit(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    if len(message.command) < 3:
        return await message.reply_text(Script.REMOVE_CREDIT_USAGE)
    try:
        user_id = int(message.command[1])
        amount = int(message.command[2])
        await db.add_credits(user_id, -amount)
        await message.reply_text(Script.REMOVE_CREDIT_SUCCESS.format(amount=amount, user_id=user_id))
    except ValueError:
        await message.reply_text(Script.ID_AMOUNT_ERROR)

# ================= 🚀 TRUE PERMANENT INDEXER (NO CHANNEL NEEDED) =================
OLD_DB_CHANNEL = -1002266490060

def get_file_info(message):
    try:
        media = message.document or message.video or message.audio or message.photo or message.animation or message.sticker or message.voice
        if media:
            f_id = media.file_id if not isinstance(media, list) else media[-1].file_id
            cap = message.caption.html if message.caption else ""
            return f_id, cap
    except Exception: pass
    text_content = message.text.html if message.text else ""
    return None, text_content

@Client.on_message(filters.command("index_links") & filters.private)
async def index_links_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    target_msg = message.reply_to_message
    if not target_msg:
        return await message.reply_text("❌ **সঠিক নিয়ম:** যেসব পুরনো লিংক সেভ করতে চান, সেই মেসেজে রিপ্লাই করে `/index_links` দিন।")
        
    text = target_msg.text or target_msg.caption
    if not text:
        return await message.reply_text("❌ **মেসেজে কোনো টেক্সট বা লিংক নেই!**")
        
    links = re.findall(r'start=([A-Za-z0-9-_=]+)', text)
    if not links:
        return await message.reply_text("❌ **এই মেসেজে কোনো লিংক পাওয়া যায়নি!**")
        
    wait_msg = await message.reply_text(f"⏳ **{len(links)} টি লিংক পাওয়া গেছে! Permanent Indexing শুরু হচ্ছে...**\n*(সব ফাইলের গ্লোবাল file_id স্ক্যান করে আপডেট করা হচ্ছে)*")
    
    success = 0
    db_abs = abs(OLD_DB_CHANNEL)
    
    for payload in links:
        try:
            padding = "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload + padding).decode('utf-8')
            parts = decoded.split("-")
            
            # 🚀 Single File 
            if len(parts) == 2 or len(parts) == 4:
                msg_id = int(int(parts[1] if len(parts) == 2 else parts[3]) / db_abs)
                try:
                    db_msg = await client.get_messages(OLD_DB_CHANNEL, msg_id)
                    f_id, cap = get_file_info(db_msg)
                    
                    new_doc = {'t': 's', 'm': msg_id} # Channel ID ('c') ইচ্ছাকৃতভাবে বাদ দেওয়া হয়েছে
                    if f_id: new_doc['f'] = f_id
                    if cap: new_doc['cap'] = cap
                    
                    # ⚠️ FORCE UPDATE: আগের ব্রোকেন ডাটা রিপ্লেস করে দেবে
                    await db.files_col1.update_one({'_id': payload}, {'$set': new_doc}, upsert=True)
                    success += 1
                except Exception:
                    pass
                    
            # 🚀 Batch File (The Main Fix!)
            elif len(parts) == 3 or len(parts) == 5:
                f_msg_id = int(int(parts[1] if len(parts) == 3 else parts[3]) / db_abs)
                l_msg_id = int(int(parts[2] if len(parts) == 3 else parts[4]) / db_abs)
                batch_files = []
                
                for msg_id in range(f_msg_id, l_msg_id + 1):
                    try:
                        db_msg = await client.get_messages(OLD_DB_CHANNEL, msg_id)
                        if db_msg and not getattr(db_msg, "empty", True):
                            f_id, cap = get_file_info(db_msg)
                            f_data = {}
                            if f_id: f_data['f'] = f_id
                            if cap: f_data['cap'] = cap
                            if f_data: batch_files.append(f_data)
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 1)
                        db_msg = await client.get_messages(OLD_DB_CHANNEL, msg_id)
                        if db_msg and not getattr(db_msg, "empty", True):
                            f_id, cap = get_file_info(db_msg)
                            f_data = {}
                            if f_id: f_data['f'] = f_id
                            if cap: f_data['cap'] = cap
                            if f_data: batch_files.append(f_data)
                    except Exception: pass
                    await asyncio.sleep(0.5)
                    
                if batch_files:
                    # ⚠️ FORCE UPDATE: আগের f_id, l_id সিস্টেম বাদ দিয়ে সরাসরি files array সেভ করবে
                    await db.files_col1.update_one({'_id': payload}, {'$set': {'t': 'b', 'files': batch_files}}, upsert=True)
                    success += 1
                    
        except Exception:
            pass
            
    await wait_msg.edit_text(f"✅ **Permanent Indexing Completed!**\n\n🔗 **Total Links Scanned:** `{len(links)}`\n💾 **Successfully Updated:** `{success}`\n\n🎉 এখন সব ফাইলের `file_id` ডাটাবেসে সেভ হয়ে গেছে। আপনি চ্যানেল ডিলিট করলেও সব ফাইল আজীবন কাজ করবে!")

# ================= 🚀 TECH_VJ OLD LINK MIGRATOR =================
@Client.on_message(filters.command("vj_index") & filters.private)
async def vj_index_links_command(client: Client, message: Message):
    if message.from_user.id != Config.OWNER_ID: 
        return # 🚀 SILENT IGNORE
        
    target_msg = message.reply_to_message
    if not target_msg:
        return await message.reply_text("❌ **সঠিক নিয়ম:** যেসব পুরনো Tech_VJ লিংক সেভ করতে চান, সেই মেসেজে রিপ্লাই করে `/vj_index` দিন।")
        
    text = target_msg.text or target_msg.caption
    if not text:
        return await message.reply_text("❌ **মেসেজে কোনো টেক্সট বা লিংক নেই!**")
        
    # Tech_VJ লিংকের প্যাটার্ন খোঁজা 
    links = re.findall(r'start=([A-Za-z0-9-_=]+)', text)
    if not links:
        return await message.reply_text("❌ **এই মেসেজে কোনো Tech_VJ লিংক পাওয়া যায়নি!**")
        
    wait_msg = await message.reply_text(f"⏳ **{len(links)} টি Tech_VJ লিংক পাওয়া গেছে! Migration শুরু হচ্ছে...**")
    
    success = 0
    failed = 0
    
    for payload in links:
        try:
            # Batch Link Migration
            if payload.startswith("BATCH-"):
                file_id = payload.split("-", 1)[1]
                file_path = await client.download_media(file_id)
                with open(file_path, "r") as file_data:
                    msgs = json.loads(file_data.read())
                os.remove(file_path)
                
                batch_files = []
                for msg in msgs:
                    f_data = {}
                    if "file_id" in msg:
                        f_data['f'] = msg["file_id"]
                    if "caption" in msg and msg["caption"]:
                        f_data['cap'] = msg["caption"]
                    elif "title" in msg and msg["title"]:
                        f_data['cap'] = f"<code>{msg['title']}</code>"
                    
                    if f_data:
                        batch_files.append(f_data)
                        
                if batch_files:
                    # নতুন ডাটাবেসে সেভ (পুরনো পেলোডকেই আইডি হিসেবে রেখে)
                    await db.files_col1.update_one(
                        {'_id': payload}, 
                        {'$set': {'t': 'b', 'files': batch_files}}, 
                        upsert=True
                    )
                    success += 1
                    
            # Single Link Migration
            else:
                decoded = (base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).decode("ascii")
                pre, f_id = decoded.split("_", 1)
                
                new_doc = {'t': 's', 'f': f_id}
                await db.files_col1.update_one(
                    {'_id': payload}, 
                    {'$set': new_doc}, 
                    upsert=True
                )
                success += 1
        except Exception:
            failed += 1
            
    await wait_msg.edit_text(f"✅ **Tech_VJ Migration Completed!**\n\n🔗 **Total Links:** `{len(links)}`\n💾 **Success:** `{success}`\n❌ **Failed:** `{failed}`\n\n🎉 আপনার পুরনো লিংকগুলো এখন নতুন ডাটাবেসে পুরোপুরি সেভ হয়ে গেছে!")

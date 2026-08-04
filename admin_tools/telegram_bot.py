#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
admin_tools/telegram_bot.py
──────────────────────────────────────────────────────────────────────────────
Bot Telegram quản trị Admin - Tự động cấp và quản lý License Key trên Supabase.
Tác giả: Nguyễn Văn Lực (AUDIO FACTORY PREMIUM SUITE)
"""

import sys
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Thêm thư mục gốc của dự án vào sys.path để có thể import core.security
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Thử import cấu hình Supabase từ core.security, fallback nếu chạy độc lập hoàn toàn
SUPABASE_URL = os.environ.get("AUDIO_FACTORY_SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("AUDIO_FACTORY_SUPABASE_SERVICE_ROLE_KEY", "")

# Thư viện telebot (pyTelegramBotAPI)
try:
    import telebot
except ImportError:
    print("Error: Thư viện 'pyTelegramBotAPI' chưa được cài đặt. Vui lòng chạy: pip install pyTelegramBotAPI")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# CẤU HÌNH BẢO MẬT BỌC THÉP (CỦA ADMIN)
# ──────────────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("AUDIO_FACTORY_TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("AUDIO_FACTORY_TELEGRAM_ADMIN_ID", "0"))
ADMIN_NICKNAME = "lucnguyen_admin"  # Nickname Telegram để Khách liên hệ mua key

# Khởi tạo bot
if not all((SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN, ADMIN_ID)):
    raise RuntimeError(
        "Missing AUDIO_FACTORY_SUPABASE_URL, "
        "AUDIO_FACTORY_SUPABASE_SERVICE_ROLE_KEY, "
        "AUDIO_FACTORY_TELEGRAM_BOT_TOKEN or AUDIO_FACTORY_TELEGRAM_ADMIN_ID."
    )
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# ──────────────────────────────────────────────────────────────────────────────
# CÁC HÀM TƯƠNG TÁC SUPABASE REST API (POSTGREST)
# ──────────────────────────────────────────────────────────────────────────────
def supabase_request(endpoint: str, method: str = "GET", payload: dict = None, return_representation: bool = False) -> list:
    """
    Thực hiện cuộc gọi API HTTP trực tiếp tới Supabase PostgREST
    """
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    if return_representation:
        headers["Prefer"] = "return=representation"
        
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    with urllib.request.urlopen(req, timeout=10) as response:
        resp_data = response.read().decode("utf-8")
        if resp_data:
            return json.loads(resp_data)
        return []

# ──────────────────────────────────────────────────────────────────────────────
# GIAO DIỆN TIN NHẮN DÀNH CHO KHÁCH (GUEST)
# ──────────────────────────────────────────────────────────────────────────────
def send_guest_message(message):
    """
    Trả về tin nhắn quảng cáo giới thiệu khi tài khoản không phải là Admin chat với Bot.
    """
    guest_text = (
        "👋 Chào mừng bạn đến với Hệ thống bản quyền Audio Factory Premium Suite!\n"
        "💻 Đây là phần mềm xử lý âm thanh tự động chuyên nghiệp dành cho các nhà sáng tạo nội dung YouTube/TikTok.\n"
        f"🛒 Để mua License Key kích hoạt phần mềm, vui lòng liên hệ trực tiếp với Admin qua Telegram: @{ADMIN_NICKNAME}"
    )
    bot.reply_to(message, guest_text)

# ──────────────────────────────────────────────────────────────────────────────
# LỆNH ĐIỀU HƯỚNG BẢO MẬT & PHÂN QUYỀN ADMIN
# ──────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start', 'help'])
def cmd_start_help(message):
    # Kiểm tra vân tay ID Admin nghiêm ngặt
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    help_text = (
        "👑 **CHÀO MỪNG ADMIN ĐẾN VỚI HỆ THỐNG QUẢN TRỊ AUDIO FACTORY!**\n\n"
        "Các lệnh khả dụng hỗ trợ quản lý cấp Key:\n\n"
        "1️⃣ **Tạo License Key mới:**\n"
        "• `/gen` hoặc `/genkey`: Tạo Key Vĩnh Viễn (Lifetime), giới hạn 1 thiết bị.\n"
        "• `/gen <days>` hoặc `/genkey <days>`: Tạo Key thời hạn `days` ngày, 1 thiết bị. (Ví dụ: `/gen 30`)\n"
        "• `/gen <days> <max_devices>` hoặc `/genkey <days> <max_devices>`: Tạo Key thời hạn `days` ngày và `max_devices` thiết bị. (Ví dụ: `/gen 365 3`)\n\n"
        "2️⃣ **Quản lý trạng thái License Key:**\n"
        "• `/status <key>`: Tra cứu thông tin chi tiết của License Key.\n"
        "• `/reset <key>`: Reset mã máy HWID (giúp khách hàng đổi máy mới).\n"
        "• `/revoke <key>`: Khóa/Tạm dừng License Key (Đặt `is_active = false`).\n"
        "• `/activate <key>`: Mở khóa/Kích hoạt lại License Key (Đặt `is_active = true`).\n"
        "• `/delete <key>`: Xóa hoàn toàn License Key khỏi cơ sở dữ liệu.\n\n"
        "3️⃣ **Xem danh sách Key:**\n"
        "• `/list`: Hiển thị danh sách 10 License Key mới nhất trên Supabase."
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['gen', 'genkey'])
def cmd_gen(message):
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    parts = message.text.split()
    days = None
    max_devices = 1
    
    # Phân tích tham số
    if len(parts) > 1:
        try:
            val = parts[1].strip()
            if val.lower() not in ["0", "lifetime", "vinhvien"]:
                days = int(val)
        except ValueError:
            bot.reply_to(message, "⚠️ Tham số số ngày dùng `days` phải là một số nguyên hợp lệ.")
            return
            
    if len(parts) > 2:
        try:
            max_devices = int(parts[2].strip())
        except ValueError:
            bot.reply_to(message, "⚠️ Tham số số thiết bị `max_devices` phải là một số nguyên hợp lệ.")
            return

    try:
        # Xây dựng payload để gọi Supabase
        payload = {
            "max_devices": max_devices,
            "is_active": True
        }
        
        expired_str = "Vĩnh viễn (Lifetime)"
        if days is not None and days > 0:
            # Tính toán thời gian hết hạn theo múi giờ UTC
            expired_dt = datetime.now(timezone.utc) + timedelta(days=days)
            payload["expired_at"] = expired_dt.isoformat()
            # Hiển thị hạn dùng trực quan hơn cho admin
            expired_str = expired_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            payload["expired_at"] = None

        # Gửi POST để tạo mới License Key
        # Do database có Default Value cho license_key nên Supabase sẽ tự động sinh và trả về bản ghi qua Prefer: return=representation
        res = supabase_request("audio_licenses", method="POST", payload=payload, return_representation=True)
        
        if not res:
            bot.reply_to(message, "❌ Không nhận được phản hồi từ cơ sở dữ liệu Supabase khi tạo Key.")
            return
            
        created_info = res[0]
        created_key = created_info.get("license_key")
        
        success_msg = (
            "🔑 **ĐÃ TẠO LICENSE KEY THÀNH CÔNG!**\n\n"
            f"• **Key:** `{created_key}`\n"
            f"• **Số thiết bị tối đa:** `{max_devices}`\n"
            f"• **Hạn dùng:** `{expired_str}`\n\n"
            "Hãy copy đoạn mã trên để gửi cho khách hàng kích hoạt phần mềm."
        )
        bot.reply_to(message, success_msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi trong quá trình tạo License Key: {e}")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Hướng dẫn: Gõ `/status <license_key>` để tra cứu.")
        return
        
    key = parts[1].strip()
    encoded_key = urllib.parse.quote(key)
    
    try:
        res = supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="GET")
        if not res:
            bot.reply_to(message, f"❌ Không tìm thấy License Key `{key}` trên hệ thống.")
            return
            
        info = res[0]
        hwids_val = info.get("device_hwids") or info.get("devices") or info.get("hwid")
        hwid_str = f"`{hwids_val}`" if hwids_val else "_Chưa kích hoạt (Sẵn sàng gắn máy)_"
        is_active = info.get("is_active", True)
        status_str = "🟢 Hoạt động" if is_active else "🔴 Đang bị khóa"
        max_devices = info.get("max_devices", 1)
        expired_at_val = info.get("expired_at")
        
        expired_str = "Vĩnh viễn (Lifetime)"
        if expired_at_val:
            try:
                # Chuẩn hóa để parse hiển thị đẹp
                normalized = str(expired_at_val).replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
                expired_str = dt.strftime("%Y-%m-%d %H:%M:%S") + " UTC"
            except Exception:
                expired_str = str(expired_at_val)
                
        info_msg = (
            "ℹ️ **THÔNG TIN LICENSE KEY**\n\n"
            f"• **Key:** `{info.get('license_key')}`\n"
            f"• **Tên khách:** `{info.get('customer_name', 'Chưa đặt')}`\n"
            f"• **Trạng thái:** {status_str}\n"
            f"• **Số thiết bị tối đa:** `{max_devices}`\n"
            f"• **Mã máy HWID:** {hwid_str}\n"
            f"• **Hạn dùng:** `{expired_str}`\n"
            f"• **Mã ID:** `{info.get('id')}`"
        )
        bot.reply_to(message, info_msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi truy vấn thông tin Key: {e}")

@bot.message_handler(commands=['reset'])
def cmd_reset(message):
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Hướng dẫn: Gõ `/reset <license_key>` để reset HWID.")
        return
        
    key = parts[1].strip()
    encoded_key = urllib.parse.quote(key)
    
    try:
        res = supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="GET")
        if not res:
            bot.reply_to(message, f"❌ Không tìm thấy License Key `{key}`.")
            return
            
        # Thực hiện cập nhật device_hwids về mảng rỗng
        payload = {
            "device_hwids": []
        }
        supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="PATCH", payload=payload)
        
        bot.reply_to(message, f"✅ Đã reset mã máy HWID của Key `{key}` thành công. Khách hàng có thể kích hoạt lại trên máy tính mới.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi reset HWID: {e}")

@bot.message_handler(commands=['revoke'])
def cmd_revoke(message):
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Hướng dẫn: Gõ `/revoke <license_key>` để khóa Key.")
        return
        
    key = parts[1].strip()
    encoded_key = urllib.parse.quote(key)
    
    try:
        res = supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="GET")
        if not res:
            bot.reply_to(message, f"❌ Không tìm thấy License Key `{key}`.")
            return
            
        payload = {"is_active": False}
        supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="PATCH", payload=payload)
        
        bot.reply_to(message, f"🔒 Đã khóa/vô hiệu hóa thành công License Key `{key}`.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi vô hiệu hóa Key: {e}")

@bot.message_handler(commands=['activate'])
def cmd_activate(message):
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Hướng dẫn: Gõ `/activate <license_key>` để mở khóa Key.")
        return
        
    key = parts[1].strip()
    encoded_key = urllib.parse.quote(key)
    
    try:
        res = supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="GET")
        if not res:
            bot.reply_to(message, f"❌ Không tìm thấy License Key `{key}`.")
            return
            
        payload = {"is_active": True}
        supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="PATCH", payload=payload)
        
        bot.reply_to(message, f"🔓 Đã kích hoạt hoạt động lại thành công cho License Key `{key}`.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi kích hoạt lại Key: {e}")

@bot.message_handler(commands=['delete'])
def cmd_delete(message):
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Hướng dẫn: Gõ `/delete <license_key>` để xóa Key.")
        return
        
    key = parts[1].strip()
    encoded_key = urllib.parse.quote(key)
    
    try:
        res = supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="GET")
        if not res:
            bot.reply_to(message, f"❌ Không tìm thấy License Key `{key}`.")
            return
            
        # Thực hiện xóa vĩnh viễn khỏi Database
        supabase_request(f"audio_licenses?license_key=eq.{encoded_key}", method="DELETE")
        
        bot.reply_to(message, f"🗑️ Đã xóa hoàn toàn License Key `{key}` ra khỏi cơ sở dữ liệu.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi xóa Key: {e}")

@bot.message_handler(commands=['list'])
def cmd_list(message):
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    try:
        # Lấy tối đa 100 dòng để sort trong python lấy 10 key mới nhất 
        res = supabase_request("audio_licenses", method="GET")
        
        if not res:
            bot.reply_to(message, "📭 Cơ sở dữ liệu License hiện tại đang trống.")
            return
            
        # Sắp xếp theo ID/Thời gian tạo
        def get_sort_key(item):
            return item.get("created_at") or item.get("id") or ""
            
        sorted_list = sorted(res, key=get_sort_key, reverse=True)[:10]
        
        lines = []
        for i, item in enumerate(sorted_list):
            k = item.get("license_key")
            is_active = item.get("is_active", True)
            status_emoji = "🟢" if is_active else "🔴"
            hwid = item.get("hwid")
            hwid_status = "🔗" if hwid else "🆓"
            expired_at = item.get("expired_at")
            expired_type = "Vĩnh viễn" if not expired_at else "Hạn định"
            
            lines.append(f"{i+1}. {status_emoji} `{k}` ({expired_type}) {hwid_status}")
            
        list_text = (
            "📋 **DANH SÁCH 10 KEY MỚI NHẤT:**\n\n"
            + "\n".join(lines) + "\n\n"
            "*(Chú thích: 🟢 = Active, 🔴 = Locked | 🔗 = Đã gắn HWID, 🆓 = HWID Trống)*"
        )
        bot.reply_to(message, list_text, parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi lấy danh sách Key: {e}")

@bot.message_handler(func=lambda message: True)
def handle_all_other_messages(message):
    """
    Chặn và xử lý tất cả tin nhắn chat thông thường không phải lệnh
    """
    if message.from_user.id != ADMIN_ID:
        send_guest_message(message)
        return
        
    # Phản hồi cho Admin nếu gõ tin nhắn tự do không thuộc cấu trúc lệnh
    bot.reply_to(message, "⚠️ Lệnh hoặc tin nhắn không hợp lệ. Vui lòng gõ `/help` để xem danh sách lệnh quản trị.")

# ──────────────────────────────────────────────────────────────────────────────
# CHẠY BOT VÒNG LẶP VÔ HẠN
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("AUDIO FACTORY LICENSE TELEGRAM BOT IS RUNNING...")
    print(f"Admin ID cấu hình: {ADMIN_ID}")
    print(f"Nickname liên hệ: @{ADMIN_NICKNAME}")
    print("=" * 60)
    
    # Bắt đầu vòng lặp thăm dò tin nhắn (polling)
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\nBot đã được dừng bởi người dùng.")
        sys.exit(0)

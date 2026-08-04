#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
core/localization.py
──────────────────────────────────────────────────────────────────────────────
Từ điển ngôn ngữ và các chuỗi hiển thị giao diện (Bản quyền Audio Factory).
Hỗ trợ chuyển đổi ngôn ngữ động: Tiếng Việt (vi) & Tiếng Anh (en).
"""

from typing import Dict, Any

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "vi": {
        "window_title": "Audio Factory",
        "tab_silence": "Cắt Khoảng Lặng",
        "btn_start": "▶  Bắt đầu xử lý",
        "btn_start_processing": "⏳  Đang xử lý...",
        "btn_cancel": "■  Hủy bỏ",
        "btn_cancel_processing": "⏳  Đang hủy...",
        "lbl_threshold": "Ngưỡng âm lượng (dB):",
        "lbl_duration": "Thời gian im lặng (s):",
        "msg_success": "🎉 Xử lý âm thanh thành công!",
        "msg_license_error": "❌ Mã Key bản quyền không hợp lệ hoặc đã hết hạn!",
        
        "header_subtitle": "Được phát triển bởi Lực Nguyễn",
        "footer": "Powered by FFmpeg + Whisper Local + Lực Nguyễn",
        "panel_input": "Đầu Vào",
        "panel_output": "Đầu Ra",
        "panel_processing": "Cấu Hình Xử Lý",
        "panel_subtitles": "Cấu Hình Phụ Đề",
        "panel_log": "Nhật ký xử lý",
        "panel_progress": "Tiến trình",
        
        # Input buttons / labels
        "btn_add_files": "＋  Thêm tệp",
        "btn_remove_selected": "🗑  Xóa tất cả",
        "btn_move_up": "↑  Lên",
        "btn_move_down": "↓  Xuống",
        "lbl_sum_count": "📁  Tổng số: {count} tệp",
        "lbl_sum_duration": "⏱  Tổng thời lượng: {duration}",
        "lbl_sum_size": "💾  Tổng kích thước: {size}",
        "lbl_summary": "💡 *Kéo thả tệp âm thanh/video vào bảng trên để bắt đầu nhập*",
        
        # Table Headers
        "table_header_stt": "STT",
        "table_header_name": "Tên tệp",
        "table_header_duration": "Thời lượng",
        "table_header_size": "Kích thước",
        "table_header_action": "✕",
        
        # Output section
        "lbl_out_dir": "Thư mục đầu ra:",
        "placeholder_out_dir": "Chọn thư mục lưu kết quả...",
        "btn_browse_output": "📁  Chọn thư mục",
        "lbl_project_name": "Tên dự án:",
        "lbl_output_format": "Định dạng xuất:",
        
        # Feature cards
        "card_merge": "Gộp Audio",
        "card_voice": "Lọc Giọng Nói",
        "card_volume": "Cân Bằng Âm Lượng",
        "card_silence": "Thu Gọn Im Lặng",
        "card_split": "Tách Câu Spoken",
        
        # Subtitles / Translation Configuration
        "lbl_auto_sub": "Tạo phụ đề tự động",
        "lbl_trans_ai": "Dịch Phụ Đề",
        "lbl_lang": "Ngôn ngữ",
        "lbl_model": "Mô hình Whisper",
        "lbl_speed": "Tốc độ ASR",
        "lbl_batch": "Kích thước lô (Batch)",
        "lbl_format": "Khung hình video",
        "lbl_lines": "Số dòng tối đa",
        "lbl_target_lang": "Ngôn ngữ đích",
        "lbl_translate_model": "Model dịch",
        "lbl_google_msg": "✅ Dịch miễn phí qua Google — Không cần API Key",
        "lbl_api_key": "API Key:",
        "lbl_gemini_hint": "<span style='color:#a78bfa; font-weight:600;'>Gemini 3.5/3.1 Flash</span> yêu cầu một API Key hợp lệ từ Google AI Studio. <a href='https://aistudio.google.com/' style='color:#a78bfa; text-decoration:underline;'>Lấy Key tại đây</a>.",
        "engine_gemini_35": "Gemini 3.5 Flash",
        "engine_gemini_31": "Gemini 3.1 Flash Lite",
        "engine_google": "Google Bypass (Miễn phí)",
        
        # Log & Status
        "btn_clear_log": "🗑  Xóa log",
        "btn_export_log": "💾  Xuất log",
        "lbl_status_title": "Trạng thái:",
        "status_ready": "Sẵn sàng",
        "status_processing": "Đang xử lý...",
        "status_done": "Hoàn thành!",
        "status_translating": "Đang dịch phụ đề...",
        "status_error": "Gặp lỗi trong quá trình xử lý.",
        "status_cancelling": "Đang hủy...",
        "status_cancelled": "Đã hủy dịch thuật.",
        "lbl_elapsed_title": "Thời gian xử lý:",
        "btn_open_folder": "📁  Mở thư mục kết quả",

        # Extra status translations
        "status_translation_done": "Dịch phụ đề hoàn thành!",
        "status_translation_error": "Dịch phụ đề gặp lỗi.",
        "status_translation_cancelled": "Đã hủy dịch thuật.",
        "status_quota_exceeded": "API đạt giới hạn quota.",
        
        # License status messages (v2)
        "license_valid": "Bản quyền hợp lệ.",
        "license_activated": "Kích hoạt bản quyền thành công trên máy này!",
        "license_migrated": "Đã chuyển đổi bản quyền sang hệ thống mới thành công!",
        "license_not_found": "Key bản quyền không tồn tại.",
        "license_disabled": "Key bản quyền đã bị vô hiệu hóa.",
        "license_expired": "Mã dùng thử 3 ngày của bạn đã hết hạn! Vui lòng gia hạn gói Premium để tiếp tục sử dụng.",
        "license_device_mismatch": "Key đã được sử dụng ở máy khác!",
        "license_legacy_device_mismatch": "Key đã được sử dụng ở máy khác (phiên bản cũ).",
        "license_device_id_unavailable": "Không thể xác định mã thiết bị ổn định. Vui lòng khởi động lại Windows hoặc liên hệ hỗ trợ.",
        "license_network_error": "Lỗi kết nối kiểm tra bản quyền. Vui lòng kiểm tra mạng và thử lại.",
        "license_server_error": "Lỗi máy chủ bản quyền. Vui lòng thử lại sau.",
        "license_client_config_error": "Lỗi cấu hình máy chủ bản quyền. Vui lòng cập nhật phần mềm hoặc liên hệ hỗ trợ.",
        "license_auth_error": "Lỗi xác thực máy chủ bản quyền. Vui lòng liên hệ hỗ trợ.",
        "license_empty_key": "Vui lòng nhập Key kích hoạt.",
        "license_bind_failed": "Không thể liên kết mã máy HWID vào máy chủ.",
        
        # Combobox options: combo_lang
        "combo_lang_auto": "Tự động nhận diện",
        "combo_lang_vi": "Tiếng Việt",
        "combo_lang_en": "Tiếng Anh (English)",
        "combo_lang_zh": "Tiếng Trung (中文)",
        "combo_lang_ja": "Tiếng Nhật (日本語)",
        "combo_lang_ko": "Tiếng Hàn (한국어)",
        "combo_lang_ru": "Tiếng Nga (Русский)",
        "combo_lang_fr": "Tiếng Pháp (Français)",
        "combo_lang_es": "Tiếng Tây Ban Nha",
        
        # Combobox options: combo_model
        "combo_model_turbo": "large-v3-turbo (Nhanh x8, chính xác tốt - Khuyên dùng)",
        "combo_model_large": "large-v3 (Chính xác tối đa - Yêu cầu cấu hình mạnh)",
        "combo_model_medium": "medium (Tốc độ nhanh, nhẹ máy - Độ chính xác khá)",
        
        # Combobox options: combo_speed
        "combo_speed_10x": "1.0x (Tốc độ gốc - Mặc định)",
        "combo_speed_09x": "0.9x (Giọng nói nhanh - Tăng chính xác)",
        "combo_speed_08x": "0.8x (Giọng nói cực nhanh / Tin tức / Rap)",
        
        # Combobox options: combo_batch
        "combo_batch_1": "1 (Tuần tự - Ít VRAM nhất, chậm nhất)",
        "combo_batch_2": "2 (Song song nhẹ)",
        "combo_batch_4": "4 (Song song vừa)",
        "combo_batch_8": "8 (Song song nhanh - Khuyên dùng)",
        "combo_batch_16": "16 (Song song tối đa - Cần nhiều VRAM)",
        "combo_batch_32": "32 (Cực nhanh - Yêu cầu GPU khủng)",
        
        # Combobox options: combo_format
        "combo_format_169": "16:9 (Video Ngang)",
        "combo_format_916": "9:16 (Video Dọc)",
        "combo_format_11": "1:1 (Video Vuông)",
        
        # Combobox options: combo_lines
        "combo_lines_1": "1 dòng (Gọn – 1 hàng chữ mỗi đoạn)",
        "combo_lines_2": "2 dòng (2 hàng chữ mỗi đoạn)",
        
        # Combobox options: combo_translate_lang
        "combo_target_vi": "Tiếng Việt (vi)",
        "combo_target_en": "Tiếng Anh (en)",
        "combo_target_zh": "Tiếng Trung giản thể (zh)",
        "combo_target_ja": "Tiếng Nhật (ja)",
        "combo_target_ko": "Tiếng Hàn (ko)",
        "combo_target_es": "Tiếng Tây Ban Nha (es)",
        "combo_target_fr": "Tiếng Pháp (fr)",
        "combo_target_ru": "Tiếng Nga (ru)"
    },
    "en": {
        "window_title": "Audio Factory",
        "tab_silence": "Cut Silence",
        "btn_start": "▶  Start Processing",
        "btn_start_processing": "⏳  Processing...",
        "btn_cancel": "■  Cancel",
        "btn_cancel_processing": "⏳  Cancelling...",
        "lbl_threshold": "Silence Threshold (dB):",
        "lbl_duration": "Min Duration (s):",
        "msg_success": "🎉 Audio processed successfully!",
        "msg_license_error": "❌ License Key is invalid or expired!",
        
        "header_subtitle": "Created by Lực Nguyễn",
        "footer": "Powered by FFmpeg + Whisper Local + Lực Nguyễn",
        "panel_input": "Input",
        "panel_output": "Output",
        "panel_processing": "Processing Config",
        "panel_subtitles": "Subtitle Config",
        "panel_log": "Process Logs",
        "panel_progress": "Progress",
        
        # Input buttons / labels
        "btn_add_files": "＋  Add Files",
        "btn_remove_selected": "🗑  Clear All",
        "btn_move_up": "↑  Up",
        "btn_move_down": "↓  Down",
        "lbl_sum_count": "📁  Total: {count} files",
        "lbl_sum_duration": "⏱  Total duration: {duration}",
        "lbl_sum_size": "💾  Total size: {size}",
        "lbl_summary": "💡 *Drag & drop audio/video files into the table above to import*",
        
        # Table Headers
        "table_header_stt": "No.",
        "table_header_name": "File Name",
        "table_header_duration": "Duration",
        "table_header_size": "Size",
        "table_header_action": "✕",
        
        # Output section
        "lbl_out_dir": "Output Directory:",
        "placeholder_out_dir": "Choose output directory...",
        "btn_browse_output": "📁  Browse",
        "lbl_project_name": "Project Name:",
        "lbl_output_format": "Export Format:",
        
        # Feature cards
        "card_merge": "Merge Audio",
        "card_voice": "Voice Denoise",
        "card_volume": "Volume Leveler",
        "card_silence": "Silence Shortener",
        "card_split": "Sentence Splitter",
        
        # Subtitles / Translation Configuration
        "lbl_auto_sub": "Auto Generate Subtitles",
        "lbl_trans_ai": "AI Translate Subtitles",
        "lbl_lang": "Language",
        "lbl_model": "Whisper Model",
        "lbl_speed": "ASR Speed",
        "lbl_batch": "Batch Size",
        "lbl_format": "Video Aspect Ratio",
        "lbl_lines": "Max Lines",
        "lbl_target_lang": "Target Language",
        "lbl_translate_model": "Translation Model",
        "lbl_google_msg": "✅ Free Google Translation — No API Key Required",
        "lbl_api_key": "API Key:",
        "lbl_gemini_hint": "<span style='color:#a78bfa; font-weight:600;'>Gemini 3.5/3.1 Flash</span> requires a valid API Key from Google AI Studio. <a href='https://aistudio.google.com/' style='color:#a78bfa; text-decoration:underline;'>Get Key here</a>.",
        "engine_gemini_35": "Gemini 3.5 Flash",
        "engine_gemini_31": "Gemini 3.1 Flash Lite",
        "engine_google": "Google Bypass (Online Free)",
        
        # Log & Status
        "btn_clear_log": "🗑  Clear Log",
        "btn_export_log": "💾  Export Log",
        "lbl_status_title": "Status:",
        "status_ready": "Ready",
        "status_processing": "Processing...",
        "status_done": "Completed!",
        "status_translating": "Translating subtitles...",
        "status_error": "An error occurred during processing.",
        "status_cancelling": "Cancelling...",
        "status_cancelled": "Cancelled.",
        "lbl_elapsed_title": "Elapsed Time:",
        "btn_open_folder": "📁  Open Output Folder",

        # Extra status translations
        "status_translation_done": "Translation completed!",
        "status_translation_error": "Translation failed.",
        "status_translation_cancelled": "Translation cancelled.",
        "status_quota_exceeded": "API quota exceeded.",
        
        # License status messages (v2)
        "license_valid": "License is valid.",
        "license_activated": "License activated successfully on this device!",
        "license_migrated": "License migrated to the new system successfully!",
        "license_not_found": "License key not found.",
        "license_disabled": "License key has been disabled.",
        "license_expired": "Your 3-day trial has expired! Please renew your Premium plan to continue.",
        "license_device_mismatch": "This key is already in use on another device!",
        "license_legacy_device_mismatch": "This key is already in use on another device (legacy version).",
        "license_device_id_unavailable": "Unable to determine a stable device ID. Please restart Windows or contact support.",
        "license_network_error": "Network error during license verification. Please check your connection and try again.",
        "license_server_error": "License server error. Please try again later.",
        "license_client_config_error": "License server configuration error. Please update the app or contact support.",
        "license_auth_error": "License server authentication error. Please contact support.",
        "license_empty_key": "Please enter your License Key.",
        "license_bind_failed": "Unable to bind device ID to the server.",
        
        # Combobox options: combo_lang
        "combo_lang_auto": "Auto Detect",
        "combo_lang_vi": "Vietnamese",
        "combo_lang_en": "English",
        "combo_lang_zh": "Chinese (中文)",
        "combo_lang_ja": "Japanese (日本語)",
        "combo_lang_ko": "Korean (한국어)",
        "combo_lang_ru": "Russian (Русский)",
        "combo_lang_fr": "French (Français)",
        "combo_lang_es": "Spanish",
        
        # Combobox options: combo_model
        "combo_model_turbo": "large-v3-turbo (8x Faster, good accuracy - Recommended)",
        "combo_model_large": "large-v3 (Maximum accuracy - Requires high-end GPU)",
        "combo_model_medium": "medium (Fast speed, lightweight - Fair accuracy)",
        
        # Combobox options: combo_speed
        "combo_speed_10x": "1.0x (Original speed - Default)",
        "combo_speed_09x": "0.9x (Fast speech - Improves accuracy)",
        "combo_speed_08x": "0.8x (Very fast speech / News / Rap)",
        
        # Combobox options: combo_batch
        "combo_batch_1": "1 (Sequential - Least VRAM, slowest)",
        "combo_batch_2": "2 (Light parallel)",
        "combo_batch_4": "4 (Medium parallel)",
        "combo_batch_8": "8 (Fast parallel - Recommended)",
        "combo_batch_16": "16 (Maximum parallel - High VRAM)",
        "combo_batch_32": "32 (Ultra fast - Requires high-end GPU)",
        
        # Combobox options: combo_format
        "combo_format_169": "16:9 (Horizontal Video)",
        "combo_format_916": "9:16 (Vertical Video)",
        "combo_format_11": "1:1 (Square Video)",
        
        # Combobox options: combo_lines
        "combo_lines_1": "1 line (Compact – 1 row of text per segment)",
        "combo_lines_2": "2 lines (2 rows of text per segment)",
        
        # Combobox options: combo_translate_lang
        "combo_target_vi": "Vietnamese (vi)",
        "combo_target_en": "English (en)",
        "combo_target_zh": "Simplified Chinese (zh)",
        "combo_target_ja": "Japanese (ja)",
        "combo_target_ko": "Korean (ko)",
        "combo_target_es": "Spanish (es)",
        "combo_target_fr": "French (fr)",
        "combo_target_ru": "Russian (ru)"
    }
}

def get_translation(lang_code: str) -> Dict[str, str]:
    """
    Trả về bộ chuỗi ngôn ngữ tương ứng, mặc định là Tiếng Việt nếu không tìm thấy.
    """
    return TRANSLATIONS.get(lang_code, TRANSLATIONS["vi"])

"""
雲端 AI 語音轉文字模組 (Google Gemini 3.8 Flash)
功能：
1. 自動上傳音訊檔案並呼叫 Gemini 轉錄
2. 包含精確時間軸與人物角色聲音識別 (Speaker Diarization)
3. 自動分割並儲存為二個檔案：【會議摘要】與【逐字稿】
"""

import os
import sys
import json
import base64
import requests
import datetime
from pathlib import Path

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(get_base_dir(), "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"gemini_api_key": "", "save_key_local": False}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")

def transcribe_cloud_gemini(audio_path, api_key, summarize=True, progress_cb=None):
    """
    使用 Google Gemini Flash 轉錄音訊
    支援大檔案上傳 (Google AI File API)、精準時間軸、說話者識別、繁體中文輸出
    並自動分拆為【會議摘要】與【逐字稿】二個檔案儲存於音訊同目錄
    """
    def log(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)

    if not api_key:
        raise ValueError("請先輸入有效的 Gemini API Key。若無 Key，可點擊旁邊的「如何免費取得 API Key」依教學取得。")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"找不到音訊檔案：{audio_path}")

    log(0.10, "準備上傳音訊至雲端...")
    file_size = os.path.getsize(audio_path)
    ext = os.path.splitext(audio_path)[1].lower()
    
    mime_types = {
        ".mp3": "audio/mp3",
        ".wav": "audio/wav",
        ".m4a": "audio/m4a",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac"
    }
    mime_type = mime_types.get(ext, "audio/mp3")

    # 若檔案小於 15MB，可直接 inline base64；若大於 15MB 則走 Google File API
    if file_size <= 15 * 1024 * 1024:
        log(0.20, f"檔案大小約 {file_size // 1024} KB，正在打包音訊資料...")
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        audio_part = {
            "inlineData": {
                "mimeType": mime_type,
                "data": audio_b64
            }
        }
    else:
        # 使用 Google File API (Resumable Upload)
        log(0.20, f"音訊檔案較大 ({file_size // (1024*1024)} MB)，正在上傳至 Google 檔案伺服器...")
        upload_init_url = f"https://generativelanguage.googleapis.com/v1beta/files?key={api_key}"
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json"
        }
        meta = {"file": {"displayName": os.path.basename(audio_path)}}
        res_init = requests.post(upload_init_url, headers=headers, json=meta)
        if res_init.status_code != 200:
            raise RuntimeError(f"初始化檔案上傳失敗 ({res_init.status_code}): {res_init.text}")

        upload_url = res_init.headers.get("X-Goog-Upload-URL")
        with open(audio_path, "rb") as f:
            upload_headers = {
                "Content-Length": str(file_size),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize"
            }
            res_upload = requests.post(upload_url, headers=upload_headers, data=f)
        if res_upload.status_code != 200:
            raise RuntimeError(f"音訊上傳失敗 ({res_upload.status_code}): {res_upload.text}")

        file_info = res_upload.json().get("file", {})
        file_uri = file_info.get("uri")
        audio_part = {
            "fileData": {
                "mimeType": mime_type,
                "fileUri": file_uri
            }
        }

    log(0.50, "雲端 AI 正在進行語音識別、人物聲音分離與摘要分析...")

    summary_instruction = ""
    if summarize:
        summary_instruction = """
請務必使用以下特定標籤分別包裹【會議摘要】與【逐字稿】：
===SUMMARY_START===
### 📊 會議摘要
- 📌 核心重點與討論主題 (條列式)
- ✅ 待辦事項與決策指派 (Action Items)
===SUMMARY_END===
"""
    else:
        summary_instruction = "不需提供會議摘要。"

    prompt = f"""這是一段 Teams 繁體中文會議錄音。
請將這段音訊轉錄為精確的繁體中文逐字稿，要求如下：
1. 請嚴格使用以下標籤包裹逐字稿內容：
===TRANSCRIPT_START===
逐字稿內容
===TRANSCRIPT_END===
2. 逐字稿必須標註時間軸 [MM:SS] 或 [HH:MM:SS]。
3. 必須進行人物聲音識別 (Speaker Diarization)，明確區分不同的說話者（例如：「說話者 A」、「說話者 B」或根據語境角色標註）。
4. 逐字稿格式範例：
   [00:01:15] 說話者 A：大家早安，我們今天開始討論錄音專案進度...
   [00:01:23] 說話者 B：好的，目前系統架構已經完成...
5. 保持語句通順，自動校正語音辨識的同音錯字與常見 IT/商業術語。
{summary_instruction}
"""

    candidate_models = [
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-1.5-flash"
    ]

    payload = {
        "contents": [{
            "parts": [
                audio_part,
                {"text": prompt}
            ]
        }],
        "generationConfig": {
            "temperature": 0.2
        }
    }

    resp = None
    last_err = ""
    for model_name in candidate_models:
        model_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            resp = requests.post(model_url, json=payload, headers={"Content-Type": "application/json"}, timeout=180)
            if resp.status_code == 200:
                break
            elif resp.status_code == 404:
                last_err = f"模型 {model_name} 未找到，嘗試下一型號..."
                continue
            else:
                last_err = f"模型 {model_name} 回報錯誤 ({resp.status_code}): {resp.text}"
                continue
        except Exception as e:
            last_err = str(e)
            continue

    if not resp or resp.status_code != 200:
        raise RuntimeError(f"Gemini API 請求失敗：\n{last_err}")

    result_json = resp.json()
    candidates = result_json.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"未能取得轉錄內容：\n{result_json}")

    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    summary_text = ""
    transcript_text = raw_text

    if "===SUMMARY_START===" in raw_text and "===SUMMARY_END===" in raw_text:
        summary_text = raw_text.split("===SUMMARY_START===")[1].split("===SUMMARY_END===")[0].strip()

    if "===TRANSCRIPT_START===" in raw_text and "===TRANSCRIPT_END===" in raw_text:
        transcript_text = raw_text.split("===TRANSCRIPT_START===")[1].split("===TRANSCRIPT_END===")[0].strip()
    elif "===SUMMARY_END===" in raw_text:
        transcript_text = raw_text.split("===SUMMARY_END===")[1].strip()
    elif "---" in raw_text:
        parts = raw_text.split("---", 1)
        if "摘要" in parts[0] or "重點" in parts[0]:
            summary_text = parts[0].strip()
            transcript_text = parts[1].strip()

    # 自動拆分為二個獨立檔案並儲存至音訊所在資料夾
    base_dir = os.path.dirname(os.path.abspath(audio_path))
    stem = Path(audio_path).stem
    summary_file = os.path.join(base_dir, f"{stem}_會議摘要.txt")
    transcript_file = os.path.join(base_dir, f"{stem}_逐字稿.txt")

    if summary_text:
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(summary_text)

    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    log(1.0, "雲端轉錄完成！已自動儲存摘要與逐字稿二個檔案。")
    return {
        "summary": summary_text,
        "transcript": transcript_text,
        "summary_file": summary_file if summary_text else None,
        "transcript_file": transcript_file,
        "raw": raw_text
    }

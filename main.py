import os
import base64
import json
import httpx
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI(title="請款單辨識系統")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1rutFLOfG8uHeesUolKMHVZn4C4ZGUVuonCILTPZ3VCk")
SHEET_NAME = os.getenv("SHEET_NAME", "請款紀錄")

PROMPT = """分析這張請款單圖片，提取欄位資訊，以 JSON 回覆：
{"公司別":"","申請日期":"","表單類別":"","申請事項類別":"","申請人":"","對象":"","幣別":"","總金額":"","主旨":"","內容說明":""}

注意事項：
1. 公司別只能是以下三種之一：SG、CELA、MEGA。請根據圖片中的公司名稱、Logo或相關資訊判斷屬於哪一家公司。
2. 申請日期格式為 YYYY/M/D（例如：2026/1/13）
3. 總金額只填數字，不要包含貨幣符號
4. 找不到的欄位填 null
5. 只回覆 JSON，不要其他文字。"""


def get_sheets_service():
    if not GOOGLE_CREDENTIALS_JSON:
        return None
    creds = json.loads(GOOGLE_CREDENTIALS_JSON)
    credentials = service_account.Credentials.from_service_account_info(
        creds, scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return build('sheets', 'v4', credentials=credentials)


async def call_claude(img_b64: str, media_type: str, api_key: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
            {"type": "text", "text": PROMPT}
        ]}]
    )
    return parse_json(resp.content[0].text)


async def call_openai(img_b64: str, media_type: str, api_key: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{img_b64}"}}
                ]}],
                "max_tokens": 1024
            }
        )
        if resp.status_code != 200:
            raise Exception(f"OpenAI 錯誤: {resp.text}")
        return parse_json(resp.json()["choices"][0]["message"]["content"])


async def call_gemini(img_b64: str, media_type: str, api_key: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}",
            json={"contents": [{"parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": media_type, "data": img_b64}}
            ]}]}
        )
        if resp.status_code != 200:
            raise Exception(f"Gemini 錯誤: {resp.text}")
        return parse_json(resp.json()["candidates"][0]["content"]["parts"][0]["text"])


def parse_json(text: str) -> dict:
    t = text.strip()
    if "```json" in t:
        t = t.split("```json")[1].split("```")[0]
    elif "```" in t:
        t = t.split("```")[1].split("```")[0]
    return json.loads(t.strip())


def save_to_sheet(data: dict):
    service = get_sheets_service()
    if not service:
        return
    # 欄位對應：A:公司別, B:申請日期, C:表單類別, D:申請事項類別, E:申請人, F:對象, G:幣別, H:總金額, I:主旨, J:內容說明
    row = [
        data.get("公司別", ""),
        data.get("申請日期", ""),
        data.get("表單類別", ""),
        data.get("申請事項類別", ""),
        data.get("申請人", ""),
        data.get("對象", ""),
        data.get("幣別", ""),
        data.get("總金額", ""),
        data.get("主旨", ""),
        data.get("內容說明", ""),
    ]
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:J",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]}
    ).execute()


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/process")
async def process(
    files: List[UploadFile] = File(...),
    model: str = Form("claude"),
    api_key: str = Form(...)
):
    results = []
    for file in files:
        try:
            content = await file.read()
            img_b64 = base64.b64encode(content).decode()

            if model == "claude":
                data = await call_claude(img_b64, file.content_type, api_key)
            elif model == "openai":
                data = await call_openai(img_b64, file.content_type, api_key)
            elif model == "gemini":
                data = await call_gemini(img_b64, file.content_type, api_key)
            else:
                raise Exception(f"不支援: {model}")

            try:
                save_to_sheet(data)
            except Exception as e:
                print(f"Sheet 錯誤: {e}")

            results.append({"filename": file.filename, "success": True, "data": data})
        except Exception as e:
            results.append({"filename": file.filename, "success": False, "error": str(e)})

    ok = sum(1 for r in results if r["success"])
    return {"total": len(results), "successful": ok, "failed": len(results) - ok, "results": results}


app.mount("/static", StaticFiles(directory="static"), name="static")

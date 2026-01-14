"""
請款單圖片辨識 Web App - FastAPI 後端
"""
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
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI(title="請款單辨識系統", version="2.0.0")

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

EXTRACTION_PROMPT = """請仔細分析這張請款單圖片，提取以下欄位資訊。如果某個欄位找不到，請填入 null。

需要提取的欄位:
1. 申請單號 2. 申請日期 3. 表單類別 4. 申請事項類別 5. 申請人
6. 對象 7. 幣別 8. 總金額 9. 主旨 10. 內容說明 11. 附件類型

請以 JSON 格式回覆:
{"申請單號":"值","申請日期":"值","表單類別":"值","申請事項類別":"值","申請人":"值","對象":"值","幣別":"值","總金額":"值","主旨":"值","內容說明":"值","附件類型":"值"}

只回覆 JSON，不要其他文字。"""


class ExpenseClaimData(BaseModel):
    申請單號: Optional[str] = None
    申請日期: Optional[str] = None
    表單類別: Optional[str] = None
    申請事項類別: Optional[str] = None
    申請人: Optional[str] = None
    對象: Optional[str] = None
    幣別: Optional[str] = None
    總金額: Optional[str] = None
    主旨: Optional[str] = None
    內容說明: Optional[str] = None
    附件類型: Optional[str] = None


class ProcessResult(BaseModel):
    filename: str
    success: bool
    data: Optional[ExpenseClaimData] = None
    error: Optional[str] = None


class BatchProcessResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: List[ProcessResult]


def get_sheets_service():
    if not GOOGLE_CREDENTIALS_JSON:
        raise HTTPException(status_code=500, detail="未設定 GOOGLE_CREDENTIALS_JSON")
    creds = json.loads(GOOGLE_CREDENTIALS_JSON)
    credentials = service_account.Credentials.from_service_account_info(creds, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=credentials)


async def extract_with_claude(image_base64: str, media_type: str, api_key: str) -> ExpenseClaimData:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_base64}},
            {"type": "text", "text": EXTRACTION_PROMPT}
        ]}],
    )
    return parse_response(response.content[0].text)


async def extract_with_openai(image_base64: str, media_type: str, api_key: str) -> ExpenseClaimData:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": EXTRACTION_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_base64}"}}
        ]}],
        "max_tokens": 1024
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        if resp.status_code != 200:
            raise ValueError(f"OpenAI API 錯誤: {resp.json().get('error', {}).get('message', 'Unknown')}")
        return parse_response(resp.json()["choices"][0]["message"]["content"])


async def extract_with_gemini(image_base64: str, media_type: str, api_key: str) -> ExpenseClaimData:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": EXTRACTION_PROMPT}, {"inline_data": {"mime_type": media_type, "data": image_base64}}]}]}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            raise ValueError(f"Gemini API 錯誤: {resp.json().get('error', {}).get('message', 'Unknown')}")
        return parse_response(resp.json()["candidates"][0]["content"]["parts"][0]["text"])


def parse_response(text: str) -> ExpenseClaimData:
    t = text.strip()
    if "```json" in t: t = t.split("```json")[1].split("```")[0]
    elif "```" in t: t = t.split("```")[1].split("```")[0]
    return ExpenseClaimData(**json.loads(t.strip()))


async def extract_expense_data(image_base64: str, media_type: str, model: str, api_key: str) -> ExpenseClaimData:
    if model == "claude": return await extract_with_claude(image_base64, media_type, api_key)
    elif model == "openai": return await extract_with_openai(image_base64, media_type, api_key)
    elif model == "gemini": return await extract_with_gemini(image_base64, media_type, api_key)
    raise ValueError(f"不支援的模型: {model}")


def append_to_sheet(data: ExpenseClaimData):
    service = get_sheets_service()
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A:A").execute()
    next_seq = len(result.get('values', []))
    row = [next_seq, data.申請單號 or "", data.申請日期 or "", data.表單類別 or "", data.申請事項類別 or "",
           data.申請人 or "", data.對象 or "", data.幣別 or "", data.總金額 or "", data.主旨 or "",
           data.內容說明 or "", data.附件類型 or "", datetime.now().strftime("%Y/%m/%d %H:%M:%S"), "", "待審核"]
    service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A:O",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body={"values": [row]}).execute()


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}


@app.post("/api/process", response_model=BatchProcessResponse)
async def process_images(files: List[UploadFile] = File(...), model: str = Form("claude"), api_key: str = Form(...)):
    if not files: raise HTTPException(status_code=400, detail="請上傳圖片")
    if not api_key: raise HTTPException(status_code=400, detail="請提供 API Key")

    results, successful, failed = [], 0, 0
    for file in files:
        try:
            content = await file.read()
            image_base64 = base64.b64encode(content).decode("utf-8")
            expense_data = await extract_expense_data(image_base64, file.content_type, model, api_key)
            try: append_to_sheet(expense_data)
            except Exception as e: print(f"Sheet 寫入失敗: {e}")
            results.append(ProcessResult(filename=file.filename, success=True, data=expense_data))
            successful += 1
        except Exception as e:
            results.append(ProcessResult(filename=file.filename, success=False, error=str(e)))
            failed += 1
    return BatchProcessResponse(total=len(files), successful=successful, failed=failed, results=results)


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

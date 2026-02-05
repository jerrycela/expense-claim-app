import os
import re
import base64
import json
import logging
from enum import Enum
from typing import List, Optional
from datetime import datetime

import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================
# Access Code for authentication (default: cela)
ACCESS_CODE = os.getenv("ACCESS_CODE", "cela")

# AI API Keys (stored securely in environment variables)
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Google Sheets Configuration
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
SPREADSHEET_ID = "1rutFLOfG8uHeesUolKMHVZn4C4ZGUVuonCILTPZ3VCk"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid=0#gid=0"
SHEET_NAME = os.getenv("SHEET_NAME", "請款紀錄")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# File Upload Limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB total
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
VALID_COMPANIES = {"SG", "CELA", "MEGA"}

PROMPT = """分析這張請款單圖片，提取欄位資訊，以 JSON 回覆：
{"公司別":"","申請日期":"","表單類別":"","申請事項類別":"","申請人":"","對象":"","幣別":"","總金額":"","主旨":"","內容說明":""}

注意事項：
1. 公司別只能是以下三種之一：SG、CELA、MEGA。請根據圖片中的公司名稱、Logo或相關資訊判斷屬於哪一家公司。
2. 申請日期格式為 YYYY/M/D（例如：2026/1/13）
3. 總金額只填數字，不要包含貨幣符號
4. 找不到的欄位填 null
5. 只回覆 JSON，不要其他文字。"""


# ============================================================================
# Enums and Models
# ============================================================================
class ModelType(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"


class ProcessResult(BaseModel):
    filename: str
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    sheet_saved: bool = False


class ProcessResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: List[ProcessResult]
    spreadsheet_url: str = SPREADSHEET_URL


class AuthResponse(BaseModel):
    success: bool
    message: str
    available_models: List[str] = []


# ============================================================================
# FastAPI App
# ============================================================================
app = FastAPI(
    title="請款單辨識系統",
    description="AI 驅動的請款單圖片辨識與自動記錄系統",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Access-Code"],
)


# ============================================================================
# Authentication
# ============================================================================
def verify_access_code(code: Optional[str]) -> bool:
    """Verify the access code."""
    if not code:
        return False
    return code == ACCESS_CODE


def get_available_models() -> List[str]:
    """Get list of available models based on configured API keys."""
    models = []
    if CLAUDE_API_KEY:
        models.append("claude")
    if OPENAI_API_KEY:
        models.append("openai")
    if GEMINI_API_KEY:
        models.append("gemini")
    return models


def get_api_key(model: ModelType) -> Optional[str]:
    """Get API key for the specified model."""
    if model == ModelType.CLAUDE:
        return CLAUDE_API_KEY
    elif model == ModelType.OPENAI:
        return OPENAI_API_KEY
    elif model == ModelType.GEMINI:
        return GEMINI_API_KEY
    return None


# ============================================================================
# AI Model Handlers
# ============================================================================
async def call_claude(img_b64: str, media_type: str, api_key: str) -> dict:
    """Call Claude API for image analysis."""
    import anthropic
    try:
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
    except anthropic.AuthenticationError:
        raise ValueError("Claude API Key 無效")
    except anthropic.RateLimitError:
        raise ValueError("Claude API 請求過於頻繁，請稍後再試")
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise ValueError(f"Claude API 錯誤: {str(e)}")


async def call_openai(img_b64: str, media_type: str, api_key: str) -> dict:
    """Call OpenAI API for image analysis."""
    try:
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
            if resp.status_code == 401:
                raise ValueError("OpenAI API Key 無效")
            if resp.status_code == 429:
                raise ValueError("OpenAI API 請求過於頻繁，請稍後再試")
            if resp.status_code != 200:
                logger.error(f"OpenAI API error: {resp.status_code} - {resp.text[:200]}")
                raise ValueError("OpenAI API 處理失敗")
            return parse_json(resp.json()["choices"][0]["message"]["content"])
    except httpx.TimeoutException:
        raise ValueError("OpenAI API 請求超時")
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise ValueError("OpenAI API 錯誤")


async def call_gemini(img_b64: str, media_type: str, api_key: str) -> dict:
    """Call Gemini API for image analysis."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                json={"contents": [{"parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": media_type, "data": img_b64}}
                ]}]}
            )
            if resp.status_code == 400 and "API_KEY_INVALID" in resp.text:
                raise ValueError("Gemini API Key 無效")
            if resp.status_code == 429:
                raise ValueError("Gemini API 請求過於頻繁，請稍後再試")
            if resp.status_code != 200:
                logger.error(f"Gemini API error: {resp.status_code} - {resp.text[:200]}")
                raise ValueError("Gemini API 處理失敗")
            return parse_json(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
    except httpx.TimeoutException:
        raise ValueError("Gemini API 請求超時")
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise ValueError("Gemini API 錯誤")


# Model dispatcher
MODEL_HANDLERS = {
    ModelType.CLAUDE: call_claude,
    ModelType.OPENAI: call_openai,
    ModelType.GEMINI: call_gemini,
}


# ============================================================================
# Utility Functions
# ============================================================================
def parse_json(text: str) -> dict:
    """Parse JSON from AI response, handling markdown code blocks."""
    try:
        t = text.strip()
        if "```json" in t:
            t = t.split("```json")[1].split("```")[0]
        elif "```" in t:
            t = t.split("```")[1].split("```")[0]
        return json.loads(t.strip())
    except json.JSONDecodeError:
        logger.error(f"JSON parse error: {text[:200]}")
        raise ValueError("AI 回應格式錯誤，無法解析 JSON")
    except IndexError:
        logger.error(f"Cannot extract JSON from: {text[:200]}")
        raise ValueError("AI 回應格式錯誤")


def validate_expense_data(data: dict) -> dict:
    """Validate and clean extracted expense data."""
    # Validate company
    company = data.get("公司別")
    if company and company not in VALID_COMPANIES:
        logger.warning(f"Invalid company: {company}")
        company_upper = company.upper()
        for valid in VALID_COMPANIES:
            if valid in company_upper:
                data["公司別"] = valid
                break

    # Validate date format
    date_str = data.get("申請日期")
    if date_str and date_str != "null":
        try:
            for fmt in ["%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"]:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    data["申請日期"] = parsed.strftime("%Y/%m/%d")
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    # Validate amount (should be numeric)
    amount = data.get("總金額")
    if amount and amount != "null":
        cleaned = re.sub(r"[^\d.]", "", str(amount))
        if cleaned:
            data["總金額"] = cleaned

    return data


def get_sheets_service():
    """Get Google Sheets API service."""
    if not GOOGLE_CREDENTIALS_JSON:
        logger.warning("Google Sheets credentials not configured")
        return None
    try:
        creds = json.loads(GOOGLE_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            creds, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return build("sheets", "v4", credentials=credentials)
    except json.JSONDecodeError:
        logger.error("Invalid GOOGLE_CREDENTIALS_JSON format")
        return None
    except Exception as e:
        logger.error(f"Failed to create Sheets service: {e}")
        return None


def save_to_sheet(data: dict) -> bool:
    """Save expense data to Google Sheet. Returns True if successful."""
    service = get_sheets_service()
    if not service:
        return False

    try:
        row = [
            data.get("公司別") or "",
            data.get("申請日期") or "",
            data.get("表單類別") or "",
            data.get("申請事項類別") or "",
            data.get("申請人") or "",
            data.get("對象") or "",
            data.get("幣別") or "",
            data.get("總金額") or "",
            data.get("主旨") or "",
            data.get("內容說明") or "",
        ]
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]}
        ).execute()
        logger.info(f"Saved to sheet: {data.get('申請人', 'unknown')} - {data.get('總金額', 'unknown')}")
        return True
    except Exception as e:
        logger.error(f"Failed to save to sheet: {e}")
        return False


def validate_image_file(file: UploadFile) -> None:
    """Validate uploaded image file."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案類型: {file.content_type}，僅支援 JPEG, PNG, GIF, WebP"
        )


# ============================================================================
# API Endpoints
# ============================================================================
@app.get("/")
async def root():
    """Serve the main HTML page."""
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.1.0"}


@app.post("/api/auth", response_model=AuthResponse)
async def authenticate(
    x_access_code: Optional[str] = Header(None, alias="X-Access-Code"),
):
    """
    Verify access code and return available models.
    """
    if not verify_access_code(x_access_code):
        raise HTTPException(status_code=401, detail="訪問碼錯誤")

    available = get_available_models()
    if not available:
        raise HTTPException(status_code=503, detail="目前沒有可用的 AI 模型，請聯繫管理員")

    return AuthResponse(
        success=True,
        message="驗證成功",
        available_models=available
    )


@app.post("/api/process", response_model=ProcessResponse)
async def process(
    files: List[UploadFile] = File(..., description="上傳的圖片檔案"),
    model: ModelType = Query(ModelType.CLAUDE, description="AI 模型選擇"),
    x_access_code: Optional[str] = Header(None, alias="X-Access-Code"),
):
    """
    Process uploaded expense claim images.

    - **files**: One or more image files (JPEG, PNG, GIF, WebP)
    - **model**: AI model to use (claude, openai, gemini)
    - **X-Access-Code**: Access code for authentication
    """
    # Verify access code
    if not verify_access_code(x_access_code):
        raise HTTPException(status_code=401, detail="訪問碼錯誤")

    # Get API key for the model
    api_key = get_api_key(model)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"{model.value} 模型未設定，請選擇其他模型")

    # Validate files
    if not files:
        raise HTTPException(status_code=400, detail="請上傳至少一個檔案")

    if len(files) > 20:
        raise HTTPException(status_code=400, detail="一次最多處理 20 個檔案")

    # Validate each file
    for file in files:
        validate_image_file(file)

    # Get model handler
    handler = MODEL_HANDLERS.get(model)
    if not handler:
        raise HTTPException(status_code=400, detail=f"不支援的模型: {model}")

    logger.info(f"Processing {len(files)} files with model: {model}")

    results = []
    total_size = 0

    for file in files:
        try:
            # Read and validate file size
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"檔案過大 ({len(content) / 1024 / 1024:.1f}MB)，上限 10MB")

            total_size += len(content)
            if total_size > MAX_TOTAL_SIZE:
                raise ValueError("總檔案大小超過 50MB 上限")

            # Encode to base64
            img_b64 = base64.b64encode(content).decode()

            # Call AI model
            data = await handler(img_b64, file.content_type, api_key)

            # Validate extracted data
            data = validate_expense_data(data)

            # Save to Google Sheet
            sheet_saved = save_to_sheet(data)

            results.append(ProcessResult(
                filename=file.filename,
                success=True,
                data=data,
                sheet_saved=sheet_saved
            ))
            logger.info(f"Successfully processed: {file.filename}")

        except ValueError as e:
            logger.warning(f"Validation error for {file.filename}: {e}")
            results.append(ProcessResult(
                filename=file.filename,
                success=False,
                error=str(e)
            ))
        except Exception as e:
            logger.error(f"Unexpected error processing {file.filename}: {e}")
            results.append(ProcessResult(
                filename=file.filename,
                success=False,
                error="處理時發生錯誤，請稍後再試"
            ))

    successful = sum(1 for r in results if r.success)
    return ProcessResponse(
        total=len(results),
        successful=successful,
        failed=len(results) - successful,
        results=results,
        spreadsheet_url=SPREADSHEET_URL
    )


# ============================================================================
# Error Handlers
# ============================================================================
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "伺服器內部錯誤"}
    )


# ============================================================================
# Static Files (must be last)
# ============================================================================
app.mount("/static", StaticFiles(directory="static"), name="static")

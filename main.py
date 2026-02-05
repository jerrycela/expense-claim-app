import os
import re
import base64
import json
import logging
import asyncio
import uuid
import random
import threading
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict

import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Query, BackgroundTasks
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
MAX_TOTAL_SIZE = 100 * 1024 * 1024  # 100MB total (increased for batch processing)
MAX_FILES = 100  # Maximum files per batch
BATCH_SIZE = 5  # Process 5 files concurrently (reduced for rate limit safety)
BATCH_DELAY = 2.0  # Delay between batches to avoid rate limiting (increased)
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
# Task Storage (In-Memory with Thread Safety)
# ============================================================================
# For production, consider using Redis or a database
task_storage: Dict[str, Dict[str, Any]] = OrderedDict()
task_storage_lock = asyncio.Lock()

# Task TTL settings
TASK_TTL_HOURS = 24
MAX_STORED_TASKS = 500

# Retry settings
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0


# ============================================================================
# Enums and Models
# ============================================================================
class ModelType(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileResult(BaseModel):
    filename: str
    status: str  # pending, processing, success, failed
    data: Optional[dict] = None
    error: Optional[str] = None
    sheet_saved: bool = False


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    total: int
    processed: int
    successful: int
    failed: int
    results: List[FileResult]
    spreadsheet_url: str = SPREADSHEET_URL
    created_at: str
    updated_at: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    available_models: List[str] = []
    max_files: int = MAX_FILES


# ============================================================================
# FastAPI App
# ============================================================================
app = FastAPI(
    title="請款單辨識系統",
    description="AI 驅動的請款單圖片辨識與自動記錄系統（支援批次處理）",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Access-Code"],
)


# ============================================================================
# Google Sheets Service (Thread-Safe Singleton)
# ============================================================================
_sheets_service = None
_sheets_service_lock = threading.Lock()


def get_sheets_service():
    """Get Google Sheets API service (thread-safe singleton pattern)."""
    global _sheets_service

    # Fast path
    if _sheets_service is not None:
        return _sheets_service

    # Slow path with lock
    with _sheets_service_lock:
        # Double-check after acquiring lock
        if _sheets_service is not None:
            return _sheets_service

        if not GOOGLE_CREDENTIALS_JSON:
            logger.warning("Google Sheets credentials not configured")
            return None
        try:
            creds = json.loads(GOOGLE_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(
                creds, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            _sheets_service = build("sheets", "v4", credentials=credentials)
            return _sheets_service
        except json.JSONDecodeError:
            logger.error("Invalid GOOGLE_CREDENTIALS_JSON format")
            return None
        except Exception as e:
            logger.error(f"Failed to create Sheets service: {e}")
            return None


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
# AI Model Handlers (Async)
# ============================================================================
async def call_claude(img_b64: str, media_type: str, api_key: str) -> dict:
    """Call Claude API for image analysis (async)."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
                            {"type": "text", "text": PROMPT}
                        ]
                    }]
                }
            )
            if resp.status_code == 401:
                raise ValueError("Claude API Key 無效")
            if resp.status_code == 429:
                raise ValueError("Claude API 請求過於頻繁，請稍後再試")
            if resp.status_code != 200:
                logger.error(f"Claude API error: {resp.status_code} - {resp.text[:200]}")
                raise ValueError("Claude API 處理失敗")
            return parse_json(resp.json()["content"][0]["text"])
    except httpx.TimeoutException:
        raise ValueError("Claude API 請求超時")
    except ValueError:
        raise
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


async def call_with_retry(handler, img_b64: str, media_type: str, api_key: str) -> dict:
    """Call API handler with exponential backoff retry for rate limits."""
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            return await handler(img_b64, media_type, api_key)
        except ValueError as e:
            error_msg = str(e)
            # Only retry on rate limit errors
            if "請求過於頻繁" in error_msg:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    # Exponential backoff with jitter
                    delay = min(
                        BASE_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1),
                        MAX_RETRY_DELAY
                    )
                    logger.warning(
                        f"Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    continue
            raise
        except Exception:
            raise

    raise last_exception or ValueError("API 請求失敗")


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


def validate_image_file(file: UploadFile) -> None:
    """Validate uploaded image file."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案類型: {file.content_type}，僅支援 JPEG, PNG, GIF, WebP"
        )


# ============================================================================
# Batch Google Sheets Operations (with Retry)
# ============================================================================
def batch_save_to_sheet(data_list: List[dict], max_retries: int = 3) -> Tuple[int, List[dict]]:
    """
    Save multiple expense records to Google Sheet with retry.
    Returns (saved_count, failed_items).
    """
    if not data_list:
        return 0, []

    service = get_sheets_service()
    if not service:
        logger.warning("Google Sheets service not available")
        return 0, data_list

    rows = []
    for data in data_list:
        rows.append([
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
        ])

    for attempt in range(max_retries):
        try:
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:J",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": rows}
            ).execute()

            logger.info(f"Batch saved {len(rows)} records to sheet")
            return len(rows), []
        except Exception as e:
            logger.warning(f"Sheet save attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff

    logger.error(f"Failed to save {len(rows)} records after {max_retries} attempts")
    return 0, data_list


# ============================================================================
# Background Task Processing
# ============================================================================
async def process_single_file(
    filename: str,
    content: bytes,
    content_type: str,
    handler,
    api_key: str,
    task_id: str,
    file_index: int
) -> FileResult:
    """Process a single file and return the result."""
    try:
        # Update status to processing (with lock)
        async with task_storage_lock:
            if task_id in task_storage:
                task_storage[task_id]["results"][file_index]["status"] = "processing"
                task_storage[task_id]["updated_at"] = datetime.now().isoformat()

        # Encode to base64
        img_b64 = base64.b64encode(content).decode()

        # Call AI model with retry
        data = await call_with_retry(handler, img_b64, content_type, api_key)

        # Validate extracted data
        data = validate_expense_data(data)

        result = FileResult(
            filename=filename,
            status="success",
            data=data,
            sheet_saved=False  # Will be updated after batch save
        )

        logger.info(f"Successfully processed: {filename}")
        return result

    except ValueError as e:
        logger.warning(f"Validation error for {filename}: {e}")
        return FileResult(
            filename=filename,
            status="failed",
            error=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error processing {filename}: {e}")
        return FileResult(
            filename=filename,
            status="failed",
            error="處理時發生錯誤，請稍後再試"
        )


async def process_files_background(
    task_id: str,
    files_data: List[tuple],  # [(filename, content, content_type), ...]
    model: ModelType,
    api_key: str
):
    """
    Background task to process files in batches.
    Updates task_storage with progress (thread-safe).
    """
    try:
        async with task_storage_lock:
            task_storage[task_id]["status"] = TaskStatus.PROCESSING
            task_storage[task_id]["updated_at"] = datetime.now().isoformat()

        handler = MODEL_HANDLERS.get(model)
        total_files = len(files_data)
        successful_data = []  # Collect successful results for batch sheet save

        # Process in batches
        for batch_start in range(0, total_files, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_files)
            batch = files_data[batch_start:batch_end]

            # Create tasks for this batch
            tasks = []
            for i, (filename, content, content_type) in enumerate(batch):
                file_index = batch_start + i
                tasks.append(
                    process_single_file(
                        filename, content, content_type,
                        handler, api_key, task_id, file_index
                    )
                )

            # Process batch concurrently
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Update results (with lock)
            async with task_storage_lock:
                for i, result in enumerate(batch_results):
                    file_index = batch_start + i
                    if isinstance(result, Exception):
                        task_storage[task_id]["results"][file_index] = FileResult(
                            filename=files_data[file_index][0],
                            status="failed",
                            error=str(result)
                        ).model_dump()
                        task_storage[task_id]["failed"] += 1
                    else:
                        task_storage[task_id]["results"][file_index] = result.model_dump()
                        if result.status == "success":
                            task_storage[task_id]["successful"] += 1
                            successful_data.append(result.data)
                        else:
                            task_storage[task_id]["failed"] += 1

                    task_storage[task_id]["processed"] += 1

                task_storage[task_id]["updated_at"] = datetime.now().isoformat()

            # Delay between batches to avoid rate limiting
            if batch_end < total_files:
                await asyncio.sleep(BATCH_DELAY)

        # Batch save to Google Sheet (with retry)
        if successful_data:
            saved_count, failed_items = batch_save_to_sheet(successful_data)
            async with task_storage_lock:
                if saved_count > 0:
                    # Mark all successful results as sheet_saved
                    for result in task_storage[task_id]["results"]:
                        if result["status"] == "success":
                            result["sheet_saved"] = True
                    logger.info(f"Task {task_id}: Saved {saved_count} records to sheet")
                if failed_items:
                    logger.warning(f"Task {task_id}: Failed to save {len(failed_items)} records to sheet")

        async with task_storage_lock:
            task_storage[task_id]["status"] = TaskStatus.COMPLETED
            task_storage[task_id]["updated_at"] = datetime.now().isoformat()
        logger.info(f"Task {task_id} completed: {task_storage[task_id]['successful']}/{total_files} successful")

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        async with task_storage_lock:
            if task_id in task_storage:
                task_storage[task_id]["status"] = TaskStatus.FAILED
                task_storage[task_id]["updated_at"] = datetime.now().isoformat()


# ============================================================================
# Task Cleanup Background Job
# ============================================================================
async def cleanup_expired_tasks():
    """Periodically clean up expired tasks to prevent memory leaks."""
    while True:
        await asyncio.sleep(3600)  # Run every hour

        now = datetime.now()
        expired_tasks = []

        async with task_storage_lock:
            for task_id, task in list(task_storage.items()):
                try:
                    created = datetime.fromisoformat(task["created_at"])
                    # Only clean up completed/failed tasks older than TTL
                    if (now - created > timedelta(hours=TASK_TTL_HOURS) and
                            task["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED)):
                        expired_tasks.append(task_id)
                except Exception:
                    pass

            # Also clean up if we have too many tasks
            while len(task_storage) > MAX_STORED_TASKS:
                # Remove oldest completed/failed task
                for task_id, task in list(task_storage.items()):
                    if task["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                        expired_tasks.append(task_id)
                        break
                else:
                    break

            for task_id in expired_tasks:
                if task_id in task_storage:
                    del task_storage[task_id]

        if expired_tasks:
            logger.info(f"Cleaned up {len(expired_tasks)} expired tasks")


@app.on_event("startup")
async def startup_event():
    """Start background cleanup task on app startup."""
    asyncio.create_task(cleanup_expired_tasks())
    logger.info("Started task cleanup background job")


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
    return {"status": "ok", "version": "3.1.0", "max_files": MAX_FILES}


@app.post("/api/auth", response_model=AuthResponse)
async def authenticate(
    x_access_code: Optional[str] = Header(None, alias="X-Access-Code"),
):
    """Verify access code and return available models."""
    if not verify_access_code(x_access_code):
        raise HTTPException(status_code=401, detail="訪問碼錯誤")

    available = get_available_models()
    if not available:
        raise HTTPException(status_code=503, detail="目前沒有可用的 AI 模型，請聯繫管理員")

    return AuthResponse(
        success=True,
        message="驗證成功",
        available_models=available,
        max_files=MAX_FILES
    )


@app.post("/api/process")
async def process(
    files: List[UploadFile] = File(..., description="上傳的圖片檔案"),
    model: ModelType = Query(ModelType.CLAUDE, description="AI 模型選擇"),
    x_access_code: Optional[str] = Header(None, alias="X-Access-Code"),
    background_tasks: BackgroundTasks = None,
):
    """
    Process uploaded expense claim images.
    Returns immediately with a task_id for tracking progress.

    - **files**: One or more image files (JPEG, PNG, GIF, WebP), max 100 files
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

    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多處理 {MAX_FILES} 個檔案")

    # Validate and read all files
    files_data = []
    total_size = 0

    for file in files:
        validate_image_file(file)
        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"檔案 {file.filename} 過大 ({len(content) / 1024 / 1024:.1f}MB)，上限 10MB"
            )

        total_size += len(content)
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(status_code=400, detail="總檔案大小超過 100MB 上限")

        files_data.append((file.filename, content, file.content_type))

    # Create task
    task_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    task_storage[task_id] = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "total": len(files_data),
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "results": [
            {"filename": f[0], "status": "pending", "data": None, "error": None, "sheet_saved": False}
            for f in files_data
        ],
        "spreadsheet_url": SPREADSHEET_URL,
        "created_at": now,
        "updated_at": now
    }

    logger.info(f"Created task {task_id} for {len(files_data)} files with model: {model}")

    # Start background processing
    background_tasks.add_task(
        process_files_background,
        task_id,
        files_data,
        model,
        api_key
    )

    return {
        "task_id": task_id,
        "status": "pending",
        "total": len(files_data),
        "message": f"已開始處理 {len(files_data)} 個檔案"
    }


@app.get("/api/task/{task_id}", response_model=TaskResponse)
async def get_task_status(
    task_id: str,
    x_access_code: Optional[str] = Header(None, alias="X-Access-Code"),
):
    """
    Get the status of a processing task.

    - **task_id**: The task ID returned from /api/process
    """
    if not verify_access_code(x_access_code):
        raise HTTPException(status_code=401, detail="訪問碼錯誤")

    async with task_storage_lock:
        if task_id not in task_storage:
            raise HTTPException(status_code=404, detail="找不到該任務")

        task = task_storage[task_id]
        # Return a copy to avoid external mutation
        return TaskResponse(
            task_id=task["task_id"],
            status=task["status"],
            total=task["total"],
            processed=task["processed"],
            successful=task["successful"],
            failed=task["failed"],
            results=[FileResult(**r) for r in task["results"]],
            spreadsheet_url=task["spreadsheet_url"],
            created_at=task["created_at"],
            updated_at=task["updated_at"]
        )


@app.delete("/api/task/{task_id}")
async def delete_task(
    task_id: str,
    x_access_code: Optional[str] = Header(None, alias="X-Access-Code"),
):
    """Delete a completed task from storage."""
    if not verify_access_code(x_access_code):
        raise HTTPException(status_code=401, detail="訪問碼錯誤")

    async with task_storage_lock:
        if task_id not in task_storage:
            raise HTTPException(status_code=404, detail="找不到該任務")

        task = task_storage[task_id]
        # Prevent deletion of in-progress tasks
        if task["status"] in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            raise HTTPException(
                status_code=400,
                detail="無法刪除進行中的任務"
            )

        del task_storage[task_id]
    return {"success": True, "message": "任務已刪除"}


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

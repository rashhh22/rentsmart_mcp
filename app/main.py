"""FastAPI application implementing the RentSmart MCP service.

The service exposes several endpoints required by the Puch AI platform:

* `/health` – A simple heartbeat endpoint.
* `/validate` – Checks a bearer token and returns a dummy phone number.
* `/tool/generate_agreement` – Fills a rental agreement template and returns a
  publicly accessible PDF link along with metadata.
* `/tool/generate_rent_receipt` – Fills a rent receipt template and returns
  a PDF link and metadata.
* `/tool/stamp_duty_info` – Provides basic stamp duty information for
  different Indian states.

Internally the service reads text templates from the `templates` directory,
performs simple string substitution and then creates a minimal PDF file using
custom logic.  This avoids the need for heavy PDF dependencies and keeps the
entire project self‑contained.
"""

# app/main.py
import os
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
from fpdf import FPDF

# -------------------------------------------------------------------
# Config & paths
# -------------------------------------------------------------------
VALID_TOKEN = os.environ.get("RENTSMART_VALID_TOKEN", "something_secret")
BASE_DIR = Path(__file__).resolve().parent

FILES_DIR = BASE_DIR.parent / "files"
AGREEMENT_DIR = FILES_DIR / "agreements"
RECEIPT_DIR = FILES_DIR / "receipts"
AGREEMENT_DIR.mkdir(parents=True, exist_ok=True)
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)

STAMP_DUTY_DATA: Dict[str, Dict[str, str]] = {
    "Karnataka": {"stamp_duty": "1% of annual rent + deposit", "link": "https://kaverionline.karnataka.gov.in/"},
    "Maharashtra": {"stamp_duty": "0.25% of annual rent + deposit", "link": "https://gras.mahakosh.gov.in/"},
    "Tamil Nadu": {"stamp_duty": "1% of annual rent", "link": "https://tnreginet.gov.in/"},
    "Delhi": {"stamp_duty": "2% of average annual rent", "link": "https://www.shcilestamp.com/"},
}

# -------------------------------------------------------------------
# App (single instance)
# -------------------------------------------------------------------
app = FastAPI(title="RentSmart MCP", version="0.1.0")

# CORS & static files
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.mount("/files", StaticFiles(directory=str(FILES_DIR)), name="files")

# Root routes so load balancers / Puch won’t 404 on connect
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <h2>RentSmart MCP</h2>
    <ul>
      <li><a href="/health">/health</a></li>
      <li><a href="/tools">/tools</a></li>
    </ul>
    """

@app.head("/")
async def head_root():
    return Response(status_code=200)

@app.options("/{rest_of_path:path}")
async def options_any(rest_of_path: str):
    return Response(status_code=204)
  # Root POST — some clients (incl. Puch) hit POST / during handshake
@app.post("/")
async def post_root():
    return {"status": "ok"}


# -------------------------------------------------------------------
# Helpers & models
# -------------------------------------------------------------------
def format_rupee(value: str) -> str:
    try:
        return f"{int(str(value).replace(',', '').strip()):,}"
    except Exception:
        return value

def generate_verification_code(length: int = 6) -> str:
    return uuid.uuid4().hex[:length].upper()

def fill_template(template_path: Path, context: Dict[str, str]) -> str:
    template = template_path.read_text(encoding="utf-8")
    return template.format_map(context)

def create_pdf_from_text(text: str, file_path: Path) -> None:
    text = text.replace("₹", "Rs.")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for line in text.splitlines():
        pdf.cell(0, 10, txt=line, ln=1)
    pdf.output(str(file_path))

class AgreementRequest(BaseModel):
    landlord: str; tenant: str; address: str
    rent: str; deposit: str; start_date: str; duration_months: str
    @validator("rent", "deposit", pre=True)
    def _to_str(cls, v): return str(v)

class ReceiptRequest(BaseModel):
    landlord: str; tenant: str; address: str
    amount: str; month: str; year: str
    payment_mode: Optional[str] = ""; remarks: Optional[str] = ""
    @validator("amount", pre=True)
    def _to_str_amount(cls, v): return str(v)

class StampDutyRequest(BaseModel):
    state: Optional[str] = None

# -------------------------------------------------------------------
# Required endpoints
# -------------------------------------------------------------------
@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}

VALID_TOKEN = os.environ.get("RENTSMART_VALID_TOKEN", "something_secret")

@app.post("/validate")
async def validate(request: Request):
    # 1) Check for Bearer token in header
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()

    # 2) If not present, fallback to ?token= query param
    if not token:
        token = request.query_params.get("token", "")

    # 3) Compare against expected token
    if token != VALID_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"phone": "919999999999"}

@app.get("/tools")
def list_tools():
    return {
        "server_id": "rentsmart-mcp",
        "name": "RentSmart MCP",
        "version": "1.0",
        "tools": [
            {"name": "validate", "method": "POST", "path": "/validate",
             "description": "Validate bearer token and return the caller phone.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "generate_agreement", "method": "POST", "path": "/tool/generate_agreement",
             "description": "Generate a rental agreement PDF.",
             "input_schema": {"type": "object",
               "required": ["landlord","tenant","address","rent","deposit","start_date","duration_months"],
               "properties": {"landlord":{"type":"string"},"tenant":{"type":"string"},"address":{"type":"string"},
                              "rent":{"type":"string"},"deposit":{"type":"string"},"start_date":{"type":"string"},
                              "duration_months":{"type":"string"}}}},
            {"name": "generate_rent_receipt", "method": "POST", "path": "/tool/generate_rent_receipt",
             "description": "Generate a monthly rent receipt.",
             "input_schema": {"type": "object",
               "required": ["landlord","tenant","address","amount","month","year"],
               "properties": {"landlord":{"type":"string"},"tenant":{"type":"string"},"address":{"type":"string"},
                              "amount":{"type":"string"},"month":{"type":"string"},"year":{"type":"string"},
                              "payment_mode":{"type":"string"},"remarks":{"type":"string"}}}}
        ]
    }

def _gen_response(request: Request, subdir: str, filename: str, doc_id: str, code: str) -> Dict[str, str]:
    base = str(request.base_url).rstrip("/")
    link = f"{base}/files/{subdir}/{filename}"
    return {"answer": f"Your document is ready: {link}", "link": link, "id": doc_id, "verification_code": code}

@app.post("/tool/generate_agreement")
async def generate_agreement(req: AgreementRequest, request: Request) -> Dict[str, str]:
    doc_id = uuid.uuid4().hex[:8]
    code = generate_verification_code()
    ctx = {"landlord": req.landlord, "tenant": req.tenant, "address": req.address,
           "rent": format_rupee(req.rent), "deposit": format_rupee(req.deposit),
           "start_date": req.start_date, "duration_months": req.duration_months,
           "id": doc_id, "verification_code": code}
    filled = fill_template(BASE_DIR / "templates" / "agreement_template.txt", ctx)
    filename = f"agreement_{doc_id}.pdf"
    create_pdf_from_text(filled, AGREEMENT_DIR / filename)
    return _gen_response(request, "agreements", filename, doc_id, code)

@app.post("/tool/generate_rent_receipt")
async def generate_rent_receipt(req: ReceiptRequest, request: Request) -> Dict[str, str]:
    doc_id = uuid.uuid4().hex[:8]
    code = generate_verification_code()
    ctx = {"landlord": req.landlord, "tenant": req.tenant, "address": req.address,
           "amount": format_rupee(req.amount), "month": req.month, "year": req.year,
           "payment_mode": req.payment_mode or "", "remarks": req.remarks or "",
           "id": doc_id, "verification_code": code}
    filled = fill_template(BASE_DIR / "templates" / "receipt_template.txt", ctx)
    filename = f"receipt_{doc_id}.pdf"
    create_pdf_from_text(filled, RECEIPT_DIR / filename)
    return _gen_response(request, "receipts", filename, doc_id, code)

@app.post("/tool/stamp_duty_info")
async def stamp_duty_info(req: StampDutyRequest) -> Dict[str, object]:
    if req.state:
        key = next((k for k in STAMP_DUTY_DATA if k.lower() == req.state.lower()), None)
        if not key:
            return {"answer": f"Sorry, I don’t have stamp duty information for {req.state}."}
        return {"answer": f"Stamp duty information for {key}: {STAMP_DUTY_DATA[key]['stamp_duty']}.",
                "data": {key: STAMP_DUTY_DATA[key]}}
    return {"answer": "Stamp duty information for available states.", "data": STAMP_DUTY_DATA}

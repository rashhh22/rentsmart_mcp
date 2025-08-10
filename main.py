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

import os
import uuid
import random
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# A simple bearer token used for validation.  In production this should be
# replaced with a secure secret or integrated with your authentication
# mechanism.
VALID_TOKEN = os.environ.get("RENTSMART_VALID_TOKEN", "your_test_token")

# Base directory where this file lives.  We derive other paths relative to
# this location.
BASE_DIR = Path(__file__).resolve().parent

# Directory to store generated files.  The FastAPI StaticFiles middleware
# serves files from this directory at the `/files` route.
FILES_DIR = BASE_DIR.parent / "files"
AGREEMENT_DIR = FILES_DIR / "agreements"
RECEIPT_DIR = FILES_DIR / "receipts"

# Ensure directories exist at import time.  `exist_ok=True` avoids raising
# errors if the directories already exist.
AGREEMENT_DIR.mkdir(parents=True, exist_ok=True)
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)

# Stamp duty data for demonstration.  Modify or extend this dictionary to
# include all states you care about.  Each entry should contain a short
# description of the stamp duty calculation and optionally a URL for more
# information.
STAMP_DUTY_DATA: Dict[str, Dict[str, str]] = {
    "Karnataka": {
        "stamp_duty": "1% of annual rent + deposit",
        "link": "https://kaverionline.karnataka.gov.in/",
    },
    "Maharashtra": {
        "stamp_duty": "0.25% of annual rent + deposit",
        "link": "https://gras.mahakosh.gov.in/",
    },
    "Tamil Nadu": {
        "stamp_duty": "1% of annual rent",
        "link": "https://tnreginet.gov.in/",
    },
    "Delhi": {
        "stamp_duty": "2% of average annual rent",
        "link": "https://www.shcilestamp.com/",
    },
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def format_rupee(value: str) -> str:
    """Format a numeric string with commas for readability.

    Although Indian numbering uses a different comma grouping, this function
    performs a simple western grouping (e.g. 15000 → 15,000).  If the input
    cannot be converted to an integer it is returned unchanged.

    Args:
        value: A numeric string.
    Returns:
        The string with commas inserted.
    """
    try:
        # Remove existing commas and whitespace
        cleaned = str(value).replace(",", "").strip()
        number = int(cleaned)
        return f"{number:,}"
    except Exception:
        # Fall back to the original value if conversion fails
        return value


def generate_verification_code(length: int = 6) -> str:
    """Generate a simple uppercase hexadecimal verification code."""
    return uuid.uuid4().hex[:length].upper()


def fill_template(template_path: Path, context: Dict[str, str]) -> str:
    """Read a template file and fill it using the provided context.

    Args:
        template_path: Path to the template file.
        context: Mapping of placeholder names to replacement values.
    Returns:
        The filled template as a single string.
    """
    template = template_path.read_text(encoding="utf-8")
    try:
        return template.format_map(context)
    except KeyError as exc:
        missing = exc.args[0]
        raise ValueError(f"Missing placeholder in context: {missing}") from exc


from fpdf import FPDF

def create_pdf_from_text(text: str, file_path: Path) -> None:
    # Sanitize rupee symbols just in case
    text = text.replace("₹", "Rs.")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for line in text.splitlines():
        pdf.cell(0, 10, txt=line, ln=1)

    pdf.output(str(file_path))

# ---------------------------------------------------------------------------
# Pydantic models for requests
# ---------------------------------------------------------------------------

class AgreementRequest(BaseModel):
    landlord: str
    tenant: str
    address: str
    rent: str
    deposit: str
    start_date: str
    duration_months: str

    @validator("rent", "deposit", pre=True)
    def ensure_numeric_strings(cls, v):  # noqa: D417
        # Accept numeric values and strings.  Convert numbers to strings.
        return str(v)


class ReceiptRequest(BaseModel):
    landlord: str
    tenant: str
    address: str
    amount: str
    month: str
    year: str
    payment_mode: str
    remarks: str

    @validator("amount", pre=True)
    def ensure_amount_string(cls, v):  # noqa: D417
        return str(v)


class StampDutyRequest(BaseModel):
    state: Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

app = FastAPI(title="RentSmart MCP", version="0.1.0")

# Serve static files (generated PDFs) from the /files URL path
app.mount("/files", StaticFiles(directory=str(FILES_DIR)), name="files")


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/validate")
async def validate(request: Request) -> Dict[str, str]:
    """Validate the bearer token and return a dummy phone number.

    Puch AI calls this endpoint to verify that your MCP server is reachable
    and that the provided token is accepted.  If the token is invalid a 401
    error is returned.
    """
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if token != VALID_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Return any phone number you wish to associate with this token.  In a real
    # system you might derive the phone from the token or session.
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
             "input_schema": {"type":"object","properties":{}}},
            {"name": "generate_agreement", "method": "POST", "path": "/tool/generate_agreement",
             "description": "Generate a rental agreement PDF.",
             "input_schema": {"type":"object",
               "required":["landlord","tenant","address","rent","deposit","start_date","duration_months"],
               "properties":{
                 "landlord":{"type":"string"}, "tenant":{"type":"string"},
                 "address":{"type":"string"}, "rent":{"type":"string"},
                 "deposit":{"type":"string"}, "start_date":{"type":"string"},
                 "duration_months":{"type":"string"}}}},
            {"name":"generate_rent_receipt","method":"POST","path":"/tool/generate_rent_receipt",
             "description":"Generate a monthly rent receipt.",
             "input_schema":{"type":"object",
               "required":["landlord","tenant","address","amount","month","year"],
               "properties":{
                 "landlord":{"type":"string"},"tenant":{"type":"string"},
                 "address":{"type":"string"},"amount":{"type":"string"},
                 "month":{"type":"string"},"year":{"type":"string"},
                 "payment_mode":{"type":"string"},"remarks":{"type":"string"}}}}
        ]
    }



def _generate_response(request: Request, subdir: str, filename: str, id_: str, verification_code: str) -> Dict[str, str]:
    """Helper to assemble the JSON response for generated files."""
    base_url = str(request.base_url).rstrip("/")
    link = f"{base_url}/files/{subdir}/{filename}"
    return {
        "answer": f"Your document is ready: {link}",
        "link": link,
        "id": id_,
        "verification_code": verification_code,
    }


@app.post("/tool/generate_agreement")
async def generate_agreement(req: AgreementRequest, request: Request) -> Dict[str, str]:
    """Generate a rental agreement PDF based on user input."""
    # Generate identifiers
    doc_id = uuid.uuid4().hex[:8]
    verification_code = generate_verification_code()

    # Prepare context for the template
    context = {
        "landlord": req.landlord,
        "tenant": req.tenant,
        "address": req.address,
        "rent": format_rupee(req.rent),
        "deposit": format_rupee(req.deposit),
        "start_date": req.start_date,
        "duration_months": req.duration_months,
        "id": doc_id,
        "verification_code": verification_code,
    }

    # Fill template
    template_path = BASE_DIR / "templates" / "agreement_template.txt"
    filled = fill_template(template_path, context)

    # Generate PDF
    filename = f"agreement_{doc_id}.pdf"
    pdf_path = AGREEMENT_DIR / filename
    create_pdf_from_text(filled, pdf_path)

    # Build response
    return _generate_response(request, "agreements", filename, doc_id, verification_code)


@app.post("/tool/generate_rent_receipt")
async def generate_rent_receipt(req: ReceiptRequest, request: Request) -> Dict[str, str]:
    """Generate a rent receipt PDF based on user input."""
    doc_id = uuid.uuid4().hex[:8]
    verification_code = generate_verification_code()

    context = {
        "landlord": req.landlord,
        "tenant": req.tenant,
        "address": req.address,
        "amount": format_rupee(req.amount),
        "month": req.month,
        "year": req.year,
        "payment_mode": req.payment_mode,
        "remarks": req.remarks,
        "id": doc_id,
        "verification_code": verification_code,
    }

    template_path = BASE_DIR / "templates" / "receipt_template.txt"
    filled = fill_template(template_path, context)
    filename = f"receipt_{doc_id}.pdf"
    pdf_path = RECEIPT_DIR / filename
    create_pdf_from_text(filled, pdf_path)

    return _generate_response(request, "receipts", filename, doc_id, verification_code)


@app.post("/tool/stamp_duty_info")
async def stamp_duty_info(req: StampDutyRequest) -> Dict[str, object]:
    """Return stamp duty information for the requested state or all states."""
    if req.state:
        # Normalize state name for case‑insensitive lookup
        state_key = None
        for name in STAMP_DUTY_DATA:
            if name.lower() == req.state.lower():
                state_key = name
                break
        if not state_key:
            return {
                "answer": f"Sorry, I don’t have stamp duty information for {req.state}.",
            }
        data = STAMP_DUTY_DATA[state_key]
        return {
            "answer": f"Stamp duty information for {state_key}: {data['stamp_duty']}.",
            "data": {state_key: data},
        }
    # If no state provided, return all data
    return {
        "answer": "Stamp duty information for available states.",
        "data": STAMP_DUTY_DATA,
    }
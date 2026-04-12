"""FastAPI routes for model governance portal."""

import json
import os
from pathlib import Path
from typing import Any

import anthropic
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/models", tags=["models"])

# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

_REGISTRY_PATH = Path(__file__).parent.parent / "model_docs" / "registry.json"
_MDD_DIR = Path(__file__).parent.parent / "model_docs"
_PDF_DIR = Path(__file__).parent.parent / "model_docs" / "pdfs"
_ALLOWED_SUFFIXES = {".tex", ".md", ".pdf"}
_DOC_SEARCH_DIRS = (
    _MDD_DIR,
    _MDD_DIR / "latex",
    _MDD_DIR / "pdfs",
    _MDD_DIR / "xva",
)

# Models owned by front-office quant (Tanaka answers as owner/builder)
_TANAKA_MODELS = {"APEX-MDL-0004", "APEX-MDL-0005", "APEX-MDL-0006"}

# Allowlist populated lazily from registry.json
_VALID_MODEL_IDS: set[str] = set()


def _ensure_allowlist() -> None:
    if not _VALID_MODEL_IDS:
        registry = _load_registry()
        for m in registry.get("models", []):
            _VALID_MODEL_IDS.add(m["id"])


def _load_registry() -> dict[str, Any]:
    with _REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _get_model(model_id: str) -> dict[str, Any]:
    registry = _load_registry()
    for model in registry["models"]:
        if model["id"] == model_id:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")


def _resolve_doc_path(filename: str) -> Path:
    for base_dir in _DOC_SEARCH_DIRS:
        candidate = (base_dir / filename).resolve()
        if str(candidate).startswith(str(base_dir.resolve())) and candidate.exists():
            return candidate
    raise HTTPException(status_code=404, detail=f"Document file '{filename}' not found on disk")


def _resolve_pdf_path(model: dict[str, Any]) -> Path:
    short = model.get("short_name", model.get("short", ""))
    version = model.get("version", "")

    candidate_names: list[str] = []
    if short:
        if version:
            candidate_names.append(f"mdd_{short}_v{version}.pdf")
        candidate_names.append(f"mdd_{short}_v1.0.pdf")

    for doc_name in model.get("doc_files", []):
        stem, suffix = os.path.splitext(doc_name)
        if suffix.lower() in {".md", ".tex"}:
            candidate_names.append(f"{stem}.pdf")
        elif suffix.lower() == ".pdf":
            candidate_names.append(doc_name)

    seen: set[str] = set()
    for name in candidate_names:
        if name in seen:
            continue
        seen.add(name)
        try:
            return _resolve_doc_path(name)
        except HTTPException:
            continue

    raise HTTPException(status_code=404, detail=f"PDF not yet compiled for model '{model['id']}'")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/registry")
def get_registry() -> dict[str, Any]:
    """Return the full model registry JSON."""
    return _load_registry()


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """Return summary statistics across all registered models."""
    registry = _load_registry()
    models = registry["models"]

    by_status: dict[str, int] = {}
    open_findings_total = 0
    critical_open = 0
    tier1_count = 0

    for model in models:
        status = model.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        open_findings_total += model.get("open_findings", 0)

        if model.get("tier") == 1:
            tier1_count += 1

        for finding in model.get("findings", []):
            if finding.get("severity") == "critical" and finding.get("status") == "open":
                critical_open += 1

    return {
        "total_models": registry["metadata"]["total_models"],
        "by_status": by_status,
        "open_findings_total": open_findings_total,
        "critical_open": critical_open,
        "tier1_count": tier1_count,
    }


@router.get("/{model_id}")
def get_model(model_id: str) -> dict[str, Any]:
    """Return a single model record by ID (e.g. APEX-MDL-0014)."""
    return _get_model(model_id)


@router.get("/{model_id}/pdf")
def get_model_pdf(model_id: str) -> FileResponse:
    """Download the SR 11-7 Model Development Document PDF for a model."""
    model = _get_model(model_id)
    pdf_path = _resolve_pdf_path(model)
    pdf_filename = pdf_path.name
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_filename,
    )


@router.get("/{model_id}/findings")
def get_findings(model_id: str) -> list[dict[str, Any]]:
    """Return the findings list for a specific model."""
    model = _get_model(model_id)
    return model.get("findings", [])


@router.get("/{model_id}/doc/{filename}")
def get_doc(model_id: str, filename: str) -> FileResponse:
    """Serve a model document file (.tex, .md, or .pdf) for the given model."""
    # Validate model exists
    model = _get_model(model_id)

    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' is not permitted. Allowed: {sorted(_ALLOWED_SUFFIXES)}",
        )

    if filename not in model.get("doc_files", []):
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' is not registered for model '{model_id}'",
        )

    file_path = _resolve_doc_path(filename)

    media_type_map = {
        ".tex": "text/plain",
        ".md": "text/plain",
        ".pdf": "application/pdf",
    }

    return FileResponse(
        path=str(file_path),
        media_type=media_type_map.get(suffix, "application/octet-stream"),
        filename=filename,
    )


# ---------------------------------------------------------------------------
# Model Q&A — POST /api/models/chat
# ---------------------------------------------------------------------------

class ModelChatRequest(BaseModel):
    model_id: str
    question: str
    stream: bool = True


def _get_persona(model_id: str) -> tuple[str, str]:
    """Return (name, role_description) for the responding persona."""
    if model_id in _TANAKA_MODELS:
        return (
            "Dr. Yuki Tanaka",
            "Quant Researcher and model owner. You built this model and understand "
            "every implementation detail. Answer from a front-office quant perspective: "
            "focus on usage, calibration, assumptions, and practical implications. "
            "Be technically precise but accessible to risk managers.",
        )
    return (
        "Dr. Samuel Achebe",
        "Model Validation Officer. You are the independent validator who reviewed "
        "this model under SR 11-7. Answer from a second-line risk perspective: "
        "focus on validation findings, limitations, open issues, regulatory compliance, "
        "and compensating controls. Be rigorous and flag known weaknesses honestly.",
    )


def _load_mdd_content(model_card: dict) -> str:
    """Load the MDD markdown file for a model card. Returns empty string if not found."""
    short = model_card.get("short", "")
    if not short:
        return ""
    mdd_path = _MDD_DIR / f"mdd_{short}_v1.0.md"
    if mdd_path.exists():
        return mdd_path.read_text(encoding="utf-8")
    return ""


@router.get("/governance/registry")
async def model_registry_list():
    """Full SR 11-7 model governance registry (SQLite-backed lifecycle store)."""
    from infrastructure.governance.model_registry import model_registry
    return {
        "models": model_registry.get_all_models(),
        "summary": model_registry.get_risk_rating_summary(),
    }


@router.get("/governance/registry/capital-approved")
async def capital_approved_models():
    """Models approved for regulatory capital use (production + sign-off)."""
    from infrastructure.governance.model_registry import model_registry
    return {"models": model_registry.get_capital_approved_models()}


@router.get("/governance/registry/{model_id}")
async def get_model_record(model_id: str):
    """Single model record with full SR 11-7 fields."""
    from infrastructure.governance.model_registry import model_registry
    m = model_registry.get_model(model_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return m


@router.post("/governance/registry/{model_id}/validate")
async def validate_model(model_id: str, body: dict):
    """
    Advance model through validation gate.
    Body: {"validator": "Dr. Rebecca Chen", "findings": "...", "approved": true}
    """
    from infrastructure.governance.model_registry import model_registry
    result = model_registry.validate_model(
        model_id=model_id,
        validator=body.get("validator", ""),
        findings=body.get("findings", ""),
        approved=bool(body.get("approved", False)),
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return result


@router.post("/chat")
async def model_chat(req: ModelChatRequest):
    """
    Q&A on a model card. Streams SSE responses (text/event-stream).
    model_id must be in the registry allowlist — unknown IDs return 422.
    Persona: Tanaka (BSM/HW1F/LMM) or Achebe (all others).
    """
    _ensure_allowlist()
    if req.model_id not in _VALID_MODEL_IDS:
        raise HTTPException(status_code=422, detail=f"Unknown model_id: {req.model_id}")

    model_card = _get_model(req.model_id)
    persona_name, persona_desc = _get_persona(req.model_id)
    mdd_content = _load_mdd_content(model_card)

    system_prompt = f"""You are {persona_name}, {persona_desc}

MODEL CARD:
{json.dumps(model_card, indent=2)}

{"MDD DOCUMENT:" + chr(10) + mdd_content if mdd_content else ""}

Answer the user's question about this model. Be concise and accurate.
Do not invent information not present in the model card or MDD.
If you don't know something, say so clearly."""

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    async def generate():
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": req.question}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text, 'persona': persona_name})}\n\n"
            yield f"data: {json.dumps({'done': True, 'persona': persona_name})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

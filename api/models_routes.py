"""FastAPI routes for model governance portal."""

import json
import os
from pathlib import Path
from typing import Any, Iterator

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
_DOCS_DIR = Path(__file__).parent.parent / "model_docs" / "xva"
_ALLOWED_SUFFIXES = {".tex", ".md", ".pdf"}

# ---------------------------------------------------------------------------
# Model chat allowlist — loaded once at module level
# ---------------------------------------------------------------------------

_VALID_MODEL_IDS: set[str] = set()
_REGISTRY_DATA: list[dict] = []

def _load_allowlist() -> None:
    global _VALID_MODEL_IDS, _REGISTRY_DATA
    try:
        data = json.loads(_REGISTRY_PATH.read_text())
        _REGISTRY_DATA = data if isinstance(data, list) else data.get("models", [])
        _VALID_MODEL_IDS = {m["id"] for m in _REGISTRY_DATA if "id" in m}
    except Exception as exc:
        log.error("models.allowlist_load_failed", error=str(exc))

_load_allowlist()  # load at import time

# Multi-persona routing
_MODEL_PERSONA: dict[str, str] = {
    "APEX-MDL-0004": "Dr. Yuki Tanaka",  # BSM
    "APEX-MDL-0005": "Dr. Yuki Tanaka",  # HW1F
    "APEX-MDL-0006": "Dr. Yuki Tanaka",  # SOFR/LMM
}

def _get_persona(model_id: str) -> str:
    return _MODEL_PERSONA.get(model_id, "Dr. Samuel Achebe")


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

class ModelChatRequest(BaseModel):
    model_id: str
    question: str
    stream: bool = True


@router.post("/chat")
async def model_chat(req: ModelChatRequest):
    if req.model_id not in _VALID_MODEL_IDS:
        raise HTTPException(status_code=422, detail=f"Unknown model_id: {req.model_id!r}")

    persona = _get_persona(req.model_id)

    # Find model card
    model_card = next((m for m in _REGISTRY_DATA if m.get("id") == req.model_id), {})

    # Try to load MDD file
    mdd_content = ""
    short = model_card.get("short_name", req.model_id.lower()).lower()
    mdd_file = _REGISTRY_PATH.parent / f"mdd_{short}_v1.0.md"
    if mdd_file.exists():
        mdd_content = mdd_file.read_text()[:8000]  # cap at 8k chars

    # Build system prompt
    if persona == "Dr. Yuki Tanaka":
        role_desc = (
            "You are Dr. Yuki Tanaka, Quant Researcher at Apex Global Bank. "
            "You built this model and know it intimately. Answer from the perspective of "
            "the model builder: focus on the theory, calibration, practical usage, and assumptions. "
            "Be precise and technically confident."
        )
    else:
        role_desc = (
            "You are Dr. Samuel Achebe, Model Validation Officer at Apex Global Bank. "
            "You independently validate models under SR 11-7. Answer from the perspective of "
            "an independent validator: focus on limitations, open findings, regulatory compliance, "
            "and validation status. Be rigorous and critical."
        )

    system = f"""{role_desc}

MODEL CARD:
{json.dumps(model_card, indent=2)}

MODEL DEVELOPMENT DOCUMENT:
{mdd_content if mdd_content else "(MDD not yet available)"}
"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate() -> Iterator[str]:
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": req.question}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

def _load_registry() -> dict[str, Any]:
    with _REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _get_model(model_id: str) -> dict[str, Any]:
    registry = _load_registry()
    for model in registry["models"]:
        if model["id"] == model_id:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")


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

    file_path = (_DOCS_DIR / filename).resolve()
    if not str(file_path).startswith(str(_DOCS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Document file '{filename}' not found on disk")

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

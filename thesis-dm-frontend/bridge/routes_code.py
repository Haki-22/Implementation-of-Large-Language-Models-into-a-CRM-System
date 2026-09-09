"""The code tab: curated source files of the prototype and a question router over them.

The quick mode answers from a keyword router with a cited file; the model mode sends
the question and the snippet through ``utils.generation``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from common import ModelChoice, check_provider, provider_http_error, require_llm_calls_on
from utils.generation import generate_text
from utils.paths import THESIS_ROOT

router = APIRouter()


class CodeAskRequest(ModelChoice):
    """One question about the repository, optionally answered by a model over the snippet."""

    question: str
    file_id: str | None = None
    file_path: str | None = None
    """A tracked repository path to cite instead of the curated catalog (the file open in the browser)."""
    use_llm: bool = False


# ---------------------------------------------------------------------------
# The curated catalog
# ---------------------------------------------------------------------------


def _code_catalog() -> list[dict[str, Any]]:
    """Curated source map for the code tab."""
    return [
        {
            "id": "readme",
            "name": "README.md",
            "path": THESIS_ROOT / "README.md",
            "icon": "file-text",
            "max_lines": 90,
        },
        {
            "id": "uc01",
            "name": "UC-01 levels",
            "path": THESIS_ROOT / "ucs" / "uc01_personalization" / "levels.py",
            "icon": "file-code",
            "max_lines": 130,
        },
        {
            "id": "uc02",
            "name": "UC-02 pseudonymizer",
            "path": THESIS_ROOT / "ucs" / "uc02_pseudonymization" / "code" / "pseudonymizer.py",
            "icon": "file-code",
            "max_lines": 130,
        },
        {
            "id": "uc03",
            "name": "UC-03 MCP tools",
            "path": THESIS_ROOT / "ucs" / "uc03_mcp_privacy" / "tools.py",
            "icon": "file-code",
            "max_lines": 130,
        },
        {
            "id": "uc04",
            "name": "UC-04 arena",
            "path": THESIS_ROOT / "ucs" / "uc04_matchmaker" / "arena.py",
            "icon": "file-code",
            "max_lines": 180,
        },
        {
            "id": "bridge",
            "name": "Frontend bridge",
            "path": THESIS_ROOT / "thesis-dm-frontend" / "bridge" / "app.py",
            "icon": "server",
            "max_lines": 180,
        },
    ]


def _code_catalog_by_id() -> dict[str, dict[str, Any]]:
    """The curated catalog rows indexed by their ``id``."""
    return {row["id"]: row for row in _code_catalog()}


def _source_snippet(path: Path, *, start: int = 1, max_lines: int = 120) -> str:
    """A bounded, numbered snippet of a file inside the thesis tree."""
    try:
        path.resolve().relative_to(THESIS_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"path_outside_thesis: {path}") from exc
    if not path.exists():
        return f"# Missing file: {path.relative_to(THESIS_ROOT)}"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start_idx = max(0, start - 1)
    selected = lines[start_idx : start_idx + max_lines]
    numbered = [f"{start_idx + i + 1:>4}  {line}" for i, line in enumerate(selected)]
    if len(lines) > start_idx + max_lines:
        numbered.append("   …  [snippet shortened]")
    return "\n".join(numbered)


def _code_file_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Render one catalog row into the file payload the page displays (name, path, snippet)."""
    path = Path(row["path"])
    return {
        "id": row["id"],
        "name": row["name"],
        "path": str(path.relative_to(THESIS_ROOT)),
        "icon": row["icon"],
        "kind": path.suffix.lstrip(".") or "text",
        "snippet": _source_snippet(path, max_lines=int(row["max_lines"])),
    }


# ---------------------------------------------------------------------------
# The keyword router
# ---------------------------------------------------------------------------


def _rules() -> list[tuple[tuple[str, ...], str, str]]:
    """Keyword -> cited file -> a short answer; every count in it is read from the registry."""
    from ucs.uc01_personalization import levels
    from ucs.uc03_mcp_privacy import config as uc03_config
    from ucs.uc03_mcp_privacy.tools import TOOL_NAMES
    from ucs.uc04_matchmaker import arms as arm_registry
    from ucs.uc04_matchmaker.arms import model as model_registry

    return [
        (
            ("uc-04", "uc04", "arena", "aréna", "doporu", "matchmaker", "hit@k", "hr@"),
            "uc04",
            f"UC-04 běží přes arénu v <b>ucs/uc04_matchmaker/arena.py</b>: {len(arm_registry.ARMS)} "
            "klasických ramen pojmenovaných podle metody, dva protokoly (celý katalog, 1 + 100 "
            "vzorkovaných), dvě větve (en, cs); každý běh zapíše složku pod <code>eval/runs/</code> "
            f"s kartou. Modelových metod je {len(model_registry.MODEL_ARMS)} v <b>arms/model/</b>, "
            "běží přes <code>model_arena.py</code>.",
        ),
        (
            ("pseudonym", "anonym", "pii", "mask", "odmask", "iban", "ičo", "email"),
            "uc02",
            "UC-02 je v <b>ucs/uc02_pseudonymization/code/pseudonymizer.py</b>: pravidlová vrstva "
            "s kontrolními součty pro formátové identifikátory, nad ní český NER, tokeny "
            "<code>&lt;TYP_N&gt;</code> a lokální mapa pro obnovu.",
        ),
        (
            ("mcp", "tool", "nástroj", "audit", "kontakt", "poznám", "hlas", "whisper"),
            "uc03",
            f"UC-03 nástroje jsou v <b>ucs/uc03_mcp_privacy/tools.py</b> ({len(TOOL_NAMES)} nástrojů, "
            f"{len(uc03_config.SECURITY_PROFILES)} bezpečnostní profily). Model je volá přes MCP, "
            "server obnovuje tokeny UC-02 při zápisu a každé volání řetězí do auditního logu.",
        ),
        (
            ("uc-01", "uc01", "personaliz", "vokativ", "ocean", "zpráv", "žebřík", "level"),
            "uc01",
            f"Žebřík UC-01 je v <b>ucs/uc01_personalization/levels.py</b>: {len(levels.LADDER)} příček "
            "od šablony po hyperpersonalizaci, každá jmenuje sloty, které potřebuje; prompt skládá "
            "<code>build_prompt</code>, zprávu soudí pravidlový soudce v <code>judge.py</code>.",
        ),
        (
            ("bridge", "most", "frontend", "stránk", "job", "přepínač", "switch"),
            "bridge",
            "Most je ve <b>thesis-dm-frontend/bridge/app.py</b> a modulech <code>routes_*.py</code>: "
            "každá cesta volá tutéž funkci jako CLI, dlouhé běhy jsou joby (<code>jobs.py</code>), "
            "každé volání modelu hlídá přepínač <code>THESIS_LLM_CALLS</code>.",
        ),
    ]


def _match_code_question(question: str) -> dict[str, str]:
    """Match ``question`` against the keyword rules, falling back to the README summary."""
    q = question.lower()
    for keywords, file_id, answer in _rules():
        if any(word in q for word in keywords):
            return {"file": file_id, "answer": answer}
    return {
        "file": "readme",
        "answer": (
            "Základní mapa prototypu je v <b>README.md</b>: sdílený substrát, čtyři balíčky "
            "use-casů, generační wrappery a demo stránka."
        ),
    }


async def _generate_code_answer(
    *,
    question: str,
    file_payload: dict[str, Any],
    provider: str,
    model: str | None,
    tier: str | None,
) -> str:
    """Ask the model to answer ``question`` about ``file_payload``'s snippet, in Czech."""
    system_prompt = (
        "Jsi technický asistent pro obhajobu diplomové práce. Odpovídej česky, stručně a věcně. "
        "Vysvětluj jen to, co lze opřít o dodaný výřez souboru. Pokud výřez nestačí, řekni přesně, "
        "co z něj není vidět. Neuváděj neověřené detaily mimo kontext."
    )
    user_prompt = (
        f"Dotaz uživatele:\n{question}\n\n"
        f"Citovaný soubor: {file_payload['path']}\n\n"
        f"Výřez souboru:\n```{file_payload['kind']}\n{file_payload['snippet']}\n```\n\n"
        "Vrať odpověď jako krátké HTML-safe odstavce bez Markdown tabulek. "
        "Můžeš použít <b>...</b> a <code>...</code>, ale nevkládej script ani style."
    )
    text = await generate_text(
        user_prompt,
        provider=provider,
        system_prompt=system_prompt,
        model=model,
        tier=tier,
        timeout=180,
    )
    return text.strip() or "(model vrátil prázdnou odpověď)"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/code/files")
def code_files() -> dict[str, Any]:
    """The curated source files of the code tab."""
    return {
        "files": [_code_file_payload(row) for row in _code_catalog()],
        "source": str(THESIS_ROOT),
        "backend": "curated real source snippets",
    }


@router.post("/code/ask")
async def code_ask(req: CodeAskRequest) -> dict[str, Any]:
    """Answer a code question with a cited file: keyword router, or a model over the snippet."""
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="empty question")
    match = _match_code_question(question)
    catalog = _code_catalog_by_id()
    if req.file_path:
        from routes_repo import read_repo_file

        repo_file = read_repo_file(req.file_path, max_bytes=60_000)
        lines = (repo_file.get("content") or "").splitlines()[:200]
        file_payload = {
            "id": "repo:" + repo_file["path"],
            "name": repo_file["name"],
            "path": repo_file["path"],
            "icon": "file-code",
            "kind": repo_file["language"],
            "snippet": "\n".join(f"{i + 1:>4}  {line}" for i, line in enumerate(lines)),
        }
    else:
        file_row = catalog.get(req.file_id or "") or catalog[match["file"]]
        file_payload = _code_file_payload(file_row)
    if not req.use_llm:
        return {
            "answer": match["answer"],
            "file": file_payload,
            "question": question,
            "backend": "keyword router over curated real source snippets",
            "used_llm": False,
        }
    check_provider(req.provider)
    require_llm_calls_on(req.provider)
    started = time.perf_counter()
    try:
        answer = await _generate_code_answer(
            question=question,
            file_payload=file_payload,
            provider=req.provider,
            model=req.model,
            tier=req.tier,
        )
    except Exception as exc:  # noqa: BLE001
        raise provider_http_error(exc, prefix="code_generation_failed") from exc
    return {
        "answer": answer,
        "file": file_payload,
        "question": question,
        "backend": f"LLM generation via utils.generation · {req.provider}",
        "used_llm": True,
        "provider": req.provider,
        "model": req.model,
        "tier": req.tier,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }

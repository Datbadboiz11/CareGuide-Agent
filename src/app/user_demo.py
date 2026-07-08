from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from careguide.graph.careguide_graph import CareGuideGraph


STATIC_DIR = Path(__file__).resolve().parent / "static" / "user"


class ChatMessage(BaseModel):

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AnalyzeRequest(BaseModel):

    messages: list[ChatMessage] = Field(min_length=1, max_length=24)


app = FastAPI(title="CareGuide User Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@lru_cache(maxsize=1)
def get_graph() -> CareGuideGraph:
    return CareGuideGraph(retrieval_mode="hybrid")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    user_turns = [message.content.strip() for message in payload.messages if message.role == "user"]
    conversation_input = "\n".join(user_turns[-6:]).strip()
    state = get_graph().run(conversation_input)
    final_output = state.get("final_output", {})
    return {
        "input": conversation_input,
        "final_output": final_output,
        "parsed": state.get("parsed").model_dump(mode="json") if state.get("parsed") else None,
        "expanded_terms": state.get("expanded_terms", []),
        "retrieval_titles": [
            hit.title for hit in state.get("answer_context", [])
        ],
    }

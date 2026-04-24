"""
Router de chat con streaming SSE (Server-Sent Events).
El frontend recibe tokens uno a uno, igual que ChatGPT.
"""
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from ..core.auth import get_current_user
from ..graph.agent import build_agent

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{role: "user"|"assistant", content: "..."}]


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Endpoint de chat con streaming SSE.
    Devuelve tokens del LLM a medida que se generan.

    Formato SSE:
        data: {"type": "token", "content": "Hola"}
        data: {"type": "tool_start", "tool": "consultar_proyectos"}
        data: {"type": "tool_end", "tool": "consultar_proyectos"}
        data: {"type": "done"}
    """
    token = _extract_token_from_user(user)
    if not token:
        raise HTTPException(status_code=401, detail="No se pudo obtener el token")

    agent = build_agent(token)

    # Construir historial de mensajes
    from langchain_core.messages import HumanMessage, AIMessage
    messages = []
    for msg in body.history[-10:]:  # últimos 10 mensajes para contexto
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=body.message))

    async def event_generator():
        try:
            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
            ):
                kind = event["event"]

                # Token del LLM
                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    yield _sse({"type": "token", "content": block["text"]})
                        elif isinstance(content, str):
                            yield _sse({"type": "token", "content": content})

                # Tool invocada
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    yield _sse({"type": "tool_start", "tool": tool_name})

                # Tool terminó
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "tool")
                    yield _sse({"type": "tool_end", "tool": tool_name})

            yield _sse({"type": "done"})

        except Exception as e:
            yield _sse({"type": "error", "content": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_token_from_user(user: dict) -> str | None:
    """
    El token original no está en el payload JWT decodificado.
    Lo pasamos via header X-Original-Token desde el middleware.
    Esta función es un placeholder; el token real viene del middleware.
    """
    return user.get("_raw_token")

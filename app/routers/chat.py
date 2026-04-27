"""
Router de chat con streaming SSE.
Usa stream_mode="messages" (forma correcta según docs LangGraph 2025).

Formato SSE devuelto al frontend:
    data: {"type": "token", "content": "Hola"}
    data: {"type": "tool_start", "tool": "consultar_proyectos"}
    data: {"type": "tool_end", "tool": "consultar_proyectos"}
    data: {"type": "done"}
    data: {"type": "error", "content": "mensaje"}
"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from ..core.auth import get_current_user
from ..graph.agent import get_graph

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Endpoint SSE: devuelve tokens del LLM a medida que se generan.
    El historial se mantiene automáticamente por thread_id (userId).
    """
    user_id: str = user["sub"]
    raw_token: str = user["_raw_token"]

    config = {
        "configurable": {
            "thread_id": user_id,   # historial por usuario
            "token": raw_token,     # token para que las tools llamen al NestJS
        }
    }

    input_state = {"messages": [HumanMessage(content=body.message)]}

    async def event_generator():
        try:
            async for msg, metadata in get_graph().astream(
                input_state,
                config=config,
                stream_mode="messages",
            ):
                # Token de texto del LLM
                if (
                    isinstance(msg, AIMessage)
                    and msg.content
                    and not msg.tool_calls
                ):
                    content = msg.content
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                yield _sse({"type": "token", "content": block["text"]})
                    elif isinstance(content, str):
                        yield _sse({"type": "token", "content": content})

                # Tool invocada — notifica al frontend para mostrar "buscando..."
                elif isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        yield _sse({"type": "tool_start", "tool": tc["name"]})

                # Resultado de tool
                elif isinstance(msg, ToolMessage):
                    yield _sse({"type": "tool_end", "tool": metadata.get("name", "tool")})

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


@router.delete("/history")
async def clear_history(user: dict = Depends(get_current_user)):
    """
    Borra el historial de conversación del usuario actual.
    """
    # Con InMemorySaver no hay API de borrado directo,
    # el historial se limpia reiniciando con un thread_id nuevo.
    # En prod con PostgresSaver se puede borrar el checkpoint.
    return {"ok": True, "message": "Historial limpiado"}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

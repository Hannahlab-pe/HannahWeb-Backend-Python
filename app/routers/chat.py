"""
Router de chat con streaming SSE.

Nota de implementación:
  Con nodos custom (async def + ainvoke) en Python 3.10, on_chat_model_stream
  y get_stream_writer no propagan el contexto correctamente. El patrón que
  funciona en este stack es on_chain_end del nodo llm_call via astream_events v2:
  el evento contiene el AIMessage final completo (sin tool_calls = respuesta final).

Formato SSE devuelto al frontend:
    data: {"type": "tool_start", "tool": "consultar_proyectos"}
    data: {"type": "tool_end",   "tool": "consultar_proyectos"}
    data: {"type": "token",      "content": "Hola..."}
    data: {"type": "done"}
    data: {"type": "error",      "content": "mensaje"}
"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage
from ..core.auth import get_current_user
from ..graph.agent import get_graph

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    user_id: str = user["sub"]
    raw_token: str = user["_raw_token"]
    thread_id = f"{user_id}:{body.session_id}" if body.session_id else user_id

    # Identidad del usuario extraída del JWT validado.
    # El rol viene firmado por NestJS — el usuario NO puede manipularlo desde el chat.
    config = {
        "configurable": {
            "thread_id": thread_id,
            "token": raw_token,
            "user_id": user_id,
            "user_rol": user.get("rol", "cliente"),
            "user_nombre": user.get("nombre", ""),
            "user_email": user.get("email", ""),
        }
    }

    input_state = {"messages": [HumanMessage(content=body.message)]}

    async def event_generator():
        try:
            tools_emitted: set[str] = set()  # evitar tool_start duplicados
            final_emitted = False             # evitar emitir la respuesta final 2 veces

            async for event in get_graph().astream_events(
                input_state,
                config=config,
                version="v2",
            ):
                kind = event["event"]
                name = event.get("name", "")
                meta_node = event.get("metadata", {}).get("langgraph_node", "")

                # ── Tool iniciada ──────────────────────────────────────────
                if kind == "on_tool_start":
                    key = f"{name}:{event.get('run_id','')}"
                    if key not in tools_emitted:
                        tools_emitted.add(key)
                        yield _sse({"type": "tool_start", "tool": name})

                # ── Tool terminada ─────────────────────────────────────────
                elif kind == "on_tool_end":
                    yield _sse({"type": "tool_end", "tool": name})

                # ── Respuesta final del LLM ────────────────────────────────
                # Con Python 3.10 + nodos custom, on_chat_model_stream no propaga.
                # on_chain_end del nodo llm_call contiene el AIMessage final completo.
                # final_emitted previene el duplicado (on_chain_end dispara 2 veces).
                elif kind == "on_chain_end" and meta_node == "llm_call" and not final_emitted:
                    output = event.get("data", {}).get("output", {})
                    msgs = output.get("messages", []) if isinstance(output, dict) else []
                    for msg in msgs:
                        if not isinstance(msg, AIMessage):
                            continue
                        if getattr(msg, "tool_calls", None):
                            continue  # LLM va a llamar una tool, no es respuesta final
                        content = msg.content
                        if not content:
                            continue
                        final_emitted = True
                        if isinstance(content, str):
                            yield _sse({"type": "token", "content": content})
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "")
                                    if text:
                                        yield _sse({"type": "token", "content": text})

            yield _sse({"type": "done"})

        except Exception as e:
            yield _sse({"type": "error", "content": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/history")
async def clear_history(user: dict = Depends(get_current_user)):
    return {"ok": True}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .core.auth import get_current_user
from .routers import chat
from .graph.nodes import build_system_prompt

app = FastAPI(
    title="Hannah AI",
    description="Backend de inteligencia artificial para Hannah Lab — FastAPI + LangGraph",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "hannah-ai"}


@app.get("/debug/me")
def debug_me(user: dict = Depends(get_current_user)):
    """Devuelve los claims del JWT y el system prompt construido. Borrar en producción estable."""
    claims = {k: v for k, v in user.items() if k != "_raw_token"}
    prompt = build_system_prompt(
        rol=user.get("rol", ""),
        nombre=user.get("nombre", ""),
        email=user.get("email", ""),
    )
    return {"claims": claims, "system_prompt_preview": prompt[:300]}

"""
Cliente HTTP para consultar el backend NestJS con el token del usuario.
Cada tool de LangGraph llama a estas funciones para obtener datos reales.
"""
import httpx
from ..core.config import settings


async def _get(path: str, token: str) -> dict | list:
    async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
        r = await client.get(path, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def get_proyectos(token: str) -> list:
    """Devuelve los proyectos del usuario autenticado."""
    return await _get("/proyectos/mis-proyectos", token)


async def get_tickets(token: str) -> list:
    """Devuelve los tickets del usuario autenticado."""
    return await _get("/tickets/mis-tickets", token)


async def get_reuniones(token: str) -> list:
    """Devuelve las reuniones del usuario autenticado."""
    return await _get("/reuniones/mis-reuniones", token)


async def get_perfil(token: str) -> dict:
    """Devuelve el perfil del usuario autenticado."""
    return await _get("/auth/perfil", token)

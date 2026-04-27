import httpx
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from ..core.config import settings


@tool
async def consultar_tickets(query: str, config: RunnableConfig) -> str:
    """
    Consulta los tickets de soporte del usuario: título, estado y prioridad.
    Úsala cuando el usuario pregunta por soporte, tickets, problemas reportados o incidencias.
    """
    token = config["configurable"].get("token", "")
    try:
        async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
            r = await client.get(
                "/tickets/mis-tickets",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            tickets = r.json()

        if not tickets:
            return "No hay tickets registrados para este usuario."

        abiertos = [t for t in tickets if t.get("estado") not in ("cerrado", "resuelto")]
        cerrados = [t for t in tickets if t.get("estado") in ("cerrado", "resuelto")]

        lines = [f"Total: {len(tickets)} ticket(s) — {len(abiertos)} abierto(s), {len(cerrados)} cerrado(s)."]

        if abiertos:
            lines.append("\n**Tickets abiertos:**")
            for t in abiertos[:8]:
                prioridad = t.get("prioridad", "—")
                estado = t.get("estado", "—")
                lines.append(f"- [{estado.upper()}] **{t['titulo']}** · prioridad: {prioridad}")

        if cerrados:
            lines.append(f"\n**Cerrados recientemente:** {len(cerrados)}")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Error al consultar tickets: {e.response.status_code}"
    except Exception as e:
        return f"Error inesperado al consultar tickets: {str(e)}"

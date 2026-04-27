import httpx
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from ..core.config import settings


@tool
async def consultar_proyectos(query: str, config: RunnableConfig) -> str:
    """
    Consulta los proyectos del usuario: nombre, estado, progreso y fecha de entrega.
    Úsala cuando el usuario pregunta por sus proyectos, avances, entregas o estado general.
    """
    token = config["configurable"].get("token", "")
    try:
        async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
            r = await client.get(
                "/proyectos/mis-proyectos",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            proyectos = r.json()

        if not proyectos:
            return "No hay proyectos activos para este usuario."

        lines = [f"Se encontraron {len(proyectos)} proyecto(s):"]
        for p in proyectos:
            estado = p.get("estado", "—")
            progreso = p.get("progreso", 0)
            fecha = p.get("fechaEntrega")
            fecha_str = fecha[:10] if fecha else "Sin fecha de entrega"
            lines.append(
                f"- **{p['nombre']}**: estado={estado}, progreso={progreso}%, entrega={fecha_str}"
            )
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Error al consultar proyectos: {e.response.status_code}"
    except Exception as e:
        return f"Error inesperado al consultar proyectos: {str(e)}"

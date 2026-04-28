import httpx
from datetime import datetime, timezone
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from ..core.config import settings


def _fmt_fecha(fecha_str: str) -> str:
    try:
        dt = datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y a las %H:%M")
    except Exception:
        return fecha_str


@tool
async def consultar_reuniones(query: str, config: RunnableConfig) -> str:
    """
    Consulta las reuniones: título, fecha, tipo, link de acceso y agenda.
    El alcance se ajusta automáticamente al rol del usuario:
    - admin/subadmin: ven todas las reuniones del sistema
    - cliente: ve solo sus propias reuniones
    """
    cfg = config.get("configurable", {})
    token = cfg.get("token", "")
    rol = cfg.get("user_rol", "cliente")
    endpoint = "/reuniones" if rol in ("admin", "subadmin") else "/reuniones/mis-reuniones"
    try:
        async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
            r = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            reuniones = r.json()

        if not reuniones:
            return "No hay reuniones programadas para este usuario."

        now = datetime.now(timezone.utc)
        proximas = []
        pasadas = []
        for r in reuniones:
            try:
                dt = datetime.fromisoformat(r["fecha"].replace("Z", "+00:00"))
                if dt > now:
                    proximas.append(r)
                else:
                    pasadas.append(r)
            except Exception:
                proximas.append(r)

        proximas.sort(key=lambda x: x["fecha"])
        pasadas.sort(key=lambda x: x["fecha"], reverse=True)

        lines = []

        if proximas:
            lines.append(f"**Próximas reuniones ({len(proximas)}):**")
            for r in proximas[:5]:
                tipo = r.get("tipo", "reunión").capitalize()
                link = f" · [Unirse]({r['linkMeet']})" if r.get("linkMeet") else ""
                proyecto = f" · Proyecto: {r['proyecto']['nombre']}" if r.get("proyecto") else ""
                agenda = f"\n  Agenda: {r['descripcion']}" if r.get("descripcion") else ""
                lines.append(
                    f"- **{r['titulo']}** ({tipo}) — {_fmt_fecha(r['fecha'])}{link}{proyecto}{agenda}"
                )

        if pasadas:
            lines.append(f"\n**Reuniones pasadas ({len(pasadas)}):**")
            for r in pasadas[:3]:
                lines.append(f"- {r['titulo']} — {_fmt_fecha(r['fecha'])}")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Error al consultar reuniones: {e.response.status_code}"
    except Exception as e:
        return f"Error inesperado al consultar reuniones: {str(e)}"

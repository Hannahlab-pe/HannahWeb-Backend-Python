"""
Tools de LangGraph que Hannah AI puede invocar para responder preguntas del usuario.
Cada tool recibe el token del usuario para consultar datos reales de su cuenta.
"""
from langchain_core.tools import tool
from . import nestjs_client


def build_tools(token: str):
    """
    Devuelve la lista de tools con el token del usuario ya inyectado.
    Se crean por request para que cada usuario vea solo sus datos.
    """

    @tool
    async def consultar_proyectos(query: str = "") -> str:
        """
        Consulta los proyectos del usuario: nombre, estado, progreso, fecha de entrega.
        Úsala cuando el usuario pregunta por el estado de sus proyectos, avances o entregas.
        """
        try:
            proyectos = await nestjs_client.get_proyectos(token)
            if not proyectos:
                return "El usuario no tiene proyectos activos."
            lines = []
            for p in proyectos:
                estado = p.get("estado", "—")
                progreso = p.get("progreso", 0)
                fecha = p.get("fechaEntrega", "Sin fecha")
                lines.append(
                    f"- **{p['nombre']}**: estado={estado}, progreso={progreso}%, entrega={fecha}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error al consultar proyectos: {e}"

    @tool
    async def consultar_tickets(query: str = "") -> str:
        """
        Consulta los tickets de soporte del usuario: título, estado, prioridad.
        Úsala cuando el usuario pregunta por soporte, tickets abiertos o problemas reportados.
        """
        try:
            tickets = await nestjs_client.get_tickets(token)
            if not tickets:
                return "El usuario no tiene tickets."
            abiertos = [t for t in tickets if t.get("estado") != "cerrado"]
            cerrados = [t for t in tickets if t.get("estado") == "cerrado"]
            lines = [f"Total: {len(tickets)} tickets ({len(abiertos)} abiertos, {len(cerrados)} cerrados)"]
            for t in abiertos[:5]:
                lines.append(f"- [{t.get('estado','—')}] **{t['titulo']}** (prioridad: {t.get('prioridad','—')})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error al consultar tickets: {e}"

    @tool
    async def consultar_reuniones(query: str = "") -> str:
        """
        Consulta las reuniones programadas del usuario: título, fecha, tipo, link.
        Úsala cuando el usuario pregunta por reuniones, agenda o próximas citas.
        """
        try:
            from datetime import datetime, timezone
            reuniones = await nestjs_client.get_reuniones(token)
            if not reuniones:
                return "No hay reuniones programadas."
            now = datetime.now(timezone.utc)
            proximas = [
                r for r in reuniones
                if datetime.fromisoformat(r["fecha"].replace("Z", "+00:00")) > now
            ]
            pasadas = [
                r for r in reuniones
                if datetime.fromisoformat(r["fecha"].replace("Z", "+00:00")) <= now
            ]
            lines = []
            if proximas:
                lines.append(f"**Próximas ({len(proximas)}):**")
                for r in sorted(proximas, key=lambda x: x["fecha"])[:3]:
                    fecha_fmt = datetime.fromisoformat(r["fecha"].replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
                    link = f" — [Unirse]({r['linkMeet']})" if r.get("linkMeet") else ""
                    lines.append(f"- **{r['titulo']}** — {fecha_fmt}{link}")
            if pasadas:
                lines.append(f"\n**Pasadas ({len(pasadas)}):**")
                for r in sorted(pasadas, key=lambda x: x["fecha"], reverse=True)[:2]:
                    fecha_fmt = datetime.fromisoformat(r["fecha"].replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
                    lines.append(f"- {r['titulo']} — {fecha_fmt}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error al consultar reuniones: {e}"

    return [consultar_proyectos, consultar_tickets, consultar_reuniones]

"""
Grafo LangGraph para Hannah AI.
Arquitectura ReAct: el LLM decide qué tools usar, las ejecuta y responde.
Soporta streaming token a token.
"""
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from ..core.config import settings
from ..tools.hannah_tools import build_tools


SYSTEM_PROMPT = """Eres Hannah AI, el asistente inteligente de Hannah Lab.
Ayudas a los clientes de Hannah Lab a entender el estado de sus proyectos, tickets y reuniones.

Reglas:
- Responde siempre en español, de forma clara y concisa.
- Usa las tools disponibles para consultar datos reales antes de responder.
- Si el usuario pregunta por proyectos, tickets o reuniones, SIEMPRE consulta primero la tool correspondiente.
- Formatea las respuestas con markdown cuando mejore la legibilidad.
- Si no tienes información suficiente, dilo con honestidad.
- No inventes datos. Solo usa lo que devuelven las tools.
- Sé amable y profesional.
"""


def build_agent(token: str):
    """
    Construye el agente LangGraph con las tools del usuario.
    Usa Claude si hay API key de Anthropic, sino OpenAI.
    """
    tools = build_tools(token)

    if settings.anthropic_api_key:
        llm = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            api_key=settings.anthropic_api_key,
            temperature=0.3,
            max_tokens=1024,
            streaming=True,
        )
    else:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key,
            temperature=0.3,
            streaming=True,
        )

    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=SYSTEM_PROMPT,
    )
    return agent

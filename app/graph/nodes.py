from langchain_core.messages import SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from ..core.config import settings
from .state import HannahState


SYSTEM_PROMPT = """Eres Hannah AI, el asistente inteligente de Hannah Lab.
Tu rol es ayudar a los clientes a entender el estado de sus proyectos, tickets y reuniones.

Reglas:
- Responde siempre en español, de forma clara y concisa.
- Usa las herramientas disponibles para consultar datos reales ANTES de responder.
- Si el usuario pregunta por proyectos, tickets o reuniones, consulta la herramienta correspondiente.
- Formatea las respuestas con markdown cuando mejore la legibilidad (listas, negritas, etc).
- No inventes datos. Solo usa lo que devuelven las herramientas.
- Si no encuentras información, dilo con honestidad.
- Sé amable, profesional y directo.
"""


def get_llm(tools: list):
    """Inicializa el LLM con tools enlazadas."""
    if settings.anthropic_api_key:
        llm = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=settings.anthropic_api_key,
            temperature=0.2,
            max_tokens=1024,
        )
    else:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key,
            temperature=0.2,
        )
    return llm.bind_tools(tools)


def make_llm_node(llm_with_tools):
    """
    Devuelve el nodo llm_call con el LLM ya configurado.
    El nodo recibe el estado, prepara los mensajes con el system prompt,
    y devuelve la respuesta del LLM.
    """
    async def llm_call(state: HannahState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    return llm_call

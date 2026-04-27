from langgraph.graph import MessagesState


class HannahState(MessagesState):
    """
    Estado del agente Hannah AI.
    Extiende MessagesState (que ya incluye 'messages' con reducer add_messages).
    """
    user_rol: str  # admin | subadmin | cliente — para personalizar respuestas

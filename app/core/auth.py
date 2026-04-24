"""
Valida el JWT del frontend (mismo secret que NestJS) e inyecta
el token raw en el payload para que las tools puedan llamar al NestJS.
"""
from fastapi import Header, HTTPException, status
from jose import jwt, JWTError
from .config import settings


def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    raw_token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = jwt.decode(raw_token, settings.jwt_secret, algorithms=["HS256"])
        # Inyectamos el token raw para que las tools llamen al NestJS en nombre del usuario
        payload["_raw_token"] = raw_token
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

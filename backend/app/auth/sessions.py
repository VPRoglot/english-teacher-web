import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Response
from redis.asyncio import Redis

from app.auth.models import UserRole
from app.auth.tokens import sha256_hex
from app.core.config import Settings
from app.core.redis import RedisClient

SESSION_COOKIE = "session"
SESSION_TTL: dict[UserRole, timedelta] = {
    UserRole.TUTOR: timedelta(days=7),
    UserRole.PARENT: timedelta(days=30),
    UserRole.CHILD: timedelta(days=30),
}
# Индекс сессий пользователя живёт не меньше самой долгой сессии.
_INDEX_TTL = max(SESSION_TTL.values())


@dataclass(frozen=True)
class SessionData:
    user_id: uuid.UUID
    role: UserRole
    created_at: datetime


def _session_key(token: str) -> str:
    return f"session:{sha256_hex(token)}"


def _index_key(user_id: uuid.UUID) -> str:
    return f"user_sessions:{user_id}"


class SessionStore:
    """Серверные сессии в Redis. Ключи содержат sha256 токена, а не сам токен."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def create(self, user_id: uuid.UUID, role: UserRole) -> str:
        token = secrets.token_urlsafe(32)
        digest = sha256_hex(token)
        payload = json.dumps(
            {
                "user_id": str(user_id),
                "role": role.value,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        index = _index_key(user_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(f"session:{digest}", payload, ex=SESSION_TTL[role])
            pipe.sadd(index, digest)
            pipe.expire(index, _INDEX_TTL)
            await pipe.execute()
        return token

    async def get(self, token: str) -> SessionData | None:
        """Возвращает сессию и продлевает её срок (плавающий): каждый успешный get — новый TTL."""
        key = _session_key(token)
        data = _parse(await self._redis.get(key))
        if data is not None:
            # Индекс продлевается вместе с сессией, иначе он истечёт раньше долгоживущей сессии
            # и delete_all_for_user перестанет её находить.
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.expire(key, SESSION_TTL[data.role])
                pipe.expire(_index_key(data.user_id), _INDEX_TTL)
                await pipe.execute()
        return data

    async def delete(self, token: str) -> None:
        # Владелец известен только из содержимого сессии; GETDEL читает и удаляет атомарно.
        data = _parse(await self._redis.getdel(_session_key(token)))
        if data is not None:
            await self._redis.srem(_index_key(data.user_id), sha256_hex(token))

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        """Удаляет все сессии пользователя и индекс; возвращает число реально удалённых сессий."""
        index = _index_key(user_id)
        # Чтение и удаление индекса — одна транзакция: сессия, созданная после неё, попадёт
        # в новый индекс и не потеряется.
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.smembers(index)
            pipe.delete(index)
            digests, _ = await pipe.execute()
        if not digests:
            return 0
        # В индексе могут остаться хэши уже истёкших сессий — DEL считает только существующие.
        return int(await self._redis.delete(*(f"session:{_text(d)}" for d in digests)))


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _parse(raw: bytes | str | None) -> SessionData | None:
    """Битое или неполное содержимое трактуется как отсутствие сессии."""
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
        return SessionData(
            user_id=uuid.UUID(payload["user_id"]),
            role=UserRole(payload["role"]),
            created_at=datetime.fromisoformat(payload["created_at"]),
        )
    except (ValueError, KeyError, TypeError):
        return None


async def get_session_store(redis: RedisClient) -> SessionStore:
    return SessionStore(redis)


SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]


def set_session_cookie(response: Response, token: str, role: UserRole, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL[role].total_seconds()),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )

import httpx
import structlog
from asgi_lifespan import LifespanManager
from pydantic import SecretStr

from app.core.config import Settings
from app.leads.captcha import DisabledCaptchaVerifier, YandexCaptchaVerifier
from app.main import create_app


def _verifier(transport: httpx.MockTransport) -> YandexCaptchaVerifier:
    return YandexCaptchaVerifier(httpx.AsyncClient(transport=transport), "server-key")


async def test_disabled_verifier_accepts_everything() -> None:
    assert await DisabledCaptchaVerifier().verify(None, None) is True


async def test_yandex_ok_and_failed() -> None:
    ok = _verifier(httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok"})))
    failed = _verifier(
        httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "failed"}))
    )
    assert await ok.verify("token", "1.2.3.4") is True
    assert await failed.verify("token", "1.2.3.4") is False


async def test_yandex_sends_secret_token_ip() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    await _verifier(httpx.MockTransport(handler)).verify("tok", "1.2.3.4")
    (request,) = requests
    assert request.method == "POST"
    assert str(request.url) == "https://smartcaptcha.yandexcloud.net/validate"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert request.content == b"secret=server-key&token=tok&ip=1.2.3.4"


async def test_yandex_omits_ip_when_unknown() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    await _verifier(httpx.MockTransport(handler)).verify("tok", None)
    assert requests[0].content == b"secret=server-key&token=tok"


async def test_yandex_fails_open_on_error() -> None:
    def server_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    def connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет сети")

    for handler in (server_error, connect_error):
        verifier = _verifier(httpx.MockTransport(handler))
        with structlog.testing.capture_logs() as logs:
            assert await verifier.verify("tok", "1.2.3.4") is True
        unavailable = [e for e in logs if e["event"] == "captcha_unavailable"]
        assert len(unavailable) == 1
        assert unavailable[0]["log_level"] == "warning"


async def test_yandex_fails_open_on_malformed_body() -> None:
    verifier = _verifier(httpx.MockTransport(lambda r: httpx.Response(200, text="not json")))
    with structlog.testing.capture_logs() as logs:
        assert await verifier.verify("tok", "1.2.3.4") is True
    assert [e["event"] for e in logs] == ["captcha_unavailable"]


async def test_empty_token_is_rejected_without_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    verifier = _verifier(httpx.MockTransport(handler))
    assert await verifier.verify(None, "1.2.3.4") is False
    assert await verifier.verify("", "1.2.3.4") is False
    assert requests == []


async def test_lifespan_picks_verifier_by_server_key(settings: Settings) -> None:
    plain = create_app(settings)
    async with LifespanManager(plain):
        assert isinstance(plain.state.captcha, DisabledCaptchaVerifier)

    keyed = create_app(
        settings.model_copy(update={"smartcaptcha_server_key": SecretStr("server-key")})
    )
    async with LifespanManager(keyed):
        verifier = keyed.state.captcha
        assert isinstance(verifier, YandexCaptchaVerifier)
        client = verifier._client
        assert not client.is_closed
    assert client.is_closed

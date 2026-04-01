"""Provider integration tests for WhatsApp adapters."""

from __future__ import annotations

from typing import Any

import pytest

from svmp_core.config import Settings
from svmp_core.exceptions import IntegrationError
from svmp_core.integrations.whatsapp_provider import TwilioWhatsAppProvider
from svmp_core.models import OutboundTextMessage


def test_twilio_provider_normalizes_form_payload() -> None:
    """Twilio form data should normalize into the internal webhook schema."""

    provider = TwilioWhatsAppProvider()

    payloads = provider.normalize_form_payload(
        {
            "MessageSid": "SM123",
            "From": "whatsapp:+919845891194",
            "Body": "hello from twilio",
        },
        tenant_id="Niyomilan",
    )

    assert len(payloads) == 1
    assert payloads[0].tenant_id == "Niyomilan"
    assert payloads[0].client_id == "whatsapp"
    assert payloads[0].user_id == "+919845891194"
    assert payloads[0].text == "hello from twilio"
    assert payloads[0].provider == "twilio"
    assert payloads[0].external_message_id == "SM123"


@pytest.mark.asyncio
async def test_twilio_provider_send_text_uses_rest_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twilio outbound send should format auth and form payload correctly."""

    captured: dict[str, Any] = {}

    class FakeResponse:
        is_error = False

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"sid": "SM999"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, data=None, auth=None):
            captured["url"] = url
            captured["data"] = dict(data)
            captured["auth"] = auth
            return FakeResponse()

    monkeypatch.setattr("svmp_core.integrations.whatsapp_provider.httpx.AsyncClient", FakeAsyncClient)

    provider = TwilioWhatsAppProvider()
    result = await provider.send_text(
        OutboundTextMessage(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="+919845891194",
            text="hello from svmp",
        ),
        settings=Settings(
            _env_file=None,
            TWILIO_ACCOUNT_SID="AC123",
            TWILIO_AUTH_TOKEN="secret",
            TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886",
        ),
    )

    assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert captured["data"] == {
        "From": "whatsapp:+14155238886",
        "To": "whatsapp:+919845891194",
        "Body": "hello from svmp",
    }
    assert captured["auth"] == ("AC123", "secret")
    assert result.provider == "twilio"
    assert result.accepted is True
    assert result.external_message_id == "SM999"
    assert result.status == "accepted"


@pytest.mark.asyncio
async def test_twilio_provider_send_text_surfaces_provider_error_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Twilio outbound failures should expose the provider's response message."""

    class FakeResponse:
        status_code = 400
        is_error = True

        def json(self) -> dict[str, str]:
            return {"message": "The From address whatsapp:+14155238886 is not enabled for this account."}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, data=None, auth=None):
            return FakeResponse()

    monkeypatch.setattr("svmp_core.integrations.whatsapp_provider.httpx.AsyncClient", FakeAsyncClient)

    provider = TwilioWhatsAppProvider()

    with pytest.raises(IntegrationError, match="Twilio send failed \\(400\\): The From address"):
        await provider.send_text(
            OutboundTextMessage(
                tenantId="Niyomilan",
                clientId="whatsapp",
                userId="+919845891194",
                text="hello from svmp",
            ),
            settings=Settings(
                _env_file=None,
                TWILIO_ACCOUNT_SID="AC123",
                TWILIO_AUTH_TOKEN="secret",
                TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886",
            ),
        )


@pytest.mark.asyncio
async def test_twilio_provider_send_typing_indicator_uses_typing_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Twilio typing indicators should call the dedicated messaging endpoint."""

    captured: dict[str, Any] = {}

    class FakeResponse:
        is_error = False

        def json(self) -> dict[str, str]:
            return {"status": "accepted"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, data=None, auth=None):
            captured["url"] = url
            captured["data"] = dict(data)
            captured["auth"] = auth
            return FakeResponse()

    monkeypatch.setattr("svmp_core.integrations.whatsapp_provider.httpx.AsyncClient", FakeAsyncClient)

    provider = TwilioWhatsAppProvider()
    await provider.send_typing_indicator(
        inbound_message_id="SM123",
        settings=Settings(
            _env_file=None,
            TWILIO_ACCOUNT_SID="AC123",
            TWILIO_AUTH_TOKEN="secret",
            TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886",
        ),
    )

    assert captured["url"] == "https://messaging.twilio.com/v2/Indicators/Typing.json"
    assert captured["data"] == {
        "messageId": "SM123",
        "channel": "whatsapp",
    }
    assert captured["auth"] == ("AC123", "secret")

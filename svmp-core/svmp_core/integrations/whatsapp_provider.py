"""Provider-agnostic WhatsApp ingress and outbound abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError as PydanticValidationError

from svmp_core.config import Settings
from svmp_core.exceptions import IntegrationError, ValidationError
from svmp_core.models import OutboundSendResult, OutboundTextMessage, WebhookPayload


def _require_non_blank(value: str | None, field_name: str) -> str:
    """Trim and require a non-blank string value."""

    if value is None:
        raise ValidationError(f"{field_name} is required")

    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} is required")

    return normalized


def _normalize_phone_identity(value: str) -> str:
    """Normalize provider phone identities into a stable user id."""

    normalized = value.strip()
    if normalized.lower().startswith("whatsapp:"):
        return normalized.split(":", 1)[1]
    return normalized


class WhatsAppProvider(ABC):
    """Provider abstraction for ingress normalization and outbound sending."""

    name: str

    def verify_webhook(
        self,
        *,
        settings: Settings,
        hub_mode: str | None,
        hub_verify_token: str | None,
        hub_challenge: str | None,
    ) -> str | None:
        """Verify webhook setup if the provider supports GET verification."""

        return None

    def normalize_json_payload(
        self,
        payload: Mapping[str, Any],
        *,
        tenant_id: str | None,
    ) -> list[WebhookPayload]:
        """Normalize a JSON provider payload into internal webhook payloads."""

        raise ValidationError(f"{self.name} does not accept JSON webhook payloads")

    def normalize_form_payload(
        self,
        payload: Mapping[str, Any],
        *,
        tenant_id: str | None,
    ) -> list[WebhookPayload]:
        """Normalize a form provider payload into internal webhook payloads."""

        raise ValidationError(f"{self.name} does not accept form webhook payloads")

    @abstractmethod
    async def send_text(
        self,
        message: OutboundTextMessage,
        *,
        settings: Settings,
    ) -> OutboundSendResult:
        """Send a normalized outbound text message using the provider."""


class NormalizedWhatsAppProvider(WhatsAppProvider):
    """Provider adapter for already-normalized internal webhook payloads."""

    name = "normalized"

    def normalize_json_payload(
        self,
        payload: Mapping[str, Any],
        *,
        tenant_id: str | None,
    ) -> list[WebhookPayload]:
        try:
            return [WebhookPayload(**dict(payload), provider=self.name)]
        except PydanticValidationError as exc:
            raise ValidationError("invalid normalized webhook payload") from exc

    async def send_text(
        self,
        message: OutboundTextMessage,
        *,
        settings: Settings,
    ) -> OutboundSendResult:
        return OutboundSendResult(
            provider=self.name,
            accepted=True,
            external_message_id=None,
            status="simulated",
            metadata={
                "clientId": message.client_id,
                "userId": message.user_id,
                "text": message.text,
            },
        )


class MetaWhatsAppProvider(WhatsAppProvider):
    """Provider adapter for Meta WhatsApp Business webhook payloads."""

    name = "meta"

    def verify_webhook(
        self,
        *,
        settings: Settings,
        hub_mode: str | None,
        hub_verify_token: str | None,
        hub_challenge: str | None,
    ) -> str | None:
        verify_token = settings.WHATSAPP_VERIFY_TOKEN
        expected_token = verify_token.get_secret_value() if verify_token is not None else None

        if hub_mode != "subscribe" or expected_token is None or hub_verify_token != expected_token:
            raise ValidationError("webhook verification failed")

        if hub_challenge is None:
            raise ValidationError("missing hub.challenge")

        return hub_challenge

    def normalize_json_payload(
        self,
        payload: Mapping[str, Any],
        *,
        tenant_id: str | None,
    ) -> list[WebhookPayload]:
        resolved_tenant_id = _require_non_blank(tenant_id, "tenantId")
        normalized_messages: list[WebhookPayload] = []

        raw_entries = payload.get("entry", [])
        if not isinstance(raw_entries, list):
            raise ValidationError("Meta webhook entry must be a list")

        for entry in raw_entries:
            if not isinstance(entry, Mapping):
                continue

            changes = entry.get("changes", [])
            if not isinstance(changes, list):
                continue

            for change in changes:
                if not isinstance(change, Mapping):
                    continue

                value = change.get("value", {})
                if not isinstance(value, Mapping):
                    continue

                messages = value.get("messages", [])
                if not isinstance(messages, list):
                    continue

                for message in messages:
                    if not isinstance(message, Mapping):
                        continue

                    raw_text = message.get("text", {})
                    text_body = raw_text.get("body") if isinstance(raw_text, Mapping) else None
                    from_user = message.get("from")

                    if not isinstance(text_body, str) or not text_body.strip():
                        continue
                    if not isinstance(from_user, str) or not from_user.strip():
                        continue

                    normalized_messages.append(
                        WebhookPayload(
                            tenantId=resolved_tenant_id,
                            clientId="whatsapp",
                            userId=_normalize_phone_identity(from_user),
                            text=text_body,
                            provider=self.name,
                            externalMessageId=message.get("id"),
                        )
                    )

        if not normalized_messages:
            raise ValidationError("Meta webhook contained no supported inbound messages")

        return normalized_messages

    async def send_text(
        self,
        message: OutboundTextMessage,
        *,
        settings: Settings,
    ) -> OutboundSendResult:
        token = settings.WHATSAPP_TOKEN
        if token is None:
            raise IntegrationError("WHATSAPP_TOKEN is not configured")
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        if phone_number_id is None or not phone_number_id.strip():
            raise IntegrationError("WHATSAPP_PHONE_NUMBER_ID is not configured")

        url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": message.user_id,
            "type": "text",
            "text": {"body": message.text},
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        message_id = None
        messages = body.get("messages", [])
        if isinstance(messages, list) and messages and isinstance(messages[0], Mapping):
            raw_id = messages[0].get("id")
            if isinstance(raw_id, str):
                message_id = raw_id

        return OutboundSendResult(
            provider=self.name,
            accepted=True,
            external_message_id=message_id,
            status="accepted",
            metadata={"response": body},
        )


class TwilioWhatsAppProvider(WhatsAppProvider):
    """Provider adapter for Twilio WhatsApp webhook payloads."""

    name = "twilio"

    def normalize_form_payload(
        self,
        payload: Mapping[str, Any],
        *,
        tenant_id: str | None,
    ) -> list[WebhookPayload]:
        resolved_tenant_id = _require_non_blank(tenant_id, "tenantId")
        body = payload.get("Body")
        from_user = payload.get("From")

        if not isinstance(body, str) or not body.strip():
            raise ValidationError("Twilio webhook Body is required")
        if not isinstance(from_user, str) or not from_user.strip():
            raise ValidationError("Twilio webhook From is required")

        return [
            WebhookPayload(
                tenantId=resolved_tenant_id,
                clientId="whatsapp",
                userId=_normalize_phone_identity(from_user),
                text=body,
                provider=self.name,
                externalMessageId=payload.get("MessageSid"),
            )
        ]

    async def send_text(
        self,
        message: OutboundTextMessage,
        *,
        settings: Settings,
    ) -> OutboundSendResult:
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_WHATSAPP_NUMBER

        if account_sid is None or not account_sid.strip():
            raise IntegrationError("TWILIO_ACCOUNT_SID is not configured")
        if auth_token is None:
            raise IntegrationError("TWILIO_AUTH_TOKEN is not configured")
        if from_number is None or not from_number.strip():
            raise IntegrationError("TWILIO_WHATSAPP_NUMBER is not configured")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        form_data = {
            "From": from_number,
            "To": message.user_id if message.user_id.startswith("whatsapp:") else f"whatsapp:{message.user_id}",
            "Body": message.text,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                data=form_data,
                auth=(account_sid, auth_token.get_secret_value()),
            )
            response.raise_for_status()
            body = response.json()

        sid = body.get("sid") if isinstance(body, Mapping) else None
        return OutboundSendResult(
            provider=self.name,
            accepted=True,
            external_message_id=sid if isinstance(sid, str) else None,
            status="accepted",
            metadata={"response": body},
        )


_PROVIDERS: dict[str, WhatsAppProvider] = {
    "normalized": NormalizedWhatsAppProvider(),
    "meta": MetaWhatsAppProvider(),
    "twilio": TwilioWhatsAppProvider(),
}


def is_normalized_payload(payload: Mapping[str, Any]) -> bool:
    """Return whether a payload should be treated as the internal normalized schema."""

    normalized_markers = {"tenantId", "clientId", "userId", "text"}
    return bool(normalized_markers.intersection(set(payload.keys())))


def get_whatsapp_provider(
    *,
    settings: Settings,
    requested_provider: str | None = None,
    payload: Mapping[str, Any] | None = None,
    content_type: str | None = None,
) -> WhatsAppProvider:
    """Resolve the provider adapter for the current webhook request."""

    if requested_provider is not None and requested_provider.strip():
        provider_name = requested_provider.strip().lower()
    elif payload is not None and is_normalized_payload(payload):
        provider_name = "normalized"
    elif content_type is not None and "application/x-www-form-urlencoded" in content_type.lower():
        provider_name = "twilio"
    else:
        provider_name = settings.WHATSAPP_PROVIDER.strip().lower()

    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        raise ValidationError(f"unsupported WhatsApp provider: {provider_name}")
    return provider

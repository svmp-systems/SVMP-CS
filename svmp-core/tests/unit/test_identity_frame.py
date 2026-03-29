"""Unit tests for the canonical identity frame."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from svmp_core.core import IdentityFrame
from svmp_core.models import WebhookPayload


def test_identity_frame_accepts_python_field_names() -> None:
    """IdentityFrame should accept snake_case field names."""

    identity = IdentityFrame(
        tenant_id="Niyomilan",
        client_id="whatsapp",
        user_id="9845891194",
    )

    assert identity.as_tuple() == ("Niyomilan", "whatsapp", "9845891194")


def test_identity_frame_accepts_aliases_and_normalizes_whitespace() -> None:
    """IdentityFrame should accept canonical aliases and trim values."""

    identity = IdentityFrame(
        tenantId=" Niyomilan ",
        clientId=" whatsapp ",
        userId=" 9845891194 ",
    )

    assert identity.tenant_id == "Niyomilan"
    assert identity.client_id == "whatsapp"
    assert identity.user_id == "9845891194"


def test_identity_frame_builds_from_webhook_payload() -> None:
    """Webhook payloads should convert directly into identity frames."""

    payload = WebhookPayload(
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        text="hi",
    )

    identity = IdentityFrame.from_webhook_payload(payload)

    assert identity.as_tuple() == ("Niyomilan", "whatsapp", "9845891194")


def test_identity_frame_rejects_blank_values() -> None:
    """Blank identity parts should fail validation."""

    with pytest.raises(ValidationError, match="identity fields must not be blank"):
        IdentityFrame(
            tenant_id="Niyomilan",
            client_id="whatsapp",
            user_id="   ",
        )


def test_identity_frame_can_build_from_mapping() -> None:
    """Mappings with canonical aliases should parse cleanly."""

    identity = IdentityFrame.from_mapping(
        {
            "tenantId": "Niyomilan",
            "clientId": "whatsapp",
            "userId": "9845891194",
        }
    )

    assert identity.as_tuple() == ("Niyomilan", "whatsapp", "9845891194")

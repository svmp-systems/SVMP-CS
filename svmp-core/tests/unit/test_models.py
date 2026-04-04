"""Sanity tests for the core data models."""

from __future__ import annotations

from datetime import datetime, timezone

from svmp_core.models import GovernanceDecision, GovernanceLog, KnowledgeEntry, SessionState, WebhookPayload


def test_session_state_accepts_internal_field_names() -> None:
    """SessionState should validate using Python snake_case field names."""

    session = SessionState(
        tenant_id="Niyomilan",
        client_id="whatsapp",
        user_id="9845891194",
    )

    assert session.status == "open"
    assert session.processing is False
    assert session.escalate is False
    assert session.pending_escalation is False
    assert session.pending_escalation_expires_at is None
    assert session.pending_escalation_metadata == {}
    assert session.messages == []


def test_session_state_accepts_mongo_aliases() -> None:
    """SessionState should accept Mongo-style aliases on input."""

    session = SessionState(
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        messages=[{"text": "hi"}],
    )

    assert session.tenant_id == "Niyomilan"
    assert session.client_id == "whatsapp"
    assert session.user_id == "9845891194"
    assert session.escalate is False
    assert session.pending_escalation is False
    assert session.messages[0].text == "hi"


def test_session_state_normalizes_naive_datetimes_to_utc() -> None:
    """Naive datetimes loaded from Mongo should be treated as UTC."""

    session = SessionState(
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        messages=[{"text": "hi", "at": datetime(2026, 4, 4, 16, 11, 17)}],
        createdAt=datetime(2026, 4, 4, 16, 11, 17),
        updatedAt=datetime(2026, 4, 4, 16, 11, 18),
        debounceExpiresAt=datetime(2026, 4, 4, 16, 11, 19),
        pendingEscalation=True,
        pendingEscalationExpiresAt=datetime(2026, 4, 4, 16, 11, 24),
    )

    assert session.messages[0].at == datetime(2026, 4, 4, 16, 11, 17, tzinfo=timezone.utc)
    assert session.created_at == datetime(2026, 4, 4, 16, 11, 17, tzinfo=timezone.utc)
    assert session.updated_at == datetime(2026, 4, 4, 16, 11, 18, tzinfo=timezone.utc)
    assert session.debounce_expires_at == datetime(2026, 4, 4, 16, 11, 19, tzinfo=timezone.utc)
    assert session.pending_escalation_expires_at == datetime(2026, 4, 4, 16, 11, 24, tzinfo=timezone.utc)


def test_knowledge_entry_defaults_and_alias_dump() -> None:
    """KnowledgeEntry should keep defaults and serialize with aliases."""

    entry = KnowledgeEntry(
        tenant_id="Niyomilan",
        domain_id="general",
        question="What does our company do?",
        answer="We are Niyomilan.",
    )

    dumped = entry.model_dump(by_alias=True)

    assert entry.active is True
    assert dumped["tenantId"] == "Niyomilan"
    assert dumped["domainId"] == "general"


def test_governance_log_supports_expected_decisions() -> None:
    """Governance logs should validate typed decisions and optional score."""

    log = GovernanceLog(
        tenant_id="Niyomilan",
        client_id="whatsapp",
        user_id="9845891194",
        decision=GovernanceDecision.ANSWERED,
        similarity_score=0.82,
        combined_text="hi what do you guys do",
        answer_supplied="We are Niyomilan.",
    )

    assert log.decision == GovernanceDecision.ANSWERED
    assert log.similarity_score == 0.82


def test_webhook_payload_parses_normalized_alias_fields() -> None:
    """WebhookPayload should validate the normalized inbound message contract."""

    payload = WebhookPayload(
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        text="hi",
    )

    assert payload.tenant_id == "Niyomilan"
    assert payload.client_id == "whatsapp"
    assert payload.user_id == "9845891194"
    assert payload.text == "hi"

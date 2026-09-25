"""Fixtures use synthetic data, never personal accounts."""

from unittest.mock import AsyncMock, patch

import pytest

USER = {
    "id": "synthetic-account",
    "members": [{"id": "member", "companyId": "company"}],
    "installations": [{"id": "installation", "name": "Test home"}],
}
CARDS = [{"id": "card", "label": "Test card", "type": "msp"}]
SESSIONS = [
    {
        "start": "2026-09-20T12:00:00Z",
        "end": "2026-09-20T13:00:00Z",
        "kwh": 7.5,
        "duration": 60,
        "status": "COMPLETED",
    }
]


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    yield


@pytest.fixture
def mock_api():
    from custom_components.blossom_energy.api import Tokens

    with (
        patch(
            "custom_components.blossom_energy.config_flow.login",
            new_callable=AsyncMock,
            return_value=Tokens("synthetic-refresh", "synthetic-access", float("inf")),
        ) as login,
        patch(
            "custom_components.blossom_energy.api.BlossomClient.current_user",
            new_callable=AsyncMock,
            return_value=USER,
        ) as current,
        patch(
            "custom_components.blossom_energy.api.BlossomClient.cards",
            new_callable=AsyncMock,
            return_value=CARDS,
        ) as cards,
        patch(
            "custom_components.blossom_energy.api.BlossomClient.recent_sessions",
            new_callable=AsyncMock,
            return_value=SESSIONS,
        ) as sessions,
    ):
        yield {"login": login, "current": current, "cards": cards, "sessions": sessions}

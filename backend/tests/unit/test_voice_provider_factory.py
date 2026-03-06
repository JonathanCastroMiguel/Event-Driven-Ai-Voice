"""Unit tests for create_voice_provider factory."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.voice_runtime.openai_realtime_provider import OpenAIRealtimeProvider
from src.voice_runtime.realtime_provider import StubVoiceProvider, create_voice_provider


class TestCreateVoiceProvider:
    async def test_returns_openai_provider_when_key_set(self) -> None:
        with (
            patch("src.config.settings") as mock_settings,
            patch.object(OpenAIRealtimeProvider, "connect", new_callable=AsyncMock) as mock_connect,
        ):
            mock_settings.openai_api_key = "sk-test-key"
            mock_settings.openai_realtime_model = "gpt-4o-mini-realtime-preview"

            provider = await create_voice_provider()

            assert isinstance(provider, OpenAIRealtimeProvider)
            mock_connect.assert_awaited_once()

    async def test_returns_stub_when_key_empty(self) -> None:
        with patch("src.config.settings") as mock_settings:
            mock_settings.openai_api_key = ""

            provider = await create_voice_provider()

            assert isinstance(provider, StubVoiceProvider)

    async def test_returns_stub_when_key_not_set(self) -> None:
        with patch("src.config.settings") as mock_settings:
            mock_settings.openai_api_key = ""

            provider = await create_voice_provider()

            assert isinstance(provider, StubVoiceProvider)

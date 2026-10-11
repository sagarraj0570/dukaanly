import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.config import Settings
from app.db.init_predeploy import init_predeploy


@pytest.mark.asyncio
async def test_init_predeploy_success():
    """Verify that init_predeploy completes successfully against a healthy database."""
    # Running directly against local dev db
    await init_predeploy()


def test_settings_database_url_protocol_mapping():
    """Verify that PaaS postgresql:// connection strings are translated to asyncpg."""
    s = Settings(
        DATABASE_URL="postgresql://dukaanly_user:secret@dpg-abc-a:5432/dukaanly"
    )
    assert s.database_url == "postgresql+asyncpg://dukaanly_user:secret@dpg-abc-a:5432/dukaanly"


def test_settings_cors_origins_parsing():
    """Verify that comma-separated ALLOWED_ORIGINS are parsed and trimmed correctly."""
    s = Settings(
        ALLOWED_ORIGINS="https://dukaanly-frontend.onrender.com, https://dukaanly.example.com"
    )
    assert s.cors_origins == [
        "https://dukaanly-frontend.onrender.com",
        "https://dukaanly.example.com",
    ]


@pytest.mark.asyncio
async def test_init_predeploy_fails_when_extension_missing():
    """Verify that init_predeploy exits with status 1 if PostGIS is not available."""
    mock_conn = AsyncMock()
    # Mock result for pg_available_extensions to return None (no postgis extension found)
    mock_result = MagicMock()
    mock_result.mappings().fetchone.return_value = None
    mock_conn.execute.side_effect = [
        MagicMock(),  # SELECT 1
        mock_result,  # pg_available_extensions
    ]

    mock_connect = MagicMock()
    mock_connect.__aenter__.return_value = mock_conn
    mock_connect.__aexit__.return_value = None

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_connect
    mock_engine.dispose = AsyncMock()

    with patch("app.db.init_predeploy.engine", mock_engine):
        with pytest.raises(SystemExit) as exc_info:
            await init_predeploy()
        assert exc_info.value.code == 1

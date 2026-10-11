import pytest
from pydantic import ValidationError
from app.core.config import Settings

def test_production_rejects_default_dev_jwt_secret():
    with pytest.raises(ValidationError) as exc:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="supersecret_for_development_only",
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=False,
        )
    assert "In production, JWT_SECRET_KEY must be a strong random secret of at least 32 characters" in str(exc.value)

def test_production_rejects_jwt_secret_shorter_than_32_chars():
    with pytest.raises(ValidationError) as exc:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="short_secret_under_32_chars",
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=False,
        )
    assert "In production, JWT_SECRET_KEY must be a strong random secret of at least 32 characters" in str(exc.value)

def test_production_rejects_debug_true():
    with pytest.raises(ValidationError) as exc:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="a" * 32,
            DEBUG=True,
            ALLOW_MOCK_PAYMENTS=False,
        )
    assert "DEBUG mode must be False in production" in str(exc.value)

def test_production_rejects_mock_payments_true():
    with pytest.raises(ValidationError) as exc:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="a" * 32,
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=True,
        )
    assert "ALLOW_MOCK_PAYMENTS cannot be enabled in production" in str(exc.value)

def test_production_accepts_valid_hardened_config():
    valid_settings = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="a" * 32,
        DEBUG=False,
        ALLOW_MOCK_PAYMENTS=False,
    )
    assert valid_settings.APP_ENV == "production"
    assert valid_settings.ALLOW_MOCK_PAYMENTS is False
    assert valid_settings.DEBUG is False

def test_development_defaults_allow_mock_payments():
    dev_settings = Settings(
        APP_ENV="development",
    )
    assert dev_settings.ALLOW_MOCK_PAYMENTS is True

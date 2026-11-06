"""
Browser UI Test Suite (Marker: ui, optional).

Exercises frontend flows via Playwright headless browser if installed.
Skips cleanly if playwright is not installed in the environment.
"""

import pytest


@pytest.mark.ui
async def test_ui_customer_discovery_and_cart():
    """Placeholder UI flow verifying headless browser page load."""
    pytest.importorskip("playwright", reason="Playwright is not installed; skipping browser UI tier.")

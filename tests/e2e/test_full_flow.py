"""Opt-in browser smoke for the local Streamlit process using Playwright."""

import os
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest


pytestmark = pytest.mark.browser


@pytest.mark.skipif(os.getenv("RUN_BROWSER_E2E") != "1", reason="set RUN_BROWSER_E2E=1 to run local browser tests")
def test_streamlit_browser_smoke(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = "8502"
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "sql_tutor/app.py", "--server.port", port, "--server.headless", "true"],
        env={**os.environ, "STREAMLIT_SERVER_ADDRESS": "127.0.0.1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urlopen(f"{base_url}/_stcore/health", timeout=1) as response:
                    if response.read().decode() == "ok":
                        break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("Streamlit did not become healthy within 30 seconds")

        with playwright.sync_playwright() as api:
            browser = api.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            console_errors = []
            external_requests = []
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("request", lambda request: external_requests.append(request.url) if not request.url.startswith(base_url) else None)
            page.goto(base_url, wait_until="networkidle")
            assert page.get_by_text("Adaptive SQL Tutor", exact=True).count() == 1
            page.screenshot(path=str(tmp_path / "adaptive-sql-tutor.png"), full_page=True)
            browser.close()

        assert not console_errors
        assert not external_requests
    finally:
        process.terminate()
        process.wait(timeout=10)

"""PDF rendering for the newsletter delivery pipeline.

Uses Playwright + headless Chromium to print the already-rendered
`issues/{slug}/index.html` via its file:// URL. `prefer_css_page_size` +
zero margins let the existing @page rules in the print stylesheet drive
pagination exactly as Chrome does under Cmd+P, so the emailed PDF
matches what an interactive user would save locally.

This is the one place in the pipeline that uses a headless browser.
See CLAUDE.md for the scoped rule.
"""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import async_playwright

from app.config import settings

logger = logging.getLogger(__name__)


async def build_issue_pdf(slug: str) -> bytes:
    """Render the rendered HTML for `slug` into PDF bytes.

    Raises FileNotFoundError when the HTML hasn't been written yet (issue
    likely not `ready`). Raises PlaywrightError on browser launch failures.
    Neither re-raises into the graph: callers catch and record failure in
    meta.notify / return a 500 on /send."""
    html_path = Path(settings.issues_dir) / slug / "index.html"
    if not html_path.exists():
        raise FileNotFoundError(f"rendered HTML missing for slug={slug!r}: {html_path}")

    url = f"file://{html_path}"
    logger.info("pdf: rendering %s", url)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            pdf = await page.pdf(
                format="Letter",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
        finally:
            await browser.close()

    logger.info("pdf: rendered %s bytes for %s", len(pdf), slug)
    return pdf

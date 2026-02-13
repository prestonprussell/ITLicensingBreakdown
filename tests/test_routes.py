from app.main import STATIC_DIR, app


def test_launcher_and_invoice_routes_registered() -> None:
    paths = {route.path for route in app.routes}

    assert "/" in paths
    assert "/apps/invoice-analyzer" in paths


def test_launcher_html_lists_invoice_analyzer() -> None:
    html = (STATIC_DIR / "launcher.html").read_text(encoding="utf-8")

    assert "CodexPlayground" in html
    assert "Invoice Analyzer" in html

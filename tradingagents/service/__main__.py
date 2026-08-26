"""Run the optional ARVEN Trade web API with Uvicorn."""

from __future__ import annotations

import os


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - operator guidance
        raise SystemExit('Install the web extra first: pip install ".[web]"') from exc

    host = os.getenv("TRADINGAGENTS_API_HOST", "127.0.0.1")
    port = int(os.getenv("TRADINGAGENTS_API_PORT", "8000"))
    uvicorn.run(
        "tradingagents.service.api:create_app",
        factory=True,
        host=host,
        port=port,
        workers=1,
    )


if __name__ == "__main__":
    main()

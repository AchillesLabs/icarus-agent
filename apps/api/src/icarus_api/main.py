"""CLI entrypoint for running the Icarus API server with Uvicorn."""

import uvicorn

from icarus_api.app import create_app
from icarus_api.config import ApiSettings

app = create_app()


def main() -> None:
    """Run the FastAPI application via uvicorn server."""
    settings = ApiSettings()
    uvicorn.run(
        "icarus_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()

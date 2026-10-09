"""Start the server: .venv/bin/python -m voicer  (UI and API at http://localhost:8765)."""
import uvicorn

from . import config


def main() -> None:
    uvicorn.run("voicer.server:app", host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()

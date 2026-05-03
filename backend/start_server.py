import os

try:
    from .programAPI import run_server
except ImportError:
    from programAPI import run_server


def main() -> None:
    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND_PORT", "5000"))
    debug = os.environ.get("BACKEND_DEBUG", "false").lower() in {"1", "true", "yes", "on"}
    run_server(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
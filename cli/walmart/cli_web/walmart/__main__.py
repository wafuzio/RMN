"""Allow running as: python -m cli_web.walmart"""
from .walmart_cli import main

if __name__ == "__main__":
    main()  # use main() to ensure _client.close_context() teardown runs

"""`python -m waflet_recorder --service` runs the background service; without arguments the GUI (phase 2)."""
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--service" in argv:
        from .service import run_service
        return run_service()
    print("The recorder GUI is not implemented yet (phase 2). Use --service to run the background service.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

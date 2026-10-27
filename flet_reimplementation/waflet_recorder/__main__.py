"""`python -m waflet_recorder` runs the GUI; `--service` the background service; `--web [PORT]` serves the GUI to a browser."""
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--service" in argv:
        from .service import run_service
        return run_service()
    run_kwargs = {}
    if "--web" in argv:
        import flet as ft
        rest = argv[argv.index("--web") + 1:]
        run_kwargs = dict(view=ft.AppView.WEB_BROWSER, port=int(rest[0]) if rest and rest[0].isdigit() else 8551)
    from .app import main as run_gui
    run_gui(**run_kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())

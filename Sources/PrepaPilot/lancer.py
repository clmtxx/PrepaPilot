"""Windows entry point; diagnostic mode uses only temporary school data."""
from pathlib import Path
import sys


def launch():
    # Branch before importing the application and its pages. The helper only
    # loads the lightweight splash widget and cannot recursively launch itself.
    if '--startup-splash' in sys.argv:
        from mpsi_desktop.startup_splash import run_splash
        return run_splash()
    testing='--self-test' in sys.argv
    if testing and getattr(sys,'frozen',False):
        import faulthandler
        output=Path(sys.executable).resolve().parent/'self-test.log'
        sys.stdout=sys.stderr=output.open('w',encoding='utf-8',buffering=1)
        faulthandler.enable()
        # The builder owns the process timeout. Keep native crash diagnostics
        # without an asynchronous stack dump racing the Qt/Python main thread.
        print('Loading application modules.',flush=True)
    startup = None
    if not testing:
        from mpsi_desktop.startup import StartupScreen
        startup = StartupScreen()
        startup.start()
    try:
        from mpsi_desktop.main import main
        if testing:print('Starting application.',flush=True)
        return main(startup=startup)
    except Exception:
        if testing:
            import traceback
            traceback.print_exc()
            return 1
        raise
    finally:
        if startup is not None:
            startup.close()
        if testing and getattr(sys,'frozen',False):
            import faulthandler
            faulthandler.disable()


if __name__=='__main__':
    raise SystemExit(launch())

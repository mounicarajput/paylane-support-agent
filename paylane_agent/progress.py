"""A small 'still working' notice, so a slow model does not look like a hang."""
import threading
from contextlib import contextmanager


@contextmanager
def thinking(show=print, after: float = 4.0, every: float = 30.0):
    """Print a note if the work takes longer than `after` seconds, then again every `every` seconds."""
    stop = threading.Event()

    def run():
        waited = after
        if stop.wait(after):
            return
        show("  ...the agent is thinking. On a laptop CPU a reply can take a minute or two.")
        while not stop.wait(every):
            waited += every
            show(f"  ...still working ({int(waited)}s)")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()

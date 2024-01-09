import faulthandler
import signal


def handle_sigusr1():
    def handle(sig, frame):
        faulthandler.dump_traceback()

    signal.signal(signal.SIGUSR1, handle)

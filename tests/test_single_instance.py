import subprocess
import sys
import threading
import uuid

from vnrpc import single_instance

_CHILD = """
import sys, threading
sys.path.insert(0, {root!r})
from vnrpc import single_instance
inst = single_instance.acquire({mutex!r}, {event!r})
print("first" if inst else "second", flush=True)
shown = threading.Event()
inst.on_show_request(shown.set)
print("shown" if shown.wait(10) else "timeout", flush=True)
"""


def _names():
    tag = uuid.uuid4().hex
    return f"Local\\vnrpc-test-{tag}", f"Local\\vnrpc-test-{tag}-show"


def test_second_start_asks_the_first_to_show_itself():
    mutex, event = _names()
    first = single_instance.acquire(mutex, event)
    assert first is not None
    shown = threading.Event()
    first.on_show_request(shown.set)

    assert single_instance.acquire(mutex, event) is None
    assert shown.wait(5)
    shown.clear()
    assert single_instance.acquire(mutex, event) is None  # and again
    assert shown.wait(5)


def test_another_process_is_detected():
    mutex, event = _names()
    root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
    child = subprocess.Popen([sys.executable, "-c", _CHILD.format(root=root, mutex=mutex, event=event)],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "first"
        assert single_instance.acquire(mutex, event) is None
        assert child.stdout.readline().strip() == "shown"
    finally:
        child.kill()
        child.wait()
    # Once it's gone, the app can start again.
    assert single_instance.acquire(mutex, event) is not None

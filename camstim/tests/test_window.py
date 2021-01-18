"""
test_window.py

Just tests that the major programs in the package are all compatible with
    a psychopy stimulus window.

"""
from camstim import Window, SweepStim, Behavior, VisualObject
import pytest


@pytest.fixture(scope="module")
def window():
    w = Window()
    yield w
    # teardown
    w.close()


def test_window(window):
    window.flip()

def test_sweepstim(window):
    ss = SweepStim(window=window)

def test_behavior(window):
    b = Behavior(window=window)
    b.update(0)

def test_visual_obj(window):
    vo = VisualObject(window=window)
    vo.update(0)

import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (_TESTS, os.path.join(os.path.dirname(_TESTS), "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from helpers import SYNTH, SYNTH_B  # noqa: E402


@pytest.fixture(scope="session")
def device():
    from etk_core.svd import load_device

    return load_device(SYNTH)


@pytest.fixture(scope="session")
def device_b():
    from etk_core.svd import load_device

    return load_device(SYNTH_B)

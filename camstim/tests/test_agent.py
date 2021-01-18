"""

"""
import pytest
import time

from camstim.zro.agent import Agent

TEST_SCRIPT = """
import sys
import json
print("HELLO TEST")
param_file = sys.argv[1]
"""

PARAMS = {
    "test_param": 5,
}

LONG_SCRIPT = """
import time
time.sleep(10.0)
"""


@pytest.fixture(scope='module')
def agent():
    return Agent()


def _wait_for_completion(agent):
    t0 = time.clock()
    while agent.is_running():
        if time.clock() - t0 > 10.0:
            raise Exception("Test script never completed.")
        time.sleep(0.01)


def test_status(agent):
    agent.status
    agent.elapsed_time
    agent.start_script(TEST_SCRIPT, PARAMS)
    _wait_for_completion(agent)
    assert agent.returncode == 0


def test_io(tmpdir, agent):
    script_path = str(tmpdir) + "test.py"
    with open(script_path, 'w') as f:
        f.write(TEST_SCRIPT)
    agent.start_script(script_path, PARAMS)
    _wait_for_completion(agent)
    assert agent.returncode == 0

    copy_path = str(tmpdir) + "copy.py"
    agent.copy_arbitrary_file(script_path, copy_path)

def test_kill(agent):
    agent.start_script(LONG_SCRIPT)
    agent.kill_script()
    _wait_for_completion(agent)
    assert agent.returncode == 1


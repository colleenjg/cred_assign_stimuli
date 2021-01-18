"""
test_translator.py

This trial translator is used to convert foraging2-style trials to
    foraging1-style trials for backwards compatibility.

"""
import os
import pickle
import pytest

from camstim.translator import TrialTranslator

NEW_TRIAL = {
    'index': 2,
    'rewards': [(27.841424298714276, 1208)],
    'success': True,
    'stimulus_changes': [('im037', 'im053', 'im053', 1195, 27.62538964595279)],
    'licks': [(27.84083197013925, 1208)],
    'cumulative_volume': 0.024,
    'cumulative_rewards': 3,
    'trial_params': {'catch': False, 'auto_reward': False, 'change_time': 0.714659882515285},
    'events': [
        ['initial_blank', 'enter', 24.5573796492532, 1012],
        ['pre_change', 'enter', 24.558120316613483, 1012],
        ['initial_blank', 'exit', 24.557770770894596, 1012],
        ['stimulus_window', 'enter', 26.8076471980138, 1146],
        ['pre_change', 'exit', 26.80728533350306, 1146],
        ['stimulus_changed', '', 27.6257284127288, 1196],
        ['response_window', 'enter', 27.774681597726772, 1204],
        ['hit', '', 27.841401714262542, 1208],
        ['response_window', 'exit', 29.643072245094682, 1316],
        ['no_lick', 'exit', 32.81303204990343, 1485]
        ]
    }

@pytest.fixture
def translator():
    return TrialTranslator()

def test_translator(translator):
    t = translator
    old_trial = t.translate_trial(NEW_TRIAL)
    assert old_trial['rewarded'] == True
    assert old_trial['startframe'] == 1012
    assert old_trial['auto_rewarded'] == False

def test_translate_file(tmpdir, translator):
    t = translator
    path = "example_output.pkl"
    out_path = str(tmpdir) + "/output.pkl"
    with open(path, 'rb') as f:
        exp_data = pickle.load(f)
    new_trials = t.find_trial_logs(exp_data)
    old_trial_log = t.translate_file(path, out_path)
    assert len(new_trials) == len(old_trial_log)

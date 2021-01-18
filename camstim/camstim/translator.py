"""
translator.py

Translates new-style trials into old ones.

Useful for backwards compatibility with old behavior code.

"""
import datetime
import pickle

import numpy as np


class TrialTranslator(object):
    """ 
    """
    def __init__(self, task=None):
        self._task = task

    def translate_trial(self, new_trial):
        """ Creates an old-style (forating 1) trial out of a new trial
            so that we use the same analysis code.
            This is only temporary.
        """
        old_trial = {}
        old_trial['cumulative_volume'] = new_trial['cumulative_volume']
        old_trial['cumulative_reward_number'] = new_trial.get(
            'cumulative_rewards', 0)
        old_trial['publish_time'] = str(datetime.datetime.now())
        old_trial['response_type'] = []
        old_trial['response_latency'] = None
        old_trial['stim_on_frames'] = []
        old_trial['rewarded'] = True if len(
            new_trial['rewards']) > 0 else False
        old_trial['initial_contrast'] = None
        old_trial['change_contrast'] = None
        old_trial['index'] = new_trial['index']
        old_trial['auto_rewarded'] = old_trial['rewarded'] and new_trial['trial_params']['auto_reward']
        old_trial['change_time'] = new_trial['stimulus_changes'][-1][-1] if new_trial['stimulus_changes'] else None
        old_trial['starttime'] = new_trial['events'][0][-2]
        old_trial['startframe'] = new_trial['events'][0][-1]
        old_trial['reward_frames'] = [r[1] for r in new_trial['rewards']]
        old_trial['reward_times'] = [r[0] for r in new_trial['rewards']]
        old_trial['lick_times'] = [l[0] for l in new_trial['licks']]
        old_trial['scheduled_change_time'] = new_trial['trial_params']['change_time']
        old_trial['response_latency'] = None
        old_trial['optogenetics'] = False
        return old_trial

    def translate_log(self, trial_log):
        """ Translates a list of trials """
        translated = []
        for trial in trial_log:
            translated.append(self.translate_trial(trial))
        return translated

    def find_trial_logs(self, exp_data):
        """ In case we discover trials from older/newer versions keep trials
                in other places.
            For now just go to where they are now.
        """
        return exp_data['items']['behavior']['trial_log']

    def find_params(self, exp_data):
        """ Finds params dictionary.
        """
        return exp_data['items']['behavior']['params']

    def find_vsyncs(self, exp_data):
        """ Finds stimulus vsync intervals.
        """
        intervals = exp_data['items']['behavior'].get('intervalsms', [])
        if len(intervals) == 0:
            # ran headless (no graphics)
            vsyncs = exp_data['items']['behavior']['update_count']
            intervals = [16.0] * vsyncs
        return intervals

    def find_rewards(self, exp_data):
        """ Finds array of reward [time, frame]
        """
        trials = self.find_trial_logs(exp_data)
        rewards = np.array([t['rewards'][0] for t in trials if t['rewards']],
                           dtype=np.float)
        return rewards

    def find_licks(self, exp_data):
        """ Finds frames where licks occurred?
        """
        trials = self.find_trial_logs(exp_data)
        licks = [t['licks'][0][1] for t in trials if t['licks']]
        return licks

    def find_dx(self, exp_data):
        """ Finds wheel rotation for each frame.
        """
        return exp_data['items']['behavior']['encoders'][0]['dx']

    def make_stim_log(self, exp_data):
        """
        """
        vsyncs = exp_data['items']['behavior']['update_count']
        draw_log = exp_data['items']['behavior']['stimuli'].items()[0][1]['draw_log'] #GROSS
        log = []
        for i in range(vsyncs):
            entry = {
                'frame': i,
                'state': bool(draw_log[i]),
                'ori': 0,
            }
            log.append(entry)
        return log

    def make_response_log(self, exp_data):
        """ 
        """
        licks = self.find_licks(exp_data)
        log = [{'frame': i} for i in licks]
        return log

    def translate_file(self, new_data, output_path=""):
        """ 
        """
        if isinstance(new_data, str):
            # TODO: prepare for non-pickle files? zipped files?
            with open(new_data, 'rb') as f:
                data = pickle.load(f)

        try:
            data['items']['behavior']
        except KeyError:
            data = {'items': {'behavior': data,},}

        trial_log = self.find_trial_logs(data)
        params = self.find_params(data)
        vsyncs = self.find_vsyncs(data)
        rewards = self.find_rewards(data)
        dx = self.find_dx(data)
        stim_log = self.make_stim_log(data)
        response_log = self.make_response_log(data)

        old_trial_log = self.translate_log(trial_log)
        if output_path:
            with open(output_path, 'wb') as f:
                pickle.dump({
                    'triallog': old_trial_log,
                    'new_trial_log': trial_log,
                    'params': params,
                    'vsyncintervals': vsyncs,
                    'rewards': rewards,
                    'dx': dx,
                    'stimuluslog': stim_log,
                    'responselog': response_log,
                }, f)
        return old_trial_log

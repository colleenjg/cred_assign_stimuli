"""
Change detection module.  Contains base classes for change
    detection task.
"""

import time
import datetime
import numpy as np
import os
import sys
import ConfigParser
import io
import random
import itertools
import json
import pickle
import zipfile
import string
from collections import OrderedDict

from psychopy import visual
from pyglet.window import key
from qtpy import QtCore
Signal = QtCore.Signal
import numpy as np

from .behavior import Epoch, TrialGenerator, Task, VisualObject, DummyPsycopyStimulus
from .misc import get_config, check_dirs, CAMSTIM_DIR, get_platform_info,\
    save_session, ImageStimNumpyuByte  # TODO:rename these??
from .experiment import EObject, Timetrials, Experiment, ETimer
from .lims import LimsInterface, LimsError, BehaviorTriggerFile
from .translator import TrialTranslator

import logging

class DoCTask(Task):
    """
    DoC Task skeleton.
    """
    startingCatchTrial = Signal()
    startingGoTrial = Signal()
    startingTrial = Signal()
    trialEnded = Signal()

    hitOccurred = Signal()
    autoRewardOccurred = Signal()
    missOccurred = Signal()
    earlyResponseOccurred = Signal()
    falseAlarmOccurred = Signal()
    rejectionOccurred = Signal()
    abortOccurred = Signal()

    changeOccurred = Signal()
    shamChangeOccurred = Signal()

    def __init__(self,
                 *args,
                 **kwargs
                 ):
        super(DoCTask, self).__init__(*args, **kwargs)

        self.config["DoC"] = self.load_config("DetectionOfChange",
                                              override=self.params)
        self._doc_config = self.config["DoC"]

        self._trial_generator = DoCDefaultTrialGenerator(
            warm_up_trials=self._doc_config['warm_up_trials'])
        self._doc_stimulus = None
        self._current_trial_params = {}
        self._current_trial_data = {}
        self.trial_log = []
        self.trial_count = 0

        self._epochs = []
        self._active_epochs = []
        self._event_log = []
        self._starting_epoch = None

        # state variables
        self._in_catch_trial = False
        self._success = None
        self._last_lick = 0.0
        self._trial_licks = []
        self._trial_rewards = []
        self._trial_changes = []

        ## TODO: handle multiple lick sensors
        self.lick_sensors[0].lickOccurred.connect(self._lick_event)

        self._setup_default_epochs()
        self._setup_safety_timer()
        self._setup_remote_interface()


    def _setup_default_epochs(self):
        initial_blank = self._doc_config['initial_blank']
        self._blank_epoch = DoCNoStimEpoch(self,
                                           duration=initial_blank,
                                           name="initial_blank")

        pre_change_time = self._doc_config['pre_change_time']
        self._pre_change_epoch = DoCMinPrechange(self,
                                                 duration=pre_change_time,
                                                 name="pre_change")

        sw_dur = self._doc_config['stimulus_window']
        self._stimulus_window_epoch = DoCStimulusWindow(self,
                                                        duration=sw_dur,
                                                        name="stimulus_window")

        rw = self._doc_config['response_window']
        rw_dur = rw[1]-rw[0]
        rw_delay = rw[0]
        self._response_window_epoch = DoCResponseWindow(self,
                                                        duration=rw_dur,
                                                        delay=rw_delay,
                                                        name="response_window")

        nl_dur = self._doc_config['min_no_lick_time']
        self._no_lick_epoch = DoCMinNoLickEpoch(self,
                                                duration=nl_dur,
                                                name="no_lick")

        timeout_dur = self._doc_config['timeout_duration']
        self._timeout_epoch = DoCTimeoutEpoch(self,
                                              duration=timeout_dur,
                                              name="timeout")

        for epoch in  [self._blank_epoch,
                       self._pre_change_epoch,
                       self._stimulus_window_epoch,
                       self._response_window_epoch,
                       self._no_lick_epoch,
                       self._timeout_epoch
                       ]:
            self.add_epoch(epoch)

        # epocs that automatically transition to each other
        self._blank_epoch.epochEnded.connect(self._pre_change_epoch.enter)
        self._pre_change_epoch.epochEnded.connect(self._stimulus_window_epoch.enter)
        self._stimulus_window_epoch.epochEnded.connect(self._no_lick_epoch.enter)

        self.set_starting_epoch(self._blank_epoch)

    def _setup_safety_timer(self):
        """sets up a safety timer to provide a maximum trial length in case
            of edge cases. """
        self._safety_timer = ETimer()
        self._safety_timer.setSingleShot(True)
        self._safety_timer.timeout.connect(self._safety_timer_timeout)

    def _setup_remote_interface(self):
        """ sets up a remote interface.
        """
        try:
            from camstim.zro.remote import DoCRemoteControl
            self._remote_interface = DoCRemoteControl(task=self)
            self.add_item(self._remote_interface, "remote_interface")
            # TODO: remove TrialTranslator when we don't care about
            # backwards compatibility
            if self._doc_config['trial_translator']:
                self._trial_translator = TrialTranslator()
            else:
                self._trial_translator = None
        except Exception as e:
            self._remote_interface = None
            self._trial_translator = None
            logging.warning("Failed to create remote interface: {}".format(e))

    def _safety_timer_start(self):
        st_dur = self._doc_config["safety_timer_padding"] + \
            self.expected_trial_duration
        self._safety_timer.start(st_dur)

    def _safety_timer_timeout(self):
        """ Callback for safety timer. """
        self._log_msg("Safety timer triggered!", logging.info)
        self._end_trial()

    def set_starting_epoch(self, epoch):
        self._starting_epoch = epoch

    def set_trial_generator(self, generator):
        self._trial_generator = generator
        self._trial_generator._task = self

    def set_stimulus(self, stimulus, name=""):
        self._doc_stimulus = stimulus
        flash = self._doc_config['periodic_flash']
        self._doc_stimulus.set_periodic_flash(flash)
        self._doc_stimulus.changeOccurred.connect(self._change_event)
        self.add_stimulus(stimulus, name)

    def add_epoch(self, epoch):
        epoch.epochStarted.connect(self._epoch_started)
        epoch.epochEnded.connect(self._epoch_ended)
        self._epochs.append(epoch)

    def _lick_event(self):
        # send lick even to all active epochs
        t = time.clock()
        self._last_lick = t
        self._trial_licks.append((t, self.update_count))
        for epoch in self._active_epochs:
            epoch._lick_event()

    def _next_trial(self):
        """ Called to initial the next trial. """
        self._clear_trial_data()
        self._current_trial_params = self._get_next_trial()
        self._setup_trial(self._current_trial_params)
        self.startingTrial.emit()

        self._safety_timer_start()

        if self._starting_epoch:
            self._starting_epoch.enter()
        
    def _setup_trial(self, trial):
        """ Sets up trial parameters """
        logging.debug("trial params: {}".format(trial))
        self._current_trial_data.update({"trial_params": trial})
        if trial.get("catch", False):
            self._start_catch_trial()
        else:
            self._start_go_trial()
        self._apply_trial(trial)

    def _apply_trial(self, trial):
        """ Applies trial parameters. """
        change_time = trial.get("change_time", None)
        self._stimulus_window_epoch._change_time = change_time

    def _start_catch_trial(self):
        """ called when a catch trial starts """
        logging.debug("Starting catch trial.")
        self._in_catch_trial = True
        self.startingCatchTrial.emit()

    def _start_go_trial(self):
        """ called when a go trial starts """
        logging.debug("Starting go trial.")
        self._in_catch_trial = False
        self.startingGoTrial.emit()

    def change(self, next_flash_start=True):
        """ tell the stimulus to change """
        if not self._doc_stimulus.is_flashing():
            # don't want to wait for next flash if it isn't flashing
            next_flash_start = False
        if next_flash_start:
            self._doc_stimulus.on_next_flash(self._response_window_epoch.enter)
            self._response_window_epoch.set_active(True)
        else:
            self._response_window_epoch.enter()
        if not self._in_catch_trial:
            self._doc_stimulus.change(next_flash_start=next_flash_start)
        else:
            self._doc_stimulus.on_next_flash(self._sham_change_event)

    def stim_on(self):
        """ Turns the stimulus on """
        self._doc_stimulus.on()

    def stim_off(self):
        """ Turns the stimulus off """
        self._doc_stimulus.off()

    def clear_epochs(self):
        for epoch in self._epochs:
            epoch.kill()

    def _get_next_trial(self):
        return self._trial_generator.next()

    def start(self):
        """ Starts the task. """
        super(DoCTask, self).start()
        self._next_trial()

    def _register_result(self, event, success, signal=None):
        """ Registers a trial result, success boolean, and a signal to call.
        """
        self._log_msg(event.upper(), logging.info)
        self._log_event(event.lower())
        self._success = success
        if signal:
            signal.emit()

    #### Possible Trial Results #############
    ## TODO: should these be objects?

    def _abort(self):
        """ Trial aborted for various reasons. """
        self._register_result("abort", False, self.abortOccurred)
        self._abort_default_handler()

    def _miss(self):
        """ Mouse didn't lick in go trial. """
        self._register_result("miss", False, self.missOccurred)
        self._miss_default_handler()

    def _hit(self):
        """ Mouse licked at correct time. """
        self._register_result("hit", True, self.hitOccurred)
        self._hit_default_handler()

    def _auto_reward(self):
        """ Automatic reward events have a special reward volume """
        self._register_result("auto_reward", True, self.autoRewardOccurred)
        self._auto_reward_default_handler()

    def _rejection(self):
        """ Mouse witheld during catch trial """
        self._register_result("rejection", True, self.rejectionOccurred)
        self._rejection_default_handler()

    def _false_alarm(self):
        """ Mouse responded during catch trial """
        self._register_result("false_alarm", False, self.falseAlarmOccurred)
        self._false_alarm_default_handler()

    def _early_response(self):
        """ Mouse responded too early. """
        self._register_result("early_response", False, self.earlyResponseOccurred)
        self._early_response_default_handler()

    #### Default Result Handlers ############
    ## TODO: move theses into result objects?

    def _abort_default_handler(self):
        self.clear_epochs()
        self._doc_stimulus.clear_events()
        self._doc_stimulus.clear_changes()
        self._timeout_epoch.enter()

    def _miss_default_handler(self):
        pass

    def _hit_default_handler(self):
        self.issue_reward(0)  # index should come from where?

    def _early_response_default_handler(self):
        self._abort()

    def _false_alarm_default_handler(self):
        #self._abort() # task amended to not abort on false alarms.
        pass

    def _rejection_default_handler(self):
        pass

    def _auto_reward_default_handler(self):
        temp_vol = self._doc_config['auto_reward_volume']
        self.issue_reward(0, temp_vol)

    #########################################

    def _change_event(self, event):
        self._trial_changes.append(event)
        self._log_msg("STIMULUS CHANGED", logging.info)
        self._log_event("stimulus_changed")
        if self._current_trial_data['trial_params']['auto_reward']:
            self._auto_reward()
        self.changeOccurred.emit()

    def _sham_change_event(self):
        self._log_msg("SHAM STIMULUS CHANGE", logging.info)
        self._log_event("sham_change")
        self.shamChangeOccurred.emit()

    def issue_reward(self, index=0, volume=None):
        """ Issues a reward to the specified reward line. """
        t = time.clock()
        self._trial_rewards.append((t, self.update_count))
        if self.rewards:
            self.rewards[index].reward(volume)
        else:
            logging.warning("Issued reward to virtual reward line {}".format(index))

    def _end_trial(self):
        """ trial is over. cleanup, log, and start the next one. """
        self._trial_ended()
        self._log_trial()

        self.trial_count += 1

        max_task_duration_min = self._doc_config['max_task_duration_min']
        if max_task_duration_min*60.0 < time.clock():
            logging.info("Task reached max duration of {} minutes".format(max_task_duration_min))
            self._close()
        else:
            ## TODO: make this optional
            if self._doc_stimulus.is_flashing():
                self._doc_stimulus.on_next_flash(self._next_trial)
            else:
                self._next_trial()

    def _trial_ended(self):
        """ called at the end of a trial (regardless of how it ended.) """
        logging.debug("Trial ended.")
        self.trialEnded.emit()

    def _log_trial(self):
        """ log trial data """
        trial_data = {
            "events": self._event_log,
            "licks": self._trial_licks,
            "rewards": self._trial_rewards,
            "stimulus_changes": self._trial_changes,
            "index": self.trial_count,
            'success': self._success,
            'cumulative_volume': self.volume_dispensed,
            'cumulative_rewards': self.rewards_dispensed,
        }
        self._current_trial_data.update(trial_data)
        self.trial_log.append(self._current_trial_data)
        if self._remote_interface:
            #### Remove translation after OAG update
            if self._trial_translator:
                trial_data = self._trial_translator.translate_trial(self._current_trial_data)
                logging.debug("Trial translated.")
            ######################################## 
            self._remote_interface.publish(trial_data)
            logging.debug("Published trial to sink.")
        logging.info("Trial data: {}".format(self._current_trial_data))
        self._clear_trial_data()

    def _clear_trial_data(self):
        self._event_log = []
        self._trial_licks = []
        self._trial_rewards = []
        self._trial_changes = []
        self._current_trial_data = {}
        self._success = None

    def check_for_completion(self):
        if self.is_trial_finished():
            self._end_trial()

    def is_trial_finished(self):
        #here we determine if a trial is finished
        if self._active_epochs:
            return False
        elif self._doc_stimulus._scheduled_on_flash:
            return False
        else:
            return True

    def _epoch_started(self, t=None):
        name = self.sender().name
        self._log_event(name, "enter", t)

    def _epoch_ended(self, t=None):
        name = self.sender().name
        self._log_event(name, "exit", t)

    def _log_event(self, name, direction="", t=None):
        """ Logs an event. """
        self._event_log.append(self._build_event(name, direction, t))


    def _build_event(self, name, direction="", t=None):
        """ Builds an event to log. Should events be a class? """
        clock, frame = self._timepoint
        return [name, direction, t or clock, frame]

    @property
    def _timepoint(self):
        return time.clock(), self.update_count

    @property
    def expected_trial_duration(self):
        return sum([epoch.duration for epoch in self._epochs])

    def _log_msg(self, message, level=logging.debug):
        level("{} - {}".format(self.update_count, message))

    def _close(self):
        if self._remote_interface:
            logging.info("PUBLISHING FOOTER")
            self._remote_interface.publish_footer()
        super(DoCTask, self)._close()


########################################################
# EPOCHS
########################################################


class DoCEpoch(Epoch):
    """ A DoC Epoch.  Handles lick events from Task. """
    def _lick_event(self):
        pass

class DoCNoStimEpoch(DoCEpoch):
    """ DoC Epoch that disables stimulus flashing. """
    def _lick_event(self):
        self._task._early_response()

    def _on_entry(self):
        self._task.stim_off()

    def _on_exit(self):
        self._task.stim_on()

class DoCResponseWindow(DoCEpoch):
    """ A response window for Detection of Change.  Gives up to one reward. """
    def __init__(self, *args, **kwargs):
        super(DoCResponseWindow, self).__init__(*args, **kwargs)
        self._available = False
        self._rewarded = False
        self._false_alarm = False

    def _on_entry(self):
        self._available = True
        self._false_alarm = False

        # prevents mouse from getting a reward after an
        # auto reward.  do we want to do this?
        if self._task._trial_rewards:
            self._rewarded = True
        else:
            self._rewarded = False

    def _lick_event(self):
        if self._task._in_catch_trial:
            if not self._false_alarm:
                self._false_alarm = True
                self._task._false_alarm()
        else:
            if not self._rewarded:
                if self._available:
                    self._task._hit()
                    self._available = False
                    self._rewarded = True

    def _on_exit(self):
        self._available = False
        if not self._task._in_catch_trial:
            if not self._rewarded:
                self._task._miss()
        else:
            if not self._false_alarm:
                self._task._rejection()

        self._task.check_for_completion()


class DoCStimulusWindow(DoCEpoch):
    def __init__(self, *args, **kwargs):
        super(DoCStimulusWindow, self).__init__(*args, **kwargs)
        self._change_time = None
        self._change_timer = ETimer()
        self._change_timer.setSingleShot(True)
        self._change_timer.timeout.connect(self._trigger_change)
        self._after_change = False
        self._task.changeOccurred.connect(self._change_handler)
        self._task.shamChangeOccurred.connect(self._change_handler)

    def _on_entry(self):
        if self._change_time:
            self._change_timer.start(self._change_time)
        self._after_change = False

    def _trigger_change(self):
        """ Triggers the scheduled 'change'. May not happen, though,
                until next flash.
        """
        self._task.change()
        #self._after_change = True

    def _change_handler(self):
        self._after_change = True

    def _lick_event(self):
        if not self._after_change:
            self._task._early_response()
        else:
            pass

    def kill(self):
        self._change_timer.stop()
        super(DoCStimulusWindow, self).kill()

    def _on_exit(self):
        self._task.check_for_completion()

class DoCMinPrechange(DoCEpoch):
    def _lick_event(self):
        self._task._early_response()

class DoCMinNoLickEpoch(DoCEpoch):
    def _lick_event(self):
        """ Any lick event should reset the timer. """
        self.reset()

    def enter(self):
        """ Epoch entry override because duration is dependent on last lick. """
        logging.debug("Entering epoch: {}".format(self.name))
        self._active = True
        self._on_entry()

        t = time.clock()
        since_last_lick = t - self._task._last_lick
        if since_last_lick < self.duration:
            self._epoch_timer.start(self.duration-since_last_lick)
            self.entries.append(t)
            self.epochStarted.emit(t)
        else:
            self.exit()

    def _on_exit(self):
        self._task.check_for_completion()

class DoCTimeoutEpoch(DoCEpoch):
    def _lick_event(self):
        self.reset()

    def _on_exit(self):
        self._task.check_for_completion()

############################################################
# TRIAL GENERATORS
############################################################


class DoCDefaultTrialGenerator(TrialGenerator):
    """ Minimal Trial Generator for Detection of Change
    """
    def __init__(self, sequence=None, task=None, warm_up_trials=0):
        super(DoCDefaultTrialGenerator, self).__init__(sequence, task)

        self.warm_up_trials = warm_up_trials

        self.add_random_param("catch", [True, False])
        self.add_random_param("change_time", [1.0, 2.0, 3.0, 4.0])
        self.add_random_param("auto_reward", [False])

    def next(self):
        trial = super(DoCDefaultTrialGenerator, self).next()
        if self.warm_up_trials != 0:
            trial['auto_reward'] = True
            trial['catch'] = False
            self.warm_up_trials -= 1
        return trial

class DoCTrialGenerator(TrialGenerator):
    """ Fancy Trial Generator.  This is where all of the logic
            behind trial parameter generation lives.
    """
    def __init__(self, task=None, cfg={}):
        super(DoCTrialGenerator, self).__init__(task=task)

        self.catch_freq = cfg.get("catch_freq", 0.5)
        self.warm_up_trials = cfg.get("warm_up_trials", 0)
        self.change_time_dist = cfg.get("change_time_dist", "exponential")
        self.change_time_scale = cfg.get("change_time_scale", 2)
        self.free_reward_trials = cfg.get("free_reward_trials", 10)
        self.failure_repeats = cfg.get("failure_repeats", 10)

        self.add_random_param("catch", self._pick_catch)
        self.add_random_param("change_time", self._pick_change_time)
        self.add_random_param("auto_reward", self._pick_auto_reward)

        self._last_trial = {}
        self._repeats = 0
        self._trials_since_lick = 0

    def _pick_change_time(self):
        """ Picks a change time. 

            Returns:
                float
        """
        stim_window = self._task._doc_config['stimulus_window']
        if self.change_time_dist == "exponential":
            t = np.random.exponential(self.change_time_scale)
            if t < stim_window:
                return t
            else:
                # pick a different one
                return self._pick_change_time()
        else:
            # uniform?
            t = np.random.random() * stim_window
            return t

    def _pick_auto_reward(self):
        """ Picks auto reward.

            Returns:
                bool
        """
        if self.warm_up_trials != 0:
            self.warm_up_trials -= 1
            return True
        else:
            return False

    def _pick_catch(self):
        r = np.random.random()
        if r < self.catch_freq:
            return True
        else:
            return False

    def _previous_trial_result(self):
        """ Returns true if previous trial was a success.
        """
        if self._task.trial_log:
            prev = self._task.trial_log[-1]
            if prev['success']:
                return True
        else:
            return True
        return False

    def _lick_training(self):
        """ updates no_lick counter
        ##TODO: think of a better way to get last trial
        """
        if self._task.trial_log:
            prev = self._task.trial_log[-1]
            licks = prev.get("licks", [])
            if licks:
                self._trials_since_lick = 0
            else:
                self._trials_since_lick += 1

    def next(self):
        """ Automatically called by the task to get the next trial.
        """
        if self._previous_trial_result() or (self._repeats >= self.failure_repeats):
            self._repeats = 0
            return self.new()
        else:
            self._repeats += 1
            logging.info("Repeating previous trial.")
            return self._last_trial

    def _condition_trial(self, trial):
        """ Last minute trial conditioning.
        """
        self._lick_training()
        if self._trials_since_lick >= self.free_reward_trials:
            trial['auto_reward'] = True
            self._trials_since_lick = 0
        # always want auto_reawrd trials to be "go" trials
        # TODO: think of a better way to handle this parameter "coupling"
        if trial['auto_reward']:
            trial['catch'] = False
        return trial

    def new(self):
        """ Gets a new trial.
        """
        trial = super(DoCTrialGenerator, self).next()
        self._last_trial = trial
        return trial



############################################################
# STIM OBJECTS
############################################################


class DoCStimulus(VisualObject):
    """ 
    """
    changeOccurred = Signal(tuple)

    def __init__(self,
                 stimulus=None,
                 *args,
                 **kwargs
                 ):
        super(DoCStimulus, self).__init__(stimulus=stimulus, *args, **kwargs)

        self.stim_groups = OrderedDict()
        self._current_group = ""
        self._current_item = 0
        self._current_value = None

        self._tweak_on_flash = False
        self._tweak_randomize = True # otherwise will iterate

        self._scheduled_tweaks = []
        self._scheduled_changes = []
        self._scheduled_on_flash = []
        self._scheduled_on_change = []

        self._change_log = []
        self._tweak_log = []

    @property
    def tweak_on_flash(self):
        return self._tweak_on_flash

    @tweak_on_flash.setter
    def tweak_on_flash(self, value):
        self._tweak_on_flash = value

    def is_flashing(self):
        return self._periodic_flash

    def _on_flash_start(self):
        """ Occurs at the start of a flash.
        """
        #logging.debug("Flash started!")
        if self._scheduled_on_flash:
            while self._scheduled_on_flash:
                call = self._scheduled_on_flash.pop()
                call()
        if self._scheduled_changes:
            group_name = self._scheduled_changes.pop()
            self.change(group_name, False)
        elif self._scheduled_tweaks:
            random_item = self._scheduled_tweaks.pop()
            self.tweak(False, random_item)
        elif self.tweak_on_flash:
            self.tweak(False, random_item=self._tweak_randomize)

    def _on_flash_end(self):
        """ Occurs at the end of a flash.
        """
        #logging.debug("Flash ended!")
        pass

    def _on_change(self):
        """ Called when a change occurs.
        """
        if self._scheduled_on_change:
            while self._scheduled_on_change:
                call = self._scheduled_on_change.pop()
                call()
        
    def change(self, group_name="", next_flash_start=True):
        """ Change the stimulus group.
        """
        current_group = self._current_group
        current_val = self._current_value

        if next_flash_start:
            self._scheduled_changes.append(group_name)
            return
        if group_name:
            new_val = self.set_group(group_name)
        else:
            # get a random group different from the current one
            group_names = self.stim_groups.keys()
            if len(group_names) > 1:
                group_names.remove(self._current_group)
            group_name = random.choice(group_names)
            new_val = self.set_group(group_name)
        event = ((current_group, current_val), (group_name, new_val),
                 time.clock(), self.update_count)
        self._on_change()
        self.changeOccurred.emit(event)
        self._change_log.append(event)
        logging.debug("Stimulus group changed!")

    def change_later(self, seconds, group_name="", next_flash_start=True):
        """ Change at a future time.
        ??unnecessary?
        """
        ms = int(seconds*1000)
        
    def on_next_flash(self, to_call):
        """ Schedule a call for the next flash.
        """
        self._scheduled_on_flash.append(to_call)

    def on_next_change(self, to_call):
        """ Scheduled a call for the next change.
        """
        self._scheduled_on_change.append(to_call)

    def clear_events(self):
        self._scheduled_on_flash = []

    def clear_changes(self):
        self._scheduled_changes = []

    def events_pending(self):
        """ Returns the numer of scheduled events and/or changes.
        """
        return len(self._scheduled_on_flash) + len(self._scheduled_changes)

    def tweak(self, next_flash_start=True, random_item=True):
        """ Change the stimulus to a different item in same group.
        """
        if next_flash_start:
            self._scheduled_tweaks.append(random_item)
        param, vals = self.stim_groups[self._current_group]
        if random_item:
            val = random.choice(vals)
        else:
            self._current_item += 1
            self._current_item %= len(vals)
            val = vals[self._current_item]
            self._current_value = val
        #logging.debug("Stim tweaked: ({}, {})".format(param, val))
        self.set_stim_param(param, val)
        return val


    def add_stimulus_group(self, group_name, param, values):
        """ Add a stimlus group (category)

            args:
                group_name (str): name for the stimulus group
                param (str): stim parameter to modify
                values (iterable): potential values

            Example:
                >>> stim.add_stimulus_group("image_set_one",
                                            "Image",
                                            ['img0.png', 'img1.png', 'img2.png'])
        """
        self.stim_groups[group_name] = (param, values)
        if not self._current_group:
            self._current_group = group_name

    def set_group(self, group_name):
        """ Sets the group by name. """
        group = self.stim_groups[group_name]
        self._current_group = group_name
        new_val = self.tweak(next_flash_start=False)
        logging.debug("Stim group set to: {}".format(group_name))
        return new_val

    def set_stim_param(self, param, value):
        """ Sets the parameter to a specified value. """
        try:
            setter = getattr(self.stimulus, "set%s" % param)
            setter(value)
        except AttributeError:
            logging.warning("Tried to set visual stim property.")
        self._tweak_log.append((value, self.update_count, time.clock()))
        logging.debug("Stimulus {} set to: {}".format(param, value))


class DoCGratingStimulus(DoCStimulus):
    def __init__(self,
                 window=None,
                 tex="sqr",
                 sf=0.1,
                 ori=0.0,
                 phase=(0.0,0.0),
                 contrast=1.0,
                 opacity=1.0,
                 mask='none',
                 pos=(0,0),
                 size=None,
                 units="deg",
                 **kwargs):
        self.pos = pos
        self.size = size
        self.units = units
        self._window = window

        if self._window:
            stim = visual.GratingStim(window,
                                      tex=tex,
                                      sf=sf,
                                      ori=ori,
                                      phase=phase,
                                      contrast=contrast,
                                      opacity=opacity,
                                      mask=mask,
                                      pos=pos,
                                      size=size,
                                      units=units)
        else:
            stim = DummyPsycopyStimulus()
        super(DoCGratingStimulus, self).__init__(stim)


class DoCImageStimulus(DoCStimulus):
    """ DoC Stimulus optimized for image sets. 
    
    As of right now, image sets are of this shape:

        {"group0_name": {"image0_name": image0_data, 
                         "image1_name": image_1data},
         "group1_name" ....
        }

    OR a path to pickled data of this shape.

    #TODO: refactor to remove any duplication with DoCStimulus
    """
    def __init__(self,
                 window=None,
                 image_set="",
                 sampling="random",
                 sequence=None,
                 pos=(0,0),
                 size=None,
                 units="pix",
                 **kwargs
                 ):
        self.pos = pos
        self.size = size
        self.units = units
        self.sampling = sampling
        self.sequence = sequence
        
        self._window = window

        self._initialized = False

        super(DoCImageStimulus, self).__init__(**kwargs)

        self.image_walk = []
        if image_set:
            self.load_image_set(image_set)
        

    def start(self):
        if not self._initialized:
            raise RuntimeError("Stimulus uninitialized. No stimulus group added.")
        super(DoCImageStimulus, self).start()

    def _initialize(self):
        _, images = self.stim_groups[self._current_group]
        init_img_name, init_img = images[0]
        self._current_value = init_img_name
        if (self.size is None) and (self.units == 'pix'):
            self.size = (init_img.shape[1], init_img.shape[0])
        if self._window:
            self.stimulus = ImageStimNumpyuByte(self._window,
                                                image=init_img,
                                                pos=self.pos,
                                                units=self.units,
                                                size=self.size,
                                                flipHoriz=False,
                                                flipVert=True,
                                                )
        else:
            self.stimulus = DummyPsycopyStimulus()
        self._initialized = True

    def load_image_set(self, image_set):
        """ Load in an image set.
        
        Loads an image set in the format used by Behavior team prototype.
        ##TODO: review this image set format and make image set loading more general.
        """
        if isinstance(image_set, str):
            self.image_path = image_set
            if image_set.endswith(".zip"):
                # image data is zipped
                with zipfile.ZipFile(image_set, 'r') as myzip:
                    inner_path = image_set.replace(".zip", ".pkl")
                    with myzip.open(os.path.basename(inner_path)) as f:
                        self._image_set = pickle.load(f)
            else:
                # not zipped
                with open(image_set, 'rb') as f:
                    self._image_set = pickle.load(f)
            for group_name, group in self._image_set.items():
                images = group.items()
                self.add_stimulus_group(group_name, images)
        if self.sampling in ['even', 'file']:
            # TODO: fix hard-coded path here.  where should this live?
            num_groups = len(list(self._image_set.items()))
            path = self.sequence or "//allen/aibs/mpe/Software/stimulus_files/sequences/paths_for_even_matrix_sampling_n={}.csv".format(num_groups)
            self.sampling_matrix = np.loadtxt(path, delimiter=",", dtype='|S2')
            self._category_codes = [string.ascii_lowercase[n] for n in range(num_groups)]
            self._select_image_walk()
            #import pdb;pdb.set_trace()

    def _select_image_walk(self):
        """ Choose a random image walk from sampling matrix
        """
        self._current_walk = self.sampling_matrix[:, np.random.randint(low=0, high=self.sampling_matrix.shape[1])]
        self.image_walk.append(self._current_walk)
        self._walk_index = 0

    def add_stimulus_group(self, group_name, images):
        super(DoCImageStimulus, self).add_stimulus_group(group_name, "Image", images)
        if not self._initialized:
            self._initialize()

    def set_stim_param(self, param, value):
        """ Sets the parameter to a specified value. """
        image_name, image_data = value
        try:
            setter = getattr(self.stimulus, "set%s" % param)
            setter(image_data)
        except AttributeError:
            logging.warning("Tried to set visual stim property.")
        self._current_value = image_name
        self._tweak_log.append((image_name, self.update_count, time.clock()))
        logging.debug("Stimulus {} set to: {}".format(param, image_name))

    def change(self, group_name="", next_flash_start=True):
        """ Change the stimulus group.
        #TODO: remove duplication with base class
        """
        current_group = self._current_group
        current_value = self._current_value

        if next_flash_start:
            self._scheduled_changes.append(group_name)
            return
        if group_name:
            new_val = self.set_group(group_name)
        else:
            # get a random group different from the current one
            group_names = self.stim_groups.keys()
            if self.sampling == "random":
                group_names.remove(self._current_group)
                group_name = random.choice(group_names)
                new_name, new_val = self.set_group(group_name)
            else:
                #TODO: replace this with an ImageWalk object
                image_index = self._category_codes.index(self._current_walk[self._walk_index][1])
                group_name = group_names[image_index]
                new_name, new_val = self.set_group(group_name)
                self._walk_index = (self._walk_index + 1) % len(self._current_walk)

        event = ((current_group, current_value), (group_name, new_name), 
                 self.update_count, time.clock())
        self._on_change()
        self.changeOccurred.emit(event)
        self._change_log.append(event)
        logging.debug("Stimulus group changed!")

    def package(self):
        # THIS IS TO REMOVE THE NUMPY IMAGES FROM THE STIM GROUPS
        # SO WE CAN STILL SAVE WHICH IMAGES ARE IN WHICH GROUP
        self.stim_groups = [(k, [v[0] for v in v[1]])
                            for k, v in self.stim_groups.items()]
        return super(DoCImageStimulus, self).package()




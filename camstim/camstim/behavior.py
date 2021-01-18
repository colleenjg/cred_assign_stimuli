"""
Unfinished.  Attempting to create a more object-oriented extensible version of
    Foraging.

    Goals:
        - Runs with or without stimuli of any kind.
        - Add foraging objects (lick sensors, encoders, stimulus objects, etc)
            a la carte.
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
#import shutil
import zipfile
from collections import OrderedDict

import yaml
from psychopy import visual
from pyglet.window import key
from qtpy import QtCore
Signal = QtCore.Signal

from misc import get_config, check_dirs, CAMSTIM_DIR, get_platform_info,\
    save_session, ImageStimNumpyuByte  # TODO:rename these??
from experiment import EObject, Timetrials, Experiment, ETimer
from lims import LimsInterface, LimsError, BehaviorTriggerFile
from synchro import SyncPulse, SyncSquare

import logging


class BehaviorBase(EObject):
    """
    What should be in here?  Basically the skeleton of a behavior experiment.
        Stuff that should be in every type of experiment we can think of.

    Basically, it should hold the encoders, rewards, lick sensors, nidaq tasks.

    But it shouldn't impose any type of logic.

    """
    def __init__(self,
                 auto_update=False,
                 params={},
                 nidaq_tasks={},
                 ):

        super(BehaviorBase, self).__init__()

        self.cl_params = self._get_cl_params()
        self.params = self._load_kwargs(params)
        self.params.update(self.cl_params)
        self.config_path = os.path.join(CAMSTIM_DIR, "config/stim.cfg")

        self.config = {
            'behavior': self.load_config("Behavior",
                                         override=self.params),
        }

        self.encoders = []
        self.rewards = []
        self.lick_sensors = []

        self.nidaq_tasks = nidaq_tasks
        self.auto_update = auto_update
        self._setup_DAQ()

        self.update_count = 0
        self._update_timer = QtCore.QTimer()
        self._update_timer.timeout.connect(self.update)
        self._update_interval_ms = 1

        logging.info("Initilized behavior.")

    def _load_kwargs(self, params):
        """
        Loads params that will override config.  Should either be a dictionary
            of keys and values, or a path to a json or pickle file to load.
        """
        kwargs = {}
        if isinstance(params, str):
            # filename
            if params.endswith((".pkl", ".pickle")):
                # pickle file
                import pickle
                with open(params, 'rb') as f:
                    kwargs.update(pickle.load(f))
            elif params.endswith(".json"):
                with open(params) as f:
                    kwargs.update(json.load(f))
            else:
                raise IOError("Unknown param filetype. Should be json or pickle.")
        elif isinstance(params, dict):
            kwargs.update(params)
        else:
            raise IOError("params kwargs should be dict or filename.")

        if len(sys.argv) > 1:
            clarg = sys.argv[1]
            if clarg.endswith(".json"):
                logging.info("Loading parameter file: {}".format(clarg))
                try:
                    with open(clarg, "r") as f:
                        kwargs.update(json.load(f))
                except IOError as e:
                    logging.warning("Couldn't read parameter file: {}".format(e))
            else:
                logging.warning("Paramter file not a .json file.")

        return kwargs

    def _get_cl_params(self):
        """ Gets any parameters passed in by an optional json command line
                arg.
        """
        if len(sys.argv) > 1:
            json_path = sys.argv[1]
            try:
                with open(json_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning("Could not load json param file: {}".format(json_path))
                return {}
        else:
            return {}

    def start(self):
        """ Starts the behavior session.  If configured to autoupdate, it begins
            calling update at the specified interval.  Otherwise, it simply
            starts all child objects. If session does not have a parent experiment,
            it creates one.
        """
        if not self._parent:
            self._parent = Experiment()
            self._parent.add_item(self, name="behavior")
            self._parent.start()
        else:
            if self.auto_update:
                self._update_timer.start(self._update_interval_ms)

            for item in self.items.values():
                item.start()

    def update(self, index=None):
        """ Updates all encoders, rewards, lick_sensors, and any other items.

        Index can be passed in (for example if you want your items to know a
            stimulus frame number), otherwise uses its own counter.
        """
        index = index or self.update_count
        for item in self.items.values():
            item.update(index)

        for e in self.encoders:
            e.update(index)
        for r in self.rewards:
            r.update(index)
        for l in self.lick_sensors:
            l.update(index)
        self.update_count += 1

    def set_update_interval_ms(self, ms):
        self._update_interval_ms = ms
        logging.info("Update interval set to %s ms" % ms)

    def load_config(self, section, override={}):
        """ Reads the config file for the specified section.
        """
        self.config_path = os.path.join(CAMSTIM_DIR, "config/stim.cfg")
        config = get_config(section, self.config_path)
        for k in override.keys():
            if k in config.keys():
                config[k] = override[k]
        return config

    def package(self):
        """ Packages the experiment and gets it ready for storage.
        """
        self.nidaq_tasks = {k: str(v) for k, v in self.nidaq_tasks.iteritems()}
        self.encoders = [e.package() for e in self.encoders]
        self.rewards = [r.package() for r in self.rewards]
        self.lick_sensors = [l.package() for l in self.lick_sensors]
        self.items = OrderedDict({k: v.package() for k,
                                 v in self.items.iteritems()})
        return super(BehaviorBase, self).package()

    def add_encoder(self, encoder):
        """ Adds a behavior encoder.
        """
        self.encoders.append(encoder)

    def add_reward(self, reward):
        """ Adds a behavior reward.
        """
        self.rewards.append(reward)

    def add_lick_sensor(self, lick_sensor):
        """ Adds a lick sensor to the behavior session.
        """
        self.lick_sensors.append(lick_sensor)

    def _setup_DAQ(self):
        """ Sets up some DAQ tasks for behavior.  Not all tasks will be available
            on every rig, so we just log a warning if any fail to start.
        """
        cfg = self.config['behavior']
        nidaq = cfg['nidevice']

        #get any tasks passed in
        tasks = self.nidaq_tasks

        try:
            if not tasks.get('analog_input', None):
                from toolbox.IO.nidaq import AnalogInput
                self.ai = AnalogInput(device=nidaq,
                                      channels=range(8),
                                      buffer_size=25,
                                      clock_speed=1000.0)
                self.ai.start()
            else:
                self.ai = tasks['analog_input']  # AI task was passed in

        except Exception as e:
            logging.warning("Failed to set up AnalogInput: %s" % e)
            self.ai = None

        try:
            if not tasks.get('analog_output', None):
                from toolbox.IO.nidaq import AnalogOutput
                self.ao = AnalogOutput(device=nidaq,
                                       channels=range(2),
                                       voltage_range=[0.0, 5.0])
                self.ao.start()
            else:
                self.ao = tasks['analog_output']  # AO task was passed in
        except Exception as e:
            logging.warning("Failed to set up AnalogOutput: %s" % e)
            self.ao = None

        logging.info("Initialzed nidaq.")

    def close(self):
        self._update_timer.stop()
        if self.ai:
            self.ai.clear()
            self.ai = str(self.ai)
        if self.ao:
            self.ao.clear()
            self.ao = str(self.ao)

        for item in self.items.values():
            item.close()


class Behavior(BehaviorBase):
    """ Defines a basic Behavior experiment. 

    Just BehaviorBase with some features automatically added, and the
        possibility of a visual stimulus.

    """
    def __init__(self,
                 window=None,
                 params={},
                 nidaq_tasks={},
                 mask_times=None,
                 auto_update=False,
                 ):

        super(Behavior, self).__init__(params=params,
                                       nidaq_tasks=nidaq_tasks,
                                       auto_update=auto_update)

        self.window = window
        self.stimuli = OrderedDict()

        self.behavior_text = ""
        self.behavior_path = ""

        #INITIALIZE ENCODER
        self._encoder_setup()

        #INITIALIZE REWARD
        self._reward_setup()

        # #INITIALIZE LICK SENSOR
        self._lick_setup()

        # INIT SYNC SIGNALS
        self._setup_sync()

        #INIT PERFORMANCE TRACKER IF POSSIBLE
        self._datastream_setup()

        # SET KEY HANDLER FOR POTENTIAL KEYBINDS
        self._keys_setup()

        logging.info("Initialized behavior.")

    @staticmethod
    def from_file(path,
                  window=None,
                  auto_update=True,
                  params={},
                  nidaq_tasks={}):
        """
        Loads a setup from a file.  Include a window if you create any stimuli
            in your setup file.

        #TODO replace loading with exec with something safe.  json or some shit.

        """
        with open(path, 'r') as f:
            behavior_text = f.read()
        behavior = None
        exec(behavior_text)
        behavior.behavior_text = behavior_text
        behavior.behavior_path = path
        return behavior

    def add_stimulus(self, stimulus, name=""):
        """
        Adds a foraging stimulus to the session.  If stimulus is a string, it
            is assumed to be a file path and is loaded from there.
        """
        if type(stimulus) is str:
            stimulus = self._load_stimulus(stimulus)

        if not name:
            length = len(self.stimuli.keys())
            name = "unnamed_stimulus_{}".format(length)
        self.stimuli[name] = stimulus

    def remove_stimulus(self, stimulus):
        if isinstance(stimulus, str):
            # a name
            del self.stimuli[stimulus]
        else:
            for k,v in self.stimuli.iteritems():
                if stimulus is v:
                    del self.stimuli[k]
                    break

    def _load_stimulus(self, path):
        return VisualObject.from_file(path,
                                      self.window,
                                      self.encoders[0],
                                      self.lick_sensors,
                                      self.rewards)

    def update(self, index=None):
        """
        Update method for behavior.
        """
        index = index or self.update_count
        super(Behavior, self).update(index)

        for stimulus in self.stimuli.values():
            stimulus.update(index)

        if self.sync_sqr:
            self.sync_sqr.update(index)

        if self.auto_update:
            if self.window:
                if self.frame_pulse:
                    self.frame_pulse.set_high()
                self.window.flip()
                if self.frame_pulse:
                    self.frame_pulse.set_low()

        self._check_keys()

    def _splash(self):
        """ Grey splash screen if we have sync square.
        """
        if self.sync_sqr:
            nom_freq = self.sync_sqr.frequency
            self.sync_sqr.frequency = 5
            for i in range(30):
                self.sync_sqr.update(i)
                self.window.flip()
            self.sync_sqr.frequency = nom_freq

    def start(self):
        super(Behavior, self).start()
        self._splash()
        if self.trigger_output:
            self.trigger_output.set_high()
        for stimulus in self.stimuli.values():
            stimulus.start()
        if self.window:
            self.window.setRecordFrameIntervals(True)
        logging.info("Task started.")

    def close(self):
        self._update_timer.stop()
        if self.trigger_output:
            self.trigger_output.set_low()
        super(Behavior, self).close()
        if self.window:
            self.window.setRecordFrameIntervals(False)
            try:
                self._splash()
                self.intervalsms = np.array(self.window.frameIntervals)*1000
                self._print_frame_report()
                self.window.close()
                self.window = None
            except:
                #window is already closed...
                pass
        logging.info("Task closed.")

    def _print_frame_report(self):
        pass

    def _setup_sync(self):
        self.sync_sqr = None
        self.sync_pulse = None
        cfg = self.config['sync'] = self.load_config("Sync",
                                                     override=self.params)
        if cfg['sync_sqr']:
            self._setup_sync_sqr(cfg)
        self._setup_sync_pulse()

    def _setup_sync_sqr(self, cfg):
        if self.window:
            sqr = SyncSquare(self.window,
                            size=cfg['sync_sqr_size'],
                            pos=cfg['sync_sqr_loc'],
                            frequency=cfg['sync_sqr_freq'],
                            colorSequence=cfg['sync_sqr_color_sequence'])
            self.sync_sqr = sqr
            logging.debug("SyncSquare configured.")
        else:
            logging.warning("Failed to create sync square: No display window.")

    def _setup_sync_pulse(self):
        """ Sets up a frame pulse and an output trigger line.
        #TODO: remove overlap with sweepstim.
        """
        cfg = self.config['sync']
        self.frame_pulse = None
        self.trigger_output = None
        try:
            if cfg['frame_pulse']:
                device, port, line = cfg['frame_pulse']
                self.frame_pulse = SyncPulse(device,
                                             port,
                                             line)
                self.frame_pulse.set_low()
                logging.debug("Frame pulse configured on port {}, line {}".format(port, line))
            if cfg['acq_on_pulse']:
                device, port, line = cfg['acq_on_pulse']
                self.trigger_output = SyncPulse(device,
                                                port,
                                                line)
                self.trigger_output.set_low()
                logging.debug("Trigger output configured on port {}, line {}".format(port, line))
        except Exception as e:
            logging.warning("Failed to create sync pulse: {}".format(e))


    def _encoder_setup(self):
        """
        Set up encoder based on config file.

        TODO:
            - update config names

        """
        try:
            from toolbox.Encoders import AnalogEncoder
            self.config['encoder'] = self.load_config('Encoder',
                                                      override=self.params)

            nidevice = self.config['encoder']['nidevice']
            vin = self.config['encoder']['encodervinchannel']
            vsig = self.config['encoder']['encodervsigchannel']

            # TODO: when passing a pre-configured NI task like this,
            #   there is really no reason to specify device, but it
            #   is require by old encoder object.
            encoder = AnalogEncoder(device=nidevice,
                                    vin=vin,
                                    vsig=vsig,
                                    task=self.ai,
                                    )

            self.add_encoder(BehaviorEncoder(encoder))

        except ImportError as e:
            encoder = None
            logging.warning("Couldn't import encoder: %s" % e)
        except Exception as e:
            logging.warning("Couldn't setup encoder: %s" % e)
            encoder = None

        if not encoder:
            #logging.warning("Switching to keyboard control.")
            try:
                encoder = KeyboardEncoder(self.window)

                self.add_encoder(BehaviorEncoder(encoder))
            except Exception as e:
                logging.warning("Couldn't create keyboard encoder: %s" % e)

    def _reward_setup(self):
        """
        Set up reward valves based on config file.

        TODO:
            - update config names?
        """
        self.volume_dispensed = 0.0
        self.rewards_dispensed = 0
        self._volume_limit = self.config['behavior']['volume_limit']
        try:
            camstim_folder = CAMSTIM_DIR
            config_folder = os.path.join(camstim_folder, 'config')
            check_dirs(config_folder)
            volumecalfile = os.path.join(config_folder, 'volume.yml')
            # with open(volumecalfile, 'r') as f:
            #     calibrations = [eval(line) for line in f.readlines()]
            with open(volumecalfile, 'r') as f:
                calibrations = yaml.load(f).values()
            print(calibrations)
            logging.info("Volume calibration values: %s" % calibrations)
        except Exception as e:
            logging.warning("Couldn't read volume calibration values: %s" % e)
            calibrations = [{'calibration': {'slope': 10.0, 'intercept': 0.0}},]

        try:
            cfg = self.config['reward'] = self.load_config("Reward",
                                                           override=self.params)
            reward_lines = cfg['reward_lines']
            reward_vol = cfg['reward_volume']
            nidevice = cfg['nidevice']
            invert_logic = cfg['invert_logic']

            from reward import Reward

            rewards = []

            for i, (port,line) in enumerate(reward_lines):
                try:
                    vol_cals = calibrations[i]['calibration']
                    slope, intercept = vol_cals['slope'], vol_cals['intercept']
                    r = Reward(device=nidevice,
                               port=port,
                               line=line,
                               rewardvol=reward_vol,
                               calibration=(slope, intercept),
                               mode='volume',
                               #task=self.do,
                               invert=invert_logic)
                    behavior_reward = BehaviorReward(r)
                    logging.debug("Reward initialized on port {}, line {}".format(port,
                                                                                  line))
                except Exception as e:
                    logging.warning("Failed to set up reward: {}".format(e))
                    behavior_reward = KeyboardReward(self.window)
                    logging.debug("Keyboard reward initialized.")

                behavior_reward.rewardtriggered.connect(self._reward_triggered)
                self.add_reward(behavior_reward)

        except Exception as e:
            logging.warning("Failed to initialize rewards: %s" % e)

    def _lick_setup(self):
        """
        Set up lick sensors based on config file.
        """
        cfg = self.config['lick'] = self.load_config("Licksensing",
                                                     override=self.params)
        nidevice = cfg['nidevice']
        lick_lines = cfg['lick_lines']
        lick_sensors = []

        for i, (port, line) in enumerate(lick_lines):
            try:
                from toolbox.IO.nidaq import DigitalInput
                di = DigitalInput(nidevice, port=port, lines=str(line))
                #ls = BehaviorLickSensor(di_task=self.di, line=line)
                ls = BehaviorLickSensor(di_task=di, line=0)
                if ls.test():
                    lick_sensors.append(ls)
                    logging.debug("lick sensor initialized on port {}, line {}".format(port, line))
                else:
                    logging.warning("Lick sensor %s failed self-test." % i)
                    raise RuntimeError("Lick sensor %s failed self-test" % i)

            except Exception as e:
                logging.warning("Failed to initialize a hardware lick sensor: %s" % e)
                ls = KeyboardLickSensor(self.window, hotkey=str(i))
                lick_sensors.append(ls)
                logging.info("Keyboard lick sensor added: %s" % i)

        for l in lick_sensors:
            self.add_lick_sensor(l)

    def _datastream_setup(self):
        """
        #TODO: Possibly another type besides ZRO?  HTTP PUT?
        #TODO: Change this to pass self and put packet creating inside BehaviorDataSource
        """
        self.config['Datastream'] = self.load_config('Datastream',
                                                     override=self.params)
        cfg = self.config['Datastream']

    def _keys_setup(self):
        """ Sets up keyboard control.
        #TODO: only works for experiments with a display window. Pick more general solution?
        """
        if self.window:
            self._keys = key.KeyStateHandler()
            self.window.winHandle.push_handlers(self._keys)
        else:
            self._keys = None

    def _check_keys(self):
        if self._keys:
            if self._keys[key.ESCAPE]:
                self._close()

    def _close(self):
        if self._parent:
            self._parent.close()
        else:
            self.close()

    def _reward_triggered(self, volume):
        """
        Callback for a reward being triggered on any of the reward lines.

        Just adds the dispensed volume to the total and closes if there is a
            maximum dispensed volume.

        TODO: How should this be handled?  Seems a little hard coded to me.

        """
        self.volume_dispensed += volume
        self.rewards_dispensed += 1
        if self._volume_limit is not None:
            if self.volume_dispensed >= self._volume_limit:
                logging.info("Volume limit of {} reached.".format(self._volume_limit))
                self._close()

    def package(self):
        self.window = str(self.window)
        self.stimuli = OrderedDict({k:v.package() for k,v in self.stimuli.items()})

        data = super(Behavior, self).package()
        if isinstance(self._parent, Experiment):
            self._save_session(data)
        return data

    def _save_session(self, data):
        if self._parent:
            data['platform_info']=self._parent.platform_info
            dt = self._parent._output_file.dt
        else:
            data['platform_info']=get_platform_info()
            dt = datetime.datetime.now()
        # SAVES SESSION TO MOUSE_INFO IF NECESSARY
        # Should this be here?  TODO: find a better system for this
        mouse_id = self.config['behavior']['mouse_id'].strip("Mm")
        script_path = sys.argv[0]
        with open(script_path, 'r') as f:
            script = f.read()
        if mouse_id is not 'testmouse':
            try:
                save_session(mouse_id=mouse_id,
                             dt=dt,
                             data=data,
                             script=script,
                             )
                logging.info("Saved session to mouse: {}".format(mouse_id))
            except Exception as e:
                logging.exception("Failed to save session to mouse info: {}".format(e))
        else:
            logging.info("No mouse_info data saved.")

# backwards compatibility?
Foraging = Behavior
Task = Behavior


class VisualObject(EObject):
    """
    Abstract visual object for behavior.

    Parameter tables can be autogenerate from lists of possible/correct values
        or from pre-defined sequences.

    """
    stimulus_changed = QtCore.Signal(tuple)
    flash_started = QtCore.Signal()
    flash_ended = QtCore.Signal()

    def __init__(self,
                 stimulus=None,
                 **kwargs):
        super(VisualObject, self).__init__()
        self.stimulus = stimulus
        self.kwargs = kwargs
        self.obj_text = ""

        self._on = True
        self._current_params = None
        self._current_correct = False
        self._sequence_index = 0
        self._current_flash_frame = 0
        self._periodic_flash = False
        self.correct_freq = 0.5
        self.fps = 60.0
        self.flash_interval_sec = None
        self.draw_log = []

        self.param_names = None
        self.possibility_table = None
        self.correct_table = None
        self.incorrect_table = None

        self.sequence = None

        self.update_count = 0
        self.log = []  #keeps track of all stimulus changes

        self.on_draw = {}


    @staticmethod
    def from_file(path,
                  window,
                  encoder=None,
                  lick_sensors=[],
                  rewards=[],):
        """
        Your standard "from_file" staticmethod.  Returns a visual object in
            a file and intitalizes it to the specified psychopy window.
        #TODO: window optional?
        """
        with open(path, 'r') as f:
            obj_text = f.read()
        obj = None
        exec(obj_text)
        obj.obj_text = obj_text
        obj.obj_path = path
        return obj

    @property
    def on(self):
        return self._on

    @on.setter
    def on(self, value):
        self._on = value

    def update(self, index=None):
        """
        Ran every update.
        """
        if self._on:
            #self._check_reward_criteria()
            if self.stimulus:
                self.draw()
            else:
                self._to_draw()
        else:
            pass
        self.update_count += 1

    def draw(self):
        """
        On draw events.
        """
        for k, v in self.on_draw.iteritems():
            if k == "TF":
                v = float(v)
                self.stimulus.setPhase(v*self.update_count/self.fps)
        
        if self._to_draw():
            self.draw_log.append(1)
            self.stimulus.draw()
        else:
            self.draw_log.append(0)

    def _to_draw(self):
        """ Decides whether to actually draw the stimulus.

        TODO: this works, but is stupid. refactor at some point
        """
        if not self._periodic_flash:
            return True
        else:
            if self._current_flash_frame >= self._flash_period_frame:
                self.reset_flash()
                self.flash_ended.emit()
                self._on_flash_start()
                return True
            elif self._current_flash_frame > self._flash_interval_frame:
                self._current_flash_frame+=1
                return False
            elif self._current_flash_frame == self._flash_interval_frame:
                self._current_flash_frame+=1
                self._on_flash_end()
                return False
            else:
                self._current_flash_frame+=1
                return True


    def set_periodic_flash(self,
                           interval_sec,
                           ):
        if interval_sec in (None, "None"):
            self._periodic_flash = False
        else:
            self._periodic_flash = True
            self.flash_interval_sec = interval_sec
            if isinstance(interval_sec, (int, float)):
                #flash_interval_sec = interval_sec
                self._flash_interval_frame = int(self.fps * interval_sec)
                self._off_interval_frame = self._flash_interval_frame
            elif isinstance(interval_sec, (list, tuple)):
                self._flash_interval_frame = int(interval_sec[0] * self.fps)
                self._off_interval_frame = int(interval_sec[1] * self.fps)
            else:
                print(interval_sec)
                raise TypeError("interval_sec should be a float or a (on_sec, off_sec) tuple, not: {}".format(type(interval_sec)))
            self._flash_period_frame = self._flash_interval_frame + self._off_interval_frame

    def reset_flash(self):
        self._current_flash_frame = 0

    def _on_flash_start(self):
        """ Called at the start of every flash.
            Override.
        """
        pass

    def _on_flash_end(self):
        """ Called at the end of every flash
        """
        pass

    def new(self):
        if random.random() < self.correct_freq:
            self.new_correct()
        else:
            self.new_incorrect()

    def new_correct(self):
        """ Get new parameters for a correct object based on table.
        """
        if self.correct_table is not None:
            new = random.choice(self.correct_table)
            self._update_stimulus(new)
            logging.debug("Stimulus updated: {}".format(new))
        else:
            logging.warning("Stimulus could not be changed: No correct value table.")
        self._current_correct = True

    def new_incorrect(self):
        """ Get new parameters for an incorrect object based on table.
        """
        if self.incorrect_table is not None:
            new = random.choice(self.incorrect_table)
            self._update_stimulus(new)
            logging.debug("Stimulus updated: {}".format(new))
        else:
            logging.warning("Stimulus could not be changed: No incorrect value table.")
        self._current_correct = False

    def next(self):
        """ Move to next row in the sequence.
        """
        self.set_param_index(self._sequence_index+1)

    def _update_stimulus(self, values):
        """ Updates stimulus with current parameters.
        """
        for k, v in zip(self.param_names, values):
            try:
                method = getattr(self.stimulus, "set%s" % k)
                method(v)
            except AttributeError:
                if k == "PosX":
                    self.stimulus.setPos((v, self.stimulus.pos[1]))
                elif k == "PosY":
                    self.stimulus.setPos((self.stimulus.pos[0], v))
                elif k == "TF":
                    self.on_draw[k] = v
                else:
                    logging.warning("Foraging stimulus object param incorrectly formatted: %s->%s" % (k, v))
        self._current_params = values
        self.stimulus_changed.emit((self.param_names, values))
        self.log.append((values, self.update_count))
        logging.debug("Stimulus changed: {} {} {}".format(values,
                                                          self._current_correct,
                                                          self.update_count))

    def set_param_sequence(self, names, sequence):
        """ Sets a parameter sequence.  Sequence is configured the same way as the
            old sequence files.  SHOULD IT BE THO?
        """
        self.param_names = names
        self.sequence = sequence
        if len(self.param_names) != len(self.sequence[0][0]):
            raise IndexError("Sequence parameter list and name list are different lengths")

        self.set_param_index(0)

    def set_param_index(self, index):
        """ Sets the sequence index.
        """
        new = self.sequence[index][0]
        self._current_correct = self.sequence[index][1]
        self._sequence_index = index
        self._update_stimulus(new)

    def build_param_table(self, params):
        """ Build a param table from some stuff.
        """
        self.param_names = [p['name'] for p in params]
        possibles = [p['possible'] for p in params]
        correct = [p['correct'] for p in params]

        self.possibility_table = list(itertools.product(*possibles))
        self.correct_table = list(itertools.product(*correct))
        self.incorrect_table = [p for p in self.possibility_table if p not in self.correct_table]

        # get one to start ??
        #self.new()

    def load_param_sequence(self, path):
        """ Loads a parameter sequence from a file.
        """

    def get_possibility_table(self):
        """ Gets the table of possible values.
        """
        return self.possibility_table

    def get_correct_table(self):
        """ Gets the table of correct values.
        """
        return self.correct_table

    def get_incorrect_table(self):
        """ Gets the table of incorrect values.
        """
        return self.incorrect_table

    def add_reward_criteria(self, reward_critera):
        """
        Adds a reward criteria for this object.
        """

    def remove_reward_criteria(self, index):
        """
        Removes a reward criteria for this object.
        """

    def _check_reward_criteria(self):
        """
        Should this be here?
        """
        pass

    def on(self):
        """
        Turns object on.  Objects like this.
        """
        self._on = True

    def off(self):
        """
        Turns object off.  Objects dislike this.
        """
        self._on = False

    def package(self):
        self.stimulus = str(self.stimulus.__dict__)
        return super(VisualObject, self).package()

ForagingObject = VisualObject  # backwards compatibility


class Epoch(EObject):
    """ A period of time in a behavior task that can impose custom logic. 
    
        args:
            task (Task): reference to task we wish to control
            duration (float): give epoch a default duration in seconds
            delay (float): delay start of epoch in seconds
            name (str): epoch name
    """
    epochStarted = Signal(float)
    epochEnded = Signal(float)

    def __init__(self, task, duration=0.0, delay=0.0, name=""):
        super(Epoch, self).__init__()
        self._task = task

        self.entries = []
        self.exits = []

        self.duration = duration
        self.delay = delay
        self._name = name

        self._epoch_timer = ETimer()
        self._epoch_timer.setSingleShot(True)
        self._epoch_timer.timeout.connect(self.exit)

        self._start_timer = ETimer()
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self._delayed_enter)

    def enter(self, immediately=False):
        self._active = True

        #TODO: rethink the way delay works
        if immediately:
            pass
        elif self.delay <= 0:
            pass
        else:
            self._start_timer.start(self.delay)
            return
        logging.debug("Entering epoch: {}".format(self.name))
        self._on_entry()

        t = time.clock()
        self.entries.append(t)
        self.epochStarted.emit(t)

        if self.duration:
            self._epoch_timer.start(self.duration)
        else:
            self.exit()

    def _delayed_enter(self):
        self.enter(immediately=True)

    def reset(self):
        logging.debug("Epoch timer reset: {}".format(self.name))
        self._epoch_timer.start(self.duration)
        # should this send the enter signal again?

    def kill(self):
        """ kills epoch timers and deactivates epoch. """
        self._epoch_timer.stop()
        self._start_timer.stop()
        self._active = False

    def _on_entry(self):
        """ Called on epoch entry. """
        pass

    def exit(self):
        """ Exits the epoch. """
        logging.debug("Exitting epoch: {}".format(self.name))
        self.kill()
        t = time.clock()
        self.exits.append(t)
        self.epochEnded.emit(t)
        self._on_exit()

    def _on_exit(self):
        """ Called on epoch exit. """
        pass

    @property
    def name(self):
        return self._name or str(self)

    @property
    def _active(self):
        return self in self._task._active_epochs

    @_active.setter
    def _active(self, value):
        if value is True:
            if not self._active:
                self._task._active_epochs.append(self)
        else:
            if self._active:
                self._task._active_epochs.remove(self)

    def set_active(self, active):
        self._active = active


class TrialGenerator(EObject):
    """ Generates trial parameters.
    ##TODO: should trial be a class instead of a dict?
    """
    def __init__(self, sequence=None, task=None):
        super(TrialGenerator, self).__init__()
        if isinstance(sequence, str):
            sequence = self._load_sequence(sequence)

        self._sequence = sequence
        self._task = task

        self._trial_index = 0
        self.random_params = {}

    def _load_sequence(self, path):
        """ Load a sequence from a file.
        TODO: LATER
        """

    def _condition_trial(self, trial):
        """ This is where we put in any last minute logic once
            our parameters have been chosen.
        """
        return trial

    def __iter__(self):
        return self

    def next(self):
        trial = {}
        if self._sequence:
            trial.update(self._sequence[self._trial_index])
        if self.random_params:
            for k, v in self.random_params.iteritems():
                if callable(v):
                    trial[k] = v()
                else:
                    trial[k] = random.choice(v)
        self._trial_index += 1
        trial = self._condition_trial(trial)
        return trial

    def add_random_param(self, name, values):
        """ Adds a param to choose for each trial.

            If `values` is iterable, picks one at random.
            If `values` is callable, picks the return value
        """
        # TODO: make sure values is sequence or callable
        # TODO: rethink name, because the values can be non-random
        self.random_params[name] = values


class AFCForaging(Behavior):
    """ AFC Foraging.

    Has built-in time trials.  Supports randomized trials or set sequence.
    """
    all_trials_completed = QtCore.Signal()

    def __init__(self,
                 *args,
                 **kwargs
                 ):
        super(AFCForaging, self).__init__(*args, **kwargs)
        self.stim_sequence = []

    def set_time_trials(self, lengths_secs, max_trials=None):
        if isinstance(lengths_secs, (int, float)):
            if max_trials:
                length_sequence = [lengths_secs] * max_trials
            else:
                length_sequence = [lengths_secs]
        else:
            # array
            length_sequence = lengths_secs
            if max_trials:
                length_sequence = length_sequence[:max_trials]
        tt = Timetrials(length_sequence, units='sec')
        tt.trial_started.connect(self.start_trial)
        tt.all_trials_completed.connect(self.session_completed)

        self.add_item(tt, name="time_trials")

    def set_stim_sequence(self, sequence):
        pass

    def start_trial(self, index):
        if len(self.stim_sequence) <= index:
            # no stimulus chosen at this trial, pick a random one
            stim_index = random.randint(0, len(self.stimuli)-1)
            #print(stim_index)
            self.stim_sequence.append(stim_index)
        else:
            stim_index = self.stim_sequence[index]
        # THIS WILL ONLY WORK WITH 2 STIMULI
        self.stimuli[stim_index].enabled = True
        self.stimuli[stim_index-1].enabled = False
        self.stimuli[stim_index].flash()


    def session_completed(self):
        self.all_trials_completed.emit()

    def set_start_cue(self,
                      stimulus,
                      ):
        self.add_item(stimulus, "start_que")

        if self.has_item("time_trials"):
            tt = self.get_item("time_trials")
            tt.trial_started.connect(stimulus.flash)
        else:
            raise RuntimeError("Set up time trials before start que.")

    def set_failure_cue(self,
                        failure_cue,
                        ):
        self.add_item(failure_cue, "failure_cue")
        for stimulus in self.stimuli:
            stimulus.sigMiss.connect(failure_cue.flash)
            stimulus.sigFalseAlarm.connect(failure_cue.flash)

class Cue(EObject):
    """
    A Cue is just a visual indicator that displays for a specified amount of time.

    Can be an arbitrary psychopy stimulus.

    """
    def __init__(self,
                 psychopy_stimulus,
                 duration_ms,
                 ):
        super(Cue, self).__init__()
        self._stimulus = psychopy_stimulus
        self.duration_ms = duration_ms

        self._flashing = False
        self._flash_frame_count = 0

    @property
    def duration_ms(self):
        return self._duration_ms

    @duration_ms.setter
    def duration_ms(self, value):
        self._duration_ms = value
        self._duration_frames = value*60.0/1000.0

    def update(self, index=None):
        if self._flashing:
            self._stimulus.draw()
            self._flash_frame_count += 1
            if self._flash_frame_count > self._duration_frames:
                self._flashing = False
        else:
            pass

    def flash(self):
        self._flashing = True
        self._flash_frame_count = 0

class FailureCue(Cue):
    """
    A Cue that flashes the whole screen at a specified period.
    """
    def __init__(self,
                 window,
                 duration_ms,
                 period_ms=200,
                 ):
        stimulus = visual.GratingStim(window,
                                      units='deg',
                                      size=(300,300),
                                      pos=(0,0),
                                      tex=None,
                                      color=-1,
                                      )
        
        super(FailureCue, self).__init__(stimulus, duration_ms)
        self.period_ms = period_ms
        

        self._color = -1
        self._flashing = False
        self._flashing_frame_count = 0

    @property
    def period_ms(self):
        return self._period_ms
    
    @period_ms.setter
    def period_ms(self, value):
        self._period_ms = value
        self._period_frames = value*60.0/1000.0

    def update(self, index=None):
        if self._flashing:
            self._stimulus.draw()
            self._flash_frame_count += 1
            if self._flash_frame_count > self._duration_frames:
                self._flashing = False
            if self._flash_frame_count % (self._period_frames / 2) == 0:
                self._color *= -1
                self._stimulus.setColor(self._color)
        else:
            pass

    def flash(self):
        if not self._flashing:
            self._flashing = True
            self._flash_frame_count = 0


class LapStimulus(VisualObject):
    """
    A VisualObject that moves and triggers rewards/punishments.

    Gets a new stimulus every time a lap completes.
    """
    def __init__(self, stimulus, encoder, laps=None, **kwargs):
        super(LapStimulus, self).__init__(stimulus, **kwargs)
        self.encoder = encoder
        self.laps = laps

        self.window_width = 100
        self.window_posx = 0
        self.start_position = (-1200, 0)
        self.direction = [1, 0]  # (x,y)

        if self.laps:
            self.laps.lap_started.connect(self.new)

    def set_direction(self, x, y):
        """
        Sets the direction that the stimulus moves.
        """
        self.direction = [x, y]

    def update(self, index=None):
        """
        Ran every update.  Moves the stimulus based on encoder position.
        """
        dx = self.encoder.value
        pos = self.stimulus.pos
        self.stimulus.setPos([pos[0]+dx*self.direction[0],
                              pos[1]+dx*self.direction[1]])
        super(LapStimulus, self).update(index)

    def new_incorrect(self):
        self.stimulus.setPos(self.start_position)
        super(LapStimulus, self).new_incorrect()

    def new_correct(self):
        self.stimulus.setPos(self.start_position)
        super(LapStimulus, self).new_correct()

    def next(self):
        self.stimulus.setPos(self.start_position)
        super(LapStimulus, self).next()


class FlashStimulus(VisualObject):
    """
    VisualObject that flashes on screen and can trigger rewards/punishments.

    There are four timers here.

    Pre-flash timer:  Controls the period during which a flash is queued but
        hasn't started yet.
    Flash timer:  Controls a period where the object is visible.
    Response timer: Controls the period where rewards are available.
    Availability timer: Controls the availability delay (Time between start
        of flash and availability of reward).

    """
    flash_ended = QtCore.Signal(float)

    def __init__(self,
                 stimulus,
                 encoder,
                 lick_sensors,
                 rewards,
                 pre_flash_duration=0,
                 flash_duration=250,
                 response_window=500,
                 availability_delay=0,
                 extension_duration=0,
                 timing_mode="timer",
                 **kwargs):

        super(FlashStimulus, self).__init__(stimulus, **kwargs)
        # major inputs
        self._encoder = encoder
        self._lick_sensors = lick_sensors
        self._rewards = rewards

        # timing attributes
        self.pre_flash_duration = pre_flash_duration
        self.flash_duration = flash_duration  # ms
        self.response_window = response_window  # ms
        self.availability_delay = availability_delay
        self.extension_duration = extension_duration
        self.timing_mode=timing_mode ##TODO: make this work

        # counters, etc
        self._flashing = False
        self._available = False
        self._in_response_window = False
        self._extension_time = 0

        # lick/reward setup
        ##TODO: make it more configurable
        ## Should it even have mandatory lick sensors?
        if not isinstance(self._lick_sensors, list):
            self._lick_sensors = [self._lick_sensors]
        for ls in self._lick_sensors:
            ls.lickoccurred.connect(self._lick)

        # timer setup
        self._pre_flash_timer = QtCore.QTimer()
        self._pre_flash_timer.timeout.connect(self._pre_flash_ended)

        self._flash_timer = QtCore.QTimer()  # should it be a qtimer or just count frames?
        self._flash_timer.timeout.connect(self._flash_ended)

        self._availability_timer = QtCore.QTimer()
        self._availability_timer.timeout.connect(self._availablity_timer_ended)

        self._response_timer = QtCore.QTimer()
        self._response_timer.timeout.connect(self._response_time_ended)

        # logging
        self.flash_starts = []
        self.flash_ends = []

    def extend(self, ms=None):
        """
        Adds extension time to the next pre-flash.
        """
        if ms is None:
            self._extension_time += self.extension_duration
        else:
            self._extension_time += ms
        logging.debug("Trial extended by {} ms".format(ms))

    def flash(self):
        """
        Starts a flash sequence.
        """
        self._pre_flash_timer.start(self.pre_flash_duration + self._extension_time)
        self._extension_time = 0
        logging.info("Flash sequence started: {}".format(len(self.flash_starts)))
        self.flash_starts.append(self.update_count)

    def _pre_flash_ended(self):
        """
        End of pre-flash period.
        """
        self._pre_flash_timer.stop()

        self._flashing = True
        self._flash_timer.start(self.flash_duration)

        self._availability_timer.start(self.availability_delay)

    def _availablity_timer_ended(self):
        """
        Availability delay has ended.
        """
        self._availability_timer.stop()

        self._available = True
        self._response_timer.start(self.response_window)
        self._in_response_window = True

    def update(self, index=None):
        """
        Ran every update.
        """
        if self._on:
            #self._check_reward_criteria()
            if self._flashing:
                if self.stimulus:
                    self.stimulus.draw()
        else:
            pass
        self.update_count += 1

    def _flash_ended(self):
        """
        Ends a flash.
        """
        self._flash_timer.stop()
        self._flashing = False

        self.flash_ends.append(self.update_count)

        if self.sequence:
            self.next()
        else:
            self.new()

        self.flash_ended.emit(time.clock())

    def _response_time_ended(self):
        """
        Ends a response time.
        """
        self._response_timer.stop()
        self._available = False
        self._in_response_window = False

    def _lick(self):
        if self._available:
            pass  #deliver rewards or something?  wat do?


class AFCStimulus(FlashStimulus):
    """
    A specific type of FlashStimulus that, when paired with multiple lick spouts,
        will reward one and punish the others.

    """
    sigHit = QtCore.Signal()
    sigMiss = QtCore.Signal()
    sigFalseAlarm = QtCore.Signal()

    def __init__(self,
                 stimulus,
                 lick_sensors,
                 rewards,
                 pre_flash_duration=1000,
                 flash_duration=1000,
                 response_window=1000,
                 availability_delay=0,
                 timing_mode="timer",
                 ):
        super(AFCStimulus, self).__init__(stimulus,
                                          lick_sensors=lick_sensors,
                                          rewards=rewards,
                                          encoder=None,
                                          pre_flash_duration=pre_flash_duration,
                                          flash_duration=flash_duration,
                                          response_window=response_window,
                                          availability_delay=availability_delay,
                                          timing_mode=timing_mode,)
        self.disconnect_lick_sensors()

        self.correct_lick_spout = None
        self.correct_freq = 1.0

        self._no_lick = False
        self.enabled = False

    def set_correct_lick_spout(self, spout):
        """
        Set which lick spout is rewarded.
        """
        if isinstance(spout, int):
            self.correct_lick_spout = spout
        elif spout in self._lick_sensors:
            self.correct_lick_spout = self._lick_sensors.index(spout)
        else:
            raise IndexError("Could not locate requested lick spout.")

        for i, ls in enumerate(self._lick_sensors):
            if i == self.correct_lick_spout:
                ls.lickoccurred.connect(self._hit)
            else:
                ls.lickoccurred.connect(self._miss)

    def disconnect_lick_sensors(self):
        """
        Disconnects lick sensors so that we may reconnect them as desired.
        """
        for ls in self._lick_sensors:
            ls.lickoccurred.disconnect()

    def _hit(self):
        """
        Callback for a lick on the correct spout.
        """
        if self.enabled:
            if self.correct_lick_spout is not None:
                if self._available:
                    # mouse licked correct spout when reward was available
                    self._rewards[self.correct_lick_spout].reward()
                    self._available = False
                    self.sigHit.emit()
                # elif self._no_lick:
                #     # mouse licked correct spout during "no-lick" period
                #     #self.abort() # ???
                #     pass
                elif self._in_response_window:
                    pass
                elif self._flashing:
                    pass
                else:
                    # mouse licked correct spout when reward was unavailable
                    self.sigFalseAlarm.emit()

    def _miss(self):
        """ Callback for a lick on the incorrect spout.
        """
        if self.enabled:
            if self._available:
                # mouse licked the wrong spout when reward was available
                self._flashing = False
                self.sigMiss.emit()
            elif self._in_response_window:
                pass
            elif self._flashing:
                pass
            else:
                # mouse licked the incorrect spout when a reward was not available
                self.sigFalseAlarm.emit()
                #pass

class GNGFlashStimulus(FlashStimulus):
    """
    Flash Stimulus designed for Go/No-go detection.

    Args:
        stimulus (psychopy stimulus object): The psychopy stimulus object.
        lick_sensors (list): List of lick sensors that the Object might need to
            use.
        rewards (list): List of rewards that the object might need to use.
        no_lick_duration (int): duration of the no-lick period in milliseconds
        flash_duration (int): duration of the flash period in milliseconds
        response_window (int): duration of the response window in milliseconds
        availability_delay (int): duration of the availability delay in milliseconds
        trial_length (int): trial length in milliseconds
        max_trials (int): total trials until completion

    Signals:
        sigHit: when a "hit" occurs
        sigMiss: when a "miss" occurs
        sigAbort: when an trial is aborted
        sigTrialsComplete: when all trials have been completed.

    """
    sigHit = QtCore.Signal()
    sigMiss = QtCore.Signal()
    sigAbort = QtCore.Signal()
    sigTrialsComplete = QtCore.Signal()

    def __init__(self,
                 stimulus,
                 lick_sensors,
                 rewards,
                 no_lick_duration=1000,
                 flash_duration=250,
                 response_window=1000,
                 availability_delay=0,
                 trial_length=10000,
                 max_trials=600,
                 timing_mode="timer",
                 **kwargs):

        super(GNGFlashStimulus, self).__init__(stimulus,
                                               encoder=None,
                                               lick_sensors=lick_sensors,
                                               rewards=rewards,
                                               pre_flash_duration=no_lick_duration,
                                               flash_duration=flash_duration,
                                               response_window=response_window,
                                               availability_delay=availability_delay,
                                               extension_duration=0,
                                               timing_mode=timing_mode,
                                               **kwargs)

        self._no_lick_timer = self._pre_flash_timer
        self._no_lick = False

        self._trials = None
        self.set_trials(trial_length, max_trials)

    def set_trials(self, length, max_trials):
        """
        Sets up the time trials with a specific length and max number of trials.
        """
        if self._trials:
            self._trials.stop()
        self._trials = Timetrials(times=[length]*max_trials,
                                  units='ms')
        self._trials.trial_started.connect(self.flash)
        self._trials.all_trials_completed.connect(self.trials_complete)

    def start(self):
        """
        Starts the time trials.
        """
        self._trials.start()
        logging.debug("GNGFlashStimulus time trials started.")

    def flash(self):
        """
        Triggers a flash to begin.
        """
        self._no_lick = True
        super(GNGFlashStimulus, self).flash()

    def _pre_flash_ended(self):
        """
        Pre-flash period has ended.
        """
        self._no_lick = False
        super(GNGFlashStimulus, self)._pre_flash_ended()

    def _lick(self):
        """
        Lick callback.
        """
        if self._no_lick:
            self.abort()
        elif self._available:
            self.hit()
        else:
            self.miss()

    def abort(self):
        """
        Aborts the current trial.
        """
        self._no_lick_timer.stop()
        self._no_lick = False
        self.sigAbort.emit()
        logging.info("Trial aborted @ {}".format(self.update_count))

    def hit(self):
        """
        A hit was triggered.
        """
        self._available = False
        self.sigHit.emit()
        logging.debug("Hit @ {}".format(self.update_count))

    def miss(self):
        """
        A miss occurred.
        """
        self.sigMiss.emit()
        logging.debug("Miss @ {}".format(self.update_count))

    def stop(self):
        """
        Time trials stopped.
        """
        self._trials.stop()
        logging.debug("GNGFlashStimulus time trials stopped.")

    def trials_complete(self):
        """
        Time trials completed.
        """
        logging.debug("GNGFlashStimulus all trials completed.")
        self.sigTrialsComplete.emit()

    def close(self):
        """
        Closes GNG stimulus.
        """
        self._trials.close()
        logging.debug("GNGFlashStimulus time trials closed.")


class Laps(EObject):
    """
    Laps.  Pass it an encoder object.  It tracks the progress and signals
        when laps are started/completed.
    """

    lap_completed = QtCore.Signal(int)
    lap_started = QtCore.Signal(int)
    all_laps_completed = QtCore.Signal(int)
    lap_timed_out = QtCore.Signal(int)

    def __init__(self,
                 encoder,
                 lap_distance=None,
                 lap_timeout=None,
                 lap_limit=None,
                 ):

        super(Laps, self).__init__()

        self._encoder = encoder
        self.lap_limit = lap_limit

        self.completed_laps = []

        self._running = False  #should be on/off?
        self._current_lap_index = 0
        self._current_lap_distance = 0.0
        self._current_lap_length = None
        self._current_lap_timeout = None
        self._lap_timer = None

        self._lap_setup(lap_distance, lap_timeout)

    def _lap_setup(self, lap_distance, lap_timeout):
        """
        Sets up lap plan.
        """
        if isinstance(lap_distance, int):
            self.lap_distance = [lap_distance]
        elif isinstance(lap_distance, (list, tuple, np.ndarray)) or (lap_distance is None):
            self.lap_distance = lap_distance
        else:
            raise TypeError("lap_distance must be int, iterable, or None.")

        if isinstance(lap_timeout, (float, int)):
            self.lap_timeout = [lap_timeout]
        elif isinstance(lap_timeout, (list, tuple, np.ndarray)) or (lap_timeout is None):
            self.lap_timeout = lap_timeout
        else:
            raise TypeError("lap_timeout must be int, float, iterable, or None.")

        if self.lap_timeout:
            self._lap_timer = QtCore.QTimer()

        self._total_distance = 0

        self.set_lap(0)

    def start(self):
        self._running = True
        if self._lap_timer:
            self._lap_timer.start(self._current_lap_timeout)
        logging.info("Laps started.")

    def stop(self):
        self._running = False
        if self._lap_timer:
            self._lap_timer.stop()
        logging.info("Laps stopped.")

    def extend_lap(self, distance):
        """
        Extends the lap by a certain distance.
        """
        self._current_lap_length += distance

    def update(self, index=None):
        """
        Overwrite of EObject update function.  If laps are running, it checks
            encoder and determines if the lap is completed.
        """
        if self._running:
            self._current_lap_distance += self._encoder.value

            if self.lap_distance and self._check_for_distance():
                self.lap_completed.emit(self._current_lap_index)
                self.next_lap()
        else:
            return

    def set_lap(self, lap):
        """
        Sets the lap to a specific index or value.  Resets lap progress.

        args
        ----
        lap : (int) or (tuple)
            Lap integer to move to.  Also accepts tuple formatted (distance,
                timeout)

        """
        if isinstance(lap, int):
            self._current_lap_index = lap
            if self.lap_distance:
                self._current_lap_length = self.lap_distance[lap % len(self.lap_distance)]
            if self.lap_timeout:
                self._current_lap_timeout = self.lap_timeout[lap % len(self.lap_timeout)]
        elif isinstance(lap, (list, tuple, np.ndarray)):
            self._current_lap_length, self._current_lap_timeout = lap
            self._current_lap_index += 1

        if self._current_lap_timeout:
            self.set_lap_timer(self._current_lap_timeout)

        self._current_lap_distance = 0.0

        logging.debug("Lap set to %s" % lap)

    def set_lap_timer(self, sec):
        """
        Sets the lap timer to a specific value.
        """
        self._current_lap_timeout = sec

        if not self._lap_timer:
            self._lap_timer = QtCore.QTimer()

        if self.running:
            self._lap_timer.start(sec*1000)

        logging.info("Lap timer set to %s" % sec)

    def _check_for_distance(self):
        """
        Checks to see if we've run far enough to finish the lap.
        """
        if self._current_lap_distance > self._current_lap_length:
            return True
        else:
            return False

    def next_lap(self):
        """
        Moves to the next lap in the sequence.
        """
        next_lap = self._current_lap_index+1
        self._total_distance += self._current_lap_distance

        self.completed_laps.append(self._current_lap_index)

        if self.lap_limit:
            if next_lap > self.lap_limit:
                self.stop()
                self.all_laps_completed.emit(len(self.completed_laps))
                logging.info("All laps completed.")
                return

        self.set_lap(next_lap)

    def _lap_timeout(self):
        """
        Callback for lap timer.
        """
        self.lap_timed_out.emit(self._current_lap_index)
        logging.info("Lap %s timed out!" % self._current_lap_index)

    def close(self):
        logging.info("Total laps completed: %s" % len(self.completed_laps))
        super(Laps, self).close()


class BehaviorEncoder(EObject):
    """
    Encoder wrapper designed for behavior.  Saves position / voltage
        information every time it is updated.

    TODO: Find the proper place for this.

    """
    def __init__(self, encoder, gain=1.0):
        super(BehaviorEncoder, self).__init__()
        self._encoder = encoder
        self.gain = gain

        for i in range(10):
            self._last_deg = self._encoder.get_degrees()
            if self._last_deg is None:
                time.sleep(0.1)
            else:
                break

        if self._last_deg is None:
            raise ValueError("Unable to read initial degree value from encoder.")

        self._last_dx = 0.0

        self.dx = []
        self._dx = 0

        #should we really keep these?
        self.vin = []
        self.vsig = []

        self.value = self._last_deg

    def get_dx(self):
        """
        Returns the degree rotation since last call to get_dx.
        """
        deg = self._encoder.get_degrees()
        vin = self._encoder.get_vin()
        #vsig = self._encoder.get_vsig()
        #print vin, vsig, deg
        #cover for some weird nidaq errors
        if (6 > vin > 4) & (deg is not None):
            #normal scenario
            dx = deg - self._last_deg
            self._last_deg = deg
        else:
            #weird error, just use last dx
            dx = self._last_dx
            self._last_deg += dx
        return dx

    def update(self, index=0):
        dx = self.get_dx()
        if 180 > dx > -180:  # encoder hasn't looped
            self.value = dx*self.gain
            self._last_dx = dx
        else:
            self.value = self._last_dx*self.gain
        self.dx.append(self._last_dx)

    def set_gain(self, gain):
        self.gain = gain

    def package(self):
        self._encoder = str(self._encoder)
        self.dx = np.array(self.dx, dtype=np.float32)
        return super(BehaviorEncoder, self).package()

class _BaseReward(EObject):
    """
    Base class for rewards.  Used for both keyboard and NIDAQ based rewards.
    """
    rewardtriggered = QtCore.Signal(float)

    def __init__(self):
        super(_BaseReward, self).__init__()
        self.reward_times = []

        self._update_count = 0
        self._rewards_since_last_packet = []
        self._periodic_timer = None

    def update(self, index=None):
        self._update_count += 1

    def reward(self, volume=None):
        """
        Triggers a reward.  Sends signal.
        """
        t = time.clock()
        self.reward_times.append((t, self._update_count))
        self._rewards_since_last_packet.append((t, self._update_count))
        logging.debug("Reward triggered at {}".format(self.reward_times[-1]))

    def set_periodic_reward(self, period_ms):
        """
        Triggers the reward every <period_ms> milliseconds.
        """
        self._periodic_timer = QtCore.QTimer()
        self._periodic_timer.timeout.connect(self.reward)
        self._periodic_timer.start(period_ms)

    def stop_periodic_reward(self):
        """
        Stops giving periodic rewards.
        """
        if self._periodic_timer:
            self._periodic_timer.stop()
            self._periodic_timer = None

    @property
    def _reward_packet(self):
        """ Represents a single packet of reward data for online analysis. """
        rewards = self._rewards_since_last_packet
        self._rewards_since_last_packet = []
        return rewards

    def package(self):
        """
        Package the data.
        """
        if self._periodic_timer:
            self.stop_periodic_reward()
        self.reward_count = len(self.reward_times)
        self.reward_times = np.array(self.reward_times, dtype=np.float32)
        return super(_BaseReward, self).package()

class BehaviorReward(_BaseReward):
    """
    Reward using an NIDAQ reward object.  Includes Qt signal for reward dispense.  tracks
        dispenses and reward times.
    """
    def __init__(self, reward):
        super(BehaviorReward, self).__init__()
        self._reward = reward

    def reward(self, volume=None):
        """
        Triggers NIDAQ reward, then runs _BaseReward.reward()
        """
        self._reward.reward()
        if not volume:
            volume = self._reward.rewardvol
        self.rewardtriggered.emit(self._reward.rewardvol)
        super(BehaviorReward, self).reward()

    def package(self):
        """
        Package the data.
        """
        self.volume_dispensed = self._reward.volumedispensed
        return super(BehaviorReward, self).package()


class KeyboardReward(_BaseReward):
    """
    Uses keystrokes to issue "rewards."
    """
    def __init__(self, window=None, kotkey="r"):
        super(KeyboardReward, self).__init__()

        ##TODO: Handle window=None
        self._window = window

        self.volume_dispensed = 0
        self._reward_volume = 0.008

        self._keys = key.KeyStateHandler()
        if self._window:
            self._window.winHandle.push_handlers(self._keys)

        # lockout timer in case person holds key down
        self._lockout_timer = QtCore.QTimer()
        self._lockout_timer.timeout.connect(self._lockout_ended)
        self._lockout = False

    def update(self, index=None):
        self._check_keys()
        self._update_count += 1

    def _check_keys(self):
        if self._keys[key.R]:
            if not self._lockout:
                self.reward()
                self._lockout = True
                self._lockout_timer.start(200)

    def _lockout_ended(self):
        self._lockout = False
        self._lockout_timer.stop()

    def reward(self, volume=None):
        self.volume_dispensed += self._reward_volume
        self.rewardtriggered.emit(self._reward_volume)
        super(KeyboardReward, self).reward()


class _BaseLickSensor(EObject):
    """ Base class for lick sensors. Used by both NIDAQ and keyboard lick
            sensors.
    """
    lickOccurred = QtCore.Signal()

    def __init__(self):
        super(_BaseLickSensor, self).__init__()

        self.lick_data = []
        self.lick_events = []

        self._events_since_last_packet = []
        self._last_value = 0

    def test(self):
        return True

    def update(self, index=None):
        """
        Updates the data, emits signal if lick occurred.
        """
        data = self.read()
        self.lick_data.append(data)

        if data > self._last_value:
            self.lick_events.append(index)
            self._events_since_last_packet.append(index)
            self.lickOccurred.emit()

        self._last_value = data

    def read(self):
        """
        Returns the current value of the lick sensor.
        """
        return 0

    @property
    def _lick_packet(self):
        """ One packet of lick data destined for display server. """
        events = self._events_since_last_packet
        self._events_since_last_packet = []
        return events

    def package(self):
        self.lick_data = np.where(np.array(self.lick_data, dtype=np.uint8) > 0)
        return super(_BaseLickSensor, self).package()


class BehaviorLickSensor(_BaseLickSensor):
    """
    NIDAQ-based lick sensor.
    """
    def __init__(self, di_task, line):
        super(BehaviorLickSensor, self).__init__()
        self._di_task = di_task
        self.line = line

    def test(self):
        """
        Tests to ensure that the DI line is ok.
        """
        test_data = []
        for i in range(30):
            test_data.append(self.read())
            time.sleep(0.01)
        licktest = np.array(test_data, dtype=np.uint8)
        if len(licktest[np.where(licktest > 0)]) > 25:
            #fail
            return False
        else:
            #pass
            return True

    def read(self):
        """
        Returns the current value of the lick sensor.
        """
        value = self._di_task.read()[self.line]
        return value

    def package(self):
        self._di_task = str(self._di_task)
        return super(BehaviorLickSensor, self).package()


class KeyboardLickSensor(_BaseLickSensor):
    """
    Uses keystrokes to trigger "licks."
    """
    def __init__(self, window=None, hotkey="1"):

        super(KeyboardLickSensor, self).__init__()
        self._window = window

        self._keys = key.KeyStateHandler()
        if self._window:
            self._window.winHandle.push_handlers(self._keys)

        key_map = {"0": key._1, "1": key._2, "2": key._3}

        self._hotkey = key_map[hotkey]

    def test(self):
        if self._window:
            return True
        else:
            return False

    def read(self):
        return self._check_keys()

    def _check_keys(self):
        if self._keys[self._hotkey]:
            return 1
        else:
            return 0


class KeyboardEncoder(object):
    """
    Uses keystrokes in specified window to simulate an encoder.

    DOESNT WORK YET WITHOUT A PYGLET WINDOW.  If we wanted it to we'd need to rewrite
        with lower level windows api hooks.

    """
    def __init__(self, window=None):

        self._window = window
        self.current_value = 0.0

        self._keys = key.KeyStateHandler()
        if self._window:
            self._window.winHandle.push_handlers(self._keys)

    def get_degrees(self):
        #check keys
        #self.window.winHandle.dispatch_events()  #only necessary if we aren't flipping window
        result = self._check_keys()
        #add gain to result
        self.current_value += result
        return self.current_value

    def get_vin(self):
        return 5

    def get_vsig(self):
        return 0

    def _check_keys(self):
        if self._keys[key.D]:
            return 1
        elif self._keys[key.A]:
            return -1
        else:
            return 0


class DummyPsycopyStimulus(object):
    def __init__(self, *args, **kwargs):
        self.pos = (0, 0)
    
    def draw(self):
        pass

    def setOri(self, ori):
        pass

    def setPos(self, pos):
        pass

    def setPhase(self, phase):
        pass

    def setImage(self, image):
        pass

    def setReplaceImage(self, image):
        pass



class LimsBehaviorUpload(object):
    """ Sets up a LIMS behavior upload and writes trigger file. 
        TODO: remove this.  should just use LIMSTK
    """
    def __init__(self, mouse_id, dummy=False):
        super(LimsBehaviorUpload, self).__init__()
        self.mouse_id = mouse_id
        self.dummy = dummy

        self._lims = LimsInterface()

    def upload(self, pickle_path, summary={}):
        """ Package data for Lims.
        """
        try:
            behavior_id = self._lims.get_behavior_id(self.mouse_id)
            trigger_dir = self._lims.get_trigger_dir(self.mouse_id)
        except LimsError:
            logging.warning("LIMS could not be reached.  No session info will be saved.")
            return False

        trigger = BehaviorTriggerFile(trigger_dir=trigger_dir, dummy=self.dummy)

        # summary json
        summary_filename = "{}_{}.json".format(trigger.timestamp,
                                               self.mouse_id)
        summary_path = os.path.join(trigger.incoming_dir, summary_filename)

        # pickle file
        pickle_filename = os.path.basename(pickle_path)
        pickle_destination = os.path.join(trigger.incoming_dir,
                                          pickle_filename)
        zip_destination = pickle_destination.replace(".pkl", ".zip")

        # write them
        try:
            if not os.path.isdir(trigger.trigger_dir):
                os.makedirs(trigger.trigger_dir)
            with open(summary_path, 'w') as f:
                json.dump(summary, f)
            #shutil.copy(pickle_path, pickle_destination)  # unzipped
            zf = zipfile.ZipFile(zip_destination, 'w',
                                 compression=zipfile.ZIP_DEFLATED)  # zipped
            zf.write(pickle_path, os.path.basename(pickle_path))
            zf.close()
        except IOError as e:
            import traceback; traceback.print_exc()
            logging.warning("Incoming directory could not be reached.  No session info will be saved.")
            return

        # lims likes linux pathsfile, new
        summary_path = summary_path.replace("//allen", "/allen")
        zip_destination = zip_destination.replace("//allen", "/allen")

        # finally write trigger file
        fields = {
            "id": behavior_id,
            "output": zip_destination,
            "summary": summary_path,
        }
        trigger_filename = summary_filename.replace(".json", ".bt")
        trigger.write(trigger_filename, fields=fields)
        print("[[TRIGGERED]]")
        return True



if __name__ == '__main__':

    pass

"""
automation.py

Some tools for automation.

@author: derricw

Jan 16 2018

"""
import logging
import random
from experiment import EObject, ETimer


class _BaseMouse(EObject):
    """ _BaseMouse contains everything except behavior logic.

    After attaching to a task, has access to the task's lick sensors,
    encoders, and rewards.

    #TODO: maybe re-think how this works.  Perhaps `behaviors` could be attached
        to some Basic mouse so that different behaviors can be easily mixed and matched,
        rather than extending the basic mouse.
    """
    def __init__(self,
                 encoders=[],
                 lick_sensors=[],
                 rewards=[],
                 ):
        super(_BaseMouse, self).__init__()
        self._encoders = encoders
        self._lick_sensors = lick_sensors
        self._rewards = rewards
        self._task = None

    def attach(self, task):
        """ Attaches the mouse to the task. Gets access to
            lick sensors, encoders, and reward lines.
        """
        self._encoders = getattr(task, "encoders", [])
        self._lick_sensors = getattr(task, "lick_sensors", [])
        self._rewards = getattr(task, "rewards", [])

        task.add_item(self)
        self._task = task

        self._init_behavior()

    def _init_behavior(self):
        """ _Base mouse doesn't have any default behavior.
        """
        pass

    def package(self):
        return {}

    def lick(self, sensor_index=0):
        if self._lick_sensors:
            self._lick_sensors[sensor_index].lickOccurred.emit()


class PerfectDoCMouse(_BaseMouse):
    """ A perfect DoC mouse automatically licks 200ms after change occurs.
    """
    def _init_behavior(self):
        """ Sets up mouse's behavior. """
        self._task.changeOccurred.connect(self._handle_change)

    def _handle_change(self):
        """ Hangles a stimulus change event. """
        logging.info("Perfect mouse handling change event!")
        ETimer.singleShot(0.2, self.lick)


class StupidDoCMouse(_BaseMouse):
    """ A stupid DoC mouse licks randomly every 2-8 seconds """
    def _init_behavior(self):
        self._lick_timer = ETimer()
        self._lick_timer.timeout.connect(self._handle_timer)

    def _get_random_time(self):
        """ gets a random time between 2 and 4 """
        return random.random() * 6 + 2

    def _handle_timer(self):
        logging.info("Stupid mouse is licking for some reason!")
        self.lick()
        t = self._get_random_time()
        self._lick_timer.start(t)
        
    def start(self):
        """ Ran once at experiment start """
        t = self._get_random_time()
        self._lick_timer.start(t)

class VerySpecificMouse(_BaseMouse):
    """ A very specific mouse that licks every trial at a certain time during the 
            stimulus window relative to the scheduled change time.
    """
    def _init_behavior(self):
        self._task._stimulus_window_epoch.epochStarted.connect(self._handle_stim_window)

    def _handle_stim_window(self):
        """ 
        """
        change_time = self._task._current_trial_data['trial_params']['change_time']
        ETimer.singleShot(change_time+0.1, self._handle_timer) # licks 0.1 seconds after change time

    def _handle_timer(self):
        logging.info("Very specific mouse is licking!")
        self.lick()
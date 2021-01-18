###############################################################################
# DoC Day 0
###############################################################################

from camstim.change import DoCTask, DoCStimulus, DoCTrialGenerator
from camstim import Window, Experiment
from psychopy import visual
import logging

# Configure logging level
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Set up display window
window = Window(fullscr=True, screen=1, monitor='testMonitor')

# Set up Task
params = {
    'nidevice': 'Dev2',
    'task_id': "DoC",
    'volume_limit': 1.5, #mL
    'auto_reward_volume': 0.007,
    'pre_change_time' : 2.25,
    'response_window': (0.15, 1.0),
    'stimulus_window': 6.0,
    'periodic_flash': None,
    'max_task_duration_min': 15.0,
    'warm_up_trials': -1,  # infinite
}

f = DoCTask(window=window,
            auto_update=True,
            params=params)

t = DoCTrialGenerator(cfg=f.params) # fix this later
f.set_trial_generator(t)

# Set up our DoC stimulus
obj = DoCStimulus(stimulus=visual.GratingStim(window,
                                              tex='sqr',
                                              units='deg',
                                              size=(300, 300),
                                              sf=0.04,),
                 )
obj.add_stimulus_group("group0", 'Ori', [0])
obj.add_stimulus_group("group1", 'Ori', [90])

# Add our DoC stimulus to the Task
f.set_stimulus(obj, "grating")

# Run it
f.start()


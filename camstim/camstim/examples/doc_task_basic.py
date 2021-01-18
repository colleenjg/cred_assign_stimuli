###############################################################################
# DoC Task Example
###############################################################################

# Imports are subject to change
from camstim.change import DoCTask, DoCStimulus
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
    'mouse_id': "M999999",
    'task_id': "DoC_Test",
    'nidevice': 'Dev1',
    'lick_lines': [0],
    'volume_limit': 1.00, #mL
    'pre_change_time' : 2.0,
    'response_window': (0.15, 2.0),
    'stimulus_window': 6.0,
    'blank_duration_range': (0.5, 0.5),
    'initial_blank': 0.0,
    'timeout_duration': 0.0,
    'min_no_lick_time': 0.3,
    'safety_timer_padding': 5.0,
    'periodic_flash': (0.25, 0.5),
}

f = DoCTask(window=window,
            auto_update=True,
            params=params)

# Set up our DoC stimulus
obj = DoCStimulus(stimulus=visual.GratingStim(window,
                                              units='deg',
                                              size=(30, 30),
                                              mask='circle',
                                              sf=0.1,),
                 )
obj.add_stimulus_group("group0", 'Ori', [0])
obj.add_stimulus_group("group1", 'Ori', [90])

# Add our DoC stimulus to the Task
f.set_stimulus(obj, "grating")

# Run it
f.start()
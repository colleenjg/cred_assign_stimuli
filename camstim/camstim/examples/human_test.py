###############################################################################
# DoC Stage 4 but with a fake mouse
###############################################################################

from camstim.change import DoCTask, DoCImageStimulus, DoCTrialGenerator
from camstim.automation import PerfectDoCMouse, StupidDoCMouse
from camstim import Window, Experiment
import logging

# Configure logging level
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Set up display window
window = Window(fullscr=True, screen=1, monitor='testMonitor')

# Set up Task
params = {
    'nidevice': "Dev1",
    'task_id': "DoC",
    'volume_limit': 1.5, #mL
    'auto_reward_volume': 0.007,
    'reward_volume': 0.007,
    'pre_change_time' : 2.25,
    'response_window': (0.15, 2.0),
    'stimulus_window': 6.0,
    'periodic_flash': (0.25, 0.5),
    'max_task_duration_min': 60.0,
    'catch_freq': 0.125,
    'failure_repeats': 5,
    'warm_up_trials': 0,
}

f = DoCTask(window=window,
            auto_update=True,
            params=params)

#mouse = PerfectDoCMouse()
#mouse = StupidDoCMouse()
#mouse.attach(f)

# Trial Generator
t = DoCTrialGenerator(cfg=params)
f.set_trial_generator(t)

# Set up our DoC stimulus
img_data = "//allen/programs/braintv/workgroups/nc-ophys/Doug/Stimulus_Code/image_dictionaries/Natural_Images_Lum_Matched_set_ophys_0_2017.07.14.pkl"
obj = DoCImageStimulus(window,
                       image_set=img_data,
                       )

# Add our DoC stimulus to the Task
f.set_stimulus(obj, "natual_scenes")

# Run it
f.start()

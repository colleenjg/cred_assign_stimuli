###############################################################################
# Two AFC Task Example
###############################################################################

# Imports are subject to change
from camstim.foraging import AFCForaging, AFCStimulus
from camstim import Window, Experiment, Timetrials
from psychopy import visual
import logging

# Configure logging level
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Set up Experiment
e = Experiment()

# Set up display window
window = Window(fullscr=True, screen=0, monitor='testMonitor')

# Set up foraging
params = {
    'nidevice': 'Dev6',
    'lick_lines': [0, 1],
    'rewardlines': [0, 1],
    'volume_limit': 1.00, #mL
    #'data_export': True,
}

f = AFCForaging(window=window,
                auto_update=True,
                params=params)

# Set up our flash stimulus
obj0 = AFCStimulus(stimulus=visual.GratingStim(window,
                                              units='deg',
                                              size=(30,30),
                                              mask='circle',
                                              sf=0.1,
                                              ori=90,
                                              ),
                   lick_sensors=f.lick_sensors,
                   rewards=f.rewards,
                   flash_duration=1000,
                   response_window=1000,
                   availability_delay=0,
                   )

# Set up our flash stimulus
obj1 = AFCStimulus(stimulus=visual.GratingStim(window,
                                              units='deg',
                                              size=(30,30),
                                              mask='circle',
                                              sf=0.1,
                                              ori=0,
                                              ),
                   lick_sensors=f.lick_sensors,
                   rewards=f.rewards,
                   flash_duration=1000,
                   response_window=1000,
                   availability_delay=0,
                   )

obj0.set_correct_lick_spout(0)
obj1.set_correct_lick_spout(1)

# Add our flash stimulus to Foraging
f.add_stimulus(obj0)
f.add_stimulus(obj1)

f.set_time_trials(lengths_secs=5, max_trials=6)
f.all_trials_completed.connect(e.close)

# Add Foraging to our experiment
e.add_item(f, name='foraging')

# Run it
e.start()
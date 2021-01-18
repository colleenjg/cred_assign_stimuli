"""
Runs a sweepstim 2 test and ensures that the display sequence and sweep table
    match the expected values.

"""

from camstim import SweepStim, Stimulus, Window, Warp
from psychopy import visual

window = Window(fullscr=True, monitor="GammaCorrect30",
                warp=Warp.Spherical)

stim = Stimulus.from_file("natural_scenes.stim", window=window)

ss = SweepStim(window,
               pre_blank_sec=0.0,
               post_blank_sec=0.0)
ss.add_stimulus(stim)

ss.run()
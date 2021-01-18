"""
Creates a stimulus with an auto-generated sweep order then replaces it with a
    custom one.

"""

from camstim import SweepStim, Stimulus, Window
from psychopy import visual

window = Window(fullscr=True, monitor="GammaCorrect20")

stim = Stimulus(visual.GratingStim(window,
                         pos=(0, 0),
                         units='deg',
                         size=(250, 250),
                         mask="None",
                         texRes=256,
                         sf=0.04,
                         contrast=0.8,
                         ),
                sweep_params={
                    'TF': ([1.0, 8.0], 0),
                    'Ori': (range(0, 90, 45), 1),
                    },
                sweep_length=5.0,
                start_time=0.0,
                blank_length=1.0,
                blank_sweeps=2,
                runs=2,
                shuffle=True,
                save_sweep_table=True,
                )

# replace the auto-generated sweep order with a custom one
stim.sweep_order = [0, 1, 0, 1, 0, 1, 0, 1]
# rebuild the frame list (I may make this automatic in the future)
stim._build_frame_list()

ss = SweepStim(window,
               pre_blank_sec=0.0,
               post_blank_sec=0.0)
ss.add_stimulus(stim)

ss.run()
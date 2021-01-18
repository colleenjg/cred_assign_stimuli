from camstim import MovieStim, SweepStim, Window
import logging

logging.basicConfig(level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

window = Window(fullscr=True,
                monitor='testMonitor',
                screen=1,)

g0 = MovieStim(movie_path="//aibsdata/neuralcoding/Saskia/Visual Stimuli 151207/Movie_TOE1.npy",
               window=window,
               frame_length=2.0/60.0,
               size=(1920, 1080),
               start_time=0.0,
               stop_time=None,
               flip_v=True,)

config = {
    'sync_sqr': True,
}

ss = SweepStim(window,
               stimuli=[],
               pre_blank_sec=1,
               post_blank_sec=1,
               params=config,
               )

ss.add_stimulus(g0)

ss.run()

"""
sweepstim.py 2: Sweep Harder

@author: derricw

Experimental rewrite of old SweepStim.

Takes N stimuli, builds N sweep tables and runs all simultaneously.
    Experiment length is determined by the longest display sequence.

This should eventually replace SweepStim in the old stimulus module.

"""
import random
import datetime
import time
import sys
import socket
import os
import logging
import math
import shutil
from collections import OrderedDict

from psychopy import visual, event
import numpy as np

from stim import Stim
from experiment import EObject, OutputFile
from synchro import SyncPulse, SyncSquare
##TODO: find better place for stuff in Core.py
from misc import buildSweepTable, getSweepFrames, getConfig, wecanpicklethat, \
    getMonitorInfo, getPlatformInfo, check_dirs, ImageStimNumpyuByte, CAMSTIM_DIR


class Stimulus(EObject):
    """
    Container for a single stimulus.  Builds its sweep table, allows you to set
        display sequence, etc.

    Args:
        psychopy_stimulus : A psychopy stimulus object.
        sweep_params (dict): A dictionary of stimulus parameters and values to
            build a sweep table with. Ensure that your psychopy stimulus object
            has the parameters. Format is <"Name": ([values], column)>  
            Ex: `{"Ori": ([0, 90, 180], 0)`
        sweep_length (float): number of seconds to display each sweep.
        start_time (float): number of seconds after experiment start to delay
            before stimulus presentation.
        stop_time (float): time to end stimulus presentation, even if there are
            still sweeps left to display.
        blank_length (float): blank time in seconds between sweeps.
        blank_sweeps (int): blank presentation every N sweeps.
        runs (int): number of sweep table repeats.
        shuffle (bool): shuffle sweep display order.
        fps (float): Display FPS.  Should match monitor FPS
        save_sweep_table (bool): whether to save the sweep table values in the
            output file.  Set to false when loading in large tables for movies,
            natural scenes, etc.

    #TODO: make sweep_params optional.

    """
    def __init__(self,
                 psychopy_stimulus,
                 sweep_params,
                 sweep_length,
                 start_time=0.0,
                 stop_time=None,
                 blank_length=0,
                 blank_sweeps=0,
                 runs=1,
                 shuffle=False,
                 fps=60.0,
                 save_sweep_table=True,
                 ):

        self.stim = psychopy_stimulus
        self.sweep_params = sweep_params
        self.sweep_length = sweep_length
        self.start_time = start_time
        self.stop_time = stop_time
        self.blank_length = blank_length
        self.blank_sweeps = blank_sweeps
        self.runs = runs
        self.shuffle = shuffle
        self.fps = fps
        self.save_sweep_table = save_sweep_table

        self.stim_text = ""
        self.stim_path = ""

        self._build_sweep_table()

        self._current_sweep = None
        self.display_sequence = None

        self._build_frame_list()

        self.on_draw = {}

    @staticmethod
    def from_file(path, window):
        """
        Your standard "from_file" staticmethod.  Returns a stimulus defined in
            a file and initializes it to the specified psychopy window.

        TODO: make this safe.

        """
        with open(path, 'r') as f:
            stim_text = f.read()
        stimulus = None
        exec(stim_text)
        stimulus.stim_text = stim_text
        stimulus.stim_path = path
        return stimulus

    def to_file(self, path):
        """
        Writes stimulus to a file.
        """
        raise NotImplementedError("Can't save to file yet.")

    def _build_sweep_table(self):
        """
        Builds sweep table and order.
        """
        ##TODO: review buildSweepTable
        self.sweep_table, self.sweep_order, self.dimnames = buildSweepTable(
            self.sweep_params, self.runs, self.blank_sweeps)
        if self.shuffle:
            random.shuffle(self.sweep_order)

    def _build_sweep_frames(self):
        """
        Build start/stop frame pairs.
        """
        ##TODO: review getSweepFrames
        self.sweep_frames = getSweepFrames(self.sweep_order, self.sweep_length,
                                           0, 0, self.blank_length, self.fps)

    def _build_frame_list(self):
        """
        Builds frame array.  Array is -1 for blank periods, and sweep # otherwise.
        """

        #we don't want to build a normal frame list if we have a custom
        #display sequence
        if self.display_sequence is not None:
            self.set_display_sequence(self.display_sequence)
            return

        self._build_sweep_frames()

        seq = []

        # start time
        seq.extend([-1]*int(self.fps*self.start_time))

        # sweeps
        for index, sweep in enumerate(self.sweep_frames):
            seq.extend([self.sweep_order[index]]*(int(sweep[1]-sweep[0]+1)))
            seq.extend([-1]*int(self.fps*self.blank_length))

        # stop time?
        if self.stop_time:
            stop_frame = int(self.fps*self.stop_time)
            seq = seq[:stop_frame]

        self.frame_list = np.array(seq, dtype=np.int32)
        self.total_frames = len(self.frame_list)

    def get_total_frames(self):
        """
        Returns the total # of frames in the experiment.

        Returns:
            int: total frames in experiment.

        """
        return len(self.frame_list)

    def get_total_time(self):
        """
        Gets the total length of the stimulus in seconds.

        Returns
            float: length of experiment in seconds.

        """
        return float(self.total_frames)/self.fps

    def get_display_sequence(self):
        """
        Gets the current display sequence.  If there is no custom sequence,
            then [(start_time, stop_time)] is returned.
        """
        if self.display_sequence is not None:
            return self.display_sequence
        else:
            return np.array([(self.start_time, self.stop_time)])

    def update(self, frame):
        """
        Updates the stimulus based on the current frame.

        Args:
            frame (int): frame number for this update.
        """
        self.current_frame = frame
        try:
            sweep_number = self.frame_list[frame]
        except IndexError:
            #stimulus finished
            return
        if sweep_number == self._current_sweep:
            #still on same sweep
            pass
        elif sweep_number == -1:
            #on a grey screen or blank screen
            return
        else:
            #new sweep
            # TODO: do this zip() operation elsewhere for performance
            for k, v in zip(self.dimnames, self.sweep_table[
                            sweep_number]):
                try:
                    set_function = getattr(self.stim, "set%s" % k)
                    set_function(v)
                except Exception as e:
                    if k == 'TF':
                        self.on_draw[k] = v
                    elif k == 'PosX':
                        self.stim.setPos((v, self.stim.pos[1]))
                    elif k == 'PosY':
                        self.stim.setPos((self.stim.pos[0], v))
                    else:
                        print("Sweep param incorrectly formatted:", k, v, e)
        self._current_sweep = sweep_number

        self.draw()

    def draw(self):
        """
        Draws the stimulus.  Implements any "on_draw" effects.
        """
        for k, v in self.on_draw.iteritems():
            if k == 'TF':
                v = float(v)
                self.stim.setPhase(v*self.current_frame/self.fps)
        self.stim.draw()

    def set_fps(self, fps):
        """
        Have to rebuild the frame list every time we change fps.
        """
        self.fps = fps
        self._build_frame_list()

    def set_start_time(self, start_time):
        """
        Have to rebuild the frame list every time we change start time.
        """
        self.start_time = start_time
        self._build_frame_list()

    def set_stop_time(self, stop_time):
        """
        Have to rebuild the frame list every time we change stop time.
        """
        self.stop_time = stop_time
        self._build_frame_list()

    def set_blank_length(self, blank_length):
        """
        Sets a new blank length and rebuilds frame list.
        """
        self.blank_length = blank_length
        self._build_frame_list()

    def set_sweep_length(self, sweep_length):
        """
        Sets a new sweep length and rebuilds frame list.
        """
        self.sweep_length = sweep_length
        self._build_frame_list()

    def set_runs(self, runs):
        """
        Sets a new run amount. Rebuilds sweep table and frame list.
        """
        self.runs = runs
        self._build_sweep_table()
        self._build_frame_list()

    def set_blank_sweeps(self, blank_sweeps):
        """
        Sets a new blank sweeps. Rebuilds sweep table and frame list.
        """
        self.blank_sweeps = blank_sweeps
        self._build_sweep_table()
        self._build_frame_list()

    def set_sweep_order(self, sequence):
        """
        Sets the sweep order and rebuilds the frame list.

        Args:
            sequence (iterable): list or tuple or ndarray

        """
        self.sweep_order = sequence
        self._build_frame_list()

    def set_display_sequence(self, display_intervals):
        """
        Sets the stimulus to display in custom intervals defined by a sequence
            of the format [(start0, stop0),...,(startN, stopN)] where all
            values are float seconds.

        Overwrites the current frame list.  This overrides start_time and
            stop_time.
        
        args:
            display_intervals : tuple or list
                Tuple or list of intervals in the form [(start, stop),...

        """
        seq = []

        display_intervals = np.array(display_intervals)  # rectangular

        #ensure the display intervals are formatted correctly
        if display_intervals.shape[1] != 2:
            raise ValueError("Display intervals must be of shape Nx2")

        #ensure no negative values
        if (display_intervals < 0).any():
            raise ValueError("Do you have a time machine? No negative times, plz.")

        #ensure that all stops are after their starts
        if not (display_intervals[:, 1]-display_intervals[:, 0] > 0).all():
            raise ValueError("Interval cannot stop before it starts.")

        #ensure that all starts and stops are monotonically increasing
        if not (np.diff(display_intervals[:, 0]) > 0).all():
            raise ValueError("Starts are not monotonically increasing.")
        if not (np.diff(display_intervals[:, 1]) > 0).all():
            raise ValueError("Stops are not monotonically increasing.")

        #build the basic list assuming no gaps
        seq0 = []

        self._build_sweep_frames()

        for index, sweep in enumerate(self.sweep_frames):
            seq0.extend([self.sweep_order[index]]*(int(sweep[1]-sweep[0]+1)))
            seq0.extend([-1]*int(self.fps*self.blank_length))

        #create a new sequence that includes the display intervals
        seq = []
        s0 = display_intervals[0,0]  #first start
        seq.extend([-1]*int(self.fps*s0))  #pad until first start

        for i, (start, stop) in enumerate(display_intervals):
            frames_to_add = int((stop-start)*self.fps)
            seq.extend(seq0[:frames_to_add])
            try:
                next_start = display_intervals[i+1, 0]
            except IndexError:
                #end of sequence
                break
            grey_frames_to_add = int((next_start-stop)*self.fps)
            seq.extend([-1]*grey_frames_to_add)
            seq0 = seq0[frames_to_add:]

        self.frame_list = np.array(seq, dtype=np.int32)
        self.total_frames = len(self.frame_list)
        self.display_sequence = display_intervals#.tolist()

    def package(self):
        """
        Package for serializing.  Basically get rid of stuff that won't
            unpickle well.
        """
        if not self.save_sweep_table:
            self.sweep_table = None
            self.sweep_params = self.sweep_params.keys()
        self_dict = self.__dict__
        self_dict['stim'] = str(self_dict['stim'])
        return wecanpicklethat(self_dict)

class GratingStim(Stimulus):
    """
    A grating stimulus.  Takes all kwards that a psychopy GratingStim takes,
        plus the ones that Stimulus takes.
    """
    def __init__(self,
                 window,
                 sweep_params,
                 tex='sin',
                 mask='none',
                 units="",
                 pos=(0.0,0.0),
                 size=None,
                 sf=None,
                 ori=0.0,
                 phase=0.0,
                 contrast=1.0,
                 opacity=1.0,
                 maskParams=None,
                 color=(1.0,1.0,1.0),
                 texRes=128,
                 start_time=0.0,
                 stop_time=None,
                 blank_length=0,
                 blank_sweeps=0,
                 runs=1,
                 shuffle=False,
                 fps=60.0,
                 interpolate=False,
                 ):
        psychopy_stimulus = visual.GratingStim(window,
                                               tex=tex,
                                               mask=mask,
                                               units=units,
                                               pos=pos,
                                               size=size,
                                               sf=sf,
                                               ori=ori,
                                               phase=phase,
                                               contrast=contrast,
                                               opacity=opacity,
                                               maskParams=maskParams,
                                               interpolate=interpolate,
                                               color=color,
                                               texRes=texRes)
        super(GratingStim, self).__init__(sweep_params,
                                          start_time=start_time,
                                          stop_time=stop_time,
                                          blank_length=blank_length,
                                          blank_sweeps=blank_sweeps,
                                          runs=runs,
                                          shuffle=shuffle,
                                          fps=fps,
                                          save_sweep_table=True)


class MovieStim(Stimulus):
    """
    A movie stimulus designed for playing Numpy uint8 movies of arbitrary
        size/resolution.
    """
    def __init__(self,
                 movie_path,
                 window,
                 frame_length,
                 size=(640,480),
                 pos=(0,0),
                 start_time=0.0,
                 stop_time=None,
                 blank_length=0,
                 blank_sweeps=0,
                 runs=1,
                 shuffle=False,
                 fps=60.0,
                 flip_v=False,
                 flip_h=False,
                 interpolate=False,
                 ):

        self.movie_path = movie_path
        self.frame_length = frame_length

        movie_data = self.load_movie(movie_path)

        psychopy_stimulus = ImageStimNumpyuByte(window,
                                                image=movie_data[0],
                                                size=size,
                                                pos=pos,
                                                units='pix',
                                                flipVert=flip_v,
                                                flipHoriz=flip_h,
                                                interpolate=interpolate)
        sweep_params = {
            'ReplaceImage': (movie_data, 0),
        }
        super(MovieStim, self).__init__(psychopy_stimulus,
                                        sweep_params,
                                        sweep_length=frame_length,
                                        start_time=start_time,
                                        stop_time=stop_time,
                                        blank_length=blank_length,
                                        blank_sweeps=blank_sweeps,
                                        runs=runs,
                                        shuffle=shuffle,
                                        fps=fps,
                                        save_sweep_table=False)

    def _local_copy(self, source):
        """
        Creates a local copy of a movie.
        """
        filename = os.path.basename(source)
        local_dir = os.path.join(CAMSTIM_DIR, "movies")
        check_dirs(local_dir)
        local_path = os.path.join(local_dir, filename)
        if os.path.isfile(local_path):
            print("Movie file already exists locally @ {}".format(local_path))
        else:
            print("Movie not saved locally, copying...")
            shutil.copy(source, local_path)
            print("... Done!")
        return local_path

    def load_movie(self, path):
        """
        Loads a movie from a specified path.  Currently only supports .npy files.
        """
        if path[-3:] == "npy":
            return self.load_numpy_movie(path)
        else:
            raise IOError("Incorrect movie file type.")

    def load_numpy_movie(self, path):
        """
        Loads a numpy movie.  Ensures that it is read as a contiguous array and
            three dimensional.
        """
        self.movie_local_path = self._local_copy(path)
        movie_data = np.ascontiguousarray(np.load(self.movie_local_path))

        # check shape/type
        if movie_data.ndim != 3:
            raise ValueError("Movie must have 3 dimenstions: (t, y, x))")
        if not movie_data.dtype in [np.uint8, np.ubyte]:
            raise ValueError("Movie must be dtype numpy.uint8")

        return movie_data

class NaturalScenes(Stimulus):
    """
    Modified version of Stimulus class for natural scenes.  Has special sweep
        table and update method.

    TODO: remove any code overlap with `Stimulus`

    """
    def __init__(self,
                 image_path_list,
                 window,
                 sweep_length,
                 pos=(0,0),
                 start_time=0.0,
                 stop_time=None,
                 blank_length=0,
                 blank_sweeps=0,
                 runs=1,
                 shuffle=False,
                 fps=60.0,
                 ):

        if isinstance(image_path_list, str):
            # probably a folder of images
            if os.path.isdir(image_path_list):
                self._image_path_list = [os.path.join(image_path_list,f) for f in
                                        os.listdir(image_path_list) if len(f) > 4 and 
                                        f[-4:] in ['.jpg','.png','.tif','tiff']]
            else:
                # a single image
                self._image_path_list = [image_path_list]
        else:
            # a list of image paths
            self._image_path_list = image_path_list

        # load the images, save a list of paths that were successfully loaded.
        self.stim = []
        self.image_path_list = []
        
        from camstim.misc import ImageStimNumpyuByte
        import matplotlib.pyplot as plt
        
        for img_path in self._image_path_list:
            try:
                img = plt.imread(img_path).astype(np.ubyte)
                scene = ImageStimNumpyuByte(window,
                                            image=img,
                                            pos=pos,
                                            size=img.shape[::-1],
                                            units="pix",
                                            flipVert=True)
                
                self.stim.append(scene)
                self.image_path_list.append(img_path)
            except (IOError, ValueError) as e:
                import traceback; traceback.print_exc()
                print("Failed to load: {} It will be skipped.".format(img_path))

        self.sweep_length = sweep_length
        self.start_time = start_time
        self.stop_time = stop_time
        self.blank_length = blank_length
        self.blank_sweeps = blank_sweeps
        self.runs = runs
        self.shuffle = shuffle
        self.fps = fps

        self.stim_text = ""
        self.stim_path = ""

        self.save_sweep_table = True

        self._build_sweep_table()

        self._current_sweep = None
        self.display_sequence = None

        self._build_frame_list()

        self.on_draw = {}

    def _build_sweep_table(self):
        """
        Overwrites the stimulus `_build_sweep_table` method.
        """
        self.sweep_table, self.sweep_order, self.dimnames = [], range(len(self.stim)), []
        if self.blank_sweeps is not 0:
            segments = [self.sweep_order[i:i+self.blank_sweeps] for i in range(0, len(self.sweep_order), self.blank_sweeps)]
            self.sweep_order = []
            for x in segments:
                for y in x:
                    self.sweep_order.append(y)
                if len(x) == self.blank_sweeps:
                    self.sweep_order.append(-1)
        self.sweep_order *= self.runs

        if self.shuffle:
            random.shuffle(self.sweep_order)


    def update(self, frame):
        """
        Updates the stimulus based on the current sweep.
        """
        self.current_frame = frame
        try:
            sweep_number = self.frame_list[frame]
        except IndexError:
            #stimulus finished
            return
        if sweep_number == self._current_sweep:
            #still on same sweep
            pass
        elif sweep_number == -1:
            #on a grey screen or blank screen
            return
        else:
            #new sweep
            self._current_sweep = sweep_number

        self.draw()

    def draw(self):
        self.stim[self._current_sweep].draw()


class StimulusArray(Stimulus):
    """
    A stimulus array.  They can have different sweep tables but they are always
        displayed together.  Just for convenience so that we can treat several
        `Stimulus` objects as a single object.
    """
    def __init__(self,
                 stimuli,
                 sweep_length,
                 blank_length=0.0,
                 start_time=0.0,
                 stop_time=None,
                 runs=1,):

        self.stimuli = stimuli
        self.set_sweep_length(sweep_length)
        self.set_blank_length(blank_length)
        self.set_start_time(start_time)
        self.set_stop_time(stop_time)

        self.display_sequence = None


    def get_display_sequence(self):
        if self.display_sequence is not None:
            return self.display_sequence
        else:
            return [(self.start_time, self.stop_time)]
        
    def set_sweep_length(self, sweep_length):
        self.sweep_length = sweep_length
        for stim in self.stimuli:
            stim.set_sweep_length(sweep_length)

    def set_blank_length(self, blank_length):
        self.blank_length = blank_length
        for stim in self.stimuli:
            stim.set_blank_length(blank_length)

    def set_start_time(self, start_time):
        self.start_time = start_time
        for stim in self.stimuli:
            stim.set_start_time(start_time)

    def set_stop_time(self, stop_time):
        self.stop_time = stop_time
        for stim in self.stimuli:
            stim.set_stop_time(stop_time)

    def set_runs(self, runs):
        self.runs = runs
        for stim in self.stimuli:
            stim.set_runs(runs)

    def set_display_sequence(self, display_intervals):
        for stim in self.stimuli:
            stim.set_display_sequence(display_intervals)
        self.display_sequence = display_intervals

    def draw(self):
        for stim in self.stimuli:
            stim.draw()

    def update(self, frame):
        for stim in self.stimuli:
            stim.update(frame)

    def package(self):
        self.stimuli = [stim.package() for stim in self.stimuli]
        return wecanpicklethat(self.__dict__)

    def get_total_frames(self):
        return max([stim.total_frames for stim in self.stimuli])


class SweepStim(Stim):
    """
    Plays a set of stimuli in an ordered fashion.

    args:
        window (psychopy.visual.Window): Window to display to.
        stimuli (list): list of stimulus objects
        pre_blank_sec (float): Pre-experiment blank period in seconds
        post_blank_sec (float): Post-experiment blank period in seconds
        params (dict): Dictionary of optional configuration values
        nidaq_tasks (dict): nidaq tasks to use
        movie_output (str): path for writing the simulus frames

    """
    def __init__(self,
                 window,
                 stimuli=[],
                 pre_blank_sec=0.0,
                 post_blank_sec=0.0,
                 params={},
                 nidaq_tasks={},
                 movie_output="",
                 **kwargs):

        super(SweepStim, self).__init__(window=window,
                                        params=params,
                                        **kwargs)

        self.config = self.load_config(self.config_path, 'SweepStim',
                                       override=self.params)
        self.lims_config = self.load_config(self.config_path, 'LIMS',
                                            override=self.params)
        self.sync_config = self.load_config(self.config_path, "Sync",
                                            override=self.params)

        self.pre_blank_sec = pre_blank_sec
        self.post_blank_sec = post_blank_sec
        self.nidaq_tasks = nidaq_tasks  #TODO: do something with these.
        self.movie_output = movie_output

        self.sweepstim_text = ""

        self.stimuli = []

        for stim in stimuli:
            self.add_stimulus(stim)

        self.items = OrderedDict()

        self.primary_stimulus = None

        self.vsynccount = 0

        #set up required submodules
        self._setup_syncpulse()
        self._setup_syncsquare()
        self._setup_controlstream()

        # BACKWARDS COMPATIBILITY, REMOVE LATER
        self.di, self.do = None, None
        

    @staticmethod
    def from_file(path, window):
        """
        Your standard "from_file" staticmethod.  Returns a sweepstim defined in
            a file and initializes it in the specified psychopy window.

        TODO: Come up with a safe way to do this.  Json maybe?
        """
        with open(path, 'r') as f:
            ss_text = f.read()
        sweepstim = None
        exec(ss_text)
        sweepstim.sweepstim_text = ss_text
        return sweepstim

    def load_config(self, path, section, override={}):
        """
        Reads the config file for the specified section.
        """
        config = getConfig(section, path)
        for k in override.keys():
            if k in config.keys():
                config[k] = override[k]
        return config

    def _setup_syncpulse(self):
        """
        Sets up the sync pulse.

        """
        try:
            frame_pulse = self.sync_config['frame_pulse']
            acq_on_pulse = self.sync_config['acq_on_pulse']

            if frame_pulse:
                device, port, line = frame_pulse
                self.framepulse = SyncPulse(device, port, line)
                self.framepulse.set_low()
            else:
                self.framepulse = None

            if acq_on_pulse:
                device, port, line = acq_on_pulse
                self.onpulse = SyncPulse(device, port, line)
                self.onpulse.set_low()
            else:
                self.onpulse = None
        except Exception as e:
            logging.warning("Failed to set up sync pulse: {}".format(e))

    def _setup_syncsquare(self):
        """
        Creates sync square object and adds it to experiment.

        """
        sync_sqr = self.sync_config['sync_sqr']
        sync_sqr_loc = self.sync_config['sync_sqr_loc']
        sync_sqr_size = self.sync_config['sync_sqr_size']
        sync_sqr_color_sequence = self.sync_config['sync_sqr_color_sequence']
        sync_sqr_freq = self.sync_config['sync_sqr_freq']

        if sync_sqr:
            self._syncsqr = SyncSquare(window=self.window,
                                       pos=sync_sqr_loc,
                                       frequency=sync_sqr_freq,
                                       size=sync_sqr_size,
                                       colorSequence=sync_sqr_color_sequence)
            self.add_item(self._syncsqr, name="sync_square")
        else:
            self._syncsqr = None

    def _setup_controlstream(self):
        """
        Sets up control steam socket to receive commands.

        TODO:
            - port should be configurable in some way.
        """
        try:
            controlstream = ControlStream(1111, self)
            self.add_item(controlstream, name="control_stream")
        except Exception as e:
            logging.exception("Failed to set up control stream: {}".format(e))

    def set_datastream(self, datastream):
        """
        Adds info to a datastream header.
        """
        extra_data = {
            'passive_stimulus': {
                'expected_duration_sec': self._count_total_frames()/60,
                'block_segments': [stim.display_sequence for stim in self.stimuli]
            }
        }
        datastream.add_init_data(extra_data)

    def add_stimulus(self, stimulus, index=None):
        """
        Adds a stimulus object or file path.
        """
        if type(stimulus) is str:
            stimulus = self._load_stimulus(stimulus)

        #stimulus.set_fps(self.fps)
        if index:
            self.stimuli.insert(index, stimulus)
        else:
            self.stimuli.append(stimulus)

    def _load_stimulus(self, path):
        """
        Load a stimulus from a file.
        """
        return Stimulus.from_file(path, self.window)

    def remove_stimulus(self, stimulus=None, index=None):
        """
        Removes a stimulus object.
        """
        if index:
            self.stimuli.pop(index)
        else:
            self.stimuli.remove(stimulus)

    def add_item(self, item, name=""):
        """
        Adds an item to the experiment.
        """
        if not name:
            length = len(self.items.keys())
            name = "unnamed_item_%s" % length

        item._parent = self
        self.items[name] = item

        # TODO: merge this into EObject
        if item.has_item("data_source"):
            self.set_datastream(item.get_item("data_source"))

    def remove_item(self, item=None, name=""):
        """
        Removes an item by name or reference.
        """
        if item:
            for k, v in self.items.iteritems():
                if item is v:
                    del self.items[k]
                    break
        else:
            del self.items[name]

    def run(self):
        """
        Runs the stimulus experiment.

        1) Sets up the experiment with `_setup_run`
        2) Iterates through each frame of the experiment.  Updates stimuli and
            items between each frame.
        3) Takes down the run with `_takedown_run`

        """
        self._setup_run()

        # experiment
        for frame in range(self.total_frames):
            self.update(frame)

        self._takedown_run()

    def _setup_run(self):
        """
        Sets up an experiment.

        1) Starts all items.
        2) Counts the total frames for the experiment.
        3) Sets "on" pulse high.
        4) Waits for `trigger_delay_sec` seconds.
        5) Plays grey screen to get ready for first official frame.
        6) Plays grey screen for `pre_blank_sec` seconds.  These are "official"
            frames that count toward the total frames of the experiment.

        """

        for i in self.items.values():
            i.start()

        #import pdb; pdb.set_trace()
        self.total_frames = self._count_total_frames()

        self._printExpInfo()

        if self.onpulse:
            self.onpulse.set_high()

        self.window.setRecordFrameIntervals(False)

        #Post-start-trigger delay (Default is 0.0 seconds)
        self._trigger_delay()

        #Flip for 1/2 second
        self._splash_grey(int(self.fps/2))

        self.startdatetime = datetime.datetime.now()
        self.start_time = time.time()
        self.window.setRecordFrameIntervals(True)

        # pre blank
        for frame in range((int(self.pre_blank_sec*self.fps))):
            self._blank_period(frame)

    def _takedown_run(self):
        """
        Post-run takedown.

        1) Plays grey screen for `post_blank_sec`
        2) Runs the `_finalize` method.

        """
        # post blank
        for frame in range((int(self.post_blank_sec*self.fps))):
            self._blank_period(frame)

        self._finalize()

    def setPrimaryStimulus(self, index):
        """
        Deprecated.
        """
        self.set_primary_stimulus(index)

    def set_primary_stimulus(self, index):
        """
        Experiment will end when primary stimulus ends.
        """
        if index < len(self.stimuli):
            self.primary_stimulus = index
        else:
            raise IndexError('There are only %i stimuli.' % len(self.stimuli))

    def update(self, frame):
        self._update_stimuli(frame)
        self._update_items(frame)
        self.flip()
        self.vsynccount += 1
        self._check_keys()

    def flip(self):
        if self.framepulse:
            self.framepulse.set_high()
        self.window.flip()
        if self.framepulse:
            self.framepulse.set_low()
        if self.movie_output:
            self.window.getMovieFrame()

    def _update_stimuli(self, frame):
        for stim in self.stimuli:
            stim.update(frame)

    def _update_items(self, frame):
        for item in self.items.values():
            item.update(frame)

    def _check_keys(self):
        for keys in event.getKeys(timeStamped=True):
            if keys[0]in ['escape', 'q']:
                self.escape_pressed = True
                self._finalize()

    def _printExpInfo(self):

        total_frames = self._count_total_frames()
        exp_time_sec = (self.pre_blank_sec + self.post_blank_sec +
                        total_frames / self.fps)
        exp_time_frames = int(exp_time_sec*self.fps)
        timestr = str(datetime.timedelta(seconds=exp_time_sec))
        endtime = str(datetime.datetime.now() +
                      datetime.timedelta(seconds=exp_time_sec))
        print("Expected experiment duration: %s" % timestr)
        print("Expected end time: %s" % endtime)
        print("Expected vsyncs: %s" % exp_time_frames)

    def _count_total_frames(self):
        if not self.stimuli:
            return 0
        if not self.primary_stimulus:
            total_frames = max([s.get_total_frames() for s in self.stimuli])
        else:
            total_frames = self.stimuli[
                self.primary_stimulus].get_total_frames()
        return total_frames

    def _finalize(self):
        """
        Stops the experiment and prepares for cleanup.

        1) Plays grey screen for 0.5 seconds.
        2) Waits for `trigger_delay_sec` seconds.
        3) Sets "on" pulse low.
        4) Closes the window.
        5) Prints experiment duration info for user.
        6) Runs `_cleanup` to shut down hardware and save output files.
        7) Closes python interpreter.

        """
        self.window.setRecordFrameIntervals(False)
        self.stop_time = time.time()

        #Flip for 1/2 second
        self._splash_grey(int(self.fps/2))

        #Pre-stop-trigger delay (Default is 0.0 seconds)
        self._trigger_delay()

        if self.onpulse:
            self.onpulse.set_low()

        if self.movie_output:
            self.window.saveMovieFrames(self.movie_output)

        try:
            self.window.close()
        except:
            #window is already closed.  New versions of psychopy don't seem
            #to have this problem.
            pass

        timestr = str(datetime.timedelta(seconds=(
            self.stop_time-self.start_time)))
        self.stopdatetime = datetime.datetime.now()
        print("Actual experiment duration: %s" % timestr)
        print("Actual vsync count: %i" % self.vsynccount)
        print("Actual end time: %s" % str(self.stopdatetime))

        self.printFrameInfo()  #also saves intervalsms

        self._cleanup()

        sys.exit(0)

    def package(self):
        """
        Package method.  Converts self, stimuli, and all items into a picklable
            dictionary and returns it.
        """
        self.items = OrderedDict({k: v.package() for k, v in self.items.iteritems()})
        self.stimuli = [stim.package() for stim in self.stimuli]

        self.scripttext = open(self.script, 'r').read()
        self.monitor = getMonitorInfo(self.monitor)
        self.platform = getPlatformInfo()

        if hasattr(self.window, "get_config"):  #backwards compatibility.  remove when people stop using visual.window
            self.window = self.window.get_config()
        else:
            self.window = str(self.window)

        return self.__dict__

    def _cleanup(self):
        """
        Close all IO and save log files.
        """
        #close any items
        for i in self.items.values():
            i.close()

        #save output
        self._save_output()

    def _save_output(self):
        """
        Saves the experiment data to a file.
        """
        packaged = self.package()
        packaged = wecanpicklethat(packaged)

        output_file = OutputFile()
        #_ = [pprint.pprint(item) for item in wecanpicklethat(self.__dict__).items()]
        output_file.add_data(packaged)

        output_filename = os.path.splitext(os.path.basename(self.script))[0] + ".pkl"
        logdir = os.path.join(CAMSTIM_DIR, 'output')
        output_path = os.path.join(logdir, output_filename)

        logging.info("saving pkl file at %s..." % output_path)
        output_file.save(output_path)
        logging.info("output saved successfully!")

        backupdir = self.config['backupdir']
        mouseid = self.config['mouseid']
        if backupdir:
            mouse_dir = os.path.join(backupdir, mouseid+"/output")
            backup_path = os.path.join(mouse_dir, output_filename)
            logging.info("Backing up pkl file at %s" % backup_path)
            output_file.save(backup_path)
            logging.info("Backup complete!")

        # LIMS
        lims_upload = self.lims_config['lims_upload']
        lims_dummy = self.lims_config['lims_dummy']
        if lims_upload:
            logging.info("Beginning LIMS upload for mouse: {}".format(mouseid))
            from foraging import LimsBehaviorUpload
            lbi = LimsBehaviorUpload(mouseid, dummy=lims_dummy)
            summary = {}  # for now
            success = lbi.upload(output_file.path, summary)
            if success:
                logging.info("LIMS upload complete!")
            else:
                logging.info("LIMS upload failed.")

    def _trigger_delay(self):
        """
        Trigger delay for output trigger.
        """
        delay_sec = self.config['trigger_delay_sec']
        delay_frames = int(delay_sec*self.fps)
        for i in range(delay_frames):
            self.window.flip()

    def _splash_grey(self, frames):
        """
        Pre and post experiment grey period.  Special syncsqr behavior.
        """
        if self._syncsqr:
            old_sync_freq = self._syncsqr.frequency
            self._syncsqr.frequency = 5  # hard code start-stop indicator to 5?
        for i in range(frames):
            if self._syncsqr:
                self._syncsqr.update(i)
            self.window.flip()
        if self._syncsqr:
            self._syncsqr.frequency = old_sync_freq

    def _blank_period(self, frame):
        """
        Updates items but not stimuli.
        """
        self._update_items(frame)
        self.flip()
        self.vsynccount += 1
        self._check_keys()





class ControlStream(EObject):
    """
    Stream for socket commands.  Allows commands from the agent.

    #TODO: replace this with something like ZMQ or ZRO

    """
    def __init__(self, port, parent):
        super(ControlStream, self).__init__()
        self.port = port
        self.parent = parent

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', self.port))
        self.sock.settimeout(0.0)

    def update(self, frame):
        if frame % 10 == 0:
            try:
                data, addr = self.sock.recvfrom(48)
                if data:
                    data = data.split(' ')
                    self._handleCommand(data)
            except socket.error as e:
                pass
            except Exception as e:
                print("Controlstream error: %s" % e)

    def _handleCommand(self, command):
        """
        Handles a command from a UDP source.

        TODO:
            - Make this not totally fucking insane.
        """

        if command[0] == 'SET':
            try:
                name = command[1].split('.')
                newvalue = eval(command[2])
                if len(name,) == 2:
                    oldvalue = getattr(eval("self."+name[0]), name[1])
                    if type(oldvalue) == type(newvalue):
                        setattr(eval("self.parent."+name[0]), name[1], newvalue)  # value is in child object
                    else:
                        try:
                            oldtype = type(oldvalue)  # cast as new type?
                            newvalue = oldtype(newvalue)
                            setattr(eval("self.parent."+name[0]), name[1], newvalue)  # value is in child object
                        except:
                            raise TypeError('Old value is %s, new value is %s' % (
                                type(oldvalue), type(newvalue)))
                elif len(name,) == 1:
                    oldvalue = getattr(self, name[0])
                    if type(oldvalue) == type(newvalue):
                        setattr(self.parent, name[0], newvalue)  # value is in self
                    else:
                        try:
                            oldtype = type(oldvalue)
                            newvalue = oldtype(newvalue)
                            setattr(self.parent, name[0], newvalue)
                        except:
                            raise TypeError('Old value is %s, new value is %s' % (
                                type(oldvalue), type(newvalue)))
                elif len(name,) > 2:
                    raise ValueError('Command could not be parsed. Check formatting.')
                commandlist = (command[1], oldvalue, newvalue, self.vsynccount)
                self.commandrecord.append(commandlist)
                print(commandlist)
            except Exception as e:
                print("Failed to set value: %s" % e)

        elif command[0] == 'GET':
            ##TODO: Do something with value that we get...
            try:
                name = command[1].split('.')
                if len(name,) == 2:
                    value = getattr(eval("self.parent."+name[0]), name[1])
                elif len(name,) == 1:
                    value = getattr(self.parent, name[0])
            except Exception as e:
                print("Failed to get value: %s" % e)

        elif command[0] == 'RUN':
            try:
                methodname = command[1]  # currently only works with no args
                getattr(self.parent, methodname)()
                commandlist = (command[1], self.vsynccount)
                self.commandrecord.append(commandlist)
                print(commandlist)
            except Exception as e:
                print("Failed to run method: %s" % e)
        else:
            print("Couldn't parse received command: %s" % command)

    def package(self):
        self.sock = str(self.sock)
        self.parent = str(self.parent)
        return super(ControlStream, self).package()


def interleave(stimulus_list,
               intervals,
               shuffle=False,
               flatten=False,
               ):
    """
    Creates custom display sequences for each stimuli in a list, such that they
        are interleaved.

    args
    ----
    stimulus_list : list
        List of stimuli to interleave.
    intervals : list
        Duration of segments for each stimuli in seconds.
    shuffle : bool
        Randomize presentation order. (doesn't do anything yet).
    flatten : bool
        Squeezes end of presentation if some stimuli have ended while others
        are still going. (doesn't do anything yet)

    """
    # if intervals is an integer convert it to a list
    if isinstance(intervals, (int, float)):
        intervals = [[intervals]*len(stimulus_list)]

    if (len(stimulus_list) != len(intervals)):
        raise ValueError("Stimulus and interval lists must be same length.")

    #how many intervals for each stimulus?
    interval_count = []
    for i, (stim, interval) in enumerate(zip(stimulus_list, intervals)):
        stim.set_start_time(0.0)
        tt = stim.get_total_time()
        interval_count.append(int(math.ceil(tt/interval)))  #round up

    #create a display sequence for each stimulus and apply it
    for i, (stim, interval) in enumerate(zip(stimulus_list, intervals)):
        epoc_length = sum(intervals)
        pre_length = sum(intervals[:i])
        t = 0.0
        display_sequence = []
        for seg in range(interval_count[i]):
            start = pre_length + t
            stop = pre_length + t + interval
            t += epoc_length
            display_sequence.append([start, stop])
        stim.set_display_sequence(display_sequence)


if __name__ == '__main__':
    pass

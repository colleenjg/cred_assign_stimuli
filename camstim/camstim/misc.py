"""
author: derricw
2/4/13

core.py

This is just a set of random helper functions that are used by a lot of other files,
    as well as the default configuration of various components.

"""
import itertools
import logging
import os
import sys
import platform
import ctypes
import ctypes.util
import ConfigParser
import io
import __main__

import numpy
from psychopy import visual, monitors

import camstim

CAMSTIM_DIR = os.path.expanduser('~/camstim/')

DEFAULTCONFIG = """
[Stim]
showmouse = False
miniwindow = False
fps = 60.000
monitor_brightness = 30
monitor_contrast = 50
script = __main__.__file__    # CAN I GET RID OF THIS?

[LIMS]
lims_upload = False
lims_dummy = True

[SweepStim]
backupdir = None
mouseid = 'test'
userid = 'user'
bgcolor = (0,0,0)
controlstream = True
trigger = None
triggerdiport = 0
triggerdiline = 0
trigger_delay_sec = 0.0
savesweeptable = True
eyetracker = False

[Sync]
sync_sqr = False
sync_sqr_loc = (-300,-300)
sync_sqr_freq = 60                    # actually half-period
sync_sqr_size = (100,100)
sync_sqr_color_sequence = [-1,1]
frame_pulse = None                    # (device, port, line) high during each call to window.flip()
acq_on_pulse = None                   # (device, port, line) high while session is running                                     

[Behavior]
nidevice = "Dev1"
mouse_id = "testmouse"
task_id = "dummy_task"
volume_limit = None
lims_upload = False
default_monitor_calibration = 'testMonitor' # if no window is passed

[DetectionOfChange]
abort_on_cycle_end = True            
pre_change_time = 2.0                # mandatory time before stim window
response_window = (0.15, 1.0)        # after change, start/stop of reward availability
stimulus_window = 6.0                # time when change can occur
blank_duration_range = (0.5, 0.5)    # unused right now
initial_blank = 0.0                  # period without stimulus at start of trial
timeout_duration = 0.0               # extra time punishment for early responses
min_no_lick_time = 0.0               # trial doesn't end until mouse hasn't licked for N seconds
safety_timer_padding = 5.0           # if no epochs are active for N seconds, end trial
auto_reward_volume = 0.005
max_task_duration_min = 60.0
warm_up_trials = 3                   # auto rewards for the first N trials
failure_repeats = 10                 # repeats failed trials up to N times
free_reward_trials = 10              # free reward if no licks for N trials
periodic_flash = (0.25, 0.5)         # (on, off)
trial_translator = False             # translates 2.0 trials to 1.0 trials before publishing

[Datastream]
data_export_type = "zro"
data_export = True
data_export_port = 9998
data_export_rep_port = 8888

[Encoder]
nidevice = 'Dev1'
encodervinchannel = 0
encodervsigchannel = 1

[Optogenetics]
optogenetics = False

[Reward]
nidevice = 'Dev1'
reward_lines = [(1, 0)]              # list of (port, line) numbers
rewardlimit = None
reward_volume = 0.008
invert_logic = False

[Licksensing]
nidevice = 'Dev1'
lick_lines = [(0, 0)]                # list of (port, line) numbers

[Eyetracking]

"""



def get_config(section, path='stim.cfg', default="DEFAULTCONFIG"):
    """ Reads the config file for the specified section. """
    # GET DEFAULT PARAMETERS
    params = {}

    try:
        defaults = ConfigParser.RawConfigParser()
        defaults.readfp(io.BytesIO(eval(default)))
        for (k, v) in defaults.items(section):
            params[k] = eval(v)
    except Exception, e:
        logging.warning("Error reading default params for {}: {}".format(section, e))

    # Check for local file, create one if it doesn't exist
    dir_name = os.path.dirname(path)
    if not os.path.isdir(dir_name):
        os.makedirs(dir_name)
    if not os.path.isfile(path):
        with open(path, 'w') as f:
            f.write(DEFAULTCONFIG)

    # MERGE WITH LOCAL FILE
    try:
        localconfig = ConfigParser.RawConfigParser()
        localconfig.read(path)
        for (k, v) in localconfig.items(section):
            params[k] = eval(v)
    except Exception, e:
        logging.warning("Error reading config file {}: {}".format(path, e))

    return params

getConfig = get_config


def set_config(path, section, value):
    """ Sets a config file value. INCOMPLETE and UNUSED """
    parser = ConfigParser.RawConfigParser()

def buildSweepTable(sweep, runs=1, blanksweeps=0):
    """

    Builds an ordered table of every permutation of input dictionary of tuples.
        The format is:
            'name':([possiblevalues],column)

        The possible values are self explanatory.  The column number is what
            column of the table this parameter goes in.

    """
    sweepcount = 1
    dimensions = len(sweep)
    dimarray = []
    dimnames = []

    # Check order
    try:
        unordered = []
        seq = range(dimensions)
        for index, (k, v) in enumerate(sweep.iteritems()):
            if len(v) == 2:
                if v[1] in seq:
                    seq.remove(v[1])
                else:
                    unordered.append(k)
            else:
                unordered.append(k)
        if len(seq) > 0:
            for index, value in enumerate(seq):
                sweep[unordered[index]] = (sweep[unordered[index]][0],
                                           value)
    except Exception, e:
        print "Sweep table order error:", e

    # Create table
    for key, values in sweep.iteritems():
        sweepcount *= len(values[0])  # get number of sweeps

    for d in range(dimensions):
        for k, v in sweep.iteritems():
            if v[1] == d:
                dimarray.append(len(v[0]))  # get ordered dimenstion array
                dimnames.append(k)  # get ordered name array

    dimlist = [sweep[k][0] for k in dimnames]  # get ordered value array
    sweeptable = list(itertools.product(*dimlist))  # get full ordered table
    sweeporder = range(sweepcount)

    # Add blank sweeps
    if blanksweeps is not 0:
        segments = [sweeporder[i:i + blanksweeps]
                    for i in range(0, len(sweeporder), blanksweeps)]
        sweeporder = []
        for x in segments:
            for y in x:
                sweeporder.append(y)  # insert segments
            if len(x) == blanksweeps:
                sweeporder.append(-1)  # insert blank sweeps

    return sweeptable, sweeporder * runs, dimnames


def get_monitor_info(monitor):
    """ Creates a dictionary of relevent monitor information. """
    info = {
        'gamma': monitor.getGamma(),
        'gammagrid': monitor.getGammaGrid().tolist(),
        'distancecm': monitor.getDistance(),
        'sizepix': monitor.getSizePix(),
        'widthcm': monitor.getWidth(),
        'calibrationdate': str(monitor.getCalibDate()),
        'name': monitor.name,
    }
    return info

getMonitorInfo = get_monitor_info

def get_git_commit(package):
    """ Gets git commit for specified package if available. """
    cwd = os.getcwd()
    import subprocess
    if isinstance(package, str):
        import importlib
        try:
            i = importlib.import_module(package)
        except ImportError:
            return None
        folder = os.path.dirname(i.__file__)
    else:
        folder = os.path.dirname(package.__file__)
    os.chdir(folder)
    try:
        short_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
    except subprocess.CalledProcessError, WindowsError:
        os.chdir(cwd)
        return None
    except Exception as e:
        print("Couldn't save git commit for uncaught reason: {}".format(e))
        return None
    short_hash = short_hash.strip("\n")
    os.chdir(cwd)
    return short_hash

getGitCommit = get_git_commit

def get_platform_info():
    """ Gets system and version information. """
    from psychopy import __version__ as psychopyVersion
    from pyglet.gl import gl_info
    import pyglet
    import sys
    import platform
    info = {
        "camstim": camstim.__version__,
        "camstim_git_hash": getGitCommit("camstim"),
        "psychopy": psychopyVersion,
        "python": sys.version.split()[0],
        "pyglet": pyglet.version,
        "opengl": gl_info.get_version(),
        "os": (platform.system(), platform.release(), platform.version()),
        "hardware": (platform.processor(), platform.machine())
    }
    return info

getPlatformInfo = get_platform_info

def printHeader():
    pl = getPlatformInfo()
    print "***************************************"
    print "********* CAMSTIM", pl['camstim'], "****************"
    print "***************************************"
    print "Psychopy version:", pl['psychopy']
    print "Python version:", pl['python']
    print "Pyglet version:", pl['pyglet']
    print "OpenGL version", pl['opengl']
    print "Platform:", pl['os']
    print "System Info:", pl['hardware']
    print "camstim git commit hash:", pl['camstim_git_hash']
    cwd = os.getcwd()
    print "Current working directory:", cwd


def getSweepFrames(sweeporder, sweeptime, preexpsec, postexpsec, postsweepsec, fps):
    """ Gets the sweep frame (start,stop) list in frame domain """
    sweepframelist = []
    frame = int(preexpsec * fps)
    for i in range(len(sweeporder)):
        frames = (frame, frame + int(fps * sweeptime) - 1)
        sweepframelist.append(frames)
        frame = frames[1] + int(fps) * postsweepsec + 1
    return sweepframelist


class prettyfloat(float):
    """ Prettier format for float text output. """
    def __repr__(self):
        return "%0.4f" % self


def setpriority():
    """ Set The Priority of a Process to highest priority. """
    import psutil
    import os
    import sys
    try:
        p = psutil.Process(os.getpid())
        if sys.platform.startswith('linux'):
            p.nice(10)
        else:
            try:
                p.set_nice(psutil.REALTIME_PRIORITY_CLASS)
            except AttributeError:
                p.nice(psutil.REALTIME_PRIORITY_CLASS)
        # print "Set process priority to:",str(psutil.REALTIME_PRIORITY_CLASS)
    except Exception as e:
        logging.exception("Unable to set nice: {}".format(e))


def check_dirs(*args):
    """ Checks to see if any of the directories exist.  Creates them if they don't"""
    import os
    for arg in [x for x in args if x is not None]:
        if not os.path.isdir(arg):
            os.makedirs(arg)
            print("Creating new path: {}".format(arg))

checkDirs = check_dirs  # old


def createConfig(path):
    """ Creates a config file. Applies default config. """
    folder = os.path.dirname(path)
    check_dirs(folder)
    f = open(path, 'w+')
    # write some default variables
    f.write(DEFAULTCONFIG)
    f.close()


def wecanpicklethat(datadict):
    """ Input is a dictionary.
        Attempts to pickle every item.  If it doesn't pickle it is discarded
        and its key is added to the output as "unpickleable"
    """
    import cPickle as pickle
    pickleable = {}
    unpickleable = []
    for k, v in datadict.iteritems():
        try:
            if k[0] != "_":  # we don't want private counters and such
                test = v
                teststring = pickle.dumps(test)
                pickleable[k] = v
        except:
            unpickleable.append(k)
    pickleable['unpickleable'] = unpickleable
    return pickleable


def save_session(mouse_id, dt, data, script="", adjustment={}):
    """ Saves a session to MouseInfo service layer """
    from mouse_info import Session
    session = Session(mouse_id, dt)
    session.session_data = data
    session.script = script
    session.adjustment = adjustment
    session.save()


def cm2deg(cm, monitor):
    """Convert size in cm to size in degrees for a given Monitor object"""
    # check we have a monitor
    if not isinstance(monitor, monitors.Monitor):
        raise ValueError(
            "cm2deg requires a monitors.Monitor object as the second argument but received %s" %
            str(type(monitor)))
    # get monitor dimensions
    dist = 1.0 * monitor.getDistance()
    # check they all exist
    if dist is None:
        raise ValueError(
            "Monitor %s has no known distance (SEE MONITOR CENTER)" %
            monitor.name)
    # return cm/(dist*0.017455)
    return numpy.degrees(numpy.arctan(cm / dist))


def deg2cm(deg, monitor):
    """Convert size in degrees to size in pixels for a given Monitor object"""
    # check we have a monitor
    if not isinstance(monitor, monitors.Monitor):
        raise ValueError(
            "deg2cm requires a monitors.Monitor object as the second argument but received %s" %
            str(type(monitor)))
    # get monitor dimensions
    dist = monitor.getDistance()
    # check they all exist
    if dist is None:
        raise ValueError(
            "Monitor %s has no known distance (SEE MONITOR CENTER)" %
            monitor.name)
    # return degrees*dist*0.017455
    return numpy.tan(numpy.radians(deg)) * dist

# import platform specific C++ libs for controlling gamma (see below)
if sys.platform == 'win32':
    from ctypes import windll
elif sys.platform == 'darwin':
    carbon = ctypes.CDLL('/System/Library/Carbon.framework/Carbon')
elif sys.platform.startswith('linux'):
    # we need XF86VidMode
    xf86vm = ctypes.CDLL(ctypes.util.find_library('Xxf86vm'))


def setGammaRamp(pygletWindow, newRamp, nAttempts=3):
    """
    DW: we replace this psychopy function because it fails in 64-bit python
        about half the time, due to the way that Windows assigns window
        handles.

    Sets the hardware look-up table, using platform-specific ctypes functions.
    For use with pyglet windows only (pygame has its ow routines for this).
    Ramp should be provided as 3x256 or 3x1024 array in range 0:1.0

    On windows the first attempt to set the ramp doesn't always work. The parameter nAttemps
    allows the user to determine how many attempts should be made before failing

    """
    if sys.platform == 'win32':
        newRamp = (255.0 * newRamp).astype(numpy.uint16)
        # necessary, according to pyglet post from Martin Spacek
        newRamp.byteswap(True)
        for n in range(nAttempts):
            success = windll.gdi32.SetDeviceGammaRamp(
                0xFFFFFFFF & pygletWindow._dc,
                newRamp.ctypes)
            if success:
                break
        assert success, 'SetDeviceGammaRamp failed'

    if sys.platform == 'darwin':
        newRamp = (newRamp).astype(numpy.float32)
        LUTlength = newRamp.shape[1]
        error = carbon.CGSetDisplayTransferByTable(
            pygletWindow._screen.id, LUTlength,
                   newRamp[0, :].ctypes, newRamp[1,:].ctypes, newRamp[2,:].ctypes)
        assert not error, 'CGSetDisplayTransferByTable failed'

    if sys.platform.startswith('linux'):
        newRamp = (65535 * newRamp).astype(numpy.uint16)
        success = xf86vm.XF86VidModeSetGammaRamp(
            pygletWindow._x_display, pygletWindow._x_screen_id, 256,
                    newRamp[0, :].ctypes, newRamp[1,:].ctypes, newRamp[2,:].ctypes)
        assert success, 'XF86VidModeSetGammaRamp failed'


def pickle2hdf5(pickle_file):
    """ Safely converts a pickle file to an hdf5 file, prints anything that doesn't convert. """
    import hdf5pickle
    import tables
    import cPickle as pickle
    fname = pickle_file.split(".")[0]
    h5 = tables.openFile(fname + ".h5", 'w')
    pkl = open(pickle_file, 'rb')
    data = pickle.load(pkl)
    for k, v in data.iteritems():
        try:
            hdf5pickle.dump(v, h5, "/" + k)
        except Exception, e:
            print k, v, e

    h5.close()
    pkl.close()


class SyncSquare(visual.GratingStim):

    """
    A small square that can be used to flash black to white at a specified frequency.

    """

    def __init__(self, window, tex=None, size=(100, 100), pos=(-300, -300),
                 frequency=1, colorSequence=[-1, 1]):
        visual.GratingStim.__init__(self, win=window, tex=None,
                                    size=size, pos=pos, color=colorSequence[0],
                                    units='pix')  # old style class
        # this is actually 1/2 period in frames (180Hz use 180)
        self.frequency = frequency
        self.colorSequence = colorSequence
        self.seq_length = len(self.colorSequence)
        self.index = 0

    def flip(self, vsync=1):
        if vsync % self.frequency == 0:
            self.setColor(self.colorSequence[self.index])
            self.index += 1
            if self.index >= self.seq_length:
                self.index = 0
        self.draw()

    def state(self):
        return self.colorSequence[self.index-1] #must use last index because it is incremented right after color is set in flip method

# jaybo
from psychopy import visual
import pyglet
GL = pyglet.gl
import numpy as np


class ImageStimNumpyuByte(visual.ImageStim):

    '''Subclass of ImageStim which allows fast updates of numpy ubyte images,
       bypassing all internal PsychoPy format conversions.
    '''

    def __init__(self,
                 win,
                 image=None,
                 mask=None,
                 units="",
                 pos=(0.0, 0.0),
                 size=None,
                 ori=0.0,
                 color=(1.0, 1.0, 1.0),
                 colorSpace='rgb',
                 contrast=1.0,
                 opacity=1.0,
                 depth=0,
                 interpolate=False,
                 flipHoriz=False,
                 flipVert=False,
                 texRes=128,
                 name='',
                 autoLog=True,
                 maskParams=None):

        if image is None or type(image) != numpy.ndarray or len(image.shape) != 2:
            raise ValueError(
                'ImageStimNumpyuByte must be numpy.ubyte ndarray (0-255)')

        self.interpolate = interpolate

        # convert incoming Uint to RGB trio only during initialization to keep PsychoPy happy
        # else, error is: ERROR   numpy arrays used as textures should be in
        # the range -1(black):1(white)

        data = numpy.zeros((image.shape[0], image.shape[1], 3), numpy.float32)
        # (0 to 255) -> (-1 to +1)
        fimage = image.astype(numpy.float32) / 255 * 2.0 - 1.0
        k = fimage[0, 0] / 255
        data[:, :, 0] = fimage#R
        data[:, :, 1] = fimage#G
        data[:, :, 2] = fimage#B

        visual.ImageStim.__init__(self,
                                  win,
                                  image=data,
                                  mask=mask,
                                  units=units,
                                  pos=pos,
                                  size=size,
                                  ori=ori,
                                  color=color,
                                  colorSpace=colorSpace,
                                  contrast=contrast,
                                  opacity=opacity,
                                  depth=depth,
                                  interpolate=interpolate,
                                  flipHoriz=flipHoriz,
                                  flipVert=flipVert,
                                  texRes=texRes,
                                  name=name, autoLog=autoLog,
                                  maskParams=maskParams)

        self.setImage = self.setReplaceImage
        self.setImage(image)

    def setReplaceImage(self, tex):
        '''
        Use this function instead of 'setImage' to bypass format conversions
        and increase movie playback rates.
        '''
        #intensity = tex.astype(numpy.ubyte)
        intensity = tex
        internalFormat = GL.GL_LUMINANCE
        pixFormat = GL.GL_LUMINANCE
        dataType = GL.GL_UNSIGNED_BYTE
        # data = numpy.ones((intensity.shape[0],intensity.shape[1],3),numpy.ubyte)#initialise data array as a float
        # data[:,:,0] = intensity#R
        # data[:,:,1] = intensity#G
        # data[:,:,2] = intensity#B
        data = intensity
        texture = tex.ctypes  # serialise
        try:
            tid = self._texID  # psychopy renamed this at some point.
        except AttributeError:
            tid = self.texID
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tid)
        # makes the texture map wrap (this is actually default anyway)
        if self.interpolate:
            interpolation = GL.GL_LINEAR
        else:
            interpolation = GL.GL_NEAREST
        GL.glTexParameteri(GL.GL_TEXTURE_2D,
                           GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,
                           GL.GL_TEXTURE_MAG_FILTER, interpolation)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,
                           GL.GL_TEXTURE_MIN_FILTER, interpolation)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, internalFormat,
                        # [JRG] for non-square, want data.shape[1], data.shape[0]
                        data.shape[1], data.shape[0], 0,
                        pixFormat, dataType, texture)
        pass

if __name__ == "__main__":
    pass

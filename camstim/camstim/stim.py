"""

@author:derricw

DW: THIS IS OLD AND IN THE PROCESS OF BEING REMOVED.

#------------------------------------------------------------------------------
Stim.py
#------------------------------------------------------------------------------

Base stim class.  Contains common stimulus functions and classes.

All other stimulus types should inherit this.

TODO: Completely rethink this.  Should some of it be inside sweepstim?  Should
    some of sweepstim be inside here?  This is super old legacy shit why
    haven't I removed it?'

"""

from psychopy import event,visual,misc,gamma
from misc import *
import time
import numpy
import copy
import sys
import io
import logging
import json

#Overwrite a psychopy gamma function without own to avoid 64-bit pyglet window handle issue
#https://code.google.com/p/pyglet/issues/detail?id=664
gamma.setGammaRamp = setGammaRamp


class Stim(object):
    """
    Base class for all Stimuli.
    """

    def __init__(self,
                 window,
                 params={}):

        #check for config file
        self.config_path = os.path.join(CAMSTIM_DIR, "config/stim.cfg")
        if not os.path.exists(self.config_path):
            createConfig(self.config_path)

        self.window = window

        self._get_params(params)

        #GET ATTRIBUTES FROM CONFIG, OVERRIDE WITH SCRIPT
        self._readconfig('Stim', override=self.params)

        printHeader()

        #MONITOR INFO
        setpriority() #from core
        self.wwidth = self.window.size[0]
        self.wheight = self.window.size[1]
        self.monitor = self.window.monitor

        #TURN OFF MOUSE? CONFIG SETTING
        if not self.showmouse:
            self.window.winHandle.set_exclusive_mouse()
            self.window.winHandle.set_exclusive_keyboard()
            self.window.winHandle.set_mouse_visible(False)
            #Prevent mouse from appearing in middle of screen until moved.
            try:
                if sys.platform.startswith('linux'):
                    from Xlib import X, display
                    d = display.Display()
                    s = d.screen()
                    root = s.root
                    root.warp_pointer(0, 0)
                    d.sync()
                elif sys.platform.startswith('darwin'):
                    #Mac stuff here
                    pass
                else:
                    import win32api
                    win32api.SetCursorPos((self.wwidth, self.wheight))
            except:
                pass  # Mac?

        # SET MONITOR BRIGHTNESS/CONTRAST
        self._setup_brightness()

        # VSYNC COUNTER
        self.vsynccount = 0

        # STIMULI?
        self.stimuli = []

    def _get_params(self, params):
        """
        Copys script kwargs and checks if json data is to be used.
        """
        self.params = copy.deepcopy(params)
        if len(sys.argv) > 1:
            clarg = sys.argv[1]
            if clarg.endswith(".json"):
                logging.info("Loading parameter file: {}".format(clarg))
                try:
                    with open(clarg, "r") as f:
                        data = json.load(f)
                except IOError as e:
                    logging.warning("Couldn't read parameter file: {}".format(e))
                    return
                if isinstance(data, dict):
                    self.params.update(data)
                    print(data)
                else:
                    logging.warning("Parameter file did not contain dict.")
            else:
                logging.warning("Paramter file not a .json file.")

    def _readconfig(self, section, override={}):
        """
        Reads the config file for the specified section.
        """
        config = getConfig(section, self.config_path)
        print("Loaded config file @: {}".format(self.config_path))
        config.update(override)
        ## TODO: shouldn't set these as attributes
        for k, v in config.iteritems():
            setattr(self, k.lower(), v)

    def printFrameInfo(self):
        """ Prints data about frame times """
        intervalsMS = numpy.array(self.window.frameIntervals)*1000
        self.intervalsms = intervalsMS
        m = numpy.mean(intervalsMS)
        sd = numpy.std(intervalsMS)
        distString = "Mean=%.1fms,   s.d.=%.1f,   99%%CI=%.1f-%.1f" % (m,
            sd, m-3*sd, m+3*sd)
        nTotal = len(intervalsMS)
        nDropped = sum(intervalsMS > (1.5*m))
        self.droppedframes = ([x for x in intervalsMS if x > (1.5*m)],
            [x for x in range(len(intervalsMS)) if intervalsMS[x] > (1.5*m)])
        droppedString = "Dropped/Frames = %i/%i = %.3f%%" %(nDropped,
            nTotal, nDropped/float(nTotal+0.0000001)*100)  # avoid /0
        logging.info("Actual vsyncs displayed: {}".format(self.vsynccount))
        logging.info("Frame interval statistics: {}".format(distString))
        logging.info("Drop statistics: {}".format(droppedString))

    def _setup_brightness(self):
        """
        Sets the brightness and contrast on windows platforms.
        """
        if sys.platform.startswith("win"):
            # we only have a brightness setting solution for windows.
            try:
                from gamma.winmonitor import WinMonitor
                screen_index = self.window.screen
                monitor = WinMonitor(screen_index)
                monitor.brightness = self.monitor_brightness
                print("Brightness for screen {} set to {}".format(screen_index,
                    self.monitor_brightness))
                monitor.contrast = self.monitor_contrast
                print("Contrast for screen {} set to {}".format(screen_index,
                    self.monitor_contrast))
            except Exception as e:
                import traceback; traceback.print_exc()
                logging.warning("Failed to set brightness/contrast on screen")


if __name__ == '__main__':
    pass
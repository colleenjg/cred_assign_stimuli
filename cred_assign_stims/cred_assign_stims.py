# -*- coding: utf-8 -*-
"""
Created on Tue Apr 24 03:35:50 2018

@author: lyra7
"""
import logging
import os
import time

from PIL import ImageChops
from psychopy import logging as logging_psychopy
from psychopy import event, core
from psychopy.visual import ElementArrayStim
from psychopy.tools.arraytools import val2array
from psychopy.tools.attributetools import attributeSetter, setAttribute

import numpy as np

from camstim import SweepStim

def unique_directory(main_path):
    # creates a unique directory and returns path
    dirname = os.path.dirname(main_path)
    origname = dirname
    i = 1
    while os.path.exists(dirname):
        dirname = "{}_{}".format(origname, i)
        i += 1
    os.makedirs(dirname)
    main_path = main_path.replace(origname, dirname)

    return main_path, dirname

def file_append_attempt(file_path, append_text, max_attempts=4):
    # allows several file append attempts if they fail due to a permission 
    # denied error.

    attempts = 0
    while True:
        try:
            with open(file_path, "a") as f:
                f.write(append_text)
            break
        except Exception as err:
            attempts += 1
            if not "Permission denied" in str(err) or attempts == max_attempts:
                raise(err)
            logging.warning("Failed to write to 'frame_list.txt'. Trying again.")
            time.sleep(1) # wait a second
    return

def frame_log_freq(n_total):
    # calculate frequency at which to log frame number reached.

    order = np.floor(np.log10(n_total)) - 1
    order = int(np.max([1, order]))
    freq = 10 ** order

    return freq



class SweepStimModif(SweepStim):
    def __init__(self, frames_output=False, save_from_frame=0, name="", warp=False, 
                 set_brightness=True, **kwargs):
        """
        Modified camstim sweep stimulus allowing frames to be saved in an on-going way, 
        instead of accumulating in memory.
        """

        self._set_brightness = set_brightness

        super(SweepStimModif, self).__init__(**kwargs)

        self.warp = warp
        self.name = name
        self.frames_output = frames_output
        if self.movie_output and self.frames_output:
            raise ValueError("Do not set both self.frames_output and self.movie_output.")

        # set the frame path to a unique directory
        self._skip_flip = False
        if self.frames_output:
            self.save_from_frame = save_from_frame
            self._skip_flip = True
            self._save_buffer = "back"
            self.frames_output, frames_dirname = unique_directory(self.frames_output)
            self.frames_path, self.frames_ext = os.path.splitext(self.frames_output)
            self.frames_list = os.path.join(frames_dirname, "frame_list.txt")
            logging.info("Saving frames to {}.".format(frames_dirname))

            if self.warp:
                self._save_buffer = "front"
                self._skip_flip = False

            if self.save_from_frame < 0:
                raise ValueError("self.save_from_frame cannot be negative.")


    def save_frame(self, frame, warn_final=False):
        """
        Saves new frames, and list of saved frames needed to recreate the movie.
        Saves only as of self.save_from_frame frame (default: 0)
        """

        # initialize default attributes
        if not hasattr(self, "_save_defaults_set"):
            self._prev_blank = False
            self._local_frame_name = None
            self._save_frame = False
            self._log_freq = frame_log_freq(self.total_frames)
            self._save_defaults_set = True
            # if front buffer is being used (only way to get warped stim), 
            # must record frame on the next pass
            self._shift_save = (self._save_buffer == "front")

        if not os.path.exists(self.frames_list):
            with open(self.frames_list, "w") as f:
                f.write("# {} frame list".format(self.name))

        if frame % self._log_freq == 0:
            logging.info("At frame {}...".format(frame))

        self._save_next = self._save_frame
        self._save_frame = False

        # check whether current frame (i.e., the one in the back buffer) must be saved
        too_early = frame < self.save_from_frame
        if not too_early:
            first_frame = (frame == self.save_from_frame) # first frame 
            still_blank = (self.window._is_blank and self._prev_blank) # no change blank
            same_stim = not (self.window._is_blank or self.window._stim_has_changed) # no change stim
            self._save_frame =  first_frame or not (still_blank or same_stim)

        # whether to record frame currently in the buffer being used
        save_frame = ((self._save_frame * (not self._shift_save)) or 
            (self._save_next * self._shift_save))
        
        # save frame in buffer being used
        if save_frame:
            if warn_final:
                # this will only occur when the stimulus is warped and the final frame 
                # is a new frame (very rarely)
                logging.warning("Final warped frame image cannot be retrieved "
                    "from the front buffer. The final frame image recorded will be a "
                    "duplicate of the preceeding frame.")

            self.window.getMovieFrame(buffer=self._save_buffer)
            frame_name = "{}{}{}".format(
                self.frames_path, frame - self._shift_save, self.frames_ext)
            self.window.saveMovieFrames(frame_name, fps=self.fps)
            self._local_frame_name = os.path.split(frame_name)[1]
        
        # record frame name (only once at least one frame image has been saved)
        if self._local_frame_name is not None:
            append_text = "\nfile '{}'".format(self._local_frame_name)
            file_append_attempt(self.frames_list, append_text, max_attempts=4)

        # record for later
        self._prev_blank = self.window._is_blank
            

    def run(self):
        """
        Same as self.super.run(), except saving frames included, and 
        clearing buffer if flips are skipped.
        """
        self._setup_run()
        
        if self._skip_flip:
            logging.warning("Frames will not appear in the window. They are only saved.")

        if self.warp and self.frames_output:
            logging.warning("Frames will appear in the window, as warped stimuli cannot "
                "be saved otherwise. Note that this is slower than saving unwarped stimuli.")

        # experiment
        self._prev_blank = False
        frame = -1 # in case of no frames
        for frame in range(self.total_frames):
            self.window._is_blank = True # default assumption
            self.update(frame)
            if self.frames_output:
                self.save_frame(frame)
            if self._skip_flip:
                self.window.clearBuffer()

        self._takedown_run(frame)


    def update(self, frame):
        """
        Same as self.super._blank_period(), except skips flips 
        if required (e.g., saving frames).
        """
        self._update_stimuli(frame)
        self._update_items(frame)
        if not self._skip_flip:
            self.flip()
        self.vsynccount += 1
        self._check_keys()


    def _blank_period(self, frame):
        """
        Same as self.super._blank_period(), except skips flips 
        if required (e.g., saving frames).
        """
        self._update_items(frame)
        if not self._skip_flip:
            self.flip()
        self.vsynccount += 1
        self._check_keys()


    def printFrameInfo(self):
        """
        Skips collecting and printing frame information if not 
        displaying images.
        """

        if self._skip_flip:
            logging.info(
                "Frame interval statistic not calculated as frames were "
                "not displayed.")
            self.intervalsms = None
            self.droppedframes = None
        else:
            super(SweepStimModif, self).printFrameInfo()


    def _takedown_run(self, last_frame=-1):
        """
        Same as self.super._takedown_run(), except saves frames 
        and clears buffer if flips are skipped.
        """
        # post blank

        self.window._is_blank = True
        frame = -1
        for frame in range((int(self.post_blank_sec * self.fps))):
            self._blank_period(frame)
            if self.frames_output:
                self.save_frame(frame + last_frame + 1) 
            if self._skip_flip:
                self.window.clearBuffer()
        
        if self.frames_output and (self._save_buffer == "front"):
            warn_final = True if frame == -1 else False
            self.save_frame(frame + last_frame + 2, warn_final=True)

        self._finalize()


    def _setup_brightness(self):
        """
        Same as self.super._setup_brightness(), but allows brightness 
        and contrast setting to be skipped.
        """

        if self._set_brightness:
            super(SweepStimModif, self)._setup_brightness()
        else:
            logging.warning("Not setting screen brightness or contrast.")


class CredAssignStims(ElementArrayStim):
    """
    Stimulus class for Credit Assignment project Gabors and Bricks stimuli.
    """

    def __init__(self,
                 win,
                 elemParams,
                 fieldSize, # [wid, hei]
                 direc=0.0, # only supports a single value (including "right" or "left"). Use speed to flip direction of some elements.
                 speed=0.0, # units are sort of arbitrary for now
                 sizeparams=None, # range from which to sample uniformly [min, max]. Height and width sampled separately from same range.
                 possizes=None, # zipped lists of pos and sizes (each same size as nStims) for A, B, C, D, U
                 cyc=None, # number of cycles visible (for Gabors)
                 newpos=[], # frames at which to reinitialize stimulus positions
                 newori=[0], # frames at which to change stimulus orientations (always include 0)
                 orimus=[0.0], # parameter (mu) to use when setting/changing stimulus orientations in deg
                 orikappa=None, # dispersion for sampling orientations (radians)
                 flipdirec=[], # intervals during which to flip direction [start, end (optional)]S
                 flipfrac=0.0, # fraction of elements that should be flipped (0 to 1)
                 duration=-1, # duration in seconds (-1 for no end)
                 currval=None, # pass some values for the first initialization (from fliparray)
                 initScr=True, # initialize elements on the screen
                 rng=None,
                 fps=60, # frames per second
                 autoLog=None):
    
            self._initParams = __builtins__["dir"]()
            self._initParams.remove("self")
            
            super(CredAssignStims, self).__init__(win, autoLog=False, **elemParams) # set autoLog at end of init
            
            self._printed = False # useful for printing things once     
            self._stim_updated = True # used to initiate any new draws
            
            self.elemParams = elemParams
            
            self.setFieldSize(fieldSize)
            self.init_wid = fieldSize[0] * 1.1 # add a little buffer
            self.init_hei = fieldSize[1] * 1.1 # add a little buffer
            
            self.possizes = possizes

            self._sizeparams = sizeparams
            if self._sizeparams is not None:
                self._sizeparams = val2array(sizeparams) # if single value, returns it twice
                self._initSizes(self.nElements)
                
            self._cyc = cyc
            
            if "sfs" in self.elemParams:
                self.sf = self.elemParams["sfs"]
            else:
                self.sf = None
            
            self.setDirec(direc)
            self._stimOriginVar()
            if len(newpos) != 0: # get frames from sec
                newpos = [x * float(fps) for x in newpos]
            self._newpos = newpos
            
            self._flip=0
            if currval is not None:
                self._flip=currval
            self.defaultspeed = speed
            self._speed = np.ones(self.nElements)*speed
            self._flipdirec = flipdirec
            self._randel = None
            self.rng = rng
            self.flipfrac = float(flipfrac)
            self.flipstart = list()
            self.flipend = list()
            if len(self._flipdirec) != 0: # get frames from sec
                self._flipdirec = [[y * float(fps) for y in x] for x in self._flipdirec]
                self._initFlipDirec()
            
            self._newori = [x * float(fps) for x in newori] # get frames from sec
            self._orimus = orimus
            self._orimu = self._orimus[0]
            self._orikappa = orikappa
            self._initOriArrays()
            
            self.duration = duration*float(fps)
            self.initScr = initScr
            
            self._countframes = 0
            self.last_frame = list([self._countframes]) # workaround so the final value can be logged
            
            self.starttime = core.getTime()
            
            if self.defaultspeed != 0.0:
                # initialize list to compile pos_x, pos_y by frame (as int16)
                self.posByFrame = list()
            else: # assuming if no speed, that it is gabors!
                # initialize list to compile orientations at every change (as int16)
                self.orisByImg = list()
                
            
            if possizes is None:
                self._newStimsXY(self.nElements) # update self._coords
                # start recording positions
                self.setXYs(self._coords)
            
            else: 
                self.setXYs(possizes[0][0])
                self.setSizes(possizes[0][1])
                self._adjustSF(possizes[0][1])
            
            # set autoLog now that params have been initialised
            self.__dict__["autoLog"] = autoLog or autoLog is None and self.win.autoLog
            if self.autoLog:
                logging_psychopy.exp("Created %s = %s" %(self.name, str(self)))

    def setContrast(self, contrast, operation="", log=None):
        """Usually you can use "stim.attribute = value" syntax instead,
        but use this method if you need to suppress the log message."""
        self.setContrs(contrast, operation, log)
        self._stim_updated = True
    
    def setDirec(self, direc):
        if direc == "left":
            direc = 180
        elif direc == "right":
            direc = 0
        elif direc == "up":
            direc = 90
        elif direc == "down":
            direc = 270
        
        direc = direc%360.0
        if direc < 0:
            direc = 360 - direc
        self._direc = direc


    def setFlip(self, fliparray, operation="", log=None):
        """Not used internally, but just to allows direction flips to occur, 
        new sizes and number of elements, and a new direction to be set.
        """
        # check if switching from reg to mismatch or back, and if so initiate
        # speed update
        if self._flip == 1 and fliparray == 0:
            self._flip=0
            self._update_stim_speed(self._flip)
        elif self._flip == 0 and fliparray == 1:
            self._flip=1
            self._update_stim_speed(self._flip)
        
        newInit = False
        # reinitialize
        if newInit is True:
            self.initScr = True
            self._newStimsXY(self.nElements) # updates self._coords
            self.setXYs(self._coords)
            newInit = False
    
    def setOriSurp(self, oriparsurp, operation="", log=None):
        """Not used internally, but just to allow new sets of orientations to 
        be initialized based on a new mu, and set whether the 4th set 
        is a surprise (90 deg shift and U locations and sizes).
        """
        
        self._orimu = oriparsurp[0] # set orientation mu (deg)
        
        # set if surprise set
        self._surp = oriparsurp[1]
        
        # set orientations
        self.setOriParams(operation, log)

        # compile orientations at every sweep (as int16)
        self.orisByImg.extend([np.around(self.oris).astype(np.int16)])
        
        
    def setOriKappa(self, ori_kappa, operation="", log=None):
        """Not used internally, but just to allow new sets of orientations to 
        be initialized based on a new mu.
        """
        # update current kappa
        self._orikappa = ori_kappa
        
        # set orientations
        self.setOriParams(operation, log)
    
    def setOriParams(self, operation="", log=None):
        """Initialize new sets of orientations based on parameters using sweeps.
        No need to pass anything as long as self._orimu and self._orikappa are up to date.
        """
        if self._orikappa is None: # no dispersion
            ori_array = self._orimu
        else:
            if self.rng is not None:
                ori_array_rad = self.rng.vonmises(np.deg2rad(self._orimu), self._orikappa, self.nElements)
            else:
                ori_array_rad = np.random.vonmises(np.deg2rad(self._orimu), self._orikappa, self.nElements)
            ori_array = np.rad2deg(ori_array_rad)
        
        self.setOris(ori_array, operation, log)
        self._stim_updated = True
    
    def setSizesAll(self, sizes, operation="", log=None):
        """Set new sizes.
        Pass list (same size as nStims)
        """
        
        self.setSizes(sizes, operation, log)
        self._adjustSF(sizes)
        self._stim_updated = True
    
    def _adjustSF(self, sizes):
        # update spatial frequency to fit with set nbr of visible cycles
                
        if self._cyc is not None:
            sfs = self._cyc/sizes
            self.setSfs(sfs)
        
        # if units are pixels, assume sf was provided to elementarray as cyc/pix, 
        # update spatial frequency cyc/stim_wid (which is what elementarray expects)
        if self.sf is not None and self.units == "pix":
            sfs = [self.sf * x for x in sizes]
            self.setSfs(sfs)
            
            
    def setSizeParams(self, size_params, operation="", log=None):
        """Allows Sweeps to set new sizes based on parameters (same width and height).
        Pass tuple [mu, std (optional)]
        """
        size_params = val2array(size_params) # if single value, returns it twice
        if size_params.size > 2:
            e = "Too many parameters: " + str(size_params.size)
            raise ValueError(e)
        elif size_params[0] == size_params[1]: # originally single value, no range
            sizes = np.ones(self.nElements)*size_params[0]
        elif self._sizeparams.size == 2:
            # sample uniformly from range
            if self.rng is not None:
                sizes = self.rng.uniform(size_params[0], size_params[1], self.nElements)
            else:
                sizes = np.random.uniform(size_params[0], size_params[1], self.nElements)
        
        self.setSizes(sizes, operation, log)
        self._adjustSF(sizes)
        self._stim_updated = True
                
    def setPosAll(self, pos, operation="", log=None):
        """Set new positions.
        Pass list (same size as nStims)
        """
        
        self.setXYs(pos, operation, log)
        self._stim_updated = True
    
    def setPosSizesAll(self, combo, operation="", log=None):
        """Allows Sweeps to set which pos/size combo to use where
        0, 1, 2, 3 = A, B, C, D.
        4 is set manually below (U)
        """
        
        # if it's the D (4th set) of a surprise round, switch orientation mu
        # and switch positions to U
        # note: this is done here because the sweep visits the highest level param last
        if self._surp == 1 and combo == 3:
            pos = self.possizes[4][0]
            sizes = self.possizes[4][1]
            self._orimu = (self._orimu + 90)%360
        
        else:
            pos = self.possizes[combo][0]
            sizes = self.possizes[combo][1]
        
        self.setXYs(pos, operation, log)
        self.setSizes(sizes, operation, log)
        self._adjustSF(sizes)
    
        # resample orientations each time new positions and sizes are set
        self.setOriParams(operation, log)
        self._stim_updated = True
    
    def _stimOriginVar(self):
        """Get variables relevant to determining where to initialize stimuli
        """
        self._dirRad = self._direc*np.pi/180.0
        
        # set values to calculate new stim origins
        quad = int(self._direc/90.0)%4
        if quad == 0:
            self._buffsign = np.array([1, 1])
        elif quad == 1:
            self._buffsign = np.array([-1, 1])
        elif quad == 2:
            self._buffsign = np.array([-1, -1])
        elif quad == 3:
            self._buffsign = np.array([1, -1])
        basedirRad = np.arctan(1.0*self.init_hei/self.init_wid)
        self._buff = (self.init_wid+self.init_hei)/10 # size of initialization area (10 is arbitrary)
        
        if self._direc%90.0 != 0.0:
            self._ratio = self._dirRad%(np.pi/2)/basedirRad
            self._leng = self.init_wid*self._ratio + self.init_hei/self._ratio
        
        
    def _initFlipDirec(self):      
        self.flipstart = list()
        self.flipend = list()
        
        for i, flip in enumerate(self._flipdirec):
            flip = val2array(flip) # if single value, returns it twice
            if flip.size > 2:
                raise ValueError("Too many parameters.")
            else:
                self.flipstart.append(flip[0])
            if flip[0] == flip[1]: # assume last end possible if same value (originally single value)
                if i == len(self._flipdirec) - 1:
                    self.flipend.append(-1)
                else:
                    self.flipend.append(self._flipdirec[i+1][0] - 1)
            else:
                self.flipend.append(flip[1])
        
    def _newStimsXY(self, newStims):
        
        # initialize on screen (e.g., for first initialization)
        if self.initScr:
            if self._speed[0] == 0.0: # initialize on screen
                if self.rng is not None:
                    coords_wid = self.rng.uniform(-self.init_wid/2, self.init_wid/2, newStims)[:, np.newaxis]
                    coords_hei = self.rng.uniform(-self.init_hei/2, self.init_hei/2, newStims)[:, np.newaxis]
                else:
                    coords_wid = np.random.uniform(-self.init_wid/2, self.init_wid/2, newStims)[:, np.newaxis]
                    coords_hei = np.random.uniform(-self.init_hei/2, self.init_hei/2, newStims)[:, np.newaxis]

                self._coords = np.concatenate((coords_wid, coords_hei), axis=1)
                return self._coords
        
            else: # initialize on screen and in buffer areas
                if self._direc % 180.0 == 0.0: # I stim origin case:
                    if self.rng is not None:
                        coords_wid = self.rng.uniform(-self.init_wid/2-self._buff, self.init_wid/2+self._buff, newStims)[:, np.newaxis]
                        coords_hei = self.rng.uniform(-self.init_hei/2, self.init_hei/2, newStims)[:, np.newaxis]
                    else:
                        coords_wid = np.random.uniform(-self.init_wid/2-self._buff, self.init_wid/2+self._buff, newStims)[:, np.newaxis]
                        coords_hei = np.random.uniform(-self.init_hei/2, self.init_hei/2, newStims)[:, np.newaxis]
                elif self._direc % 90.0 == 0.0:
                    if self.rng is not None:
                        coords_wid = self.rng.uniform(-self.init_wid/2, self.init_wid/2, newStims)[:, np.newaxis]
                        coords_hei = self.rng.uniform(-self.init_hei/2-self._buff, self.init_hei/2+self._buff, newStims)[:, np.newaxis]
                    else:
                        coords_wid = np.random.uniform(-self.init_wid/2, self.init_wid/2, newStims)[:, np.newaxis]
                        coords_hei = np.random.uniform(-self.init_hei/2-self._buff, self.init_hei/2+self._buff, newStims)[:, np.newaxis]
                else:
                    if self.rng is not None:
                        coords_wid = self.rng.uniform(-self.init_wid/2-self._buff, self.init_wid/2+self._buff, newStims)[:, np.newaxis]
                        coords_hei = self.rng.uniform(-self.init_hei/2-self._buff, self.init_hei/2+self._buff, newStims)[:, np.newaxis]
                    else:
                        coords_wid = np.random.uniform(-self.init_wid/2-self._buff, self.init_wid/2+self._buff, newStims)[:, np.newaxis]
                        coords_hei = np.random.uniform(-self.init_hei/2-self._buff, self.init_hei/2+self._buff, newStims)[:, np.newaxis]

                self._coords = np.concatenate((coords_wid, coords_hei), axis=1)
                self.initScr = False
                return self._coords
        
        # subsequent initializations from L around window (or I if mult of 90)
        elif self._speed[0] != 0.0:            
            # initialize for buffer area
            if self.rng is not None:
                coords_buff = self.rng.uniform(-self._buff, 0, newStims)[:, np.newaxis]
            else:
                coords_buff = np.random.uniform(-self._buff, 0, newStims)[:, np.newaxis]
            
            if self._direc%180.0 == 0.0: # I stim origin case
                if self.rng is not None:
                    coords_hei = self.rng.uniform(-self.init_hei/2, self.init_hei/2, newStims)[:, np.newaxis]            
                else:
                    coords_hei = np.random.uniform(-self.init_hei/2, self.init_hei/2, newStims)[:, np.newaxis]
                coords = np.concatenate((self._buffsign[0]*(coords_buff - self.init_wid/2), coords_hei), axis=1)
            elif self._direc%90.0 == 0.0: # flat I stim origin case
                if self.rng is not None:
                    coords_wid = self.rng.uniform(-self.init_wid/2, self.init_wid/2, newStims)[:, np.newaxis]
                else:
                    coords_wid = np.random.uniform(-self.init_wid/2, self.init_wid/2, newStims)[:, np.newaxis]
                coords = np.concatenate((coords_wid, self._buffsign[1]*(coords_buff - self.init_hei/2)), axis=1)
            else:
                if self.rng is not None:
                    coords_main = self.rng.uniform(-self._buff, self._leng, newStims)[:, np.newaxis]
                else:
                    coords_main = np.random.uniform(-self._buff, self._leng, newStims)[:, np.newaxis]
                coords = np.concatenate((coords_main, coords_buff), axis=1)
                for i, val in enumerate(coords):
                    if val[0] > self.init_wid*self._ratio: # samples in the height area
                        new_main = val[0] - self.init_wid*self._ratio # for val over wid -> hei
                        coords[i][0] = (val[1] - self.init_wid/2)*self._buffsign[0] 
                        coords[i][1] = new_main*self._ratio - self.init_hei/2
                    elif val[0] < 0.1: # samples in the corner area
                        coords[i][0] = (val[0] - self.init_wid/2)*self._buffsign[0]
                        coords[i][1] = (val[1] - self.init_hei/2)*self._buffsign[1]
                    else: # samples in the width area
                        coords[i][0] = val[0]*self._ratio - self.init_wid/2
                        coords[i][1] = (val[1] - self.init_hei/2)*self._buffsign[1]
            return coords
        
        else:
            raise ValueError("Stimuli have no speed, but are not set to initialize on screen.")
    
    def _update_stim_mov(self):
        """
        The user shouldn"t call this - it gets done within draw()
        """
    
        """Find out of bound stims, update positions, get new positions
        """
        
        dead = np.zeros(self.nElements, dtype=bool)
    
        # stims that have exited the field
        dead = dead+(np.abs(self._coords[:,0]) > (self.init_wid/2 + self._buff))
        dead = dead+(np.abs(self._coords[:,1]) > (self.init_hei/2 + self._buff))

        # if there is speed flipping, update stimulus speeds to be flipped
        if len(self._flipdirec) != 0:
            self._update_stim_speed()
        
        if self._randel is not None and dead[self._randel].any():
            dead = self._revive_flipped_stim(dead)
        
        # update XY based on speed and dir
        self._coords[:self.nElements,0] += self._speed[:self.nElements]*np.cos(self._dirRad)
        self._coords[:self.nElements,1] += self._speed[:self.nElements]*np.sin(self._dirRad)# 0 radians=East!
        
        # update any dead stims
        if dead.any():
            self._coords[dead,:] = self._newStimsXY(sum(dead))
        
        self.setXYs(self._coords)

    def _update_stim_speed(self, signal=None):        
        # flip speed (i.e., direction) if needed
        if signal==1 or self._countframes in self.flipstart:
            if self.rng is not None:
                self._randel = np.where(self.rng.rand(self.nElements) < self.flipfrac)[0]
            else:
                self._randel = np.where(np.random.rand(self.nElements) < self.flipfrac)[0]
            self._speed[self._randel] = -self.defaultspeed
            if self._randel.size == 0: # in case no elements are selected
                self._randel = None
        elif signal==0 or self._countframes in self.flipend:
            if self._randel is not None:
                self._speed[self._randel] = self.defaultspeed
            self._randel = None
    
    def _revive_flipped_stim(self, dead):
        # revive and flip direction on flipped stimuli out of bounds
        self._speed[self._randel[np.where(dead[self._randel])[0]]] = self.defaultspeed
        dead[self._randel]=False
        
        return dead
    
    def _update_stim_ori(self):
        # change orientations
        self.oris = self._oriarrays[self._newori.index(self._countframes)]
    
    def _update_stim_pos(self):
        # get new positions
        self.initScr = True
        self.setXYs(self._newStimsXY(self.nElements))
    
    def _initOriArrays(self):
        """
        Initialize the list of arrays of orientations and set first orientations.
        """
        if len(self._newori) != len(self._orimus):
            raise ValueError("Length of newori must match length of oriparamList.")
        
        self._oriarrays = list()
        for i in self._orimus:
            if self._orikappa is None: # no dispersion
                self._oriarrays.append(np.ones(self.nElements)*i)
            else:
                if self.rng is not None:
                    neworisrad = self.rng.vonmises(np.deg2rad(i), self._orikappa, self.nElements)
                else:
                    neworisrad = np.random.vonmises(np.deg2rad(i), self._orikappa, self.nElements)
                self._oriarrays.append(np.rad2deg(neworisrad))
        
        self.oris = self._oriarrays[0]
        
    def _initSizes(self, nStims):
        """
        Initialize the sizes uniformly from range (height and width same).
        """
          
        if self._sizeparams.size > 2:
            raise ValueError("Too many parameters.")
        elif self._sizeparams[0] == self._sizeparams[1]: # assume last end possible if same value (originally single value)
            sizes = np.ones(nStims)*self._sizeparams[0]
        else:
            # sample uniformly from range
            if self.rng is not None:
                sizes = self.rng.uniform(self._sizeparams[0], self._sizeparams[1], nStims)
            else:
                sizes = np.random.uniform(self._sizeparams[0], self._sizeparams[1], nStims)
        
        self.sizes = sizes
    
    
    def draw(self, win=None):
        """Draw the stimulus in its relevant window. You must call
        this method after every MyWin.flip() if you want the
        stimulus to appear on that frame and then update the screen
        again.

        Also provides info to window object about whether a 
        CredAssignStim is being visualized and whether it has changed.
        (This will be useful for recording frames.)
        """
        
        self.win._is_blank = False

        # update if new positions (newpos)
        if len(self._newpos) > 0 and self._countframes in self._newpos:
            self.win._stim_has_changed = True
            self._update_stim_pos()
            self._stim_updated = True
        
        # update if new orientations (newori)
        if len(self._newori) > 1 and self._countframes in self._newori[1:]:
            self._update_stim_ori()
            self._stim_updated = True
        
        # log current posx, posy (rounded to int16) if stim is moving
        # shape is n_frames x n_elements x 2
        if self.defaultspeed != 0.0:
            self.posByFrame.extend([np.around(self._coords).astype(np.int16)])
            self._stim_updated = True
        
        super(CredAssignStims, self).draw()

        self.win._stim_has_changed = self._stim_updated
        self._stim_updated = False
        
        # count frames
        self.last_frame[0] = [self._countframes]
        self._countframes += 1
        
        
        # update based on speed
        if self.defaultspeed != 0.0:
            self._update_stim_mov()

        
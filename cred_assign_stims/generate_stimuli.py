"""
This is code to generate stimuli of the desired length

For ophys type sessions, unexpected sequences or violations are included. These are 
every 30-90 seconds, and last 2-4 seconds for the visual flow, and 3-6 seconds for the Gabors.
For hab type sessions, no unexpected sequences or violations occur.

Everything is randomized for each session for each animal (ordering of stim 
types (gabors vs visual flow), ordering of visual flow directions (left, right), 
positions, sizes and orientations of Gabors, location of visual flow squares, and time
and duration of unexpected sequences or violations if these occur.
"""

import copy
import logging
import os
import random
import sys
from win32api import GetSystemMetrics

import numpy as np
from psychopy import monitors

from camstim import Window, Warp

import stimulus_params
from cred_assign_stims import SweepStimModif, unique_directory

# Configuration settings used in the Credit Assignment project
WIDTH = 52.0
DISTANCE = 15.0
SIZEPIX = [1920, 1200]

def get_cred_assign_monitor():
    # Monitor sizing specs used in the Credit Assignment project
    monitor = monitors.Monitor("CredAssign")
    monitor.setWidth(WIDTH)
    monitor.setDistance(DISTANCE)
    monitor.setSizePix(SIZEPIX)

    return monitor


def check_reproduce(monitor, fullscreen=False, raise_error=False):
    
    orig_widpix, orig_heipix = SIZEPIX
    orig_wid = WIDTH
    orig_dist = DISTANCE

    curr_widpix, curr_heipix = monitor.getSizePix()
    fsc_str = ""
    if fullscreen:
        curr_widpix, curr_heipix = [GetSystemMetrics(i) for i in [0, 1]]
        fsc_str = " (fullscreen)"
    curr_wid = monitor.getWidth()
    curr_dist = monitor.getDistance()

    names = ["width (pix)", "height (pix)", "width (cm)", "distance (cm)"]
    values = [(orig_widpix, curr_widpix), (orig_heipix, curr_heipix), 
        (orig_wid, curr_wid), (orig_dist, curr_dist)]

    accumulate_names = []
    for name, (orig, curr) in zip(names, values):
        if orig != curr:
            accumulate_names.append(name)

    if len(accumulate_names) != 0:
        verb = "does" if len(accumulate_names) == 1 else "do"
        msg = ("Current {}{} {} not match original used in experiment. "
            "Seeds will not allow exact Credit Assignment stimulus parameter "
            "reproduction.").format(", ".join(accumulate_names), fsc_str, verb)
        if raise_error:
            raise ValueError(msg)
        else:
            logging.warning(msg)


def generate_stimuli(session_params, seed=None, save_frames="", save_directory=".", 
                     monitor=None, fullscreen=False, warp=False, save_from_frame=0):
    """
    generate_stimuli(session_params)

    Required args:
        - session_params (dict): see run_generate_stimuli.SESSION_PARAMS_OPHYS for 
                                 required keys and description.
    
    Optional args:
        - seed (int)           : seed to use to initialize Random Number Generator. 
                                 If None, will be set randomly.
                                 default: None
        - save_frames (str)    : extension to use for saving frames (frames not saved 
                                 if "")
                                 default: ""
        - save_directory (str) : main directory in which to save frames
                                 default: "."
        - monitor (Monitor)    : Psychopy Monitor. If None, a default test Monitor is 
                                 initialized instead.
                                 default: None
        - fullscreen (bool)    : If True, overrides monitor size
                                 default: False
        - warp (bool)          : If True, image is warped
                                 default: False
        - save_from_frame (int): Frame as of which to start saving frames, if saving
                                 default: 0
    """

    # Record orientations of gabors at each sweep (LEAVE AS TRUE)
    recordOris = True

    # Record positions of squares at all times (LEAVE AS TRUE)
    recordPos = True
            
    # create a monitor
    if monitor is None:
        get_cred_assign_monitor()
    
    check_reproduce(monitor, fullscreen=fullscreen, raise_error=False)

    if seed is None:
            # randomly set a seed for the session
        session_params["seed"] = random.randint(1, 10000)
    else:
        session_params["seed"] = seed
    logging.info("Seed: {}".format(session_params["seed"]))
    session_params["rng"] = np.random.RandomState(session_params["seed"])

    # check session params add up to correct total time
    tot_calc = session_params["pre_blank"] + session_params["post_blank"] + \
               2 * session_params["inter_blank"] + session_params["gab_dur"] + \
               2 * session_params["sq_dur"]
    if tot_calc != session_params["session_dur"]:
        logging.warning("Session expected to add up to {} s, but adds up to {} s."
              .format(session_params["session_dur"], tot_calc))

    # Create display window
    window_kwargs = {
        "fullscr": fullscreen,
        "size"   : monitor.getSizePix(), # May return an error due to size. Ignore.
        "monitor": monitor, # Will be set to a gamma calibrated profile by MPE
        "screen" : 0,
    }
    if warp:
        window_kwargs["warp"] = Warp.Spherical
    
    window = Window(**window_kwargs)
   
    # initialize the stimuli
    gb = stimulus_params.init_gabors(window, session_params.copy(), recordOris)
    sq_left = stimulus_params.init_squares(window, "left", session_params.copy(), recordPos)
    sq_right = stimulus_params.init_squares(window, "right", session_params.copy(), recordPos)

    # initialize display order and times
    stim_order = ["g", "b"]
    session_params["rng"].shuffle(stim_order) # in place shuffling
    sq_order = ["l", "r"]
    session_params["rng"].shuffle(sq_order) # in place shuffling

    start = session_params["pre_blank"] # initial blank
    stimuli = []
    for i in stim_order:
        if i == "g":
            stimuli.append(gb)
            gb.set_display_sequence([(start, start + session_params["gab_dur"])])
            # update the new starting point for the next stim
            start += session_params["gab_dur"] + session_params["inter_blank"] 
        elif i == "b":
            for j in sq_order:
                if j == "l":
                    stimuli.append(sq_left)
                    sq_left.set_display_sequence([(start, start+session_params["sq_dur"])])
                elif j == "r":
                    stimuli.append(sq_right)
                    sq_right.set_display_sequence([(start, start+session_params["sq_dur"])])
                # update the new starting point for the next stim
                start += session_params["sq_dur"] + session_params["inter_blank"] 

    # prepare path for file saving
    frames_path = ""
    if save_frames:
        frames_directory = os.path.join(
            save_directory, "frames_{}".format(str(session_params["seed"])))
        frames_path = os.path.join(frames_directory, "frame_.{}".format(save_frames))

    ss = SweepStimModif(
        window=window,
        stimuli=stimuli,
        post_blank_sec=session_params["post_blank"],
        params={},  # will be set by MPE to work on the rig
        frames_output=frames_path,
        save_from_frame=save_from_frame,
        name=session_params["seed"],
        warp=warp,
        set_brightness=False # skip setting brightness
        )

    # catch system exit 0 thrown by ss._finalize()
    try:
        ss.run()
    except SystemExit as cm:
        if cm.code != 0:
            sys.exit(cm.code)
        logging.warning("Ignoring automatic post-sweep system exit.")



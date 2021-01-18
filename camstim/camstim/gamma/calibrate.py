# -*- coding: utf-8 -*-
"""! @file  calibrate.py

   @brief Script to do calibration of visual stimulus monitors.

   @author  Perry Hargrave, Jay Borseth, Derric Williams
   @copyright Allen Institute for Brain Science

This works to adjust gamma and luminance so the response of the monitor is
roughly a straight line with an output of ~50 cd/m^2 when a default, gray
psychopy window is shown on-screen.
"""
from __future__ import print_function 
# FIXME: deprecate this someday.
from GammaWindow import GammaWindow

import ctypes
import psychopy
from psychopy import visual, logging
import psychopy.hardware.crs.colorcal
import psychopy.monitors.calibTools
import numpy as np
import pyglet
import seabreeze.spectrometers as sb
import sys
import win32api
import util
import datetime

from winmonitor import WinMonitor

def get_spectrometer(index=0, integration_mult=5):
    """Tries to open the spectrometer at index.

    integration_mult: Use this to multiply by the spectrometers *minimum*
                      integration time. For the USB-FLAME it seems around five
                      gives a nice smooth curve/line for gamma calibration. [5]
    """
    try:
        dev = sb.list_devices()[index]
        spec = sb.Spectrometer(dev)

    except IndexError:
        raise IndexError("Gee Bob, looks like there's no spectrometer here.")

    except sb.SeaBreezeError as e:
        # Seabreeze 'e.error_code' are all empty, so handle known problems with
        # good conditionals or match e.message (yuk)
        from seabreeze.backends import get_backend
        sb_lib = get_backend()

        if sb_lib.device_is_open(dev):
            wopen = "Spec at {0} already open, trying to close/open"
            logging.warn(wopen.format(dev))
            sb_lib.device_close(dev)
            spec = sb.Spectrometer(sb.list_devices()[index])
        else:
            raise e

    integration_time = spec.minimum_integration_time_micros * integration_mult
    spec.integration_time_micros(integration_time)
    return spec

def get_colorcal(ports=range(0,10)):
    """Find the colorcal using psychopy's hardware method.

    This isn't very elegant and is nearly impossible to do anything with, so I
    keep it separate from the luminance adjustment.
    """
    cc = psychopy.hardware.findPhotometer(device='ColorCAL', ports=ports)
    if cc == None:
        raise AttributeError("No ColorCAL to use. Maybe specify the port?")
    print('Opened ColorCal: ' + cc.longName + ' on port: ' + cc.portString)
    print('ColorCal needs zero calibration: ' + str(cc.getNeedsCalibrateZero()))
    return cc


def gamma(screen=0, target_candela=50, squelch = False):
    """Runs gamma calibration on monitor.
    screen : Index of monitor to use, indexed from 0, same as psychopy
    target_candela : lum target required for saving calibration file name

    returns the name of the gamma corrected monitor (with brightness setting appended to the name, eg. "GammaCorrect43"
    
    DW: We need to re-write GammaWindow.
    """
    spec = get_spectrometer(integration_mult=100)
    savepath = util.make_folders()
    if not squelch:
        print("Config will be saved to: {}".format(psychopy.monitors.calibTools.monitorFolder))
    
    win_monitor = WinMonitor(screen)
    
    gw = GammaWindow(spec=spec,
                     savepath=savepath,
                     brightness=win_monitor.brightness,
                     screen=screen,
                     target_candela=target_candela)
    monitor_type = gw.monitorcal()
    spec.close()
    del spec
    return monitor_type    

def get_system_hardware_info():
    """
    DW: why have a function that doesn't return or print anything and just logs?
    """
    # Pyglet's version of screens
    allScreens = pyglet.window.get_platform().get_default_display().get_screens()
    print('pyglet.window.get_platform().get_default_display().get_screens(): ' + str(allScreens))

    # What are the available monitor calibrations in PsychoPy?
    monitors = psychopy.monitors.getAllMonitors()
    print('psychopy.monitors.getAllMonitors(): '+ str(monitors))

    # What are the available spectrophotometers?
    devices = sb.list_devices()
    print('Spectrophotometers: ' + str(devices))

    # is ColorCal available?
    cc = get_colorcal()
    if cc:
        print('ColorCal: ' + str(cc.getInfo()))
        cc.com.close()
    else:
        print('ColorCal: not found')

def get_luminance(psychopy_monitor,
                  colorcal,                  
                  screen=0,
                  color=(0.0, 0.0, 0.0)):
    """
    Gets the luminance of a psychopy monitor calibration using a ColorCal
        @ a specified color.

    Args:
        psychopy_monitor (str): a psychopy monitor calibration name
        colorcal (psychopy.hardware.crs.ColorCal): a ColorCal
        screen (int): screen to draw to
        color (tuple): color to draw (grey is (0,0,0))

    Returns:
        float: luminance in cd/m^3

    """
    #print(psychopy_monitor, colorcal, screen, color)
    lum_window = visual.Window(fullscr=True,
                               screen=screen,
                               monitor=psychopy_monitor,
                               color=color)
    for i in range(5):
        lum_window.flip()
    lum = colorcal.getLum()
    lum_window.close()
    
    return lum

def step_luminance(colorcal, step_size = 10, lum_target=50.0, screen = 0):
    mon = WinMonitor(screen)
    print('min brightness:', mon.brightness_min)
    print('max brightness:', mon.brightness_max)

    init_brightness = mon.brightness
    init_contrast = mon.contrast
    optimal_brightness = None

    # Should require at most 8 iterations regardless of tolerance.
    print('Timestamp, {}'.format(datetime.datetime.now()))
    print('Luminance Target, {}'.format(lum_target))
    print('Step size, {}'.format(step_size))
    print('Luminance, Brightness')
    monitor_cal = 'Gamma1.Luminance50'
    luminances = []
    mon.contrast = 50
    #gamma(screen=screen, target_candela=lum_target, squelch=True)
    for step in range(0, 110, step_size):
        print (step, end=',')
        mon.brightness = step       
        luminances.append(get_luminance(monitor_cal, colorcal, screen=screen))
        #print("{}, {}".format(step, lum))
    print('')
    for lum in luminances:
        print(lum, end=',')
    print('')
    mon.brightness = init_brightness
    mon.contrast = init_contrast
    return optimal_brightness


def luminance_search(colorcal,
                     lum_target=50.0,
                     lum_tolerance=2.0,
                     color_target=(0.0,0.0,0.0),
                     screen=0,):
    """
    Searches for the optimal brightness to achieve a target luminance.
        Generates a psychopy monitor calibration file named "Gamma1.LuminanceN"
        where N is `lum_target`.

    Algorithm is:
    1. set brightness
    2. calibrate gamma @ brightness
    3. check luminance @ color_target
    4. If luminance within tolerance of target, done. Otherwise pick new 
         brightness and go back to 1.

    Args:
        colorcal (psychopy.hardware.crs.ColorCal): a ColorCal
        lum_target (float): target luminance in cd/m^3
        lum_tolerance (float): luminance tolerance in cd/m^3
        color_target (tuple): target color to optimize luminance at
        screen (int): screen to draw to

    Returns:
        int: optimal brightness for reaching `lum_target` @ `color_target`

    """
    # starting brightness
    b = 50
    max_bright = 100
    min_bright = 0

    mon = WinMonitor(screen)
    init_brightness = mon.brightness
    init_contrast = mon.contrast
    optimal_brightness = None
    mon.contrast = 50
    # Should require at most 8 iterations regardless of tolerance.
    for _ in range(8):
        mon.brightness = b
        # Calibrate monitor @ brightness        
        monitor_cal = gamma(screen=screen, target_candela=lum_target)
        # Check Luminance
        lum = get_luminance(monitor_cal, colorcal, screen=screen)
        print("Luminance @ brightness {}: {}".format(b, lum))
        if abs(lum-lum_target) <= lum_tolerance:
            # found optimal brightness
            optimal_brightness = b
            break
        elif lum > lum_target:
            # lower
            max_bright = b
        elif lum < lum_target:
            # higher
            min_bright = b
        else:
            # shouldn't ever happen
            raise ValueError("Here be dragins.")
            
        b = int((max_bright + min_bright)/2)

    # return to original brightness
    mon.brightness = init_brightness
    mon.contrast = init_contrast
    return optimal_brightness


def main(*args):
    '''
    arg[1] is either 'calibrate' : perform full calibration, or
                     'luminance' - get current luminance value at (0,0,0)
                     'devices' - show list of calibration devices installed
    arg[2] is target candela / m**2 (defaults to 50 if not provided)
    arg[3] is the screen to use in Psychopy (0, 1, ...)
    '''
    screen = 0
    lum_target = 50 # cd/m^3
    lum_tolerance = 2 # +/- cd/m^3
    color_target = (0.0,0.0,0.0) #grey
    #color_target = (-1.0, -1.0, -1.0) #black

    #brightness
    b = 50
    max_bright = 100
    min_bright = 0

    try:
        command = args[1].lower()
        try:
            arg2 = float(args[2])
            try:
                arg3 = int(args[3])
            except IndexError:
                arg3 = None
        except IndexError:
            arg2, arg3 = None, None
    except IndexError:
        command = None

    if command == 'devices':
        # displays connected hardware
        get_system_hardware_info()

    elif command == 'luminance':
        # gets luminance using a gamma window 
        # @ a specified color
        # @ the current brightness
        colorcal = get_colorcal()
        screen = int(arg2) or screen
        lum = get_luminance("Gamma1.Luminance{}".format(lum_target),
                            colorcal=colorcal,
                            screen=screen,
                            color=color_target)
        colorcal.com.close()
        print('Color: {}, cd/m^2: {}'.format(color_target, lum))

    elif command == 'verify':
        # loops through the color range (-1.0, 1.0)
        # shows the liminance values
        # @ the current brightness
        colorcal = get_colorcal()
        screen = int(arg2) or screen

        for i in range(-10, 11, 1):
            color = 0.1*i
            lum = get_luminance("Gamma1.Luminance{}".format(lum_target),
                                colorcal=colorcal,
                                screen=screen,
                                color=(color, color, color))
            print('Color: {}, cd/m^2: {}'.format(color, lum))
        colorcal.com.close()

    elif command == "step":
        lum_target = arg2 or lum_target
        step_size = arg3 or 10
        colorcal = get_colorcal()
        step_luminance(colorcal, lum_target=lum_target, step_size=step_size, screen=0)
        colorcal.com.close()

    elif command == "calibrate":
        # calibrates monitor and displays optimal brightness setting
        colorcal = get_colorcal()
        screen = arg3 or screen
        lum_target = arg2 or lum_target
        lum = luminance_search(colorcal=colorcal,
                               lum_target=lum_target,
                               lum_tolerance=lum_tolerance,
                               color_target=color_target,
                               screen=screen)
        colorcal.com.close()
        if lum is not None:
            print("Optimal brightness @ {} cd/m^3: {}".format(lum_target,
                                                              lum))
        else:
            print("Optimal brightness not found.")

    else:
        print("Valid commands are: \n\t1. calibrate\n\t2. devices\n\t3. luminance\n\t4. verify\t5. step")

if __name__ == "__main__":
    #TODO: use argparse library
    main(*sys.argv)

    

# -*- coding: utf-8 -*-
"""! @file  util.py

   @brief Utility functions for gammacal, hopefully temporary.

   @author  Perry Hargrave
   @date    2016-05-05

A temporary file while re-factoring old gammacal code bits.
"""
from datetime import datetime
import logging
from matplotlib import pyplot as plt
import numpy as np
import os
import psychopy
import psychopy.visual
import time
import winerror

# FIXME: Monkey patching psychopy?
# According to Derric W, this may have been due to:
#   https://github.com/psychopy/psychopy/issues/504
#
# from gammaAIBS import setGammaRamp as RAMP
# psychopy.gamma.setGammaRamp = RAMP

COLORS = [np.array([-1.0, -1.0, -1.0]) + 0.1*i for i in range(0, 21)]

def make_folders():
    """Create output folders for graphs and csv values.

    Normally in C:\users\%USER%\Desktop\gamma_correct

    return filepath created.
    """
    root = os.path.join(os.environ.get('userprofile'),
                        'desktop',
                        'gamma_correction',
                        datetime.now().strftime("%Y%m%d_%H%M"))
    try:
        os.makedirs(root)
    except WindowsError as we:
        logging.debug("Caught error making folder: %s", we)
        if we.winerror not in (winerror.ERROR_ALREADY_EXISTS, ):
            raise we
    logging.debug("Created folders in: %s", root)
    return root

def make_graphs(intensity, rawlum, fitlum, brightness, path, corrected=False):
    """Plots of illuminance vs intensity and saves csv arrays.
    """
    xaxis = [x[0] for x in COLORS]
    fig = plt.figure(figsize=(12, 7.5))
    raw = np.array([xaxis, rawlum])
    fit = np.array([xaxis, fitlum])

    # original code converts x-axis to +/-1 but why is unclear to me. Maybe
    # makes sense to be 0-1?
    # raw[0] = np.arange(0, 1.01, 0.05)
    plt.plot(raw[0], raw[1], 'b.', label="Data")
    plt.plot(fit[0], fit[1], 'r-', label="Curve fit")
    plt.legend(loc=0)
    plt.xlabel("Intensity")
    plt.ylabel("Illuminance (counts)")

    if corrected:
        plt_title = "GammaCorrect"
        csv_data = fit
    else:
        plt_title = "testMonitor"
        csv_data = raw

    basename = "{0}{1}".format(plt_title, brightness)
    plt.title(basename)

    fig.savefig(os.path.join(path, basename + '.pdf'))

    np.savetxt(os.path.join(path,
                            basename + '.csv'),
               csv_data,
               delimiter=",")
    plt.close(fig)


def gamma_test(spec, w):
    """
    NOTE: Assumes integration time has already been set.
    """
    samples = []
    for color in COLORS:
        w.setColor(color)
        w.flip()
        w.flip()
        time.sleep(.1)
        samples.append(spec.spectrum())
    return samples

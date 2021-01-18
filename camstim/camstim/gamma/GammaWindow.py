# -*- coding: utf-8 -*-
"""
Created on Fri Nov 01 11:56:08 2013

@author: chrism
"""
import psychopy.monitors
import psychopy.visual
import numpy as np
from scipy.optimize import curve_fit
import time

from util import make_graphs, gamma_test

# Units in CM, taken from 'old' code
MONITOR_WIDTH = 52
MONITOR_DISTANCE = 15

class GammaWindow(object):
    def __init__(self,
                 spec,
                 savepath,
                 brightness, 
                 screen,
                 sizePix = [1920,1200],
                 target_candela = 50):
        self.brightness = brightness
        self.savepath = savepath
        self.spec = spec
        self.gammamode = False
        self.screen = screen
        self.sizePix = sizePix
        self.target_candela = target_candela

    def _make_monitor(self):
        """Returns a monitor with correct properties for CAM.
        """
        m = psychopy.monitors.Monitor(self.monitor_type,
                                      width=MONITOR_WIDTH,
                                      distance=MONITOR_DISTANCE)
        # Didn't see a way to pass this to the constructor
        m.setSizePix((1920, 1200))
        return m

    @property
    def monitor_type(self):
        # keeping monitor labeling in case camstim is using this
        mtype = "Gamma1.Luminance{0}".format(int(self.target_candela))
        if self.gammamode == False:
            #mtype = "testMonitor1.Luminance{0}".format(self.target_candela)
            mtype = "testMonitor"
        return mtype

    def getGammaGrid(self, fitparams):
        mon = self._make_monitor()
        grid = np.empty((4,6))
        grid = mon.getGammaGrid()
        grid[0,2] = fitparams[3,1]
        grid[0,3] = fitparams[3,2]
        grid[0,5] = fitparams[3,0]
        grid[1,2] = fitparams[2,1]
        grid[1,3] = fitparams[2,2]
        grid[1,5] = fitparams[2,0]
        grid[2,2] = fitparams[1,1]
        grid[2,3] = fitparams[1,2]
        grid[2,5] = fitparams[1,0]
        grid[3,2] = fitparams[0,1]
        grid[3,3] = fitparams[0,2]
        grid[3,5] = fitparams[0,0]
        return grid

    def monitorcal(self):
        ''' 
        '''
        self.gammamode = False
        #print("MONITOR", self.monitor_type)
        m = self._make_monitor()

        new_gamma = 1.001
        grid = m.getGammaGrid()
        for j in range(4):
            grid[j,2] = new_gamma
        m.setGammaGrid(grid)

        m.saveMon()
        w = psychopy.visual.Window(monitor=self.monitor_type,
                                   fullscr=True,
                                   screen=self.screen,
                                   waitBlanking=True, 
                                   size=self.sizePix)
        sample = gamma_test(self.spec, w)
        w.close()
        fp = self.fit_gamma(sample)
        grid = self.getGammaGrid(fp)
        del m

        # Now the updated gammaramp will save to corrected monitor type
        self.gammamode = True
        #print("MONITOR", self.monitor_type)
        m = self._make_monitor()
        m.setGammaGrid(grid)
        m.saveMon()
        w = psychopy.visual.Window(monitor=self.monitor_type,
                                   fullscr=True,
                                   screen=self.screen,
                                   waitBlanking=True,
                                   size=self.sizePix)
        sample = gamma_test(self.spec, w)
        w.close()
        fp = self.fit_gamma(sample)
        return self.monitor_type


    def fit_gamma(self, sample):
        #FIXED WITH THE NEW FUNC CHANGE  FIXME: <<- saywha?
        values = np.arange(0, 21, 1, dtype=float)
        # values = arange(1E-9,21+(1E-9),1, dtype=float)
        # stop = 201 must be > final value
        # step = 10 is the step size between value points.
        data = np.zeros((len(values),4))
        fitparams = np.empty((4,3))

        for i in range(0,len(values)):
            spin=sample[i]
            data[i,0] = np.average(spin[1][(spin[0] < 451) & (spin[0] > 449)])
            data[i,1] = np.average(spin[1][(spin[0] < 536) & (spin[0] > 534)])
            data[i,2] = np.average(spin[1][(spin[0] < 601) & (spin[0] > 599)])
            data[i,3] = sum(data[i,0:3])

        def func(x,k,g,a):
            if k < 0:
                # FIXME: What does this mean?
                # this fix works..., make sure that the input values are floats,
                # or else, this method doesn't work, you probably won't even get
                # a traceback for it...
                if x[0] != 1E-9:
                    x[0] += 1E-9
            return (k*(pow(x,g)))+a

        p0 = [200, 2, 10]
        for i in range(0,4):
            popt, pcov = curve_fit(func, values, data[:,i], p0)
            fitparams[i,:] = popt
            yf = ((popt[0])*(pow(values, (popt[1]))))+(popt[2])

        make_graphs(intensity=10*values,
                    rawlum=data[:,3],
                    fitlum=yf,
                    corrected=self.gammamode,
                    path=self.savepath,
                    brightness=self.brightness)

        return fitparams



if __name__ == "__main__":
    Calib=GammaWindow()



'''
Created on Nov 9, 2012

@author: derricw

Reward.py

Simple reward class.  Uses NIDAQ digital IO to trigger a reward (can be anything, we are currently
    using this to flip a relay controlling a valve).

#TODO: rewrite this whole shitfest.

'''
from toolbox.IO.nidaq import DigitalOutput as do
from toolbox.IO.nidaq import AnalogOutput as ao
from toolbox.IO.nidaq import DigitalInput as di

import numpy as np
from threading import Timer
import time


class Reward(object):
    '''
    Reward object. Flips a timed IO Line.

    Parameters
    ----------

    device : 'Dev1'
        NI DAQ device id
    port : 1
        NI DAQ port number (Digital)
    line : 0
        NI DAQ line number (Digital)
    channel : 0
        NI DAQ channel number (Analog)
    mode : 'volume'
        Accepts 'volume' or 'time'.  Volume mode will calculate time
        based on slope and offset from calibration.
    rewardtime : 0.2
        How long (seconds) the reward trigger lasts.
    rewardvol : 0.01
        Volume of reward.
    calibration : (1,0)
        Slope and offset for volume calibrations.
    device_type : 'digital'
        'Analog' or 'digital' task.
    task : NIDAQMX task object
        Optional NIDAQMX task to be used.
    invert : False
        Boolean; should we invert NC/NO on the relay?

    Examples
    --------

    >>> reward = Reward('Dev1',
                        device_type='digital')  #create a reward object
    >>> reward.reward()           #trigger reward
    >>> time.sleep(5)             #sleep for 5 seconds
    >>> reward.stop()             #turn off NIDAQ (can be restarted)
    >>> reward.clear()            #clear NIDAQ task (cannot be restarted)

    '''

    def __init__(self, 
                 device='Dev1',
                 port=0, 
                 line=0,
                 channel=0,
                 mode='volume',
                 rewardtime=0.2,
                 rewardvol=0.01,
                 calibration=(1,0),
                 task=None,
                 invert=False,
                 ):

        self.device = device
        self.port = port
        self.line = line
        self.channel=channel
        self.rewardtime = rewardtime
        self.rewardvol = rewardvol
        self.mode = mode.lower()
        self.calibration = calibration
        self.invert=invert

        if task:
            self.out = task
        else:
            self.out = do(device,port,lines=str(line))
            self.line = 0  #because from here on out we use this as an index
        self.on = 1
        self.off = 0

        self.rewardcount = 0
        self.volumedispensed = 0

        if not task: self.start()

        if invert:
            self.on, self.off = self.off, self.on
        
    def __repr__(self):
        return "Reward('%s',%s,%s,%s,'%s',%s,%s,%s,'%s',%s)"%(self.device,self.port,self.line,
            self.channel,self.mode,self.rewardtime,self.rewardvol,
            self.calibration,self.out,self.invert)

    def start(self):
        '''Starts IO task '''
        try:
            self.out.StartTask()
        except Exception, e:
            logging.warning("Warning starting reward task: {}".format(e))
        
    def stop(self):
        '''Stops IO task '''
        self.out.WriteBit(self.line,self.off)
        try:
            self.out.StopTask()
        except Exception, e:
            logging.warning("Couldn't stop task: {}".format(e))

    def clear(self):
        '''Clears IO task '''
        try:
            self.stop()
        except:
            pass #already stopped?
        try:
            self.out.ClearTask()
        except Exception, e:
            logging.warning("Couldn't clear task: {}".format(e))

    def reward(self):
        '''Dispenses reward and starts timer'''

        #reward mode: time or volume?
        if self.mode == 'time':
            rwtime=self.rewardtime
        elif self.mode == 'volume':
            rwtime = self.rewardvol*self.calibration[0]+self.calibration[1]
        else:
            rwtime=0
            logging.warning("Reward mode %s is invalid."%(self.mode))

        #start reward
        self.out.WriteBit(self.line,self.on)

        #end reward with a callback
        t = Timer(rwtime,self._endreward)
        t.start()
        self.rewardcount += 1
        self.volumedispensed += self.rewardvol
        
    def _endreward(self):
        '''Ends the reward after timer ticks '''
        self.out.WriteBit(self.line,self.off)


class Punishment(object):
    """Punishment is, until further need, just a slightly different version of Reward"""
    def __init__(self, 
        device='Dev1',
        port=0, 
        line=0,
        punishtime=0.2,
        task=None,
        invert=False,
        ):

        '''Construct punishment '''
        self.device = device
        self.port = port
        self.line = line
        self.punishtime=punishtime

        if task:
            self.out = task
        else:
            self.out = do(device,port)
        self.on = 0
        self.off = 1

        self.punishcount=0

        if invert:
            self.on,self.off=self.off,self.on

        if not task: self.start()

    def __repr__(self):
        return "Punishment('%s',%s,%s,%s)"%(self.device,self.port,self.line,
            self.punishtime)

        
    def start(self):
        '''Starts IO task '''
        try:
            self.out.StartTask()
        except Exception, e:
            print "Warning starting punishment task:",e
        
    def stop(self):
        '''Stops IO task '''
        self.out.WriteBit(self.line,self.off)
        try:
            self.out.StopTask()
        except Exception, e:
            print "Couldn't stop task:",e

        
    def clear(self):
        '''Clears IO task '''
        try:
            self.stop()
        except:
            pass #already stopped?
        try:
            self.out.ClearTask()
        except Exception, e:
            print "Couldn't clear task:",e

    def punish(self):
        '''Dispenses punishment and starts timer'''
        #start reward
        self.out.WriteBit(self.line,self.on)

        #end reward with a callback
        t = Timer(self.punishtime,self._endpunish)
        t.start()
        self.punishcount += 1
        
    def _endpunish(self):
        '''Ends the reward after timer ticks '''
        self.out.WriteBit(self.line,self.off)    


class Licksensor(object):
    """ 
    Simple abstration layer for lick sensor. 
    """
    def __init__(self,
        device='Dev1',
        port=0,
        line=0,
        invert=False,
        task=None):

        self.line = line
        self.port = port
        self.invert = invert

        if task:
            self.task = task
        else:
            self.task = di(device,port)
            self.task.StartTask()

    def clear(self):
        try:
            self.task.ClearTask()
        except Exception, e:
            print "Couldn't clear lick sensor task.",e

    def getState(self):
        state = self.task.Read()[self.line]
        if not self.invert:
            return state
        else:
            return np.abs(1-state)

    def __repr__(self):
        return "Licksensor('%s',%s,%s,%s,%s)"%(self.device,self.port,self.line,
            self.invert,self.task)
            
            
            
class StartLapTTL(object):
    """Based on the Reward digital out"""
    def __init__(self, 
        device='Dev1',
        port=0, 
        line=0,
        pulsetime=0.05,
        task=None,
        invert=False,
        ):

        '''Construct '''
        self.device = device
        self.port = port
        self.line = line
        self.pulsetime=pulsetime

        if task:
            self.out = task
        else:
            self.out = do(device,port)
        self.on = 0
        self.off = 1

        self.ttlcount=0  # Maybe delete this

        if invert:
            self.on,self.off=self.off,self.on

        if not task: 
            self.start()

    def __repr__(self):
        return "StartLapTTL('%s',%s,%s,%s)"%(self.device,self.port,self.line,
            self.pulsetime)

        
    def start(self):
        '''Starts IO task '''
        try:
            self.out.StartTask()
        except Exception, e:
            print "Warning starting punishment task:",e
        
    def stop(self):
        '''Stops IO task '''
        self.out.WriteBit(self.line,self.off)
        try:
            self.out.StopTask()
        except Exception, e:
            print "Couldn't stop task:",e

        
    def clear(self):
        '''Clears IO task '''
        try:
            self.stop()
        except:
            pass #already stopped?
        try:
            self.out.ClearTask()
        except Exception, e:
            print "Couldn't clear task:",e

    def ttlPulse(self):
        '''Dispenses punishment and starts timer'''
        #start pulse
        self.out.WriteBit(self.line,self.on)

        #end pulse with a callback
        t = Timer(self.pulsetime,self._endPulse)
        t.start()
        self.ttlcount += 1
        
    def _endPulse(self):
        '''Ends the reward after timer ticks '''
        self.out.WriteBit(self.line,self.off)   


if __name__ == "__main__":
    import time
    p = Reward('Dev1',1,0)
    print str(p)
    p.reward()
    time.sleep(2)
    p.clear()
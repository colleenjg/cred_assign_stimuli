# -*- coding: utf-8 -*-
"""
sync.py

@author: derricw

Provides some classes useful for synchronization and data alignment.
"""
from psychopy import visual
from camstim.experiment import EObject


class SyncPulse(EObject):
    """
    Digital IO pulse that can occur at various times in the experiment.

    args
    ----
    device : str
        NIDAQ device id, for example "Dev1"
    port : int
        NIDAQ port number
    line : int
        NIDAQ line number
    invert : bool
        Whether to invert IO logic
    task : task
        NIDAQ task to use.  If none, SyncPulse creates its own.

    """

    def __init__(self,
                 device,
                 port,
                 line,
                 invert=False,
                 task=None):

        super(SyncPulse, self).__init__()
        self.device = device
        self.port = port
        self._task = task
        self.line = line
        self.invert = invert

        self._high = 1
        self._low = 0

        if self.invert:
            self._high, self._low = self._low, self._high
            initial_state = "high"
        else:
            initial_state = "low"

        if not self._task:
            from toolbox.IO.nidaq import DigitalOutput
            self._task = DigitalOutput(self.device,
                                       port=self.port,
                                       lines=str(self.line),
                                       initial_state=initial_state)

            self._task.start()

    def set_high(self):
        self._task.writeBit(0, self._high)

    def set_low(self):
        self._task.writeBit(0, self._low)

    def package(self):
        return super(SyncPulse, self).package()


class SyncSquare(visual.GratingStim, EObject):
    """
    A small square that can be used to flash black to white at a specified
        frequency.
    """

    def __init__(self,
                 window,
                 tex=None,
                 size=(100, 100),
                 pos=(-300, -300),
                 frequency=1,  # this is actually half period in frames
                 colorSequence=[-1, 1],
                 ):

        visual.GratingStim.__init__(self,
                                    win=window,
                                    tex=None,
                                    size=size,
                                    pos=pos,
                                    color=colorSequence[0],
                                    units='pix')  # old style class

        # this is actually 1/2 period in frames, not frequency
        self.frequency = frequency
        self.colorSequence = colorSequence
        self.seq_length = len(self.colorSequence)
        self.index = 0

    def update(self, vsync):
        if vsync % self.frequency == 0:
            self.setColor(self.colorSequence[self.index])
            self.index += 1
            if self.index >= self.seq_length:
                self.index = 0
        self.draw()



#!/usr/bin/env python

"""
Experimenting with QCoreApplication for experiment container
    and component signaling.
"""
import os
import sys
import time
import signal
import pprint
import datetime
import platform
from collections import OrderedDict

from qtpy import QtCore

from misc import getPlatformInfo, printHeader, save_session, CAMSTIM_DIR

if "Windows" in platform.system():
    try:
        #attempt to fix numpy's weird handling for CTRL+C in WINDOWS
        ##########################################################################

        import imp, win32api, ctypes, thread
        basepath = imp.find_module("numpy")[1]
        lib1 = ctypes.CDLL(os.path.join(basepath, 'core', 'libmmd.dll'))
        lib2 = ctypes.CDLL(os.path.join(basepath, 'core', 'libifcoremd.dll'))


        def ctrlc_handler(sig, hook=thread.interrupt_main):
            hook()
            return 1

        win32api.SetConsoleCtrlHandler(ctrlc_handler, 1)
        ##########################################################################
    except Exception as e:
        print("Failed to fix numpy CTRL+C handler.")
import logging

###############################################################################


class Experiment(QtCore.QObject):
    """
    Defines a basic behavior or stimulus experiment.
    """

    started = QtCore.Signal()
    closed = QtCore.Signal()

    def __init__(self, parent=None):
        super(Experiment, self).__init__(parent)
        self._parent = parent

        self._update_timer = QtCore.QTimer()
        self._update_timer.timeout.connect(self.update)
        self._update_count = 0

        self.platform_info = getPlatformInfo()
        logging.debug("{}".format(self.platform_info))

        self.items = OrderedDict()
        self.threads = []
        self._qthreads = []

        self._app = QtCore.QCoreApplication(sys.argv)
        self.closed.connect(self._app.quit)
        signal.signal(signal.SIGINT, self.exit_handler)

        # Signal timer lets python handle signals like CRTL+C
        self._signal_timer = QtCore.QTimer()
        self._signal_timer.timeout.connect(lambda: None)
        self._signal_timer.start(100)

    def add_item(self, item, name=""):
        """
        Adds an item to the experiment.
        """
        if not name:
            length = len(self.items.keys())
            name = "unnamed_item_%s" % length

        item._parent = self
        self.items[name] = item

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

    def start(self):
        logging.info("Experiment started.")
        self.start_time = datetime.datetime.now()
        for item in self.items.values():
            item.start()
        for thread in self.threads:
            QtCore.QTimer.singleShot(1, thread.run)
        self.started.emit()

        sys.exit(self._app.exec_())

    def update(self):
        #is this necessary?
        self._update_count += 1

    def close(self):
        """ Ends the session.  Closes all items and threads, saves
            output file.
        """
        self.stop_time = datetime.datetime.now()
        self._output_file = OutputFile()

        for item in self.items.values():
            item.close()
        for thread in self.threads:
            thread.terminate()
        for qthread in self._qthreads:
            qthread.quit()

        logging.info("Experiment closed.")
        self.closed.emit()

        self.items = OrderedDict({k: v.package() for k, v in self.items.iteritems()})

        #_ = [pprint.pprint(item) for item in wecanpicklethat(self.__dict__).items()]
        self._output_file.add_data(self.__dict__)
        self._output_file.save()

        logging.info("Experiment saved to: {}".format(self._output_file.path))

    def exit_handler(self, *args):
        self.close()
        self._app.quit()


class EObject(QtCore.QObject):
    """
    Base class for all experiment objects.
    """
    def __init__(self):
        QtCore.QObject.__init__(self)
        self._parent = None
        self.items = OrderedDict()

    def add_item(self, item, name=""):
        """
        Adds an item to the experiment.
        """
        if not name:
            length = len(self.items.keys())
            name = "unnamed_item_%s" % length

        self.items[name] = item
        item._parent = self  # DO I LIKE THIS? NOT REALLY

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

    def has_item(self, name):
        if name in self.items.keys():
            return True
        else:
            return False

    def get_item(self, name):
        return self.items[name]

    def update(self, index=None):
        pass

    def start(self):
        pass

    def close(self):
        pass

    def package(self):
        return wecanpicklethat(self.__dict__)


class ETimer(QtCore.QTimer):
    """ Extends QTimer execept handles conversion to msecs, since that is
        preferred by the scientists.
    """
    @staticmethod
    def singleShot(seconds, receiver):
        msecs = int(seconds*1000)
        QtCore.QTimer.singleShot(msecs, receiver)

    def start(self, seconds):
        msecs = int(seconds*1000)
        super(ETimer, self).start(msecs)


class Timetrials(EObject):
    """ Timetrials object.

    TODO: switch timers to ETimer

    Args:
        times (Optional[list]): a iterable containing times.
        units (Optional[str]): units for the times ('msec', 'sec', 'min')

    """
    trial_started = QtCore.Signal(int)
    trial_completed = QtCore.Signal(int)
    all_trials_completed = QtCore.Signal(int)

    _u_multi = {'msec': 1, 'ms':1, 'sec': 1000, 's': 1000, 'min': 60000,
                'hours': 3600000}

    def __init__(self,
                 times=[],
                 units='sec'):

        super(Timetrials, self).__init__()

        self.units = units

        if times:
            self.set_times(times, units)

        self._trial = 0

        self.t0 = 0
        self.trial_lengths = []
        self._current_trial_len = 0.0
        self.auto_start = True
        self.trial_starts = []

        self.trial_timer = QtCore.QTimer()
        self.trial_timer.timeout.connect(self._trial_ended)

    def set_times(self, times, units=None):
        """
        Sets the trials for this experiment.
        """
        if units:
            self.set_units(units)
        if isinstance(times, (int, float)):
            self.times = int(times*self._u_multi[self.units])
        else:
            self.times = [int(t*self._u_multi[self.units]) for t in times]

    def extend_trial(self, t):
        """ extends the trial by a certain amount of time.
            If no trial is started, starts a trial with `time` extra length
            units must be same as trials.
        """
        elapsed = time.clock() - self.trial_starts[-1]
        remaining = self._current_trial_len - elapsed
        self.trial_timer.stop()
        self.trial_timer.start(remaining + t)
        logging.info("Trial {} extended by {} seconds.".format(self._trial, t))

    def set_units(self, units):
        if units.lower() in self._u_multi.keys():
            self.units = units.lower()
        else:
            raise ValueError("Invalid unit string. Try 'sec', etc")

    def _trial_ended(self):
        """
        Callback for trial_timer timeout.  Ends trial, logs the time.
        """
        self.trial_completed.emit(self._trial)
        t = time.clock()
        self.trial_lengths.append(t-self.trial_starts[-1])
        self.trial_starts.append(t)
        logging.info("Trial %s timed out at %s" % (self._trial-1, t))
        if not self.auto_start:
            self.stop()

    def next(self):
        """ Starts the next trial.
        """
        if not isinstance(self.times, int):
            try:
                self._current_trial_len = self.times[self._trial]
            except IndexError:
                self.trial_timer.stop()
                logging.info("All timetrials completed.")
                self.all_trials_completed.emit(self._trial)
                return
        else:
            self._current_trial_len = self.times

        self.trial_starts.append(time.clock())
        self.trial_timer.start(self._current_trial_len)
        self.trial_started.emit(self._trial)
        self._trial += 1

    def start(self, times=[]):
        """ Starts the time trials.  Optionally can pass some times if we haven't
            set up a list of times yet.
        """
        #self.trial_starts.append(t)
        if times:
            self.set_times(times)
        if self.times:
            self.next()
        else:
            raise RuntimeError("No trial times assigned.")

    def stop(self):
        """
        Stops the time trials.
        """
        self.trial_timer.stop()
        logging.info("Timetrials stopped.")

    def close(self):
        """
        Close method for time trials.
        """
        self.stop()
        logging.info("Timestrials closing.")




class OutputFile(QtCore.QObject):
    """
    Docstring for OutputFile

    #TODO: Should this be an EObject?
    """

    output_saved = QtCore.Signal()

    def __init__(self, path="", output={}):
        super(OutputFile, self).__init__(None)
        self.path = path
        self._output = output

        self.dt = datetime.datetime.now()
        self.dt_str = self.dt.strftime('%y%m%d%H%M%S')

    def save(self, path=""):
        import cPickle as pickle
        output = wecanpicklethat(self._output)
        if path:
            self.path = path
        if self.path:
            path = self.path
        else:
            path = os.path.join(CAMSTIM_DIR, "output/%s.pkl" % self.dt_str)
        dirname = os.path.dirname(path)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        if os.path.isfile(path):
            filename = os.path.basename(path)
            dirname = os.path.dirname(path)
            path = os.path.join(dirname, self.dt_str+"-"+filename)
            logging.warning("File path already exists, saving to: {}".format(path))
        with open(path, 'wb') as f:
            pickle.dump(output, f)
        self.path = path


    def add_data(self, data_dict):
        self._output.update(data_dict)


def wecanpicklethat(datadict):
    """
    Input is a dictionary.
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
                _ = pickle.dumps(test)
                pickleable[k] = v
        except:
            unpickleable.append(k)
    pickleable['unpickleable'] = unpickleable
    return pickleable


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    pass

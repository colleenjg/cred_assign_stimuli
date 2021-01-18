""" ZRO remote control and data publishing functionality for behavior.
"""
import time
from camstim.experiment import EObject
from zro import Publisher

class RemoteControl(Publisher, EObject):
    """
    Implements some public functions for controlling the task, and some
        functionality for publishing data.
    """
    def __init__(self, task, rep_port=12000, pub_port=9998, hwm=100):
        self._task = task
        Publisher.__init__(self, rep_port=rep_port, pub_port=pub_port, hwm=hwm)
        EObject.__init__(self)


    def _finalize(self):
        self._task._close()

    def update(self, index=None):
        self._check_rep()

    def package(self):
        return {"rep_port": self.rep_port,
                "pub_port": self.pub_port}

    def _build_header(self):
        return {
            'init_data': {
            "task_id": self._task.config.get('behavior', {}).get('task_id', ""),
            "mouse_id": self._task.config.get('behavior', {}).get('mouse_id', ""),
            },
            "index": -1,
        }

    def _build_footer(self):
        header = {
            "task_id": self._task.config.get('behavior', {}).get('task_id', ""),
            "mouse_id": self._task.config.get('behavior', {}).get('mouse_id', ""),
            }
        
        return {
            'header': header,  # backwards compatibility hack for OAG
            'init_data': header, # backwards compatibility hack for OAG
            'final_data': {},
            "index": -2,
        }

    def publish_header(self):
        time.sleep(0.5)
        header = self._build_header()
        self.publish(header)

    def publish_footer(self):
        footer = self._build_footer()
        self.publish(footer)


    def close(self):
        pass

class HabituationRemoteControl(RemoteControl):
    """ Passive habituation remote control.  Exposes controls for habituating
        animals and automatically publishes data every second.
    """
    def __init__(self,
                 task,
                 rep_port=12000,
                 pub_port=9998,
                 ):
        super(HabituationRemoteControl, self).__init__(self,
                                                       rep_port=rep_port,
                                                       pub_port=pub_port)
        self._packet_interval = 60  #send a packet every 60 updates (frames)
        self._packet_counter = 0

        # publish header automatically
        self.publish_header()

    def update(self, index=None):
        super(HabituationRemoteControl, self).update(index)
        if not index:
            index = self._task._update_count
        if index % self._packet_interval == 0:
            self.publish(self._build_packet())
        self._packet_counter += 1

    def _build_packet(self):
        return {
            "lick_sensors": self._lick_packet,
            "rewards": self._reward_packet,
            "encoder": self._encoder_packet,
            "index": self._packet_counter,
        }

    @property
    def _lick_packet(self):
        """ A single packet of lick data for real-time analysis. 
            TODO: move out of here"""
        return [l._lick_packet for l in self._task.lick_sensors]

    @property
    def _reward_packet(self):
        """ A single packet of reward data for real_time analysis. """
        return [r._reward_packet for r in self._task.rewards]

    @property
    def _encoder_packet(self):
        """One packet of encoder data destined for display server."""
        return self._task.encoders[0].dx[-59:]

    def close(self):
        """ Called at experiment end. Automatically publishes footer. """
        self.publish_footer()
        super(HabituationRemoteControl, self).close()


class DoCRemoteControl(RemoteControl):
    """ Detection of Change remote control.  Exposes controls specific for
            the detection of change task. """
    def __init__(self,
                 task,
                 rep_port=12000,
                 pub_port=9998,
                 ):
        super(DoCRemoteControl, self).__init__(task=task,
                                               rep_port=rep_port,
                                               pub_port=pub_port)
        self.publish_header()
        
            
if __name__ == "__main__":
    rc = RemoteControl("test")
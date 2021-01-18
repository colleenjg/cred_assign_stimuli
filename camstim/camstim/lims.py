"""

lims.py

Some functions for lims interaction.

"""

import urllib2
import json
import urlparse
import platform
import os
import pprint
import datetime

class LimsInterface(object):
    """ A lims connection providing donor and behavior info. """
    def __init__(self, base_url="http://lims2"):
        super(LimsInterface, self).__init__()
        self.base_url = base_url

        self._cache = {}
        
    def get_donor_info(self, labtracks_id):
        """
        Returns all information for a donor.
        """
        labtracks_id = str(labtracks_id)
        if labtracks_id in self._cache:
            return self._cache[labtracks_id]

        url = urlparse.urljoin(self.base_url,
            "donors/info/details.json?external_donor_name=%s" % labtracks_id)
        donor_html = self.get_html(url)
        data = json.loads(donor_html)
        if isinstance(data, list):
            data = data[0]

        self._cache[labtracks_id] = data
        return data

    def get_html(self, url):
        try:
            return urllib2.urlopen(url).read()
        except urllib2.URLError:
            #try a mouse we KNOW exists
            url = urlparse.urljoin(self.base_url,
                "donors/info/details.json?external_donor_name=122123")
            try:
                urllib2.urlopen(url).read()
            except urllib2.URLError:
                raise LimsError("LIMS could not be reached.")

            raise LimsError("Mouse doesn't exist in LIMS.")

    def get_donor_id(self, labtracks_id):
        donor = self.get_donor_info(labtracks_id)
        return donor.get("id", None)

    def get_behavior_info(self, labtracks_id):
        donor = self.get_donor_info(labtracks_id)
        return donor.get('behavior_training', {})

    def get_behavior_id(self, labtracks_id):
        behavior_info = self.get_behavior_info(labtracks_id)
        return behavior_info.get('id', None)

    def get_trigger_dir(self, labtracks_id):
        donor = self.get_donor_info(labtracks_id)
        return donor['specimens'][0]['project']['trigger_dir']


class TriggerFile(object):
    """
    A trigger file for data upload to LIMS.
    """
    def __init__(self, trigger_dir, dummy=False):
        self._trigger_dir = trigger_dir
        self.dummy = dummy
        self.timestamp = datetime.datetime.now().strftime('%y%m%d%H%M%S')

        self._windows_dir = "/" + self._trigger_dir
        self._unix_dir = self._trigger_dir

    @property
    def trigger_dir(self):
        if self.dummy:
            user_dir = os.path.expanduser("~")
            fake_trigger_dir = os.path.join(
                user_dir, self._trigger_dir[1:])
            return fake_trigger_dir
        else:
            if "windows" in platform.system().lower():
                return self._windows_dir
            else:
                return self._unix_dir

    @property
    def incoming_dir(self):
        return self.trigger_dir.replace("trigger/", "")
    
    def generate_text(self, fields={}):
        """
        Generates the yaml text for a set of data fields.
        """
        yaml_text = ""
        for k,v in fields.iteritems():
            v = str(v).replace("\\","/")  # lims requires all forward slashes
            yaml_text += "{}: {}\n".format(k, v)
        return yaml_text

    def write(self, trigger_filename="", fields={}):
        """
        Writes a trigger file with the specified name and data fields.
        """
        yaml_text = self.generate_text(fields)
        if not os.path.isdir(self.trigger_dir):
            os.makedirs(self.trigger_dir)
        if trigger_filename:
            if not trigger_filename.endswith(".bt"):
                trigger_filename = trigger_filename + ".bt"
            trigger_path = os.path.join(self.trigger_dir,
                                        trigger_filename)
        else:
            trigger_path = os.path.join(self.trigger_dir,
                                        self.timestamp+".bt")
        with open(trigger_path, 'w') as f:
            f.write(yaml_text)

class BehaviorTriggerFile(TriggerFile):
    """
    A behavior-rig trigger file.  So far the only think specific to beahvior
        trigger files are their project, which determines the LIMS incoming
        directory.
    """
    def __init__(self, trigger_dir, dummy=False):
        super(BehaviorTriggerFile, self).__init__(trigger_dir=trigger_dir, dummy=dummy,)

class LimsError(Exception):
    pass

if __name__ == '__main__':

    labtracks_id = "352471"

    lims = LimsInterface()
    donor = lims.get_donor_info(labtracks_id)
    b_id = lims.get_behavior_id(labtracks_id)
    trigger_dir = lims.get_trigger_dir(labtracks_id)
    print b_id
    print trigger_dir

    t = BehaviorTriggerFile(trigger_dir, dummy=True)
    print t.trigger_dir
    print t.incoming_dir

    fields = {
        "id": b_id,
        "summary": r"/projects/incoming/neuralcoding/behavior_json.json",
        "output": r"/projects/incoming/neuralcoding/behavior_pickle.pkl",
    }

    print t.generate_text(fields)

    #t.write("test_trigger", fields)

    #pprint.pprint(donor)


    #import pdb; pdb.set_trace()

"""
agent.py

Allen Institute for Brain Science

created on 20 Oct 2016

author: derricw

ZRO device for controlling behavior scripts.

This is essentially a rewrite of the stim_device.py used for CAM.

##TODO: Raises runtime errors because I can't decide on what type the errors
    actually should be.  Don't want custom error type because ZRO unpickling.

"""
import logging
import time
import os
import sys
from datetime import datetime
import subprocess
import json
from shutil import copyfile

from zro import Publisher, Proxy, ZroError
from zmq.error import Again

from camstim.misc import CAMSTIM_DIR
from camstim import __version__

AGENTLOG = os.path.join(CAMSTIM_DIR, 'agentlog')
LOG = os.path.join(CAMSTIM_DIR, 'log')
CONFIG_PATH = os.path.join(CAMSTIM_DIR, 'config/agent_config.json')

AGENT_DIR = os.path.dirname(os.path.realpath(__file__))


def make_folder(folder):
    if not os.path.isdir(folder):
        os.makedirs(folder)

for folder in [AGENTLOG,LOG,os.path.dirname(CONFIG_PATH)]:
    make_folder(folder)

DEFAULT_CONFIG = {
    "network_mouse_folder": "//allen/programs/braintv/workgroups/neuralcoding/Behavior/Data",
    "nidaq": {
        "iodaq_port_line_list": [(1,0),],
        "do_open": 1,
        "device": "Dev1",
    },
    "zro": {
        "script_rep_port": 12000,
        "rep_port": 5000,
        "pub_port": 5001,
        "whitelist": ['localhost'],
    },
    "email": {
        "error": ["derricw@alleninstitute.org"],
        "user_name": "behavioralert@alleninstitute.org",
        "password": "",
        "type": "aibs",
    },
    "rig_id": "",
}


class Agent(Publisher):
    """
    Runs scripts in a subprocess.

    Configure @ ~/camstim/config/agent_config.json

    Run with:
        $python agent.py

    Control using ZRO:
        http://stash.corp.alleninstitute.org/projects/ENG/repos/zro/browse

        >>> from zro import Proxy
        >>> p = Proxy("computer_name:rep_port")  # reply port specified in config
        >>> p.start_script("my_script.py", params=my_params)

    """
    def __init__(self):
        self._load_config()
        super(Agent, self).__init__(rep_port=self.config['zro']['rep_port'],
                                    pub_port=self.config['zro']['pub_port'])
        #super(Agent, self).set_whitelist(*self.config['zro']['whitelist'])

    def init(self):
        """
        Resets device and terminates any currently running subprocess.
        """
        if hasattr(self, "_sp"):
            self._sp.terminate()
        self._sp = None
        self._light_sp = None
        self._sp_proxy = None
        self._log = None
        self._t0 = None

        # _running is a hack i'm using to make a ghetto callback for when
        # a script completes.  attaching a callback to subprocess.Popen using
        # threading worked but I had difficulties with polling and killing the
        # process
        self._running = False
        self._light = False

        self.script_path = ""
        self.param_path = ""
        self.log_path_out = ""
        self.log_path_err = ""

        self.params = {}
        self.script = ""
        #self._load_config()
        logging.info("Device initialized...")
        self.publish(self.status)

        self.update_interval = 1000

    def _load_config(self):
        """ Loads a config file or creates one if necessary.
        """
        config_dir = os.path.dirname(CONFIG_PATH)
        if not os.path.isdir(config_dir):
            os.makedirs(config_dir)
        if not os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, sort_keys=True, indent=4,
                          separators=(",", ": "))
        
        self.config = DEFAULT_CONFIG
        logging.info("Loading config @ {}".format(CONFIG_PATH))
        with open(CONFIG_PATH, 'r') as f:
            self.config.update(json.load(f))
        logging.info("Config loaded: {}".format(self.config))

    @property
    def status(self):
        """ Status packet that provides the current state of the agent.
        """
        params = self.params
        return {
            "mouse_id": params.get('mouse_id', None),
            "task_id": params.get('task_id', None),
            "user_id": params.get('user_id', None),
            "running": self.is_running(),
            "light": self._light,
            "script_path": self.script_path,
            "param_path": self.param_path,
            "stdout_path": self.log_path_out,
            "stderr_path": self.log_path_err,
            "error_code": self.returncode,
            "elapsed_time": self.elapsed_time,
            "dio_state": self.dio_state,
        }

    @property
    def returncode(self):
        """ Return code of the most recent or currently running script.
        """
        if self._sp:
            return self._sp.returncode

    @property
    def elapsed_time(self):
        """ Time since script started.
        """
        if self.is_running():
            return time.clock()-self._t0
        else:
            return None

    @property
    def platform_info(self):
        info = super(Agent, self).platform_info
        info['version'] = __version__
        return info

    def get_state(self):
        """ WSE2 api requirement.
        """
        if self.is_running():
            return ("BUSY", "Script in progress.")
        else:
            return ("READY", "")

    def _handle_request(self, request):
        """ Publish new status packet after every request.
        """
        super(Agent, self)._handle_request(request)
        self.publish(self.status)

    def start_script(self, script, params={}):
        """
        Starts a script in a subprocess.

        Args:
            script (str): file path or just raw code to run.
            params (Optional[dict, str]): paramter dictionary to pass to script
                or path to json file
        
        """
        if self.is_running():
            raise Exception("A script is currently running.\
                Please end it before starting a new one.")

        self.light(False)
        
        if os.path.isfile(script):
            logging.info("Existing script passed: {}".format(script))
            os.chdir(os.path.dirname(script))
            with open(script, 'r') as f:
                script_text = f.read() 
        else:
            logging.info("Raw script text passed.")
            script_text = script
        self.script = script_text

        if isinstance(params, str):
            logging.info("Param file path passed: {}".format(params))
            self.param_path = params
            with open(params, 'r') as f:
                params = json.load(f)
        self.params = params
        
        mouse_id = params.get("mouse_id", None)
        if mouse_id:
            self.script_path, self.param_path = self._save_script(script_text, 
                                                                  params,
                                                                  mouse_id)
        else:
            self.script_path, self.param_path = self._temp_script(script_text,
                                                                  params)
        self._run_script()

    def start_script_from_path(self, script, temp_script_name="", params={}):
        """ DEPRECATED
        """
        logging.info("Existing script passed: {}".format(script))
        # go ahead and set CWD to same as script
        os.chdir(os.path.dirname(script))

        with open(script, 'r') as f:
            script_text = f.read() 
        self.script_path, self.param_path = self._temp_script(script_text,
                                                              params,
                                                              temp_script_name)
        self._run_script()

    def _save_script(self, script_text, params, mouse_id):
        """ Saves script to mouse folder. Returns their paths.
        
        This has gotten messy and out of control.  Lets rewrite this when we
            get a chance.
        """
        data_folder = self.config['network_mouse_folder']
        if mouse_id.lower()[0] != "m":
            mouse_id = "M" + mouse_id

        now = datetime.now().strftime('%y%m%d%H%M%S')
        local_log = "{}/{}".format(LOG, now)
        make_folder(local_log)
        
        local_scriptpath = os.path.join(local_log, "{}.py".format(now))
        local_paramspath = os.path.join(local_log, "{}.json".format(now))

        # write script and params to local session folder
        with open(local_scriptpath, 'w') as f:
            f.write(script_text)
            logging.info("Saved local script @ {}".format(local_scriptpath))
        with open(local_paramspath, 'w') as f:
            json.dump(params, f, sort_keys=True, indent=4,
                    separators=(",", ": "))
            logging.info("Saved local params @ {}".format(local_paramspath))

        network_mouse_folder = os.path.join(data_folder, mouse_id)
        network_scriptlog = os.path.join(network_mouse_folder, "scriptlog")
        network_paramlog = os.path.join(network_mouse_folder, "adjustment")

        network_scriptpath = os.path.join(network_scriptlog,"{}.py".format(now))
        network_paramspath = os.path.join(network_paramlog,"{}.json".format(now))

        for folder in [network_scriptlog, network_paramlog]:
            try:
                make_folder(folder)
            except Exception as e:
                logging.exception("Failed to create network mouse folder.")
        try:
            # write script and params to mouse folder
            with open(network_scriptpath, 'w') as f:
                f.write(script_text)
            logging.info("Saved network script @ {}".format(network_scriptpath))

            with open(network_paramspath, 'w') as f:
                json.dump(params, f, sort_keys=True, indent=4,
                        separators=(",", ": "))
            logging.info("Saved network params @ {}".format(network_paramspath))
        except Exception as e:
            logging.exception("Failed to save session to network mouse folder @ {}".format(network_mouse_folder))

        # save the paths to the network data to the database
        self._push_to_database(mouse_id, network_scriptpath, network_paramspath)
        # we want to run the local ones though
        return local_scriptpath, local_paramspath

    def _push_to_database(self, mouse_id, scriptpath, params):
        """ ADD TO MOUSE DATABASE HERE...
        ##TODO: make this work
        """
        pass

    def _run_script(self):
        """ Runs the currently loaded script and param file.
        """
        self.log_path_out = self.script_path.replace(".py", "_out.log")
        self.log_path_err = self.script_path.replace(".py", "_err.log")

        exec_string = "python {} {}".format(self.script_path, self.param_path)
        logging.info("Executing: {}".format(exec_string))
        self._t0 = time.clock()
        with open(self.log_path_out, 'wb') as out, open(self.log_path_err, 'wb') as err:
            self._sp = subprocess.Popen(exec_string.split(),
                                        stdout=out,
                                        stderr=err)
        # self._sp = subprocess.Popen(exec_string.split(),
        #                             stdout=subprocess.PIPE,
        #                             stderr=subprocess.PIPE)
        
        self._running = True
        self._sp_proxy = Proxy("localhost:{}".format(
                                self.config['zro']['script_rep_port']),
                                timeout=0.5)
        logging.info("Subprocess started. PID: {}".format(self._sp.pid))
        self.publish(self.status)

    def _temp_script(self, script_text, params, temp_script_name=""):
        """ ##TODO: remove overlap with save_script
        """
        if not temp_script_name:
            temp_script_name = datetime.now().strftime('%y%m%d%H%M%S')
        else:
            logging.info("Specific script path requested: {}".format(temp_script_name))

        local_log = "{}/{}".format(LOG, temp_script_name)
        
        make_folder(local_log)
        local_scriptpath = os.path.join(local_log, "{}.py".format(temp_script_name))

        if params:
            local_paramspath = os.path.join(local_log, "{}.json".format(temp_script_name))
            with open(local_paramspath, 'w') as f:
                json.dump(params, f, sort_keys=True, indent=4,
                        separators=(",", ": "))
        else:
            local_paramspath = None
        
        # write script and params to local session folder
        with open(local_scriptpath, 'w') as f:
            f.write(script_text)

        return local_scriptpath, local_paramspath

    def is_running(self):
        """
        Checks to see if a script is running.

        Returns:
            bool: True if script is running.

        """
        if self._sp:
            if self._sp.poll() is None:
                return True
            else:
                if self._running is True:
                    self._running = False
                    self._process_complete()
                return False
        else:
            return False


    def kill_script(self):
        """ Kills the current script.  No data is saved.
        """
        if self._sp:
            try:
                self._sp.kill()
                logging.info("Process {} terminated.".format(self._sp.pid))
            except Exception as e:
                logging.exception("Process termination failed: {}".format(e))
                raise RuntimeError("Failed to terminate script: {}".format(e))
        else:
            logging.warning("Process termination requested but no script is running.")
            raise RuntimeError("No script is running.")

    def stop_script(self):
        """ Ends a stimulus script gracefully.  Session data is saved.
        """
        if self.is_running():
            try:
                self._sp_proxy._finalize()
            except (ZroError, Again):
                logging.warning("Didn't receive response after stop command.")
            #self.publish(self.status)
        else:
            logging.warning("Script stop requested but no script is running.")

    def reward(self, spout=0):
        """ Sends a reward signal to the script.  Will call the "reward" method in
                the running behavior script if it exists.

            If no script is running, do nothing for now.  Should this do anything?

            Might want to handle situations where there is a timeout. 2 seconds
                is a long time and might not want to block that long.
        """
        if self.is_running():
            self._sp_proxy._reward(spout)
        else:
            raise RuntimeError("No script is running")

    def open_reward_line(self, port=1, line=0):
        """ Opens the specified reward line.
        ##TODO: think of a better way to use this.  Maybe ask Chris what his GUI
            would prefer.
        """
        if self.is_running():
            raise RuntimeError("Cannot open reward line while script is running")
        else:
            from toolbox.IO.nidaq import DigitalOutput
            device = self.config['nidaq']['device']
            do_open = self.config['nidaq']['do_open']

            do = DigitalOutput(device, lines=line, port=port)
            do.start()
            do.writeBit(0, do_open)
            do.clear()

    def close_reward_line(self, port=1, line=0):
        """ Closes the specified reward line.
        ##TODO: think of a better way to use this.  Maybe ask Chris what his GUI
            would prefer.
        """
        if self.is_running():
            raise RuntimeError("Cannot close reward line while script is running")
        else:
            from toolbox.IO.nidaq import DigitalOutput
            device = self.config['nidaq']['device']
            do_close = abs(self.config['nidaq']['do_open']-1)

            do = DigitalOutput(device, lines=line, port=port)
            do.start()
            do.writeBit(0, do_close)
            do.clear()

    @property
    def dio_state(self):
        device = self.config['nidaq']['device']
        line_list = self.config['nidaq']["iodaq_port_line_list"]
        do_open = self.config['nidaq']['do_open']
        states = []
        if self.is_running():
            return []
        else:
            try:
                from toolbox.IO.nidaq import DigitalOutput
                for (port, line) in line_list:
                    do = DigitalOutput(device, lines=line, port=port)
                    val = int(do.readLines())
                    if val == do_open:
                        states.append(True)
                    else:
                        states.append(False)
            except Exception as e:
                logging.warning("Failed to check DIO state: {}".format(e))
        return states

    def copy_arbitrary_file(self, source, destination, delete_source=False):
        """
        Copies an arbitrary file.

        Args:
            source (str): source file path
            destination (str): destination file path
            delete_source (bool): if true, removes the original file

        """
        logging.info("Copying: \n {} -> {}".format(source, destination))
        copyfile(source, destination)
        logging.info("... Finished!")
        if delete_source:
            os.remove(source)
            logging.info("SOURCE COPY REMOVED!")

    def get_last_output(self, root_dir):
        """ Gets the most recent output file in the root directory
                including subdirectories.
        """
        pkls = []
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith(".pkl"):
                    pkls.append(os.path.join(root, file))

        latest_file = max(pkls, key=os.path.getctime)
        return latest_file

    def update_package(self):
        """
        If agent.py is being run from a git repository, it will attempt to
            update (run "git pull").  If successful, it will restart itself.
        """
        oldcwd = os.getcwd()
        os.chdir("../..")
        #os.system("git pull")
        ret = subprocess.call("git pull")
        if ret == 0:
            logging.info("Successfully updated camstim repository. Restarting agent.")
            self._rep_sock.send_pyobj(ret) # no json?  can't get to __send_func
            self._rep_sock.close()
            time.sleep(1.0)
            os.chdir(oldcwd)
            os.execv(sys.executable, ["derp", "agent.py"]) # first "arg" is ignored
        else:
            logging.warning("Failed to update camstim repository.")
            os.chdir(oldcwd)

    def git_status(self):
        '''gets some relevent git information'''
        old_cwd = os.getcwd()
        os.chdir("../..")
        try:
            short_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
            date = subprocess.check_output(['git', 'log', '-1', '--format=%cd', '--date=local'])
        except subprocess.CalledProcessError, WindowsError:
            os.chdir(old_cwd)
            return None
        except Exception as e:
            logging.warning("Couldn't acquire git info for uncaught reason: {}".format(e))
            return None
        output = {
            "commit": short_hash.strip("\n"),
            "date": date.strip("\n"),
        }
        os.chdir(old_cwd)
        return output

    def light(self, on=True):
        """ Enables or disables light.
        """
        if on:
            if not self._light_sp:
                path = os.path.join(AGENT_DIR, "agent_lib/light.py")
                exec_str = "python {}".format(path)
                self._light_sp = subprocess.Popen(exec_str)
            else:
                raise RuntimeError("Light already on!")
            self._light = True
        else:
            if self._light_sp:
                self._light_sp.kill()
                self._light_sp = None
            self._light = False

    def flush(self):
        """ Flushes lines.
        What should this do?
        """
        pass

    def _onupdate(self):
        """
        """
        self.is_running()

    def get_log_tail(self, lines=20):
        """ Gets the last lines from the stdout log file for the current
            subprocess.

        args:
            lines (int): number of lines to read

        * A note on this: If your script doesn't call sys.stdout.flush(), then
            it will buffer the file writing, so this function will not give you
            the up-to-date output until the process terminates.
        """
        if self.log_path_out:
            with open(self.log_path_out, "r") as f:
                output_lines = f.readlines()[-lines:]
                return "\n".join(output_lines)
    
    def get_log_err(self):
        """ Gets the fatal error from the stderr file for the current
                subprocess.
        """
        if self.log_path_err:
            with open(self.log_path_err, "r") as f:
                output = f.read()
                return output
        
    def _process_complete(self):
        """ Callback for when script completes.
        """
        logging.info("Process {} completed. Return code: {}".format(
            self._sp.pid, self.returncode))

        self.publish(self.status)

        # if there was an error
        if self.returncode != 0:
            self._error_email()

    def _error_email(self):
        """ Gets email configuration and sends an error email if properly
                configured.
        """
        user = self.config["email"]["user_name"]
        password = self.config['email']['password']
        mail_type = self.config['email'].get('type', "aibs")
        if mail_type == "aibs":
            send_mail = send_mail_aibs
        else:
            send_mail = send_mail_gmail
        if user == "":
            return
        recipients = self.config['email']['error']
        rig_id = self.config.get("rig_id", "")
        subject = "Script Error on rig {}".format(rig_id)
        error_msg = self.get_log_err()
        
        if not "Traceback" in error_msg:
            return # no traceback

        body = "\nRig: {}\nUser: {}\nMouse: {}\nError:\n{}".format(rig_id,
                                                                   self.params.get('user_id', None),
                                                                   self.params.get('mouse_id', None),
                                                                   error_msg)
        try:
            send_mail(user, password, recipients, subject, body)
        except Exception as e:
            logging.exception("Failed to send error email: {}".format(e))


def send_mail_aibs(user,
                   password,
                   recipients,
                   subject,
                   body,
                   files=[],
                   ):
    from toolbox.misc.mail import AIBSMailer
    aibs_mailer = AIBSMailer(user, password)
    aibs_mailer.send_message(recipients, subject, body, files)

def send_mail_gmail(user,
                    password,
                    recipients,
                    subject,
                    body,
                    files=[]):
    """ Oh god the Gmail API got complicated.  We're going to put this on the
            back-burner for now.
    """
    raise(NotImplementedError("Haven't set up gmail error messages yet."))


def main():
    #add a log file handler to logging so we can check agent activity
    log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    rootlogger = logging.getLogger()
    rootlogger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    rootlogger.addHandler(console_handler)

    #add a log file handler to logging
    dtstring = datetime.now().strftime('%y%m%d%H%M%S')

    log_file_name = os.path.join(AGENTLOG, dtstring)+".log"
    file_handler = logging.FileHandler(log_file_name)
    file_handler.setFormatter(log_formatter)
    rootlogger.addHandler(file_handler)

    logging.info("Log started @ {}".format(log_file_name))

    agent = Agent()
    agent.run_forever()


if __name__ == '__main__':
    main()

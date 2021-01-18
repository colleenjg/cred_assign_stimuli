Introduction
============
Works with psyschopy, a spectrometer and colorimeter to adjust a
monitors gamma calibration. The end-goal being a monitor calibration for
psychopy that gives linear response across grayscale and a final
Luminance value of 50 cd / m^2 when a psychopy (0, 0, 0) window is
displayed.

Theory/history
------------------
The original intent here was to measure the screens output across a
grayscale, then adjust it so that the monitors un-weighted luminosity is
a straight line.

A spectrometer would be placed against the screen and the
[GammaWindow](GammaWindow.py)
module had code that would check three colors (red, green, blue).

These values were used to generate to adjust the monitors gamma to
linearize the output of the monitor across the grey scale. This
correction seemed to be inconsistently applied; sometimes the gamma
correction just did nothing.

This measure & correct gamma sequence was done at every `10` brightness
level from 0-100.

After this iterative gamma correction step, a colorimeter was used to
measure the luminance of the monitor. For this measurement a default
gray psychopy window would be displayed. Then monitors brightness would
be adjusted using the OSD until it was close to the target candela
value.

Finally, the stim config was updated to load the monitor configuration
with gamma correction most closely matching the brightness setting.

Current Implementation
----------------------
The current implementation uses a binary search to automatically determine
the the opitimal monitor brightness setting to achieve the target
50 cd / m^2 at psychopy (0, 0, 0).

At the conclusion of the run (which takes about 4 minutes) it will display the 
candela values at the extremes and midpoint and the optimal monitor calibration name.

```
TARGET CANDELA: 50, colors: [(-1.0, -1.0, -1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)], 
    actual cd/m**2: [0.22451899999999997, 50.204001999999996, 115.59921199999999]
BEST monitor calibration = GammaCorrect59
```

Gamma
-----
There isn't any tolerance specified for the _straightness_ of this
response.

Luminance
---------
For the measurement target of 50 cd/m^2, _Luminance_ is a property
defined by the [CIE 1931 color space][1].  Using the CIE space, the `Y`
parameter is luminance.

The reason for this is we target is based on the output of a ColorCal,
which reports its value in CIE space.

There isn't any tolerance specified for the _Luminance_ value.

Colors
------
The grayscale was generated using a series of psychopy windows with
colors beginning at (-1, -1, -1) and incrementing by 0.1 up to (1, 1,
1).


Hardware
========
Spectrometer
------------
The predicate device was an Ocean Optics [Red Tide][2] spectrometer
which is intended only for student use. It is pretty cheap and can't be
really calibrated.

AIBS-MPE has now purchased the [Flame][3] spectrometer, with radiometric
calibration and it should be used going forward.

This change required some tweaks to the code grabbing RGB values from
the spectrometer. See [81fc66b][4].

Having a calibrated spectrometer means it would be possible to remove
the colorimeter adjustment later, but it's going to be a lot of work.
And we already have these colorimeters, so might as well use them.

Colorimeter
-----------
The [CRS ColorCal][5] was chosen because it was radiometrically
calibrated, relatively inexpensive and had been in service as a
predicate device by some AIBS researchers.

The fact that it reports CIE Luminance is more a hindrance than benefit,
but the value of '50 cd/m^2' was arrived at, I'm told, by someone using
a _SpectroCal_ device to calibrate a monitor and then checked with the
ColorCal. The SpectroCal which can report luminosity without traditional
weighting for human-eye (e.g. _luminance_).

Misc
----
* USB mouse+keyboard
* USB extension cables (6 ft.)
* Flashlight (if working in a dark room)


Dependencies
============
* python 2.7.x
* psychopy
* python-seabreeze
* cseabreeze
  - _Soon_ we'll want to move to pyseabreeze/pyUSB to support Red Tide
    also
* pyglet
* avbin
* ColorCal [driver][6]
* pyserial 2.7


Installation
============

VNC can be used for installing software on the mouse-computers, but NOT while running the
gamma calibration (it will crash).  Pull up the instructions from the README.md file at
http://stash.corp.alleninstitute.org/projects/ENG/repos/camstim/browse/camstim/gamma

Get up-to-date software on the mouse-computer:

Start with a sane terminal, then update from GIT:

```
\\aibsfileprint\public\martins\cmder_mini\Cmder.exe
```
On Behavior Rig F:
```
cd C:\Users\Public\Desktop\pythondev\camstim
```

On Cam2P3,4, and 5:
```
cd \Users\svc_flex4\Desktop\cam\camstim
```

```
git fetch
git pull
python setup.py 
```

Install USB device drivers
--------------------------

### ColorCal x64 driver: 

Right-click on
```
 \\aibsdata\mpe\Software\Products\GammaCalibration\ColorCAL MKII USB CDC\crsltd_usb_cdc_acm.inf 
```
and select Install



### Spectrometer:

Run installer
```
 \\aibsdata\mpe\Software\Products\GammaCalibration\seabreeze-3.0.11-Setup64.msi 
```

In the terminal,
```
 pip install \\aibsdata\mpe\Software\Products\GammaCalibration\seabreeze-0.5.3-cp27-cp27m-win_amd64.whl
```

If that fails, then follow the instructions for updating pip, which are:
```
 python -m pip install --upgrade pip
```
and redo the _.whl_ installation.

Plug-in the USB devices, and wait for them to be detected by Windows. 

The Ocean Optics Flame-S driver is usually not found. Install it by specifying the correct directory 
in the Device Manager window: 
  C:\Program Files\Ocean Optics

In the terminal, test if the devices are detected:
```
 cd C:\Users\Public\Desktop\pythondev\camstim\camstim\gamma
 python calibrate.py devices
```

You will probably get an error _No module named serial_. Install that with 
```
 pip install "pyserial>=2.0,<2.99"
```
and retest to detect the devices. There will be lots of warnings and errors.Look for the Spectrophotometer and the ColorCal  being recognized. Then, you are ready for calibration. 

Disconnect the VNC client and connect a mouse&keyboard. If SetDeviceGammaRamp fails, then double check that VNC is down, and restart if still not working.



Use
===
- Reset the monitor (which must be an ASUS PA 248). Color curve and contrast must be at default setting.
- Position ColorCal on the monitor (touching)
- Position the spectrometer on the monitor (touching)
- Darken the room, or use a blackout curtain over the ColorCal and spectrophotometer (doesn't seem to
have much of an effect either way)
- Run the camstim.gamma.calibrate module with a python interpreter

    ```
    python calibrate.py calibrate
        is equivalent to:
    python calibrate.py calibrate 50 0
    ```
    ```
    arg[1] is either "calibrate" : perform full calibration (default), or
                     "luminance" - get current luminance setting at (0,0,0)
                     "devices" - show list of calibration devices installed
    arg[2] is target candela / m**2 (defaults to 50 if not provided)
    arg[3] is the screen to use in Psychopy (0, 1, ...)
    ```

- calibrate.py will run a binary search for a linear output over the (-1, 1)
range of PsychoPy stimulus values by adjusting the monitor brightness setting
while searching for the target candela value at a stimulus of (0,0,0)
- Check graphs for sanity in %USER%\Desktop\gamma_correction

- If you receive an error regarding not being able to get contrast or brightness, 
it's likely you've selected the wrong screen in arg[3]. This happens when the built-in ASPEED graphics adapter is ON.
Turn it OFF by going to:
```
 Control Panels/Display/Screen Resolution
 Select "Adjust Resolution"
 Under: Multiple Displays: Show desktop only on 2 (or whichever # is the big screen)
```

The configuration is stored in %APPDATA%\psycophy. That path is
specified by: `psycophy.monitors.calibTools.monitorFolder`. The correct monitor brightness is stored independently in the Desktop/gamma_calibration  directory within a dated folder.

Check if there’s a config file in C:\\camstim\config\ , if not generate a config file by running
```
 cd ../scripts
 python movie_stim.py
```

Press ESC after the movie runs for a few seconds.

Then update the brightness setting in /camstim/config/stim.cfg

If the program complains about some array.gl not found, then 
```
 pip install pyopengl
```


Examples
--------
un-corrected and corrected measurement are in doc/images
directory:
![uncorrected monitor](/doc/images/testMonitor.jpg?raw=true)

![corrected monitor](/doc/images/correctedMonitor.jpg?raw=true)

These plot the sum of RGB values as measured by spectrometer.

Bugs
====
MS:  This bug seems to have been fixed by Jay:  1. The testMonitor gamma ramp is not always set correctly.  This is under investigation
but doesn't seem to adversely affect the resulting gamma created.

References
==========
[1]: https://en.wikipedia.org/wiki/CIE_1931_color_space
[2]: http://oceanoptics.com/product/usb-650-red-tide-spectrometers/
[3]: http://oceanoptics.com/product/flame-spectrometer/
[4]: http://stash.corp.alleninstitute.org/projects/ENG/repos/camstim/commits/81fc66b5370ef4d0a08ee5a327cbcd8ba50b20e0
[5]: http://www.crsltd.com/tools-for-vision-science/light-measurement-display-calibation/colorcal-mkii-colorimeter/
[6]: http://www.crsltd.com/assets/Support/M0030-ColorCAL-MKII/ColorCAL-MKII-USB-CDC.zip
[7]: http://www.lagom.nl/lcd-test/gamma_calibration.php 
[8]: https://sourceforge.net/projects/seabreeze/


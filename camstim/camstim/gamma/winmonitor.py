import ctypes
import logging
import win32api


#logging.console.setLevel(logging.CRITICAL)

class _WinMonitor(ctypes.Structure):
    """Physical monitor structure from Windows API.

    hPhysicalMonitor : handle to physical monitor.
    zPhysicalMonitorDescription : Unicode descriptive string. It seems to always
                                  be empty.
    """
    _fields_ = [("hPhysicalMonitor", ctypes.c_int),
            ("zPhysicalMonitorDescription", (ctypes.c_wchar) * 128)]


class WinMonitor(object):
    """Control physical monitors.

    Lots of windows calls via ctypes to get & set monitor properties.

    screen_number: indexed from zero, same values as psychopy
    """
    def __init__(self, screen_number=1):
        self._iscr = screen_number
        self._winmon = _WinMonitor()
        self._init_lib_functions()

        # Flag saves some lib calls later.  An update to the instance's monitor
        # handle can be made by a call to `get_monitor` later.
        self._handle_init = False

        # Monitor property values.
        self._v_min = None
        self._v_cur = None
        self._v_max = None

    def __dll_fetcher(self, dllname):
        """Helper to shorten dll setups later in this class.
        """
        return ctypes.cdll.LoadLibrary(ctypes.util.find_library(dllname))

    def _init_lib_functions(self):
        """Shortcuts to windows API and dll calls, makes syntactic sugar.

        Could probably skip most of these but I don't see good documenation on
        when to/not use argtypes. So, explicit is better than implicit.
        """
        self._d2 = self.__dll_fetcher("dxva2.dll")
        self._u32 = self.__dll_fetcher("user32.dll")
        self._k32 = self.__dll_fetcher("kernel32.dll")

        # GetNumber...(monitor handle, *number of monitors)
        self._count_monitors = self._d2.GetNumberOfPhysicalMonitorsFromHMONITOR
        self._count_monitors.argtype = [ctypes.c_int,
                                        ctypes.c_int,]
        self._count_monitors.restype = ctypes.c_int

        # GetPhysicalMon...(monitor handle, array size, *array of monitors)
        self._get_monitor = self._d2.GetPhysicalMonitorsFromHMONITOR
        self._get_monitor.argtype = [ctypes.c_int,
                                     ctypes.c_int,
                                     ctypes.POINTER(_WinMonitor),]
        self._get_monitor.restype = ctypes.c_int

        # Get..Brightness(monitor handle, *min brightness, *current, *max)
        self._get_brightness = self._d2.GetMonitorBrightness
        self._get_brightness.argtype = [ctypes.c_int,
                                        ctypes.c_int,
                                        ctypes.c_int,
                                        ctypes.c_int,]
        self._get_brightness.restype = ctypes.c_int

        # Set..Brightness(monitor handle, brightness)
        self._set_brightness = self._d2.SetMonitorBrightness
        self._set_brightness.argtype = [ctypes.c_int,
                                        ctypes.c_int,]
        self._set_brightness.restype = ctypes.c_int

        # Get..Contrast(monitor handle, *min contrast, *current, *max)
        self._get_contrast = self._d2.GetMonitorContrast
        self._get_contrast.argtype = [ctypes.c_int,
                                      ctypes.c_int,
                                      ctypes.c_int,
                                      ctypes.c_int,]
        self._get_contrast.restype = ctypes.c_int

        # Set..Contrast(monitor handle, contrast)
        self._set_contrast = self._d2.SetMonitorContrast
        self._set_contrast.argtype = [ctypes.c_int,
                                      ctypes.c_int,]
        self._set_contrast.restype = ctypes.c_int


    def _brightness_update(self):
        self._v_min = ctypes.c_int()
        self._v_cur = ctypes.c_int()
        self._v_max = ctypes.c_int()
        s = self._get_brightness(self.physical_handle,
                                 ctypes.byref(self._v_min),
                                 ctypes.byref(self._v_cur),
                                 ctypes.byref(self._v_max))
        if s != 1:
            raise Exception("Error getting brightness: errno = {0}".format(s))

    def _contrast_update(self):
        self._v_min = ctypes.c_int()
        self._v_cur = ctypes.c_int()
        self._v_max = ctypes.c_int()
        s = self._get_contrast(self.physical_handle,
                               ctypes.byref(self._v_min),
                               ctypes.byref(self._v_cur),
                               ctypes.byref(self._v_max))
        if s != 1:
            raise Exception("Error getting contrast: errno = {0}".format(s))

    @property
    def brightness(self):
        """Current brightness value.
        """
        self._brightness_update()
        return self._v_cur.value

    @brightness.setter
    def brightness(self, brightness):
        # Letting an out-of-bounds value get passed really screwed up my
        # monitor
        # for a while and all calls to setBrightness failed.
        if brightness < self.brightness_min or brightness > self.brightness_max:
            emsg = "Brightness value = {0} is out of bounds ({1},{2})."
            raise ValueError(emsg.format(brightness,
                                         self.brightness_min,
                                         self.brightness_max))

        s = self._set_brightness(self.physical_handle,
                                 ctypes.c_int(brightness))
        if s != 1:
            raise Exception("Error setting brightness: error = {0}".format(s))

    @property
    def brightness_min(self):
        self._brightness_update()
        return self._v_min.value

    @property
    def brightness_max(self):
        self._brightness_update()
        return self._v_max.value

    @property
    def contrast(self):
        """Current contrast value.
        """
        self._contrast_update()
        return self._v_cur.value

    @contrast.setter
    def contrast(self, contrast):
        if contrast < self.contrast_min or contrast > self.contrast_max:
            emsg = "Contrast value = {0} is out of bounds ({1},{2})."
            raise ValueError(emsg.format(contrast,
                                         self.contrast_min,
                                         self.contrast_max))

        s = self._set_contrast(self.physical_handle,
                                 ctypes.c_int(contrast))
        if s != 1:
            raise Exception("Error setting contrast: error = {0}".format(s))

    @property
    def contrast_min(self):
        self._contrast_update()
        return self._v_min.value

    @property
    def contrast_max(self):
        self._contrast_update()
        return self._v_max.value

    def count_monitors(self, sw_handle=None):
        num_monitors = ctypes.c_int()
        if sw_handle == None:
            sw_handle = self.sw_handle
        s = self._count_monitors(sw_handle,
                                 ctypes.byref(num_monitors))
        if s != 1:
            raise Exception("oh snap, cant count the monitors.")

        return num_monitors.value

    def get_monitor(self, sw_handle=None):
        """Sets instances hardware monitor based on sw_handle.
        """
        if sw_handle == None:
            sw_handle = self.sw_handle
        s = self._get_monitor(sw_handle,
                              ctypes.c_int(self.count_monitors()),
                              ctypes.byref(self._winmon))
        if s != 1:
            raise Exception("problem getting physical monitor.")

        return self._winmon

    @property
    def physical_handle(self):
        if self._handle_init != True:
            self.get_monitor()
            self._handle_init = True

        return self._winmon.hPhysicalMonitor

    @property
    def sw_handle(self):
        ''' 0 referenced, like psychopy '''
        monitor_list = win32api.EnumDisplayMonitors()
        return int(monitor_list[self._iscr][0])

    @property
    def width(self):
        # DW: how to select a monitor?  This seems to only work for the
        # primary monitor
        width = win32api.GetSystemMetrics(0)
        if width:
            return width
        else:
            raise WindowsError("Failed to get monitor width.")

    @property
    def height(self):
        # DW: how to select a monitor?  This seems to only work for the
        # primary monitor
        height = win32api.GetSystemMetrics(1)
        if height:
            return height
        else:
            raise WindowsError("Failed to get monitor height.")
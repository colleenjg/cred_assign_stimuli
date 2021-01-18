"""
Tests control of monitor settings.
"""
import unittest
import sys
from camstim.gamma.calibrate import WinMonitor

class TestMonitor(unittest.TestCase):
    def test_properties(self):
        """
        Tests property setting/getting.
        """
        mon = WinMonitor(0)
        b_cur = mon.brightness
        b_min = mon.brightness_min
        b_max = mon.brightness_max
        c_cur = mon.contrast
        c_min = mon.contrast_min
        c_max = mon.contrast_max

        #try setting to min/max
        mon.brightness = b_min
        mon.brightness = b_max
        mon.contrast = c_min
        mon.contrast = c_max

        # return to original settings
        mon.contrast = c_cur
        mon.brightness = b_cur

        # settting outside of range should throw valueerror
        with self.assertRaises(ValueError):
            mon.brightness = b_min - 1

        with self.assertRaises(ValueError):
            mon.brightness = b_max + 1

        # check to ensure that we can get width, height
        w, h = mon.width, mon.height

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMonitor)
    unittest.TextTestRunner(verbosity=2).run(suite)

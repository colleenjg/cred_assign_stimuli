"""

@author: derricw

Displays a full screen light.

"""

from psychopy import visual, event, core

win = visual.Window(screen=0,fullscr=True,color=(1,1,1))

while 1:
    win.flip()
    for keys in event.getKeys(timeStamped=True):
        if keys[0]in ['escape','q']:
            win.close()
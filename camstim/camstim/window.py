#!/usr/bin/env python2
'''Subclass of standard PsychoPy Window to perform warping and RGB60 -> Mono180 Hz'''

import sys
import os

# Ensure setting pyglet.options['debug_gl'] to False is done prior to any
# other calls to pyglet or pyglet submodules, otherwise it may not get picked
# up by the pyglet GL engine and have no effect.
# Shaders will work but require OpenGL2.0 drivers AND PyOpenGL3.0+
import pyglet
pyglet.options['debug_gl'] = False
GL = pyglet.gl
import ctypes

#try to find avbin (we'll overload pyglet's load_library tool and then add some paths)
import pyglet.lib
# jayb import _pygletLibOverload
# jayb pyglet.lib.load_library = _pygletLibOverload.load_library
#on windows try to load avbin now (other libs can interfere)
if sys.platform == 'win32':
    #make sure we also check in SysWOW64 if on 64-bit windows
    if 'C:\\Windows\\SysWOW64' not in os.environ['PATH']:
        os.environ['PATH'] += ';C:\\Windows\\SysWOW64'

    try:
        from pyglet.media import avbin
        haveAvbin = True
    except ImportError:
        # either avbin isn't installed or scipy.stats has been imported
        # (prevents avbin loading)
        haveAvbin = False

import psychopy  # so we can get the __path__
from psychopy import core, platform_specific, logging, prefs, monitors, event
import psychopy.event

# tools must only be imported *after* event or MovieStim breaks on win32
# (JWP has no idea why!)
#jayb from psychopy.tools.arraytools import val2array
#jayb from psychopy import makeMovies
#jayb from psychopy.visual.text import TextStim
#jayb from psychopy.visual.grating import GratingStim
#jayb from psychopy.visual.helpers import setColor

try:
    from PIL import Image
except ImportError:
    import Image

if sys.platform == 'win32' and not haveAvbin:
    logging.error("""avbin.dll failed to load.
                     Try importing psychopy.visual as the first library
                     (before anything that uses scipy)
                     and make sure that avbin is installed.""")

from psychopy.core import rush

global currWindow
currWindow = None
reportNDroppedFrames = 5  # stop raising warning after this

from psychopy.gamma import getGammaRamp, setGammaRamp, setGamma
#import pyglet.gl, pyglet.window, pyglet.image, pyglet.font, pyglet.event
import psychopy._shadersPyglet as _shaders
try:
    from pyglet import media
    havePygletMedia = True
except:
    havePygletMedia = False

try:
    import pygame
except:
    pass

global DEBUG
DEBUG = False

global IOHUB_ACTIVE
IOHUB_ACTIVE = False

#keep track of windows that have been opened
openWindows = []

# can provide a default window for mouse
psychopy.event.visualOpenWindows = openWindows

#jayb
import numpy as np
from OpenGL.arrays import ArrayDatatype as ADT
from psychopy import visual, monitors
import ConfigParser

# DW Set up default monitor
test_mon = monitors.Monitor("testMonitor")
if not test_mon.getSizePix():
    test_mon.setSizePix((1920, 1200))
    test_mon.setWidth(51)
    test_mon.setDistance(50)
    test_mon.saveMon()


class Projector (tuple):
    Normal = 0
    DLP180Hz = 1

class Warp(tuple):
    Disabled = 0
    Spherical = 1
    Cylindrical = 2
    Curvilinear = 3
    Warpfile = 4

    # this is so ugly, how to do Enums prior to Python3?
    @staticmethod
    def asString (warp):  
         if warp == Warp.Disabled: return 'Disabled'
         if warp == Warp.Spherical: return 'Spherical'
         if warp == Warp.Cylindrical: return 'Cylindrical'
         if warp == Warp.Curvilinear: return 'Curvilinear'
         if warp == Warp.Warpfile: return 'Warpfile'
         return 'Invalid warp value'

class Window(visual.Window):
    '''
    Subclass of Window to handle multiple frame packing and warping.

    Parameters
    ----------

    projectorType: can be any of the following:
        Projector.Normal -no frame packing, use this for LCD displays (default)
        Projector.DLP180Hz - pack 3 (grayscale) images into one RGB output frame.
            This allows structured light projectors to produce 180Hz monochrome stimulus from 60Hz display cards.

    warp: defines the warping projection to be applied. Values can be:
        Warp.Disabled - no correction, same as default PsychoPy projection
        Warp.Spherical - correct using spherical projection (aka "Radial" or "Equirectangular)
        Warp.Cylindrical - correct using cylindrical projection
        Warp.Curvilinear - correct using curvilinear projection. This is spatially less accurate than Spherical or Cylindrical.
        Warp.Warpfile - use the warp file provided in the warpfile argument.  
            'eyepoint' is ignored in this mode.

    warpfile: defines the file to use when warp == Warp.Warpfile

    warpGridsize: defines the x and y dimensions of the warp grid

    eyepoint: position of the eye in normalized coordinates
        (0,0) is lower left, (1,1) is upper right, (0.5, 0.5) is the center (default)

    flipHorizontal: if True, flip the entire warp horizontally.  
        This is useful for rear screen projectors.  Default is false.

    flipVertical: if True, flip the entire warp vertically.
        Default is false.
    '''

    def __init__(self, projectorType=Projector.Normal, warp=Warp.Disabled, warpfile = None, warpGridsize = 300, eyepoint=(0.5, 0.5), 
                flipHorizontal=False, flipVertical=False, *args,**kwargs):
        self.projectorType = projectorType
        self.warp = warp
        self.warpfile = warpfile
        self._eyepoint = eyepoint
        self.flipHorizontal = flipHorizontal
        self.flipVertical = flipVertical
        self.flipCounter = 0
        self.aspect = 1
        self.isPsychoPyV180OrAbove = (psychopy.__version__ >= '1.80')
        self.warpGridsize = warpGridsize
        self.initDefaultWarpSize()
        self.bitsMode = None

        self.flipEvery3rdFrame = False
        if self.projectorType == Projector.DLP180Hz:
            self.flipEvery3rdFrame = True
            #self._monitorFrameRate = None

        # if 'checkTiming' is True, 
        # then flip will be called before window creation,
        # so we must initialize the projection prematurely
        self.projectionNone()   
        
        if self.isPsychoPyV180OrAbove:
            visual.Window.__init__(self, useFBO=True,*args,**kwargs)
        else:
            visual.Window.__init__(self, *args,**kwargs)

        # if packing 3 images into one HDMI frame...
        if self.projectorType == Projector.DLP180Hz:
            self._refreshThreshold = 1.2 / 180
            GL.glColorMask(False, False, True, True)
            
        # if warping the output
        #   get the eye distance from the monitor object,
        #   but the pixel dimensions from the actual window object
        w, h = self.size
        self.aspect = float(w) / h
        self.dist_cm = self.monitor.getDistance()
        if self.dist_cm is None:
            # create a fake monitor if one isn't defined
            self.dist_cm = 30.0
            self.mon_width_cm = 50.0
            logging.warning('Monitor is not calibrated')
        else:
            self.mon_width_cm = self.monitor.getWidth()

        self.mon_height_cm = self.mon_width_cm / self.aspect
        self.mon_width_pix = w 
        self.mon_height_pix = h

        self.setupProjection(warp, warpfile, eyepoint)
        self._setupMouse()

    def _setupMouse(self):
        self.winHandle.set_exclusive_mouse()
        self.winHandle.set_exclusive_keyboard()
        self.winHandle.set_mouse_visible(False)
        try:
            import win32api
            win32api.SetCursorPos((self.size[0], self.size[1]))
        except Exception as e:
            logging.warning("Failed to move cursor: {}".format(e))

    def _getActualFrameRate(self, nMaxFrames=100, nWarmUpFrames=10, threshold=1):
        if self.projectorType == Projector.DLP180Hz:
            return None
        else:
            return visual.Window._getActualFrameRate(self, nMaxFrames, nWarmUpFrames, threshold)

    def _setupPyglet(self):
        self.useFBO = True
        visual.Window._setupPyglet(self)
    
    def initDefaultWarpSize(self):
        self.xgrid = self.warpGridsize
        self.ygrid = self.warpGridsize


    def setupProjection (self, warp, warpfile, eyepoint):
        self.warp = warp
        self.warpfile = warpfile
        self._eyepoint = eyepoint

        # warpfile might have changed the size...
        self.initDefaultWarpSize()  

        if (self.warp == Warp.Disabled):
            self.projectionNone()
        elif (self.warp == Warp.Spherical):
            self.projectionSphericalOrCylindrical(False)
        elif self.warp == Warp.Cylindrical:
            self.projectionSphericalOrCylindrical(True)
        elif self.warp == Warp.Curvilinear:
            self.projectionCurvilinear()
        elif self.warp == Warp.Warpfile:
            self.projectionWarpfile()

    def projectionNone(self):
        '''
        No correction, same projection as original PsychoPy
        '''
        # Vertex data 
        v0 = ( -1.0, -1.0)
        v1 = ( -1.0,  1.0)
        v2 = (  1.0,  1.0)
        v3 = (  1.0, -1.0)
        
        # Texture coordinates
        t0 = ( 0.0, 0.0)
        t1 = ( 0.0, 1.0)
        t2 = ( 1.0, 1.0)
        t3 = ( 1.0, 0.0)
        
        vertices = np.array( [ v0, v1, v2, v3 ], 'float32' )
        tcoords = np.array( [ t0, t1, t2, t3 ], 'float32' )

        #draw four quads during rendering loop
        self.nverts = 4  
        self.createVertexAndTextureBuffers (vertices, tcoords)        

    def projectionSphericalOrCylindrical(self, isCylindrical=False):
        '''
        Correct perspective on flat screen using either a spherical or cylindrical projection.
        '''
        self.nverts = (self.xgrid-1)*(self.ygrid-1)*4

        # eye position in cm
        xEye = self._eyepoint[0] * self.mon_width_cm
        yEye = self._eyepoint[1] * self.mon_height_cm

        #create vertex grid array, and texture coords
        #times 4 for quads
        vertices = np.zeros(((self.xgrid-1)*(self.ygrid-1)*4, 2),dtype='float32')
        tcoords = np.zeros(((self.xgrid-1)*(self.ygrid-1)*4, 2),dtype='float32')

        equalDistanceX = np.linspace(0, self.mon_width_cm, self.xgrid)
        equalDistanceY = np.linspace(0, self.mon_height_cm, self.ygrid)

        # vertex coordinates        
        x_c = np.linspace(-1.0,1.0,self.xgrid)
        y_c = np.linspace(-1.0,1.0,self.ygrid)
        x_coords, y_coords = np.meshgrid(x_c,y_c)

        x = np.zeros(((self.xgrid), (self.ygrid)),dtype='float32')
        y = np.zeros(((self.xgrid), (self.ygrid)),dtype='float32')

        x[:,:] = equalDistanceX - xEye
        y[:,:] = equalDistanceY - yEye
        y = np.transpose(y)

        r = np.sqrt(np.square(x) + np.square(y) + np.square(self.dist_cm))

        azimuth = np.arctan(x / self.dist_cm)
        altitude = np.arcsin(y / r)

        # calculate the texture coordinates
        if isCylindrical:
            tx = self.dist_cm * np.sin(azimuth)
            ty = self.dist_cm * np.sin(altitude)
        else:
            tx = self.dist_cm * (1 + x / r)- self.dist_cm
            ty = self.dist_cm * (1 + y / r) - self.dist_cm

        # prevent div0
        azimuth[azimuth==0] = np.finfo(np.float32).eps
        altitude[altitude==0] = np.finfo(np.float32).eps

        # the texture coordinates (which are now lying on the sphere)
        # need to be remapped back onto the plane of the display.
        # This effectively stretches the coordinates away from the eyepoint.
   
        if isCylindrical:
            tx = tx * azimuth / np.sin(azimuth) 
            ty = ty * altitude / np.sin(altitude)
        else:
            centralAngle = np.arccos (np.cos(altitude) * np.cos(np.abs(azimuth)))
            # distance from eyepoint to texture vertex
            arcLength = centralAngle * self.dist_cm
            # remap the texture coordinate
            theta = np.arctan2(ty, tx)
            tx = arcLength * np.cos(theta)
            ty = arcLength * np.sin(theta)

        u_coords = tx / self.mon_width_cm + 0.5
        v_coords = ty / self.mon_height_cm + 0.5

        #loop to create quads
        vdex = 0
        for y in xrange(0,self.ygrid-1):
            for x in xrange(0,self.xgrid-1):
                index = y*(self.xgrid) + x
                
                vertices[vdex+0,0] = x_coords[y,x]
                vertices[vdex+0,1] = y_coords[y,x]
                vertices[vdex+1,0] = x_coords[y,x+1]
                vertices[vdex+1,1] = y_coords[y,x+1]
                vertices[vdex+2,0] = x_coords[y+1,x+1]
                vertices[vdex+2,1] = y_coords[y+1,x+1]
                vertices[vdex+3,0] = x_coords[y+1,x]
                vertices[vdex+3,1] = y_coords[y+1,x]
                
                tcoords[vdex+0,0] = u_coords[y,x]
                tcoords[vdex+0,1] = v_coords[y,x]
                tcoords[vdex+1,0] = u_coords[y,x+1]
                tcoords[vdex+1,1] = v_coords[y,x+1]
                tcoords[vdex+2,0] = u_coords[y+1,x+1]
                tcoords[vdex+2,1] = v_coords[y+1,x+1]
                tcoords[vdex+3,0] = u_coords[y+1,x]
                tcoords[vdex+3,1] = v_coords[y+1,x]
                
                vdex += 4
        self.createVertexAndTextureBuffers (vertices, tcoords)        

        
    def projectionCurvilinear (self):
        '''
        Correct perspective on flat screen using curvilinear projection.
        http://en.wikipedia.org/wiki/Curvilinear_perspective 
        '''
        self.nverts = (self.xgrid-1)*(self.ygrid-1)*4

        # eye position in cm
        xEye = self._eyepoint[0] * self.mon_width_cm
        yEye = self._eyepoint[1] * self.mon_height_cm

        # create vertex grid array, and texture coords times 4 for quads
        vertices = np.zeros(((self.xgrid-1)*(self.ygrid-1)*4, 2),dtype='float32')
        tcoords = np.zeros(((self.xgrid-1)*(self.ygrid-1)*4, 2),dtype='float32')
        
        # vertex points are spaced equal distances apart
        equalDistanceX = np.linspace(0, self.mon_width_cm, self.xgrid)
        equalDistanceY = np.linspace(0, self.mon_height_cm, self.ygrid)

        # vertex coordinates        
        x_c = np.linspace(-1.0,1.0,self.xgrid)
        y_c = np.linspace(-1.0,1.0,self.ygrid)
        x_coords, y_coords = np.meshgrid(x_c,y_c)

        x = np.zeros(((self.xgrid), (self.ygrid)),dtype='float32')
        y = np.zeros(((self.xgrid), (self.ygrid)),dtype='float32')

        x[:,:] = equalDistanceX - xEye 
        y[:,:] = equalDistanceY - yEye 
        y = np.transpose(y)

        r = np.sqrt(np.square(x) + np.square(y) + np.square(self.dist_cm))
        azimuth = np.arctan(x / self.dist_cm)
        altitude = np.arcsin(y / r)

        tx = self.dist_cm * (1 + x / r)- self.dist_cm
        ty = self.dist_cm * (1 + y / r) - self.dist_cm
        
        # prevent div0
        azimuth[azimuth==0] = np.finfo(np.float32).eps
        altitude[altitude==0] = np.finfo(np.float32).eps

        # map texture onto the x, y plane
        tx = tx * azimuth / np.sin(azimuth) 
        ty = ty * altitude / np.sin(altitude)

        u_coords = tx / self.mon_width_cm + 0.5
        v_coords = ty / self.mon_height_cm + 0.5

        #loop to create quads
        vdex = 0
        for y in xrange(0,self.ygrid-1):
            for x in xrange(0,self.xgrid-1):
                index = y*(self.xgrid) + x
                
                vertices[vdex+0,0] = x_coords[y,x]
                vertices[vdex+0,1] = y_coords[y,x]
                vertices[vdex+1,0] = x_coords[y,x+1]
                vertices[vdex+1,1] = y_coords[y,x+1]
                vertices[vdex+2,0] = x_coords[y+1,x+1]
                vertices[vdex+2,1] = y_coords[y+1,x+1]
                vertices[vdex+3,0] = x_coords[y+1,x]
                vertices[vdex+3,1] = y_coords[y+1,x]
                
                tcoords[vdex+0,0] = u_coords[y,x]
                tcoords[vdex+0,1] = v_coords[y,x]
                tcoords[vdex+1,0] = u_coords[y,x+1]
                tcoords[vdex+1,1] = v_coords[y,x+1]
                tcoords[vdex+2,0] = u_coords[y+1,x+1]
                tcoords[vdex+2,1] = v_coords[y+1,x+1]
                tcoords[vdex+3,0] = u_coords[y+1,x]
                tcoords[vdex+3,1] = v_coords[y+1,x]
                
                vdex += 4

        self.createVertexAndTextureBuffers (vertices, tcoords)        
        

    def projectionWarpfile (self):
        ''' Use a warp definition file to create the projection.
            See: http://paulbourke.net/dome/warpingfisheye/ 
        '''
        try:
            fh = open (self.warpfile)
            lines = fh.readlines()
            fh.close()
            filetype = int(lines[0])
            rc = map(int, lines[1].split())
            cols, rows = rc[0], rc[1]
            warpdata = np.loadtxt(self.warpfile, skiprows=2)
        except:
            error = 'Unable to read warpfile: ' + self.warpfile
            logging.warning(error)
            print error
            return

        if (cols * rows != warpdata.shape[0] or warpdata.shape[1] != 5 or filetype != 2 ):
            error = 'warpfile data incorrect: ' + self.warpfile
            logging.warning(error)
            print error
            return

        self.xgrid = cols
        self.ygrid = rows
          
        self.nverts = (self.xgrid-1)*(self.ygrid-1)*4

        # create vertex grid array, and texture coords times 4 for quads
        vertices = np.zeros(((self.xgrid-1)*(self.ygrid-1)*4, 2),dtype='float32')
        tcoords = np.zeros(((self.xgrid-1)*(self.ygrid-1)*4, 2),dtype='float32')
        # opacity is RGBA
        opacity = np.ones(((self.xgrid-1)*(self.ygrid-1)*4,4),dtype='float32')

        #loop to create quads
        vdex = 0
        for y in xrange(0,self.ygrid-1):
            for x in xrange(0,self.xgrid-1):
                index = y*(self.xgrid) + x
                
                vertices[vdex+0,0] = warpdata[index,0]          #x_coords[y,x]
                vertices[vdex+0,1] = warpdata[index,1]          #y_coords[y,x]
                vertices[vdex+1,0] = warpdata[index+1,0]        #x_coords[y,x+1]
                vertices[vdex+1,1] = warpdata[index+1,1]        #y_coords[y,x+1]
                vertices[vdex+2,0] = warpdata[index+cols+1,0]   #x_coords[y+1,x+1]
                vertices[vdex+2,1] = warpdata[index+cols+1,1]   #y_coords[y+1,x+1]
                vertices[vdex+3,0] = warpdata[index+cols,0]     #x_coords[y+1,x]
                vertices[vdex+3,1] = warpdata[index+cols,1]     #y_coords[y+1,x]
                
                tcoords[vdex+0,0] = warpdata[index,2]           # u_coords[y,x]
                tcoords[vdex+0,1] = warpdata[index,3]           # v_coords[y,x]
                tcoords[vdex+1,0] = warpdata[index+1,2]         # u_coords[y,x+1]
                tcoords[vdex+1,1] = warpdata[index+1,3]         # v_coords[y,x+1]
                tcoords[vdex+2,0] = warpdata[index+cols+1,2]    # u_coords[y+1,x+1]
                tcoords[vdex+2,1] = warpdata[index+cols+1,3]    # v_coords[y+1,x+1]
                tcoords[vdex+3,0] = warpdata[index+cols,2]      # u_coords[y+1,x]
                tcoords[vdex+3,1] = warpdata[index+cols,3]      # v_coords[y+1,x]
                
                opacity[vdex,3] = warpdata[index, 4]
                opacity[vdex+1,3] = warpdata[index+1, 4]
                opacity[vdex+2,3] = warpdata[index+cols+1, 4]
                opacity[vdex+3,3] = warpdata[index+cols, 4]

                vdex += 4

        self.createVertexAndTextureBuffers (vertices, tcoords, opacity)        
        

    def createVertexAndTextureBuffers(self, vertices, tcoords, opacity = None):
        ''' Allocate hardware buffers for vertices, texture coordinates, and optionally opacity '''

        if self.flipHorizontal:
            vertices[:,0] = -vertices[:,0]
        if self.flipVertical:
            vertices[:,1] = -vertices[:,1]

        GL.glEnableClientState (GL.GL_VERTEX_ARRAY)

        #vertex buffer in hardware
        self.gl_vb = GL.GLuint()
        GL.glGenBuffers(1 , self.gl_vb)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.gl_vb)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, ADT.arrayByteCount(vertices), ADT.voidDataPointer(vertices), GL.GL_STATIC_DRAW)

        #vertex buffer tdata in hardware
        self.gl_tb = GL.GLuint()
        GL.glGenBuffers(1 , self.gl_tb)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.gl_tb)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, ADT.arrayByteCount(tcoords), ADT.voidDataPointer(tcoords), GL.GL_STATIC_DRAW)

        # opacity buffer in hardware (only for warp files)
        if opacity is not None:
            self.gl_color = GL.GLuint()
            GL.glGenBuffers(1 , self.gl_color)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.gl_color)
            #convert opacity to RGBA, one point for each corner of the quad
            GL.glBufferData(GL.GL_ARRAY_BUFFER, ADT.arrayByteCount(opacity), ADT.voidDataPointer(opacity), GL.GL_STATIC_DRAW)
        else:
            self.gl_color = None    

        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        
    def drawWarp(self):
        ''' 
        Warp the output, using the vertex, texture, and optionally an opacity array
        '''
        #GL.glPushMatrix() 
        #GL.glMatrixMode(GL.GL_MODELVIEW)
        #GL.glLoadIdentity()
        #GL.glMatrixMode(GL.GL_PROJECTION)
        #GL.glLoadIdentity()

        GL.glUseProgram(0)
            
        #point to color (opacity)
        if self.gl_color is not None:
            GL.glEnableClientState(GL.GL_COLOR_ARRAY)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.gl_color)
            GL.glColorPointer(4, GL.GL_FLOAT, 0, None)
            GL.glEnable(GL.GL_BLEND);
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ZERO);
        
        # point to vertex data
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.gl_vb)
        GL.glVertexPointer(2, GL.GL_FLOAT, 0, None)
            
        #point to texture
        GL.glEnableClientState(GL.GL_TEXTURE_COORD_ARRAY)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.gl_tb)
        GL.glTexCoordPointer(2, GL.GL_FLOAT, 0, None)

        #GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        #GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        #GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        #GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)

        #draw quads
        GL.glDrawArrays (GL.GL_QUADS, 0, self.nverts)

        # cleanup
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        GL.glDisableClientState(GL.GL_TEXTURE_COORD_ARRAY)

        if self.gl_color is not None:
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            GL.glDisableClientState(GL.GL_COLOR_ARRAY)

        #GL.glPopMatrix() 

    # override the default Flip in PsychoPy.Window to pack multiple frames per VSync
    def flip(self, clearBuffer=True):
        """Flip the front and back buffers after drawing everything for your frame.
        (This replaces the win.update() method, better reflecting what is happening underneath).

        win.flip(clearBuffer=True)#results in a clear screen after flipping
        win.flip(clearBuffer=False)#the screen is not cleared (so represent the previous screen)
        """
        global currWindow

        # Pack multiple frames into one VSync!
        if (self.flipEvery3rdFrame):
            clearBuffer = (self.flipCounter %3 == 2)

        # decide whether to really perform a hardware flip
        flipThisFrame = (not self.flipEvery3rdFrame) or (self.flipEvery3rdFrame and (self.flipCounter %3 == 2))

        for thisStim in self._toDraw:
            thisStim.draw()

        if self.useFBO:
            if flipThisFrame:
                if self.isPsychoPyV180OrAbove:
                    GL.glUseProgram(self._progFBOtoFrame)
                #need blit the frambuffer object to the actual back buffer

                # unbind the framebuffer as the render target
                GL.glBindFramebufferEXT(GL.GL_FRAMEBUFFER_EXT, 0)
                GL.glDisable(GL.GL_BLEND)

                #before flipping need to copy the renderBuffer to the frameBuffer
                GL.glActiveTexture(GL.GL_TEXTURE0)
                GL.glEnable(GL.GL_TEXTURE_2D)
                GL.glBindTexture(GL.GL_TEXTURE_2D, self.frameTexture)
                GL.glColor3f(1.0, 1.0, 1.0) # glColor multiplies with texture
                GL.glColorMask(True, True, True, True)

                #Texture interp, wrapping
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)

                # do the warp!
                self.drawWarp()

                GL.glEnable(GL.GL_BLEND)
                GL.glUseProgram(0)

        #update the bits++ LUT
        if self.bitsMode in ['fast', 'bits++']:
            self.bits._drawLUTtoScreen()

        if self.winType == "pyglet":
            #make sure this is current context
            if currWindow != self:
                self.winHandle.switch_to()
                currWindow = self

            GL.glTranslatef(0.0, 0.0, -5.0)

            for dispatcher in self._eventDispatchers:
                dispatcher.dispatch_events()

            # this might need to be done even more often than once per frame?
            self.winHandle.dispatch_events()

            # for pyglet 1.1.4 you needed to call media.dispatch for
            # movie updating
            if pyglet.version < '1.2':
                pyglet.media.dispatch_events()  # for sounds to be processed

            if self.flipEvery3rdFrame:
                if (self.flipCounter %3 == 2):
                    self.winHandle.flip()
            else:
                self.winHandle.flip()

        else:
            if pygame.display.get_init():
                if self.flipEvery3rdFrame:
                    if (self.flipCounter %3 == 2):
                        pygame.display.flip()
                else:
                    pygame.display.flip()
                
                # keeps us in synch with system event queue
                pygame.event.pump()
            else:
                core.quit()  # we've unitialised pygame so quit

        if self.useFBO:
            if flipThisFrame:
                #set rendering back to the framebuffer object
                GL.glBindFramebufferEXT(GL.GL_FRAMEBUFFER_EXT, self.frameBuffer)
                GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0_EXT)
                GL.glDrawBuffer(GL.GL_COLOR_ATTACHMENT0_EXT)
                #set to no active rendering texture
                GL.glActiveTexture(GL.GL_TEXTURE0)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        #rescale/reposition view of the window
        if self.viewScale is not None:
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glLoadIdentity()
            GL.glOrtho(-1, 1, -1, 1, -1, 1)
            GL.glScalef(self.viewScale[0], self.viewScale[1], 1)
        else:
            GL.glLoadIdentity()  # still worth loading identity

        if self.viewPos is not None:
            GL.glMatrixMode(GL.GL_MODELVIEW)
            if not self.viewScale:
                scale = [1, 1]
            else:
                scale = self.viewScale
            norm_rf_pos_x = self.viewPos[0]/scale[0]
            norm_rf_pos_y = self.viewPos[1]/scale[1]
            GL.glTranslatef(norm_rf_pos_x, norm_rf_pos_y, 0.0)

        if self.viewOri is not None:
            GL.glRotatef(self.viewOri, 0.0, 0.0, -1.0)

        #reset returned buffer for next frame
        if clearBuffer:
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        # Pack multiple frames into one VSync!
        if (self.flipEvery3rdFrame):
            self.flipCounter += 1
            if self.flipCounter %3 == 0:
                GL.glColorMask(False, True, False, True)       # rgba
            elif self.flipCounter %3 == 1:
                 GL.glColorMask(True, False, False, True)
            elif self.flipCounter %3 == 2:
                GL.glColorMask(False, False, True, True)
                clearBuffer = True

        #waitBlanking
        if self.waitBlanking and ((not self.flipEvery3rdFrame) or (clearBuffer and self.flipEvery3rdFrame)):
            GL.glBegin(GL.GL_POINTS)
            GL.glColor4f(0, 0, 0, 0)
            if sys.platform == 'win32' and self.glVendor.startswith('ati'):
                pass
            else:
                # this corrupts text rendering on win with some ATI cards :-(
                GL.glVertex2i(10, 10)
            GL.glEnd()
            GL.glFinish()

        #get timestamp
        now = logging.defaultClock.getTime()

        # run other functions immediately after flip completes
        for callEntry in self._toCall:
            callEntry['function'](*callEntry['args'], **callEntry['kwargs'])
        del self._toCall[:]

        # do bookkeeping
        if self.recordFrameIntervals:
            self.frames += 1
            deltaT = now - self.lastFrameT
            self.lastFrameT = now
            if self.recordFrameIntervalsJustTurnedOn:  # don't do anything
                self.recordFrameIntervalsJustTurnedOn = False
            else:  # past the first frame since turned on
                self.frameIntervals.append(deltaT)
                if deltaT > self._refreshThreshold:
                    self.nDroppedFrames += 1
                    if self.nDroppedFrames < reportNDroppedFrames:
                        logging.warning('t of last frame was %.2fms (=1/%i)' %
                                        (deltaT*1000, 1/deltaT), t=now)
                    elif self.nDroppedFrames == reportNDroppedFrames:
                        logging.warning("Multiple dropped frames have "
                                        "occurred - I'll stop bothering you "
                                        "about them!")

        #log events
        for logEntry in self._toLog:
            #{'msg':msg,'level':level,'obj':copy.copy(obj)}
            logging.log(msg=logEntry['msg'],
                        level=logEntry['level'],
                        t=now,
                        obj=logEntry['obj'])
        del self._toLog[:]

        #keep the system awake (prevent screen-saver or sleep)
        if self.isPsychoPyV180OrAbove:
            platform_specific.sendStayAwake()

        #    If self.waitBlanking is True, then return the time that
        # GL.glFinish() returned, set as the 'now' variable. Otherwise
        # return None as before
        #
        if self.waitBlanking is True:
            return now
    
    @property
    def eyepoint(self):
        return self._eyepoint

    @eyepoint.setter
    def eyepoint(self, value):
        self.setupProjection(self.warp, self.warpfile, value)

    def get_config(self):
        """
        Some configuration attributes we'd like to be able to track.
        """
        return {
            "warp": Warp.asString(self.warp),
            "eye_pos": self._eyepoint,
        }

class WindowSettingsFromStimCfg(object):
    ''' Read stim.cfg for window creation parameters.
        These are needed before the Stim config parsing happens.
    '''
    def __init__(self):
        object.__init__(self)        
        try:
            config = ConfigParser.RawConfigParser()
            config.read(r'stim.cfg')
            self.setValueOrDefault(config, 'Display', 'monitor', 'testMonitor')
            self.setValueOrDefault(config, 'Display', 'screen', '1')
            self.setValueOrDefault(config, 'Display', 'projectorType', 'Projector.Normal')
            self.setValueOrDefault(config, 'Display', 'warp', 'Warp.Disabled')
            self.setValueOrDefault(config, 'Display', 'warpfile', None)
            self.setValueOrDefault(config, 'Display', 'flipHorizontal', False)
            self.setValueOrDefault(config, 'Display', 'flipVertical', False)
            self.setValueOrDefault(config, 'Display', 'eyepoint', (0.5,0.5))
            self.setValueOrDefault(config, 'Stim',    'fps', 60.0)
        except Exception as e:
            logging.warning('Some Projector settings missing in stim.cfg')

    def setValueOrDefault (self, config, section, name, default):
        try:
            v = config.get(section, name)
        except Exception as e:
            v = default
        try:
            setattr(self, name, eval(v))
        except Exception as e:
            # simple strings get here
            setattr(self, name, v)


if __name__ == "__main__":
    win = Window(fullscr=True, projectorType=Projector.Normal, warp=Warp.Cylindrical, monitor='testmonitor')

    stim = visual.GratingStim(win, size=tuple(win.size), units='deg')

    for i in range(1200):
        stim.setPhase(1.0*i/180)
        stim.draw()
        win.flip()

    win.close()

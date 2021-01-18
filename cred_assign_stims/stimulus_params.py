import pickle as pkl
import os
import numpy as np
import itertools
import time

from camstim import Stimulus
from cred_assign_stims import CredAssignStims

""" Functions to initialize parameters for Gabors or Squares, and present and record stimuli.

Parameters are set here.
"""

GABOR_PARAMS = {
                ### PARAMETERS TO SET
                "n_gabors": 30,
                # range of size of gabors to sample from (height and width set to same value)
                "size_ran": [10, 20], # in deg (regardless of units below), full-width half-max 
                "sf": 0.04, # spatial freq (cyc/deg) (regardless of units below)
                "phase": 0.25, #value 0-1
                
                "oris": [0.0, 45.0, 90.0, 135.0], # orientation means to use (deg)
                "ori_std": 0.25, # orientation st dev to use (rad) (single value)
                
                ###FOR NO SURPRISE, enter [0, 0] for surp_len and [block_len, block_len] for reg_len
                "im_len": 0.3, # duration (sec) of each image (e.g., A)
                "reg_len": [30, 90], # range of durations (sec) for seq of regular sets
                "surp_len": [3, 6], # range of durations (sec) for seq of surprise sets
                "sd": 3, # nbr of st dev (gauss) to edge of gabor (default is 6)
                
                ### Changing these will require tweaking downstream...
                "units": "pix", # avoid using deg, comes out wrong at least on my computer (scaling artifact? 1.7)
                "n_im": 4 # nbr of images per set (A, B, C, D/U)
                }

SQUARE_PARAMS = {
                ### PARAMETERS TO SET
                "size": 8, # in deg (regardless of units below)
                "speed": 50, # deg/sec (regardless of units below)
                "flipfrac": 0.25, # fraction of elements that should be flipped (0 to 1)
                "density": 0.75,
                "seg_len": 1, # duration (sec) of each segment (somewhat arbitrary)
                
                ###FOR NO SURPRISE, enter [0, 0] for surp_len and [block_len, block_len] for reg_len
                "reg_len": [30, 90], # range of durations (sec) for reg flow
                "surp_len": [2, 4], # range of durations (sec) for mismatch flow
                
                ### Changing these will require tweaking downstream...
                "units": "pix", # avoid using deg, comes out wrong at least on my computer (scaling artifact? 1.7)
                
                ## ASSUMES THIS IS THE ACTUAL FRAME RATE 
                "fps": 60 # frames per sec, default is 60 in camstim
                }

def winVar(win=None, units="pix", dist=None, width=None, size=None):
    """Returns width and height of the window in units as tuple.
    If win is not provided, dist (cm), width (cm) and size (wid pix, hei pix) are required.

    NOTE: The deg_per_pix calculation here is different from allensdk implementation 
    http://alleninstitute.github.io/AllenSDK/_modules/allensdk/brain_observatory/stimulus_info.html#Monitor.pixels_to_visual_degrees

    Here, deg_per_pix are calculated from full screen instead of on 1 pixel (central), leading
    to a value near 0.07 (here) instead of 0.12 (allensdk implementation).
    """

    if win is None: 
        if dist is None or width is None or size is None:
            raise ValueError("If win is not provided, must provide dist, width and size.")
    else:
        dist = win.monitor.getDistance()
        width = win.monitor.getWidth()
        size = win.size
    
    # get values to convert deg to pixels
    deg_wid = np.rad2deg(np.arctan((0.5 * width) / dist)) * 2 # about 120
    deg_per_pix = deg_wid/size[0] # about 0.07
    
    if units == "deg":
        deg_hei = deg_per_pix * size[1] # about 67
        # Something is wrong with deg as this does not fill screen
        init_wid = deg_wid
        init_hei = deg_hei
        fieldSize = [init_wid, init_hei]

    elif units == "pix":
        init_wid = size[0]
        init_hei = size[1]
        fieldSize = [init_wid, init_hei]
    
    else:
        raise ValueError("Only implemented for deg or pixel units so far.")
    
    return fieldSize, deg_per_pix
        
        
def posarray(rng, fieldsize, n_elem, n_im):
    """Returns 2D array of positions in field.
    Takes a seeded numpy random number generator, 
    fieldsize, number of elements (e.g., of gabors), 
    and number of images (e.g., A, B, C, D, U).
    """
    coords_wid = rng.uniform(-fieldsize[0]/2, fieldsize[0]/2, [n_im, n_elem])[:, :, np.newaxis]
    coords_hei = rng.uniform(-fieldsize[1]/2, fieldsize[1]/2, [n_im, n_elem])[:, :, np.newaxis]
        
    return np.concatenate((coords_wid, coords_hei), axis=2)


def sizearray(rng, size_ran, n_elem, n_im):
    """Returns array of sizes in range (1D).
    Takes a seeded numpy random number generator, 
    start and end of range, number of elements 
    (e.g., of gabors), and number of images (e.g., A, B, C, D, U).
    """
    if len(size_ran) == 1:
        size_ran = [size_ran[0], size_ran[0]]
    
    sizes = rng.uniform(size_ran[0], size_ran[1], [n_im, n_elem])
    
    return np.around(sizes)


def possizearrays(rng, size_ran, fieldsize, n_elem, n_im):
    """Returns zip of list of pos and sizes for n_elem.
    Takes a seeded numpy random number generator,
    start and end of size range, fieldsize, number of elements (e.g., of 
    gabors), and number of images (e.g., A, B, C, D/U).
    """
    pos = posarray(rng, fieldsize, n_elem, n_im + 1) # add one for U
    sizes = sizearray(rng, size_ran, n_elem, n_im + 1) # add one for U
    
    return zip(pos, sizes)  


def createseqlen(rng, block_segs, regs, surps):
    """
    Arg:
        block_segs: number of segs per block
        regs: duration of each regular set/seg 
        surps: duration of each regular set/seg
    
    Returns:
         list comprising a sublist of regular set durations 
         and a sublist of surprise set durations, both of equal
         lengths.
    
    FYI, this may go on forever for problematic duration ranges.
    
    """
    minim = regs[0]+surps[0] # smallest possible reg + surp set
    maxim = regs[1]+surps[1] # largest possible reg + surp set
    
    # sample a few lengths to start, without going over block length
    n = int(block_segs/(regs[1]+surps[1]))
    # mins and maxs to sample from
    reg_block_len = rng.randint(regs[0], regs[1] + 1, n).tolist()
    surp_block_len = rng.randint(surps[0], surps[1] + 1, n).tolist()
    reg_sum = sum(reg_block_len)
    surp_sum = sum(surp_block_len)
    
    while reg_sum + surp_sum < block_segs:
        rem = block_segs - reg_sum - surp_sum
        # Check if at least the minimum is left. If not, remove last. 
        while rem < minim:
            # can increase to remove 2 if ranges are tricky...
            reg_block_len = reg_block_len[0:-1]
            surp_block_len = surp_block_len[0:-1]
            rem = block_segs - sum(reg_block_len) - sum(surp_block_len)
            
        # Check if what is left is less than the maximum. If so, use up.
        if rem <= maxim:
            # get new allowable ranges
            reg_min = max(regs[0], rem - surps[1])
            reg_max = min(regs[1], rem - surps[0])
            new_reg_block_len = rng.randint(reg_min, reg_max + 1)
            new_surp_block_len = int(rem - new_reg_block_len)
        
        # Otherwise just get a new value
        else:
            new_reg_block_len = rng.randint(regs[0], regs[1] + 1)
            new_surp_block_len = rng.randint(surps[0], surps[1] + 1)
 
        reg_block_len.append(new_reg_block_len)
        surp_block_len.append(new_surp_block_len)
        
        reg_sum = sum(reg_block_len)
        surp_sum = sum(surp_block_len)     

    return [reg_block_len, surp_block_len]


def orisurpgenerator(rng, oris, block_segs):
    """
    Args:
        oris: mean orientations
        block_segs: list comprising a sublist of regular set durations 
                    and a sublist of surprise set durations, both of equal
                    lengths
    
    Returns:
        zipped lists, one of mean orientation, and one of surprise value 
        for each image sequence.
    
    FYI, this may go on forever for problematic duration ranges.
    """
    n_oris = float(len(oris)) # number of orientations

    orilist = list()
    surplist = list()
    for _, (reg, surp) in enumerate(zip(block_segs[0], block_segs[1])):     
        # deal with reg
        oriadd = list()
        for _ in range(int(np.ceil(reg/n_oris))):
            rng.shuffle(oris) # in place
            oriadd.extend(oris[:])
        oriadd = oriadd[:reg] # chop!
        surpadd = np.zeros_like(oriadd) # keep track of not surprise (0)
        orilist.extend(oriadd)
        surplist.extend(surpadd)
        
        # deal with surp
        oriadd = list()
        for _ in range(int(np.ceil(surp/n_oris))):
            rng.shuffle(oris) # in place
            oriadd.extend(oris[:])
        oriadd = oriadd[:surp]
        surpadd = np.ones_like(oriadd) # keep track of surprise (1)
        orilist.extend(oriadd)
        surplist.extend(surpadd)
    
    return zip(orilist, surplist)


def orisurporder(rng, oris, n_im, im_len, reg_len, surp_len, block_len):
    """
    Args:
        oris: orientations
        n_im: number of images (e.g., A, B, C, D/U)
        im_len: duration of each image
        reg_len: range of durations of reg seq
        surp_len: range of durations of surp seq
        block_len: duration of the block (single value)
    
    Returns:
        zipped lists, one of mean orientation, and one of surprise value 
        for each image sequence.
    """
    set_len = im_len * (n_im + 1.0) # duration of set (incl. one blank per set)
    reg_sets = [x/set_len for x in reg_len] # range of nbr of sets per regular seq, e.g. 20-60
    surp_sets = [x/set_len for x in surp_len] # range of nbr of sets per surprise seq, e.g., 2-4
    block_segs = block_len/set_len # nbr of segs per block, e.g. 680
    
    # get seq lengths
    block_segs = createseqlen(rng, block_segs, reg_sets, surp_sets)
    
    # from seq durations get zipped lists, one of oris, one of surp=0 or 1
    # for each image
    orisurplist = orisurpgenerator(rng, oris, block_segs)

    return orisurplist


def flipgenerator(flipcode, segperblock):
    """
    Args:
        flipcode: should be [0, 1] with 0 for regular flow and 1 for mismatch 
                  flow.
        segperblock: list comprising a sublist of regular set durations 
                     and a sublist of surprise set durations, both of equal
                     lengths.
    
    Returns:
        a list of surprise value (0 or 1), for each segment 
        (each 1s for example).
    
    """

    fliplist = list()
    for _, (reg, surp) in enumerate(zip(segperblock[0], segperblock[1])):
        regadd = [flipcode[0]] * reg
        surpadd = [flipcode[1]] * surp
        fliplist.extend(regadd)
        fliplist.extend(surpadd)
        
    return fliplist


def fliporder(rng, seg_len, reg_len, surp_len, block_len):
    """ 
    Args:
        seg_len: duration of each segment (arbitrary minimal time segment)
        reg_len: range of durations of reg seq
        surp_len: range of durations of surp seq
        block_len: duration of each block (single value)
    
    Returns:
        a zipped list of sublists with the surprise value (0 or 1), size, 
        number of squares, direction for each kappa value
        and surprise value (0 or 1) for each segment (each 1s for example).
    
    """

    reg_segs = [x/seg_len for x in reg_len] # range of nbr of segs per regular seq, e.g. 30-90
    surp_segs = [x/seg_len for x in surp_len] # range of nbr of segs per surprise seq, e.g., 2-4
    block_segs = block_len/seg_len # nbr of segs per block, e.g. 540
    
    # get seg lengths
    segperblock = createseqlen(rng, block_segs, reg_segs, surp_segs)
    
    # flip code: [reg, flip]
    flipcode = [0, 1]
    
    # from seq durations get a list each kappa or (ori, surp=0 or 1)
    fliplist = flipgenerator(flipcode, segperblock)

    return fliplist


def init_squares(window, direc, session_params, recordPos, square_params=SQUARE_PARAMS):

    # get fieldsize in units and deg_per_pix
    fieldsize, deg_per_pix = winVar(window, square_params["units"])
    
    # convert values to pixels if necessary
    if square_params["units"] == "pix":
        size = np.around(square_params["size"]/deg_per_pix)
        speed = square_params["speed"]/deg_per_pix
    else:
        size = square_params["size"]
        speed = square_params["speed"]
    
    # convert speed for units/s to units/frame
    speed = speed/square_params["fps"]
    
    # to get actual frame rate
    act_fps = window.getMsPerFrame() # returns average, std, median
    
    # calculate number of squares for each square size
    n_Squares = int(square_params["density"]*fieldsize[0]*fieldsize[1] \
                /np.square(size))
    
    # check whether it is a habituation session. If so, remove any surprise
    # segments
    if session_params["type"] == "hab":
        square_params["reg_len"] = [session_params["sq_dur"], session_params["sq_dur"]]
        square_params["surp_len"] = [0, 0]

    # establish a pseudorandom array of when to switch from reg to mismatch
    # flow and back    
    fliparray = fliporder(session_params["rng"],
                          square_params["seg_len"],
                          square_params["reg_len"], 
                          square_params["surp_len"],
                          session_params["sq_dur"])
    
    session_params["windowpar"] = [fieldsize, deg_per_pix]
    
    elemPar={ # parameters set by ElementArrayStim
            "units": square_params["units"],
            "nElements": n_Squares,
            "sizes": size,
            "fieldShape": "sqr",
            "contrs": 1.0,
            "elementTex": None,
            "elementMask": None,
            "name": "bricks",
            }
    
    sweepPar={ # parameters to sweep over (0 is outermost parameter)
            "Flip": (fliparray, 0),
            }
    
    # Create the stimulus array
    squares = CredAssignStims(window, elemPar, fieldsize, direc=direc, speed=speed,
        flipfrac=square_params["flipfrac"], currval=fliparray[0], rng=session_params["rng"])
    
    # Add these attributes for the logs
    squares.square_params = square_params
    squares.actual_fps = act_fps
    squares.direc = direc
    
    sq = Stimulus(squares,
                  sweepPar,
                  sweep_length=square_params["seg_len"], 
                  start_time=0.0,
                  runs=1,
                  shuffle=False,
                  )

    # record attributes from CredAssignStims
    if recordPos: # potentially large arrays
        session_params["posbyframe"] = squares.posByFrame
    
    # add more attribute for the logs
    squares.session_params = session_params

    # record attributes from CredAssignStims
    attribs = ["elemParams", "fieldSize", "tex", "colors", "square_params",
               "initScr", "autoLog", "units", "actual_fps", "direc", 
               "session_params", "last_frame"]
    
    sq.stim_params = {key:sq.stim.__dict__[key] for key in attribs}
    
    return sq


def init_gabors(window, session_params, recordOris, gabor_params=GABOR_PARAMS):

    # get fieldsize in units and deg_per_pix
    fieldsize, deg_per_pix = winVar(window, gabor_params["units"])
    
    # convert values to pixels if necessary
    if gabor_params["units"] == "pix":
        size_ran = [np.around(x/deg_per_pix) for x in gabor_params["size_ran"]]
        sf = gabor_params["sf"]*deg_per_pix
    else:
        size_ran = gabor_params["size_ran"]
        sf = gabor_params["sf"]
    
    # get kappa from orientation std
    kap = 1.0/gabor_params["ori_std"]**2

    # size is set as where gauss std=3 on each side (so size=6 std). 
    # Convert from full-width half-max
    gabor_modif = 1.0 / (2 * np.sqrt(2 * np.log(2))) * gabor_params["sd"]
    size_ran = [np.around(x * gabor_modif) for x in size_ran]
    
    # get positions and sizes for each image (A, B, C, D, U)
    session_params["possize"] = possizearrays(session_params["rng"],
                                              size_ran, 
                                              fieldsize, 
                                              gabor_params["n_gabors"], 
                                              gabor_params["n_im"])
    
    # check whether it is a habituation session. If so, remove any surprise
    # segments
    if session_params["type"] == "hab":
        gabor_params["reg_len"] = [session_params["gab_dur"], session_params["gab_dur"]]
        gabor_params["surp_len"] = [0, 0]

    # establish a pseudorandom order of orientations to cycle through
    # (surprise integrated as well)    
    orisurps = orisurporder(session_params["rng"],
                            gabor_params["oris"], 
                            gabor_params["n_im"], 
                            gabor_params["im_len"], 
                            gabor_params["reg_len"], 
                            gabor_params["surp_len"],
                            session_params["gab_dur"])
    
    session_params["windowpar"] = [fieldsize, deg_per_pix]
            
    elemPar={ # parameters set by ElementArrayStim
            "units": gabor_params["units"],
            "nElements": gabor_params["n_gabors"], # number of stimuli on screen
            "fieldShape": "sqr",
            "contrs": 1.0,
            "phases": gabor_params["phase"],
            "sfs": sf,
            "elementTex": "sin",
            "elementMask": "gauss",
            "texRes": 48,
            "maskParams": {"sd": gabor_params["sd"]},
            "name": "gabors",
            }
    
    sweepPar={ # parameters to sweep over (0 is outermost parameter)
            "OriSurp": (orisurps, 0), # contains (ori in degrees, surp=0 or 1)
            "PosSizesAll": ([0, 1, 2, 3], 1), # pass sets of positions and sizes
            }
    
    # Create the stimulus array 
    gabors = CredAssignStims(window, elemPar, fieldsize, orikappa=kap,
        possizes=session_params["possize"], rng=session_params["rng"])
    
    # Add these attributes for the logs
    gabors.gabor_params = gabor_params
    
    gb = Stimulus(gabors,
                  sweepPar,
                  sweep_length=gabor_params["im_len"], 
                  blank_sweeps=gabor_params["n_im"], # present a blank screen after every set of images
                  start_time=0.0,
                  runs=1,
                  shuffle=False,
                  )
    
    # record attributes from CredAssignStims
    if recordOris: # potentially large array
        session_params["orisbyimg"] = gabors.orisByImg
    
    # add more attribute for the logs
    gabors.session_params = session_params

    attribs = ["elemParams", "fieldSize", "tex", "colors", "gabor_params",
               "initScr", "autoLog", "units", "session_params", "last_frame"]
    
    gb.stim_params = {key:gb.stim.__dict__[key] for key in attribs}
    
    return gb

import argparse
import json
import logging
import os

import numpy as np
from psychopy import monitors

from cred_assign_stims.generate_stimuli import generate_stimuli, \
    get_cred_assign_monitor, check_reproduce


# For full ophys recording (70 min)
SESSION_PARAMS_OPHYS = {
    "type": "ophys", # type of session (habituation or ophys)
    "session_dur": 70 * 60, # expected total session duration (sec)
    "pre_blank": 30, # blank before stim starts (sec)
    "post_blank": 30, # blank after all stims end (sec)
    "inter_blank": 30, # blank between all stims (sec)
    "gab_dur": 34 * 60, # duration of gabor block (sec)
    "sq_dur": 17 * 60, # duration of each visual flow block (2 blocks total) (sec)
    }

# For a test ophys run (2 min)
SESSION_PARAMS_TEST = {
    "type": "ophys",
    "session_dur": 117,
    "pre_blank": 5,
    "post_blank": 5,
    "inter_blank": 5,
    "gab_dur": 33,
    "sq_dur": 32,
    }

# For habituation recordings (10-60 min)
SESSION_PARAMS_HABITUATION = {
    "type": "hab",
    "pre_blank": 30, 
    "post_blank": 30, 
    "inter_blank": 30, 
    }

# For a test habituation run (22 sec)
SESSION_PARAMS_TEST_HAB = {
    "type": "hab",
    "session_dur": 22, 
    "pre_blank": 1,
    "post_blank": 1,
    "inter_blank": 1,
    "gab_dur": 6,
    "sq_dur": 6,
    }

# sq_dur for each habituation recording length
HABITUATION_SQ_DUR = {
    10: 2,
    20: 4.5,
    30: 7,
    40: 9.5,
    50: 12,
    60: 14.5,
    }

# seeds used in the Credit Assignment project
CA_SEEDS = [
    30587, 5730, 36941, 11883, 8005, 34380, 44023, 29259, 
    1118, 997, 33856, 23187, 33767, 32698, 17904, 44721, 32579, 
    26850, 39002, 6698, 8612, 12470, 7038, 23433, 20846, 35159, 
    34931, 32706, 8114, 11744, 303, 13515, 32899, 38171, 38273, 
    18246, 17769, 18665, 36, 7754, 35969, 10378, 42270, 27797, 
    16745, 10210, 24253, 19576, 30582]


def get_ca_seeds(ca_seeds, verbose=False):
    if ca_seeds in ["any", "all"]:
        seeds = CA_SEEDS
    elif "-" in ca_seeds:
        if ca_seeds[0] == "-":
            seeds = CA_SEEDS[: int(ca_seeds[1:])]
        elif ca_seeds[-1] == "-":
            seeds = CA_SEEDS[int(ca_seeds[:-1]) :]
        else:
            idx_st, idx_end = ca_seeds.split("-")
            seeds = CA_SEEDS[int(idx_st) : int(idx_end) + 1]
    else:
        seeds = [CA_SEEDS[int(ca_seeds)]]
    
    if verbose:
        seeds_str = [str(seed) for seed in seeds]
        logging.info("Running through seeds: {}".format(", ".join(seeds_str)))
    
    return seeds


def run_generate_stimuli(args):

    # collect correct session parameters
    if args.test_run:
        if args.test_hab:
            raise ValueError("Can only run test_run or test_hab, not both.")
        if args.hab_duration != 0:
            raise ValueError("Test run not implemented for habituation stimulus.")
        session_params = SESSION_PARAMS_TEST
        run_type = "test_run"
    elif args.test_hab:
        session_params = SESSION_PARAMS_TEST_HAB
        run_type = "test_hab"
    elif args.hab_duration == 0:
        session_params = SESSION_PARAMS_OPHYS
        run_type = "ophys_run"
    elif args.hab_duration not in HABITUATION_SQ_DUR.keys():
        raise ValueError("Habituation must last a multiple of 10 min, up to 60 min.")
    else:
        session_params = SESSION_PARAMS_HABITUATION
        sq_dur = HABITUATION_SQ_DUR[args.hab_duration]
        session_params["session_dur"] = 60 * args.hab_duration
        session_params["gab_dur"] = 60 * sq_dur * 2
        session_params["sq_dur"] = 60 * sq_dur
        run_type = "habituation_run_{}".format(args.hab_duration)
    
    # collect frames saving information
    args.save_directory = os.path.abspath(os.path.join(args.save_directory, run_type))
    if args.save_frames:
        args.save_frames = args.save_extension.strip(".").lower()

    # format seed(s)
    if args.ca_seeds is not None:
        seeds = get_ca_seeds(args.ca_seeds, verbose=True)
    else:
        if args.seed is not None:
            args.seed = int(args.seed)
        seeds = [args.seed]

    # retrieve monitor configuration used for the Credit Assignment project
    monitor = get_cred_assign_monitor()

    if args.reproduce:
        check_reproduce(monitor, fullscreen=args.fullscreen, raise_error=True)

    # run generation script
    for seed in seeds:
        generate_stimuli(session_params, seed=seed, save_frames=args.save_frames, 
            save_directory=args.save_directory, monitor=monitor, 
            fullscreen=args.fullscreen, warp=args.warp, 
            save_from_frame=args.save_from_frame)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument("--test_run", action="store_true", 
        help="Test run optical physiology recording stimulus (2 min).")
    parser.add_argument("--test_hab", action="store_true", 
        help="Test run habituation recording stimulus (15 sec).")
    parser.add_argument("--hab_duration", default=0, type=int,
        help="Duration of habituation stimulus (10-60 min). If 0, optical "
        "physiology recording stimulus is produced (fixed duration).")

    parser.add_argument("--reproduce", action="store_true", 
        help="Ensures that original Credit Assignment stimuli are reproduced.")
    parser.add_argument("--fullscreen", action="store_true", 
        help="Generates and displays stimuli for fullscreen. Only compatible "
        "with --reproduce if current monitor settings happen to match original ones.")
    parser.add_argument("--warp", action="store_true", 
        help="Generates and displays stimuli warped.")
    parser.add_argument("--seed", default=None, help="Stimulus seed (int).")
    parser.add_argument("--ca_seeds", default=None, 
        help="Indices of Credit Assignment stimulus seeds to run through, "
        "e.g. 'all', '0-5', '6-'.")
    
    parser.add_argument("--save_frames", action="store_true", 
        help="Save stimulus frames.")
    parser.add_argument("--save_directory", default="frames", 
        help="Main directory in which to save frames, if saved.")
    parser.add_argument("--save_extension", default="png", 
        help="Format for saving stimulus frames (jpg, png, tif).")
    parser.add_argument("--save_from_frame", default=0, type=int,
        help="Frame from which to start saving, if saving.")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    run_generate_stimuli(args)


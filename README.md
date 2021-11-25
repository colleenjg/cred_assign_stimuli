# Credit Assignment Project Stimulus Code

This repository contains the code needed to reproduce the stimuli used in the **Credit Assignment project**, an [Allen Institute for Brain Science](https://alleninstitute.org/what-we-do/brain-science/) [OpenScope](https://alleninstitute.org/what-we-do/brain-science/news-press/press-releases/openscope-first-shared-observatory-neuroscience) project. 
&nbsp;

The Credit Assignment experiment was conceptualized by [Joel Zylberberg](http://www.jzlab.org/) (York University), [Blake Richards](http://linclab.org/) (McGill University), [Timothy Lillicrap](http://contrastiveconvergence.net/~timothylillicrap/index.php) (DeepMind) and [Yoshua Bengio](https://yoshuabengio.org/) (Mila), and the stimuli were coded by [Colleen Gillon](https://sites.google.com/mila.quebec/linc-lab/team/colleen?authuser=0).

The experiment details, analyses and results are published in [Gillon _et al._, 2021, _bioRxiv_](https://www.biorxiv.org/content/10.1101/2021.01.15.426915v2). 
&nbsp;

## Installation
### Dependencies:
- Windows OS (see **Camstim package**)
- python 2.7
- psychopy 1.82.01
- camstim 0.2.4
&nbsp;

### Camstim 0.2.4: 
- Built and licensed by the [Allen Institute](https://alleninstitute.org/).
- Written in **Python 2** and designed for **Windows OS** (requires `pywin32`).
- Pickled stimulus presentation logs are typically saved under `user/camstim/output`.
&nbsp;

### Installation with [Anaconda](https://docs.anaconda.com/anaconda/install/) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html):
1. Navigate to repository and install conda environment.  
    `conda env create -f cred_assign_stimuli.yml`
2. Activate the environment.  
    `conda activate cred_assign_stimuli`
3. Install the Allen Institute `camstim` package in the environment.  
    `pip install camstim/.`
4. Revert the version of the `pillow` package (ignore incompatibility warning for `camstim`).  
    `pip install pillow==2.9.0`. 
5. Download and install [`AVbin`](https://avbin.github.io/AVbin/Download.html) for your OS.  
&nbsp;

## Run
View an **optical physiology** session presentation (70 min) with the same parameters are used in the Credit Assignment project by running  
`python run_generate_stimuli.py`.  

To exit the presentation at any time, press `Ctrl-C` or `Esc`.  
&nbsp;

### Example uses of arguments:
`--test_run`               ->  **abridged** 2 min example of an **optical physiology** session presentation.  
`--test_hab`               ->  **abridged** 22 sec example of a **habituation** session presentation.  
`--hab_duration 10`   ->  `10` min habituation session.  
&nbsp;

`--seed 101`     ->  seeds the random processes generating the stimuli to allow reproduction, e.g. with a seed value of `101`.  
`--ca_seeds 0`  ->  reproduces the stimuli presented in the first (`0`th) Credit Assignment session.  
&nbsp;

`--fullscreen`  ->  produces the presentation in fullscreen mode.   
_Note that the same stimulus seed used with different presentation window sizes produces **different stimuli**. Do not use if your aim is to reproduce a specific Credit Assignment session's stimuli, unless your screen is the same size (1920 x 1200 pixels)._  
`--reproduce`    ->  checks that the presentation window size is correct for reproducing the Credit Assignment experiment, and raises an error if it is not.  
`--warp`             ->  warps the stimuli on the screen, as was done during the experiment to simulate a spherical screen on a flat screen.  
&nbsp;

`--save_frames`                                 ->  instead of presenting the stimuli, saves each new frame as an image, and produces a frame list file (see **Notes on saving frames**, below.)  
`--save_directory your_directory`  ->  main directory to which frames are saved, e.g. `your_directory`.  
`--save_extension png`                     ->  format in which to save frames as images, e.g. `png`.  
`--save_from_frame 100`                   ->  frame at which to start saving frames, e.g. `100` (if omitted, starts from beginning).  
&nbsp;

## Notes
### Helper scripts under `cred_assign_stims`:
- `generate_stimuli.py`: Generates stimuli and either projects them or saves them.
- `cred_assign_stims.py`: Defines classes used to build stimuli, and enable stimulus frames to be saved.
- `stimulus_params.py`: Initializes stimuli and their parameters.  
&nbsp;


### Saving frames:
- Process saves each new frame as an image, and `frame_list.txt` which lists the frame images that appear at each frame throughout the entire presentation.
- Frame saving is very slow during the Bricks stimuli (up to 10x slower), as each individual frame is saved.
- To partially compensate for the lag induced when saving frames, **stimuli are not drawn to the presentation window** - it remains gray.  
**NOTE:** _This does **not** apply when using the warping effect, which must be drawn to apply to the saved frames._
- File format considerations: 
    - `tif`: fastest, lossless, produces very large files
    - `jpg`: slower, lossy, produces much smaller files 
    - `png`: slowest, lossless, produces smallest files
- For instructions to assemble files into a movie using `ffmpeg`, see `example_videos`.  
&nbsp;

### Known bugs:
- Non fullscreen presentation window may appear cropped, not showing the full frame image. The saved frames, however, do reflect the full frame image.
- Lags (i.e., dropped frames) may occur during the stimulus presentation if sufficient compute resources are not available.  
**NOTE:** _When saving frames, saved frames and `framelist.txt` will **not** reflect any lags._  
- On rare occasions, stimuli fail to be drawn to occupy the full presentation window, e.g. corner quadrants remain gray. Typically, this occurs if the presentation window is minimized during the presentation or frame saving. If this occurs, it is best to restart the recording.  
&nbsp;

### Warnings/messages printed to console which can be ignored:
- Brightness/contrast not set.  
- Git commit error.  
- Import warnings (e.g., Movie2 stim, TextBox stim).
- TextBox Font Manager warning.
- Monitor specification warning.
&nbsp;

## Experimental design
&nbsp;  
During each session, subjects were presented with two stimulus types, in random order:  

### 1. Sparse Gabor sequences:
- Adapted from [Homann _et al._, 2017, _biorXiv_](https://www.biorxiv.org/content/biorxiv/early/2017/10/03/197608.full.pdf).
- Each sequence lasted **1.5 sec** and cycled through the frames: **A, B, C, D, grayscreen (G)**.
- For **each presentation session**, **new positions and sizes** were sampled for the 30 Gabor patches in each frame (A, B, C, and D).
- Within a presentation session, at each sequence repetition, the **orientation** of each of the Gabor patches was resampled around the **sequence mean** (sampled from 0, 45, 90 or 135 degrees). 
&nbsp;

### 2. Visual flow squares:
- Randomly positioned squares moved **right** for one half of the stimulus presentation, and **left** for the other (direction order was random).  
- All squares moved at the same speed.  
&nbsp;

### **Habituation** sessions:
- Lasted **10-60 min**, increasing by 10 min between each of the 6 sessions.
- Presentation time was equally split between the two stimulus types, presented in random order.  
&nbsp;

### **Optical physiology** sessions:
- Lasted **70 min**.
- Presentation time was equally split between the two stimulus types, presented in random order.
- **Unexpected sequences or "surprises"** were introduced, occurring around **5-7%** of the time.
#### 1. Sparse Gabor unexpected sequences: 
- Unexpected sequences lasted **3-6 sec (2-4 consecutive sequences)**, and occurred every 30-90 sec.
- During unexpected sequences, the D frames were replaced with **U frames**. 
- Each session's **U frame Gabor patches** had **distinct locations and sizes** from the session's D frame Gabor patches. 
- U frame Gabor patch orientations were sampled not from the sequence mean, but from the **sequence mean + 90 degrees**. So, they were about 90 degrees off from the rest of the sequence they appeared in.
#### 2. Visual flow squares: 
- Unexpected visual flow lasted **2-4 sec**, and occurred every 30-90 sec.  
- During unexpected visual flow, **25% of squares** moved in the direction opposite to the main flow.  
&nbsp;

#### Code and documentation (excluding `camstim`) built by Colleen Gillon (University of Toronto).


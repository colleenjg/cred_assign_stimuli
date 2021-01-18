# Credit Assignment project example videos

Stimulus presentation frames (saved in `png` format) from example videos were concatenated using [ffmpeg](https://ffmpeg.org/).  
&nbsp;

### test_hab_seed_10.avi
Lossy compressed video of **abridged habituation** stimulus presentation obtained by running:    
`python run_generate_stimuli.py --test_hab --seed 10 --save_frames --save_ext png`  
&nbsp;


### test_run_seed_10.avi
Lossy compressed video of **abridged optical physiology** stimulus presentation obtained by running:  
`python run_generate_stimuli.py --test_run --seed 10 --save_frames --save_ext png`  
- Unexpected Gabor sequence occur from **0:35-0:38**.
- Visual flow violations occur around **1:13** and **1:49**.  
&nbsp;


## Generating videos from saved frames
Navigate to directory containing recorded frames and `frame_list.txt`.  
&nbsp;

### Lossy compression  
- Smaller files.
- Lower fidelity: color shift and artifacts in Gabor contours are visible.
- Compatible with most playback software.
- Minimal playback lag.  
`ffmpeg -f concat -r 60 -i frame_list.txt -c:v libx264 -pix_fmt yuv420p -refs 10 -crf 10 -vf fps=60 stimulus_presentation_lossy.avi`  
&nbsp;

### Lossless compression  
- Larger files.
- Higher fidelity: minimal artifacts.
- Can play back with [VLC](https://www.videolan.org/vlc/index.html).
- More lag due to RGB pixel format.  
`ffmpeg -f concat -r 60 -i frame_list.txt -c:v libx264rgb -pix_fmt rgb24 -refs 10 -qp 0 -vf fps=60 stimulus_presentation_lossless.avi`  
&nbsp;

## Masking videos
Stimuli were presented to subjects warped on a flat screen to simulate a spherical screen. As a result, parts of the unwarped stimuli extended out of frame. To visualize this, one can apply **display_mask.png** to the stimulus videos (out-of-frame pixels are then masked in black). The display mask was obtained using [`make_display_mask()`](http://alleninstitute.github.io/AllenSDK/_modules/allensdk/brain_observatory/stimulus_info.html#make_display_mask) from the [**allensdk**](https://allensdk.readthedocs.io/en/latest/).

e.g., on the lossy video (preserving the same video codec with `-c:v libx264`)  
`ffmpeg -i stimulus_presentation_lossy.avi -i display_mask.png -filter_complex overlay -c:v libx264 stimulus_presentation_lossy_masked.avi`
&nbsp;

or on the lossless video (preserving the full quality)  
`ffmpeg -i stimulus_presentation_lossless.avi -i display_mask.png -filter_complex "[0:0][1:0]overlay=format=rgb[out]" -map "[out]" -c:v libx264rgb -pix_fmt rgb24 -refs 10 -qp 0 libx264 stimulus_presentation_lossless_masked.avi`
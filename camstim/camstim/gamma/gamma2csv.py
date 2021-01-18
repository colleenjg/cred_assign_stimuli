#! /usr/bin/env python

import os
import sys
import json
import glob


def main():
    if len(sys.argv) != 3:
        print('usage: {} <input dir> <output file>'.format(sys.argv[0]))
        exit(1)

    input_dir = sys.argv[1]
    output_filename = sys.argv[2]

    files = glob.glob(sys.argv[1] + '/*.json')
    if len(files) == 0:
        print('could not find json files in: {}'.format(input_dir))
        exit(1)

    write_header = False
    if not os.path.exists(output_filename):
        write_header = True

    with open('c:/users/public/desktop/calibration.log', 'r') as f:
        lines = f.readlines()

    brightness = 0
    for line in lines: 
        if 'Optimal brightness @ 50 cd/m^3' in line:
            brightness = line.split(':')[1]
            brightness = brightness.strip()
            break


    calibration_id = raw_input('Enter calibration id: ')
    for json_file in files:
        if 'testMonitor.json' in json_file:
            continue

        try:
            with open(json_file, 'r') as f:
                gammagrid = json.load(f)
        except Exception as error:
            print('Error parsing JSON from {}: {}'.format(json_file, error))
            continue

        with open(output_filename, 'a') as f:
            if write_header:
                f.write('calibration_id\tdate\tmonitor name\tbrightness\tfilename\tdistance\tgammagrid\tCorder\tsizePix\n')
                write_header = False
            monitor_name = os.path.basename(json_file)
            date = list(gammagrid)[0]
            f.write('{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(calibration_id,
                                                      date,
                                                      monitor_name,
                                                      brightness,
                                                      json_file,
                                                      gammagrid[date]['distance'],
                                                      str(gammagrid[date]['gammaGrid']['__ndarray__']),
                                                      gammagrid[date]['gammaGrid']['Corder'],
                                                      str(gammagrid[date]['sizePix'])))


if __name__ == '__main__':
    main()

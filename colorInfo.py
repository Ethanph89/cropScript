# IMPORTS
import json
from os import rename, remove
from PIL import Image, ImageFilter, ImageShow
import numpy as np
import boto3
import tkinter as tk
from tkinter.filedialog import askopenfilename
import sys
np.set_printoptions(threshold=sys.maxsize)

# MAIN
def main():

    # asks for CSV that contains a path to the images for processing
    root = tk.Tk()
    root.withdraw()
    filename = askopenfilename()

    csvFile = open(filename, 'r')

    # go through CSV line by line
    for line in csvFile:

        # only processes non-header lines
        if (line != "Header\n"):

            xmpPathMac = line.strip() + '.xmp'

            readXMP(xmpPathMac)


# BODY FUNCTIONS


# makes XMP file for CR2
def readXMP(path):
    f_tmp = open(path + '_tmp', 'w')

    # goes line by line until 'HasCrop' is found
    with open(path, 'r') as f:
        for line in f:
            if "HasCrop" in line:

            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()
        remove(path)
        rename(path + '_tmp', path)

# runs main
if __name__ == '__main__':
    main()
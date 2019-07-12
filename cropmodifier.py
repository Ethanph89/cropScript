# IMPORTS
import json
from os import rename, remove
import PIL.Image
from PIL import Image, ImageFilter, ImageShow
import numpy as np
import boto3
import tkinter as tk
from tkinter.filedialog import askopenfilename
from tkinter import *
from pathlib import Path
import shutil
import sys
from colormath.color_objects import LabColor, XYZColor, sRGBColor, AdobeRGBColor
from colormath.color_conversions import convert_color
np.set_printoptions(threshold=sys.maxsize)

# MAIN
def main():
    print("Please select the _JPG_CROP folder of the rig you'd like to modify")
    pathToFolder = browse_button()

    pathlist = Path(pathToFolder).glob('**/*.jpg')

    print("Enter the value by which you would like to modify exposure for the school")
    userL = float(input())
    print("Enter the value by which you would like to modify temperature for the school")
    usera = float(input())
    print("Enter the value by which you would like to modify tint for the school")
    userb = float(input())

    for path in pathlist:
        path_in_str = str(path)

        # redefining the paths out of the folder
        xmpPath = path_in_str.replace('_JPG_CROP', '').replace('.jpg', '.xmp')

        # changes XMP vals by user givern percent
        XMPmod(xmpPath, userL, usera, userb)

# BODY FUNCTIONS

# allows user to browse for a folder
def browse_button():
    # Allow user to select a directory and store it in global var
    # called folder_path
    global folder_path
    filename = filedialog.askdirectory()
    folder_path.set(filename)
    print(filename)

    return filename

# TK initialization
root = Tk()
folder_path = StringVar()
lbl1 = Label(master=root, textvariable=folder_path)
lbl1.grid(row=0, column=1)
button2 = Button(text="Browse", command=browse_button)
button2.grid(row=0, column=3)

# changes XMP vals by user givern percent
def XMPmod(path, uL, ua, ub):
    f_tmp = open(path + '_tmp', 'w')

    with open(path, 'r') as f:
        for line in f:
            if "crs:Exposure2012=" in line:
                exp = float(line.replace("   crs:Exposure2012=", "").replace("\"", "").replace("\n", ""))
                print("exposure: " + str(exp))
                exp = exp + uL
                f_tmp.write("   crs:Exposure2012=\"" + str(exp) + "\"\n")
            elif "crs:Temperature" in line:
                temper = float(line.replace("   crs:Temperature=", "").replace("\"", "").replace("\n", ""))
                print("temperaturee: " + str(temper))
                temper = temper + ua
                f_tmp.write("   crs:Temperature=\"" + str(temper) + "\"\n")
            elif "crs:Tint" in line:
                tint = float(line.replace("   crs:Tint=", "").replace("\"", "").replace("\n", ""))
                print("tint: " + str(tint))
                tint = tint + ub
                f_tmp.write("   crs:Tint=\"" + str(tint) + "\"\n")
            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()
        remove(path)
        rename(path + '_tmp', path)

# runs main
if __name__ == '__main__':
    main()
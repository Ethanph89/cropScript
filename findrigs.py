# IMPORTS
import numpy as np
import boto3
import tkinter as tk
from tkinter.filedialog import askopenfilename
from tkinter import *
from pathlib import Path
import sys
np.set_printoptions(threshold=sys.maxsize)


# MAIN
def main():

    f = open("J:/_CropScript/rigdata.csv", "w")
    f.write('rig' + ',' + 'exposureRange' + ',' + 'avgExposureVal' '\n')
    f.close()

    u = open("J:/_CropScript/rigkiddata.csv", "w")
    u.write('xmp' + ',' + 'exposureVal' + ',' + 'temperatureVal' + ',' + 'tintVal' '\n')
    u.close()

    allFolders = []
    moreFolders = "t"

    while moreFolders == "t":
        pathToFolder = browse_button() + "/"
        print("pathToFolder: " + str(pathToFolder))
        if str(pathToFolder) != "/":
            allFolders.append(str(pathToFolder))

        if len(str(pathToFolder)) > 1:
            moreFolders = "t"
        else:
            moreFolders = "f"

    print(allFolders)

    folderval = 0

    for folder in allFolders:
        pathCount = 0
        xmpVal = 0
        print("folder: " + str(folder))

        print("allFolders[folderval]: " + str(allFolders[folderval]))
        pathlist = Path(allFolders[folderval]).glob('**/*.xmp')
        print("pathlist: " + str(pathlist))

        g = open(str(allFolders[folderval]) + "rigkiddata.csv", "w")
        g.write('xmp' + ',' + 'exposureVal' + ',' + 'temperatureVal' + ',' + 'tintVal' '\n')
        g.close()

        for path in pathlist:

            path_in_str = str(path)

            xmpPath = path_in_str.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
            print("xmpPath: " + str(xmpPath))

            xmpVal = xmpVal + readXMPs(xmpPath, allFolders[folderval])
            if missexpXMPs(xmpPath) != 1:
                pathCount += 1

        xmpAvg = float(xmpVal/pathCount)
        folderval += 1

        d = open("J:/_CropScript/rigdata.csv", "a")
        if xmpAvg >= 0.25:
            d.write(str(folder) + ',' + "0.25+" + ',' + str(xmpAvg) + '\n')
        elif xmpAvg > -0.25 and xmpAvg < 0.25:
            d.write(str(folder) + ',' + "0" + ',' + str(xmpAvg) + '\n')
        else:
            d.write(str(folder) + ',' + "-0.25-" + ',' + str(xmpAvg) + '\n')
        d.close()


# BODY FUNCTIONS

# allows user to browse for a folder
def browse_button():
    # Allow user to select a directory and store it in global var
    # called folder_path
    global folder_path
    filename = filedialog.askdirectory()
    folder_path.set(filename)

    return filename

# TK initialization
root = Tk()
folder_path = StringVar()
lbl1 = Label(master=root, textvariable=folder_path)
lbl1.grid(row=0, column=1)
button2 = Button(text="Browse", command=browse_button)
button2.grid(row=0, column=3)

# colors based on school averages
def readXMPs(path, folderPath):
    exp = 0
    temper = 0
    tint = 0

    with open(path, 'r') as f:
        for line in f:
            if "crs:Exposure2012=" in line:
                exp = float(line.replace("\"", "").replace("   crs:Exposure2012=", "").replace("+", ""))
            elif "crs:Temperature" in line:
                temper = float(line.replace("\"", "").replace("   crs:Temperature=", "").replace("+", ""))
            elif "crs:Tint" in line:
                tint = float(line.replace("\"", "").replace("   crs:Tint=", "").replace("+", ""))

    u = open("J:/_CropScript/rigkiddata.csv", "a")
    u.write(str(path) + ',' + str(exp) + ',' + str(temper) + ',' + str(tint) + '\n')
    u.close()

    v = open(folderPath + "rigkiddata.csv", "a")
    v.write(str(path) + ',' + str(exp) + ',' + str(temper) + ',' + str(tint) + '\n')
    v.close()

    print(exp)
    f.close()

    return exp

def missexpXMPs(path):
    noexp = 1

    with open(path, 'r') as f:
        for line in f:
            if "crs:Exposure2012=" in line:
                noexp = 0

    print(noexp)
    f.close()

    return noexp

# runs main
if __name__ == '__main__':
    main()
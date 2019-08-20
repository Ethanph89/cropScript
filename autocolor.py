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
import csv
np.set_printoptions(threshold=sys.maxsize)


# MAIN
def main():

    try:
        CONST_PARAM = "J:/_CropScript/parameters.txt"

        print("ALERT: Please make sure all relevant CSV files are closed before running this program")
        params = readParams(CONST_PARAM)
        bgType = findBackgroundColor()

        toneSchool = [0, 0, 0]
        pathlistTwo = []

        rTone = 0
        gTone = 0
        bTone = 0

        pathToFolder = browse_button()
        folderPath = pathToFolder.replace('_JPG_CROP', '')
        csvPath = (folderPath + "/" + "colordata.csv")

        b = open(folderPath + "/" + "colordata_temp.csv", "w")
        b.write(
            'image,' + 'toneR,' + 'toneG,' + 'toneB,' + 'origL,' + 'origa,' + 'origb,' + 'newL,' + 'newa,' + 'newb,' + 'change' '\n')
        b.close()

        with open(csvPath, mode='r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            line_count = 0
            for row in csv_reader:
                if line_count == 0:
                    print(f'Column names are {", ".join(row)}')
                    line_count += 1

                rTonex = {row["toneR"]}
                rToney = ''.join(map(str, rTonex))
                rTone += float(rToney)

                gTonex = {row["toneG"]}
                gToney = ''.join(map(str, gTonex))
                gTone += float(gToney)

                bTonex = {row["toneB"]}
                bToney = ''.join(map(str, bTonex))
                bTone += float(bToney)

                pathlistTwox = {row["image"]}
                pathlistTwoy = ''.join(map(str, pathlistTwox))
                pathlistTwo.append(pathlistTwoy)

                line_count += 1
            print(f'Processed {line_count} lines.')

        # finds average tone for entire school
        toneSchool[0] = round(rTone/line_count)
        toneSchool[1] = round(gTone/line_count)
        toneSchool[2] = round(bTone/line_count)
        print("Rig RGB averages: \nR: " + str(toneSchool[0]) + " G: " + str(toneSchool[1]) + " B: " + str(toneSchool[2]))

        # uses mathColor to convert between RGB and Lab values
        rgb = sRGBColor(toneSchool[0], toneSchool[1], toneSchool[2])
        xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
        lab = convert_color(xyz, LabColor).get_value_tuple()

        # converts lab values into workable numbers
        convertedLab = [lab[0], lab[1], lab[2]]
        convertedLab[0] = round(int(convertedLab[0]) / 100)
        convertedLab[1] = round(int(convertedLab[1]) / 100)
        convertedLab[2] = round(int(convertedLab[2]) / 100)
        print("Rig Lab averages: \nL: " + str(convertedLab[0]) + " a: " + str(convertedLab[1]) + " b: " + str(convertedLab[2]))


        print("Correcting beginning")

        for path in pathlistTwo:
            path_in_str = str(path)

            # redefining the paths out of the folder
            xmpPath = path_in_str.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
            jpgPath = path_in_str

            # redefining face and tone averages
            faceFeaturesJSON = rekognitionRequest(jpgPath)
            awsMasterOutput = parse_aws_output(faceFeaturesJSON)
            pixelArray = openJPG(jpgPath)
            BoundingBoxJSON = awsMasterOutput[0]
            BBTop = BoundingBoxJSON.get("Top")
            BBBottom = BBTop + BoundingBoxJSON.get("Height")
            iTone = skinToneAverage(pixelArray, BoundingBoxJSON, BBTop, BBBottom)
            # finding individual color values
            irgb = sRGBColor(iTone[0], iTone[1], iTone[2])
            ixyz = convert_color(irgb, XYZColor, target_illuminant='d50')
            ilab = convert_color(ixyz, LabColor).get_value_tuple()
            iConvertedLab = [ilab[0], ilab[1], ilab[2]]
            iConvertedLab[0] = round(int(iConvertedLab[0]) / 100)
            iConvertedLab[1] = round(int(iConvertedLab[1]) / 100)
            iConvertedLab[2] = round(int(iConvertedLab[2]) / 100)
            print("iL: " + str(iConvertedLab[0]) + " " + "ia: " + str(iConvertedLab[1]) + " " + "ib: " + str(iConvertedLab[2]))
            # colors according to school average
            iVal = schoolColor(xmpPath, convertedLab[0], convertedLab[1], convertedLab[2], bgType, params)
            # colors according to individual average
            individualColor(xmpPath, iConvertedLab[0], iVal[0], iVal[1], iVal[2], convertedLab[0], bgType)
            # copies data to csv
            printColorInformation(jpgPath, iTone, iConvertedLab, iVal, folderPath)

        remove(folderPath + "/" + "colordata.csv")
        rename(folderPath + "/" + "colordata_temp.csv", folderPath + "/" + "colordata.csv")

        print("Coloring finished successfully!")

    except:
        raise Exception("There was an asynchronous error. "
                        "Please close all open CSVs and rerun the rig and it will fix itself. If this doesn't work, "
                        "contact Ethan")

# BODY FUNCTIONS

# allows user to browse for a folder
def readParams(file):
    param_tmp = open(file, 'r')

    with param_tmp as f:
        for line in f:
            if "bluetemp" in line:
                blueTemp = int(line.replace('bluetemp = ', '').replace('\n', ''))
            elif "bluetint" in line:
                blueTint = float(line.replace('bluetint = ', '').replace('\n', ''))
            elif "bluew" in line:
                blueW = int(line.replace('bluew = ', '').replace('\n', ''))
            elif "blueb" in line:
                blueB = int(line.replace('blueb = ', '').replace('\n', ''))
            elif "blueexp" in line:
                blueexp = int(line.replace('blueexp = ', '').replace('\n', ''))

            elif "greytemp" in line:
                greyTemp = int(line.replace('greytemp = ', '').replace('\n', ''))
            elif "greytint" in line:
                greyTint = float(line.replace('greytint = ', '').replace('\n', ''))
            elif "greyw" in line:
                greyW = int(line.replace('greyw = ', '').replace('\n', ''))
            elif "greyb" in line:
                greyB = int(line.replace('greyb = ', '').replace('\n', ''))
            elif "greyexp" in line:
                greyexp = int(line.replace('greyexp = ', '').replace('\n', ''))

            elif "greentemp" in line:
                greenTemp = int(line.replace('greentemp = ', '').replace('\n', ''))
            elif "greentint" in line:
                greenTint = float(line.replace('greentint = ', '').replace('\n', ''))
            elif "greenw" in line:
                greenW = int(line.replace('greenw = ', '').replace('\n', ''))
            elif "greenb" in line:
                greenB = int(line.replace('greenb = ', '').replace('\n', ''))
            elif "greenexp" in line:
                greenexp = int(line.replace('greenexp = ', '').replace('\n', ''))
    f.close()

    return blueTemp, blueTint, blueW, blueB, greyTemp, greyTint, greyW, greyB, greenTemp, greenTint, greenW, greenB, \
           blueexp, greyexp, greenexp


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
button2 = Button(text="Select _JPG_CROP folder", command=browse_button)
button2.grid(row=0, column=3)

# opens JPG and returns pixel array
def openJPG(path):
    im = PIL.Image.open(path)
    pixel_array = np.array(im)

    #v = open("array.txt", "w")
    #v.write(str(pixel_array))
    #v.close()

    return pixel_array

# parses AWS output into an array
def parse_aws_output(JSONResponse):
    awsData = json.loads(json.dumps(JSONResponse))
    BoundingBox = awsData.get("FaceDetails")[0].get("BoundingBox")
    Landmarks = awsData.get("FaceDetails")[0].get("Landmarks")
    OrientationCorrection = awsData.get("OrientationCorrection")
    return [BoundingBox, Landmarks, OrientationCorrection]

# finds the background color
def findBackgroundColor():
    print("Please specify background color (blue, grey, green): ")
    background = input()
    # for blue backgrounds
    if background == "blue":
        print("blue")
        bgType = 0

    # for grey backgrounds
    elif background == "grey" or background == "gray":
        print("grey")
        bgType = 1

    # for greenscreen backgrounds
    else:
        print("green")
        bgType = 2

    return bgType

# sends image to Rekognition client
def rekognitionRequest(path):
    client = boto3.client('rekognition')

    image = open(path, "rb")

    response = client.detect_faces(
        Image={'Bytes': image.read()},
        Attributes=['DEFAULT']
    )

    image.close()
    strResponse = str(response)

    if len(strResponse) > 500:
        print("found")
        return response
    else:
        print("not found")
        return 0

# find average RGB values of skin tone
def skinToneAverage(pixelArray, boundingBox, BBTop, BBBottom):

    # uses width of head to make average despairities easier to find
    leftBBInPixels = (int)(pixelArray.shape[1] * boundingBox.get("Left"))
    rigthBBInPixels = (int)(
        (pixelArray.shape[1] * boundingBox.get("Left")) + (pixelArray.shape[1] * boundingBox.get("Width")))
    topBBInPixels = (int)(pixelArray.shape[0] * BBTop)
    bottomBBInPixels = (int)(pixelArray.shape[0] * BBBottom)

    # finds BB dimensions
    BBWidth = rigthBBInPixels - leftBBInPixels
    BBHeight = bottomBBInPixels - topBBInPixels
    BBArea = BBHeight * BBWidth
    #print(rigthBBInPixels, ' ', leftBBInPixels, ' ', bottomBBInPixels, ' ', topBBInPixels)
    #print(BBWidth, ' ', BBHeight, ' ', BBArea)

    # compares read in pixels to average value row by row until it finds an average bigger than averageToCrop
    rowNum = 0
    rSum = 0
    gSum = 0
    bSum = 0
    for row in pixelArray[topBBInPixels:bottomBBInPixels:1]:
        for i in range(leftBBInPixels, rigthBBInPixels):
            rSum += row[i][0]
            gSum += row[i][1]
            bSum += row[i][2]
            rowNum += 1
    skinAverage = [rSum / BBArea, gSum / BBArea, bSum / BBArea]

    #print(skinAverage)
    return skinAverage

# colors based on school averages
def schoolColor(path, Lval, aval, bval, bgType, params):

    # sets XMP values based on if the background is blue grey or green
    # blue
    if bgType == 0:
        exp = ((params[12] - Lval) / 20)
        temper = params[0]
        tint = params[1]
        wh = params[2]
        bl = params[3]
    # grey
    elif bgType == 1:
        exp = ((params[13] - Lval) / 20)
        temper = params[4]
        tint = params[5]
        wh = params[6]
        bl = params[7]
    # green
    else:
        exp = ((params[14] - Lval) / 20)
        temper = params[8]
        tint = params[9]
        wh = params[10]
        bl = params[11]

    newL = Lval + (20 * exp)
    newa = aval
    newb = bval

    f_tmp = open(path + '_tmp', 'w')

    with open(path, 'r') as f:
        for line in f:
            if "crs:Exposure2012=" in line:
                f_tmp.write("   crs:Exposure2012=\"" + str(exp) + "\"\n")
            elif "crs:Temperature" in line:
                f_tmp.write("   crs:Temperature=\"" + str(temper) + "\"\n")
            elif "crs:Tint" in line:
                f_tmp.write("   crs:Tint=\"" + str(tint) + "\"\n")
            elif "crs:Whites2012=" in line:
                f_tmp.write("   crs:Whites2012=\"" + str(wh) + "\"\n")
            elif "crs:Blacks2012=" in line:
                f_tmp.write("   crs:Blacks2012=\"" + str(bl) + "\"\n")
            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()
        remove(path)
        rename(path + '_tmp', path)

    return exp, temper, tint, wh, bl, newL, newa, newb

# colors based on individual values
def individualColor(path, Lval, expSchool, temperSchool, tintSchool, LvalSchool, bgType):
    print("Color correcting " + path)

    # blue individual color correction
    if bgType == 0:
        # same tone
        if Lval <= (LvalSchool + 2) and  Lval >= (LvalSchool - 2):
            exp = expSchool
            temper = temperSchool
            tint = tintSchool
        # light
        elif Lval > (LvalSchool + 2):
            exp = expSchool - 0.2
            temper = temperSchool * 1
            tint = tintSchool
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.40
            temper = temperSchool * 1
            tint = tintSchool
        # dark
        elif Lval < (LvalSchool - 2):
            exp = expSchool + 0.2
            temper = temperSchool
            tint = tintSchool
        # very dark
        else:
            exp = expSchool + 0.40
            temper = temperSchool
            tint = tintSchool

    # grey individual color correction
    elif bgType == 1:
        # same tone
        if Lval <= (LvalSchool + 3) and Lval >= (LvalSchool - 3):
            exp = expSchool
            temper = temperSchool
            tint = tintSchool
        # light
        elif Lval > (LvalSchool + 3):
            exp = expSchool - 0.35
            temper = temperSchool * 1
            tint = tintSchool
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.40
            temper = temperSchool * 1
            tint = tintSchool
        # dark
        elif Lval < (LvalSchool - 3):
            exp = expSchool + 0.3
            temper = temperSchool
            tint = tintSchool
        # very dark
        else:
            exp = expSchool + 0.35
            temper = temperSchool
            tint = tintSchool

    # green individual color correction
    else:
        # same tone
        if Lval <= (LvalSchool + 3) and Lval >= (LvalSchool - 3):
            exp = expSchool
            temper = temperSchool
            tint = tintSchool
        # light
        elif Lval > (LvalSchool + 3):
            exp = expSchool - 0.35
            temper = temperSchool * 1
            tint = tintSchool
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.40
            temper = temperSchool * 1
            tint = tintSchool
        # dark
        elif Lval < (LvalSchool - 3):
            exp = expSchool + 0.3
            temper = temperSchool
            tint = tintSchool
        # very dark
        else:
            exp = expSchool + 0.35
            temper = temperSchool
            tint = tintSchool

    f_tmp = open(path + '_tmp', 'w')

    with open(path, 'r') as f:
        for line in f:
            if "crs:Exposure2012=" in line:
                f_tmp.write("   crs:Exposure2012=\"" + str(exp) + "\"\n")
            elif "crs:Temperature" in line:
                f_tmp.write("   crs:Temperature=\"" + str(temper) + "\"\n")
            elif "crs:Tint" in line:
                f_tmp.write("   crs:Tint=\"" + str(tint) + "\"\n")
            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()
        remove(path)
        rename(path + '_tmp', path)

    return

# copies color info to colordata.csv
def printColorInformation(imgName, tone, lab, lab2, folder):
    d = open(folder + "/" + "colordata_temp.csv", "a")
    d.write(str(imgName) + ',' + str(round(tone[0])) + ',' + str(round(tone[1])) + ',' +str(round(tone[2])) + ',' +
            str(lab[0]) + ',' + str(lab[1]) + ',' + str(lab[2]) + ',' + str(lab2[5]) + ',' +
            str(lab[1]) + ',' + str(lab[2]) + ',' + str(lab[0] - lab2[5]) + '\n')
    d.close()

# runs main
if __name__ == '__main__':
    main()
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
            individualColor(xmpPath, iConvertedLab[0], iVal[0], iVal[1], iVal[2], convertedLab[0], bgType, params)
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
            elif "bluesat" in line:
                bluesat = int(line.replace('bluesat = ', '').replace('\n', ''))
            elif "bluehsl_org_lum" in line:
                bluehsl_org_lum = int(line.replace('bluehsl_org_lum = ', '').replace('\n', ''))
            elif "blues_curve" in line:
                blues_curve = str(line.replace('blueexp = ', '').replace('\n', ''))
                if blues_curve == "y":
                    blueParamS = -3
                    blueParamD = -6
                    blueParamH = 3
                    blueParamL = 6
                else:
                    blueParamS = 0
                    blueParamD = 0
                    blueParamH = 0
                    blueParamL = 0

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
            elif "greysat" in line:
                greysat = int(line.replace('greysat = ', '').replace('\n', ''))
            elif "greyhsl_org_lum" in line:
                greyhsl_org_lum = int(line.replace('greyhsl_org_lum = ', '').replace('\n', ''))
            elif "greys_curve" in line:
                greys_curve = str(line.replace('greyexp = ', '').replace('\n', ''))
                if greys_curve == "y":
                    greyParamS = 0
                    greyParamD = 0
                    greyParamH = 0
                    greyParamL = 0
                #Ethan -- this is not prompting to user
                else:
                    greyParamS = 0
                    greyParamD = 0
                    greyParamH = 0
                    greyParamL = 0

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
            elif "greensat" in line:
                greensat = int(line.replace('greensat = ', '').replace('\n', ''))
            elif "greenhsl_org_lum" in line:
                greenhsl_org_lum = int(line.replace('greenhsl_org_lum = ', '').replace('\n', ''))
            elif "greens_curve" in line:
                greens_curve = str(line.replace('greenexp = ', '').replace('\n', ''))
                if greens_curve == "y":
                    greenParamS = -6
                    greenParamD = -3
                    greenParamH = 6
                    greenParamL = 3
                else:
                    greenParamS = 0
                    greenParamD = 0
                    greenParamH = 0
                    greenParamL = 0

            elif "paleexp" in line:
                paleexp = float(line.replace('paleexp = ', '').replace('\n', ''))
            elif "paletemp" in line:
                paletemp = float(line.replace('paletemp = ', '').replace('\n', ''))
            elif "paletint" in line:
                paletint = float(line.replace('paletint = ', '').replace('\n', ''))

            elif "tanexp" in line:
                tanexp = float(line.replace('tanexp = ', '').replace('\n', ''))
            elif "tantemp" in line:
                tantemp = float(line.replace('tantemp = ', '').replace('\n', ''))
            elif "tantint" in line:
                tantint = float(line.replace('tantint = ', '').replace('\n', ''))

            elif "darkexp" in line:
                darkexp = float(line.replace('darkexp = ', '').replace('\n', ''))
            elif "darktemp" in line:
                darktemp = float(line.replace('darktemp = ', '').replace('\n', ''))
            elif "darktint" in line:
                darktint = float(line.replace('darktint = ', '').replace('\n', ''))

            elif "percent_above_hair_close" in line:
                percent_above_hair = float(line.replace('percent_above_hair_close = ', '').replace('\n', ''))
            elif "percent_below_chin_close" in line:
                percent_below_chin = float(line.replace('percent_below_chin_close = ', '').replace('\n', ''))
            elif "is_far" in line:
                is_far = int(line.replace('is_far = ', '').replace('\n', ''))
            elif "percent_above_hair_far" in line:
                percent_above_hair_far = float(line.replace('percent_above_hair_far = ', '').replace('\n', ''))
            elif "percent_below_chin_far" in line:
                percent_below_chin_far = float(line.replace('percent_below_chin_far = ', '').replace('\n', ''))
            elif "average_to_crop" in line:
                average_to_crop = int(line.replace('average_to_crop = ', '').replace('\n', ''))

    f.close()

    return blueTemp, blueTint, blueW, blueB, greyTemp, greyTint, greyW, greyB, greenTemp, greenTint, greenW, greenB, \
           blueexp, greyexp, greenexp, paleexp, paletemp, paletint, tanexp, tantemp, tantint, darkexp, darktemp, darktint,\
           bluesat, bluehsl_org_lum, blueParamD, blueParamH, blueParamL, blueParamS, greysat, greyhsl_org_lum, greyParamD, \
           greyParamH, greyParamL, greyParamS, greensat, greenhsl_org_lum, greenParamD, greenParamH, greenParamL, greenParamS, \
           percent_above_hair, percent_below_chin, is_far, percent_above_hair_far, percent_below_chin_far, average_to_crop


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

    return pixel_array

# parses AWS output into an array
def parse_aws_output(JSONResponse):
    awsData = json.loads(json.dumps(JSONResponse))
    BoundingBox = awsData.get("FaceDetails")[0].get("BoundingBox")
    Landmarks = awsData.get("FaceDetails")[0].get("Landmarks")
    OrientationCorrection = awsData.get("OrientationCorrection")
    return [BoundingBox, Landmarks, OrientationCorrection]

# finds the background specs for the rig
def findBackgroundColor():
    aboveHead = 0
    belowChin = 0

    print("Please specify background color (blue, grey, green, MYSA): ")
    background = input()

    # for blue backgrounds
    if background.lower() == "blue":
        print("blue")
        bg_type = 0

    # for grey backgrounds
    elif background.lower() == "grey" or background.lower() == "gray":
        print("grey")
        bg_type = 1

    # for greenscreen backgrounds
    elif background.lower() == "green":
        print("Kids or Seniors? (K/S)")
        aboveHead = input()
        if aboveHead.lower() == "k":
            aboveHead = .03
        elif aboveHead.lower() == "s":
            aboveHead = 0
        else:
            print("Input not recognized, please respecify specs.")
            findBackgroundColor()

        print("green")
        bg_type = 2

    # for grey backgrounds
    elif background.lower() == "mysa":
        print("MYSA")
        bg_type = 3
        aboveHead = 0
        belowChin = .0

    # catches non-recognized backgrounds
    else:
        print("Background type not recognized. Please re-enter.")
        bg_type = findBackgroundColor()

    return bg_type, aboveHead, belowChin

# sends image to rekognition client
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

    # uses width of head to make average disparities easier to find
    leftBBInPixels = (int)(pixelArray.shape[1] * boundingBox.get("Left"))
    rigthBBInPixels = (int)(
        (pixelArray.shape[1] * boundingBox.get("Left")) + (pixelArray.shape[1] * boundingBox.get("Width")))
    topBBInPixels = (int)(pixelArray.shape[0] * BBTop)
    bottomBBInPixels = (int)(pixelArray.shape[0] * BBBottom)

    # finds BB dimensions
    BBWidth = rigthBBInPixels - leftBBInPixels
    BBHeight = bottomBBInPixels - topBBInPixels
    BBArea = BBHeight * BBWidth

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
def schoolColor(path, Lval, aval, bval, bg_type, params):
    adiff = 0
    bdiff = 15 - bval

    # sets XMP values based on if the background is blue grey or green
    # blue
    if bg_type == 0:
        exp = ((params[12] - Lval) / 20)
        temper = (params[0] + (bdiff * 100))
        tint = (params[1] + adiff)
        wh = params[2]
        bl = params[3]

    # grey
    elif bg_type == 1:
        exp = ((params[13] - Lval) / 20)
        temper = (params[4] + (bdiff * 100))
        tint = (params[5] + adiff)
        wh = params[6]
        bl = params[7]

    # green
    else:
        exp = ((params[14] - Lval) / 20)
        temper = (params[8] + (bdiff * 100))
        tint = (params[9] + adiff)
        wh = params[10]
        bl = params[11]

    newL = Lval + (20 * exp)
    newa = tint
    newb = temper

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
def individualColor(path, Lval, expSchool, temperSchool, tintSchool, LvalSchool, bg_type, params):
    #print(Lval)
    print("Color correcting " + path)

    # blue individual color correction
    if bg_type == 0:
        # same tone
        if Lval <= (LvalSchool + 2) and Lval >= (LvalSchool - 2):
            exp = expSchool + params[18]
            temper = temperSchool + params[19]
            tint = tintSchool + params[20]
        # light
        elif Lval > (LvalSchool + 2):
            exp = expSchool + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.15 + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
        # dark
        elif Lval < (LvalSchool - 2):
            exp = expSchool + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]
        # very dark
        else:
            exp = expSchool + 0.15 + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]

    # grey individual color correction
    elif bg_type == 1:
        # same tone
        if Lval <= (LvalSchool + 2) and Lval >= (LvalSchool - 2):
            exp = expSchool + params[18]
            temper = temperSchool + params[19]
            tint = tintSchool + params[20]
        # light
        elif Lval > (LvalSchool + 2):
            exp = expSchool + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.15 + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
        # dark
        elif Lval < (LvalSchool - 2):
            exp = expSchool + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]
        # very dark
        else:
            exp = expSchool + 0.15 + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]

    # green individual color correction
    else:
        # same tone
        if Lval <= (LvalSchool + 2) and Lval >= (LvalSchool - 2):
            exp = expSchool + params[18]
            temper = temperSchool + params[19]
            tint = tintSchool + params[20]
        # light
        elif Lval > (LvalSchool + 2):
            exp = expSchool + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.15 + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
        # dark
        elif Lval < (LvalSchool - 2):
            exp = expSchool + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]
        # very dark
        else:
            exp = expSchool + 0.15 + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]

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
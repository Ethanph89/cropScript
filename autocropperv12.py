# IMPORTS
import json
from os import rename, remove
import os.path
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
import itertools
from colormath.color_objects import LabColor, XYZColor, sRGBColor, AdobeRGBColor
from colormath.color_conversions import convert_color
np.set_printoptions(threshold=sys.maxsize)


# XMP FILE DIRECTIONS DON'T CORRESPOND TO WHAT YOU THINK:
#   LEFT SIDE OF IMAGE => XMP TOP
#   TOP OF IMAGE => XMP RIGHT
#   RIGHT SIDE OF IMAGE => XMP BOTTOM
#   BOTTOM OF IMAGE => XMP LEFT
#   BOTTOM LEFT OF IMAGE IS (0,0)

# MAIN
def main():

    try:
        # paths to supporting .xmp files used as defaults
        CONST_CR2XMP = "J:/_CropScript/CR2template.xmp"
        CONST_ARWXMP = "J:/_CropScript/ARWtemplate.xmp"

        # path to support .txt file used to decided color correcting*
        CONST_PARAM = "J:/_CropScript/parameters.txt"
        params = readParams(CONST_PARAM)

        # close up const
        CONST_PERCENT_ABOVE_HAIR = params[42]
        CONST_PERCENT_BELOW_CHIN = params[43]

        # far away const
        CONST_IS_FAR = params[44]
        CONST_PERCENT_ABOVE_HAIR_FAR = params[45]
        CONST_PERCENT_BELOW_CHIN_FAR = params[46]

        # cropping difference required to find top of head
        CONST_AVERAGE_TO_CROP = params[47]

        # allows user to select background specs
        bg_type = findBackgroundColor()

        # creates a list of images where the face couldn't be found to skip them
        bad_list = []

        # sets initial tone values
        toneCount = 0
        rTone = 0
        gTone = 0
        bTone = 0

        # asks user if test run
        print("ALERT: Please make sure all relevant CSV files are closed before running this program")
        print("Is this a test? (Tests only run the first 20 images) (Y/N)")
        testBool = input().lower()
        if testBool == "y":
            print("This is a test run.")
        else:
            print("This is a full run.")

        # to choose a 'Selects' folder
        print("Do you want to run a 'Selects' folder (Y/N)?")
        selectsBool = input().lower()

        # defines path to JPGs
        # user selects JPG folder
        pathToFolder = browse_button()
        #print(pathToFolder)

        # creates JPG count to know if user selected correct folder
        pathlistJPG = Path(pathToFolder).glob('**/*.jpg')
        countJPG = 0
        pathlist = Path(pathToFolder).glob('**/*.jpg')

        if testBool == "y":
            if selectsBool == "y":
                top20 = itertools.islice(pathlist, 50)
                pathlist = top20
            else:
                top20 = itertools.islice(pathlist, 20)
                pathlist = top20

        for path in pathlistJPG:
            countJPG += 1

        if countJPG == 0:
            print("ALERT: It appears you selected the wrong folder. Please try again selecting the _JPG_CROP folder")
            return

        #print("pathlist: " + str(pathlist))

        if selectsBool == 'y':
            folderPath = pathToFolder.replace('_JPG_CROP', '/Selects')
        else:
            folderPath = pathToFolder.replace('_JPG_CROP', '')

        print('path to folder: ' + folderPath)

        # creates a data.csv file that contains all cropping info
        f = open(folderPath + "/" + "data.csv", "w")
        f.write(
            'image,' + 'tophead,' + 'topcrop,' + 'bottomcrop,' + 'leftcrop,' + 'rightcrop,' '\n')
        f.close()

        # creates a data.csv file that contains all color info
        b = open(folderPath + "/" + "colordata.csv", "w")
        b.write('image,' + 'toneR,' + 'toneG,' + 'toneB,' + 'origL,' + 'origa,' + 'origb,' + 'newL,' + 'newa,' + 'newb,' + 'change' '\n')
        b.close()

        # creates a linedata.csv file that contains all the color analysis by line info
        b = open(folderPath + "/" + "linedata.csv", "w")
        b.write(
            'image,' + 'line,' + 'R,' + 'G,' + 'B,' + 'L,' + 'a,' + 'b' '\n')
        b.close()

        # goes through each JPG individually
        for path in pathlist:
            path_in_str = str(path)

            # defining the paths out of the CSV
            jpgPath = path_in_str
            #print('path to jpg: ' + jpgPath)
            if selectsBool == 'y':
                xmpPath = path_in_str.replace('_JPG_CROP', '/Selects').replace('.jpg', '.xmp')
            else:
                xmpPath = path_in_str.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
            #print('path to xmp: ' + xmpPath)

            # finds the file type (ARW/CR2)
            filetype = findFiletype(xmpPath)

            # initializes default XMP
            skipBool = defaultXMP(folderPath, xmpPath, filetype, CONST_CR2XMP, CONST_ARWXMP, selectsBool)

            # opening jpg into pixel array
            pixelArray = openJPG(jpgPath)

            # makes request to rekognition and grabs JSON return
            faceFeaturesJSON = rekognitionRequest(jpgPath)
            if faceFeaturesJSON != 0 and skipBool != 'skip':

                # getting aws rekognition JSON output
                awsMasterOutput = parse_aws_output(faceFeaturesJSON)
                BoundingBoxJSON = awsMasterOutput[0]
                #LandmarksJSON = awsMasterOutput[1]
                #OrientationCorrection = awsMasterOutput[2]

                # getting center of face
                faceCenterPercentages = centerOfBoundingBox(BoundingBoxJSON)

                # gets average pixel color of first 100 rows
                averageBackgroundColor = getAverageBackgroundColor(pixelArray)

                # finds percentage-based measure of top of head
                hairCoords = findTopOfHair(pixelArray, BoundingBoxJSON, bg_type[0], CONST_AVERAGE_TO_CROP,
                                           averageBackgroundColor, folderPath, xmpPath)

                # defines bounding box top and bottom
                BBTop = BoundingBoxJSON.get("Top")
                BBBottom = BBTop + BoundingBoxJSON.get("Height")

                # uses width of head to make average disparities easier to find
                leftBBInPixels = (int)(pixelArray.shape[1] * BoundingBoxJSON.get("Left"))
                rigthBBInPixels = (int)(
                    (pixelArray.shape[1] * BoundingBoxJSON.get("Left")) + (
                                pixelArray.shape[1] * BoundingBoxJSON.get("Width")))
                topBBInPixels = (int)(pixelArray.shape[0] * BBTop)
                bottomBBInPixels = (int)(pixelArray.shape[0] * BBBottom)

                # finds BB dimensions
                BBWidthInPixels = rigthBBInPixels - leftBBInPixels
                BBHeightInPixels = bottomBBInPixels - topBBInPixels
                BBAreaInPixels = BBHeightInPixels * BBWidthInPixels

                # finds top and bottom crop depending on pose
                if (BBAreaInPixels > CONST_IS_FAR):
                    BBHeight = BBBottom - BBTop
                    cropCoordsTop = hairCoords - (CONST_PERCENT_ABOVE_HAIR + bg_type[1])
                    cropHeadDiff = hairCoords - cropCoordsTop
                    topHalf = BBHeight + cropHeadDiff
                    bottomHalf = (1 - params[48]) * topHalf
                    cropCoordsBottom = bottomHalf + BBBottom
                else:
                    cropCoordsTop = hairCoords - (CONST_PERCENT_ABOVE_HAIR_FAR + bg_type[1])
                    cropCoordsBottom = (CONST_PERCENT_BELOW_CHIN_FAR + bg_type[2]) + BBBottom

                # finds all dimensions and crop coords for XMP
                totalCropHeight = cropCoordsBottom - cropCoordsTop
                cropHeightPixels = totalCropHeight * pixelArray.shape[0]
                cropWidthPixels = (cropHeightPixels / 5) * 4
                cropWidth = cropWidthPixels / pixelArray.shape[1]
                cropLeft = faceCenterPercentages[0] - (cropWidth / 2)
                cropRight = faceCenterPercentages[0] + (cropWidth / 2)

                # ensures all crops are within range
                if cropLeft < 0:
                    cropLeft = 0
                if cropLeft > 1:
                    cropLeft = 1
                if cropRight > 1:
                    cropRight = 1
                if cropRight < 0:
                    cropRight = 0
                if cropCoordsTop > 1:
                    cropCoordsTop = 1
                if cropCoordsTop < 0:
                    cropCoordsTop = 0
                if cropCoordsBottom > 1:
                    cropCoordsBottom = 1
                if cropCoordsBottom < 0:
                    cropCoordsBottom = 0

                # makes the XMP file
                makeXMP(cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, xmpPath)

                # find skin tone
                tone = skinToneAverage(pixelArray, BoundingBoxJSON, BBTop, BBBottom)
                toneCount = toneCount + 1
                rTone = rTone + tone[0]
                rTone = rTone + tone[0]
                gTone = gTone + tone[1]
                bTone = bTone + tone[2]

                # applies Shoob default color corrections
                defaultColor(xmpPath, params, bg_type[0])

                # copies data to csv
                printInformation(jpgPath, hairCoords, cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, folderPath)
                print("Cropping " + xmpPath)

            else:
                # creates a list of all the "bad" images
                #print("bad image")
                bad_list.append(jpgPath)
                print("Bad JPGs: " + str(bad_list))

        # finds average tone for entire school
        toneSchool = [0, 0, 0]
        toneSchool[0] = round(rTone/toneCount)
        toneSchool[1] = round(gTone/toneCount)
        toneSchool[2] = round(bTone/toneCount)
        print("Rig RGB averages:\nR: " + str(toneSchool[0]) + " G: " + str(toneSchool[1]) + " B: " + str(toneSchool[2]))

        # uses mathColor to convert between RGB and Lab values
        rgb = sRGBColor(toneSchool[0], toneSchool[1], toneSchool[2])
        xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
        lab = convert_color(xyz, LabColor).get_value_tuple()

        # converts lab values into workable numbers
        convertedLab = [lab[0], lab[1], lab[2]]
        convertedLab[0] = round(int(convertedLab[0]) / 100)
        convertedLab[1] = round(int(convertedLab[1]) / 100)
        convertedLab[2] = round(int(convertedLab[2]) / 100)
        print("Rig Lab averages:\nL: " + str(convertedLab[0]) + " a: " + str(convertedLab[1]) + " b: " +
              str(convertedLab[2]))

        print("Cropping finished successfully!")

        # ceates new pathlist for color correcting that skips "bad" images
        pathlistTwo = Path(pathToFolder).glob('**/*.jpg')

        # different list of test runs
        if testBool == "y":
            if selectsBool == 'y':
                top20two = itertools.islice(pathlistTwo, 50)
                pathlistTwo = top20two
            else:
                top20two = itertools.islice(pathlistTwo, 20)
                pathlistTwo = top20two

        for path in pathlistTwo:
            badPath = 0
            path_in_str = str(path)

            # redefining the paths out of the folder
            if selectsBool == 'y':
                xmpPath = path_in_str.replace('_JPG_CROP', '/Selects').replace('.jpg', '.xmp')
                jpgPath = path_in_str
            else:
                xmpPath = path_in_str.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
                jpgPath = path_in_str

            for item in bad_list:
                if jpgPath == item:
                    badPath = 1

            if badPath != 1:
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

                print("iL: " + str(iConvertedLab[0]) + " " + "ia: " + str(iConvertedLab[1]) + " " + "ib: " +
                      str(iConvertedLab[2]))

                # PASS ONE
                # colors according to school average
                expPercentDiff = (55 - convertedLab[0])/55
                iVal = schoolColor(xmpPath, convertedLab[0], convertedLab[1], convertedLab[2], bg_type[0], params,
                                   expPercentDiff, iConvertedLab[0], iConvertedLab[1], iConvertedLab[2])

                # PASS TWO
                if params[49] == 2:
                    # colors according to individual average
                    individualColor(xmpPath, iConvertedLab[0], iVal[0], iVal[1], iVal[2], convertedLab[0], bg_type[0], params)

                # copies data to csv
                printColorInformation(jpgPath, iTone, iConvertedLab, iVal, folderPath)

        print("Coloring finished successfully!")

    except:
        raise Exception("There was an asynchroynous error. "
                        "Please close all open CSVs and rerun the rig and it will fix itself. If this doesn't work, "
                        "contact Ethan")

# BODY FUNCTIONS

# finds which filetype a given XMP will apply to
def findFiletype(xmp):
    ARWpath = xmp.replace('.xmp', '.arw')
    CR2path = xmp.replace('.xmp', '.cr2')

    if os.path.exists(CR2path):
        filetype = "CR2"
    elif os.path.exists(ARWpath):
        filetype = "ARW"
    else:
        filetype = "ERROR"

    if filetype != 'ERROR':
        print(filetype)

    return filetype

# allows user to browse for a folder
def readParams(file):
    param_tmp = open(file, 'r')

    with param_tmp as f:
        for line in f:

            # Blue
            if "bluetemp" in line:
                blueTemp = int(line.replace('bluetemp = ', '').replace('\n', ''))
            elif "bluetint" in line:
                blueTint = float(line.replace('bluetint = ', '').replace('\n', ''))
            elif "bluew" in line:
                blueW = int(line.replace('bluew = ', '').replace('\n', ''))
            elif "blueb" in line:
                blueB = int(line.replace('blueb = ', '').replace('\n', ''))
            elif "bluehigh" in line:
                blueH = int(line.replace('bluehigh = ', '').replace('\n', ''))
            elif "blueshad" in line:
                blueS = int(line.replace('blueshad = ', '').replace('\n', ''))
            elif "blueexp" in line:
                blueexp = int(line.replace('blueexp = ', '').replace('\n', ''))
            elif "bluesat" in line:
                bluesat = int(line.replace('bluesat = ', '').replace('\n', ''))
            elif "bluehsl_org_lum" in line:
                bluehsl_org_lum = int(line.replace('bluehsl_org_lum = ', '').replace('\n', ''))
            elif "blues_curve" in line:
                blues_curve = str(line.replace('blues_curve = ', '').replace('\n', ''))
                if blues_curve == "y":
                    blueParamS = -6
                    blueParamD = -3
                    blueParamH = 6
                    blueParamL = 3
                else:
                    blueParamS = 0
                    blueParamD = 0
                    blueParamH = 0
                    blueParamL = 0

            # Grey
            elif "greytemp" in line:
                greyTemp = int(line.replace('greytemp = ', '').replace('\n', ''))
            elif "greytint" in line:
                greyTint = float(line.replace('greytint = ', '').replace('\n', ''))
            elif "greyw" in line:
                greyW = int(line.replace('greyw = ', '').replace('\n', ''))
            elif "greyb" in line:
                greyB = int(line.replace('greyb = ', '').replace('\n', ''))
            elif "greyhigh" in line:
                greyH = int(line.replace('greyhigh = ', '').replace('\n', ''))
            elif "greyshad" in line:
                greyS = int(line.replace('greyshad = ', '').replace('\n', ''))
            elif "greyexp" in line:
                greyexp = int(line.replace('greyexp = ', '').replace('\n', ''))
            elif "greysat" in line:
                greysat = int(line.replace('greysat = ', '').replace('\n', ''))
            elif "greyhsl_org_lum" in line:
                greyhsl_org_lum = int(line.replace('greyhsl_org_lum = ', '').replace('\n', ''))
            elif "greys_curve" in line:
                greys_curve = str(line.replace('greys_curve = ', '').replace('\n', ''))
                if greys_curve == "y":
                    greyParamS = -6
                    greyParamD = -3
                    greyParamH = 6
                    greyParamL = 3
                else:
                    greyParamS = 0
                    greyParamD = 0
                    greyParamH = 0
                    greyParamL = 0

            # Green
            elif "greentemp" in line:
                greenTemp = int(line.replace('greentemp = ', '').replace('\n', ''))
            elif "greentint" in line:
                greenTint = float(line.replace('greentint = ', '').replace('\n', ''))
            elif "greenw" in line:
                greenW = int(line.replace('greenw = ', '').replace('\n', ''))
            elif "greenb" in line:
                greenB = int(line.replace('greenb = ', '').replace('\n', ''))
            elif "greenhigh" in line:
                greenH = int(line.replace('greenhigh = ', '').replace('\n', ''))
            elif "greenshad" in line:
                greenS = int(line.replace('greenshad = ', '').replace('\n', ''))
            elif "greenexp" in line:
                greenexp = int(line.replace('greenexp = ', '').replace('\n', ''))
            elif "greensat" in line:
                greensat = int(line.replace('greensat = ', '').replace('\n', ''))
            elif "greenhsl_org_lum" in line:
                greenhsl_org_lum = int(line.replace('greenhsl_org_lum = ', '').replace('\n', ''))
            elif "greens_curve" in line:
                greens_curve = str(line.replace('greens_curve = ', '').replace('\n', ''))
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

            # Very pale
            elif "palevexp" in line:
                palevexp = float(line.replace('palevexp = ', '').replace('\n', ''))
            elif "palevtemp" in line:
                palevtemp = float(line.replace('palevtemp = ', '').replace('\n', ''))
            elif "palevtint" in line:
                palevtint = float(line.replace('palevtint = ', '').replace('\n', ''))

            # Pale
            elif "paleexp" in line:
                paleexp = float(line.replace('paleexp = ', '').replace('\n', ''))
            elif "paletemp" in line:
                paletemp = float(line.replace('paletemp = ', '').replace('\n', ''))
            elif "paletint" in line:
                paletint = float(line.replace('paletint = ', '').replace('\n', ''))

            # Tan
            elif "tanexp" in line:
                tanexp = float(line.replace('tanexp = ', '').replace('\n', ''))
            elif "tantemp" in line:
                tantemp = float(line.replace('tantemp = ', '').replace('\n', ''))
            elif "tantint" in line:
                tantint = float(line.replace('tantint = ', '').replace('\n', ''))

            # Dark
            elif "darkexp" in line:
                darkexp = float(line.replace('darkexp = ', '').replace('\n', ''))
            elif "darktemp" in line:
                darktemp = float(line.replace('darktemp = ', '').replace('\n', ''))
            elif "darktint" in line:
                darktint = float(line.replace('darktint = ', '').replace('\n', ''))

            # Very dark
            elif "darkvexp" in line:
                darkvexp = float(line.replace('darkvexp = ', '').replace('\n', ''))
            elif "darkvtemp" in line:
                darkvtemp = float(line.replace('darkvtemp = ', '').replace('\n', ''))
            elif "darkvtint" in line:
                darkvtint = float(line.replace('darkvtint = ', '').replace('\n', ''))

            # Cropping
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
            elif "percent_face" in line:
                percent_face = float(line.replace('percent_face = ', '').replace('\n', ''))

            # Coloring
            elif "pass_num" in line:
                pass_num = int(line.replace('pass_num = ', '').replace('\n', ''))
            elif "vac" in line:
                vac = int(line.replace('vac = ', '').replace('\n', ''))

    f.close()

    return blueTemp, blueTint, blueW, blueB, greyTemp, greyTint, greyW, greyB, greenTemp, greenTint, greenW, greenB, \
           blueexp, greyexp, greenexp, paleexp, paletemp, paletint, tanexp, tantemp, tantint, darkexp, darktemp, darktint,\
           bluesat, bluehsl_org_lum, blueParamD, blueParamH, blueParamL, blueParamS, greysat, greyhsl_org_lum, greyParamD, \
           greyParamH, greyParamL, greyParamS, greensat, greenhsl_org_lum, greenParamD, greenParamH, greenParamL, greenParamS, \
           percent_above_hair, percent_below_chin, is_far, percent_above_hair_far, percent_below_chin_far, average_to_crop, \
           percent_face, pass_num, vac, blueH, blueS, greyH, greyS, greenH, greenS, palevexp, palevtemp, palevtint, \
           darkvexp, darkvtemp, darkvtint

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

# creates the default XMP
def defaultXMP(folderpath, fullpath, filetype, CR2XMP, ARWXMP, selects):
    #print(folderpath)
    #print(fullpath)
    filename = fullpath.replace(folderpath, "").replace(".xmp", "")
    #print(folderpath)

    # if file is a CR2
    if filetype == "CR2":
        shutil.copy2(CR2XMP, fullpath)
        f_tmp = open(fullpath + "_tmp", "w")

        with open(fullpath, 'r') as f:
            for line in f:
                if "RawFileName" in line:
                    f_tmp.write("   crs:RawFileName=\"" + filename + "\">")
                else:
                    f_tmp.write(line)

    # if file is an ARW
    elif filetype == "ARW":
        shutil.copy2(ARWXMP, fullpath)
        f_tmp = open(fullpath + "_tmp", "w")

        with open(fullpath, 'r') as f:
            for line in f:
                if "RawFileName" in line:
                    f_tmp.write("   crs:RawFileName=\"" + filename + "\">")
                else:
                    f_tmp.write(line)

    # if file isn't valid RAW
    else:
        if selects == 'y':
            return "skip"
        else:
            print("ERROR CANNOT FIND FILETYPE")
            return

    f.close()
    f_tmp.close()
    remove(fullpath)
    rename(fullpath + '_tmp', fullpath)

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

# finds the center of the bouding box
def centerOfBoundingBox(boundingBoxJSON):
    BBLeft = boundingBoxJSON.get("Left")
    BBTop = boundingBoxJSON.get("Top")
    BBRight = BBLeft + boundingBoxJSON.get("Width")
    BBBottom = BBTop + boundingBoxJSON.get("Height")

    return ((BBLeft + BBRight) / 2, (BBTop + BBBottom) / 2)

# using the pixel array, finds the average RGB value of the first 75 rows
def getAverageBackgroundColor(pixelArray):
    rSum = 0
    gSum = 0
    bSum = 0
    rNum = 0
    gNum = 0
    bNum = 0

    for i in range(75):
        for pixel in pixelArray[i]:
            rSum += pixel[0]
            gSum += pixel[1]
            bSum += pixel[2]
            rNum += 1
            gNum += 1
            bNum += 1

    rAverage = rSum / rNum
    gAverage = gSum / gNum
    bAverage = bSum / bNum

    return [rAverage, gAverage, bAverage]

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

    # for MYSA
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

# finds the top og the hair by comparing average RGB values to RGB values going down the image
def findTopOfHair(pixelArray, boundingBox, bg_type, averageToCrop, averageBackgroundColor, folder, imageName):

    # uses width of head to make average despairities easier to find
    leftBBInPixels = (int)(pixelArray.shape[1] * boundingBox.get("Left"))
    rigthBBInPixels = (int)(
        (pixelArray.shape[1] * boundingBox.get("Left")) + (pixelArray.shape[1] * boundingBox.get("Width")))
    BBWidth = rigthBBInPixels - leftBBInPixels

    # for blue backgrounds
    if bg_type == 0:
        # print("blue top")
        rowNum = 0
        for row in pixelArray:
            rSum = 0
            gSum = 0
            bSum = 0
            for i in range(leftBBInPixels, rigthBBInPixels):
                rSum += row[i][0]
                gSum += row[i][1]
                bSum += row[i][2]
            # print(bSum)
            # print(BBWidth)
            tempRowAverage = [rSum / BBWidth, gSum / BBWidth, bSum / BBWidth]
            # print(tempRowAverage)

            rgb = sRGBColor(tempRowAverage[0], tempRowAverage[1], tempRowAverage[2])
            xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
            lab = convert_color(xyz, LabColor).get_value_tuple()

            tempRowAverageLab = [lab[0], lab[1], lab[2]]
            tempRowAverageLab[0] = round(int(tempRowAverageLab[0]) / 100)
            tempRowAverageLab[1] = round(int(tempRowAverageLab[1]) / 100)
            tempRowAverageLab[2] = round(int(tempRowAverageLab[2]) / 100)

            rowNum += 1

            # Writes line color averages to a CSV
            d = open(folder + "/" + "linedata.csv", "a")
            d.write(
                str(imageName) + ',' + str(rowNum) + ',' + str(round(tempRowAverage[0])) + ',' + str(
                    round(tempRowAverage[1])) + ',' + str(round(tempRowAverage[2])) + ',' +
                str(round(tempRowAverageLab[0])) + ',' + str(round(tempRowAverageLab[1])) + ',' + str(
                    round(tempRowAverageLab[2])) + '\n')
            d.close()

            if (tempRowAverage[2] < 110):
                print("Blue break on " + str(rowNum))
                if rowNum < 75:
                    rowNum = (boundingBox.get("Top") * 480) - 22
                break
            if (tempRowAverage[0] > 105 and tempRowAverage[1] > 105 and tempRowAverage[2] > 105):
                print("All break on " + str(rowNum))
                if rowNum < 75:
                    rowNum = (boundingBox.get("Top") * 480) - 22
                break

    # for grey backgrounds
    elif bg_type == 1:
        #print("grey top")
        averageBackgroundColorTotal = averageBackgroundColor[0] + averageBackgroundColor[1] + averageBackgroundColor[2]
        averageBackgroundColorTotalP = averageBackgroundColorTotal + 80
        averageBackgroundColorTotalM = averageBackgroundColorTotal - 80
        rowNum = 0

        # totalbreak loop
        for row in pixelArray:
            rSum = 0
            gSum = 0
            bSum = 0
            totalDiff = 0
            totalbreak = 0
            for i in range(leftBBInPixels, rigthBBInPixels):
                rSum += row[i][0]
                gSum += row[i][1]
                bSum += row[i][2]
            tempRowAverage = [rSum / BBWidth, gSum / BBWidth, bSum / BBWidth]
            tempRowAverageTotal = tempRowAverage[0] + tempRowAverage[1] + tempRowAverage[2]
            for j in range(3):
                totalDiff += abs(averageBackgroundColor[j] - tempRowAverage[j])

            rgb = sRGBColor(tempRowAverage[0], tempRowAverage[1], tempRowAverage[2])
            xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
            lab = convert_color(xyz, LabColor).get_value_tuple()

            tempRowAverageLab = [lab[0], lab[1], lab[2]]
            tempRowAverageLab[0] = round(int(tempRowAverageLab[0]) / 100)
            tempRowAverageLab[1] = round(int(tempRowAverageLab[1]) / 100)
            tempRowAverageLab[2] = round(int(tempRowAverageLab[2]) / 100)

            rowNum += 1

            if (tempRowAverageTotal > averageBackgroundColorTotalP or
                    tempRowAverageTotal < averageBackgroundColorTotalM):
                totalbreak = rowNum
                break

        # redbreak loop
        for row in pixelArray:
            rSum = 0
            gSum = 0
            bSum = 0
            totalDiff = 0
            redbreak = 0
            for i in range(leftBBInPixels, rigthBBInPixels):
                rSum += row[i][0]
                gSum += row[i][1]
                bSum += row[i][2]
            tempRowAverage = [rSum / BBWidth, gSum / BBWidth, bSum / BBWidth]
            tempRowAverageTotal = tempRowAverage[0] + tempRowAverage[1] + tempRowAverage[2]
            for j in range(3):
                totalDiff += abs(averageBackgroundColor[j] - tempRowAverage[j])

            rgb = sRGBColor(tempRowAverage[0], tempRowAverage[1], tempRowAverage[2])
            xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
            lab = convert_color(xyz, LabColor).get_value_tuple()

            tempRowAverageLab = [lab[0], lab[1], lab[2]]
            tempRowAverageLab[0] = round(int(tempRowAverageLab[0]) / 100)
            tempRowAverageLab[1] = round(int(tempRowAverageLab[1]) / 100)
            tempRowAverageLab[2] = round(int(tempRowAverageLab[2]) / 100)

            rowNum += 1

            if (tempRowAverage[0] > averageBackgroundColor[0] + 25 or
                    tempRowAverage[0] < averageBackgroundColor[0] - 25):
                redbreak = rowNum
                break

        # find if totalbreak or redbreak is closer to head
        print("Top of head: " + str(boundingBox.get("Top") * 480))
        totalbreakDif = (boundingBox.get("Top") * 480) - totalbreak
        if totalbreakDif < 0:
            totalbreakDif = 999
        print("Totalbreak: " + str(totalbreak))
        redbreakDif = (boundingBox.get("Top") * 480) - redbreak
        if redbreakDif < 0:
            redbreakDif = 999
        print("Redbreak: " + str(redbreak))

        # chooses which break to use for cropping
        if totalbreakDif > redbreakDif and redbreakDif != 999 and redbreakDif < 40:
            rowNum = redbreak - 10
            print("Using redbreak... ")
        elif totalbreakDif < redbreakDif and totalbreakDif != 999 and totalbreakDif < 40:
            rowNum = totalbreak - 10
            print("Using totalbreak... ")
        else:
            rowNum = int((boundingBox.get("Top") * 480) - 40)
            print("Using boundingbox...")

    # for greenscreen backgrounds
    elif bg_type == 2:
        #print("green top")
        rowNum = 0
        for row in pixelArray:
            rSum = 0
            gSum = 0
            bSum = 0
            redDiff = 0
            greenDiff = 0
            for i in range(leftBBInPixels, rigthBBInPixels):
                rSum += row[i][0]
                gSum += row[i][1]
                bSum += row[i][2]
            tempRowAverage = [rSum / BBWidth, gSum / BBWidth, bSum / BBWidth]
            redDiff += abs(averageBackgroundColor[0] - tempRowAverage[0])
            greenDiff += abs(averageBackgroundColor[1] - tempRowAverage[1])

            rgb = sRGBColor(tempRowAverage[0], tempRowAverage[1], tempRowAverage[2])
            xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
            lab = convert_color(xyz, LabColor).get_value_tuple()

            tempRowAverageLab = [lab[0], lab[1], lab[2]]
            tempRowAverageLab[0] = round(int(tempRowAverageLab[0]) / 100)
            tempRowAverageLab[1] = round(int(tempRowAverageLab[1]) / 100)
            tempRowAverageLab[2] = round(int(tempRowAverageLab[2]) / 100)

            rowNum += 1

            # Writes line color averages to a CSV
            d = open(folder + "/" + "linedata.csv", "a")
            d.write(
                str(imageName) + ',' + str(rowNum) + ',' + str(round(tempRowAverage[0])) + ',' + str(
                    round(tempRowAverage[1])) + ',' + str(round(tempRowAverage[2])) + ',' +
                str(round(tempRowAverageLab[0])) + ',' + str(round(tempRowAverageLab[1])) + ',' + str(
                    round(tempRowAverageLab[2])) + '\n')
            d.close()

            if (greenDiff > averageToCrop) or (redDiff > 50):
                rowNum += 15
                break

    # for MYSA
    elif bg_type == 3:
        rowNum = int((boundingBox.get("Top") * 480) - 40)

    # defines hair position percent by the row / total rows
    hairPosition = rowNum / pixelArray.shape[0]

    return hairPosition

# makes XMP file for CR2
def makeXMP(cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, path):
    f_tmp = open(path + '_tmp', 'w')

    # goes line by line until 'HasCrop' is found
    with open(path, 'r') as f:
        for line in f:
            if "HasCrop" in line:
                f_tmp.write("   crs:CropTop=\"{}\"\n".format(cropLeft))
                f_tmp.write("   crs:CropLeft=\"{}\"\n".format(1 - cropCoordsTop))
                f_tmp.write("   crs:CropBottom=\"{}\"\n".format(cropRight))
                f_tmp.write("   crs:CropRight=\"{}\"\n".format(1 - cropCoordsBottom))
                f_tmp.write("   crs:CropAngle=\"0\"\n")
                f_tmp.write("   crs:CropConstrainToWarp=\"1\"\n")
                f_tmp.write("   crs:CropWidth=\"4\"\n")
                f_tmp.write("   crs:CropHeight=\"5\"\n")
                f_tmp.write("   crs:CropUnit=\"3\"\n")
                f_tmp.write("   crs:HasCrop=\"True\"\n")
            else:
                f_tmp.write(line)

    f.close()
    f_tmp.close()
    remove(path)
    rename(path + '_tmp', path)

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
    # var for dark kids so they don't lose area on skin tones
    BBAreaDark = BBArea

    # compares read in pixels to average value row by row until it finds an average bigger than averageToCrop
    rowNum = 0
    rSum = 0
    gSum = 0
    bSum = 0
    for row in pixelArray[topBBInPixels:bottomBBInPixels:1]:
        for i in range(leftBBInPixels, rigthBBInPixels):

            # Ensures green background isn't added to skin color
            if row[i][0] < 100 and row[i][1] > 100 and row[i][2] < 100:
                BBArea = BBArea - 1
                BBAreaDark = BBAreaDark - 1

            # Clears out dark hair values
            elif row[i][0] < 50 and row[i][1] < 50 and row[i][2] < 50:
                BBArea = BBArea - 1

            else:
                rSum += row[i][0]
                gSum += row[i][1]
                bSum += row[i][2]
                rowNum += 1

    skinAverage = [rSum / BBArea, gSum / BBArea, bSum / BBArea]
    darkSkinAverage = [rSum / BBAreaDark, gSum / BBAreaDark, bSum / BBAreaDark]

    #print(skinAverage)
    return skinAverage

# applies the shoob default color corrections
def defaultColor(path, params, bgtype):
    f_tmp = open(path + '_tmp', 'w')

    # blue parameters
    if bgtype == 0:
        sat = params[24]
        lum = params[25]
        ParamD = params[26]
        ParamH = params[27]
        ParamL = params[28]
        ParamS = params[29]
        white = params[2]
        black = params[3]
        high = params[51]
        shad = params[52]

    # gray parameters
    elif bgtype == 1:
        sat = params[30]
        lum = params[31]
        ParamD = params[32]
        ParamH = params[33]
        ParamL = params[34]
        ParamS = params[35]
        white = params[6]
        black = params[7]
        high = params[53]
        shad = params[54]

    # green parameters
    else:
        sat = params[36]
        lum = params[37]
        ParamD = params[38]
        ParamH = params[39]
        ParamL = params[40]
        ParamS = params[41]
        white = params[10]
        black = params[11]
        high = params[55]
        shad = params[56]


    # goes line by line until 'HasCrop' is found
    with open(path, 'r') as f:
        for line in f:
            if "HasSettings" in line:
                f_tmp.write("   crs:Version=\"11.2\"\n")
                f_tmp.write("   crs:ProcessVersion=\"11.0\"\n")
                f_tmp.write("   crs:WhiteBalance=\"Custom\"\n")
                f_tmp.write("   crs:Temperature=\"4937\"\n")
                f_tmp.write("   crs:Tint=\"+5.2\"\n")
                f_tmp.write("   crs:Saturation=\"" + str(sat) + "\"\n")
                f_tmp.write("   crs:Sharpness=\"40\"\n")
                f_tmp.write("   crs:LuminanceSmoothing=\"0\"\n")
                f_tmp.write("   crs:ColorNoiseReduction=\"25\"\n")
                f_tmp.write("   crs:VignetteAmount=\"0\"\n")
                f_tmp.write("   crs:ShadowTint=\"0\"\n")
                f_tmp.write("   crs:RedHue=\"0\"\n")
                f_tmp.write("   crs:RedSaturation=\"0\"\n")
                f_tmp.write("   crs:GreenHue=\"0\"\n")
                f_tmp.write("   crs:GreenSaturation=\"0\"\n")
                f_tmp.write("   crs:BlueHue=\"0\"\n")
                f_tmp.write("   crs:BlueSaturation=\"0\"\n")
                f_tmp.write("   crs:Vibrance=\"5\"\n")
                f_tmp.write("   crs:HueAdjustmentRed=\"0\"\n")
                f_tmp.write("   crs:HueAdjustmentOrange=\"0\"\n")
                f_tmp.write("   crs:HueAdjustmentYellow=\"0\"\n")
                f_tmp.write("   crs:HueAdjustmentGreen=\"0\"\n")
                f_tmp.write("   crs:HueAdjustmentAqua=\"0\"\n")
                f_tmp.write("   crs:HueAdjustmentBlue=\"0\"\n")
                f_tmp.write("   crs:HueAdjustmentPurple=\"0\"\n")
                f_tmp.write("   crs:HueAdjustmentMagenta=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentRed=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentOrange=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentYellow=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentGreen=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentAqua=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentBlue=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentPurple=\"0\"\n")
                f_tmp.write("   crs:SaturationAdjustmentMagenta=\"0\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentRed=\"0\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentOrange=\"" + str(lum) + "\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentYellow=\"0\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentGreen=\"0\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentAqua=\"0\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentBlue=\"0\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentPurple=\"0\"\n")
                f_tmp.write("   crs:LuminanceAdjustmentMagenta=\"0\"\n")
                f_tmp.write("   crs:SplitToningShadowHue=\"0\"\n")
                f_tmp.write("   crs:SplitToningShadowSaturation=\"0\"\n")
                f_tmp.write("   crs:SplitToningHighlightHue=\"0\"\n")
                f_tmp.write("   crs:SplitToningHighlightSaturation=\"0\"\n")
                f_tmp.write("   crs:SplitToningBalance=\"0\"\n")
                f_tmp.write("   crs:ParametricShadows=\"" + str(ParamS) + "\"\n")
                f_tmp.write("   crs:ParametricDarks=\"" + str(ParamD) + "\"\n")
                f_tmp.write("   crs:ParametricLights=\"" + str(ParamL) + "\"\n")
                f_tmp.write("   crs:ParametricHighlights=\"" + str(ParamH) + "\"\n")
                f_tmp.write("   crs:ParametricShadowSplit=\"25\"\n")
                f_tmp.write("   crs:ParametricMidtoneSplit=\"50\"\n")
                f_tmp.write("   crs:ParametricHighlightSplit=\"75\"\n")
                f_tmp.write("   crs:SharpenRadius=\"+1.0\"\n")
                f_tmp.write("   crs:SharpenDetail=\"25\"\n")
                f_tmp.write("   crs:SharpenEdgeMasking=\"0\"\n")
                f_tmp.write("   crs:PostCropVignetteAmount=\"0\"\n")
                f_tmp.write("   crs:GrainAmount=\"0\"\n")
                f_tmp.write("   crs:ColorNoiseReductionDetail=\"50\"\n")
                f_tmp.write("   crs:ColorNoiseReductionSmoothness=\"50\"\n")
                f_tmp.write("   crs:LensProfileEnable=\"0\"\n")
                f_tmp.write("   crs:LensManualDistortionAmount=\"0\"\n")
                f_tmp.write("   crs:PerspectiveVertical=\"0\"\n")
                f_tmp.write("   crs:PerspectiveHorizontal=\"0\"\n")
                f_tmp.write("   crs:PerspectiveRotate=\"0.0\"\n")
                f_tmp.write("   crs:PerspectiveScale=\"100\"\n")
                f_tmp.write("   crs:PerspectiveAspect=\"0\"\n")
                f_tmp.write("   crs:PerspectiveUpright=\"0\"\n")
                f_tmp.write("   crs:PerspectiveX=\"0.00\"\n")
                f_tmp.write("   crs:PerspectiveY=\"0.00\"\n")
                f_tmp.write("   crs:AutoLateralCA=\"0\"\n")
                f_tmp.write("   crs:Exposure2012=\"+0.379\"\n")
                f_tmp.write("   crs:Contrast2012=\"0\"\n")
                f_tmp.write("   crs:Highlights2012=\"" + str(high) + "\"\n")
                f_tmp.write("   crs:Shadows2012=\"" + str(shad) + "\"\n")
                f_tmp.write("   crs:Whites2012=\"" + str(white) + "\"\n")
                f_tmp.write("   crs:Blacks2012=\"" + str(black) + "\"\n")
                f_tmp.write("   crs:Clarity2012=\"0\"\n")
                f_tmp.write("   crs:DefringePurpleAmount=\"0\"\n")
                f_tmp.write("   crs:DefringePurpleHueLo=\"30\"\n")
                f_tmp.write("   crs:DefringePurpleHueHi=\"70\"\n")
                f_tmp.write("   crs:DefringeGreenAmount=\"0\"\n")
                f_tmp.write("   crs:DefringeGreenHueLo=\"40\"\n")
                f_tmp.write("   crs:DefringeGreenHueHi=\"60\"\n")
                f_tmp.write("   crs:Dehaze=\"0\"\n")
                f_tmp.write("   crs:ToneMapStrength=\"0\"\n")
                f_tmp.write("   crs:ConvertToGrayscale=\"False\"\n")
                f_tmp.write("   crs:OverrideLookVignette=\"False\"\n")
                f_tmp.write("   crs:ToneCurveName=\"Medium Contrast\"\n")
                f_tmp.write("   crs:ToneCurveName2012=\"Linear\"\n")
                f_tmp.write("   crs:CameraProfile=\"Adobe Portrait\"\n")
                f_tmp.write("   crs:CameraProfileDigest=\"41F68367DA3B31B07AB631D81D0E942D\"\n")
                f_tmp.write("   crs:LensProfileSetup=\"LensDefaults\"\n")
                f_tmp.write("   crs:UprightVersion=\"151388160\"\n")
                f_tmp.write("   crs:UprightCenterMode=\"0\"\n")
                f_tmp.write("   crs:UprightCenterNormX=\"0.5\"\n")
                f_tmp.write("   crs:UprightCenterNormY=\"0.5\"\n")
                f_tmp.write("   crs:UprightFocalMode=\"0\"\n")
                f_tmp.write("   crs:UprightFocalLength35mm=\"35\"\n")
                f_tmp.write("   crs:UprightPreview=\"False\"\n")
                f_tmp.write("   crs:UprightTransformCount=\"6\"\n")
                f_tmp.write("   crs:UprightFourSegmentsCount=\"0\"\n")
                f_tmp.write("   crs:HasSettings=\"True\"\n")
            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()

    remove(path)
    rename(path + '_tmp', path)

# colors based on school averages
def schoolColor(path, Lval, aval, bval, bg_type, params, expPercentDiff, iLval, iaval, ibval):
    adiff = 0
    bdiff = 15 - bval
    Lchange = iLval * (1 + expPercentDiff)

    # sets XMP values based on if the background is blue grey or green
    # blue
    if bg_type == 0:
        if params[50] == 1:
            exp = ((params[12] - Lval) / 20)
        else:
            exp = ((params[12] - Lchange) / 20)
        temper = (params[0] + (bdiff * 100))
        tint = (params[1] + adiff)
        wh = params[2]
        bl = params[3]

    # grey
    elif bg_type == 1:
        if params[50] == 1:
            exp = ((params[13] - Lval) / 20)
        else:
            exp = ((params[13] - Lchange) / 20)
        temper = (params[4] + (bdiff * 100))
        tint = (params[5] + adiff)
        wh = params[6]
        bl = params[7]

    # green
    else:
        if params[50] == 1:
            exp = ((params[14] - Lval) / 20)
            print("old")
        else:
            exp = ((params[14] - Lchange) / 20)
            print("new")
        print(exp)
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
    rating = 0

    # blue individual color correction
    if bg_type == 0:
        # same tone
        if Lval <= (LvalSchool + 2) and Lval >= (LvalSchool - 2):
            exp = expSchool + params[18]
            temper = temperSchool + params[19]
            tint = tintSchool + params[20]
            tag = ""
        # light
        elif Lval > (LvalSchool + 2):
            exp = expSchool + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
            tag = "Second"
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.15 + params[15] + params[51] + params[18]
            temper = temperSchool + params[16] + params[52]
            tint = tintSchool + params[17] + params[53]
            tag = "Review"
            rating = 1
        # dark
        elif Lval < (LvalSchool - 2):
            exp = expSchool + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]
            tag = "Select"
        # very dark
        else:
            exp = expSchool + 0.15 + params[21] + params[54] + params[18]
            temper = temperSchool + params[22] + params[55]
            tint = tintSchool + params[23] + params[56]
            tag = "Approved"
            rating = 1

    # grey individual color correction
    elif bg_type == 1:
        # same tone
        if Lval <= (LvalSchool + 2) and Lval >= (LvalSchool - 2):
            exp = expSchool + params[18]
            temper = temperSchool + params[19]
            tint = tintSchool + params[20]
            tag = ""
        # light
        elif Lval > (LvalSchool + 2):
            exp = expSchool + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
            tag = "Second"
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.15 + params[15] + params[51] + params[18]
            temper = temperSchool + params[16] + params[52]
            tint = tintSchool + params[17] + params[53]
            tag = "Review"
            rating = 1
        # dark
        elif Lval < (LvalSchool - 2):
            exp = expSchool + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]
            tag = "Select"
        # very dark
        else:
            exp = expSchool + 0.15 + params[21] + params[54] + params[18]
            temper = temperSchool + params[22] + params[55]
            tint = tintSchool + params[23] + params[56]
            tag = "Approved"
            rating = 1

    # green individual color correction
    else:
        # same tone
        if Lval <= (LvalSchool + 2) and Lval >= (LvalSchool - 2):
            exp = expSchool + params[18]
            temper = temperSchool + params[19]
            tint = tintSchool + params[20]
            tag = ""
        # light
        elif Lval > (LvalSchool + 2):
            exp = expSchool + params[15] + params[18]
            temper = temperSchool + params[16]
            tint = tintSchool + params[17]
            tag = "Second"
        # very light
        elif Lval > (LvalSchool + 5):
            exp = expSchool - 0.15 + params[15] + params[51] + params[18]
            temper = temperSchool + params[16] + params[52]
            tint = tintSchool + params[17] + params[53]
            tag = "Review"
            rating = 1
        # dark
        elif Lval < (LvalSchool - 2):
            exp = expSchool + params[21] + params[18]
            temper = temperSchool + params[22]
            tint = tintSchool + params[23]
            tag = "Select"
        # very dark
        else:
            exp = expSchool + 0.15 + params[21] + params[54] + params[18]
            temper = temperSchool + params[22] + params[55]
            tint = tintSchool + params[23] + params[56]
            tag = "Approved"
            rating = 1

    f_tmp = open(path + '_tmp', 'w')

    with open(path, 'r') as f:
        for line in f:
            if "crs:Exposure2012=" in line:
                f_tmp.write("   crs:Exposure2012=\"" + str(exp) + "\"\n")
            elif "crs:Temperature" in line:
                f_tmp.write("   crs:Temperature=\"" + str(temper) + "\"\n")
            elif "crs:Tint" in line:
                f_tmp.write("   crs:Tint=\"" + str(tint) + "\"\n")
            elif "xmp:Label" in line:
                f_tmp.write("   xmp:Label=\"" + str(tag) + "\"\n")
                print(tag)
            elif "xmp:Rating" in line:
                f_tmp.write("   xmp:Rating=\"" + str(rating) + "\"\n")
                print(rating)
            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()
        remove(path)
        rename(path + '_tmp', path)

    return

# copies crop info to data.csv
def printInformation(imgName, hairCoords, cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, folder):
    d = open(folder + "/" + "data.csv", "a")
    d.write(str(imgName) + ',' + str(hairCoords) + ',' + str(cropCoordsTop) + ',' + str(cropCoordsBottom) + ',' +
            str(cropLeft) + ',' + str(cropRight) + '\n')
    d.close()

# copies color info to colordata.csv
def printColorInformation(imgName, tone, lab, lab2, folder):
    d = open(folder + "/" + "colordata.csv", "a")
    d.write(str(imgName) + ',' + str(round(tone[0])) + ',' + str(round(tone[1])) + ',' +str(round(tone[2])) + ',' +
            str(lab[0]) + ',' + str(lab[1]) + ',' + str(lab[2]) + ',' + str(lab2[5]) + ',' +
            str(lab[1]) + ',' + str(lab[2]) + ',' + str(lab[0] - lab2[5]) + '\n')
    d.close()


# runs main
if __name__ == '__main__':
    main()
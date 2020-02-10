# IMPORTS---------------------------------------------------------------------------------------------------------------
import json
from os import rename, remove
import os.path
import PIL.Image
from PIL import Image, ImageFilter, ImageShow
import PIL.Image
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
from psd_tools import PSDImage
from matplotlib import pyplot
from mpl_toolkits.mplot3d import Axes3D
import random
import csv
np.set_printoptions(threshold=sys.maxsize)


# XMP FILE DIRECTIONS DON'T CORRESPOND TO WHAT YOU THINK:
#   LEFT SIDE OF IMAGE => XMP TOP
#   TOP OF IMAGE => XMP RIGHT
#   RIGHT SIDE OF IMAGE => XMP BOTTOM
#   BOTTOM OF IMAGE => XMP LEFT
#   BOTTOM LEFT OF IMAGE IS (0,0)


# CLASS DEFINITIONS-----------------------------------------------------------------------------------------------------
#   class for image
class myImg(object):

    def __init__(self, name, JSON, pixelArray, params, selects, csvData):
        leftBound = JSON.get("Left")
        rightBound = leftBound + JSON.get("Width")
        topBound = JSON.get("Top")
        bottomBound= topBound + JSON.get("Height")
        self.name = name

        if "spr" in self.name:
            self.seasonNum = 24
        else:
            self.seasonNum = 23

        self.nameNoExt = self.name[-self.seasonNum:].replace('.jpg', '')
        print("no ext: " + str(self.nameNoExt))

        if selects == False:
            self.selected = False
            self.xmpFolder = self.name[:-self.seasonNum].replace('_JPG_CROP', '')
        else:
            self.selected = True
            self.xmpFolder = self.name[:-self.seasonNum].replace('_JPG_CROP', '/Selects')
        print("xmpFolder: " + str(self.xmpFolder))

        self.jpgFolder = self.name[:-self.seasonNum]
        print("jpgFolder: " + str(self.jpgFolder))

        self.pixelArray = pixelArray
        self.filetype = self.findFiletype()
        self.background = 'green'

        #   values in percent
        self.leftBoundPercent = leftBound
        self.rightBoundPercent = rightBound
        self.topBoundPercent = topBound
        self.bottomBoundPercent = bottomBound

        self.widthPercent = rightBound - leftBound
        self.heightPercent = bottomBound - topBound
        self.centerPercent = self.findCenter()

        #   values in pixels
        self.leftBoundPixel = int(pixelArray.shape[1] * leftBound)
        self.rightBoundPixel = int((pixelArray.shape[1] * leftBound) + (pixelArray.shape[1] * JSON.get("Width")))
        self.topBoundPixel = int(pixelArray.shape[0] * topBound)
        self.bottomBoundPixel = int(pixelArray.shape[0] * bottomBound)

        self.widthPixel = self.rightBoundPixel - self.leftBoundPixel
        self.heightPixel = self.bottomBoundPixel - self.topBoundPixel

        self.areaPixel = self.widthPixel * self.heightPixel

        #   hair value
        self.hairPercent = self.findHair()

        #   determine distance of shot
        for x in csvData:
            if self.nameNoExt in x[0]:
                self.dist = x[1]
                break

        print(self.dist)

        if self.dist == "close":          # headshot
            aboveHead = params.aboveHead
            belowChin = params.belowChin
        elif self.dist == "mid":          # mid
            aboveHead = params.midHead
            belowChin = params.midChin
        else:                             # standing
            aboveHead = params.farHead
            belowChin = params.farChin

        #   crop values
        self.cropCoordsTopPercent = self.hairPercent - aboveHead
        self.cropCoordsBottomPercent = self.bottomBoundPercent + belowChin

        self.cropHeightPercent = self.cropCoordsBottomPercent - self.cropCoordsTopPercent
        self.cropHeightPixel = self.cropHeightPercent * self.pixelArray.shape[0]
        self.cropWidthPixel = (self.cropHeightPixel / 5) * 4
        self.cropWidthPercent = self.cropWidthPixel / self.pixelArray.shape[1]
        self.cropLeftPercent = self.centerPercent[0] - (self.cropWidthPercent / 2)
        self.cropRightPercent = self.centerPercent[0] + (self.cropWidthPercent / 2)

        if self.cropLeftPercent < 0:
            self.cropLeftPercent = 0
        if self.cropLeftPercent > 1:
            self.cropLeftPercent = 1

        if self.cropRightPercent > 1:
            self.cropRightPercent = 1
        if self.cropRightPercent < 0:
            self.cropRightPercent = 0

        if self.cropCoordsTopPercent > 1:
            self.cropCoordsTopPercent = 1
        if self.cropCoordsTopPercent < 0:
            self.cropCoordsTopPercent = 0

        if self.cropCoordsBottomPercent > 1:
            self.cropCoordsBottomPercent = 1
        if self.cropCoordsBottomPercent < 0:
            self.cropCoordsBottomPercent = 0

        #   color values
        self.RGB = self.skinToneAverage()
        self.Lab = self.RGBtoLab()
        self.modifiedLab = self.modifyLab()  # modified Lab is the value post-fudging

    #   finds the raw filetype being used
    def findFiletype(self):
        ARWpath = self.name.replace('_JPG_CROP', '').replace('.jpg', '.arw')
        CR2path = self.name.replace('_JPG_CROP', '').replace('.jpg', '.cr2')

        if os.path.exists(CR2path):
            filetype = "CR2"
        elif os.path.exists(ARWpath):
            filetype = "ARW"
        else:
            filetype = "ERROR"

        if filetype != 'ERROR':
            print("filetype: " + filetype)

        return filetype


    #   finds centerpoint of image
    def findCenter(self):
        return ((self.leftBoundPercent + self.rightBoundPercent) / 2,
                (self.topBoundPercent + self.bottomBoundPercent) / 2)


    #   finds avergae skin tone colors as RGB
    def skinToneAverage(self):
        self.RGB = []
        #   var for dark kids so they don't lose area on skin tones
        areaDarkPixel = self.areaPixel

        #   compares read in pixels to average value row by row until it finds an average bigger than averageToCrop
        rowNum = 0
        rSum = 0
        gSum = 0
        bSum = 0

        for row in self.pixelArray[self.topBoundPixel:self.bottomBoundPixel:1]:
            for i in range(self.leftBoundPixel, self.rightBoundPixel):

                #   ensures green background isn't added to skin color
                if row[i][0] < 100 and row[i][1] > 100 and row[i][2] < 100:
                    self.areaPixel = self.areaPixel - 1
                    areaDarkPixel = areaDarkPixel - 1

                #   if color is not green, add it to the total
                else:
                    rSum += row[i][0]
                    gSum += row[i][1]
                    bSum += row[i][2]
                    rowNum += 1

        r = rSum / self.areaPixel
        g = gSum / self.areaPixel
        b = bSum / self.areaPixel
        self.RGB.append(r)
        self.RGB.append(g)
        self.RGB.append(b)

        skinAverage = [r, g, b]
        darkSkinAverage = [rSum /areaDarkPixel, gSum / areaDarkPixel, bSum / areaDarkPixel]

        #print(skinAverage)
        return skinAverage


    def RGBtoLab(self):
        #   uses mathColor to convert between RGB and Lab values
        rgb = sRGBColor(self.RGB[0], self.RGB[1], self.RGB[2])
        xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
        lab = convert_color(xyz, LabColor).get_value_tuple()

        #   converts lab values into workable numbers
        self.Lab = [lab[0], lab[1], lab[2]]
        self.Lab[0] = int(self.Lab[0]) / 100
        self.Lab[1] = int(self.Lab[1]) / 100
        self.Lab[2] = int(self.Lab[2]) / 100

        return self.Lab


    def modifyLab(self):
        L = self.Lab[0]
        a = self.Lab[1] + 1.62  # 1.62 a fudging constant
        b = self.Lab[2] + 2.88  # 2.88 b fudging constant

        return [L, a, b]


    #   crops code to just face for color correcting tests
    def cropAmazonFace(self):
        saveExtension = self.name[-self.seasonNum:].replace('.jpg', '_crop.jpg')
        saveLocation = self.jpgFolder + '_faceCropped\\'

        if not os.path.exists(saveLocation):
            os.makedirs(saveLocation)

        saveLocation = saveLocation + saveExtension

        imageObj = PIL.Image.open(self.name)
        croppedImage = imageObj.crop((self.leftBoundPixel, self.topBoundPixel,
                                      self.rightBoundPixel, self.bottomBoundPixel))
        croppedImage.save(saveLocation)
        #croppedImage.show()

        return


    #   finds top of hair
    def findHair(self):
        folder = self.xmpFolder
        rowValues = []
        rowNum = 0

        for row in self.pixelArray:
            convertedLab = []
            rSum = 0
            gSum = 0
            bSum = 0

            for pixel in range(self.leftBoundPixel, self.rightBoundPixel):
                rSum += row[pixel][0]
                gSum += row[pixel][1]
                bSum += row[pixel][2]

            rAvg = rSum/self.widthPixel
            gAvg = gSum/self.widthPixel
            bAvg = bSum/self.widthPixel

            rgb = sRGBColor(rAvg, gAvg, bAvg)
            xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
            lab = convert_color(xyz, LabColor).get_value_tuple()

            convertedLab.append(round(int(lab[0] / 100)))
            convertedLab.append(round(int(lab[1] / 100)))
            convertedLab.append(round(int(lab[2] / 100)))

            rowData = [rowNum, convertedLab[0], convertedLab[1], convertedLab[2]]
            #print("rowdata: " + str(rowData))

            #   writes line color averages to a CSV
            d = open(folder + "linedata.csv", "a")
            d.write(str(self.name) + ',' + str(rowData[0]) + ',' + str(rowData[1]) + ',' + str(rowData[2]) + ',' +
                    str(rowData[3]) + '\n')
            d.close()

            rowValues.append(rowData)
            rowNum += 1

            if (convertedLab[1] > -25 and rowNum > 25):
                rowNum += 1
                break

        hairPercent = rowNum / self.pixelArray.shape[0]

        return hairPercent


#   class for parameters
class parameters(object):

    def __init__(self, file):
        self.file = file

        #   blue parameters
        self.blueL = self.readFile()[0]
        self.blueA = self.readFile()[1]
        self.blueB = self.readFile()[2]
        self.blueWhites = self.readFile()[3]
        self.blueBlacks = self.readFile()[4]
        self.blueHighlights = self.readFile()[5]
        self.blueShadows = self.readFile()[6]
        self.blueSaturation = self.readFile()[7]

        #   grey parameters
        self.greyL = self.readFile()[8]
        self.greyA = self.readFile()[9]
        self.greyB = self.readFile()[10]
        self.greyWhites = self.readFile()[11]
        self.greyBlacks = self.readFile()[12]
        self.greyHighlights = self.readFile()[13]
        self.greyShadows = self.readFile()[14]
        self.greySaturation = self.readFile()[15]

        #   green parameters
        self.greenL = self.readFile()[16]
        self.greenA = self.readFile()[17]
        self.greenB = self.readFile()[18]
        self.greenWhites = self.readFile()[19]
        self.greenBlacks = self.readFile()[20]
        self.greenHighlights = self.readFile()[21]
        self.greenShadows = self.readFile()[22]
        self.greenSaturation = self.readFile()[23]

        #   crop parameters
        self.aboveHead = self.readFile()[24]
        self.belowChin = self.readFile()[25]
        self.midHead = self.readFile()[26]
        self.midChin = self.readFile()[27]
        self.farHead = self.readFile()[28]
        self.farChin = self.readFile()[29]


    def readFile(self):
        param_tmp = open(self.file, 'r')

        with param_tmp as f:
            for line in f:

                #   blue
                if "blueL!" in line:
                    blueL = float(line.replace('blueL! = ', '').replace('\n', ''))
                elif "blueA!" in line:
                    blueA = float(line.replace('blueA! = ', '').replace('\n', ''))
                elif "blueB!" in line:
                    blueB = float(line.replace('blueB! = ', '').replace('\n', ''))
                elif "blueWhites" in line:
                    blueWhites = float(line.replace('blueWhites = ', '').replace('\n', ''))
                elif "blueBlacks" in line:
                    blueBlacks = float(line.replace('blueBlacks = ', '').replace('\n', ''))
                elif "blueHighlights" in line:
                    blueHighlights = float(line.replace('blueHighlights = ', '').replace('\n', ''))
                elif "blueShadows" in line:
                    blueShadows = float(line.replace('blueShadows = ', '').replace('\n', ''))
                elif "blueSaturation" in line:
                    blueSaturation = float(line.replace('blueSaturation = ', '').replace('\n', ''))

                #   grey
                if "greyL!" in line:
                    greyL = float(line.replace('greyL! = ', '').replace('\n', ''))
                elif "greyA!" in line:
                    greyA = float(line.replace('greyA! = ', '').replace('\n', ''))
                elif "greyB!" in line:
                    greyB = float(line.replace('greyB! = ', '').replace('\n', ''))
                elif "greyWhites" in line:
                    greyWhites = float(line.replace('greyWhites = ', '').replace('\n', ''))
                elif "greyBlacks" in line:
                    greyBlacks = float(line.replace('greyBlacks = ', '').replace('\n', ''))
                elif "greyHighlights" in line:
                    greyHighlights = float(line.replace('greyHighlights = ', '').replace('\n', ''))
                elif "greyShadows" in line:
                    greyShadows = float(line.replace('greyShadows = ', '').replace('\n', ''))
                elif "greySaturation" in line:
                    greySaturation = float(line.replace('greySaturation = ', '').replace('\n', ''))

                #   green
                if "greenL!" in line:
                    greenL = float(line.replace('greenL! = ', '').replace('\n', ''))
                elif "greenA!" in line:
                    greenA = float(line.replace('greenA! = ', '').replace('\n', ''))
                elif "greenB!" in line:
                    greenB = float(line.replace('greenB! = ', '').replace('\n', ''))
                elif "greenWhites" in line:
                    greenWhites = float(line.replace('greenWhites = ', '').replace('\n', ''))
                elif "greenBlacks" in line:
                    greenBlacks = float(line.replace('greenBlacks = ', '').replace('\n', ''))
                elif "greenHighlights" in line:
                    greenHighlights = float(line.replace('greenHighlights = ', '').replace('\n', ''))
                elif "greenShadows" in line:
                    greenShadows = float(line.replace('greenShadows = ', '').replace('\n', ''))
                elif "greenSaturation" in line:
                    greenSaturation = float(line.replace('greenSaturation = ', '').replace('\n', ''))

                #   crop
                if "aboveHead" in line:
                    aboveHead = float(line.replace('aboveHead = ', '').replace('\n', ''))
                elif "belowChin" in line:
                    belowChin = float(line.replace('belowChin = ', '').replace('\n', ''))
                elif "midHead" in line:
                    midHead = float(line.replace('midHead = ', '').replace('\n', ''))
                elif "midChin" in line:
                    midChin = float(line.replace('midChin = ', '').replace('\n', ''))
                elif "farHead" in line:
                    farHead = float(line.replace('farHead = ', '').replace('\n', ''))
                elif "farChin" in line:
                    farChin = float(line.replace('farChin = ', '').replace('\n', ''))

        f.close()

        return blueL, blueA, blueB, blueWhites, blueBlacks, blueHighlights, blueShadows, blueSaturation, \
               greyL, greyA, greyB, greyWhites, greyBlacks, greyHighlights, greyShadows, greySaturation, \
               greenL, greenA, greenB, greenWhites, greenBlacks, greenHighlights, greenShadows, greenSaturation, \
               aboveHead, belowChin, midHead, midChin, farHead, farChin


# MAIN FUNCTION---------------------------------------------------------------------------------------------------------
def main():
    # CONSTANTS INITIALIZATION------------------------------------------------------------------------------------------
    CONST_PARAM = "J:/_CropScript/parameters.txt"
    CONST_CR2XMP = "J:/_CropScript/CR2template.xmp"
    CONST_ARWXMP = "J:/_CropScript/ARWtemplate.xmp"


    # VARIABLE INITIALIZATION-------------------------------------------------------------------------------------------
    #   defining parameters
    shoobparams = parameters(CONST_PARAM)

    #   for counting JPGs
    countJPG = 0

    #   user selects folder
    selects = False
    pathToFolder = browse_button()
    print("path: " + str(pathToFolder))

    #   provision for handling Selects folders
    if "Selects" in pathToFolder:
        selects = True
        rawList = set()
        pathlistRAW = Path(pathToFolder).glob('**/*.*r*')

        for path in pathlistRAW:
            path = str(path).replace('\Selects', '_JPG_CROP').replace('.arw', '.jpg').replace('.cr2', '.jpg')
            rawList.add(Path(path))

        pathlistJPG = set(rawList)

        #   for defining the pathlist used for iteration
        pathlist = pathlistJPG
        print("pathlist: " + str(pathlist))

    #   if not a Selects folder
    else:
        pathlistJPG = Path(pathToFolder).glob('**/*.jpg')
        print("pathlistJPG: " + str(pathlistJPG))

        #   for defining the pathlist used for iteration
        pathlist = set(Path(pathToFolder).glob('**/*.jpg')) - set(Path(pathToFolder).glob('**/*_crop.jpg'))
        print("pathlist: " + str(pathlist))

    #   for defining color averages
    toneCount = 0
    rTone = 0
    gTone = 0
    bTone = 0

    #   for keeping track of each image object
    imageList = []
    imageListCount = 0

    #   for viewing a 3D scatterplot of data
    fig = pyplot.figure()
    ax = Axes3D(fig)
    ax.set_xlabel('L-axis')
    ax.set_ylabel('a-axis')
    ax.set_zlabel('b-axis')
    xValList = []
    yValList = []
    zValList = []


    # CSV INITIALIZATION------------------------------------------------------------------------------------------------
    #   line CSV
    if selects == False:
        f = open(pathToFolder.replace('_JPG_CROP', '') + "/" + "linedata.csv", "w")
        f.write('image,' + 'row,' + 'L,' + 'a,' + 'b' '\n')
        f.close()

        #   crop CSV
        f = open(pathToFolder.replace('_JPG_CROP', '') + "/" + "cropdata.csv", "w")
        f.write('image,' + 'tophead,' + 'topcrop,' + 'bottomcrop,' + 'leftcrop,' + 'rightcrop,' + 'distance' '\n')
        f.close()

        #   color CSV
        f = open(pathToFolder.replace('_JPG_CROP', '') + "/" + "colordata.csv", "w")
        f.write('image,' + 'R,' + 'G,' + 'B,' + 'L,' + 'a,' + 'b,' + 'modL,' + 'moda,' + 'modb' '\n')
        f.close()

        #   distance CSV
        distCSV = pathToFolder.replace('_JPG_CROP', '') + "/" + "dist.csv"

    else:
        f = open(pathToFolder.replace('_JPG_CROP', '/Selects') + "/" + "linedata.csv", "w")
        f.write('image,' + 'row,' + 'L,' + 'a,' + 'b' '\n')
        f.close()

        #   crop CSV
        f = open(pathToFolder.replace('_JPG_CROP', '/Selects') + "/" + "cropdata.csv", "w")
        f.write('image,' + 'tophead,' + 'topcrop,' + 'bottomcrop,' + 'leftcrop,' + 'rightcrop' '\n')
        f.close()

        #   color CSV
        f = open(pathToFolder.replace('_JPG_CROP', '/Selects') + "/" + "colordata.csv", "w")
        f.write('image,' + 'R,' + 'G,' + 'B,' + 'L,' + 'a,' + 'b,' + 'modL,' + 'moda,' + 'modb' '\n')
        f.close()

        #   distance CSV
        distCSV = pathToFolder.replace('_JPG_CROP', '/Selects') + "/" + "dist.csv"

    distArray = findDist(distCSV)

    # USER INPUT--------------------------------------------------------------------------------------------------------
    #   alerts for user
    print("ALERT: Please make sure all relevant CSV files are closed before running this program")

    #   ensure the correct folder has been selected by counting JPGs
    for path in pathlistJPG:
        countJPG += 1
    if countJPG == 0:
        print("ALERT: It appears you selected the wrong folder. Please try again selecting the _JPG_CROP folder")
        return


    # CROPPING----------------------------------------------------------------------------------------------------------
    for path in pathlist:
        path_in_str = str(path)

        #   defining the paths out of the CSV
        jpgPath = path_in_str
        #print('path to jpg: ' + jpgPath)

        #   opening jpg into pixel array
        pixelArray = openJPG(jpgPath)

        #   makes request to rekognition and grabs JSON return
        faceFeaturesJSON = rekognitionRequest(jpgPath)

        if faceFeaturesJSON != 0:

            #   getting aws rekognition JSON output
            awsMasterOutput = parse_aws_output(faceFeaturesJSON)
            BoundingBoxJSON = awsMasterOutput[0]
            #LandmarksJSON = awsMasterOutput[1]
            #OrientationCorrection = awsMasterOutput[2]

            #   instantiating image object and adding it to a list of images
            shoobimage = myImg(jpgPath, BoundingBoxJSON, pixelArray, shoobparams, selects, distArray)
            imageList.append(shoobimage)
            shoobimage.cropAmazonFace()

            #   creates default XMP and color settings
            defaultXMP(shoobimage, CONST_CR2XMP, CONST_ARWXMP)
            cropXMP(shoobimage)
            defaultColor(shoobimage, shoobparams)

            #   find skin tone
            tone = shoobimage.skinToneAverage()
            toneCount = toneCount + 1
            rTone = rTone + tone[0]
            gTone = gTone + tone[1]
            bTone = bTone + tone[2]

            #   writes cropping CSV
            writeCropCSV(shoobimage)
            print("Cropping " + shoobimage.name)

            #   add data to scatterplot lists
            xValList.append(shoobimage.Lab[0])
            yValList.append(shoobimage.Lab[1])
            zValList.append(shoobimage.Lab[2])

    print("*Cropping Complete*")


    # DATA ANALYSIS-----------------------------------------------------------------------------------------------------
    #   finds average RGB tone for entire school
    toneRGBSchool = [0, 0, 0]
    toneRGBSchool[0] = round(rTone / toneCount)
    toneRGBSchool[1] = round(gTone / toneCount)
    toneRGBSchool[2] = round(bTone / toneCount)
    print("Rig RGB averages:\nR: " + str(toneRGBSchool[0]) + " G: " + str(toneRGBSchool[1]) + " B: " +
          str(toneRGBSchool[2]))

    #   uses mathColor to convert between RGB and Lab values
    rgb = sRGBColor(toneRGBSchool[0], toneRGBSchool[1], toneRGBSchool[2])
    xyz = convert_color(rgb, XYZColor, target_illuminant='d50')
    lab = convert_color(xyz, LabColor).get_value_tuple()

    #   converts lab values into workable numbers
    toneLabSchool = [lab[0], lab[1], lab[2]]
    toneLabSchool[0] = round(int(toneLabSchool[0]) / 100)
    toneLabSchool[1] = round(int(toneLabSchool[1]) / 100)
    toneLabSchool[2] = round(int(toneLabSchool[2]) / 100)
    print("Rig Lab averages:\nL: " + str(toneLabSchool[0]) + " a: " + str(toneLabSchool[1]) + " b: " +
          str(toneLabSchool[2]))

    print("*Data Analysis Complete*")


    # COLOR CORRECTING--------------------------------------------------------------------------------------------------
    for path in imageList:
        print("Color image #" + str(imageListCount))
        shoobimage = imageList[imageListCount]
        print("Color correcting " + str(shoobimage.name))

        colorXMP(shoobimage, shoobparams)

        writeColorCSV(shoobimage.name, shoobimage.RGB, shoobimage.Lab, shoobimage.modifiedLab, shoobimage.xmpFolder)
        imageListCount = imageListCount + 1

    print("*Color Correcting Complete*")


    # TESTING-----------------------------------------------------------------------------------------------------------
    #   3D scatterplot of Lab values
    ax.scatter(xValList, yValList, zValList)
    #pyplot.show()

    print("*Testing Complete*")

    return


# BODY FUNCTIONS--------------------------------------------------------------------------------------------------------
#   use CSV to find distances
def findDist(csvFile):
    datafile = open(csvFile, 'r')
    datareader = csv.reader(datafile)
    data = []
    for row in datareader:
        data.append(row)

    data.sort()
    print("CSV: " + str(data))
    return data


#   folder select button
def browse_button():

    # Allow user to select a directory and store it in global var
    # called folder_path
    global folder_path
    filename = filedialog.askdirectory()
    folder_path.set(filename)
    print(filename)

    return filename


#   TK initialization
root = Tk()
folder_path = StringVar()
lbl1 = Label(master=root, textvariable=folder_path)
lbl1.grid(row=0, column=1)
button2 = Button(text="Select _JPG_CROP folder", command=browse_button)
button2.grid(row=0, column=3)


#   opens JPG and returns RGB pixel array
def openJPG(path):
    im = PIL.Image.open(path)
    pixel_array = np.array(im)

    return pixel_array


#   parses AWS output into an array
def parse_aws_output(JSONResponse):
    awsData = json.loads(json.dumps(JSONResponse))
    BoundingBox = awsData.get("FaceDetails")[0].get("BoundingBox")
    Landmarks = awsData.get("FaceDetails")[0].get("Landmarks")
    OrientationCorrection = awsData.get("OrientationCorrection")

    return [BoundingBox, Landmarks, OrientationCorrection]


#   sends image to rekognition client
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


#   initializes the default XMP
def defaultXMP(image, CR2XMP, ARWXMP):
    filetype = image.filetype
    filename = image.name.replace('.jpg', '')

    if image.selected == False:
        path = image.name.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
    else:
        path = image.name.replace('_JPG_CROP', '/Selects').replace('.jpg', '.xmp')

    #   if file is a CR2
    if filetype == "CR2":
        shutil.copy2(CR2XMP, path)
        f_tmp = open(path + "_tmp", "w")

        with open(path, 'r') as f:
            for line in f:
                if "RawFileName" in line:
                    f_tmp.write("   crs:RawFileName=\"" + filename + "\">\n")
                else:
                    f_tmp.write(line)

    #   if file is an ARW
    elif filetype == "ARW":
        shutil.copy2(ARWXMP, path)
        f_tmp = open(path + "_tmp", "w")

        with open(path, 'r') as f:
            for line in f:
                if "RawFileName" in line:
                    f_tmp.write("   crs:RawFileName=\"" + filename + "\">\n")
                else:
                    f_tmp.write(line)


    #   if file isn't valid RAW
    else:
        print("ERROR CANNOT FIND FILETYPE")
        return

    f.close()
    f_tmp.close()
    remove(path)
    rename(path + '_tmp', path)

    return


#   applies cropping coordinates to XMP
def cropXMP(image):
    if image.selected == False:
        path = image.name.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
    else:
        path = image.name.replace('_JPG_CROP', '/Selects').replace('.jpg', '.xmp')

    f_tmp = open(path + '_tmp', 'w')

    # goes line by line until 'HasCrop' is found
    with open(path, 'r') as f:
        for line in f:
            if "HasCrop" in line:
                f_tmp.write("   crs:CropTop=\"{}\"\n".format(image.cropLeftPercent))
                f_tmp.write("   crs:CropLeft=\"{}\"\n".format(1 - image.cropCoordsTopPercent))
                f_tmp.write("   crs:CropBottom=\"{}\"\n".format(image.cropRightPercent))
                f_tmp.write("   crs:CropRight=\"{}\"\n".format(1 - image.cropCoordsBottomPercent))
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

    return


#   applies the shoob default color corrections
def defaultColor(image, params):
    if image.selected == False:
        path = image.name.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
    else:
        path = image.name.replace('_JPG_CROP', '/Selects').replace('.jpg', '.xmp')

    #   determine params based on background color
    if image.background == "green":
        sat = params.greenSaturation
        high = params.greenHighlights
        shad = params.greenShadows
        wh = params.greenWhites
        bl = params.greenBlacks
    elif image.background == "blue":
        sat = params.blueSaturation
        high = params.blueHighlights
        shad = params.blueShadows
        wh = params.blueWhites
        bl = params.blueBlacks
    else:
        sat = params.greySaturation
        high = params.greyHighlights
        shad = params.greyShadows
        wh = params.greyWhites
        bl = params.greyBlacks

    #   determine star count based on distance
    if image.dist == "close":
        rating = '1'
        label = "Select"
    elif image.dist == "mid":
        rating = '2'
        label = "Second"
    else:
        rating = '3'
        label = "Approved"

    f_tmp = open(path + '_tmp', 'w')

    #   goes line by line until 'HasSettings' is found
    with open(path, 'r') as f:
        for line in f:
            if "HasSettings" in line:
                f_tmp.write("   crs:Version=\"11.2\"\n")
                f_tmp.write("   crs:ProcessVersion=\"11.0\"\n")
                f_tmp.write("   crs:WhiteBalance=\"Custom\"\n")
                f_tmp.write("   crs:Temperature=\"5000\"\n")
                f_tmp.write("   crs:Tint=\"+5\"\n")
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
                f_tmp.write("   crs:LuminanceAdjustmentOrange=\"0\"\n")
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
                f_tmp.write("   crs:ParametricShadows=\"0\"\n")
                f_tmp.write("   crs:ParametricDarks=\"0\"\n")
                f_tmp.write("   crs:ParametricLights=\"0\"\n")
                f_tmp.write("   crs:ParametricHighlights=\"0\"\n")
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
                f_tmp.write("   crs:Exposure2012=\"+0\"\n")
                f_tmp.write("   crs:Contrast2012=\"0\"\n")
                f_tmp.write("   crs:Highlights2012=\"" + str(high) + "\"\n")
                f_tmp.write("   crs:Shadows2012=\"" + str(shad) + "\"\n")
                f_tmp.write("   crs:Whites2012=\"" + str(wh) + "\"\n")
                f_tmp.write("   crs:Blacks2012=\"" + str(bl) + "\"\n")
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
            elif "xmp:Rating" in line:
                f_tmp.write("   xmp:Rating=\"" + rating + "\"\n")
            elif "xmp:Label" in line:
                f_tmp.write("   xmp:Label=\"" + label + "\"\n")
            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()

    remove(path)
    rename(path + '_tmp', path)

    return


#   adds parameter colors to XMP file
def colorXMP(image, params):
    #   initialize all variables
    background = image.background

    if image.selected == False:
        path = image.name.replace('_JPG_CROP', '').replace('.jpg', '.xmp')
    else:
        path = image.name.replace('_JPG_CROP', '/Selects').replace('.jpg', '.xmp')

    imageL = image.modifiedLab[0]
    imageA = image.modifiedLab[1]
    imageB = image.modifiedLab[2]

    if background == 'blue':
        paramsL = params.blueL
        paramsA = params.blueA
        paramsB = params.blueB
    elif background == 'grey':
        paramsL = params.greyL
        paramsA = params.greyA
        paramsB = params.greyB
    else:
        paramsL = params.greenL
        paramsA = params.greenA
        paramsB = params.greenB

    #   calculate Lab value changes needed
    xmpL = (paramsL - imageL) * 0.05
    print("xmpL: " + str(xmpL))  # set L

    AChangeAmount = paramsA - imageA
    print("A change amount: " + str(AChangeAmount))
    xmpA = 129 + round(AChangeAmount * -.87)
    print("xmpA: " + str(xmpA))  # set A

    GImpactL = round(round(AChangeAmount * (1 / -.87)) / 4)
    xmpL = xmpL + (GImpactL * 0.05)
    print("recalc xmpL: " + str(xmpL))  # account for A impacting L

    # [INSERT CODE HERE]  # account for A impacting B

    BChangeAmount  = paramsB - imageB
    print("B change amount: " + str(BChangeAmount))
    xmpB = 129 + round(BChangeAmount * (1 / -.616))
    print("xmpB: " + str(xmpB))  # set B

    #   write XMP values to the file
    f_tmp = open(path + '_tmp', 'w')

    with open(path, 'r') as f:
        for line in f:
            if "crs:Exposure2012=" in line:
                f_tmp.write("   crs:Exposure2012=\"" + str(xmpL) + "\"\n")
            elif "</xmpMM:History>" in line:
                f_tmp.write("  </xmpMM:History>\n")
                f_tmp.write("  <crs:ToneCurve>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>32, 22</rdf:li>\n")
                f_tmp.write("     <rdf:li>64, 56</rdf:li>\n")
                f_tmp.write("     <rdf:li>128, 128</rdf:li>\n")
                f_tmp.write("     <rdf:li>192, 196</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurve>\n")
                f_tmp.write("   <crs:ToneCurveRed>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurveRed>\n")
                f_tmp.write("   <crs:ToneCurveGreen>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurveGreen>\n")
                f_tmp.write("   <crs:ToneCurveBlue>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurveBlue>\n")
                f_tmp.write("   <crs:ToneCurvePV2012>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurvePV2012>\n")
                f_tmp.write("   <crs:ToneCurvePV2012Red>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurvePV2012Red>\n")
                f_tmp.write("   <crs:ToneCurvePV2012Green>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>129, " + str(xmpA) + "</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurvePV2012Green>\n")
                f_tmp.write("   <crs:ToneCurvePV2012Blue>\n")
                f_tmp.write("    <rdf:Seq>\n")
                f_tmp.write("     <rdf:li>0, 0</rdf:li>\n")
                f_tmp.write("     <rdf:li>129, " + str(xmpB) + "</rdf:li>\n")
                f_tmp.write("     <rdf:li>255, 255</rdf:li>\n")
                f_tmp.write("    </rdf:Seq>\n")
                f_tmp.write("   </crs:ToneCurvePV2012Blue>\n")
                f_tmp.write("   <crs:Look\n")
                f_tmp.write("    crs:Name=""/>\n")
            else:
                f_tmp.write(line)
        f.close()
        f_tmp.close()
        remove(path)
        rename(path + '_tmp', path)

    return


# TEST/DATA FUNCTIONS---------------------------------------------------------------------------------------------------
#   writes crop data to CSV
def writeCropCSV(image):
    d = open(image.xmpFolder + "/" + "cropdata.csv", "a")
    d.write(str(image.name) + ',' + str(image.hairPercent) + ',' +
            str(image.cropCoordsTopPercent) + ',' + str(image.cropCoordsBottomPercent) + ',' +
            str(image.cropLeftPercent) + ',' + str(image.cropRightPercent) + ',' + str(image.dist) + '\n')
    d.close()
    return

#   writes color data to CSV
def writeColorCSV(name, RGB, Lab, modLab, folder):
    d = open(folder + "/" + "colordata.csv", "a")
    d.write(str(name) + ',' +
            str(RGB[0]) + ',' + str(RGB[1]) + ',' + str(RGB[2]) + ',' +
            str(Lab[0]) + ',' + str(Lab[1]) + ',' + str(Lab[2]) + ',' +
            str(modLab[0]) + ',' + str(modLab[1]) + ',' + str(modLab[2]) + '\n')
    d.close()
    return

# RUN MAIN--------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
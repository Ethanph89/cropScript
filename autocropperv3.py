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

# XMP FILE DIRECTIONS DON'T CORRESPOND TO WHAT YOU THINK:
#   LEFT SIDE OF IMAGE => XMP TOP
#   TOP OF IMAGE => XMP RIGHT
#   RIGHT SIDE OF IMAGE => XMP BOTTOM
#   BOTTOM OF IMAGE => XMP LEFT
#   BOTTOM LEFT OF IMAGE IS (0,0)

# MAIN
def main():

    # CONSTANTS
    # Close up const
    CONST_PERCENT_ABOVE_HAIR = .07
    CONST_PERCENT_BELOW_CHIN = .24

    # Far away const
    CONST_IS_FAR = 6000
    CONST_PERCENT_ABOVE_HAIR_FAR = .07
    CONST_PERCENT_BELOW_CHIN_FAR = .50

    CONST_AVERAGE_TO_CROP = 50

    # asks for CSV that contains a path to the images for processing
    root = tk.Tk()
    root.withdraw()
    filename = askopenfilename()

    csvFile = open(filename, 'r')

    # creates a data.csv file that contains all cropping info
    f = open("data.csv", "w")
    f.write('image' + ',' + 'tophead' + ',' + 'topcrop' + ',' + 'bottomcrop' + ',' + 'leftcrop' + ',' + 'rightcrop' +
            ',' + 'toneR' + ',' + 'toneG' + ',' + 'toneB' '\n')
    f.close()

    # go through CSV line by line
    for line in csvFile:

        # only processes non-header lines
        if (line != "Header\n"):

            # defining the paths out of the CSV
            jpgPath = line.strip() + '.jpg'
            #xmpPath = line.strip().replace('crop', '') + '.xmp'
            xmpPathMac = line.strip() + '.xmp'

            # opening jpg into pixel array
            pixelArray = openJPG(jpgPath)

            # makes request to rekognition and grabs JSON return
            faceFeaturesJSON = rekognitionRequest(jpgPath)

            # getting aws rekognition JSON output
            awsMasterOutput = parse_aws_output(faceFeaturesJSON)
            BoundingBoxJSON = awsMasterOutput[0]
            LandmarksJSON = awsMasterOutput[1]
            OrientationCorrection = awsMasterOutput[2]

            # getting center of face
            faceCenterPercentages = centerOfBoundingBox(BoundingBoxJSON)

            # gets average pixel color of first 100 rows
            averageBackgroundColor = getAverageBackgroundColor(pixelArray)

            # finds percentage-based measure of top of head
            hairCoords = findTopOfHair(pixelArray, BoundingBoxJSON, averageBackgroundColor, CONST_AVERAGE_TO_CROP)

            # defines bounding box top and bottom
            BBTop = BoundingBoxJSON.get("Top")
            BBBottom = BBTop + BoundingBoxJSON.get("Height")

            # uses width of head to make average despairities easier to find
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
                cropCoordsTop = hairCoords - CONST_PERCENT_ABOVE_HAIR
                cropCoordsBottom = CONST_PERCENT_BELOW_CHIN + BBBottom
            else:
                cropCoordsTop = hairCoords - CONST_PERCENT_ABOVE_HAIR_FAR
                cropCoordsBottom = CONST_PERCENT_BELOW_CHIN_FAR + BBBottom

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
            makeXMP(cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, xmpPathMac)

            # find skin tone
            tone = skinToneAverage(pixelArray, BoundingBoxJSON, BBTop, BBBottom)

            # copies data to csv
            printInformation(jpgPath, hairCoords, cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, tone)


# BODY FUNCTIONS

# opens JPG and returns pixel array
def openJPG(path):
    im = Image.open(path)
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

# finds the center of the bouding box
def centerOfBoundingBox(boundingBoxJSON):
    BBLeft = boundingBoxJSON.get("Left")
    BBTop = boundingBoxJSON.get("Top")
    BBRight = BBLeft + boundingBoxJSON.get("Width")
    BBBottom = BBTop + boundingBoxJSON.get("Height")

    return ((BBLeft + BBRight) / 2, (BBTop + BBBottom) / 2)

# using the pixel array, finds the average RGB value of the first 100 rows
def getAverageBackgroundColor(pixelArray):
    rSum = 0
    gSum = 0
    bSum = 0
    rNum = 0
    gNum = 0
    bNum = 0

    for i in range(100):
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

# finds the top og the hair by comparing average RGB values to RGB values going down the image
def findTopOfHair(pixelArray, boundingBox, averageBackgroundColor, averageToCrop):

    # uses width of head to make average despairities easier to find
    leftBBInPixels = (int)(pixelArray.shape[1] * boundingBox.get("Left"))
    rigthBBInPixels = (int)(
        (pixelArray.shape[1] * boundingBox.get("Left")) + (pixelArray.shape[1] * boundingBox.get("Width")))
    BBWidth = rigthBBInPixels - leftBBInPixels

    # compares read in pixels to average value row by row until it finds an average bigger than averageToCrop
    rowNum = 0
    for row in pixelArray:
        rSum = 0
        gSum = 0
        bSum = 0
        totalDiff = 0
        for i in range(leftBBInPixels, rigthBBInPixels):
            rSum += row[i][0]
            gSum += row[i][1]
            bSum += row[i][2]
        tempRowAverage = [rSum / BBWidth, gSum / BBWidth, bSum / BBWidth]
        for j in range(3):
            totalDiff += abs(averageBackgroundColor[j] - tempRowAverage[j])
        rowNum += 1
        if (totalDiff > averageToCrop):
            break

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

# sends image to Rekognition client
def rekognitionRequest(path):
    client = boto3.client('rekognition')

    image = open(path, "rb")

    response = client.detect_faces(
        Image={'Bytes': image.read()},
        Attributes=['DEFAULT']
    )

    image.close()

    return response

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

# copies crop info to data.csv
def printInformation(img_name, hairCoords, cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, tone):
    d = open("data.csv", "a")
    d.write(str(img_name) + ',' + str(hairCoords) + ',' + str(cropCoordsTop) + ',' + str(cropCoordsBottom) + ',' +
            str(cropLeft) + ',' + str(cropRight) + ',' + str(round(tone[0])) + ',' + str(round(tone[1])) + ',' +
            str(round(tone[2])) + '\n')
    d.close()

# runs main
if __name__ == '__main__':
    main()
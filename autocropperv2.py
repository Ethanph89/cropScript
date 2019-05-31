# IMPORTS
import json
from os import rename, remove
from PIL import Image, ImageFilter, ImageShow
import numpy as np
import boto3
import tkinter as tk
from tkinter.filedialog import askopenfilename


# XMP FILE DIRECTIONS DON'T CORRESPOND TO WHAT YOU THINK:
#   LEFT SIDE OF IMAGE => XMP TOP
#   TOP OF IMAGE => XMP RIGHT
#   RIGHT SIDE OF IMAGE => XMP BOTTOM
#   BOTTOM OF IMAGE => XMP LEFT
#   BOTTOM LEFT OF IMAGE IS (0,0)

# MAIN
def main():
    # Constants
    CONST_PERCENT_ABOVE_HAIR = .07
    CONST_PERCENT_BELOW_CHIN = .24
    CONST_AVERAGE_TO_CROP = 50

    root = tk.Tk()
    root.withdraw()
    filename = askopenfilename()

    csvFile = open(filename, 'r')

    f = open("data.csv", "w")
    f.write('image' + ',' + 'tophead' '\n')
    f.close()

    for line in csvFile:
        if (line != "Header\n"):
            jpgPath = line.strip() + '.jpg'
            xmpPath = line.strip().replace('crop', '') + '.xmp'

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

            # prints data to screen
            printInformation(jpgPath, hairCoords, csvFile)

            # subtracts off the average amount of space on top of head
            cropCoordsTop = hairCoords - CONST_PERCENT_ABOVE_HAIR

            BBTop = BoundingBoxJSON.get("Top")
            BBBottom = BBTop + BoundingBoxJSON.get("Height")

            cropCoordsBottom = CONST_PERCENT_BELOW_CHIN + BBBottom

            totalCropHeight = cropCoordsBottom - cropCoordsTop
            cropHeightPixels = totalCropHeight * pixelArray.shape[0]
            cropWidthPixels = (cropHeightPixels / 5) * 4
            cropWidth = cropWidthPixels / pixelArray.shape[1]
            cropLeft = faceCenterPercentages[0] - (cropWidth / 2)
            cropRight = faceCenterPercentages[0] + (cropWidth / 2)

            if cropLeft < 0:
                cropLeft = 0
            if cropRight > 1:
                cropRight = 1

            makeXMP(cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, xmpPath)


# BODY FUNCTIONS
def openJPG(path):
    im = Image.open(path)
    pixel_array = np.array(im)
    return pixel_array


def parse_aws_output(JSONResponse):
    awsData = json.loads(json.dumps(JSONResponse))
    BoundingBox = awsData.get("FaceDetails")[0].get("BoundingBox")
    Landmarks = awsData.get("FaceDetails")[0].get("Landmarks")
    OrientationCorrection = awsData.get("OrientationCorrection")
    return [BoundingBox, Landmarks, OrientationCorrection]


def centerOfBoundingBox(boundingBoxJSON):
    BBLeft = boundingBoxJSON.get("Left")
    BBTop = boundingBoxJSON.get("Top")
    BBRight = BBLeft + boundingBoxJSON.get("Width")
    BBBottom = BBTop + boundingBoxJSON.get("Height")

    return ((BBLeft + BBRight) / 2, (BBTop + BBBottom) / 2)


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


def findTopOfHair(pixelArray, boundingBox, averageBackgroundColor, averageToCrop):
    leftBBInPixels = (int)(pixelArray.shape[1] * boundingBox.get("Left"))
    rigthBBInPixels = (int)(
        (pixelArray.shape[1] * boundingBox.get("Left")) + (pixelArray.shape[1] * boundingBox.get("Width")))
    BBWidth = rigthBBInPixels - leftBBInPixels

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

    hairPosition = rowNum / pixelArray.shape[0]
    return hairPosition


def makeXMP(cropCoordsTop, cropCoordsBottom, cropLeft, cropRight, path):
    f_tmp = open(path + '_tmp', 'w')

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


def rekognitionRequest(path):
    client = boto3.client('rekognition')

    image = open(path, "rb")

    response = client.detect_faces(
        Image={'Bytes': image.read()},
        Attributes=['DEFAULT']
    )

    image.close()

    return response


def printInformation(img_name, hairCoords, csvFile):
    f = open("data.csv", "a")
    f.write(str(img_name) + ',' + str(hairCoords) + '\n')
    f.close()

if __name__ == '__main__':
    main()
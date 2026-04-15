import cv2
import numpy as np

img = cv2.imread("D:/baitapxaml/HK252/DATN/Scoring/IPSC/A4_IPSC2.png")

polygons = []
scores = [10,5,3,10,7]   # mapping điểm

current_poly = []

# load polygon
with open("D:/baitapxaml/HK252/DATN/Scoring/IPSC/polygon.txt") as f:

    for line in f:

        line = line.strip()

        if line == "":
            continue

        if line.startswith("polygon"):
            current_poly = []
            continue

        if line == "END":
            polygons.append(np.array(current_poly))
            continue

        x,y = map(int,line.split(","))
        current_poly.append([x,y])

output = img.copy()


# function chấm điểm
def score_point(point):

    for i,poly in enumerate(polygons):

        result = cv2.pointPolygonTest(poly, point, False)

        if result >= 0:
            return scores[i]

    return 0


# mouse click
def mouse_click(event,x,y,flags,param):

    global output

    if event == cv2.EVENT_LBUTTONDOWN:

        score = score_point((x,y))

        print("Shot:",x,y," Score:",score)

        cv2.circle(output,(x,y),8,(0,0,255),-1)

        cv2.putText(output,
                    str(score),
                    (x+10,y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    3,
                    (0,0,255),
                    3)

        cv2.imshow("target",output)


# vẽ polygon lên trước
for poly in polygons:
    cv2.polylines(output,[poly],True,(0,255,0),2)


cv2.namedWindow("target",cv2.WINDOW_NORMAL)

cv2.setMouseCallback("target",mouse_click)

cv2.imshow("target",output)

cv2.waitKey(0)

cv2.destroyAllWindows()
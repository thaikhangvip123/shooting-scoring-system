import cv2
import numpy as np

# =========================
# load image
# =========================
img = cv2.imread("D:/baitapxaml/HK252/DATN/Scoring/Nguoi/A4_Nguoi.png")
output = img.copy()

# =========================
# load contours
# =========================
contours = []
current_contour = []

with open("D:/baitapxaml/HK252/DATN/Scoring/Nguoi/Nguoi_contours.txt") as f:

    for line in f:

        line = line.strip()

        if line == "":
            continue
            
        if line.startswith("contour"):

            if len(current_contour) > 0:
                contours.append(np.array(current_contour, dtype=np.int32))

            current_contour = []
            continue

        x, y = map(int, line.split(","))
        current_contour.append([x, y])

if len(current_contour) > 0:
    contours.append(np.array(current_contour, dtype=np.int32))

print("Loaded contours:", len(contours))

# =========================
# mapping điểm
# =========================
scores = [6,7,8,9,9,10,10]

# =========================
# function chấm điểm
# =========================
def score_point(point):

    best_score = 0
    smallest_area = 1e18

    for i, cnt in enumerate(contours):

        result = cv2.pointPolygonTest(cnt, point, False)

        if result >= 0:

            area = cv2.contourArea(cnt)

            if area < smallest_area:
                smallest_area = area
                best_score = scores[i]

    return best_score


# =========================
# mouse click
# =========================
def mouse_click(event, x, y, flags, param):

    global output

    if event == cv2.EVENT_LBUTTONDOWN:

        score = score_point((x, y))

        print("Shot:", x, y, "Score:", score)

        cv2.circle(output, (x, y), 8, (0,0,255), -1)

        cv2.putText(
            output,
            str(score),
            (x+10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            3,
            (0,0,255),
            3
        )

        cv2.imshow("target", output)


# =========================
# vẽ contour
# =========================
for cnt in contours:

    cv2.polylines(
        output,
        [cnt],
        True,
        (0,255,0),
        2
    )

# =========================
# window
# =========================
cv2.namedWindow("target", cv2.WINDOW_NORMAL)

cv2.setMouseCallback("target", mouse_click)

cv2.imshow("target", output)

cv2.waitKey(0)

cv2.destroyAllWindows()
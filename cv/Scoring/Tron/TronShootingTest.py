import cv2
import numpy as np

img = cv2.imread("D:/baitapxaml/HK252/DATN/Scoring/Tron/A4_Tron.png")

# Tâm bia bạn đã đo
center = (1240, 1754)

# Bán kính các vòng (từ ngoài vào trong)
radii = [
897.0,
802.5,
708.0,
613.5,
519.0,
424.5,
330.0,
235.5,
141.0,
51
]

# copy ảnh để vẽ
display = img.copy()


def get_score(x, y):

    dx = x - center[0]
    dy = y - center[1]

    dist = np.sqrt(dx*dx + dy*dy)

    # kiểm tra từ vòng trong ra ngoài
    for i, r in enumerate(reversed(radii)):
        if dist <= r:
            return 10 - i

    return 0


def mouse_click(event, x, y, flags, param):

    global display

    if event == cv2.EVENT_LBUTTONDOWN:

        score = get_score(x, y)

        print("Click:", x, y)
        print("Score:", score)

        # vẽ điểm bắn
        cv2.circle(display, (x, y), 10, (0,0,255), -1)

        # hiển thị điểm
        cv2.putText(display, str(score),
                    (x+10, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    3,
                    (0,0,255),
                    3)

        cv2.imshow("target", display)


cv2.namedWindow("target", cv2.WINDOW_NORMAL)
cv2.setMouseCallback("target", mouse_click)

cv2.imshow("target", display)

cv2.waitKey(0)
cv2.destroyAllWindows()
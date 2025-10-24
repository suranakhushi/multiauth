import cv2

cam = cv2.VideoCapture(0)
if not cam.isOpened():
    print("Error: Cannot access webcam.")
else:
    ret, frame = cam.read()
    if not ret or frame is None:
        print("Error: Failed to read frame from webcam.")
    else:
        print("Webcam working! Frame shape:", frame.shape)
        cv2.imshow("Test Webcam", frame)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
cam.release()

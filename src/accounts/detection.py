import cv2
import os
import numpy as np
from PIL import Image
from core.settings import BASE_DIR

detector = cv2.CascadeClassifier(BASE_DIR + '/accounts/haarcascade_frontalface_default.xml')
recognizer = cv2.face.LBPHFaceRecognizer_create()

class FaceRecognition:

    def save_face_image(self, img, face_id, count=1):
        """Save uploaded/captured face image for training."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, 1.3, 5)
        saved = 0
        for (x, y, w, h) in faces:
            save_path = BASE_DIR + f'/media/dataset/User.{face_id}.{count}.jpg'
            cv2.imwrite(save_path, gray[y:y+h, x:x+w])
            saved += 1
        return saved

    def trainFace(self):
        path = BASE_DIR + '/media/dataset'
        if not os.path.exists(path) or not os.listdir(path):
            return  # No images to train on

        def getImagesAndLabels(path):
            imagePaths = [os.path.join(path, f) for f in os.listdir(path)]
            faceSamples = []
            ids = []
            for imagePath in imagePaths:
                PIL_img = Image.open(imagePath).convert('L')
                img_numpy = np.array(PIL_img, 'uint8')
                face_id = int(os.path.split(imagePath)[-1].split(".")[1])
                faces = detector.detectMultiScale(img_numpy)
                for (x, y, w, h) in faces:
                    faceSamples.append(img_numpy[y:y+h, x:x+w])
                    ids.append(face_id)
            return faceSamples, ids

        faces, ids = getImagesAndLabels(path)
        if faces and ids:
            recognizer.train(faces, np.array(ids))
            recognizer.save(BASE_DIR + '/accounts/trainer/trainer.yml')

    def predict_from_image(self, img):
        trainer_path = os.path.join(BASE_DIR, 'accounts', 'trainer', 'trainer.yml')
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(trainer_path)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        detector = cv2.CascadeClassifier(
            os.path.join(BASE_DIR, 'accounts', 'haarcascade_frontalface_default.xml')
        )
        faces = detector.detectMultiScale(gray, 1.3, 5)

        if len(faces) == 0:
            print("⚠️ No face detected during login")
            return None, None

        best_match = (None, float('inf'))
        for (x, y, w, h) in faces:
            face_id, confidence = recognizer.predict(gray[y:y+h, x:x+w])
            print(f"🔎 Candidate → ID={face_id}, Confidence={confidence}")
            if confidence < best_match[1]:
                best_match = (face_id, confidence)

        face_id, confidence = best_match
        print(f"✅ Best match → ID={face_id}, Confidence={confidence}")
        return face_id, confidence  # ← always return values

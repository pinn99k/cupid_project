import cv2
import pygame

# 웹캠 확인
cap = cv2.VideoCapture(0)

if cap.isOpened():
    print("웹캠 연결 성공")
else:
    print("웹캠 연결 실패")

cap.release()

# 오디오 확인
pygame.mixer.init()

print("오디오 초기화 성공")
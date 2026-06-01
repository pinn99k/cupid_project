import speech_recognition as sr

r = sr.Recognizer()

with sr.Microphone() as source:
    print("말하세요")
    audio = r.listen(source)

try:
    text = r.recognize_google(audio, language="ko-KR")
    print("인식:", text)
except Exception as e:
    print(e)
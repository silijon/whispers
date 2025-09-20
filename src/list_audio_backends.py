
import sounddevice as sd

for i, api in enumerate(sd.query_hostapis()):
    print(i, api['name'])

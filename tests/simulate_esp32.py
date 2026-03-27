import requests
import json
import random
import time

URL = "http://localhost:8000/api/sensors/"

def send_data():
    payload = {
        "device_id": "ESP32_LIVING_ROOM22",
        "tensao_shunt": round(random.uniform(0.0, 5.0), 2),
        "irradiance": round(random.uniform(0.0, 1000.0), 2)
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(URL, data=json.dumps(payload), headers=headers)
        if response.status_code == 201:
            print(f"Success! Sent: {payload}")
            print(f"Response: {response.json()}")
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    print("Simulating ESP32 sending data every 0.1 seconds. Press Ctrl+C to stop.")
    try:
        while True:
            send_data()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nSimulation stopped.")
    
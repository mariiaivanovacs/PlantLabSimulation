FROM python:3.11-slim

WORKDIR /app

# Copy shared requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy plant-metrics-mqtt source
COPY . .

# Default: run subscriber (override CMD to run publisher instead)
CMD ["python", "subscriber/mqtt_subscriber.py"]

# """Sensor noise, drift, and delay simulation"""

# import random

# def add_sensor_noise(value, noise_level=0.05):
#     """Add Gaussian noise to sensor reading"""
#     noise = random.gauss(0, noise_level * value)
#     return value + noise

# def apply_sensor_drift(value, drift_rate=0.001, time_elapsed=0):
#     """Apply sensor drift over time"""
#     drift = drift_rate * time_elapsed
#     return value + drift

# def apply_sensor_delay(readings_buffer, new_value, delay_steps=1):
#     """Simulate sensor delay"""
#     readings_buffer.append(new_value)
#     if len(readings_buffer) > delay_steps:
#         return readings_buffer.pop(0)
#     return readings_buffer[0] if readings_buffer else new_value



#### CURRENTLY KEEP


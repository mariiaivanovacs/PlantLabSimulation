# visualize RGR_actual from RGR.txt

import numpy as np
import matplotlib.pyplot as plt
import os


def visualize_rgr(data_dir):
    """Visualize RGR_actual from RGR.txt"""
    # Load data
    rgr_file = os.path.join(data_dir, 'RGR.txt')
    data = np.loadtxt(rgr_file, delimiter=',', skiprows=1)
    time = data[:, 0]  # Assuming first column is time
    # last column in RGR actual
    last_column = data.shape[1] - 1
    rgr_actual = data[:, last_column]  # Assuming last column is RGR_actual
    
    # Plotting
    plt.figure(figsize=(10, 6))
    plt.plot(time, rgr_actual, label='RGR_actual', color='blue')
    plt.xlabel('Time (hours)')
    plt.ylabel('RGR_actual')
    plt.title('RGR_actual over Time')
    plt.legend()
    plt.grid(True)
    plt.show()
    
    
    
if __name__ == "__main__":
    visualize_rgr('data/records')
    
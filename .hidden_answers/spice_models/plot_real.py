#!/usr/bin/env python3
"""Plot the REAL SPICE simulation output."""

import numpy as np
import matplotlib.pyplot as plt

# Load data
data = np.loadtxt('aerotone_real_healthy.dat')

# Parse interleaved columns
time = data[:, 0]
loop_filter = data[:, 1]
motor_voltage = data[:, 3]
motor_current = data[:, 5]
conditioner = data[:, 7]

print(f"Data points: {len(time)}")
print(f"Time range: {time[0]*1000:.3f}ms to {time[-1]*1000:.3f}ms")
print(f"\nSteady state values (last 10% of sim):")
steady_start = int(len(time) * 0.9)
print(f"  Loop filter: {np.mean(loop_filter[steady_start:]):.3f} V")
print(f"  Motor voltage: {np.mean(motor_voltage[steady_start:]):.3f} V")
print(f"  Motor current: {np.mean(motor_current[steady_start:]):.3f} A")
print(f"  Conditioner: {np.mean(conditioner[steady_start:]):.3f} V")

# Plot
fig, axes = plt.subplots(4, 1, figsize=(16, 12))
fig.suptitle('REAL SPICE SIMULATION - AEROTONE VOICE CARD\n(Actual Component Models)', fontsize=14, fontweight='bold')

time_ms = time * 1000

axes[0].plot(time_ms, loop_filter, 'b-', linewidth=0.3)
axes[0].set_ylabel('Loop Filter (V)')
axes[0].set_title(f'Loop Filter: min={loop_filter.min():.3f}V, max={loop_filter.max():.3f}V')
axes[0].grid(True, alpha=0.3)

axes[1].plot(time_ms, motor_voltage, 'g-', linewidth=0.3)
axes[1].set_ylabel('Motor Voltage (V)')
axes[1].set_title(f'Motor Voltage: min={motor_voltage.min():.3f}V, max={motor_voltage.max():.3f}V')
axes[1].grid(True, alpha=0.3)

axes[2].plot(time_ms, motor_current, 'r-', linewidth=0.3)
axes[2].set_ylabel('Motor Current (A)')
axes[2].set_title(f'Motor Current: min={motor_current.min():.3f}A, max={motor_current.max():.3f}A')
axes[2].grid(True, alpha=0.3)

axes[3].plot(time_ms, conditioner, 'm-', linewidth=0.3)
axes[3].set_ylabel('Conditioner (V)')
axes[3].set_title(f'Conditioner Output: min={conditioner.min():.3f}V, max={conditioner.max():.3f}V')
axes[3].set_xlabel('Time (ms)')
axes[3].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('plots/real_spice_output.png', dpi=150)
print("\nSaved: plots/real_spice_output.png")

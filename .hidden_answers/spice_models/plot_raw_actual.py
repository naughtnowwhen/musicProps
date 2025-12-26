#!/usr/bin/env python3
"""Show ACTUAL raw SPICE data as the agent would see it."""

import numpy as np
import matplotlib.pyplot as plt
import os

def parse_spice_rawdata(filename):
    """Parse ngspice wrdata output."""
    data = np.loadtxt(filename)
    time = data[:, 0]
    n_signals = data.shape[1] // 2
    signals = {}
    names = ['loop_filter', 'motor_drive', 'motor_current', 'conditioner']
    for i in range(min(n_signals, len(names))):
        signals[names[i]] = data[:, i*2 + 1]
    return time, signals

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Plot HEALTHY raw data - full view
time_h, sig_h = parse_spice_rawdata('healthy_raw.dat')

fig, axes = plt.subplots(4, 1, figsize=(16, 10))
fig.suptitle(f'RAW SPICE DATA - HEALTHY CIRCUIT\n({len(time_h)} data points, {time_h[0]:.6f}s to {time_h[-1]:.6f}s)', fontsize=12)

for ax, (name, data) in zip(axes, sig_h.items()):
    ax.plot(time_h * 1000, data, 'b-', linewidth=0.3)
    ax.set_ylabel(name)
    ax.grid(True, alpha=0.3)
    ax.set_title(f'{name}: min={data.min():.4f}, max={data.max():.4f}, mean={data.mean():.4f}')

axes[-1].set_xlabel('Time (ms)')
plt.tight_layout()
plt.savefig('plots/raw_healthy_full.png', dpi=150)
plt.close()
print("Saved: plots/raw_healthy_full.png")

# Plot each fault - full raw view
faults = ['f001', 'f002', 'f003', 'f004', 'f005']
fault_names = ['F001 (C2 Leaky Cap)', 'F002 (Q1 Burned)', 'F003 (U2 Noisy)', 'F004 (R9 Open)', 'F005 (D2 Shorted)']

for fault, fname in zip(faults, fault_names):
    time_f, sig_f = parse_spice_rawdata(f'{fault}_raw.dat')

    fig, axes = plt.subplots(4, 1, figsize=(16, 10))
    fig.suptitle(f'RAW SPICE DATA - {fname}\n({len(time_f)} data points)', fontsize=12)

    for ax, (name, data) in zip(axes, sig_f.items()):
        ax.plot(time_f * 1000, data, 'r-', linewidth=0.3)
        ax.set_ylabel(name)
        ax.grid(True, alpha=0.3)
        ax.set_title(f'{name}: min={data.min():.4f}, max={data.max():.4f}, mean={data.mean():.4f}')

    axes[-1].set_xlabel('Time (ms)')
    plt.tight_layout()
    plt.savefig(f'plots/raw_{fault}_full.png', dpi=150)
    plt.close()
    print(f"Saved: plots/raw_{fault}_full.png")

# Side by side comparison - healthy vs F003 (the noisy one)
time_h, sig_h = parse_spice_rawdata('healthy_raw.dat')
time_f, sig_f = parse_spice_rawdata('f003_raw.dat')

fig, axes = plt.subplots(4, 2, figsize=(18, 12))
fig.suptitle('RAW SPICE COMPARISON: HEALTHY vs F003 (Noisy Op-Amp)', fontsize=14)

names = ['loop_filter', 'motor_drive', 'motor_current', 'conditioner']
for i, name in enumerate(names):
    # Healthy
    axes[i, 0].plot(time_h * 1000, sig_h[name], 'b-', linewidth=0.3)
    axes[i, 0].set_ylabel(name)
    axes[i, 0].set_title(f'HEALTHY - {name}')
    axes[i, 0].grid(True, alpha=0.3)

    # Faulty
    axes[i, 1].plot(time_f * 1000, sig_f[name], 'r-', linewidth=0.3)
    axes[i, 1].set_title(f'F003 FAULTY - {name}')
    axes[i, 1].grid(True, alpha=0.3)

axes[-1, 0].set_xlabel('Time (ms)')
axes[-1, 1].set_xlabel('Time (ms)')
plt.tight_layout()
plt.savefig('plots/raw_comparison_f003.png', dpi=150)
plt.close()
print("Saved: plots/raw_comparison_f003.png")

print("\nDone!")

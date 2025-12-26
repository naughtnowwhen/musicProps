#!/usr/bin/env python3
"""Generate comparison plots of healthy vs faulty SPICE waveforms."""

import numpy as np
import matplotlib.pyplot as plt
import os

def parse_spice_rawdata(filename):
    """Parse ngspice wrdata output (interleaved time,value pairs)."""
    data = np.loadtxt(filename)
    # Data is interleaved: t1,v1, t2,v2, t3,v3...
    # Each signal has its own time column
    n_cols = data.shape[1]
    n_signals = n_cols // 2

    signals = {}
    time = data[:, 0]  # Use first time column
    for i in range(n_signals):
        signals[f'signal_{i}'] = data[:, i*2 + 1]

    return time, signals

def plot_comparison(healthy_file, faulty_file, fault_name, output_dir):
    """Generate comparison plot."""

    time_h, sig_h = parse_spice_rawdata(healthy_file)
    time_f, sig_f = parse_spice_rawdata(faulty_file)

    # Convert to ms
    time_h_ms = time_h * 1000
    time_f_ms = time_f * 1000

    fig, axes = plt.subplots(4, 1, figsize=(14, 12))
    fig.suptitle(f'HEALTHY vs {fault_name}', fontsize=14, fontweight='bold')

    labels = ['Loop Filter (V)', 'Motor Drive (V)', 'Motor Current (A)', 'Conditioner Output (V)']

    for i, (ax, label) in enumerate(zip(axes, labels)):
        if i < len(sig_h):
            ax.plot(time_h_ms, sig_h[f'signal_{i}'], 'b-', label='Healthy', alpha=0.7)
        if i < len(sig_f):
            ax.plot(time_f_ms, sig_f[f'signal_{i}'], 'r-', label=fault_name, alpha=0.7)
        ax.set_ylabel(label)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(35, 50)  # Focus on steady state

    axes[-1].set_xlabel('Time (ms)')

    plt.tight_layout()
    output_path = os.path.join(output_dir, f'compare_{fault_name.lower().replace(" ", "_")}.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")
    return output_path

def plot_all_conditioners(output_dir):
    """Plot all conditioner outputs together for comparison."""

    files = {
        'Healthy': 'healthy_raw.dat',
        'F001 (C2 Leaky Cap)': 'f001_raw.dat',
        'F002 (Q1 Burned)': 'f002_raw.dat',
        'F003 (U2 Noisy)': 'f003_raw.dat',
        'F004 (R9 Open)': 'f004_raw.dat',
        'F005 (D2 Shorted)': 'f005_raw.dat',
    }

    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    fig.suptitle('Conditioner Output Comparison (All Faults)', fontsize=14, fontweight='bold')

    for ax, (name, filename) in zip(axes.flat, files.items()):
        try:
            time, signals = parse_spice_rawdata(filename)
            time_ms = time * 1000
            # Conditioner is signal_3 (4th column pair)
            cond = signals.get('signal_3', signals.get('signal_4', list(signals.values())[-1]))

            color = 'blue' if name == 'Healthy' else 'red'
            ax.plot(time_ms, cond, color=color, linewidth=0.5)
            ax.set_title(name)
            ax.set_xlim(40, 50)
            ax.set_ylim(-15, 15)
            ax.set_xlabel('Time (ms)')
            ax.set_ylabel('Voltage (V)')
            ax.grid(True, alpha=0.3)
        except Exception as e:
            ax.text(0.5, 0.5, f'Error: {e}', ha='center', va='center')

    plt.tight_layout()
    output_path = os.path.join(output_dir, 'all_conditioners.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")

def plot_overview(output_dir):
    """Create overview showing key differences."""

    time_h, sig_h = parse_spice_rawdata('healthy_raw.dat')
    time_ms = time_h * 1000

    faults = {
        'F001': ('f001_raw.dat', 'Leaky Capacitor C2'),
        'F002': ('f002_raw.dat', 'Burned Transistor Q1'),
        'F003': ('f003_raw.dat', 'Noisy Op-Amp U2'),
        'F004': ('f004_raw.dat', 'Open Resistor R9'),
        'F005': ('f005_raw.dat', 'Shorted Diode D2'),
    }

    fig, axes = plt.subplots(5, 4, figsize=(20, 16))
    fig.suptitle('AEROTONE VOICE CARD - FAULT SIGNATURES\n(Healthy=Blue, Faulty=Red)',
                 fontsize=14, fontweight='bold')

    col_labels = ['Loop Filter', 'Motor Drive', 'Motor Current', 'Conditioner']

    for row, (fault_id, (filename, desc)) in enumerate(faults.items()):
        time_f, sig_f = parse_spice_rawdata(filename)

        for col in range(4):
            ax = axes[row, col]

            # Plot healthy
            if col < len(sig_h):
                ax.plot(time_ms, sig_h[f'signal_{col}'], 'b-', alpha=0.6, linewidth=0.5)

            # Plot faulty
            if col < len(sig_f):
                ax.plot(time_f * 1000, sig_f[f'signal_{col}'], 'r-', alpha=0.6, linewidth=0.5)

            ax.set_xlim(40, 50)
            ax.grid(True, alpha=0.3)

            if row == 0:
                ax.set_title(col_labels[col])
            if col == 0:
                ax.set_ylabel(f'{fault_id}\n{desc}', fontsize=9)

    plt.tight_layout()
    output_path = os.path.join(output_dir, 'fault_overview.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    output_dir = os.path.join(script_dir, 'plots')
    os.makedirs(output_dir, exist_ok=True)

    # Generate individual comparisons
    faults = [
        ('f001_raw.dat', 'F001 Leaky Cap'),
        ('f002_raw.dat', 'F002 Burned Q1'),
        ('f003_raw.dat', 'F003 Noisy OpAmp'),
        ('f004_raw.dat', 'F004 Open R9'),
        ('f005_raw.dat', 'F005 Shorted D2'),
    ]

    for fault_file, fault_name in faults:
        plot_comparison('healthy_raw.dat', fault_file, fault_name, output_dir)

    # Generate combined views
    plot_all_conditioners(output_dir)
    plot_overview(output_dir)

    print("\nAll plots generated!")

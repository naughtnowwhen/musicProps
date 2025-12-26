#!/usr/bin/env python3
"""
Oscilloscope Captures - 5 Key Circuit Nodes

Generates detailed oscilloscope-style waveform plots for 5 interesting
nodes in the AeroTone circuit, showing the PLL control loop in action.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import os

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench

# Create output directory
os.makedirs('oscope_output', exist_ok=True)


def create_oscope_plot(waveform, title, subtitle, channel_color='#00ff00',
                       grid_color='#004400', bg_color='#001100',
                       time_div=None, volt_div=None, filename=None):
    """
    Create an oscilloscope-style plot with authentic CRT aesthetics.
    """
    fig, ax = plt.subplots(figsize=(12, 8), facecolor='#000000')
    ax.set_facecolor(bg_color)

    # Time array
    t = np.linspace(0, waveform.duration * 1000, len(waveform.samples))  # ms
    v = waveform.samples

    # Auto-scale if not specified
    if time_div is None:
        time_div = waveform.duration * 1000 / 10  # 10 divisions
    if volt_div is None:
        v_range = waveform.v_pp if waveform.v_pp > 0 else 1.0
        volt_div = v_range / 8  # 8 vertical divisions

    # Calculate display range
    t_max = time_div * 10
    v_center = waveform.v_avg  # DC average
    v_range = volt_div * 8

    # Draw grid (oscilloscope graticule)
    for i in range(11):
        x = i * time_div
        ax.axvline(x, color=grid_color, linewidth=0.5, alpha=0.7)
    for i in range(-4, 5):
        y = v_center + i * volt_div
        ax.axhline(y, color=grid_color, linewidth=0.5, alpha=0.7)

    # Center lines (brighter)
    ax.axhline(v_center, color=grid_color, linewidth=1.0, alpha=1.0)
    ax.axvline(t_max/2, color=grid_color, linewidth=1.0, alpha=1.0)

    # Plot waveform with glow effect
    ax.plot(t, v, color=channel_color, linewidth=1.5, alpha=0.3)  # Glow
    ax.plot(t, v, color=channel_color, linewidth=1.0, alpha=0.6)  # Mid
    ax.plot(t, v, color='#ffffff', linewidth=0.5, alpha=0.8)  # Bright center

    # Set limits
    ax.set_xlim(0, t_max)
    ax.set_ylim(v_center - v_range/2, v_center + v_range/2)

    # Axis labels
    ax.set_xlabel('Time (ms)', color='#00ff00', fontsize=10)
    ax.set_ylabel('Voltage (V)', color='#00ff00', fontsize=10)
    ax.tick_params(colors='#00aa00', labelsize=8)

    # Title (oscilloscope style)
    ax.set_title(title, color='#00ff00', fontsize=14, fontweight='bold', pad=20)

    # Info panel (like oscilloscope readout)
    info_text = f"""CH1: {subtitle}
Time/Div: {time_div:.2f} ms
Volt/Div: {volt_div:.3f} V

Vpp: {waveform.v_pp:.3f} V
Vavg: {waveform.v_avg:.3f} V
Vac: {waveform.v_ac_rms:.3f} Vrms
Freq: {waveform.frequency:.1f} Hz"""

    # Add text box
    props = dict(boxstyle='round', facecolor='#001100', edgecolor='#004400', alpha=0.9)
    ax.text(0.02, 0.98, info_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', color='#00ff00', fontfamily='monospace',
            bbox=props)

    # Add trigger marker
    ax.plot([0], [v_center], 'y>', markersize=10, alpha=0.8)

    # Border
    for spine in ax.spines.values():
        spine.set_color('#004400')
        spine.set_linewidth(2)

    plt.tight_layout()

    if filename:
        plt.savefig(filename, dpi=150, facecolor='#000000', edgecolor='none')
        print(f"  Saved: {filename}")

    plt.close()
    return fig


def main():
    print("=" * 60)
    print("  OSCILLOSCOPE CAPTURES - 5 Key Circuit Nodes")
    print("=" * 60)

    # Create voice and warm up
    print("\n[1] Initializing circuit...")
    params = SpiceVoiceParams(enable_thermal=False)
    voice = SpiceVoice(params=params, sample_rate=44100)
    voice.set_target_frequency(220.0)  # A3

    # Warm up to steady state
    print("[2] Warming up to steady state...")
    for _ in range(int(44100 * 0.5)):  # 0.5 seconds
        voice.update_physics(1/44100)

    bench = TestBench(voice)

    # Define the 5 interesting nodes
    nodes = [
        {
            'probe': 'cd4046_pin4_vco_out',
            'title': 'Node 1: VCO Output (CD4046 Pin 4)',
            'subtitle': 'VCO Square Wave Output',
            'description': 'The voltage-controlled oscillator output. This square wave is the reference frequency that the PLL is generating. The motor should spin at a rate that matches this frequency.',
            'duration': 0.02,  # 20ms to see several cycles
            'color': '#00ff00',
        },
        {
            'probe': 'loop_filter_cap_voltage',
            'title': 'Node 2: Loop Filter Capacitor (C1)',
            'subtitle': 'PLL Control Voltage',
            'description': 'The voltage stored on the loop filter capacitor. This is the "memory" of the PLL - it integrates the phase error and controls the VCO. A stable voltage means the PLL is locked.',
            'duration': 0.1,  # 100ms to see stability
            'color': '#ffff00',
        },
        {
            'probe': 'motor_voltage',
            'title': 'Node 3: Motor Drive Voltage',
            'subtitle': 'H-Bridge Output to Motor',
            'description': 'The voltage applied across the motor windings by the H-bridge. This is derived from the loop filter output and controls motor speed.',
            'duration': 0.1,
            'color': '#ff8800',
        },
        {
            'probe': 'pickup_raw',
            'title': 'Node 4: Magnetic Pickup (Raw)',
            'subtitle': 'Tachometer Sensor Output',
            'description': 'The raw sinusoidal signal from the magnetic pickup coil. The frequency of this signal indicates actual motor/propeller speed. The PLL compares this to the VCO.',
            'duration': 0.02,
            'color': '#00ffff',
        },
        {
            'probe': 'cond_comparator_out',
            'title': 'Node 5: Comparator Output (Feedback)',
            'subtitle': 'Digitized Feedback to CD4046',
            'description': 'The Schmitt trigger output - the pickup signal converted to a clean digital pulse. This feeds back to CD4046 Pin 14 (SIG_IN) to close the PLL loop.',
            'duration': 0.02,
            'color': '#ff00ff',
        },
    ]

    print("[3] Capturing waveforms...")
    print()

    for i, node in enumerate(nodes, 1):
        print(f"  Capturing {node['probe']}...")

        # Capture waveform
        waveform = bench.capture_waveform(node['probe'], node['duration'])

        # Create plot
        filename = f"oscope_output/node{i}_{node['probe']}.png"
        create_oscope_plot(
            waveform,
            title=node['title'],
            subtitle=node['subtitle'],
            channel_color=node['color'],
            filename=filename
        )

        # Print summary
        print(f"    Vpp={waveform.v_pp:.3f}V, Vavg={waveform.v_avg:.3f}V, "
              f"Freq={waveform.frequency:.1f}Hz")

    print()
    print("=" * 60)
    print("  CAPTURE COMPLETE")
    print("=" * 60)
    print()
    print("Node Descriptions:")
    print("-" * 60)
    for i, node in enumerate(nodes, 1):
        print(f"\n{i}. {node['title']}")
        print(f"   {node['description']}")

    print()
    print(f"Output saved to: oscope_output/")
    print()

    # Create a combined summary image
    print("Creating combined summary...")
    create_summary_plot(nodes, bench)


def create_summary_plot(nodes, bench):
    """Create a 5-panel summary showing all waveforms together."""
    fig, axes = plt.subplots(5, 1, figsize=(14, 16), facecolor='#000000')
    fig.suptitle('AeroTone PLL Signal Chain - 5 Key Nodes',
                 color='#00ff00', fontsize=16, fontweight='bold', y=0.98)

    for i, (ax, node) in enumerate(zip(axes, nodes)):
        ax.set_facecolor('#001100')

        # Capture waveform
        waveform = bench.capture_waveform(node['probe'], node['duration'])
        t = np.linspace(0, waveform.duration * 1000, len(waveform.samples))

        # Plot with glow
        ax.plot(t, waveform.samples, color=node['color'], linewidth=1.0, alpha=0.4)
        ax.plot(t, waveform.samples, color='#ffffff', linewidth=0.5, alpha=0.7)

        # Grid
        ax.grid(True, color='#004400', alpha=0.5, linewidth=0.5)
        ax.axhline(waveform.v_avg, color='#004400', linewidth=1, alpha=0.8)

        # Labels
        ax.set_ylabel('V', color='#00aa00', fontsize=9)
        ax.tick_params(colors='#00aa00', labelsize=7)

        # Title on left
        ax.text(-0.12, 0.5, f"Node {i+1}", transform=ax.transAxes,
                color=node['color'], fontsize=11, fontweight='bold',
                verticalalignment='center', rotation=90)

        # Info on right
        info = f"{node['subtitle']}\nVpp={waveform.v_pp:.2f}V  f={waveform.frequency:.0f}Hz"
        ax.text(1.02, 0.5, info, transform=ax.transAxes,
                color='#00aa00', fontsize=8, verticalalignment='center',
                fontfamily='monospace')

        for spine in ax.spines.values():
            spine.set_color('#004400')

    axes[-1].set_xlabel('Time (ms)', color='#00ff00', fontsize=10)

    plt.tight_layout(rect=[0.08, 0.02, 0.85, 0.96])
    plt.savefig('oscope_output/summary_all_nodes.png', dpi=150,
                facecolor='#000000', edgecolor='none')
    print("  Saved: oscope_output/summary_all_nodes.png")
    plt.close()


if __name__ == '__main__':
    main()

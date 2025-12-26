# AeroTone Model 12 - Propeller-Based Musical Instrument Simulation

A simulation of a fictional 1979 electromechanical musical instrument that uses spinning propellers to generate musical tones.

## Quick Start

```bash
# Install dependencies (if needed)
pip install numpy scipy sounddevice matplotlib

# Run the simple demo - just hear a propeller tone
python demo_simple.py

# Run with a different note
python demo_simple.py C3
```

## Demos

### 1. Simple Demo (`demo_simple.py`)
Plays a single propeller voice. Good for first test.
```bash
python demo_simple.py [note]
# Example: python demo_simple.py A2
```

### 2. Beat Frequency Demo (`demo_beats.py`)
Demonstrates the beat frequency phenomenon with two propellers.
```bash
python demo_beats.py
```

### 3. Visual Demo (`demo_visual.py`)
Real-time visualization with RPM gauge, waveform, and spectrum.
```bash
python demo_visual.py [note]
```

### 4. Interactive Demo (`demo_interactive.py`)
Play like a keyboard instrument (macOS/Linux only).
```bash
python demo_interactive.py
```

## Available Notes

| Note | Frequency | Target RPM |
|------|-----------|------------|
| A2   | 110.00 Hz | 1,320      |
| A#2  | 116.54 Hz | 1,398      |
| B2   | 123.47 Hz | 1,482      |
| C3   | 130.81 Hz | 1,570      |
| C#3  | 138.59 Hz | 1,663      |
| D3   | 146.83 Hz | 1,762      |
| D#3  | 155.56 Hz | 1,867      |
| E3   | 164.81 Hz | 1,978      |
| F3   | 174.61 Hz | 2,095      |
| F#3  | 185.00 Hz | 2,220      |
| G3   | 196.00 Hz | 2,352      |
| G#3  | 207.65 Hz | 2,492      |

## Project Structure

```
musicProps/
├── aerotone/
│   ├── __init__.py      # Package init
│   ├── motor.py         # DC motor simulation
│   ├── propeller.py     # Propeller aerodynamics
│   ├── acoustics.py     # Sound synthesis
│   └── voice.py         # Integrated voice channel
├── demo_simple.py       # Basic audio test
├── demo_beats.py        # Beat frequency demo
├── demo_visual.py       # Visual + audio demo
├── demo_interactive.py  # Keyboard playable
└── requirements.txt     # Dependencies
```

## What You Should Hear

- **Pitched tone** - Clear musical note at the target frequency
- **Harmonics** - Rich timbre from blade passage overtones
- **Texture** - Subtle broadband noise like propeller "air"
- **Beat frequencies** - Wobble when two props are mistuned

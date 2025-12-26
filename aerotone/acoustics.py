"""
Propeller Acoustic Synthesis for AeroTone

Generates realistic propeller sound based on aerodynamic parameters.
Based on propeller acoustics research (particularly Selfridge et al.)

The propeller produces three main sound components:

1. TONAL (Blade Passage Frequency + harmonics)
   - Thickness noise: Air displaced by blade volume
   - Loading noise: Thrust/drag forces on air
   - Dominates at low frequencies

2. BROADBAND (Turbulent noise)
   - Trailing edge noise: Turbulent boundary layer
   - Tip vortex noise: Swirling at blade tips
   - Inflow turbulence: Disturbed inlet air
   - Dominates at high frequencies

3. MODULATION (Variation and texture)
   - Blade imbalance: 1× RPM amplitude modulation
   - Motor ripple: Slight speed variations
   - Turbulent fluctuations: Random variations
"""

import numpy as np
from scipy import signal
from dataclasses import dataclass


@dataclass
class AcousticParams:
    """Parameters controlling the acoustic synthesis"""

    # Tonal content
    num_harmonics: int = 12          # Number of BPF harmonics
    harmonic_rolloff: float = 1.8    # Rolloff exponent (higher = faster decay)

    # Thickness vs loading balance
    thickness_weight: float = 0.3    # Contribution of thickness noise
    loading_weight: float = 0.7      # Contribution of loading noise

    # Broadband noise
    broadband_level: float = 0.08    # Relative to tonal (0 = none)
    broadband_cutoff: float = 4000   # Hz - upper frequency limit

    # Serration effect on broadband
    serration_reduction: float = 0.6 # Factor when serrations present

    # Modulation
    rpm_modulation: float = 0.005    # Fractional RPM variation
    amplitude_modulation: float = 0.03  # AM depth from imbalance

    # Master level
    master_gain: float = 0.8         # Output amplitude (0-1)


class PropellerSynth:
    """
    Real-time propeller sound synthesizer.

    Generates audio samples based on current RPM and propeller parameters.
    Designed for low-latency streaming output.
    """

    def __init__(self, sample_rate: int = 44100, params: AcousticParams = None):
        self.sample_rate = sample_rate
        self.params = params or AcousticParams()

        # Phase accumulators for each harmonic
        self.harmonic_phases = np.zeros(self.params.num_harmonics)

        # Phase accumulator for modulation
        self.mod_phase = 0.0

        # Current operating point
        self.bpf = 0.0          # Blade passage frequency
        self.thrust = 0.0       # Thrust (affects amplitude)
        self.num_blades = 12    # For modulation frequency
        self.has_serrations = True

        # Noise generator state (for continuity)
        self.noise_state = np.random.RandomState(42)
        self.noise_filter_state = None

        # Smoothing for parameter changes
        self.bpf_smooth = 0.0
        self.amp_smooth = 0.0
        self.smoothing_factor = 0.995  # Per-sample smoothing

    def set_operating_point(self, bpf: float, thrust: float = 1.0,
                            num_blades: int = 12, has_serrations: bool = True):
        """
        Set the current operating point.

        Args:
            bpf: Blade passage frequency in Hz
            thrust: Relative thrust (affects volume)
            num_blades: Number of blades (for modulation)
            has_serrations: Whether prop has TE serrations
        """
        self.bpf = bpf
        self.thrust = thrust
        self.num_blades = num_blades
        self.has_serrations = has_serrations

    def generate(self, num_samples: int) -> np.ndarray:
        """
        Generate audio samples.

        Args:
            num_samples: Number of samples to generate

        Returns:
            numpy array of audio samples (-1 to 1)
        """
        p = self.params
        output = np.zeros(num_samples)

        # Sample times
        t_step = 1.0 / self.sample_rate

        for i in range(num_samples):
            # Smooth parameter changes
            self.bpf_smooth += (self.bpf - self.bpf_smooth) * (1 - self.smoothing_factor)
            target_amp = np.sqrt(self.thrust) * p.master_gain if self.bpf > 0 else 0
            self.amp_smooth += (target_amp - self.amp_smooth) * (1 - self.smoothing_factor)

            if self.bpf_smooth < 1.0:  # Below audible
                continue

            # Calculate modulation (1× RPM frequency)
            rpm_freq = self.bpf_smooth / self.num_blades  # RPM in Hz
            self.mod_phase += 2.0 * np.pi * rpm_freq * t_step
            if self.mod_phase > 2.0 * np.pi:
                self.mod_phase -= 2.0 * np.pi

            # Amplitude modulation from imbalance
            am = 1.0 + p.amplitude_modulation * np.sin(self.mod_phase)

            # Frequency modulation (slight RPM wobble)
            fm = 1.0 + p.rpm_modulation * np.sin(self.mod_phase * 0.7)

            # Generate tonal content (harmonics of BPF)
            tonal = 0.0
            for h in range(self.params.num_harmonics):
                harmonic_num = h + 1
                freq = self.bpf_smooth * harmonic_num * fm

                # Update phase
                phase_inc = 2.0 * np.pi * freq * t_step
                self.harmonic_phases[h] += phase_inc
                if self.harmonic_phases[h] > 2.0 * np.pi:
                    self.harmonic_phases[h] -= 2.0 * np.pi

                # Amplitude with rolloff
                amp = 1.0 / (harmonic_num ** p.harmonic_rolloff)

                # Thickness vs loading weighting
                # Thickness: even harmonics weaker
                # Loading: odd harmonics slightly stronger
                if harmonic_num % 2 == 0:
                    amp *= 0.7  # Even harmonics reduced

                tonal += amp * np.sin(self.harmonic_phases[h])

            # Normalize tonal
            tonal /= sum(1.0 / (h ** p.harmonic_rolloff) for h in range(1, p.num_harmonics + 1))

            output[i] = tonal * am * self.amp_smooth

        # Add broadband noise (more efficient to do in bulk)
        if p.broadband_level > 0 and self.bpf_smooth > 1.0:
            noise = self._generate_shaped_noise(num_samples)
            output += noise * self.amp_smooth

        # Final limiting
        output = np.clip(output, -1.0, 1.0)

        return output

    def _generate_shaped_noise(self, num_samples: int) -> np.ndarray:
        """
        Generate frequency-shaped broadband noise.

        Propeller broadband noise has a characteristic spectrum:
        - Rising toward BPF
        - Peak near BPF
        - Gradual rolloff above
        """
        p = self.params

        # Generate white noise
        noise = self.noise_state.randn(num_samples)

        # Apply low-pass filter
        cutoff = min(p.broadband_cutoff, self.sample_rate * 0.45)
        if cutoff > 100:
            b, a = signal.butter(2, cutoff / (self.sample_rate / 2), 'low')
            if self.noise_filter_state is None:
                self.noise_filter_state = signal.lfilter_zi(b, a)
            noise, self.noise_filter_state = signal.lfilter(
                b, a, noise, zi=self.noise_filter_state)

        # Scale by broadband level
        level = p.broadband_level
        if self.has_serrations:
            level *= p.serration_reduction

        return noise * level

    def reset(self):
        """Reset synthesizer state"""
        self.harmonic_phases = np.zeros(self.params.num_harmonics)
        self.mod_phase = 0.0
        self.bpf_smooth = 0.0
        self.amp_smooth = 0.0
        self.noise_filter_state = None


class MultiVoiceSynth:
    """
    Multi-voice synthesizer for the complete AeroTone.

    Manages 12 independent propeller voices and mixes their outputs.
    Handles beat frequencies when voices are slightly mistuned.
    """

    def __init__(self, num_voices: int = 12, sample_rate: int = 44100):
        self.num_voices = num_voices
        self.sample_rate = sample_rate

        # Create individual voice synthesizers
        self.voices = [PropellerSynth(sample_rate) for _ in range(num_voices)]

        # Voice states
        self.voice_active = [False] * num_voices
        self.voice_bpf = [0.0] * num_voices
        self.voice_thrust = [0.0] * num_voices

    def set_voice(self, voice_idx: int, bpf: float, thrust: float = 1.0,
                  active: bool = True):
        """
        Set parameters for a single voice.

        Args:
            voice_idx: Voice index (0-11)
            bpf: Blade passage frequency
            thrust: Relative thrust level
            active: Whether voice is sounding
        """
        if 0 <= voice_idx < self.num_voices:
            self.voice_active[voice_idx] = active
            self.voice_bpf[voice_idx] = bpf
            self.voice_thrust[voice_idx] = thrust
            self.voices[voice_idx].set_operating_point(
                bpf if active else 0, thrust)

    def generate(self, num_samples: int) -> np.ndarray:
        """
        Generate mixed output from all voices.

        Returns:
            Mono audio samples
        """
        output = np.zeros(num_samples)

        active_count = sum(self.voice_active)
        if active_count == 0:
            return output

        # Mix voices with proper level management
        for i, voice in enumerate(self.voices):
            if self.voice_active[i]:
                output += voice.generate(num_samples)

        # Normalize to prevent clipping with multiple voices
        # Use sqrt(n) rule for uncorrelated signals
        output /= np.sqrt(max(active_count, 1))

        return output

    def reset(self):
        """Reset all voices"""
        for voice in self.voices:
            voice.reset()
        self.voice_active = [False] * self.num_voices


def generate_test_tone(frequency: float, duration: float = 2.0,
                       sample_rate: int = 44100) -> np.ndarray:
    """
    Generate a test propeller tone at a fixed frequency.

    Useful for quickly testing the acoustic model.
    """
    synth = PropellerSynth(sample_rate)
    synth.set_operating_point(bpf=frequency, thrust=1.0)

    # Pre-settle the smoothing
    synth.bpf_smooth = frequency
    synth.amp_smooth = synth.params.master_gain

    num_samples = int(duration * sample_rate)
    return synth.generate(num_samples)

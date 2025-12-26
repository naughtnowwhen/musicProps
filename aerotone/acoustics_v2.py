"""
Advanced Propeller Acoustic Synthesis for AeroTone (v2)

Significant improvements over v1:

1. BLADE PASSAGE WAVEFORM
   Instead of sine waves, models actual pressure pulse shape.
   Each blade creates a sharp pressure disturbance as it passes.
   The waveform is asymmetric (fast rise, slower decay).

2. DOPPLER MODULATION
   Blade tips moving toward/away from listener create pitch shifts.
   Creates the characteristic "swirling" quality of propeller sound.

3. DUCTED CHAMBER ACOUSTICS
   Models the resonance of the acoustic chamber/horn.
   Adds characteristic coloration based on chamber dimensions.

4. IMPROVED TURBULENCE
   More realistic broadband noise with proper spectral shape.
   Includes tip vortex and trailing edge noise components.

Based on propeller acoustics research:
  - Farassat's formulation for thickness and loading noise
  - Doppler shift from blade tip velocity
  - Helmholtz resonator for chamber effects
"""

import numpy as np
from scipy import signal
from dataclasses import dataclass
from typing import Optional


@dataclass
class AdvancedAcousticParams:
    """Parameters for advanced acoustic synthesis"""

    # === Blade Waveform ===
    num_harmonics: int = 16          # More harmonics for sharper waveform
    pulse_sharpness: float = 0.7     # 0=sine, 1=impulse-like
    pulse_asymmetry: float = 0.3     # Asymmetric rise/fall

    # === Doppler ===
    doppler_intensity: float = 0.02  # Max frequency deviation from tip motion
    blade_tip_mach: float = 0.15     # Blade tip velocity / speed of sound

    # === Chamber Acoustics ===
    chamber_resonance_hz: float = 280    # Primary resonance frequency
    chamber_q: float = 4.0               # Resonance Q factor (sharpness)
    chamber_size_m: float = 0.3          # Approximate chamber depth
    chamber_mix: float = 0.4             # Wet/dry mix (0=dry, 1=full resonance)

    # === Turbulence Noise ===
    broadband_level: float = 0.12        # Overall noise level
    tip_vortex_level: float = 0.06       # High-freq tip vortex contribution
    trailing_edge_level: float = 0.04    # Mid-freq trailing edge noise
    turbulence_correlation: float = 0.3  # Correlation with blade passage

    # === Modulation ===
    imbalance_am: float = 0.04           # Amplitude modulation from imbalance
    motor_ripple: float = 0.008          # Motor electrical ripple
    flutter_amount: float = 0.003        # Random pitch flutter

    # === Output ===
    master_gain: float = 0.75
    output_saturation: float = 0.95      # Soft clip threshold


@dataclass
class ChamberParams:
    """Acoustic chamber/duct parameters"""
    diameter: float = 0.5       # Chamber diameter (m)
    depth: float = 0.3          # Chamber depth (m)
    horn_flare: float = 1.2     # Horn expansion ratio
    wall_absorption: float = 0.1  # Wall absorption coefficient


class BladeWaveformGenerator:
    """
    Generates realistic blade passage waveforms.

    Instead of simple sines, creates the actual pressure signature
    of a blade passing through air:
    - Fast pressure rise as leading edge arrives
    - Peak as blade thickness maximum passes
    - Slower decay as trailing edge departs
    - Slight negative pressure in wake
    """

    def __init__(self, sample_rate: int, params: AdvancedAcousticParams):
        self.sample_rate = sample_rate
        self.params = params

        # Pre-compute blade passage waveform (one cycle)
        self.waveform_samples = 1024
        self.blade_waveform = self._compute_blade_waveform()

        # Phase accumulator
        self.phase = 0.0

    def _compute_blade_waveform(self) -> np.ndarray:
        """
        Compute one cycle of the blade passage waveform.

        Models thickness noise (volume displacement) and
        loading noise (thrust force).
        """
        p = self.params
        n = self.waveform_samples
        t = np.linspace(0, 1, n, endpoint=False)

        # === Thickness Noise Component ===
        # Blade displaces air - fast rise, slower fall
        # Model as asymmetric pulse
        rise_width = 0.3 * (1 - p.pulse_asymmetry)
        fall_width = 0.3 * (1 + p.pulse_asymmetry)

        # Gaussian-ish pulse with asymmetry
        center = 0.35  # Slightly forward
        thickness = np.zeros(n)
        for i, ti in enumerate(t):
            if ti < center:
                # Rising edge
                x = (ti - center) / rise_width
                thickness[i] = np.exp(-x**2 * (1 + p.pulse_sharpness * 2))
            else:
                # Falling edge
                x = (ti - center) / fall_width
                thickness[i] = np.exp(-x**2 * (1 + p.pulse_sharpness * 2))

        # Add slight undershoot (wake depression)
        wake_center = 0.7
        wake_width = 0.15
        wake = -0.2 * np.exp(-((t - wake_center) / wake_width)**2)
        thickness += wake

        # === Loading Noise Component ===
        # Thrust force - roughly follows blade angle of attack
        # More sinusoidal but with sharp transitions
        loading = np.sin(2 * np.pi * t)
        # Sharpen transitions
        loading = np.sign(loading) * np.abs(loading) ** (1 - p.pulse_sharpness * 0.5)

        # === Combine ===
        # Thickness dominates at low frequencies, loading at higher
        waveform = 0.4 * thickness + 0.6 * loading

        # Normalize
        waveform /= np.max(np.abs(waveform))

        return waveform

    def generate(self, num_samples: int, frequency: float) -> np.ndarray:
        """
        Generate blade waveform at given frequency.

        Uses wavetable lookup with linear interpolation.
        """
        if frequency < 1.0:
            return np.zeros(num_samples)

        output = np.zeros(num_samples)
        phase_inc = frequency / self.sample_rate

        for i in range(num_samples):
            # Wavetable lookup with interpolation
            table_pos = self.phase * self.waveform_samples
            idx = int(table_pos)
            frac = table_pos - idx
            idx = idx % self.waveform_samples
            next_idx = (idx + 1) % self.waveform_samples

            # Linear interpolation
            output[i] = (self.blade_waveform[idx] * (1 - frac) +
                        self.blade_waveform[next_idx] * frac)

            # Update phase
            self.phase += phase_inc
            if self.phase >= 1.0:
                self.phase -= 1.0

        return output


class DopplerModulator:
    """
    Models Doppler shift from rotating blade tips.

    As blade tips move toward the listener, pitch rises.
    As they move away, pitch falls.
    This creates a subtle but characteristic "swirling" effect.
    """

    def __init__(self, params: AdvancedAcousticParams):
        self.params = params
        self.phase = 0.0

    def get_frequency_modulation(self, base_freq: float, num_blades: int,
                                 num_samples: int, sample_rate: int) -> np.ndarray:
        """
        Get frequency modulation array for Doppler effect.

        Returns multiplier for base frequency (1.0 = no shift).
        """
        p = self.params
        output = np.ones(num_samples)

        if p.doppler_intensity < 0.001:
            return output

        # Doppler shift cycles at blade passage rate
        # Each blade creates one toward-away cycle
        rpm_freq = base_freq / num_blades
        phase_inc = rpm_freq / sample_rate

        for i in range(num_samples):
            # Blade tip velocity component toward listener
            # Varies sinusoidally as blade rotates
            tip_velocity_ratio = np.sin(2 * np.pi * self.phase * num_blades)

            # Doppler shift: f' = f * (1 + v/c)
            # v/c = tip_mach * sin(angle)
            doppler = 1.0 + p.doppler_intensity * tip_velocity_ratio

            output[i] = doppler

            self.phase += phase_inc
            if self.phase >= 1.0:
                self.phase -= 1.0

        return output


class AcousticChamber:
    """
    Models the acoustic chamber/duct resonance.

    The propeller sits in a ducted enclosure that:
    - Has resonant frequencies (Helmholtz + pipe modes)
    - Colors the sound character
    - Affects directivity
    """

    def __init__(self, sample_rate: int, params: AdvancedAcousticParams):
        self.sample_rate = sample_rate
        self.params = params

        # Design resonant filter
        self._design_chamber_filter()

        # Filter state
        self.filter_state = None

    def _design_chamber_filter(self):
        """Design IIR filter modeling chamber resonance."""
        p = self.params

        # Primary resonance (Helmholtz-like)
        f0 = p.chamber_resonance_hz
        q = p.chamber_q

        # Normalize frequency
        w0 = f0 / (self.sample_rate / 2)
        w0 = min(w0, 0.95)  # Keep below Nyquist

        # Second-order resonant filter (peaking EQ style)
        # H(s) = (s^2 + s*(A/Q)*w0 + w0^2) / (s^2 + s/(A*Q)*w0 + w0^2)
        # Simplified to bandpass + allpass blend

        try:
            # Bandpass for resonance
            self.b_res, self.a_res = signal.iirpeak(w0, q)
        except:
            # Fallback if scipy version doesn't have iirpeak
            bw = w0 / q
            self.b_res, self.a_res = signal.butter(2, [max(0.01, w0 - bw/2),
                                                       min(0.99, w0 + bw/2)], 'band')

        # Secondary resonance (first pipe mode)
        f1 = f0 * 2.2  # Approximate
        w1 = min(f1 / (self.sample_rate / 2), 0.95)
        try:
            self.b_res2, self.a_res2 = signal.iirpeak(w1, q * 0.7)
        except:
            self.b_res2, self.a_res2 = [1], [1]

    def process(self, audio: np.ndarray) -> np.ndarray:
        """Apply chamber resonance to audio."""
        p = self.params

        if p.chamber_mix < 0.01:
            return audio

        # Apply resonant filter
        if self.filter_state is None:
            self.filter_state = signal.lfilter_zi(self.b_res, self.a_res) * audio[0]

        resonant, self.filter_state = signal.lfilter(
            self.b_res, self.a_res, audio, zi=self.filter_state)

        # Mix dry and wet
        output = audio * (1 - p.chamber_mix) + resonant * p.chamber_mix

        return output


class TurbulenceNoiseGenerator:
    """
    Generates realistic propeller turbulence noise.

    Components:
    - Tip vortex noise (high frequency, tonal-ish)
    - Trailing edge noise (broadband, correlated with blade passage)
    - Inflow turbulence (low frequency rumble)
    """

    def __init__(self, sample_rate: int, params: AdvancedAcousticParams):
        self.sample_rate = sample_rate
        self.params = params

        # Noise generator
        self.rng = np.random.RandomState(42)

        # Filter states
        self.te_filter_state = None
        self.tip_filter_state = None
        self.lf_filter_state = None

        # Design filters
        self._design_filters()

    def _design_filters(self):
        """Design spectral shaping filters."""
        sr = self.sample_rate

        # Trailing edge noise: bandpass around 1-3 kHz
        self.te_b, self.te_a = signal.butter(3, [1000/(sr/2), 3000/(sr/2)], 'band')

        # Tip vortex noise: highpass above 2 kHz
        self.tip_b, self.tip_a = signal.butter(2, 2000/(sr/2), 'high')

        # Low frequency inflow turbulence
        self.lf_b, self.lf_a = signal.butter(2, 200/(sr/2), 'low')

    def generate(self, num_samples: int, bpf: float, blade_phase: float) -> np.ndarray:
        """
        Generate turbulence noise.

        Args:
            num_samples: Samples to generate
            bpf: Current blade passage frequency
            blade_phase: Current blade phase (for correlation)
        """
        p = self.params

        # Base white noise
        noise = self.rng.randn(num_samples)

        output = np.zeros(num_samples)

        # === Trailing Edge Noise ===
        if p.trailing_edge_level > 0:
            if self.te_filter_state is None:
                self.te_filter_state = signal.lfilter_zi(self.te_b, self.te_a) * 0

            te_noise, self.te_filter_state = signal.lfilter(
                self.te_b, self.te_a, noise, zi=self.te_filter_state)

            # Modulate with blade passage (turbulence bursts as blade passes)
            if bpf > 10 and p.turbulence_correlation > 0:
                t = np.arange(num_samples) / self.sample_rate
                blade_mod = 0.5 + 0.5 * np.cos(2 * np.pi * bpf * t + blade_phase)
                blade_mod = blade_mod ** 0.5  # Soften modulation
                te_noise *= (1 - p.turbulence_correlation) + p.turbulence_correlation * blade_mod

            output += te_noise * p.trailing_edge_level

        # === Tip Vortex Noise ===
        if p.tip_vortex_level > 0:
            if self.tip_filter_state is None:
                self.tip_filter_state = signal.lfilter_zi(self.tip_b, self.tip_a) * 0

            tip_noise, self.tip_filter_state = signal.lfilter(
                self.tip_b, self.tip_a, noise * 0.7, zi=self.tip_filter_state)

            output += tip_noise * p.tip_vortex_level

        # === Low Frequency Rumble ===
        lf_level = p.broadband_level * 0.3
        if lf_level > 0:
            if self.lf_filter_state is None:
                self.lf_filter_state = signal.lfilter_zi(self.lf_b, self.lf_a) * 0

            lf_noise, self.lf_filter_state = signal.lfilter(
                self.lf_b, self.lf_a, noise * 0.5, zi=self.lf_filter_state)

            output += lf_noise * lf_level

        return output * p.broadband_level


class AdvancedPropellerSynth:
    """
    Advanced propeller sound synthesizer.

    Combines all acoustic modeling components:
    - Realistic blade waveform
    - Doppler modulation
    - Chamber resonance
    - Turbulence noise
    """

    def __init__(self, sample_rate: int = 44100,
                 params: AdvancedAcousticParams = None):
        self.sample_rate = sample_rate
        self.params = params or AdvancedAcousticParams()

        # Sub-modules
        self.blade_gen = BladeWaveformGenerator(sample_rate, self.params)
        self.doppler = DopplerModulator(self.params)
        self.chamber = AcousticChamber(sample_rate, self.params)
        self.turbulence = TurbulenceNoiseGenerator(sample_rate, self.params)

        # State
        self.bpf = 0.0
        self.thrust = 0.0
        self.num_blades = 12

        # Smoothing
        self.bpf_smooth = 0.0
        self.amp_smooth = 0.0
        self.smoothing_tau = 0.02  # 20ms smoothing time constant

        # Harmonics phases (for additional harmonics beyond fundamental)
        self.harmonic_phases = np.zeros(16)

        # Blade phase tracking
        self.blade_phase = 0.0

    def set_operating_point(self, bpf: float, thrust: float = 1.0,
                            num_blades: int = 12, **kwargs):
        """Set current operating point."""
        self.bpf = bpf
        self.thrust = thrust
        self.num_blades = num_blades

    def generate(self, num_samples: int) -> np.ndarray:
        """Generate audio samples."""
        p = self.params
        sr = self.sample_rate

        # Smooth parameters
        smooth_alpha = 1.0 - np.exp(-num_samples / (self.smoothing_tau * sr))
        self.bpf_smooth += (self.bpf - self.bpf_smooth) * smooth_alpha
        target_amp = np.sqrt(max(self.thrust, 0)) * p.master_gain if self.bpf > 0 else 0
        self.amp_smooth += (target_amp - self.amp_smooth) * smooth_alpha

        if self.bpf_smooth < 5.0:  # Below useful range
            return np.zeros(num_samples)

        # === Generate Tonal Content ===

        # Get Doppler modulation
        doppler_mod = self.doppler.get_frequency_modulation(
            self.bpf_smooth, self.num_blades, num_samples, sr)

        # Generate fundamental with blade waveform
        # Apply Doppler by varying playback rate
        tonal = np.zeros(num_samples)

        # Fundamental
        for i in range(num_samples):
            freq = self.bpf_smooth * doppler_mod[i]

            # Add flutter
            flutter = 1.0 + p.flutter_amount * np.sin(self.blade_phase * 7.3)
            freq *= flutter

            # Update blade waveform generator phase and sample
            phase_inc = freq / sr
            table_pos = self.blade_gen.phase * self.blade_gen.waveform_samples
            idx = int(table_pos) % self.blade_gen.waveform_samples
            next_idx = (idx + 1) % self.blade_gen.waveform_samples
            frac = table_pos - int(table_pos)

            sample = (self.blade_gen.blade_waveform[idx] * (1 - frac) +
                     self.blade_gen.blade_waveform[next_idx] * frac)

            # Add harmonics with reducing amplitude
            for h in range(1, min(8, p.num_harmonics)):
                harm_freq = freq * (h + 1)
                if harm_freq < sr / 2:
                    self.harmonic_phases[h] += harm_freq / sr
                    if self.harmonic_phases[h] >= 1.0:
                        self.harmonic_phases[h] -= 1.0

                    harm_amp = 1.0 / ((h + 1) ** 1.5)
                    sample += harm_amp * np.sin(2 * np.pi * self.harmonic_phases[h])

            tonal[i] = sample

            # Update fundamental phase
            self.blade_gen.phase += phase_inc
            if self.blade_gen.phase >= 1.0:
                self.blade_gen.phase -= 1.0

            self.blade_phase += phase_inc
            if self.blade_phase >= 1.0:
                self.blade_phase -= 1.0

        # Normalize tonal
        tonal_max = np.max(np.abs(tonal))
        if tonal_max > 0:
            tonal /= tonal_max

        # === Add Amplitude Modulation (imbalance, motor ripple) ===
        t = np.arange(num_samples) / sr
        rpm_freq = self.bpf_smooth / self.num_blades

        # Imbalance at 1× RPM
        am_imbalance = 1.0 + p.imbalance_am * np.sin(2 * np.pi * rpm_freq * t)

        # Motor ripple (electrical, often at 2× or 6× electrical frequency)
        am_motor = 1.0 + p.motor_ripple * np.sin(2 * np.pi * rpm_freq * 6 * t)

        tonal *= am_imbalance * am_motor

        # === Generate Turbulence Noise ===
        noise = self.turbulence.generate(num_samples, self.bpf_smooth, self.blade_phase)

        # === Combine ===
        output = tonal * self.amp_smooth + noise * self.amp_smooth

        # === Apply Chamber Resonance ===
        output = self.chamber.process(output)

        # === Soft Saturation ===
        # Gentle limiting for analog-like character
        threshold = p.output_saturation
        output = np.tanh(output / threshold) * threshold

        return output

    def reset(self):
        """Reset all state."""
        self.blade_gen.phase = 0.0
        self.doppler.phase = 0.0
        self.harmonic_phases = np.zeros(16)
        self.blade_phase = 0.0
        self.bpf_smooth = 0.0
        self.amp_smooth = 0.0
        self.chamber.filter_state = None
        self.turbulence.te_filter_state = None
        self.turbulence.tip_filter_state = None
        self.turbulence.lf_filter_state = None


# Convenience function to create with custom chamber
def create_synth_with_chamber(sample_rate: int = 44100,
                               chamber_freq: float = 280,
                               chamber_q: float = 4.0) -> AdvancedPropellerSynth:
    """Create synth with custom chamber resonance."""
    params = AdvancedAcousticParams(
        chamber_resonance_hz=chamber_freq,
        chamber_q=chamber_q,
    )
    return AdvancedPropellerSynth(sample_rate, params)

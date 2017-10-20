# [Novo](https://github.com/m-labs/sinara/wiki/Novo) to [Urukul](https://github.com/m-labs/sinara/wiki/Urukul) servo controller

Provisional plans for using Novo as a low-bandwidth (>100 kHz loop bandwidth) feedback controller, generally servoing a Urukul DDS amplitude.

## Simple approach: software

The first iteration will use the standard EEM PHYs, i.e. TTL and simple SPI. The
interface will be native, i.e. no multi-line SPI, standard SPI read-back.

There would be no need to write custom gateware or firmware to accelerate the feedback loops. Instead, we will make use of DRTIO and do the maths on the core device or host PC, using one of the following schemes:

1. integer math on the core device (run a couple dozen PI cycles in integer math every few experiments). Expect this to take TBD per loop (SPI ADC access TBD, DRTIO ADC read ~3us, PI maths ~1us, DRTIO DDS reprogram ~8us).
2. maths on moninj from the host, completely without kernels.
3. experiment kernels broadcasting measurements as datasets, running the PI loop on the host, and then the kernels applying the updates again.

## Advanced approach: gateware

### Goal and scope

- Kasli connected to Novo and Urukul to provide as many RF channels as possible given the IDCs (inc backplane) and FPGA resources available. Any unused IDCs should be configured in a sensible arrangement of our "standard" configurations (SPI/TTL or SERDES).
- This wiring could allow (with 12 EEM IDC slots, 8 on Kasli and 4 on the backplane) a fast 16 DDS channel setup:
  * 1 x Kasli
  * 2 x Novo
  * 4 x Urukul
- There will be custom gateware optimized for maximum data rate out of
  Novo (8 channel synchronous sampling, source-synchronous data clock) and maximum update rate into Urukul (the (b) configuration with two
  IDC and quad-SPI)

### Profiles

- For each ADC-DDS channel, we have a fixed number (at least 4, up to 16 if "conveniently possible") of "profiles" on Kasli each with a user-programmed frequency, phase and amplitude as well as individual filter gains, set points and accumulators.
- Active profile for each channel is set via DRTIO.
- Expose active profile on moninj.

### DDS (Urukul)

- DDSs are reprogrammed with settings from the active profile at a constant rate of ~1MSPS. Double buffer FTW+ASF(+POW) in gateware and perform continuous update of the DDSs.
- This restricts the configuration and usage of the DDS to **only** FTW/POW/ASF: fixed profile pins (single DDS register profile), no OSK (?), fixed IO_UPDATE schedule, no configurable DDS accu clear, "relative phase offset mode", no DRG (?), no DDS RAM (?), no fiddling with the DDS PLL, cos/sin...
- DDS updates occur at deterministic times, but do not all need to occur at the same time.
- Synchronous reset via DRTIO (AD9912) or specific SYNC circuitry (AD9910) allow synchronization of DDS update cycle with global RTIO clock.
- Precise timing resolution provided by RF switches (assume switches closed when switching active profile or updating the profile registers)
- Do FTW+ASF+POW updates in a single transaction (IO_UPDATE). Can not ditch POW for speed. AD9910 packages FTW/POW/ASF in one 64 bit profile register, need to update all three.
- RF switch timing resolution: 10ns (RTIO coarse).
- Estimate update interval for QSPI and 125 MHz RTIO coarse:
  `16 ns*(8 instruction + 64 FTW/POW/ASF) = 1.168 µs` plus some overhead.
- Expose FTW/ASF on moninj.
- Initial configuration machinery (SYNC, PLL) for the DDS. Hard-coded set-up. Initial suggestion for DDS register values:

| Register | Value | Comment |
| :---        |     :---:      | :--- |
| 0x00 (CFR1) | 0x00 40 00 02 | inverse sinc enabled,  no autoclear phase accumulator, 3-wire SPI |
| 0x01 (CFR2) | 0x01 40 00 00 | ASF, SYNC_CLK, SYNC_SMP_ERR enabled |
| 0x02 (CFR3) | 0x35 38 81 14 | REF_CLK high current drive, VCO 5 (1GHz), Icp=387uA (not optimised), PLL enabled N=10 (100MHz REF_CLK), REF_CLK divider disabled |
| 0x03 (AUX_DAC) | 0x00 00 00 7F | 20.07mA |
| 0x04 (IO_UPDATE) | don't care | ineffective |
| 0x0A (multi-chip sync) | TBD | ? |

### ADC (Novo)

- ADCs sampled at same rate as DDS updates.
- Throttle the ADC sampling to the DDS updates.
- Deterministic ADC-sample to DDS-update delay should be possible. It is **not** required. The ADC inputs have a 2-pole low-pass filter at 250kHz to remove high-frequency signals, so small levels of timing jitter will not be a problem as long as they are (much) less than the loop bandwidth.
- Oversampling is not a requirement of this design.
- Novo PGIA gain and attenuators not touched by servo
- Expose data on moninj.
- Hard-coded CONV timing, LVDS frequency for simplicity.

### Filter

- PI loop-filter (first order IIR) used to steer the programmed profile amplitude using ASF so that the ADC reaches the setpoint.
- Python support to generate IIR coefficients from PI "physicist parameters".
- Tie the IIRs to the DDS ASF channels and route the ADC matrix to the filter inputs. If the crossbar fabric for the routing from ADCs to the IIRs/DDSs is too costly then do fixed routing, with fixed EEM-IDC and ADC:IIR:DDS assignment.
- Support multiple DDS channels sharing the same ADC input.
- Adjustable gains and set-points and independent accumulators (integrators) for each channel and each profile.
- Anti-wind-up functionality (don't integrate further when output railed).
- Saturating behavior, no integer overflows/wrap-arounds.
- Limited to ASF [0, 1] -- no programmable limiters required, users can set the attenuators appropriately to do that.
- Non-real time "railed" indicator that alerts the user when a limit is reached.
- No modulation/demodulation or auto-lock (assuming this is for intensity servos, rather than cavity locks etc)
- No "integrator reset"
- Smart linkage of Urukul RF switches and IIR action: servo for active channel/profile enabled when the RF switch is open. Configurable/fixed (~1-10 µs) delay between switch opening and servo activating to allow for transients, AOM propagation, photodiode settling etc.
- "Integrator hold" logic is: integrator active if profile active AND RF switch has been open for channel-specific delay AND (per-channel) integrator enabled bit set. **Integrator enabled bit must be settable in real time. Use case for this is lasers which must be on at the same time, and also share a photodiode. Need to servo one, then the other.**
- Non-real time readout and (less important) override of IIR filter output. Use cases for this and the integrator enable bit: diagnostics/debugging; setting the DDS output to a particular power for aligning AOMs/fibre coupling/etc.
- Setpoint, output: 16 bit min
- Coefficient dynamic range: 19 bit min (to cover the use case below)
- Single width multipliers (18x25).
- Expose setpoint, coefficients, active profile, ADC source, output on moninj.

### Interface/gateware implementation

- The PI logic could be multi-cycle **and** time-shared for channels and profiles, exploiting the ~128 ratio of of PI logic clock (RTIO coarse) and sample clock per channel. Use BRAMS for coefficients, setpoints, and IIR state and a sequencer to drive everything.
  * Can clock the multipliers at half rate for timing
  * 4 BRAMs `16 channels * 4 profiles x 36 bit`: FTW and IIR a1,b0,b1
  * 6 BRAMs `16 * 4 x 18 bit`: POW, setpoint, measured, IIR x1,y0,y1
- Timing should be constant and there should be no timing cross-talk. Disabled channels will not allow the others to run faster. The sequencer will just skip them.
- Since speed is allocated to support 16 concurrent channels per Kasli, we can do a single first order IIR engine with three double-width multipliers (25x(2x18)) and BRAMs for coefficients/states. There would be 8 coarse RTIO cycles left to do one IIR iteration.
- The IIR could even time-share a single multiplier and do each multiplication in two cycles, in a typical MAC architecture... Optimal structure to be chosen for simple and rapid implementation.
- Timing quirk: if the ADC channels are read out 0,2,4,6 and then 1,3,5,7 and the DDS are updated 0-7 in parallel, then, if DDS0 uses ADC7 as input, it can only run its IIR iteration after all ADCs have been read. I.e. an ADC-IID-DDS cycle needs to be completely sequential. (If all DDS channels use ADC7, then we have to wait for the complete read-out before doing any IIR iterations and before doing any DDS update.)
- For 125 MHz RTIO, the minimum delays will be 0.768 µs for ADC readout (250 MHz LVDS data clock), 0.896 µs for all 16 IIR computations (with maximum sharing), and 1.168 µs for DDS updates (62.5 MHz SPI data clock). The pipeline would have three stages (ADC, IIR, DDS) and therefore the sample rate and throughput will be limited by DDS updates to ~0.856 MSPS. If ADC,IIR,DDS are done in sequence, the latency from input to output will be three times the stage latency (3.5 µs), resulting in a loop bandwidth of about 100 kHz (pi phase shift at 142 kHz). This does not include any delays in the analog filters.
- If resources/timing allow, pack the IIR and ADC into one pipeline stage and the DDS update into the other. This would increase the bandwidth by a third.
- Beating between the pipeline stages (if they are run at different rates) should be avoided.
- Since the ASF occupies the MSB of the 64 bit profile register on the AD9910, we could do LSB first, and overlap both ADC sample+transfer and IIR for all channels with the transfer of the previous ASF, IO_UPDATE, new FTW and new POW. In that case latency could be comparable to just one DDS update cycle. But this requires some serious pipeline and BRAM access planning.
- To "adjust lasers with PI filter off": use a profile with unit proportional gain, zero integrator corner and fixed-0 as the ADC input.

#### RTIO channels

Per DDS channel:
  - RF switch

System channels:
  - Urukul SRs for misc DDS pins, leds, attenuator settings
  - Novo SRs for PGIA

Global and serialized configuration channel across all channels (max one RTIO event
per 2 coarse RTIO cycles ~ 1/16ns, but ultimately all synchronized by IO_UPDATE)
  - Per channel:
    - Active profile: 4b
  - Per profile:
    - IIR active: 1b
    - ADC setpoint: 16 bit
    - FTW: 32 bit
    - POW: 16 bit

Over an out-of-band, slow, non-RT, configuration channel
  - Per profile:
    - ADC source: 4b
    - DDS RF switch to IIR activation delay (250 µs max, resolution 1 µs): 8b
    - IIR coefficients: a1, b0, b1: 3x24 bit

There needs to be a mechanism/API/information that allows the targeted scheduling of RTIO events over the global configuration channel to hit the same IO_UPDATE interval.

### API/UI/GUI

Provide an API for playing with/monitoring the IIR coefficients, ADC source, integrator enable, active profile, setpoint, output, FTW.

Needs [scalable moninj](https://github.com/m-labs/artiq/issues/676).

### 'scope functionality:

Beyond the scope of the initial contract, but would be a nice feature to have in the future.

Use cases:
- **Tuning up loop filters**: record the ADC values in real time while stepping the set-point. Use input DMA?
- **Diagnostics**: it would be great to be able to record the ADC values during an experiment to help identify/track down issues (noise eater ringing/railing DDS glitches/etc). Trigger-able recording of all ADC values to something like 4k samples deep, for later non-real-time readout. Potentially allow the acquisition rate to be a programmable fraction of the ADC sample rate.

### Work plan

#### Design

Initial design, resource usage, and feasibility (without hardware, ASAP)

The initial design is developed outside Sinara or Artiq. It is hosted at https://github.com/m-labs/nu-servo.

1. Sketch and prototype filter: first order IIR core with coefficients, anti-windup, saturation behavior.
  * Demonstrate in simulation, testbench.
  * Demonstrate PI coefficient dynamic range.
  * Demonstrate PI transfer function with testbench.
  * Demonstrate sufficiently small loop delay.
  * Synthesize mock-up for XC7A50T.
2. Profile and channel sequencer, IIR time-sharer, setpoint/coefficient/state
  storage.
  * Demonstrate full-rate, all channels, any profile in simulation.
  * Demonstrate sufficiently small loop delay.
  * Synthesize mock-up for XC7A50T.
3. Urukul QSPI interface, FTW/POW/ASF storage.
  * Demonstrate serializer in simulation, synthesize mock-up for XC7A50T.
  * Demonstrate sufficiently small delay.
4. Novo quad-LVDS interface.
  * Demonstrate deserializer in simulation, synthesize mock-up for XC7A50T.
  * Demonstrate sufficiently small delay.
5. Design RTIO interface to profiles/channels/sequencer/globals.
  * Determine resource usage, synthesize mock-up for XC7A50T, including ARTIQ
    core device gateware.

#### Implementation

1. With Novo: stream samples over quad-LVDS into servo, sample monitoring.
  * Demonstrate channel monitoring.
2. With Urukul: stream FTW+POW+ASF updates from servo/RTIO over QSPI, monitoring and injection.
  * Demonstrate RTIO functionality.
  * Demonstrate monitoring and injection.
3. Multichannel/multiprofile/RTIO-controlled servo, ADC/DDS system integration, servo monitoring and injection.
  * Demonstrate on hardware.
  * Test-bench with HITL.


### Case study: laser intensity servo

![system block diagram](servo.png)

Block diagram, illustrating the servo's use as a laser intensity stabiliser.

* loop filter transfer function: H(s) = kp + Ki/s
* We treat the set-point/ADC value and DDS ASF as numbers in the range [0, 1]
* For unipolar signals, the closed-loop voltage at the ADC's input should be between [+1V, +10V], (otherwise the user is expected to change the PGIA gain). The ADC offset from mid-range (0.5) is thus between [0.05, 0.5]
* The closed-loop DDS ASF should be between [0.01, 1], (otherwise the user is expected to change the attenuator setting)
* Make the approximation that the system in linear in DDS amplitude. This is slightly dodgy because: AOMs non-linear, and often operated in saturation to maximise diffraction efficiency; and, even ignoring that, single-pass AOMs are linear in DDS power. However, in practice the assumption of linearity is usually good to a factor of a few.
* the DC open-loop (no loop filter) gain, G_ol, is typically in the range [0.05, 50]
* Assume that the system (modulator etc) is "fast", so that the only significant phase shifts are due to the ADC input filters, PGIA and servo latency. This is typically fine, since the digital delay (ADC reading + DDS programming) is ~2.4us, which should be large compared with factors like AOM propagation delay (<~500ns for a well setup AOM). To do: add a troubleshooting note in the documentation, reminding users to check the rise-time on their photodiodes in case of problems with loop stability.
* Assume that we always want to run the servo as fast as possible (e.g. we're not worried about noise due to the servo etc). > 20kHz unity-gain loop bandwidth is easily achievable (>~65deg phase margin) with current Novo filters, even assuming 1us of time delay in the AOM and max PGIA gain. With a fast AOM, and assuming we move the second Novo filter to 1MHz cut-off, 50kHz should be achievable with 45deg of phase margin.
* `G_ol * ki/(2*pi*f0) = 1 => ki=2*pi*f0/G_ol => ki` between [1e3, 1e7]
* Assume that the P gain is used to add a zero near f0 to improve the phase margin => `kp = ki/(2*pi*f0) = 1/G_ol => kp` between [0.05, 50]. This assumption is generally good to a factor of ~5 or so.
* `kp*fz/fs = kp*ki/(2*pi*kp*fs) = ki/(2*pi*fs)`. For the parameters I investigated, this was always above `20kHz/(1MSPS*G_ol) = 0.02/G_ol >~ 4e-4`


### Set-up/troubleshooting guide

WIP/to do...

1. Calibrate the ADC + photodiode
  - Using laser power meter....
2. Measure the open-loop gain
3. Set P and I gains
4. Check step response and optimise

Troubleshooting:
- The main causes of problems are slow components in the feedback loop, or having an extremely high open-loop gain.
- Is open-loop gain too high? Change DDS attenuator
- Is AOM latency too high? Do a better job of aligning
- Is photodiode slow? Check on scope

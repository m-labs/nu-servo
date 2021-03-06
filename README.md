# LEGACY code

**The gateware and tests have been moved to ARTIQ**
This repository only contains the history and legacy code to test, prototype,
and evaluate the design.
See: https://github.com/m-labs/artiq/tree/master/artiq/gateware/suservo
The code contained here will diverge from the ARTIQ gateware. The latest commit that is known to work with the master branch of this repository is
https://github.com/m-labs/artiq/commit/929ed4471b1f472de81a42ef5b16dd7d5d93f2cc
The last commit that contains the NU-Servo as
a standalone test is fe4b60b9027fc93d9a7c91aec5f62aafb04b847a.

# NU-Servo

NU-Servo is a pipelined, resource efficient IIR filter (a.k.a PI controller). It is tailored to use the [Novogorny 8-channel ADC](https://github.com/m-labs/sinara/wiki/Novogorny) for monitoring the plant, the [Urukul 4-channel DDS](https://github.com/m-labs/sinara/wiki/Urukul) for driving the plant, and the [Kasli FPGA](https://github.com/m-labs/sinara/wiki/Kasli) for performing the computation.

All three devices are part of the [Sinara](https://github.com/m-labs/sinara) ([Wiki](https://github.com/m-labs/sinara/wiki)) device family.

The design and goals of the project are described in [NovoUrukulServo](doc/NovoUrukulServo.md).

## Code

### IIR processing core

* [iir.py](iir.py) Main processing core
* [iir_impl.py](iir_impl.py) Test implementation on Kasli
* [iir_transfer.py](iir_transfer.py) Transfer function simulation tool
* [iir_sim.py](iir_sim.py) Verification and unittesting tool

#### IIR pipeline

* [Pipeline plan](doc/pipeline.ods)

#### IIR states

* idle: no activity
* loading: loading ADC values into x0
* processing: computing y0 and extracting ftw/pow from memory
* shifting: x0 (current measurement) -> x1 (old measurement) value shuffling in sate memory

### ADC interface

* [adc_ser.py](adc_ser.py) Multi-lane LVDS/CMOS ADC interface for LTC2320-16 or
  similar
* [adc_sim.py](adc_sim.py) ADC interface simulation and test bench
* [adc_impl.py](adc_impl.py) Test implementation on Kasli

### DDS interface

* [dds_ser.py](dds_ser.py) Multi-lane LVDS SPI AD9910 interface
* [dds_sim.py](dds_sim.py) DDS interface simulation and test bench
* [dds_impl.py](dds_impl.py) Test implementation on Kasli

### Servo

* [servo_impl.py](servo_impl.py) Test implementation of the ADC-IIR-DDS chain
* [servo_sim.py](servo_sim.py) Full ADC-IIR-DDS pipeline test

## Design aspects

## Overall timing pipeline

```
in 8 ns cycles:
ADC: 30 ns CONVH: 4, 450 ns CONV: 57, 2*16*4 ns (125 MHz DDR LVDS) READ: 16,
48 ns RTT: 6, ODDR/IDDR: 2
IIR: 16 SHIFT, 8 LOAD, 8*4+8+1=41 PROC
DDS: 8*16 ns CMD = 8, 64*2*8 ns PROF = 128, SPI WAIT = 1, IO_UPDATE = 1

ADC CONVH CONV READ RTT
    4     57   16   8
IIR                    LOAD  PROC SHIFT
                       8     41   16
DDS                               CMD PROF WAIT IO_UP
                                  16  128  1    1

SLOT1: 4 + 57 + 16 + 6 + 2 + 8 + 41 = 134
SLOT2: 16 + 128 + 1 = 145
```

## Resource usage

For 8 channels:

* 1 DSP48E1
* 2 RAMB36
* ~900 LUTs (1.4%)
* ~1500 FFs (1.3%)

## Timing

* > 200 MHz on Kasli (xc7a100t-2)

## Ideas

### Pipelining

* extract FTW0 during CMD, extract FTW1/POW during FTW0 shift, all during CONVH/CONV/SHIFT/LOAD phase to reach one sample latency at full bandwidth
* pipeline delay updates later (m_coeff to dlys[i] path)
* shift CMD at the end of the DDS cycle

### Resources

* move current dlys into m_state RAM (high bits of y1)

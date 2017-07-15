# IIR filter processor

[Design](https://github.com/m-labs/sinara/wiki/UrukulNovogornyServo)

## Code

### IIR processing core

* [iir.py](iir.py) Main processing core
* [iir_impl.py](iir_impl.py) Test implementation on Arty
* [iir_transfer.py](iir_transfer.py) Transfer function simulation tool
* [iir_sim.py](iir_sim.py) Verification and unittesting tool

### ADC interface

* [adc_ser.py](adc_ser.py) Multi-lane LVDS/CMOS ADC interface for LTC2320-16 or
  similar
* [adc_sim.py](adc_sim.py) ADC interface simulation and test bench
* [adc_impl.py](adc_impl.py) Test implementation on Arty

### Servo

* [servo_impl.py](servo_impl.py) Test implementation of the ADC-IIR-DDS chain
  on Arty

## IIR states

* idle: no activity
* shifting: x0 -> x1 value shifting in sate memory
* loading: loading adc values into x0
* processing: computing y0 and extracting ftw/pow from memory

# IIR pipeline

[Pipeline notes](pipeline.ods)

## Overall timing pipeline

```
in 8 ns cycles:
ADC: 30 ns CONVH: 4, 450 ns CONV: 57, 2*16*4 ns (125 MHz DDR LVDS) READ: 16
IIR: 16 SHIFT, 8 LOAD, 8*4+8+1=41 PROC
DDS: 8*16 ns CMD = 8, 64*16 ns PROF = 128, SPI WAIT = 1, IO_UPDATE = 2

ADC CONVH CONV READ
    4     57   16
IIR            SHIFT LOAD  PROC
               16    8     41
DDS                             CMD PROF WAIT IO_UP
                                8   128  1    2

SLOT1: 4 + 57 + 16 + 8 + 41 = 126
SLOT2: 8 + 128 + 1 + 2 = 139
```

## TODO

* DDS interface
* en_out/en_iir/dly setting/clearing
* profile selection
* RTIO/mgmt interface

## Ideas

### Pipelining

* extract FTW0 during CMD, extract FTW1/POW during FTW0 shift, all during CONVH/CONV/SHIFT/LOAD phase to reach one sample latency at full bandwidth

### Resources

* move current dlys into m_state RAM (high bits of y1)

### Timing

* pipeline shifting stage (RAMB-out to RAMB-in path)
* pipeline delay updates later (m_coeff to dlys[i] path)

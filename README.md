# IIR filter processor

[Design](https://github.com/m-labs/sinara/wiki/UrukulNovogornyServo)

## Code

* [iir.py](iir.py) Main processing core
* [iir_impl.py](iir_impl.py) Test implementation on Arty
* [iir_transfer.py](iir_transfer.py) Transfer function simulation tool
* [iir_sim.py](iir_sim.py) Verification and unittesting tool

## IIR states

* idle
* shifting
* loading
* processing

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

## Ideas

### Resources

* move dlys into m_state RAM (high bits of y1)

### Timing

* pipeline shifting stage (RAMB-out to RAMB-in path)
* pipeline delay updates later (m_coeff to dlys[i] path)

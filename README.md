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

# Processing pipeline

[Pipeline notes](pipeline.ods)

## Overall timing pipeline

```
ADC: 2*16*4 ns (250 MHz LVDS clock) READ
FIL: 16 SHIFT, 8 LOAD, 8*4+6 PROC
DDS: 8*16 ns CMD, 64*8 PROF

ns:

ADC CONVH CONV READ
    32    480  128
FIL            SHIFT LOAD  PROC
               128   64    352
DDS                         CMD PROF
                            128 1024
```

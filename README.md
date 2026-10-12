# Tang Nano 20K Ray Tracer

A real-time, Whitted-style ray tracer in FPGA logic for the Sipeed Tang Nano 20K
(Gowin GW2AR-18). It renders spheres, a checkerboard floor, shadows, reflections
and specular highlights, and outputs 640×480 over HDMI.

Status: planning. See [docs/PLAN.md](docs/PLAN.md) for the architecture, the
feature tiers with their LUT/DSP/BSRAM budget, and the milestones.

`model/feasibility.py` is a fixed-point model that checks the plan's number
formats and throughput against a float reference (needs Python 3, numpy and
Pillow):

```
python3 model/feasibility.py          # prints error, operand ranges, fps estimate
```

![Fixed-point render of the demo scene](docs/img/preview_rgb333.png)

# UART control protocol

The board's USB-C port carries a UART through the BL616 bridge: **115200 baud,
8N1**. Any serial terminal works for the single-key controls. For named
parameters in real units, use [`tools/rtctl.py`](../tools/rtctl.py).

## Single keys

Lower-case keys act immediately and send nothing back:

| Key | Action                               | Step              |
|-----|--------------------------------------|-------------------|
| `a` / `d` | camera yaw (orbit) left / right  | 2.8°              |
| `w` / `s` | camera higher / lower (pitch)    | 1.4°              |
| `z` / `x` | camera distance closer / farther | 0.25 units        |
| `j` / `l` | sun azimuth left / right         | 5.6°              |
| `i` / `k` | sun elevation up / down          | 2.8°              |
| `o`  | camera auto-orbit on / off            |                   |
| `p`  | sun auto-motion on / off              |                   |
| `f`  | freeze frame (stop rendering)         |                   |
| `t`  | test pattern (framebuffer bring-up)   |                   |
| `c`  | reset every register to its default   |                   |

The board buttons do the same as `o` (S1) and `p` (S2).

## Line commands

Upper-case commands end with CR or LF. Numbers are hex, and spaces between
fields are optional.

| Command        | Reply          | Meaning                          |
|----------------|----------------|----------------------------------|
| `W aa vvvv`    | `ok`           | write register `aa`              |
| `R aa`         | `aa=vvvv`      | read register `aa`               |
| anything else  | `?`            | malformed command                |

```
R 00        ->  00=5254
W 02 4000   ->  ok          (yaw = 90 degrees)
R 02        ->  02=4000
```

## Registers

All registers are 16 bits wide. Angles are fractions of a turn: `0x4000` is
90°, `0xC000` is −90°.

| Addr | Name          | Format                         | Default  | Notes |
|------|---------------|--------------------------------|----------|-------|
| 00   | id            | `0x5254` ("RT")                |          | read only |
| 01   | ctrl          | bit 0 orbit, 1 sun motion, 2 freeze, 3 test pattern | `0x0003` | |
| 02   | yaw           | angle                          | `0x0000` | camera orbit angle around the target |
| 03   | pitch         | angle, signed                  | `0x0700` | positive looks down from above (9.8°) |
| 04   | dist          | u4.12 world units              | `0x6000` | camera distance from the target (6.0) |
| 05   | target_x      | s3.12 world units              | `0x0000` | point the camera orbits and looks at |
| 06   | target_y      | s3.12                          | `0x0CCD` | 0.8 |
| 07   | target_z      | s3.12                          | `0x0000` | |
| 08   | fov           | tan(horizontal fov / 2), u1.15 | `0x49E7` | 60°; writes are clamped to `0x9999` (≈100°) |
| 09   | orbit_speed   | angle per frame, signed        | `0x0020` | added to yaw every rendered frame while orbit is on |
| 0A   | sun_az        | angle                          | `0x9000` | sun azimuth; 0 is towards +z, 0x4000 towards +x |
| 0B   | sun_el        | angle, signed                  | `0x0900` | sun elevation above the floor (12.7°) |
| 0C   | sun_speed     | angle per frame, signed        | `0x0010` | added to sun_az every rendered frame while sun motion is on |
| 0D   | sdram_rd_lat  | 1..7 cycles                    | `4`      | SDRAM read capture latency, for hardware bring-up |
| 0E   | frames        | count                          |          | read only: frames rendered |
| 0F   | status        | bit 0 SDRAM ready, bit 1 front buffer |   | read only |

The camera orbits `target` at distance `dist`: yaw 0 looks along −z. The sun
is a directional light. Auto-motion adds the speed registers once per
rendered frame (the display runs at 60 Hz, and rendering keeps up with it).

## Bring-up hints

- **No picture at all:** check that `led[1]` (SDRAM ready, the second LED) is on. Then press `t`
  for the test pattern: colour bars over a grey ramp, with a white border.
- **Test pattern garbled, smeared or shifted:** the SDRAM read latency is
  wrong for your board. Try `W 0D 0003` and `W 0D 0005`. 4 is the value the
  timing analysis and simulation give for the 54 MHz clock.

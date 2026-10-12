# UART control protocol

The board's USB-C port carries a UART through the BL616 bridge: **115200 baud,
8N1, no flow control**. It is `/dev/ttyUSB1` on Linux and a COM port on
Windows (`tools/rtctl.py list` shows them). Any serial terminal (PuTTY,
Tera Term, minicom, screen) works for the single-key controls. For named
parameters in real units, use [`tools/rtctl.py`](../tools/rtctl.py) on Linux,
macOS or Windows. Lines may end with CR, LF or CR LF.

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
| `m`  | sphere motion on / off                |                   |
| `v`  | 640×480 quality mode on / off         |                   |
| `b`  | reflection bounces: 0, 1, 2, 3, 0, …  |                   |
| `r`  | floor reflectivity: 0, ¼, ½, ¾, 0, …  |                   |
| `f`  | freeze frame (stop rendering)         |                   |
| `t`  | test pattern (framebuffer bring-up)   |                   |
| `c`  | reset every register to its default   |                   |

The board buttons: **S1** pauses all motion (camera orbit, sun, spheres), or
resumes all of it if everything is paused. **S2** switches the 640×480 quality
mode on and off, like `v`.

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
| 01   | ctrl          | bit 0 orbit, 1 sun motion, 2 freeze, 3 test pattern, 4 sphere motion, 5 quality mode (640×480) | `0x0013` | |
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
| 0F   | status        | bit 0 SDRAM ready, bit 1 shown frame is 640×480, bit 2 its two checkerboard halves are merged |   | read only |
| 10   | anim          | animation time                 | `0x0000` | sphere angles are `anim × k + phase` (see `SPHERES` in `scripts/gen_tables.py`) |
| 11   | anim_speed    | added per frame                | `0x0040` | added to anim every rendered frame while sphere motion is on |
| 12   | scene         | bits 1:0 bounces, 3:2 floor reflectivity (quarters), 6:4 spheres | `0x0061` | 1 bounce, matt floor, 6 spheres; more than 6 counts as 6 |
| 13   | cycles        | clock cycles per frame / 256   |          | read only: the last finished frame (54 MHz: 0x1284 ≈ 22 ms ≈ 44.5 fps for the default 640×480 view) |

The camera orbits `target` at distance `dist`: yaw 0 looks along −z. The sun
is a directional light. Auto-motion adds the speed registers once per
rendered frame. The display always runs at 60 Hz. In the 640×480 quality
mode each frame traces one checkerboard half of the pixels, and the display
fills the other half from the previous frame (or, after a change of mode,
from the neighbouring pixel). The default view takes about 22 ms per frame
(44.5 fps at 54 MHz); a higher sun is faster, a reflective floor slower
(`R 13` shows it). A 320×240 frame takes about half as long. A finished frame
is shown at the next vertical blank, so the picture never tears.

## Bring-up hints

- **No picture at all:** check that `led[1]` (SDRAM ready, the second LED) is on. Then press `t`
  for the test pattern: colour bars over a grey ramp, with a white border.
- **Test pattern garbled, smeared or shifted:** the SDRAM read latency is
  wrong for your board. Try `W 0D 0003` and `W 0D 0005`. 4 is the value the
  timing analysis and simulation give for the 54 MHz clock.

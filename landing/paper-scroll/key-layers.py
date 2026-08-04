#!/usr/bin/env python3
"""Key the flat cream background out of the generated parallax plates.

The imagegen plates are painted on one perfectly flat cream tone. This turns
that tone into alpha with a soft matte, so the layers can be stacked over each
other without a visible rectangular edge.

Soft matte rather than a hard threshold: the watercolour edges are stippled and
antialiased, and a binary key leaves them crunchy against the layer behind.

The plates are re-keyed from `*-src.webp` originals, so the script is safe to
run repeatedly — keying an already-keyed file would eat the soft edge.

Usage:  python3 landing/paper-scroll/key-layers.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parent / "assets"

# Plates that need keying. The sky plate is full-bleed and stays opaque.
PLATES = ("layer-far", "layer-mid", "layer-near", "layer-canopy")

# Mean per-channel distance from the key colour, in 0-255 terms.
# At or below INNER a pixel is fully transparent; at or above OUTER it is
# fully opaque; between the two the alpha ramps linearly.
INNER = 8.0
OUTER = 42.0


def key_plate(name: str) -> tuple[tuple[int, int, int], float]:
    """Key one plate, preserving an untouched `-src` original."""
    live = ASSETS / f"{name}.webp"
    src = ASSETS / f"{name}-src.webp"

    # First run: stash the generator's output so re-runs stay lossless.
    if not src.exists():
        src.write_bytes(live.read_bytes())

    im = Image.open(src).convert("RGBA")
    arr = np.asarray(im).astype(np.int16)
    rgb = arr[:, :, :3]

    # Key off the single most common colour rather than a corner pixel. The
    # flat background is 75-80% of every plate, so it always wins the vote —
    # and unlike a corner sample it survives the canopy plate, whose top-left
    # corner is leaves rather than cream.
    # int32 matters: a 16-bit shift overflows int16 and clips red to 255.
    wide = rgb.astype(np.int32)
    packed = (wide[:, :, 0] << 16) | (wide[:, :, 1] << 8) | wide[:, :, 2]
    values, counts = np.unique(packed.ravel(), return_counts=True)
    dominant = int(values[counts.argmax()])
    key = np.array([(dominant >> 16) & 255, (dominant >> 8) & 255, dominant & 255])

    dist = np.abs(rgb - key).mean(axis=2)
    alpha = np.clip((dist - INNER) / (OUTER - INNER), 0.0, 1.0)

    out = arr.copy()
    out[:, :, 3] = (alpha * 255).astype(np.int16)

    Image.fromarray(out.astype(np.uint8), "RGBA").save(live, "WEBP", quality=90, method=6)

    cleared = float((alpha == 0).mean() * 100)
    return tuple(int(c) for c in key), cleared


def main() -> None:
    for name in PLATES:
        if not (ASSETS / f"{name}.webp").exists():
            print(f"skip   {name}: not generated")
            continue
        key, pct = key_plate(name)
        print(f"keyed  {name}: key=rgb{key} cleared={pct:.1f}%")


if __name__ == "__main__":
    main()

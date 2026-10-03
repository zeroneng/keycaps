# Open Gorton Regular

Gorton-style keycap lettering based on Signature Plastics' Gorton Modified.

- Upstream: https://github.com/dakotafelder/open-gorton
- Source revision: `30094223a4f1e54e44ec3e2c39477f1b7e1006e4`
- License: MIT; see `LICENSE`. Commercial use is permitted. Keep the upstream
  copyright and license notice when redistributing the font or source.
- Source file: `OpenGorton-Regular.glyphs` (upstream's `Open Gorton.glyphs`).
- Built file: `OpenGorton-Regular.ttf` (TrueType outlines).
- Build tool: `fontmake 3.12.1`.

Rebuild with:

```sh
fontmake -g OpenGorton-Regular.glyphs -o ttf --output-path OpenGorton-Regular.ttf
```

The upstream design contains uppercase A–Z, digits, punctuation, and symbols,
but no lowercase a–z. The TTF was checked with fontTools and Pillow.

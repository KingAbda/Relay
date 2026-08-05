# Asset provenance

## Source painting

`assets/hero-paper-landscape.webp` and `assets/footer-paper-landscape.webp` were
copied byte-for-byte from:

`/Users/ramiel/Documents/projects/prompt-place/Promptplace/mock-websites/prompt-place-mock-v1/assets/`

That mock's README identifies them as user-generated original assets. They are
reused here at the owner's request. Prompt Place names, logos and copy are not
reused.

## Generated depth plates

`assets/layer-{sky,far,mid,near,canopy}.webp` are the five parallax plates the
hero travels through. They were generated with the Codex CLI `imagegen` skill,
passing `hero-paper-landscape.webp` as a **style reference only** so that all
five share its palette, wash and paper grain.

Each plate except the sky was painted on a flat cream field, which
`key-layers.py` keys out to alpha with a soft matte. The `*-src.webp` files are
the untouched generator output, kept so the key can be re-run with different
thresholds without regenerating the artwork.

Plates are WebP rather than PNG: WebP stores the alpha channel losslessly, so
the matte is bit-identical, while the colour channels compress roughly 6x —
about 1.3 MB total instead of about 9.8 MB.

## Logo

`assets/relay-logo-violet.svg` is generated from the canonical
`app/static/relay-logo.svg` by changing only its colour, from the brand violet
`#8a7ef2` to the iron-gall ink violet `#3b2f5c` this page uses.

## Fonts

`fonts/` holds Fraunces (display), Public Sans (body) and Oswald (FAQ headings).
The WOFF2 files are browser-optimized conversions of the corresponding TTF
sources in the same directory. All three are SIL Open Font License; see
`fonts/OFL.txt`.

# LuoShu v2.2 device font template engine

## Goal

Replace the old one-size-fits-all metric normalization with a per-device, per-slot template pipeline. The engine must preserve the ROM's real layout contract while substituting user glyphs.

## Stage 1: read-only device template capture

`common/device_font_template.sh` runs after Android finishes booting. It discovers system, OEM and updatable-font XML files across system, system_ext, product, vendor, odm, OEM, ColorOS and HyperOS partitions. The capture is asynchronous and never delays the native font index.

`common/device_font_template.py` records, for every declared slot:

- family name, weight, style, TTC index, axes and source XML;
- resolved physical file or dynamic PostScript name;
- role classification: global UI, dynamic, mono, clock, display, fallback or protected;
- original unitsPerEm, hhea, OS/2, Windows metrics, cap/x height and head bounds;
- rendered probe bounds and advance widths for Latin caps, lowercase, descenders, digits, CJK and punctuation.

Emoji, symbols, icons, math, music and language fallback slots remain protected.

The result is stored at `config/device-font-template.json`, keyed by the ROM fingerprint and font XML metadata. It is rebuilt only after a ROM/font configuration change.

## Following stages

1. Generate 100–900 static instances from the selected source.
2. Match each generated slot to the captured reference's UPEM, baseline, ink box, cap/x height, CJK box and advance-width contract.
3. Build separate UI, display, clock, mono and named-family payloads instead of reusing one binary for every alias.
4. Generate system, OEM and Android updatable-font XML views from the captured slot map.
5. Validate file structure, metric deltas and rendered pixel bounds before committing the payload.
6. Keep the previous working payload until a complete transaction succeeds; restore the ROM configuration on default/uninstall.

## Acceptance

A slot is not considered fixed because a file was copied. Acceptance requires:

- the runtime family map resolves to the generated slot;
- integer-pixel ascent/descent and line height match the stock reference at common Android text sizes;
- rendered probe strings stay within the stock control box;
- QQ input controls, labels, titles, system clocks, manager UI and Google named families pass device tests;
- Emoji, icons and complex-script fallbacks remain untouched.

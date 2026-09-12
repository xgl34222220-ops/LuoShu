# PR 217 Test5: QQ bitmap baseline correction

QQ 9.3.15's actual mention implementation draws text into a bitmap rather than
letting TextView draw a normal text run. Restoring all stock metrics alone keeps
the difference between the font's global bottom and its descent, so it cannot
remove the error introduced by this drawing formula.

## Evidence and scope

The [official QQ website](https://im.qq.com/index/) supplies this
[9.3.15 APK](https://downv6.qq.com/qqweb/QQ_1/android_apk/9.3.15_1e8e50a57667f3d4.apk).
The inspected APK SHA-256 is
`b23acbb08d9d15ac6df43251155d37fea523262e202d2f7784d20d51057077b7`.
Read-only inspection found `AIOAtSelectMemberUseCase` → `xl6/a.l` → `xl6/c`:

- The builder passes `EditText.getPaint()` directly to the span.
- Bitmap height is `ceil(fm.bottom - fm.top)`; the text baseline inside it is `-fm.top`.
- `draw` uses `DynamicDrawableSpan.ALIGN_BOTTOM`; `getSize` returns width without
  updating the supplied line metrics.

The resulting baseline is approximately `lineBottom - fm.bottom`, whereas normal
text uses the line baseline. For a line measured with that same Paint, the error
is approximately `fm.descent - fm.bottom`, plus pixel rounding. This agrees with
the documented [ALIGN_BOTTOM behavior](https://developer.android.com/reference/android/text/style/DynamicDrawableSpan#ALIGN_BOTTOM)
and [Paint metrics](https://developer.android.com/reference/android/graphics/Paint#getFontMetrics(android.graphics.Paint.FontMetrics)).
Mixed fallback fonts or custom line spacing can still contribute another error;
this is not a claim of complete QQ screen alignment on either device.

## Runtime change

Both actual legacy font-switch paths now apply the same restricted correction in
their HyperOS/ColorOS final staging pass. Known Latin UI slots with trustworthy
stock head/line metrics reduce excess bottom padding to the effective descent.
OS/2 USE_TYPO_METRICS selects typo descent; otherwise hhea descent is used.
The main OEM slot, CJK slots, clock, monospace and symbol slots retain their
existing behavior. Missing stock data, zero descent, variable sources or Latin
descenders that would be clipped retain their original bounds.

The correction changes only head.yMin. It preserves head.yMax, hhea/OS2, glyph
outlines, advances and the user's source files. The policy is part of the output
cache key, so an aligned Latin alias cannot leak into an otherwise identical CJK
or clock alias. All files are generated before any staged alias is replaced.
Reports identify the adjusted frame as `stock-line-descent`, not exact stock.

## Other reported screens

QQ's recommendation age label follows `PYMKItemView` → `TroopLabelLayout` →
`TroopLabelTextView`. Digits and 岁 are ordinary text in the same SpannableString;
only the gender icon is an ImageSpan. The view centers text with
includeFontPadding=false. It is not the mention bitmap mechanism and is not
claimed fixed by the head-bottom change.

The [official Coolapk](https://www.coolapk.com/) 16.6.1 APK contains
`event_node_toolbar_content` and `product_node_toolbar_content` with a fixed 52dp
height, a 16sp title 8dp from the top and a 12sp subtitle 10dp from the bottom.
Both disable font padding, and neither avoids the other's bounds. This can
produce overlap as font scale grows. Runtime binding and the selected Typeface
were not confirmed in the packed APK; changing a global glyph offset would not
be an evidence-based repair of this layout.

The [official Xiaomi MiSans download](https://hyperos.mi.com/font/zh/download)
provides MiSans 4.009 VF, whose vertical metrics exactly match the reported stock
contract. Its SHA-256 is
`0ddef90648998900175cfdca9a6f087a2544c182f130b0ad4f7e94a03a115e79`.
Official 岁 spans -75..847 (center 0.386em), versus the reported donor's
-111..822 (center 0.3555em). The donor is already lower, not globally raised.
Even the official font can collide in the fixed toolbar at increased font scale
under the same assumed MiSans line metrics; this is not evidence for a blanket
downward translation or reduction of every glyph.

The previously inspected Xiaomi stopwatch loads an APK asset font independently
of system font aliases; this module update does not replace that asset. Remote
control clipping and Google-app coverage are not claimed newly resolved here.

## Verification and installation

Host tests exercise actual FreeType TTF/CFF loading and rasterization, the QQ
bitmap formula, mixed units-per-em, typo selection, preserved raw outline/line
metric tables, clipping guards, cache isolation and repeated processing. These
checks validate the mechanism, not Android device rendering.

Test5 reuses the unchanged Test4 App APK, preserving its signing certificate.
Install the module, reboot, reapply the current font/composite and reboot as
prompted. Keep “默认卸载模块” disabled. Recheck the QQ reply input and the previously
working status-bar clock; further logs are not required for this test.

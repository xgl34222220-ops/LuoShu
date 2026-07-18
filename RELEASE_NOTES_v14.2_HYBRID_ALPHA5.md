# LuoShu v14.2 Hybrid App Alpha5

- Correct font capability UI: only a real `wght` axis uses a continuous slider, static families use real discrete weights, and single fonts stay fixed.
- Add native cached font preview export for Compose cards and composition slots.
- Rebuild the native UI with a MIUIx-inspired layered glass design, gradient lighting, large rounded panels and a floating navigation dock.
- Keep native lazy loading and native composite-font tasks; no WebView in the core app.

## Integrated package refresh

- Align the module and App version with v14.2 Alpha5.
- Build a directly installable APK and an integrated module ZIP from the same workflow.
- Bundle the App inside the complete module package, with best-effort install during flashing and an action-button retry after reboot.
- Move preview file loading off the UI thread and cap preview cache growth at six files / roughly 96 MiB.

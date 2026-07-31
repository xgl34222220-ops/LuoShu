# Reference-video UI rebuild review

This branch intentionally replaces the oversized dashboard-style refactor with a compact interface matching the supplied reference video.

Acceptance points:

- Every top action uses the same shared 48 dp button and 16 dp radius.
- Page titles, grouped cards, rows and vertical spacing use compact proportions.
- The home status orb and settings decorative gear are removed.
- Font-library tools use neutral grouped surfaces instead of colored dashboard tiles.
- Studio utility and refresh actions use the exact same component.
- The floating dock is thinner, lighter and leaves content clearance.
- Kotlin compile repairs are included and the full Android validation is rerun from a repository-owner commit.
- This branch must remain unmerged until a real-device screenshot is reviewed.

## 2026-06-11 - Add ARIA Labels to Icon-Only Buttons in Data Tables
**Learning:** Found a common pattern of using icon-only buttons for actions like Edit/Delete/Test in data tables (e.g., MCPServersPage.tsx) without `aria-label` or `title` attributes. This makes them inaccessible to screen readers and unintuitive without hover descriptions.
**Action:** Always ensure icon-only buttons have descriptive `aria-label`s for accessibility and `title`s for native tooltips when custom tooltip components aren't used.
## 2024-06-12 - Missing Accessible Labels on Icon-Only Buttons
**Learning:** In component iterations, icon-only buttons (like edit pencils, delete trash cans) are frequently added without proper accessibility labels. `aria-label` provides necessary context for screen readers, while the `title` attribute acts as a native tooltip, aiding mouse users and those with cognitive disabilities who might not immediately recognize an icon's meaning.
**Action:** When adding or reviewing icon-only buttons, systematically ensure both `aria-label` and `title` attributes are present.

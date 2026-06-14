## 2026-06-11 - Add ARIA Labels to Icon-Only Buttons in Data Tables
**Learning:** Found a common pattern of using icon-only buttons for actions like Edit/Delete/Test in data tables (e.g., MCPServersPage.tsx) without `aria-label` or `title` attributes. This makes them inaccessible to screen readers and unintuitive without hover descriptions.
**Action:** Always ensure icon-only buttons have descriptive `aria-label`s for accessibility and `title`s for native tooltips when custom tooltip components aren't used.
## 2024-06-14 - Icon-Only Button Accessibility Pattern
**Learning:** Found a widespread pattern across the application where icon-only buttons (like modal close buttons `<X />`, edit buttons `<Pencil />`, and upload buttons `<Upload />`) lack accessible names (`aria-label`) and visual tooltips (`title`). This severely impacts screen reader users and reduces clarity for all users.
**Action:** When adding or reviewing icon-only buttons in the UI, always ensure they include an `aria-label` for screen readers and a `title` attribute for native hover tooltips.

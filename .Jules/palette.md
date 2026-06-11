## 2026-06-11 - Add ARIA Labels to Icon-Only Buttons in Data Tables
**Learning:** Found a common pattern of using icon-only buttons for actions like Edit/Delete/Test in data tables (e.g., MCPServersPage.tsx) without `aria-label` or `title` attributes. This makes them inaccessible to screen readers and unintuitive without hover descriptions.
**Action:** Always ensure icon-only buttons have descriptive `aria-label`s for accessibility and `title`s for native tooltips when custom tooltip components aren't used.

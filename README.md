ELITE X Public Member Portal

A mobile-first, display-only Bond Account portal designed for GitHub Pages.

Architecture

Private ELITE X Staff Records (source of truth)
â†’ sanitized `data.json`
â†’ GitHub Pages
â†’ public member portal

The portal does not calculate or edit the master Bond records.

Deploy to GitHub Pages
1. Create a GitHub repository.
2. Upload `index.html`, `style.css`, `script.js`, `data.json`, and the `assets/` folder.
3. In GitHub, open **Settings â†’ Pages**.
4. Select **Deploy from a branch**, choose the repository's main branch and `/ (root)`.
5. GitHub will provide the public Pages URL.

The URL is publicly accessible to anyone who has it.

Updating the portal
• The recommended workflow is to regenerate `data.json` from the private Excel master record, review the sanitized output, then commit the new `data.json` to the portal repository.
• A public static page cannot securely read a private Excel file directly. Do not put the private Excel workbook, staff notes, credentials, API keys, or private spreadsheet links in this repository.

Privacy limitation
• This is a public, ID-lookup display. A Member ID is an identifier, not authentication. Anyone who can access the public data source may potentially inspect its contents. Only put information into `data.json` that ELITE X is comfortable making public.

Activity-history limitation
• The current Staff Records Activity Log contains activity name/date/type/week/entry/Bonds but no Member ID. Because of that, the portal cannot safely attribute those detailed activity-log rows to individual members.
• The portal therefore displays the member's Bond entries from the member Bond Record. To support full member-specific Activity History (activity name, date, type, week, entry, Bonds), the approved source needs a Member ID field on those activity records or another authoritative mapping.

Currency
Use **BONDS ðŸ’´** only.

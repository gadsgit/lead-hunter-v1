# Lead Hunter Project Rules

## Core Directives
1. **Aggressive RAM Management:** Render has a 512MB limit. Avoid Pandas. Use `json` and `csv` modules. Clear large variables after use.
2. **One-by-One Processing:** Never batch leads. Process 1 lead, score it, save it, then move to the next.
3. **Aggressive Resource Blocking:** Block images, fonts, and stylesheets in Playwright.
4. **Resilience:** Handle Google Maps consent screens and "Robot Check" pages gracefully.
5. **No Placeholders:** Use real logic for email extraction and social media discovery.
6. **No Pandas:** The system must run on standard libraries + `gspread` + `playwright`.

### STEALTH SKILL
1. **Never** use a hardcoded User-Agent. Always rotate from a list of 5+ real browser strings.
2. **Always** apply `stealth_async(page)` before any `goto` command.
3. **Randomize** the Viewport size slightly (e.g., 1280x720 +/- 50px).
4. **Jitter:** Add a random sleep of 3-7 seconds between searching Google and clicking a LinkedIn link.

### SUMMARY CHECKLIST
- **Workbooks:** Create a new tab named `LinkedIn Leads`.
- **Logic:** Never save a lead to GSheets until the AI has returned a score.
- **Keywords:** Always make `Keyword` the first column in both tabs.
- **Checkpoints:** GSheets "Mission_Progress" tab is the source of truth for history.
- **Goal:** Never re-scrape a lead that exists in GSheets.

### ONE-CLICK DORK SCRAPER SKILL
- **Logic:** Streamlit Sidebar → Dork Generator → Background Playwright Task → GSheets Router.
- **Safety:** Rotate User-Agents for every Launch button click.
- **Workflow:** Scouts with sidebar (real IP) → Deploys bot (Rotation/Proxy/Stealth) for extraction.

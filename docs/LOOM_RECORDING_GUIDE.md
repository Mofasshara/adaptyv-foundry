# How to record the Loom demo — click by click

This is the operational companion to `docs/LOOM_SCRIPT.md` (the narration/content script). This one tells you exactly what to click, in order. Do Part A once, then Part B is the actual recording.

---

## Part A — One-time setup (do this before recording, not during)

### A1. Confirm the MCP server is built

```bash
cd /Users/naloo/Programming/adaptyv-foundry/mcp
npm run build
```

You should see it exit with no errors and `dist/index.js` should exist. (It's already built as of this writing — this just re-confirms it.)

### A2. Point Claude Desktop at the MCP server

1. Open the **Claude** desktop app.
2. Click the **Claude** menu in the top-left of your screen (next to the Apple logo) → **Settings…**
3. Click the **Developer** tab on the left.
4. Click **Edit Config**. This opens `claude_desktop_config.json` in your default text editor (or reveals it in Finder — if it opens Finder instead of a text editor, right-click the file → **Open With** → **TextEdit**).
5. The file already has some content in it (unrelated app preferences) — **do not delete what's there.** Add an `mcpServers` key. If the file currently looks like:
   ```json
   {
     "coworkUserFilesPath": "...",
     "preferences": { ... }
   }
   ```
   change it to:
   ```json
   {
     "coworkUserFilesPath": "...",
     "preferences": { ... },
     "mcpServers": {
       "adaptyv-foundry": {
         "command": "node",
         "args": ["/Users/naloo/Programming/adaptyv-foundry/mcp/dist/index.js"]
       }
     }
   }
   ```
   (Keep everything that was already in the file — you're only adding the `mcpServers` block as a new top-level key, with a comma after the line before it.)
6. Save the file (**Cmd+S**), close the editor.
7. **Fully quit** Claude Desktop — click the **Claude** menu → **Quit Claude** (or **Cmd+Q**). Just closing the window is not enough; MCP servers are only loaded at launch.
8. Re-open Claude Desktop.

### A3. Verify the tools actually show up

1. In Claude Desktop, start a new chat.
2. Look for a small tools/plug icon near the message input box (bottom of the chat window) — click it.
3. You should see **adaptyv-foundry** listed with its 8 tools (`list_experiments`, `get_experiment_status`, `create_experiment_with_sequences`, `add_sequences`, `search_targets`, `get_results`, `estimate_cost`, `draft_customer_update`). If you don't see it, re-check step A2's JSON is valid (a missing comma is the most common mistake) and that you fully quit and relaunched.

### A4. Get a Loom account/app ready

- If you don't already have Loom: go to loom.com, sign up (free plan is fine), and install the **Loom desktop app** (recommended — simpler than the browser extension for recording a whole window/screen) or the Chrome extension if you'd rather record from the browser.
- Open the Loom app once now and sign in, so you're not doing that live while recording.

### A5. Arrange your windows

- Put **Terminal** and **Claude Desktop** side by side (or on two spaces you can switch between with a keyboard shortcut) — you'll be switching between them per the script's beats.
- In Terminal, `cd` into the repo and activate the venv now, so it's already done before you hit record:
  ```bash
  cd /Users/naloo/Programming/adaptyv-foundry
  . .venv/bin/activate
  rm -f adaptyv_governance.db
  ```
- Make your terminal font size large enough to read on a recording (Terminal menu → **Font** → **Bigger**, a couple of times, or Cmd++).

---

## Part B — Recording

### B1. Start Loom

**If using the Loom desktop app:**
1. Click the Loom icon in your Mac's menu bar (top-right, near the clock).
2. Click **New Recording** (or click the Loom dock icon if it's open).
3. A small control bar appears. Choose **Screen and Cam** (shows your face in a bubble — optional, fine to skip) or **Screen Only**.
4. Click **Full Desktop** if it asks which screen/window, so you can freely switch between Terminal and Claude Desktop during the recording (recording a single fixed window would prevent switching).
5. Click the microphone icon in that same control bar to make sure your mic is selected and unmuted.

**If using the Chrome extension instead:**
1. Click the Loom icon in your Chrome toolbar.
2. Choose **Screen + Cam** or **Screen Only**.
3. Choose **Full Desktop** (not just the browser tab) so you can show Terminal too.

### B2. Do a 3-second countdown, then start talking

1. Click the big **Start Recording** button.
2. Loom gives you a 3-2-1 countdown — use that pause to make sure you're looking at the right window.
3. Begin narrating **Beat 1** from `docs/LOOM_SCRIPT.md` immediately after the countdown ends.

### B3. Follow the script

Work straight through `docs/LOOM_SCRIPT.md`'s Beats 1–5, in order:
- **Beat 1**: just talk, no window switch needed yet.
- **Beat 2**: click into the **Claude Desktop** window, type the two example prompts into the chat box exactly as written in the script, press Enter, wait for each response, narrate over it.
- **Beat 3**: click into **Terminal**, type each command shown in the script one at a time, pressing Enter after each and pausing briefly for the output before typing the next. When the script says `<draft_id>`, don't type that literally — copy the real ID from the `adaptyv review list` output just above it in your terminal (select it with your mouse, Cmd+C, then Cmd+V into the next command).
- **Beat 4**: still in Terminal, same pattern.
- **Beat 5**: just talk, no more commands.

### B4. Stop recording

**Desktop app:** click the Loom menu-bar icon again → **Stop Recording** (or use the stop button in the small floating control bar).
**Chrome extension:** click the extension icon → **Stop Recording**.

Loom will automatically open a browser tab with your recording processing, then playing back.

### B5. Get the shareable link

1. Once the recording finishes processing, Loom shows a **Share** button (top-right of the video page) — click it.
2. Make sure the visibility toggle is set to **"Anyone with the link can view"** (this is usually the default for a free account).
3. Click **Copy link** (or **Copy to clipboard**) — that's your Loom URL, ready to paste wherever you're sending this (email, application form, etc.).

### B6. Optional — trim it

If you fumbled a command or paused too long somewhere: on the video page, click **Edit** (or the scissors icon) → drag the trim handles on the timeline → **Save**. You don't need to re-record from scratch for a small stumble.

---

## If something doesn't match what you see

- Loom's exact button labels/icons shift slightly between app versions — if a button isn't exactly where described, look for the nearest equivalent (a record button, a stop button, a share button — the concepts are stable even if pixel position isn't).
- If Claude Desktop's Settings menu looks different from what's described in A2 (Anthropic does update the app), search Claude Desktop's Help/Settings for "Developer" or "MCP" — that's the section you need.

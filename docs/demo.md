# Demonstrating CodeBase Time Machine

Use a small public repository with several commits and, ideally, public pull requests and issues.
Before the demo, run these commands in separate PowerShell terminals:

```powershell
cd 'D:\swe project\backend'; npm run dev
cd 'D:\swe project\frontend'; npm run dev
cd 'D:\swe project'; .\scripts\demo-check.ps1
```

Open `http://127.0.0.1:3000`, submit the public GitHub URL, and wait for the repository job to
finish. The Overview panel reports each optional index independently. Build GitHub, graph, AI,
archaeology, and architecture-history indexes from their respective pages when needed.

Suggested walkthrough: open commits, browse a function in Code, view its historical timeline,
open related GitHub context, inspect Architecture and impact, ask why the selected code exists,
open an archaeology dossier, compare architecture snapshots, then paste a stack trace into
Investigate.

If GitHub is rate-limited, use already indexed Git/code/history features and explain that GitHub
context is an optional public API enrichment. If Ollama is unavailable, use the deterministic
views; no repository data needs to leave the machine.

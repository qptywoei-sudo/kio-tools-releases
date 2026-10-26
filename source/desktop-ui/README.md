# GalaxyControl standalone UI

Independent desktop frontend 4.2.2. No ADMIN Auth, Supabase, MCP or deployed ADMIN site is required.

```sh
npm ci
npm run build
```

The native Mac/Windows host serves `dist/` under its owned loopback `/tools/` origin and injects its private session. Output can be changed with `GALAXY_TOOLS_UI_OUT_DIR`. No ADMIN project directory or environment file is used.

All file engines, browser-capture extension, shortcuts, recording and phone controls remain in the existing native host/agent. Only its own origin and consented browser capture extensions can use the tool API. Old remote pairings are preserved but cannot access the program.

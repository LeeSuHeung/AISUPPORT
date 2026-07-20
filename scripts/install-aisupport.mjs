#!/usr/bin/env node

// Canonical entry point. Keep install-caveman.mjs as the implementation so
// existing automation and bookmarks continue to work.
await import("./install-caveman.mjs");

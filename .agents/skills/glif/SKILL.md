---
name: glif
description: Use only when the user explicitly invokes $glif or says Glif, Glyphs, or 글리프 for image, video, or audio generation and refinement through the Glif MCP server.
---

# Glif media workflow

Use Glif as a project-first media agent. Let Glif choose its internal models,
tools, and multi-step workflow unless the user explicitly requests a model.
Do not treat Glif as a raw model registry.

## Preconditions

- Require the `glif` MCP server at `https://glif.app/api/mcp`.
- If its tools are unavailable, tell the user to rerun the AISUPPORT installer,
  restart Codex, and authenticate Glif. Do not silently substitute another
  generator when the user explicitly requested Glif.
- Use `whoami` for connection, plan, balance, or recent-spend checks. Never run
  `compose_project` for a connection check.

## Prepare the request

- Answer planning, prompt-writing, and style-advice requests without generating
  media until the user asks to generate.
- Default to one output when the user does not specify a count. This limits
  accidental credit use.
- Include purpose, subject, style, composition, output type, constraints, and
  requested dimensions in the natural-language brief when known.
- For reference media, call `upload_file` first and include its returned media
  URL as an attachment or reference in `compose_project`.

## Generate and continue projects

1. Call `compose_project` without `project_id` for a new concept. Pass
   `output_preference` as `image`, `video`, or `audio` when the desired type is
   clear.
2. Preserve the returned `jobId` and `projectId`.
3. Poll `get_job_status` with the returned job ID. Honor each returned
   `pollIntervalSeconds`; continue until `completed` or `failed`.
4. After completion, call `view_media` once with the project ID. Do not call it
   during `working` polls.
5. Report a failed job with Glif's error. Never claim success from a `working`
   result.
6. For revisions, call `compose_project` with the existing `project_id`. Start
   a new project only for an independent concept or when the user requests one.
7. Use `get_project` to recover project history or media after job-status data
   expires. Use `list_projects` only when the user asks to find prior work.

Generation commonly takes several minutes. Keep the user updated during a long
run and continue polling when they asked for a finished result.

## Personal Glif skills

- Use `list_user_skills` and `get_user_skill` only for the authenticated user's
  personal Glif skills.
- Do not claim access to global Glif skills; the public MCP server does not
  expose them.
- When the user names a personal skill, read it first, then incorporate its
  instructions into the Glif project brief.

## Safety and cost

- Glif is an external service and can consume separate Glif credits. Do not
  create extra variants, videos, or audio beyond the requested count.
- Never place OAuth credentials or `glif_v1_...` API tokens in prompts,
  repository files, or generated assets.
- Upload private or confidential media only when the user explicitly places it
  in scope for Glif processing.

# JAV.bundle Changelog

Changes in this fork since the original master, grouped by date (newest first).

## 2026-07-23
- Add `AVBase` agent (avbase.net) as a metadata source.
- Add a Duga full-description backfill: when a summary is a truncated teaser, replace it with the complete synopsis from the matching Duga product.
- Add `BUENA` amateur agent.
- Add `Translate` agent (Ollama) that translates Japanese metadata to English, with a guard that discards malformed or untranslated model output instead of storing it.
- Add a romaji reading-to-romaji romanization helper.
- Add a per-agent geo proxy (`geo_proxy` preference) used only by the geo-blocked `DMM` and `MGStage` agents, so other sources stay direct.
- Route `DMM` and `MGStage` through the geo proxy for full descriptions, and let their full summary replace a shorter one from another source.
- Skip trailer resolution for geo-restricted sources to avoid spending proxy traffic on sample videos that cannot be played anyway.
- Prefer a native portrait cover for posters (e.g. the DMM `jp-1` front cover); crop a wide landscape cover only when no portrait exists.
- Pool cover and poster images across all contributing agents instead of only the highest-weight one.
- Add `duga_enabled` and `geo_proxy` preferences.
- Bundle Pillow for front-cover cropping.
- Enhance avatar agents.

## 2026-03-23
- Handle access issues and enhance avatar agents.

## 2026-03-19
- Refactor metadata ID handling and improve poster fetching.

## 2026-03-16
- Add force update preference.

# PlayStation Network integration research

Date: 2026-10-25

## Conclusion

The Playnite PSN extension does not use a documented public Sony library API. It calls private PlayStation web/mobile endpoints observed in the extension source. A Backlogia integration would therefore depend on reverse-engineered behavior that may change or be rate-limited.

## Current Playnite authentication flow

The Playnite 11 implementation uses this sequence:

1. The user supplies an NPSSO cookie value, either raw or wrapped as `{"npsso":"..."}`.
2. The NPSSO value is sent to Sony's mobile OAuth authorization endpoint.
3. Sony returns a custom-scheme redirect containing an authorization code.
4. The code is exchanged at Sony's OAuth token endpoint with the embedded PlayStation mobile-app client credentials.
5. The resulting bearer access token is used for PlayStation web/mobile requests.
6. The refresh token is encrypted and cached locally with Windows DPAPI, then redeemed on later runs while valid.
7. If refresh fails or expires, the NPSSO authentication flow is attempted again.

The stable extension stores PlayStation cookies encrypted with Windows DPAPI and migrates an older `token.json` cookie store. The PlayStation 11 branch stores NPSSO and refresh-token material using `DataProtectionScope.CurrentUser`.

## Imported data

The extension imports multiple data sets independently:

- Purchased PS4/PS5 titles.
- Recently played titles.
- Mobile play history.
- Trophy titles.

Legacy PS3, PSP, and Vita titles are obtained through trophy lists. The PlayStation 11 branch optionally imports trophy-only games. It intentionally does not classify `PSPC` as PC because Sony trophy sets can be shared between PC and PS5.

The extension merges duplicate game IDs and updates last-played time, playtime, and play count. It can optionally apply PlayStation Plus source/tag information.

## Relevant primary sources

- [Playnite PSN extension repository](https://github.com/XenorPLxx/playnite-library-psn) — MIT-licensed source repository.
- [Stable manifest](https://raw.githubusercontent.com/XenorPLxx/playnite-library-psn/main/manifest.yaml) — package `2.38`, Playnite API `6.12.0`, dated 2026-08-15.
- [Release 2.38](https://github.com/XenorPLxx/playnite-library-psn/releases/tag/2.38) — NPSSO authentication and saved-session changes; accepts raw NPSSO or complete `ssocookie` JSON.
- [Release 3.0](https://github.com/XenorPLxx/playnite-library-psn/releases/tag/3.0) — prerelease Playnite 11 build; replaces browser sign-in with mobile authorization and adds encrypted NPSSO/refresh-token storage, achievements, playtime, and optional trophy-only imports.
- [Playnite 11 branch](https://github.com/XenorPLxx/playnite-library-psn/tree/playnite-11) — current refactored implementation.
- [`PSNClient.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/main/Services/PSNClient.cs) — stable endpoints, NPSSO handling, cookie persistence, token exchange, library/history/trophy requests.
- [`PSNLibrary.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/main/PSNLibrary.cs) — authentication and the four import paths.
- [`ParserGames.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/main/Services/ParserGames.cs) — Sony response parsing.
- [`ParserPlatform.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/main/Services/ParserPlatform.cs) — PSP, Vita, PS3, PS4, and PS5 mapping.
- [`SyncGames.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/main/Services/SyncGames.cs) — duplicate merging and playtime/play-history updates.
- [`PlayStationAccountClient.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/playnite-11/PlayStationAccountClient.cs) — PlayStation 11 OAuth, bearer session, endpoint constants, and token persistence.
- [`PlayStationLibrary.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/playnite-11/PlayStationLibrary.cs) — PlayStation 11 import orchestration and platform handling.
- [`PlayStationLibrarySettings.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/playnite-11/PlayStationLibrarySettings.cs) — NPSSO, platform filters, and trophy-only settings.
- [`PlayStationSecrets.cs`](https://github.com/XenorPLxx/playnite-library-psn/blob/playnite-11/PlayStationSecrets.cs) — Windows DPAPI protection implementation.
- [Sony PlayStation Terms of Service](https://www.playstation.com/en-us/legal/psn-terms-of-service/) — applicable service and account-use terms.

## Backlogia implications

- Backlogia is a SQLite/web application with provider adapters in `web/sources/*.py`, provider upserts in `web/services/database_builder.py`, dispatch in `web/routes/sync.py`, and provider settings in `web/templates/settings.html`.
- Existing Backlogia provider credentials are plaintext in the SQLite settings table unless supplied by environment variables. Windows DPAPI cannot be reused for Docker or non-Windows deployments.
- A PSN adapter should keep NPSSO, access tokens, and refresh tokens out of logs, API responses, HTML, job messages, and exception text.
- Sony endpoint behavior, authentication requirements, rate limits, and terms must be treated as unstable external dependencies. The implementation should expose re-authentication and actionable failure states rather than silently retrying indefinitely.
- Sony title IDs, platform, region, entitlement/source type, PlayStation Store URLs, and play-history fields should remain distinct from the user-facing game name. `store="psn"` with a canonical Sony ID is compatible with Backlogia's existing `UNIQUE(store, store_id)` model.

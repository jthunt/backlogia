# ea.py
# Fetches owned games from EA using bearer token authentication
# Based on: https://github.com/Jeshibu/PlayniteExtensions
# User obtains bearer token via JavaScript snippet in browser console

import json
import requests

from ..services.settings import get_ea_credentials

# EA API endpoints
GRAPHQL_ENDPOINT = "https://service-aggregation-layer.juno.ea.com/graphql"
# Updated request documented in Dr4w/backlogia commit 3c4608f (upstream issue #95).
QUERY_HASH = "779f1cd1355699752e20c0b3877847f4e3010ef5de131c248e98f8eff84f0718"
OWNERSHIP_METHODS = [
    "UNKNOWN", "ASSOCIATION", "PURCHASE", "REDEMPTION", "GIFT_RECEIPT",
    "ENTITLEMENT_GRANT", "DIRECT_ENTITLEMENT", "PRE_ORDER_PURCHASE",
    "VAULT", "XGP_VAULT",
]

# Required headers for API requests
REQUIRED_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def get_bearer_token():
    """Get stored bearer token from settings."""
    creds = get_ea_credentials()
    token = creds.get("bearer_token")

    if token:
        # Strip "Bearer " prefix if user accidentally included it
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

    return token if token else None


def get_owned_games(token):
    """Query GraphQL endpoint for owned games using Jeshibu's persisted query approach."""
    try:
        session = requests.Session()
        headers = {
            **REQUIRED_HEADERS,
            "Authorization": f"Bearer {token}",
        }

        all_games = []
        next_offset = "0"
        limit = 500
        seen_offsets = set()

        while True:
            seen_offsets.add(next_offset)
            variables = {
                "isMac": False,
                "addFieldsToPreloadGames": True,
                "locale": "en",
                "next": next_offset,
                "limit": limit,
                "type": ["DIGITAL_FULL_GAME", "PACKAGED_FULL_GAME"],
                "entitlementEnabled": True,
                "storefronts": ["EA"],
                "ownershipMethods": OWNERSHIP_METHODS,
                "platforms": ["PC"]
            }

            # Use persisted query extension
            payload = {
                "operationName": "getPreloadedOwnedGames",
                "variables": json.dumps(variables),
                "extensions": json.dumps({
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": QUERY_HASH
                    }
                })
            }

            response = session.get(
                GRAPHQL_ENDPOINT,
                headers=headers,
                params=payload,
                timeout=30
            )

            print(f"  GraphQL response status: {response.status_code}")

            if response.status_code in (401, 403):
                raise RuntimeError("EA authentication failed; refresh your bearer token.")

            try:
                data = response.json()
            except ValueError:
                raise RuntimeError(
                    f"EA returned a non-JSON response (HTTP {response.status_code})."
                ) from None

            errors = data.get("errors") or []
            if any(error.get("message") == "PersistedQueryNotFound" for error in errors):
                raise RuntimeError(
                    "EA API error: PersistedQueryNotFound. EA no longer recognizes "
                    "the library query; the integration needs an update. "
                    "Refreshing the bearer token does not resolve this query error."
                )
            if response.status_code != 200 or errors:
                raise RuntimeError(
                    f"EA library query failed (HTTP {response.status_code})."
                )

            # Navigate the response structure
            me = (data.get("data") or {}).get("me") or {}
            preloaded = me.get("ownedGameProducts") or me.get("preloadedOwnedGames")
            if not isinstance(preloaded, dict) or "items" not in preloaded:
                raise RuntimeError("EA library response is missing owned game products.")
            items = preloaded.get("items") or []

            print(f"  Got {len(items)} items")

            if not items:
                break

            for item in items:
                # Parse based on actual EA response structure:
                # item.originOfferId, item.product.name, item.product.gameSlug, etc.
                product = item.get("product") or {}
                base_item = product.get("baseItem") or {}

                # Get name from product or baseItem
                name = product.get("name") or base_item.get("title")
                if not name:
                    continue

                # Get offer ID
                offer_id = item.get("originOfferId") or item.get("id")

                # Get game slug for potential cover image URL
                game_slug = product.get("gameSlug") or base_item.get("baseGameSlug")

                # Build cover image URL from game slug if available
                # EA uses URLs like: https://media.contentapi.ea.com/content/dam/ea/...
                cover_image = None
                if game_slug:
                    # Try common EA image URL patterns
                    cover_image = f"https://media.contentapi.ea.com/content/dam/eacom/en-us/common/games/{game_slug}/packart.jpg"

                # Get release date from lifecycle status
                release_date = None
                lifecycle = product.get("lifecycleStatus") or []
                if lifecycle:
                    release_date = lifecycle[0].get("playableStartDate")

                # Get game type
                game_type = base_item.get("gameType")

                all_games.append({
                    "offer_id": str(offer_id) if offer_id else None,
                    "name": name,
                    "cover_image": cover_image,
                    "offer_type": game_type,
                    "release_date": release_date,
                    "game_slug": game_slug,
                    "raw_data": item,
                })

            # Check for pagination
            next_offset = preloaded.get("next")
            if not next_offset or next_offset in seen_offsets:
                break

        return all_games

    except RuntimeError:
        raise
    except Exception:
        # Request exceptions may contain URLs or headers with credentials.
        raise RuntimeError("Unable to fetch EA library; check connectivity and retry.") from None


def get_ea_library():
    """Fetch all games from EA library."""
    token = get_bearer_token()
    if not token:
        print("Error: EA bearer token not configured")
        print("\nTo set up EA, use the JavaScript snippet in Settings to get your token")
        return None

    print("Fetching EA library...")

    games = get_owned_games(token)
    print(f"  Found {len(games)} EA games")

    # Deduplicate by offer_id
    seen_ids = set()
    unique_games = []
    for game in games:
        offer_id = game.get("offer_id")
        if offer_id and offer_id in seen_ids:
            continue
        if offer_id:
            seen_ids.add(offer_id)
        unique_games.append(game)

    return unique_games


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Import EA library")
    parser.add_argument("--token", type=str, help="EA bearer token (for testing)")
    parser.add_argument("--export", type=str, help="Export to JSON file instead of database")
    args = parser.parse_args()

    print("EA Library Import")
    print("=" * 60)

    if args.token:
        # Use provided token for testing
        print("Using provided token...")
        games = get_owned_games(args.token)
    else:
        games = get_ea_library()

    if not games:
        print("Failed to fetch EA library")
        return

    print(f"\nFound {len(games)} unique games")

    if args.export:
        with open(args.export, "w") as f:
            json.dump(games, f, indent=2)
        print(f"Exported to {args.export}")
    else:
        for game in games[:10]:
            print(f"  - {game['name']}")
        if len(games) > 10:
            print(f"  ... and {len(games) - 10} more")


if __name__ == "__main__":
    main()

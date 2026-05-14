"""Find the closest Fred Beans Ford dealership to a given address/town/ZIP.

Two free, key-free public APIs do the work:
  * Nominatim (OpenStreetMap) converts the user's input into lat/lng. It
    handles bare ZIPs, "City, State", and full street addresses — the Census
    Geocoder only accepts full street addresses, which is why we don't use it.
  * OSRM public router gives real driving distance + time to each store.

If OSRM is unreachable we still rank the stores using a haversine fallback,
flagged in the response so the template can show the user it's an estimate.
"""

import math
import logging

import requests

logger = logging.getLogger(__name__)

# Hardcoded lat/lng for each Fred Beans Ford store. Addresses are public.
# Coordinates were sourced from each store's published street address — verify
# any one against Google Maps if a result looks off; they're only as good as
# the lookup that produced them. The Mechanicsburg store is the only outlier
# in the network (~100mi west of the others).
DEALERSHIPS = [
    {
        "name": "Fred Beans Ford of Boyertown",
        "address": "1015 N Reading Ave, Boyertown, PA 19512",
        "lat": 40.3450,
        "lng": -75.6360,
    },
    {
        "name": "Fred Beans Ford of Doylestown",
        "address": "845 N Easton Rd, Doylestown, PA 18902",
        "lat": 40.3186,
        "lng": -75.1297,
    },
    {
        "name": "Fred Beans Ford of Exton",
        "address": "110 W Lincoln Hwy, Exton, PA 19341",
        "lat": 40.0271,
        "lng": -75.6381,
    },
    {
        "name": "Fred Beans Ford of Langhorne",
        "address": "395 W Lincoln Hwy, Langhorne, PA 19047",
        "lat": 40.1745,
        "lng": -74.9210,
    },
    {
        "name": "Fred Beans Ford of Mechanicsburg",
        "address": "6711 Carlisle Pike, Mechanicsburg, PA 17050",
        "lat": 40.2135,
        "lng": -77.0254,
    },
    {
        "name": "Fred Beans Ford of Newtown",
        "address": "715 Newtown Yardley Rd, Newtown, PA 18940",
        "lat": 40.2326,
        "lng": -74.9412,
    },
    {
        "name": "Fred Beans Ford of West Chester",
        "address": "1155 Wilmington Pike, West Chester, PA 19382",
        "lat": 39.9298,
        "lng": -75.5720,
    },
]

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a descriptive User-Agent identifying the app.
NOMINATIM_HEADERS = {"User-Agent": "FredBeansMobileService/1.0 (mobileservice@fredbeans.com)"}
OSRM_URL = "https://router.project-osrm.org/table/v1/driving"
HTTP_TIMEOUT = 5


def geocode(query):
    """Return (lat, lng) from Nominatim, or None on no-match / failure.
    Constrained to US results so 'Newtown' doesn't resolve to the UK."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers=NOMINATIM_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        matches = resp.json()
        if not matches:
            return None
        first = matches[0]
        return float(first["lat"]), float(first["lon"])
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        logger.warning(f"Nominatim geocode failed for {query!r}: {e}")
        return None


def haversine_miles(lat1, lng1, lat2, lng2):
    r = 3958.7613  # earth radius, miles
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def driving_distances(origin, destinations):
    """One OSRM /table call: origin → every dealership. Returns a list of
    {'miles': float, 'minutes': float} aligned to destinations, or None on
    any failure (network, non-200, missing fields)."""
    coords = ";".join(
        [f"{origin[1]},{origin[0]}"] + [f"{lng},{lat}" for lat, lng in destinations]
    )
    url = f"{OSRM_URL}/{coords}"
    try:
        resp = requests.get(
            url,
            params={
                "sources": "0",
                "annotations": "distance,duration",
            },
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            logger.warning(f"OSRM non-Ok response: {data.get('code')}")
            return None
        distances_m = data["distances"][0]  # meters, origin → each dest
        durations_s = data["durations"][0]  # seconds
        out = []
        for i in range(len(destinations)):
            dist_m = distances_m[i + 1]  # index 0 is origin → origin
            dur_s = durations_s[i + 1]
            if dist_m is None or dur_s is None:
                return None
            out.append({
                "miles": dist_m / 1609.344,
                "minutes": dur_s / 60.0,
            })
        return out
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        logger.warning(f"OSRM table call failed: {e}")
        return None


def find_nearest(query):
    """Look up `query` and return the dealerships ranked by driving distance.

    Return shape:
      {'origin': (lat, lng), 'results': [{...dealership, miles, minutes, is_estimate}, ...]}
    or
      {'error': <message>}
    """
    origin = geocode(query)
    if origin is None:
        return {"error": "Couldn't find that address — try adding city/state or a ZIP."}

    dests = [(d["lat"], d["lng"]) for d in DEALERSHIPS]
    driving = driving_distances(origin, dests)

    results = []
    if driving is not None:
        for d, dist in zip(DEALERSHIPS, driving):
            results.append({
                **d,
                "miles": dist["miles"],
                "minutes": dist["minutes"],
                "is_estimate": False,
            })
    else:
        # Haversine fallback. Real-road distance ≈ straight-line × 1.3; average
        # local-traffic speed assumed at 40 mph. Good enough to rank the list
        # when the routing API is down.
        for d in DEALERSHIPS:
            straight = haversine_miles(origin[0], origin[1], d["lat"], d["lng"])
            est_miles = straight * 1.3
            results.append({
                **d,
                "miles": est_miles,
                "minutes": est_miles / 40.0 * 60.0,
                "is_estimate": True,
            })

    results.sort(key=lambda r: r["miles"])
    return {"origin": origin, "results": results}

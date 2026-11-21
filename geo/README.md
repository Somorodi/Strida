# Strida route generation

## Run locally

From the repository root with Python 3.12:

```sh
python -m pip install -r geo/requirements.txt
python -m streamlit run geo/app.py
```

Enter a street address with the city and postal code. Strida looks it up with OpenStreetMap's Nominatim service. It uses the included Stafford, Virginia extract where it has nearby streets. Elsewhere, it requests pedestrian loops from the FOSSGIS OSRM service using OpenStreetMap data, and tries Overpass if that returns no suitable loops.

To route from a different local extract, set `STRIDA_OSM_PBF` to an `.osm.pbf` file covering your search area before starting Streamlit. Latitude and longitude also work when generating routes without an online address lookup.

`stafford-walkable.osm.pbf` was built from the project's July 10, 2026 Overpass responses for the Stafford area. Search areas near the edge of the extract may have incomplete coverage.

Street data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed under the Open Database License.

## Deploy a preview

Commit the app changes, including `geo/stafford-walkable.osm.pbf` and `.streamlit/config.toml`, to the GitHub branch you plan to deploy. In Streamlit Community Cloud, select that branch in `Somorodi/Strida`, set the main file path to `geo/app.py`, and select Python 3.12. Streamlit installs dependencies from `geo/requirements.txt`. [Community Cloud deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

After the app starts, generate a 1-mile loop at `10 Columbus Circle, New York, NY 10019`. Check that the map shows the routes, its layer toggles work, and each result has a GPX download.

## Map services

The default public endpoints are for low-volume previews. Nominatim and FOSSGIS each limit requests to one per second across the app. Strida limits each service in a single process. For a public launch serving sustained traffic, configure hosted or self-hosted OpenStreetMap-based services before adding traffic or replicas. [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) · [FOSSGIS routing policy](https://routing.openstreetmap.de/about.html)

Set these as environment variables or as top-level values in Community Cloud's Secrets settings:

| Setting | Service |
| --- | --- |
| `STRIDA_NOMINATIM_URL` | Nominatim base URL, before `/search` |
| `STRIDA_OSRM_FOOT_URL` | OSRM pedestrian route URL through `/route/v1/<profile>` |
| `STRIDA_OVERPASS_URL` | Overpass base API URL, before `/interpreter` |

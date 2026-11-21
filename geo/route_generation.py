import logging
import math
import os
import random
import re
from functools import lru_cache
from pathlib import Path
from threading import Lock
from time import monotonic, sleep

import requests
from requests.exceptions import RequestException
import osmnx as ox
import networkx as nx
import folium
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

METERS_PER_MILE = 1609.34
BACKUP_OVERPASS_URL = "https://overpass.private.coffee/api"
FOSSGIS_FOOT_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/driving"
OSRM_FOOT_URL = os.environ.get("STRIDA_OSRM_FOOT_URL", FOSSGIS_FOOT_URL).rstrip("/")
USER_AGENT = "Strida (https://github.com/Somorodi/Strida)"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
DEFAULT_OSM_PBF = CACHE_DIR.parent / "stafford-walkable.osm.pbf"
overpass_lock = Lock()
osrm_lock = Lock()
geocode_lock = Lock()
last_osrm_request = 0.0
logger = logging.getLogger(__name__)
ox.settings.requests_timeout = 30
ox.settings.use_cache = True
ox.settings.cache_folder = CACHE_DIR
ox.settings.http_user_agent = USER_AGENT
ox.settings.nominatim_url = os.environ.get("STRIDA_NOMINATIM_URL", ox.settings.nominatim_url).rstrip("/")
ox.settings.overpass_url = os.environ.get("STRIDA_OVERPASS_URL", ox.settings.overpass_url).rstrip("/")


def stop_on_busy_response(response, *args, **kwargs):
    # OSMnx otherwise retries these responses recursively.
    if response.status_code in (429, 502, 504):
        response.raise_for_status()
    return response


ox.settings.requests_kwargs = {"hooks": {"response": stop_on_busy_response}}


@lru_cache(maxsize=1)
def read_walkable_extract(path, modified_at):
    return ox.graph.graph_from_pbf(path, network_type="walk", retain_all=True)


def load_local_network(start_point, radius, progress=None):
    extract = os.environ.get("STRIDA_OSM_PBF")
    path = Path(extract).expanduser().resolve() if extract else DEFAULT_OSM_PBF
    if extract and not path.is_file():
        raise ValueError("The configured OpenStreetMap extract file could not be found.")
    if path.is_file():
        if progress:
            progress("Loading walkable streets from the local OpenStreetMap extract…")
        graph = read_walkable_extract(path, path.stat().st_mtime_ns)
        bounds = ox.utils_geo.bbox_from_point(start_point, dist=radius)
        try:
            local_graph = ox.truncate.truncate_graph_bbox(graph, bounds)
        except ValueError:
            local_graph = None
        if local_graph is not None and local_graph.number_of_edges():
            local_graph = ox.truncate.largest_component(local_graph)
            _, start_distance = ox.distance.nearest_nodes(
                local_graph, X=start_point[1], Y=start_point[0], return_dist=True
            )
            if start_distance <= 500:
                return local_graph
        if extract:
            raise ValueError("The local OpenStreetMap extract has no walkable connections in this search area.")


def load_walkable_network(start_point, radius, progress=None):
    if progress:
        progress("Downloading walkable streets from OpenStreetMap…")
    # OSMnx uses process-wide settings, so keep the endpoint switch local to one request.
    with overpass_lock:
        primary_url = ox.settings.overpass_url
        primary_rate_limit = ox.settings.overpass_rate_limit
        endpoints = (primary_url,) if os.environ.get("STRIDA_OVERPASS_URL") else (
            primary_url, BACKUP_OVERPASS_URL
        )
        try:
            for url in dict.fromkeys(endpoints):
                ox.settings.overpass_url = url
                # Private.coffee does not use Overpass slot limits.
                ox.settings.overpass_rate_limit = primary_rate_limit and url != BACKUP_OVERPASS_URL
                try:
                    return ox.graph_from_point(start_point, dist=radius, network_type="walk")
                except (RequestException, ox._errors.ResponseStatusCodeError,
                        ox._errors.InsufficientResponseError) as error:
                    last_error = error
                    logger.warning("Overpass request to %s failed: %s", url, type(error).__name__)
        finally:
            ox.settings.overpass_url = primary_url
            ox.settings.overpass_rate_limit = primary_rate_limit

    if isinstance(last_error, ox._errors.InsufficientResponseError):
        raise ValueError(
            "No usable walkable street network was returned. Try a nearby starting point or a larger search radius."
        ) from last_error
    raise ValueError(
        "The online street network services are unavailable. Configure a local OpenStreetMap extract to generate routes offline."
    ) from last_error


@lru_cache(maxsize=128)
def request_pedestrian_loop(points):
    global last_osrm_request
    locations = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    with osrm_lock:
        sleep(max(0, 1.05 - (monotonic() - last_osrm_request)))
        last_osrm_request = monotonic()
        response = requests.get(
            f"{OSRM_FOOT_URL}/{locations}",
            params={"geometries": "geojson", "overview": "full",
                    "radiuses": "100;100;100;100"},
            headers={"User-Agent": USER_AGENT},
            timeout=(3, 7),
        )
    data = response.json()
    if data.get("code") in {"NoRoute", "NoSegment"}:
        return None
    response.raise_for_status()
    return data["routes"][0]


def get_pedestrian_candidates(start, radius, target_meters):
    graph = nx.MultiDiGraph()
    candidates = []
    lat, lon = start
    west, south, east, north = ox.utils_geo.bbox_from_point(start, dist=radius)
    waypoint_distance = min(radius * 0.8, target_meters / 4)
    angular_distance = waypoint_distance / 6_371_009

    def waypoint(degrees):
        bearing = math.radians(degrees)
        start_lat = math.radians(lat)
        end_lat = math.asin(math.sin(start_lat) * math.cos(angular_distance)
                            + math.cos(start_lat) * math.sin(angular_distance) * math.cos(bearing))
        end_lon = lon + math.degrees(math.atan2(
            math.sin(bearing) * math.sin(angular_distance) * math.cos(start_lat),
            math.cos(angular_distance) - math.sin(start_lat) * math.sin(end_lat),
        ))
        return math.degrees(end_lat), (end_lon + 180) % 360 - 180

    for bearing in range(0, 360, 60):
        try:
            result = request_pedestrian_loop(
                (start, waypoint(bearing), waypoint(bearing + 75), start)
            )
            if result is None:
                continue
            distance = result["distance"]
            path = [(x, y) for x, y in result["geometry"]["coordinates"]]
        except (RequestException, KeyError, IndexError, TypeError, ValueError) as error:
            logger.warning("Pedestrian routing request failed: %s", type(error).__name__)
            break
        if (len(path) < 4 or path[0] != path[-1]
                or not 0.5 * target_meters <= distance <= 1.5 * target_meters
                or any(not (west <= x <= east and south <= y <= north) for x, y in path)):
            continue
        repetition = repeated_edge_ratio(path)
        if repetition > 0.5:
            continue
        graph.add_nodes_from((point, {"x": point[0], "y": point[1]}) for point in path)
        graph.add_edges_from(
            (u, v, {"length": ox.distance.great_circle(u[1], u[0], v[1], v[0])})
            for u, v in zip(path, path[1:])
        )
        candidates.append({
            "path": path,
            "length_meters": distance,
            "repeated_edge_ratio": repetition,
        })
    return graph, candidates


def route_coordinates(G, path):
    coordinates = [(G.nodes[path[0]]["y"], G.nodes[path[0]]["x"])]
    for u, v in zip(path, path[1:]):
        edge = min(G[u][v].values(), key=lambda data: data["length"])
        geometry = edge.get("geometry")
        if geometry is None:
            coordinates.append((G.nodes[v]["y"], G.nodes[v]["x"]))
            continue
        segment = [(y, x) for x, y in geometry.coords]
        if segment[0] != coordinates[-1]:
            segment.reverse()
        coordinates.extend(segment[1:])
    return coordinates


def resolve_start(address):
    address = address.strip()
    coordinates = re.fullmatch(r"([+-]?\d+(?:\.\d+)?),\s*([+-]?\d+(?:\.\d+)?)", address)
    if coordinates:
        latitude, longitude = map(float, coordinates.groups())
        if abs(latitude) <= 90 and abs(longitude) <= 180:
            return latitude, longitude
        raise ValueError("Enter latitude between -90 and 90 and longitude between -180 and 180.")

    try:
        with geocode_lock:
            return ox.geocode(address)
    except (RequestException, ValueError, ox._errors.InsufficientResponseError,
            ox._errors.ResponseStatusCodeError) as primary_error:
        if re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?(?:\s*,?\s*(?:US|USA))?$", address, re.I):
            try:
                response = requests.get(
                    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
                    params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
                    timeout=8
                )
                response.raise_for_status()
                matches = response.json()["result"]["addressMatches"]
                if matches:
                    point = matches[0]["coordinates"]
                    return float(point["y"]), float(point["x"])
            except (RequestException, KeyError, TypeError, ValueError) as error:
                raise ValueError("The address lookup services are unavailable. Try again shortly or enter coordinates.") from error
        if isinstance(primary_error, (RequestException, ox._errors.ResponseStatusCodeError)):
            raise ValueError("Address lookup is unavailable. For a U.S. address, include the state and ZIP code to try the backup service.") from primary_error
        raise ValueError("Could not find that address. Include the city, state, and ZIP code where applicable.") from primary_error

def route_to_gpx(G, route_path, route_name="Strida Route"):
    """
    Convert an OSMnx route path into a GPX XML string.

    Parameters:
        G: OSMnx/NetworkX graph
        route_path: Ordered list of node IDs
        route_name: Name displayed in Garmin or another GPS app

    Returns:
        A UTF-8 encoded GPX file as bytes.
    """

    gpx = Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "Strida",
            "xmlns": "http://www.topografix.com/GPX/1/1",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": (
                "http://www.topografix.com/GPX/1/1 "
                "http://www.topografix.com/GPX/1/1/gpx.xsd"
            ),
        },
    )

    metadata = SubElement(gpx, "metadata")
    SubElement(metadata, "name").text = route_name

    route_element = SubElement(gpx, "rte")
    SubElement(route_element, "name").text = route_name

    for node_id in route_path:
        node = G.nodes[node_id]

        latitude = node["y"]
        longitude = node["x"]

        SubElement(
            route_element,
            "rtept",
            {
                "lat": str(latitude),
                "lon": str(longitude),
            },
        )

    rough_xml = tostring(gpx, encoding="utf-8")
    formatted_xml = minidom.parseString(rough_xml).toprettyxml(
        indent="  ",
        encoding="UTF-8",
    )

    return formatted_xml

def get_edge_length(G, u, v):
    """
    Return the shortest parallel edge length between two nodes.
    """
    edge_data = G.get_edge_data(u, v)

    if not edge_data:
        raise nx.NetworkXNoPath(
            f"No edge exists between {u} and {v}."
        )

    return min(
        data.get("length", float("inf"))
        for data in edge_data.values()
    )


def calculate_path_length(G, path):
    """
    Calculate the total length of a path in meters.
    """
    return sum(
        get_edge_length(G, u, v)
        for u, v in zip(path[:-1], path[1:])
    )


def combine_paths(*paths):
    """
    Join path segments without duplicating the connecting node.
    """
    full_path = []

    for path in paths:
        if not path:
            continue

        if not full_path:
            full_path.extend(path)
        else:
            full_path.extend(path[1:])

    return full_path


def node_angle(G, start_node, node):
    """
    Return the angle from the start node to another node.
    """
    start_x = G.nodes[start_node]["x"]
    start_y = G.nodes[start_node]["y"]

    node_x = G.nodes[node]["x"]
    node_y = G.nodes[node]["y"]

    return math.atan2(
        node_y - start_y,
        node_x - start_x
    )


def path_edge_set(path):
    """
    Convert a path into undirected edge pairs.

    Treating edges as undirected lets us detect a road used
    in either direction.
    """
    return {
        frozenset((u, v))
        for u, v in zip(path[:-1], path[1:])
    }


def repeated_edge_ratio(path):
    """
    Measure how much of a route repeats roads.

    0.0 means no road segments repeat.
    Higher values indicate more retracing.
    """
    edges = [
        frozenset((u, v))
        for u, v in zip(path[:-1], path[1:])
    ]

    if not edges:
        return 1.0

    unique_edges = set(edges)

    repeated_count = len(edges) - len(unique_edges)

    return repeated_count / len(edges)

def generate_loop_candidates(
    G,
    start_node,
    target_meters,
    attempts=500,
    max_candidates=30,
    distance_tolerance=0.50,
    max_repeated_edge_ratio=0.50,
    random_seed=42,
    time_budget=15
):
    """
    Generate loop candidates using two intermediate waypoints.

    Route structure:
        start -> waypoint A -> waypoint B -> start
    """
    random_generator = random.Random(random_seed)
    deadline = monotonic() + time_budget

    # Calculate network distance from the start to every reachable node.
    distances_from_start = nx.single_source_dijkstra_path_length(
        G,
        start_node,
        cutoff=target_meters,
        weight="length"
    )
    
    
    
    
    # For a triangular loop, waypoints should generally be somewhere
    # between roughly 15% and 45% of the target distance from the start.
    minimum_waypoint_distance = target_meters * 0.15
    maximum_waypoint_distance = target_meters * 0.45

    waypoint_nodes = [
        node
        for node, distance in distances_from_start.items()
        if minimum_waypoint_distance
        <= distance
        <= maximum_waypoint_distance
        and node != start_node
    ]
    print(f"Eligible waypoint nodes: {len(waypoint_nodes)}")
    
    if len(waypoint_nodes) < 2:
        return []

    candidate_routes = []
    seen_paths = set()
    tried_waypoints = set()
    possible_pairs = len(waypoint_nodes) * (len(waypoint_nodes) - 1)

    for _ in range(attempts):
        if monotonic() >= deadline or len(tried_waypoints) == possible_pairs:
            break
        waypoint_a, waypoint_b = random_generator.sample(
            waypoint_nodes,
            2
        )
        pair = (waypoint_a, waypoint_b)
        if pair in tried_waypoints:
            continue
        tried_waypoints.add(pair)

        angle_a = node_angle(G, start_node, waypoint_a)
        angle_b = node_angle(G, start_node, waypoint_b)

        # Calculate angular separation.
        angle_difference = abs(angle_a - angle_b)
        angle_difference = min(
            angle_difference,
            (2 * math.pi) - angle_difference
        )

        # Reject waypoints pointing in nearly the same direction.
        # They often create narrow out-and-back routes.
        if angle_difference < math.radians(50):
            continue

        try:
            path_one = nx.shortest_path(
                G,
                start_node,
                waypoint_a,
                weight="length"
            )

            path_two = nx.shortest_path(
                G,
                waypoint_a,
                waypoint_b,
                weight="length"
            )

            path_three = nx.shortest_path(
                G,
                waypoint_b,
                start_node,
                weight="length"
            )

            full_path = combine_paths(
                path_one,
                path_two,
                path_three
            )

            if len(full_path) < 4:
                continue

            # The route must return to its starting network node.
            if full_path[0] != full_path[-1]:
                continue

            length = calculate_path_length(
                G,
                full_path
            )

            minimum_length = (
                target_meters
                * (1 - distance_tolerance)
            )

            maximum_length = (
                target_meters
                * (1 + distance_tolerance)
            )

            if not minimum_length <= length <= maximum_length:
                continue

            repeat_ratio = repeated_edge_ratio(full_path)

            # Reject routes that retrace too many road segments.
            if repeat_ratio > max_repeated_edge_ratio:
                continue

            # Prevent the exact same node sequence from being added twice.
            path_key = tuple(full_path)

            if path_key in seen_paths:
                continue

            seen_paths.add(path_key)

            candidate_routes.append({
                "path": full_path,
                "length_meters": length,
                "repeated_edge_ratio": repeat_ratio,
                "waypoints": [
                    waypoint_a,
                    waypoint_b
                ]
            })# Stop once we have enough valid routes to score.
            if len(candidate_routes) >= max_candidates:
                break

        except (
            nx.NetworkXNoPath,
            nx.NodeNotFound
        ):
            continue
    print(
        f"Loop generation completed: "
        f"{len(candidate_routes)} valid candidates"
    )

    return candidate_routes

def route_similarity(path_a, path_b):
    nodes_a = set(path_a)
    nodes_b = set(path_b)

    if not nodes_a or not nodes_b:
        return 0.0

    intersection = len(nodes_a & nodes_b)
    union = len(nodes_a | nodes_b)

    return intersection / union


def remove_similar_routes(routes, similarity_threshold=0.80):
    unique_routes = []

    for route in routes:
        is_duplicate = False

        for accepted_route in unique_routes:
            similarity = route_similarity(
                route["path"],
                accepted_route["path"]
            )

            if similarity >= similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            unique_routes.append(route)

    return unique_routes


def score_route(route, target_meters):
    miles = route["length_meters"] / METERS_PER_MILE

    score = 0
    reasons = []

    # Distance score: maximum 50 points.
    distance_error_ratio = (
        abs(route["length_meters"] - target_meters)
        / target_meters
    )

    distance_score = max(
        0,
        50 * (1 - distance_error_ratio)
    )

    score += distance_score
    reasons.append(
        f"distance is {miles:.2f} miles"
    )

    # Reward low repetition: maximum 30 points.
    repeat_ratio = route.get(
        "repeated_edge_ratio",
        1.0
    )

    repetition_score = max(
        0,
        30 * (1 - repeat_ratio)
    )

    score += repetition_score

    if repeat_ratio <= 0.10:
        reasons.append(
            "uses very little repeated path"
        )
    elif repeat_ratio <= 0.25:
        reasons.append(
            "has limited path repetition"
        )

    # Reward overall route variety.
    unique_nodes = len(set(route["path"]))

    if unique_nodes >= 10:
        score += 15
        reasons.append(
            "has good path variety"
        )
    elif unique_nodes >= 6:
        score += 8
        reasons.append(
            "has moderate path variety"
        )

    route["score"] = round(score, 1)
    route["reasons"] = reasons
    route["length_miles"] = miles

    return route

def generate_routes(
    candidate_routes,
    target_meters,
    number_of_routes=5,
    similarity_threshold=0.80
):
    """
    Score, rank, and remove duplicate routes.
    """

    scored_routes = []

    for route in candidate_routes:
        scored_route = score_route(
            route,
            target_meters
        )

        scored_routes.append(scored_route)

    # Sort strongest routes first
    scored_routes = sorted(
        scored_routes,
        key=lambda route: route["score"],
        reverse=True
    )

    # Remove highly similar routes
    distinct_routes = remove_similar_routes(
        scored_routes,
        similarity_threshold=similarity_threshold
    )

    return distinct_routes[:number_of_routes]

def create_strida_routes(
    address,
    target_miles,
    graph_radius=2500,
    number_of_routes=5,
    progress=None
):
    """
    Generate Strida loop routes and return a Folium map.

    Args:
        address:
            Starting street address.

        target_miles:
            Requested running distance.

        graph_radius:
            Radius in meters used to download the walking network.

        number_of_routes:
            Maximum routes displayed.

    Returns:
        folium.Map, list of routes, cycle count
    """
    if progress:
        progress("Finding your start address…")
    start_point = resolve_start(address)
    
    target_meters = target_miles * METERS_PER_MILE

    G = load_local_network(start_point, graph_radius, progress=progress)
    candidate_routes = []
    cycle_count = None
    if G is None:
        if progress:
            progress("Finding pedestrian loops on OpenStreetMap…")
        G, candidate_routes = get_pedestrian_candidates(start_point, graph_radius, target_meters)
        if not candidate_routes:
            G = load_walkable_network(start_point, graph_radius, progress=progress)

    if not candidate_routes:
        if progress:
            progress("Searching for running loops…")
        cycle_count = len(nx.cycle_basis(nx.Graph(G)))
        start_node = ox.distance.nearest_nodes(G, X=start_point[1], Y=start_point[0])
        candidate_routes = generate_loop_candidates(
            G=G,
            start_node=start_node,
            target_meters=target_meters,
            attempts=5000,
            distance_tolerance=0.50,
            max_repeated_edge_ratio=0.50,
            random_seed=42
        )

    scored_routes = generate_routes(
        candidate_routes=candidate_routes,
        target_meters=target_meters,
        number_of_routes=number_of_routes,
        similarity_threshold=0.80
    )

    if not scored_routes:
        raise ValueError(
            "No valid routes were found. Try increasing graph_radius "
            "or changing the requested distance."
        )

    route_map = folium.Map(
        location=start_point,
        zoom_start=15
    )

    colors = ("green", "blue", "purple", "darkorange", "darkred")
    for index in reversed(range(len(scored_routes))):
        route = scored_routes[index]
        name = "Best route" if index == 0 else f"Route {index + 1}"
        coordinates = route_coordinates(G, route["path"])
        layer = folium.FeatureGroup(name=name).add_to(route_map)
        folium.PolyLine(
            coordinates,
            weight=6 if index == 0 else 4,
            color=colors[index % len(colors)],
            tooltip=f"{name} | {route['length_miles']:.2f} miles | Score {route['score']}"
        ).add_to(layer)

    folium.Marker(
        location=start_point,
        tooltip=address,
        popup=f"Starting point: {address}"
    ).add_to(route_map)
    folium.LayerControl(collapsed=False).add_to(route_map)
    route_map.fit_bounds(route_map.get_bounds())

    return route_map, scored_routes, cycle_count, G



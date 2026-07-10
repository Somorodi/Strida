import math
import random
import osmnx as ox
import networkx as nx
import folium


METERS_PER_MILE = 1609.34

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
    random_seed=42
):
    """
    Generate loop candidates using two intermediate waypoints.

    Route structure:
        start -> waypoint A -> waypoint B -> start
    """
    random_generator = random.Random(random_seed)

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

    for _ in range(attempts):
        waypoint_a, waypoint_b = random_generator.sample(
            waypoint_nodes,
            2
        )

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
    start_point,
    target_miles,
    graph_radius=2500,
    number_of_routes=5
):
    """
    Generate Strida loop routes and return a Folium map.

    Args:
        start_point:
            Tuple containing latitude and longitude.

        target_miles:
            Requested running distance.

        graph_radius:
            Radius in meters used to download the walking network.

        number_of_routes:
            Maximum routes displayed.

    Returns:
        folium.Map, list of routes, cycle count
    """
    target_meters = target_miles * METERS_PER_MILE

    G = ox.graph_from_point(
        start_point,
        dist=graph_radius,
        network_type="walk",
        simplify=True
    )

    G = ox.distance.add_edge_lengths(G)

    nodes, edges = ox.graph_to_gdfs(G)

    simple_graph = nx.Graph(G)
    cycles = nx.cycle_basis(simple_graph)
    cycle_count = len(cycles)

    start_node = ox.distance.nearest_nodes(
        G,
        X=start_point[1],
        Y=start_point[0]
    )

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

    route_map = folium.Map(
        location=start_point,
        zoom_start=15
    )

    route_colors = [
        "green",
        "blue",
        "purple",
        "orange",
        "red"
    ]

    best_route = scored_routes[0]

    coords = []

    for node in best_route["path"]:
        latitude = G.nodes[node]["y"]
        longitude = G.nodes[node]["x"]

        coords.append((latitude, longitude))

    folium.PolyLine(
    coords,
    weight=8,
    color="green",
    tooltip=(
        f"{best_route['length_miles']:.2f} miles | "
        f"Score {best_route['score']}"
    )
).add_to(route_map)

    return route_map, scored_routes, cycle_count


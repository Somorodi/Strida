import osmnx as ox
import networkx as nx
import folium

place = "Government Island, Stafford, Virginia, USA"
target_miles = 1
target_meters = target_miles * 1609.34

print("Downloading walkable graph...")
G = ox.graph_from_place(place, network_type="walk")

# Add edge lengths
G = ox.distance.add_edge_lengths(G)

nodes, edges = ox.graph_to_gdfs(G)

# Pick a start node near the western side / parking area
start_point = (38.4275, -77.4135)  # lat, lon
start_node = ox.distance.nearest_nodes(G, X=start_point[1], Y=start_point[0])

print("Start node:", start_node)

candidate_routes = []

for node in G.nodes:
    try:
        path_out = nx.shortest_path(G, start_node, node, weight="length")
        path_back = nx.shortest_path(G, node, start_node, weight="length")

        full_path = path_out + path_back[1:]

        length = 0
        for u, v in zip(full_path[:-1], full_path[1:]):
            edge_data = G.get_edge_data(u, v)
            first_edge = list(edge_data.values())[0]
            length += first_edge.get("length", 0)

        # Keep routes close to target distance
        if 400 <= length <= 5000:
            candidate_routes.append({
                "path": full_path,
                "length_meters": length
            })

    except:
        continue

print(f"Candidate routes found: {len(candidate_routes)}")


# Sort closest to target
candidate_routes = sorted(
    candidate_routes,
    key=lambda r: abs(r["length_meters"] - target_meters)
)

# Score candidate routes
scored_routes = []

for route in candidate_routes:
    miles = route["length_meters"] / 1609.34

    score = 0
    reasons = []

    # Distance score: closer to target is better
    distance_error = abs(route["length_meters"] - target_meters)
    distance_score = max(0, 40 - (distance_error / 50))
    score += distance_score
    reasons.append(f"distance is {miles:.2f} miles")

    # Prefer routes with more nodes/shape instead of tiny straight out-and-backs
    unique_nodes = len(set(route["path"]))
    if unique_nodes >= 6:
        score += 15
        reasons.append("has enough path variety")

    # Prefer longer usable routes
    if route["length_meters"] >= 1200:
        score += 15
        reasons.append("long enough to be useful")

    route["score"] = round(score, 1)
    route["reasons"] = reasons
    scored_routes.append(route)

# Sort by score
scored_routes = sorted(scored_routes, key=lambda r: r["score"], reverse=True)

best_route = scored_routes[0]

print("\n----- Best Strida Route -----")
print(f"Score: {best_route['score']}")
print(f"Distance: {best_route['length_meters'] / 1609.34:.2f} miles")
print("Why:")
for reason in best_route["reasons"]:
    print("-", reason)


# Score candidate routes
scored_routes = []

for route in candidate_routes:
    miles = route["length_meters"] / 1609.34
    score = 0
    reasons = []

    distance_error = abs(route["length_meters"] - target_meters)
    distance_score = max(0, 40 - (distance_error / 50))
    score += distance_score
    reasons.append(f"distance is {miles:.2f} miles")

    unique_nodes = len(set(route["path"]))
    if unique_nodes >= 6:
        score += 15
        reasons.append("has enough path variety")

    if route["length_meters"] >= 1200:
        score += 15
        reasons.append("long enough to be useful")

    route["score"] = round(score, 1)
    route["reasons"] = reasons
    scored_routes.append(route)

scored_routes = sorted(scored_routes, key=lambda r: r["score"], reverse=True)
best_route = scored_routes[0]

print("\n----- Best Strida Route -----")
print(f"Score: {best_route['score']}")
print(f"Distance: {best_route['length_meters'] / 1609.34:.2f} miles")
print("Why:")
for reason in best_route["reasons"]:
    print("-", reason)

# Map
center = nodes.geometry.union_all().centroid
m = folium.Map(location=[center.y, center.x], zoom_start=16)

for i, route in enumerate(scored_routes[:5]):
    coords = []
    for node in route["path"]:
        y = G.nodes[node]["y"]
        x = G.nodes[node]["x"]
        coords.append((y, x))

    miles = route["length_meters"] / 1609.34
    is_best = route == best_route

    folium.PolyLine(
        coords,
        weight=10 if is_best else 4,
        color="green" if is_best else "blue",
        tooltip=f"{'BEST ' if is_best else ''}Candidate {i+1}: {miles:.2f} miles | Score {route['score']}"
    ).add_to(m)

folium.Marker(
    [start_point[0], start_point[1]],
    tooltip="Start / Parking",
    popup="🅿️ Start here"
).add_to(m)

m.save("candidate_routes.html")
print("Map created: candidate_routes.html")


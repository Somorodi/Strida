locations = [
    {
        "name": "Government Island",
        "shade": True,
        "parking": True,
        "hills": False,
        "surface": "gravel",
        "water_fountains": False,
        "flat": True,
        "loop_potential": True,
        "track_nearby": False,
        "views": True,
        "places_to_stop": True,
        "scenic": True,
        "flat_1000m_stretch": True
    },
    {
        "name": "Aquia Landing Beach Park",
        "shade": False,
        "parking": True,
        "hills": False,
        "surface": "asphalt",
        "water_fountains": True,
        "flat": True,
        "loop_potential": False,
        "track_nearby": False,
        "views": True,
        "places_to_stop": True,
        "scenic": True,
        "flat_1000m_stretch": True
    },
    {
        "name": "Stafford Civil War Park",
        "shade": True,
        "parking": True,
        "hills": True,
        "surface": "dirt",
        "water_fountains": False,
        "flat": False,
        "loop_potential": True,
        "track_nearby": False,
        "views": True,
        "places_to_stop": True,
        "scenic": True,
        "flat_1000m_stretch": False
    }
]

request = input("Tell Strida what kind of route you want: ").lower()

for location in locations:
    score = 0
    reasons = []

    if "shade" in request and location["shade"]:
        score += 15
        reasons.append("has shade")

    if "parking" in request and location["parking"]:
        score += 10
        reasons.append("has parking")

    if "hills" in request and location["hills"]:
        score += 20
        reasons.append("has hills")

    if "flat" in request and location["flat"]:
        score += 20
        reasons.append("has flat terrain")

    if "water" in request and location["water_fountains"]:
        score += 15
        reasons.append("has water fountains")

    if "loop" in request and location["loop_potential"]:
        score += 15
        reasons.append("good loop potential")

    if "track" in request and location["track_nearby"]:
        score += 15
        reasons.append("track nearby")

    if "view" in request or "scenic" in request:
        if location["views"] or location["scenic"]:
            score += 15
            reasons.append("scenic/views")

    if "1000m" in request or "1k" in request or "1000 meter" in request:
        if location["flat_1000m_stretch"]:
            score += 25
            reasons.append("has flat 1000m stretch potential")

    if location["surface"] in request:
        score += 15
        reasons.append(f"matches preferred surface: {location['surface']}")

    location["score"] = score
    location["reasons"] = reasons

best = max(locations, key=lambda x: x["score"])

print("\n----- Strida Recommendation -----")
print("Best location:", best["name"])
print("Score:", best["score"])

print("\nWhy:")
for reason in best["reasons"]:
    print("-", reason)

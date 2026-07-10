import osmnx as ox

place = "Stafford, Virginia, USA"

print("Searching for parks in Stafford...")

parks = ox.features_from_place(
    place,
    tags={"leisure": "park"}
)

print("\n----- Strida Found These Running Locations -----")

parks = parks[["name"]].dropna().drop_duplicates()

for index, row in parks.iterrows():
    print("-", row["name"])

print("\n----- Strida Location Scores -----")

for index, row in parks.iterrows():
    name = row["name"]
    score = 50
    reasons = []

    if "Island" in name:
        score += 20
        reasons.append("likely scenic/waterfront")

    if "Beach" in name or "Landing" in name:
        score += 20
        reasons.append("good scenery potential")

    if "Park" in name:
        score += 10
        reasons.append("park location")

    if "Trail" in name:
        score += 15
        reasons.append("trail-friendly")

    if "Civil War" in name or "National" in name:
        score += 10
        reasons.append("historic/scenic area")

    print(f"\n{name}")
    print(f"Strida Score: {score}/100")

    if reasons:
        print("Why:")
        for reason in reasons:
            print("-", reason)
workout = {
    "day": "Tuesday",
    "type": "intervals",
    "details": "10 miles with 8 x 1000m",
    "needs": {
        "flat_1000m_stretch": True,
        "low_stoplights": True,
        "water": True,
        "parking": True
    }
}

user_profile = {
    "name": "Simeon",
    "prefers_surface": "gravel",
    "likes_scenic": True,
    "likes_shade": True,
    "max_drive_minutes": 20,
    "preferred_run_times": ["morning"]
}

available_times = [
    {
        "time": "6:30 AM",
        "weather_score": 95,
        "schedule_fit": 90,
        "reason": "coolest part of the morning and fits schedule"
    },
    {
        "time": "12:30 PM",
        "weather_score": 45,
        "schedule_fit": 80,
        "reason": "fits schedule but hotter"
    },
    {
        "time": "7:00 PM",
        "weather_score": 75,
        "schedule_fit": 60,
        "reason": "cooler, but less ideal for your preferred routine"
    }
]

routes = [
    {
        "name": "Government Island",
        "drive_minutes": 12,
        "surface": "gravel",
        "flat_1000m_stretch": True,
        "low_stoplights": True,
        "water": False,
        "parking": True,
        "scenic": True,
        "shade": True
    },
    {
        "name": "Aquia Landing Beach Park",
        "drive_minutes": 18,
        "surface": "asphalt",
        "flat_1000m_stretch": True,
        "low_stoplights": True,
        "water": True,
        "parking": True,
        "scenic": True,
        "shade": False
    },
    {
        "name": "Stafford Civil War Park",
        "drive_minutes": 16,
        "surface": "dirt",
        "flat_1000m_stretch": False,
        "low_stoplights": True,
        "water": False,
        "parking": True,
        "scenic": True,
        "shade": True
    }
]

best_option = None
best_score = -1

for time_slot in available_times:
    for route in routes:
        score = 0
        reasons = []

        # Time score
        score += time_slot["weather_score"] * 0.25
        score += time_slot["schedule_fit"] * 0.25
        reasons.append(f"{time_slot['time']} works because {time_slot['reason']}")

        # Workout needs
        for need, required in workout["needs"].items():
            if required and route.get(need):
                score += 15
                reasons.append(f"{route['name']} satisfies workout need: {need}")

        # User preferences
        if route["surface"] == user_profile["prefers_surface"]:
            score += 10
            reasons.append(f"matches preferred surface: {route['surface']}")

        if user_profile["likes_scenic"] and route["scenic"]:
            score += 8
            reasons.append("matches your preference for scenic routes")

        if user_profile["likes_shade"] and route["shade"]:
            score += 8
            reasons.append("has shade, which you usually prefer")

        if route["drive_minutes"] <= user_profile["max_drive_minutes"]:
            score += 10
            reasons.append(f"within your drive limit: {route['drive_minutes']} minutes")

        option = {
            "time": time_slot["time"],
            "route": route["name"],
            "score": round(score, 1),
            "reasons": reasons
        }

        if option["score"] > best_score:
            best_score = option["score"]
            best_option = option

print("\n🏃 Strida Recommendation")
print("-------------------------")
print("Workout:", workout["details"])
print("Best time:", best_option["time"])
print("Best route:", best_option["route"])
print("Match score:", best_option["score"])

print("\nWhy Strida picked this:")
for reason in best_option["reasons"]:
    print("-", reason)
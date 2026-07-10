import streamlit as st
from streamlit_folium import st_folium

from route_generation import create_strida_routes


st.set_page_config(
    page_title="Strida MVP",
    page_icon="🏃",
    layout="wide"
)

st.title("🏃 Strida")
st.write(
    "Enter a starting point and target distance "
    "to generate running loops."
)

with st.sidebar:
    st.header("Route settings")

    latitude = st.number_input(
        "Starting latitude",
        value=38.4275,
        format="%.6f"
    )

    longitude = st.number_input(
        "Starting longitude",
        value=-77.4135,
        format="%.6f"
    )

    target_miles = st.number_input(
        "Target distance in miles",
        min_value=0.5,
        max_value=30.0,
        value=1.0,
        step=0.5
    )

    graph_radius = st.slider(
        "Search radius in meters",
        min_value=1000,
        max_value=5000,
        value=2500,
        step=500
    )

    generate_button = st.button(
        "Generate routes",
        type="primary",
        use_container_width=True
    )


if generate_button:
    start_point = (
        latitude,
        longitude
    )

    try:
        with st.spinner(
            "Downloading the walking network "
            "and generating loops..."
        ):
            route_map, routes, cycle_count = (
                create_strida_routes(
                    start_point=start_point,
                    target_miles=target_miles,
                    graph_radius=graph_radius,
                    number_of_routes=5
                )
            )

        st.write(
            f"Network cycles available: "
            f"**{cycle_count}**"
        )

        if not routes:
            st.warning(
                "Strida could not find a suitable loop. "
                "Try increasing the search radius or "
                "changing the starting point."
            )
        else:
            st.success(
                f"Generated {len(routes)} loop route(s)."
            )

            st_folium(
                route_map,
                width=None,
                height=650,
                returned_objects=[]
            )

            st.subheader("Route options")

            for index, route in enumerate(routes):
                with st.container(border=True):
                    route_name = (
                        "Best route"
                        if index == 0
                        else f"Route {index + 1}"
                    )

                    st.markdown(
                        f"### {route_name}"
                    )

                    column_one, column_two, column_three = (
                        st.columns(3)
                    )

                    column_one.metric(
                        "Distance",
                        f"{route['length_miles']:.2f} mi"
                    )

                    column_two.metric(
                        "Strida score",
                        route["score"]
                    )

                    repeated_percentage = (
                        route.get(
                            "repeated_edge_ratio",
                            0
                        ) * 100
                    )

                    column_three.metric(
                        "Repeated path",
                        f"{repeated_percentage:.0f}%"
                    )

                    st.write("Why Strida selected it:")

                    for reason in route["reasons"]:
                        st.write(f"• {reason}")

    except Exception as error:
        st.error(
            "Strida encountered an error while "
            "generating the route."
        )

        st.exception(error)
else:
    st.info(
        "Adjust the settings in the sidebar, "
        "then select Generate routes."
    )
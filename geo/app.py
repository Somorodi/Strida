import folium
import streamlit as st
from streamlit_folium import st_folium


from route_generation import (
    create_strida_routes,
    route_to_gpx
)


st.set_page_config(
    page_title="Strida MVP",
    page_icon="🧭",
    layout="wide"
)

st.title("Strida")

st.write(
    "Enter a starting address and target distance "
    "to generate a running loop."
)

with st.sidebar:
    st.header("Route settings")

    address = st.text_input(
        "Starting address",
        placeholder="123 Main St, Stafford, VA 22554",
        help="Use a street address with city, state and ZIP code. Latitude, longitude also works."
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
    st.session_state.pop("route_results", None)
    if not address.strip():
        st.warning(
            "Enter a starting address before generating a route."
        )

    else:
        status = st.empty()
        try:
            st.session_state["route_results"] = create_strida_routes(
                address=address.strip(),
                target_miles=target_miles,
                graph_radius=graph_radius,
                number_of_routes=5,
                progress=status.info
            )
        except ValueError as error:
            st.error(str(error))
        except Exception as error:
            st.error("Strida encountered an error while generating the route.")
            st.exception(error)
        finally:
            status.empty()


results = st.session_state.get("route_results")
if results is not None:
    route_map, routes, cycle_count, G = results
    st.write(
        f"Network cycles available: "
        f"**{cycle_count}**"
    )

    if not routes:
        st.warning(
            "Strida could not find a suitable loop. "
            "Try increasing the search radius, changing "
            "the distance, or entering a more complete address."
        )
    else:
        st.success(
            f"Generated {len(routes)} loop route(s)."
        )

        st_folium(
            route_map,
            width=None,
            height=650,
            returned_objects=[],
            key="best_route_map"
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

                (
                    column_one,
                    column_two,
                    column_three
                ) = st.columns(3)

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



                # The best route is already displayed
                # on the large map above.
                if index > 0:
                    with st.expander(
                        f"Preview {route_name}"
                    ):
                        route_coordinates = [
                            (
                                G.nodes[node]["y"],
                                G.nodes[node]["x"]
                            )
                            for node in route["path"]
                        ]

                        preview_map = folium.Map(
                            location=route_coordinates[0],
                            zoom_start=15
                        )

                        folium.PolyLine(
                            route_coordinates,
                            weight=7,
                            color="green",
                            tooltip=(
                                f"{route['length_miles']:.2f} miles | "
                                f"Score {route['score']}"
                            )
                        ).add_to(preview_map)

                        folium.Marker(
                            route_coordinates[0],
                            tooltip="Start and finish"
                        ).add_to(preview_map)

                        st_folium(
                            preview_map,
                            width=None,
                            height=450,
                            returned_objects=[],
                            key=f"route_preview_{index}"
                        )

                gpx_data = route_to_gpx(
                    G=G,
                    route_path=route["path"],
                    route_name=(
                        f"Strida Route {index + 1} "
                        f"- {route['length_miles']:.2f} miles"
                    )
                )

                st.download_button(
                    label=(
                        f"Download {route_name} as GPX"
                    ),
                    data=gpx_data,
                    file_name=(
                        f"strida_route_{index + 1}_"
                        f"{route['length_miles']:.2f}_miles.gpx"
                    ),
                    mime="application/gpx+xml",
                    key=f"gpx_download_{index}",
                    use_container_width=True
                )

elif not generate_button:
    st.info(
        "Adjust the settings in the sidebar, "
        "then select Generate routes."
    )

    st.divider()

st.subheader("Share feedback")

st.write(
    "Tested a route? Tell me what worked and what needs improvement."
)

st.link_button(
    "Open feedback form",
    "https://forms.gle/1MNstx5uq9fuFFst9",
    use_container_width=True
)

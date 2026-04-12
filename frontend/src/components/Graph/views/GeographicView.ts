import * as d3 from "d3";
import { feature } from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import type { GraphNode, GraphEdge, ViewOptions, ViewCleanup, ViewRenderer } from "../types";

interface InstitutionLocation {
  id: string;
  name: string;
  lat: number;
  lng: number;
  paper_count: number;
  country: string;
}

const renderGeographicView: ViewRenderer = (svg, nodes, edges, options) => {
  const { width, height, onBackgroundClick } = options;
  const svgSel = d3.select(svg);
  svgSel.selectAll("*").remove();

  // Zoom
  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.5, 8])
    .on("zoom", (event) => container.attr("transform", event.transform));
  svgSel.call(zoom);
  svgSel.on("click", (event) => { if (event.target === svg) onBackgroundClick(); });

  const container = svgSel.append("g");

  // Projection
  const projection = d3.geoNaturalEarth1()
    .scale(width / 5.5)
    .translate([width / 2, height / 2]);

  const pathGen = d3.geoPath().projection(projection);

  // Load world topology asynchronously
  fetch("/data/world-110m.json")
    .then((res) => res.json())
    .then((topology: Topology) => {
      const countries = feature(topology, topology.objects.countries as GeometryCollection);

      // Draw country boundaries
      container.append("g")
        .selectAll("path")
        .data(countries.features)
        .join("path")
        .attr("d", pathGen as any)
        .attr("fill", "#161B22")
        .attr("stroke", "#2D3548")
        .attr("stroke-width", 0.5);

      // Graticule
      const graticule = d3.geoGraticule();
      container.append("path")
        .datum(graticule())
        .attr("d", pathGen as any)
        .attr("fill", "none")
        .attr("stroke", "#1C2333")
        .attr("stroke-width", 0.3);

      // Fetch geographic data
      import("@/lib/api").then(({ getGeographicData }) => {
        getGeographicData().then((data: { locations: InstitutionLocation[]; total: number }) => {
          if (data.locations.length === 0) {
            container.append("text")
              .attr("x", width / 2).attr("y", height / 2 + 30)
              .attr("text-anchor", "middle").attr("fill", "#8B949E").attr("font-size", "14px")
              .text("No geographic data available yet. Enrich institutions to see the map.");
            return;
          }

          // Scale for circles
          const maxPapers = Math.max(...data.locations.map((l) => l.paper_count), 1);
          const radiusScale = d3.scaleSqrt().domain([0, maxPapers]).range([3, 20]);

          // Draw institution pins
          const pins = container.append("g")
            .selectAll("circle")
            .data(data.locations)
            .join("circle")
            .attr("cx", (d) => projection([d.lng, d.lat])?.[0] || 0)
            .attr("cy", (d) => projection([d.lng, d.lat])?.[1] || 0)
            .attr("r", (d) => radiusScale(d.paper_count))
            .attr("fill", "#E8B931")
            .attr("fill-opacity", 0.6)
            .attr("stroke", "#E8B931")
            .attr("stroke-width", 1)
            .attr("cursor", "pointer");

          // Labels
          container.append("g")
            .selectAll("text")
            .data(data.locations.filter((l) => l.paper_count > maxPapers * 0.3))
            .join("text")
            .attr("x", (d) => (projection([d.lng, d.lat])?.[0] || 0) + radiusScale(d.paper_count) + 4)
            .attr("y", (d) => (projection([d.lng, d.lat])?.[1] || 0) + 4)
            .attr("fill", "#8B949E")
            .attr("font-size", "9px")
            .text((d) => d.name);

          // Tooltip on hover
          pins
            .on("mouseenter", function (event, d) {
              d3.select(this).attr("fill-opacity", 1).attr("stroke-width", 2);
              container.append("text")
                .attr("class", "geo-tooltip")
                .attr("x", projection([d.lng, d.lat])?.[0] || 0)
                .attr("y", (projection([d.lng, d.lat])?.[1] || 0) - radiusScale(d.paper_count) - 8)
                .attr("text-anchor", "middle")
                .attr("fill", "#E8B931")
                .attr("font-size", "11px")
                .attr("font-weight", "bold")
                .text(`${d.name} (${d.paper_count} papers)`);
            })
            .on("mouseleave", function () {
              d3.select(this).attr("fill-opacity", 0.6).attr("stroke-width", 1);
              container.selectAll(".geo-tooltip").remove();
            });
        });
      });
    })
    .catch((err) => {
      console.error("Failed to load world map:", err);
      container.append("text")
        .attr("x", width / 2).attr("y", height / 2)
        .attr("text-anchor", "middle").attr("fill", "#F85149")
        .text("Failed to load world map data.");
    });

  return { zoom };
};

export default renderGeographicView;

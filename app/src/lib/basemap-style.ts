/**
 * A deliberately restrained MapLibre style.
 *
 * We use OpenFreeMap's free planet tiles (openfreemap.org — public
 * community project, no API key, no rate limits for reasonable use)
 * as the vector source, then override the paint layers to a warm,
 * desaturated palette that matches the app's canvas. The result:
 * roads are visible but muted, water is a warm slate rather than
 * the usual saturated blue, labels are small and low-contrast.
 * The intent is that our risk overlay is the loudest thing on the
 * map, not the basemap.
 */

import type { StyleSpecification } from "maplibre-gl";
import { CANVAS, HAIRLINE, INK_SOFT, INK_MUTE } from "./theme";

// A slate-warm water colour and a muted teal land colour. Softer than
// the app canvas so the overlay stands out.
const BG_LAND  = "#F1E6CE";
const BG_WATER = "#C6C8C0";
const BG_ROAD  = "#E1D0AF";
const BG_PARK  = "#DFD3B7";

export function baseMapStyle(): StyleSpecification {
  return {
    version: 8,
    name: "FloodWarn — warm mono",
    glyphs:
      "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    sources: {
      openfreemap: {
        type: "vector",
        url: "https://tiles.openfreemap.org/planet",
      },
    },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": BG_LAND },
      },
      {
        id: "landcover-park",
        type: "fill",
        source: "openfreemap",
        "source-layer": "landcover",
        filter: ["==", "class", "grass"],
        paint: { "fill-color": BG_PARK, "fill-opacity": 0.7 },
      },
      {
        id: "water",
        type: "fill",
        source: "openfreemap",
        "source-layer": "water",
        paint: { "fill-color": BG_WATER },
      },
      {
        id: "roads",
        type: "line",
        source: "openfreemap",
        "source-layer": "transportation",
        filter: [
          "!in",
          "class",
          "path", "footway", "track", "cycleway", "steps",
        ],
        paint: {
          "line-color": BG_ROAD,
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            10, 0.4,
            14, 1.0,
            17, 3.0,
          ],
        },
      },
      {
        id: "road-outlines",
        type: "line",
        source: "openfreemap",
        "source-layer": "transportation",
        filter: ["in", "class", "motorway", "trunk", "primary"],
        paint: {
          "line-color": HAIRLINE,
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            10, 0.8,
            14, 2.2,
            17, 5.0,
          ],
        },
      },
      {
        id: "place-labels",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "place",
        filter: ["in", "class", "city", "town", "village", "suburb", "neighbourhood"],
        layout: {
          "text-field": ["get", "name:en"],
          "text-font": ["Noto Sans Regular"],
          "text-size": [
            "interpolate", ["linear"], ["zoom"],
            10, 10,
            14, 12,
            17, 14,
          ],
          "text-letter-spacing": 0.02,
        },
        paint: {
          "text-color": INK_SOFT,
          "text-halo-color": CANVAS,
          "text-halo-width": 1.2,
        },
      },
      {
        id: "road-labels",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "transportation_name",
        minzoom: 14,
        layout: {
          "text-field": ["get", "name:en"],
          "text-font": ["Noto Sans Regular"],
          "text-size": 10,
          "symbol-placement": "line",
        },
        paint: {
          "text-color": INK_MUTE,
          "text-halo-color": CANVAS,
          "text-halo-width": 1,
        },
      },
    ],
  };
}

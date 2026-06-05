"""Geo helpers (Haversine distance + nearest search)."""
from __future__ import annotations

import math
import sqlite3


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def nearest_by_coords(conn: sqlite3.Connection, lat: float, lon: float,
                     carburante: str = "Benzina", radius_km: float = 10.0,
                     limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT d.*, p.prezzo_self, p.prezzo_servito, p.data_comunicazione
        FROM distributori d
        LEFT JOIN prezzi p ON p.distributore_id = d.id AND p.carburante = ?
        AND p.id = (
            SELECT id FROM prezzi
            WHERE distributore_id = d.id AND carburante = ?
            ORDER BY data_comunicazione DESC LIMIT 1
        )
        WHERE d.latitudine IS NOT NULL AND d.longitudine IS NOT NULL""",
        (carburante, carburante),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        dist = haversine_km(lat, lon, d["latitudine"], d["longitudine"])
        if dist <= radius_km:
            d["distanza_km"] = round(dist, 2)
            out.append(d)
    out.sort(key=lambda x: (
        x["prezzo_self"] if x.get("prezzo_self") is not None else 9999.0,
        x["distanza_km"],
    ))
    return out[:limit]


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon

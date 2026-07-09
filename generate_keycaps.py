#!/usr/bin/env python3
"""Generate a reset parametric low-profile MX keycap.

This version intentionally starts from simple named dimensions instead of the
older ring-profile body. The cap body is a tapered square shell with a round
Cherry MX-compatible post and cross socket.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass, fields
from math import cos, pi, sin
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


@dataclass(frozen=True)
class KeycapParams:
    # Post controls.
    post_height: float = 1.0
    post_diameter: float = 5.6
    post_cross_size: float = 1.35

    # Keycap outer bottom square controls.
    base_width: float = 18.2
    base_length: float = 18.2
    base_x: float = 0.0
    base_y: float = 0.0
    base_corner_radius: float = 0.6

    # Keycap outer top square controls.
    top_width: float = 14.4
    top_length: float = 15.2
    top_x: float = 0.0
    top_y: float = -0.8
    top_corner_radius: float = 3.0
    top_concave_depth: float = 0.5
    top_concave_axis: str = "x"

    # Shell controls.
    sidewall_thickness: float = 1.25
    top_thickness: float = 1.5
    keycap_height: float = 5.0

    # Mesh quality controls.
    surface_resolution: int = 96
    post_sections: int = 256


@dataclass(frozen=True)
class OutputFiles:
    cap_stl: str = "keycap.stl"
    image_png: str = "keycap.png"
    notes: str = "README.md"


PARAMS = KeycapParams()
OUT_DIR = Path(__file__).resolve().parent
CONFIG_SECTION = "keycap"
OUTPUT_SECTION = "output"


def read_config(config_path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    read_files = parser.read(config_path, encoding="utf-8")
    if not read_files:
        raise FileNotFoundError(f"could not read config file: {config_path}")
    return parser


def load_params(config_path: Path | None) -> KeycapParams:
    params = KeycapParams()
    if config_path is None:
        return params

    parser = read_config(config_path)
    if CONFIG_SECTION not in parser:
        raise ValueError(f"config file must contain a [{CONFIG_SECTION}] section")

    section = parser[CONFIG_SECTION]
    values: dict[str, float | int | str] = {}
    for field in fields(KeycapParams):
        if field.name not in section:
            continue
        current_value = getattr(params, field.name)
        if isinstance(current_value, int):
            values[field.name] = section.getint(field.name)
        elif isinstance(current_value, float):
            values[field.name] = section.getfloat(field.name)
        elif isinstance(current_value, str):
            values[field.name] = section.get(field.name).strip()
        else:
            raise TypeError(f"unsupported parameter type for {field.name}")

    return KeycapParams(**{**params.__dict__, **values})


def load_output_files(config_path: Path | None) -> OutputFiles:
    if config_path is None:
        return OutputFiles()

    output = OutputFiles(
        cap_stl=f"{config_path.stem}.stl",
        image_png=f"{config_path.stem}.png",
    )
    parser = read_config(config_path)
    if OUTPUT_SECTION not in parser:
        return output

    section = parser[OUTPUT_SECTION]
    values: dict[str, str] = {}
    for field in fields(OutputFiles):
        if field.name in section:
            values[field.name] = Path(section.get(field.name).strip()).name
    return OutputFiles(**{**output.__dict__, **values})


def box(size: tuple[float, float, float], center: tuple[float, float, float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=size)
    mesh.apply_translation(center)
    return mesh


def cylinder(radius: float, height: float, center_z: float, sections: int) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    mesh.apply_translation((0, 0, center_z))
    return mesh


def profile_points(
    width: float,
    length: float,
    x: float,
    y: float,
    z: float,
    corner_radius: float,
    corner_segments: int = 10,
) -> list[tuple[float, float, float]]:
    hw = width / 2
    hl = length / 2
    radius = max(0.0, min(corner_radius, hw - 0.01, hl - 0.01))
    if radius <= 0.0:
        return [
            (x - hw, y - hl, z),
            (x + hw, y - hl, z),
            (x + hw, y + hl, z),
            (x - hw, y + hl, z),
        ]

    centers = [
        (x + hw - radius, y - hl + radius, -pi / 2, 0.0),
        (x + hw - radius, y + hl - radius, 0.0, pi / 2),
        (x - hw + radius, y + hl - radius, pi / 2, pi),
        (x - hw + radius, y - hl + radius, pi, 3 * pi / 2),
    ]
    points: list[tuple[float, float, float]] = []
    for cx, cy, start, end in centers:
        for step in range(corner_segments + 1):
            angle = start + (end - start) * step / corner_segments
            points.append((cx + radius * cos(angle), cy + radius * sin(angle), z))
    return points


def frustum(
    bottom_width: float,
    bottom_length: float,
    bottom_x: float,
    bottom_y: float,
    bottom_z: float,
    bottom_radius: float,
    top_width: float,
    top_length: float,
    top_x: float,
    top_y: float,
    top_z: float,
    top_radius: float,
    top_concave_depth: float = 0.0,
    top_concave_axis: str = "y",
    surface_resolution: int = 48,
) -> trimesh.Trimesh:
    rows = surface_resolution
    cols = surface_resolution

    def half_width_at(width: float, length: float, radius: float, local_y: float) -> float:
        hw = width / 2
        hl = length / 2
        radius = max(0.0, min(radius, hw - 0.01, hl - 0.01))
        ay = abs(local_y)
        straight_y = hl - radius
        if radius <= 0.0 or ay <= straight_y:
            return hw
        dy = min(radius, ay - straight_y)
        return hw - radius + (radius * radius - dy * dy) ** 0.5

    def concave_z(local_x: float, local_y: float) -> float:
        if top_concave_axis == "x":
            t = (local_x + top_width / 2) / top_width
        else:
            t = (local_y + top_length / 2) / top_length
        return top_z - top_concave_depth * sin(pi * max(0.0, min(1.0, t)))

    verts: list[tuple[float, float, float]] = []
    top_index: list[list[int]] = []
    for row in range(rows + 1):
        row_indices: list[int] = []
        y_frac = row / rows
        y_local = -top_length / 2 + y_frac * top_length
        half_width = half_width_at(top_width, top_length, top_radius, y_local)
        for col in range(cols + 1):
            x_frac = col / cols
            x_coord = top_x - half_width + x_frac * half_width * 2
            x_local = x_coord - top_x
            z = concave_z(x_local, y_local)
            row_indices.append(len(verts))
            verts.append((x_coord, top_y + y_local, z))
        top_index.append(row_indices)

    faces: list[tuple[int, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            p00 = top_index[row][col]
            p01 = top_index[row][col + 1]
            p10 = top_index[row + 1][col]
            p11 = top_index[row + 1][col + 1]
            faces.append((p00, p01, p11))
            faces.append((p00, p11, p10))

    loop: list[tuple[int, int]] = []
    loop.extend((0, col) for col in range(cols + 1))
    loop.extend((row, cols) for row in range(1, rows + 1))
    loop.extend((rows, col) for col in range(cols - 1, -1, -1))
    loop.extend((row, 0) for row in range(rows - 1, 0, -1))

    top_loop = [top_index[row][col] for row, col in loop]
    base_loop: list[int] = []
    for row, col in loop:
        y_frac = row / rows
        x_frac = col / cols
        y_local = -bottom_length / 2 + y_frac * bottom_length
        half_width = half_width_at(bottom_width, bottom_length, bottom_radius, y_local)
        x_coord = bottom_x - half_width + x_frac * half_width * 2
        base_loop.append(len(verts))
        verts.append((x_coord, bottom_y + y_local, bottom_z))

    n = len(base_loop)
    for i in range(n):
        j = (i + 1) % n
        faces.append((base_loop[i], base_loop[j], top_loop[j]))
        faces.append((base_loop[i], top_loop[j], top_loop[i]))

    center_bottom = len(verts)
    verts.append((bottom_x, bottom_y, bottom_z))
    for i in range(n):
        j = (i + 1) % n
        faces.append((center_bottom, base_loop[j], base_loop[i]))

    return trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=False)


def union(parts: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return trimesh.boolean.union(parts, engine="manifold")


def difference(base: trimesh.Trimesh, cutters: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return trimesh.boolean.difference([base, *cutters], engine="manifold")


def validate_params(p: KeycapParams) -> None:
    if p.sidewall_thickness <= 0 or p.top_thickness <= 0:
        raise ValueError("sidewall_thickness and top_thickness must be positive")
    if p.keycap_height <= p.top_thickness:
        raise ValueError("keycap_height must be greater than top_thickness")
    if min(p.base_width, p.base_length, p.top_width, p.top_length) <= p.sidewall_thickness * 2:
        raise ValueError("base/top dimensions must be wider than two sidewalls")
    if p.post_diameter <= p.post_cross_size:
        raise ValueError("post_diameter must be larger than post_cross_size")
    if p.base_corner_radius < 0 or p.top_corner_radius < 0:
        raise ValueError("corner radii must be zero or positive")
    if p.top_concave_depth < 0:
        raise ValueError("top_concave_depth must be zero or positive")
    if p.top_concave_axis not in {"x", "y"}:
        raise ValueError("top_concave_axis must be 'x' or 'y'")
    if p.surface_resolution < 24:
        raise ValueError("surface_resolution must be 24 or greater")
    if p.post_sections < 64:
        raise ValueError("post_sections must be 64 or greater")


def make_body_shell(p: KeycapParams) -> trimesh.Trimesh:
    outer = frustum(
        p.base_width,
        p.base_length,
        p.base_x,
        p.base_y,
        0.0,
        p.base_corner_radius,
        p.top_width,
        p.top_length,
        p.top_x,
        p.top_y,
        p.keycap_height,
        p.top_corner_radius,
        p.top_concave_depth,
        p.top_concave_axis,
        p.surface_resolution,
    )

    cavity_top_z = p.keycap_height - p.top_thickness
    inner_base_radius = max(0.01, p.base_corner_radius - p.sidewall_thickness)
    inner_top_radius = max(0.01, p.top_corner_radius - p.sidewall_thickness)
    inner = frustum(
        p.base_width - 2 * p.sidewall_thickness,
        p.base_length - 2 * p.sidewall_thickness,
        p.base_x,
        p.base_y,
        -0.05,
        inner_base_radius,
        max(0.1, p.top_width - 2 * p.sidewall_thickness),
        max(0.1, p.top_length - 2 * p.sidewall_thickness),
        p.top_x,
        p.top_y,
        cavity_top_z,
        inner_top_radius,
        0.0,
        p.top_concave_axis,
        p.surface_resolution,
    )
    return difference(outer, [inner])


def make_cross_cutters(p: KeycapParams, z_min: float, z_max: float) -> list[trimesh.Trimesh]:
    height = z_max - z_min
    center_z = z_min + height / 2
    cross_length = min(p.post_diameter - 0.55, p.post_diameter * 0.74)
    vertical = box((p.post_cross_size, cross_length, height), (0, 0, center_z))
    horizontal = box((cross_length, p.post_cross_size, height), (0, 0, center_z))
    return [vertical, horizontal]


def make_cap(p: KeycapParams) -> trimesh.Trimesh:
    validate_params(p)
    body = make_body_shell(p)

    post_radius = p.post_diameter / 2
    post_top_z = max(
        p.top_thickness,
        p.keycap_height - p.top_thickness + 0.25,
    )
    post = cylinder(post_radius, p.post_height + post_top_z, (-p.post_height + post_top_z) / 2, p.post_sections)
    solid = union([body, post])

    cap = difference(solid, make_cross_cutters(p, -p.post_height - 0.2, post_top_z - 0.35))
    cap.apply_translation((0, 0, p.post_height))
    cap.merge_vertices()
    return cap


def draw_mesh(ax, mesh: trimesh.Trimesh, title: str, elev: float, azim: float) -> None:
    tris = mesh.vertices[mesh.faces]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    light = np.array([0.25, -0.45, 0.86])
    light /= np.linalg.norm(light)
    shade = np.clip(0.56 + 0.44 * (normals @ light), 0.30, 1.0)
    base = np.array([0.76, 0.79, 0.84])
    colors = np.c_[base[None, :] * shade[:, None], np.ones(len(shade))]
    poly = Poly3DCollection(tris, linewidths=0.035, edgecolors=(0.08, 0.08, 0.08, 0.07))
    poly.set_facecolor(colors)
    ax.add_collection3d(poly)
    bounds = mesh.bounds
    center = bounds.mean(axis=0)
    radius = (bounds[1] - bounds[0]).max() / 2
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius * 0.25, center[2] + radius * 1.05)
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(title, fontsize=10)
    ax.set_axis_off()


def render_preview(mesh: trimesh.Trimesh, out_path: Path) -> None:
    fig = plt.figure(figsize=(12, 4.8), dpi=160)
    ax1 = fig.add_subplot(1, 3, 1, projection="3d")
    ax2 = fig.add_subplot(1, 3, 2, projection="3d")
    ax3 = fig.add_subplot(1, 3, 3, projection="3d")
    draw_mesh(ax1, mesh, "top/body", 28, -48)
    draw_mesh(ax2, mesh, "side taper", 14, -90)
    draw_mesh(ax3, mesh, "round MX post", -68, -45)
    fig.suptitle("RCON parametric square low-profile keycap", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def render_single_view(mesh: trimesh.Trimesh, title: str, elev: float, azim: float, out_path: Path) -> None:
    fig = plt.figure(figsize=(5.2, 5.2), dpi=180)
    ax = fig.add_subplot(1, 1, 1, projection="3d")
    draw_mesh(ax, mesh, title, elev, azim)
    fig.suptitle(f"RCON parametric square keycap - {title}", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def render_views(mesh: trimesh.Trimesh, out_dir: Path) -> None:
    views = [
        ("top", 90, -90),
        ("front", 0, -90),
        ("side", 0, 0),
        ("angled", 28, -48),
    ]
    for name, elev, azim in views:
        render_single_view(mesh, name, elev, azim, out_dir / f"parametric_square_{name}.png")


def draw_cad_mesh(ax, mesh: trimesh.Trimesh, title: str, elev: float, azim: float) -> None:
    tris = mesh.vertices[mesh.faces]
    poly = Poly3DCollection(
        tris,
        linewidths=0.18,
        edgecolors=(0.05, 0.05, 0.05, 0.04),
        facecolors=(0.78, 0.81, 0.86, 1.0),
    )
    ax.add_collection3d(poly)
    bounds = mesh.bounds
    center = bounds.mean(axis=0)
    radius = (bounds[1] - bounds[0]).max() / 2
    pad = radius * 0.16
    ax.set_xlim(center[0] - radius - pad, center[0] + radius + pad)
    ax.set_ylim(center[1] - radius - pad, center[1] + radius + pad)
    ax.set_zlim(center[2] - radius * 0.35 - pad, center[2] + radius * 1.05 + pad)
    ax.set_proj_type("ortho")
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_axis_off()


def render_cad_sheet(mesh: trimesh.Trimesh, out_path: Path) -> None:
    views = [
        ("TOP", 90, -90),
        ("FRONT", 0, -90),
        ("SIDE", 0, 0),
        ("ANGLED ORTHO", 35.264, -45),
    ]
    fig = plt.figure(figsize=(10, 10), dpi=180)
    for index, (title, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(2, 2, index, projection="3d")
        draw_cad_mesh(ax, mesh, title, elev, azim)
    fig.suptitle("RCON PARAMETRIC SQUARE KEYCAP - ORTHOGRAPHIC 4 VIEW", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def write_notes(path: Path, p: KeycapParams, output: OutputFiles, config_path: Path | None = None) -> None:
    files = [
        f"- {output.cap_stl}",
        f"- {output.notes}",
    ]
    if config_path is not None:
        files.append(f"- {config_path.name}")

    path.write_text(
        "\n".join(
            [
                "# Parametric Square Keycap",
                "",
                "This is a configured parametric MX keycap generated from a conf file.",
                "",
                "Variables:",
                f"- post_height: {p.post_height}",
                f"- post_diameter: {p.post_diameter}",
                f"- post_cross_size: {p.post_cross_size}",
                f"- base_width/base_length/base_x/base_y: {p.base_width}, {p.base_length}, {p.base_x}, {p.base_y}",
                f"- base_corner_radius: {p.base_corner_radius}",
                f"- top_width/top_length/top_x/top_y: {p.top_width}, {p.top_length}, {p.top_x}, {p.top_y}",
                f"- top_corner_radius: {p.top_corner_radius}",
                f"- top_concave_depth: {p.top_concave_depth}",
                f"- top_concave_axis: {p.top_concave_axis}",
                f"- sidewall_thickness: {p.sidewall_thickness}",
                f"- top_thickness: {p.top_thickness}",
                f"- keycap_height: {p.keycap_height}",
                f"- surface_resolution: {p.surface_resolution}",
                f"- post_sections: {p.post_sections}",
                "",
                "Files:",
                *files,
                "",
                "Generated preview images are temporary send artifacts and should be deleted after delivery.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the parametric square MX keycap.")
    parser.add_argument(
        "config",
        nargs="?",
        help="Optional INI config file with a [keycap] section, for example jwa.conf.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve() if args.config else None
    params = load_params(config_path)
    output = load_output_files(config_path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cap = make_cap(params)
    cap.export(OUT_DIR / output.cap_stl)
    render_cad_sheet(cap, OUT_DIR / output.image_png)
    print(OUT_DIR)
    if config_path is not None:
        print(f"config: {config_path}")
    print(f"cap stl: {OUT_DIR / output.cap_stl}")
    print(f"image png: {OUT_DIR / output.image_png}")
    print(f"cap watertight: {cap.is_watertight}")


if __name__ == "__main__":
    main()

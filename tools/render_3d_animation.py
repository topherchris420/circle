"""Render a high-fidelity 3D animated turntable GIF of the CIRCLE Rev B board + Resonance Chamber."""

from pathlib import Path
import math
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "diagrams"
OUT_GIF = OUT_DIR / "circle-3d-animation.gif"

WIDTH = 900
HEIGHT = 540
PHI = (1.0 + math.sqrt(5.0)) / 2.0


class Camera3D:
    def __init__(self, fov=44.0, distance=260.0, center=(65.0, 27.5, 5.0)):
        self.fov = fov
        self.distance = distance
        self.center = np.array(center, dtype=np.float64)

    def project(self, points, rot_x_deg, rot_y_deg, rot_z_deg=0.0):
        pts = points - self.center
        rx = math.radians(rot_x_deg)
        ry = math.radians(rot_y_deg)
        rz = math.radians(rot_z_deg)

        cy, sy = math.cos(ry), math.sin(ry)
        R_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])

        cx, sx = math.cos(rx), math.sin(rx)
        R_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])

        cz, sz = math.cos(rz), math.sin(rz)
        R_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])

        R = R_x @ R_y @ R_z
        rotated = (R @ pts.T).T

        cam_z = rotated[:, 2] + self.distance
        f = (WIDTH / 2.0) / math.tan(math.radians(self.fov / 2.0))

        screen_x = (rotated[:, 0] * f / cam_z) + (WIDTH / 2.0)
        screen_y = (rotated[:, 1] * f / cam_z) + (HEIGHT / 2.0)
        depth = cam_z

        return screen_x, screen_y, depth, rotated


def create_box(x, y, z, dx, dy, dz, color, name="box"):
    verts = np.array([
        [x, y, z],
        [x + dx, y, z],
        [x + dx, y + dy, z],
        [x, y + dy, z],
        [x, y, z + dz],
        [x + dx, y, z + dz],
        [x + dx, y + dy, z + dz],
        [x, y + dy, z + dz],
    ], dtype=np.float64)

    faces = [
        ([0, 1, 2, 3], np.array([0, 0, -1.0]), color, name),
        ([4, 7, 6, 5], np.array([0, 0, 1.0]), color, name),
        ([0, 4, 5, 1], np.array([0, -1.0, 0]), color, name),
        ([2, 6, 7, 3], np.array([0, 1.0, 0]), color, name),
        ([0, 3, 7, 4], np.array([-1.0, 0, 0]), color, name),
        ([1, 5, 6, 2], np.array([1.0, 0, 0]), color, name),
    ]
    return verts, faces


def create_cylinder(cx, cy, z, r, h, sides=16, color=(180, 180, 190), name="cylinder"):
    verts = []
    for i in range(sides):
        ang = 2 * math.pi * i / sides
        verts.append([cx + r * math.cos(ang), cy + r * math.sin(ang), z])
    for i in range(sides):
        ang = 2 * math.pi * i / sides
        verts.append([cx + r * math.cos(ang), cy + r * math.sin(ang), z + h])

    verts = np.array(verts, dtype=np.float64)
    faces = []
    for i in range(sides):
        nxt = (i + 1) % sides
        mid_ang = 2 * math.pi * (i + 0.5) / sides
        normal = np.array([math.cos(mid_ang), math.sin(mid_ang), 0.0])
        faces.append(([i, nxt, nxt + sides, i + sides], normal, color, name))

    top_indices = list(range(sides, 2 * sides))
    faces.append((top_indices, np.array([0, 0, 1.0]), color, name))

    return verts, faces


def create_sphere_rings(cx, cy, cz, radius, color, name="sphere_ring"):
    """Create lightweight orbital rings representing a resonant spherical cavity."""
    verts = []
    faces = []
    sides = 24
    w = 0.8
    # XY ring
    for i in range(sides):
        a1 = 2 * math.pi * i / sides
        verts.append([cx + radius * math.cos(a1), cy + radius * math.sin(a1), cz - w/2])
        verts.append([cx + radius * math.cos(a1), cy + radius * math.sin(a1), cz + w/2])
    # XZ ring
    for i in range(sides):
        a1 = 2 * math.pi * i / sides
        verts.append([cx + radius * math.cos(a1), cy - w/2, cz + radius * math.sin(a1)])
        verts.append([cx + radius * math.cos(a1), cy + w/2, cz + radius * math.sin(a1)])

    verts = np.array(verts, dtype=np.float64)
    for i in range(0, len(verts) - 2, 2):
        faces.append(([i, i + 1, i + 3, i + 2], np.array([0, 0, 1.0]), color, name))

    return verts, faces


def create_merkaba(cx, cy, cz, s=8.0):
    """Create central dual-interpenetrating tetrahedron (Merkaba)."""
    # Tetra 1 (upward)
    v_up = np.array([
        [cx, cy, cz + s],
        [cx + s * math.sqrt(8/9), cy, cz - s/3],
        [cx - s * math.sqrt(2/9), cy + s * math.sqrt(2/3), cz - s/3],
        [cx - s * math.sqrt(2/9), cy - s * math.sqrt(2/3), cz - s/3],
    ], dtype=np.float64)

    # Tetra 2 (downward)
    v_down = np.array([
        [cx, cy, cz - s],
        [cx - s * math.sqrt(8/9), cy, cz + s/3],
        [cx + s * math.sqrt(2/9), cy - s * math.sqrt(2/3), cz + s/3],
        [cx + s * math.sqrt(2/9), cy + s * math.sqrt(2/3), cz + s/3],
    ], dtype=np.float64)

    verts = np.vstack([v_up, v_down])

    gold_up = (245, 195, 65)
    cyan_down = (60, 200, 240)

    def calc_normal(p0, p1, p2):
        v1 = p1 - p0
        v2 = p2 - p0
        n = np.cross(v1, v2)
        norm = np.linalg.norm(n)
        return n / norm if norm > 1e-6 else np.array([0, 0, 1.0])

    faces = [
        # Upward faces
        ([0, 1, 2], calc_normal(v_up[0], v_up[1], v_up[2]), gold_up, "tetra_up_1"),
        ([0, 2, 3], calc_normal(v_up[0], v_up[2], v_up[3]), gold_up, "tetra_up_2"),
        ([0, 3, 1], calc_normal(v_up[0], v_up[3], v_up[1]), gold_up, "tetra_up_3"),
        ([1, 3, 2], calc_normal(v_up[1], v_up[3], v_up[2]), gold_up, "tetra_up_bot"),
        # Downward faces (indices offset by 4)
        ([4, 6, 5], calc_normal(v_down[0], v_down[2], v_down[1]), cyan_down, "tetra_down_1"),
        ([4, 7, 6], calc_normal(v_down[0], v_down[3], v_down[2]), cyan_down, "tetra_down_2"),
        ([4, 5, 7], calc_normal(v_down[0], v_down[1], v_down[3]), cyan_down, "tetra_down_3"),
        ([5, 6, 7], calc_normal(v_down[1], v_down[2], v_down[3]), cyan_down, "tetra_down_top"),
    ]
    return verts, faces


def build_scene():
    all_verts = []
    all_faces = []

    def add_mesh(verts, faces):
        offset = len(all_verts)
        for v in verts:
            all_verts.append(v)
        for face_indices, norm, col, name in faces:
            shifted = [idx + offset for idx in face_indices]
            all_faces.append((shifted, norm, col, name))

    # 1. Main PCB Board: 85 x 55 x 1.6 mm
    pcb_color = (30, 42, 38)
    v, f = create_box(0, 0, -1.6, 67.5, 55.0, 1.6, pcb_color, "pcb_human")
    add_mesh(v, f)
    v, f = create_box(74.5, 0, -1.6, 10.5, 55.0, 1.6, pcb_color, "pcb_iso")
    add_mesh(v, f)
    v, f = create_box(67.5, 0, -1.6, 7.0, 4.0, 1.6, pcb_color, "pcb_bridge_top")
    add_mesh(v, f)
    v, f = create_box(67.5, 51.0, -1.6, 7.0, 4.0, 1.6, pcb_color, "pcb_bridge_bot")
    add_mesh(v, f)

    enig_gold = (212, 175, 55)

    # ESP32-S3 module
    v, f = create_box(37.0, 11.25, 0.0, 18.0, 20.0, 3.0, (205, 210, 215), "esp32_shield")
    add_mesh(v, f)
    v, f = create_box(37.0, 31.25, 0.0, 18.0, 5.5, 1.0, (18, 28, 22), "esp32_antenna")
    add_mesh(v, f)
    v, f = create_box(39.0, 32.5, 1.0, 14.0, 3.0, 0.1, enig_gold, "esp32_trace")
    add_mesh(v, f)

    # Dual BNC Connectors on isolated domain: (80, 14) and (80, 41)
    v, f = create_box(76.0, 8.0, 0.0, 8.0, 12.0, 11.0, (190, 195, 200), "bnc_in_body")
    add_mesh(v, f)
    v, f = create_cylinder(85.0, 14.0, 4.0, 4.8, 12.0, sides=16, color=(220, 225, 230), name="bnc_in_barrel")
    add_mesh(v, f)
    v, f = create_box(76.0, 35.0, 0.0, 8.0, 12.0, 11.0, (190, 195, 200), "bnc_out_body")
    add_mesh(v, f)
    v, f = create_cylinder(85.0, 41.0, 4.0, 4.8, 12.0, sides=16, color=(220, 225, 230), name="bnc_out_barrel")
    add_mesh(v, f)

    # TI ISOW7742 Isolator
    v, f = create_box(65.5, 22.5, 0.0, 11.0, 10.0, 2.4, (20, 20, 22), "isow7742_ic")
    add_mesh(v, f)
    for py in [23.5, 25.5, 27.5, 29.5, 31.5]:
        v, f = create_box(63.5, py, 0.0, 2.0, 0.8, 0.5, enig_gold, "pin_left")
        add_mesh(v, f)
        v, f = create_box(76.5, py, 0.0, 2.0, 0.8, 0.5, enig_gold, "pin_right")
        add_mesh(v, f)

    # USB-C & Connectors
    v, f = create_box(0.0, 23.0, 0.0, 8.5, 9.0, 3.2, (215, 220, 225), "usb_c")
    add_mesh(v, f)
    v, f = create_box(8.0, 3.0, 0.0, 8.0, 7.5, 6.0, (240, 240, 235), "jst_bat")
    add_mesh(v, f)
    v, f = create_box(1.0, 36.0, 0.0, 14.0, 13.0, 1.8, (195, 195, 205), "sd_slot")
    add_mesh(v, f)

    # 2. circle-ppg daughterboard
    ppg_x, ppg_y, ppg_z = 25.0, -18.0, 6.0
    v, f = create_box(ppg_x, ppg_y, ppg_z, 25.0, 18.0, 1.6, (32, 45, 40), "pcb_ppg")
    add_mesh(v, f)
    v, f = create_box(ppg_x + 9.5, ppg_y + 6.0, ppg_z + 1.6, 6.0, 4.0, 1.2, (20, 20, 22), "max30102")
    add_mesh(v, f)
    v, f = create_box(ppg_x + 10.5, ppg_y + 7.0, ppg_z + 2.8, 1.8, 1.8, 0.2, (220, 20, 50), "opt_red_led")
    add_mesh(v, f)
    v, f = create_box(ppg_x + 13.0, ppg_y + 7.0, ppg_z + 2.8, 1.8, 1.8, 0.2, (50, 20, 70), "opt_ir_sensor")
    add_mesh(v, f)
    v, f = create_box(ppg_x + 7.5, ppg_y + 13.0, ppg_z + 1.6, 10.0, 4.0, 3.5, (240, 240, 235), "jst_gh_ppg")
    add_mesh(v, f)

    # 3. EXTERNAL RESONANCE CHAMBER (Right side of bench)
    # Positioned at (140, 27.5, 12)
    ch_x, ch_y, ch_z = 142.0, 27.5, 12.0
    r_outer = 32.0
    r_middle = r_outer / PHI         # ~19.78 mm
    r_inner = r_middle / PHI         # ~12.22 mm

    # Outer Spherical Resonator (Copper/Bronze ring structure)
    v, f = create_sphere_rings(ch_x, ch_y, ch_z, r_outer, (190, 115, 60), "res_outer_sphere")
    add_mesh(v, f)

    # Middle Spherical Resonator (Golden brass structure)
    v, f = create_sphere_rings(ch_x, ch_y, ch_z, r_middle, (215, 175, 45), "res_mid_sphere")
    add_mesh(v, f)

    # Inner Spherical Resonator (Silver/Platinum structure)
    v, f = create_sphere_rings(ch_x, ch_y, ch_z, r_inner, (175, 185, 200), "res_inner_sphere")
    add_mesh(v, f)

    # Central Dual Tetrahedron (Merkaba)
    v, f = create_merkaba(ch_x, ch_y, ch_z, s=7.5)
    add_mesh(v, f)

    # Chamber Base Pedestal
    v, f = create_cylinder(ch_x, ch_y, -1.6, 22.0, 3.0, sides=20, color=(45, 50, 60), name="res_pedestal")
    add_mesh(v, f)

    # Coaxial Isolated Sync Cable connecting BNC (85, 14, 4) to Resonance Base
    v, f = create_cylinder(ch_x - 30.0, ch_y - 8.0, 0.0, 1.2, 4.0, sides=8, color=(40, 40, 45), name="sync_cable")
    add_mesh(v, f)

    return np.array(all_verts), all_faces


def render_frame(verts, faces, rot_y_deg, pitch_deg=26.0, cam_dist=265.0):
    cam = Camera3D(fov=44.0, distance=cam_dist, center=(65.0, 27.5, 6.0))
    sx, sy, depth, rot_pts = cam.project(verts, pitch_deg, rot_y_deg)

    light_dir = np.array([-0.35, -0.65, 0.68])
    light_dir = light_dir / np.linalg.norm(light_dir)

    face_render_data = []

    rx = math.radians(pitch_deg)
    ry = math.radians(rot_y_deg)
    R_y = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    R_x = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    R = R_x @ R_y

    for face_indices, norm, base_color, name in faces:
        rot_norm = R @ norm
        avg_depth = float(np.mean(depth[face_indices]))
        view_dot = float(rot_norm[2])

        diffuse = max(0.0, float(np.dot(rot_norm, light_dir)))
        ambient = 0.38
        specular = 0.0
        if diffuse > 0:
            halfway = (light_dir + np.array([0, 0, 1.0])) / np.linalg.norm(light_dir + np.array([0, 0, 1.0]))
            specular = max(0.0, float(np.dot(rot_norm, halfway))) ** 18

        intensity = ambient + 0.62 * diffuse
        shaded_r = min(255, int(base_color[0] * intensity + specular * 65))
        shaded_g = min(255, int(base_color[1] * intensity + specular * 65))
        shaded_b = min(255, int(base_color[2] * intensity + specular * 65))

        poly_2d = [(sx[i], sy[i]) for i in face_indices]
        face_render_data.append((avg_depth, view_dot, poly_2d, (shaded_r, shaded_g, shaded_b), name))

    face_render_data.sort(key=lambda item: item[0], reverse=True)

    img = Image.new("RGBA", (WIDTH, HEIGHT), (14, 17, 23, 255))
    draw = ImageDraw.Draw(img)

    # Workbench ambient glow
    draw.ellipse([WIDTH/2 - 380, HEIGHT/2 - 110, WIDTH/2 + 380, HEIGHT/2 + 180], fill=(22, 28, 36, 255))
    draw.ellipse([WIDTH/2 - 270, HEIGHT/2 - 70, WIDTH/2 + 270, HEIGHT/2 + 130], fill=(30, 38, 48, 255))

    for avg_depth, view_dot, poly, color, name in face_render_data:
        if view_dot > -0.2 or len(poly) > 4 or "sphere" in name or "tetra" in name:
            draw.polygon(poly, fill=color, outline=(min(255, color[0] + 25), min(255, color[1] + 25), min(255, color[2] + 25)))

    # Title & Module Badges
    draw.text((25, 20), "CIRCLE Rev B + Resonance Research Module", fill=(255, 255, 255))
    draw.text((25, 42), "Synchronized Biosensing · Isolated Sync · Phi-Resonant Chamber & Merkaba", fill=(140, 160, 180))

    # Legend Badges (Bottom)
    draw.rectangle([25, HEIGHT - 45, 170, HEIGHT - 20], fill=(20, 50, 35, 220), outline=(50, 180, 100))
    draw.text((35, HEIGHT - 38), "● BAT_HUMAN (Isolated)", fill=(100, 230, 140))

    draw.rectangle([180, HEIGHT - 45, 310, HEIGHT - 20], fill=(25, 45, 75, 220), outline=(70, 140, 240))
    draw.text((190, HEIGHT - 38), "● LAB_ISO (5 kVrms)", fill=(120, 180, 255))

    draw.rectangle([320, HEIGHT - 45, 520, HEIGHT - 20], fill=(55, 35, 65, 220), outline=(190, 100, 240))
    draw.text((330, HEIGHT - 38), "● 3-Sphere Phi Chamber", fill=(220, 150, 255))

    draw.rectangle([530, HEIGHT - 45, 710, HEIGHT - 20], fill=(60, 45, 20, 220), outline=(240, 180, 50))
    draw.text((540, HEIGHT - 38), "● Merkaba Dual-Tetra Core", fill=(255, 210, 80))

    # Warning badge
    draw.rectangle([WIDTH - 285, 20, WIDTH - 25, 45], fill=(50, 20, 20, 220), outline=(220, 60, 60))
    draw.text((WIDTH - 275, 26), "ENGINEERING REVIEW ONLY", fill=(255, 120, 120))

    return img.convert("RGB")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    verts, faces = build_scene()
    print(f"Built 3D scene with {len(verts)} vertices and {len(faces)} faces.")

    num_frames = 48
    frames = []
    print(f"Rendering {num_frames} turntable frames...")

    for i in range(num_frames):
        angle = (360.0 / num_frames) * i - 25.0
        pitch = 26.0 + 3.5 * math.sin(math.radians(angle * 2))
        frame = render_frame(verts, faces, angle, pitch_deg=pitch)
        frames.append(frame)
        if (i + 1) % 12 == 0:
            print(f"  rendered frame {i + 1}/{num_frames}")

    frames[0].save(
        OUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
        optimize=True,
    )
    print(f"Saved 3D animation to {OUT_GIF} ({OUT_GIF.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()

"""Render a 3D animated turntable GIF of the CIRCLE Rev B board assembly."""

from pathlib import Path
import math
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "diagrams"
OUT_GIF = OUT_DIR / "circle-3d-animation.gif"

WIDTH = 800
HEIGHT = 500

class Camera3D:
    def __init__(self, fov=45.0, distance=180.0, center=(42.5, 27.5, 0.0)):
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
        ([0, 1, 2, 3], np.array([0, 0, -1]), color, name),
        ([4, 7, 6, 5], np.array([0, 0, 1]), color, name),
        ([0, 4, 5, 1], np.array([0, -1, 0]), color, name),
        ([2, 6, 7, 3], np.array([0, 1, 0]), color, name),
        ([0, 3, 7, 4], np.array([-1, 0, 0]), color, name),
        ([1, 5, 6, 2], np.array([1, 0, 0]), color, name),
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
            
    # 1. Main PCB Board: 85 x 55 x 1.6 mm (Split by 8.0mm slot)
    pcb_color = (30, 42, 38)
    
    # Left PCB section (Human domain): X=0 to 67.5
    v, f = create_box(0, 0, -1.6, 67.5, 55.0, 1.6, pcb_color, "pcb_human")
    add_mesh(v, f)
    
    # Right PCB section (Isolated domain): X=74.5 to 85.0
    v, f = create_box(74.5, 0, -1.6, 10.5, 55.0, 1.6, pcb_color, "pcb_iso")
    add_mesh(v, f)
    
    # Bridge tabs at top and bottom of isolation slot
    v, f = create_box(67.5, 0, -1.6, 7.0, 4.0, 1.6, pcb_color, "pcb_bridge_top")
    add_mesh(v, f)
    v, f = create_box(67.5, 51.0, -1.6, 7.0, 4.0, 1.6, pcb_color, "pcb_bridge_bot")
    add_mesh(v, f)
    
    # Gold ENIG
    enig_gold = (212, 175, 55)
    
    # ESP32-S3 module: 18 x 25.5 x 3.2 mm at (46, 24)
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
    
    # TI ISOW7742 Reinforced Digital Isolator (SOIC-16W) straddling the slot at (71.0, 27.5)
    v, f = create_box(65.5, 22.5, 0.0, 11.0, 10.0, 2.4, (20, 20, 22), "isow7742_ic")
    add_mesh(v, f)
    for py in [23.5, 25.5, 27.5, 29.5, 31.5]:
        v, f = create_box(63.5, py, 0.0, 2.0, 0.8, 0.5, enig_gold, "pin_left")
        add_mesh(v, f)
        v, f = create_box(76.5, py, 0.0, 2.0, 0.8, 0.5, enig_gold, "pin_right")
        add_mesh(v, f)
        
    # USB-C Receptacle at (5.0, 27.5)
    v, f = create_box(0.0, 23.0, 0.0, 8.5, 9.0, 3.2, (215, 220, 225), "usb_c")
    add_mesh(v, f)
    
    # JST-PH Battery Connector at (12.0, 7.0)
    v, f = create_box(8.0, 3.0, 0.0, 8.0, 7.5, 6.0, (240, 240, 235), "jst_bat")
    add_mesh(v, f)
    
    # MicroSD Card Slot at (4.0, 42.0)
    v, f = create_box(1.0, 36.0, 0.0, 14.0, 13.0, 1.8, (195, 195, 205), "sd_slot")
    add_mesh(v, f)
    
    # Key ICs
    v, f = create_box(16.0, 16.0, 0.0, 4.0, 4.0, 1.0, (25, 25, 28), "ic_bq24074")
    add_mesh(v, f)
    v, f = create_box(16.0, 26.0, 0.0, 4.0, 4.0, 1.0, (25, 25, 28), "ic_tps63070")
    add_mesh(v, f)
    v, f = create_box(22.0, 26.0, 0.0, 4.5, 4.5, 2.0, (40, 40, 45), "inductor")
    add_mesh(v, f)
    
    v, f = create_box(27.0, 42.0, 0.0, 5.0, 4.5, 1.2, (25, 25, 28), "ic_ads1220")
    add_mesh(v, f)
    v, f = create_box(33.0, 42.0, 0.0, 4.5, 4.0, 1.2, (25, 25, 28), "ic_opa2192")
    add_mesh(v, f)
    v, f = create_box(39.0, 42.0, 0.0, 4.5, 4.0, 1.2, (25, 25, 28), "ic_ref5020")
    add_mesh(v, f)
    
    v, f = create_box(23.5, 12.5, 0.0, 3.0, 3.0, 0.9, (35, 35, 38), "ic_imu")
    add_mesh(v, f)
    v, f = create_box(23.5, 18.5, 0.0, 3.0, 3.0, 0.9, (35, 35, 38), "ic_haptic")
    add_mesh(v, f)
    
    for px, py in [(15, 10), (18, 10), (22, 10), (32, 18), (32, 22), (60, 15), (60, 20), (60, 35), (60, 40)]:
        v, f = create_box(px, py, 0.0, 1.2, 1.2, 0.08, enig_gold, "gold_pad")
        add_mesh(v, f)
        
    # 2. circle-ppg daughterboard: 25 x 18 x 1.6 mm
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

    return np.array(all_verts), all_faces

def render_frame(verts, faces, rot_y_deg, pitch_deg=28.0, cam_dist=190.0):
    cam = Camera3D(fov=46.0, distance=cam_dist, center=(42.5, 27.5, 1.0))
    sx, sy, depth, rot_pts = cam.project(verts, pitch_deg, rot_y_deg)
    
    light_dir = np.array([-0.4, -0.6, 0.7])
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
        ambient = 0.35
        specular = 0.0
        if diffuse > 0:
            halfway = (light_dir + np.array([0, 0, 1.0])) / np.linalg.norm(light_dir + np.array([0, 0, 1.0]))
            specular = max(0.0, float(np.dot(rot_norm, halfway))) ** 16
            
        intensity = ambient + 0.65 * diffuse
        shaded_r = min(255, int(base_color[0] * intensity + specular * 60))
        shaded_g = min(255, int(base_color[1] * intensity + specular * 60))
        shaded_b = min(255, int(base_color[2] * intensity + specular * 60))
        
        poly_2d = [(sx[i], sy[i]) for i in face_indices]
        face_render_data.append((avg_depth, view_dot, poly_2d, (shaded_r, shaded_g, shaded_b), name))
        
    face_render_data.sort(key=lambda item: item[0], reverse=True)
    
    img = Image.new("RGBA", (WIDTH, HEIGHT), (14, 17, 23, 255))
    draw = ImageDraw.Draw(img)
    
    draw.ellipse([WIDTH/2 - 280, HEIGHT/2 - 90, WIDTH/2 + 280, HEIGHT/2 + 150], fill=(22, 28, 36, 255))
    draw.ellipse([WIDTH/2 - 200, HEIGHT/2 - 50, WIDTH/2 + 200, HEIGHT/2 + 100], fill=(30, 38, 48, 255))
    
    for avg_depth, view_dot, poly, color, name in face_render_data:
        if view_dot > -0.15 or len(poly) > 4:
            draw.polygon(poly, fill=color, outline=(min(255, color[0] + 20), min(255, color[1] + 20), min(255, color[2] + 20)))

    # Header & Domain badges
    draw.text((25, 20), "CIRCLE Rev B Hardware Assembly", fill=(255, 255, 255))
    draw.text((25, 42), "3D Multi-Domain Acquisition Architecture", fill=(140, 160, 180))
    
    # Legend badges
    draw.rectangle([25, HEIGHT - 45, 170, HEIGHT - 20], fill=(20, 50, 35, 220), outline=(50, 180, 100))
    draw.text((35, HEIGHT - 38), "BAT_HUMAN (Isolated)", fill=(100, 230, 140))
    
    draw.rectangle([180, HEIGHT - 45, 310, HEIGHT - 20], fill=(25, 45, 75, 220), outline=(70, 140, 240))
    draw.text((190, HEIGHT - 38), "LAB_ISO (5 kVrms)", fill=(120, 180, 255))
    
    draw.rectangle([320, HEIGHT - 45, 470, HEIGHT - 20], fill=(60, 35, 20, 220), outline=(230, 140, 50))
    draw.text((330, HEIGHT - 38), "8.0mm Cutout Slot", fill=(255, 180, 80))
    
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
        angle = (360.0 / num_frames) * i - 30.0
        pitch = 28.0 + 4.0 * math.sin(math.radians(angle * 2))
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

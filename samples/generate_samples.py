"""
generate_samples.py - Generates realistic offline test sample medical images
(Chest X-Ray Normal & Pneumonia, Bone Fracture X-Ray, Brain MRI Normal & Stroke)
Allows immediate 1-click testing by hackathon judges and users.
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
os.makedirs(OUTPUT_DIR, exist_ok=True)

def create_chest_xray(path: str, has_pneumonia: bool = False):
    w, h = 512, 512
    arr = np.zeros((h, w), dtype=np.float32)
    
    # Background soft tissue / thoracic cage
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    
    # Rib cage boundary
    rib_cage = ((x - cx)**2 / (190**2) + (y - (cy + 20))**2 / (210**2)) <= 1.0
    arr[rib_cage] = 45.0
    
    # Bilateral dark lung fields
    left_lung = ((x - (cx - 85))**2 / (65**2) + (y - (cy - 10))**2 / (135**2)) <= 1.0
    right_lung = ((x - (cx + 85))**2 / (65**2) + (y - (cy - 10))**2 / (135**2)) <= 1.0
    arr[left_lung] = 18.0
    arr[right_lung] = 18.0
    
    # Bronchial tree / vascular markings
    np.random.seed(42)
    noise = np.random.normal(0, 4, (h, w))
    arr += noise
    
    # Spine down midline
    spine = (np.abs(x - cx) < 18) & (y > 40) & (y < 460)
    arr[spine] += 55.0
    
    # Clavicles
    clav_left = (np.abs(y - (70 + (x - 70)*0.15)) < 10) & (x > 70) & (x < 240)
    clav_right = (np.abs(y - (70 - (x - 440)*0.15)) < 10) & (x > 270) & (x < 440)
    arr[clav_left] += 70.0
    arr[clav_right] += 70.0
    
    # Rib contours
    for rib_y in range(110, 420, 36):
        rib = (np.abs(y - (rib_y + (x - cx)**2 / 700.0)) < 6) & rib_cage
        arr[rib] += 30.0
        
    # Cardiac silhouette (heart)
    heart = ((x - (cx + 25))**2 / (75**2) + (y - (cy + 60))**2 / (85**2)) <= 1.0
    arr[heart] += 75.0
    
    # Diaphragm domes
    diaphragm_l = (y > (400 - (x - 170)**2 / 400.0)) & (x < cx) & rib_cage
    diaphragm_r = (y > (395 - (x - 340)**2 / 400.0)) & (x >= cx) & rib_cage
    arr[diaphragm_l] += 60.0
    arr[diaphragm_r] += 60.0

    if has_pneumonia:
        # Add dense focal infiltrative opacity in right mid/lower lung
        infiltrate = ((x - (cx + 90))**2 / (45**2) + (y - (cy + 35))**2 / (40**2)) <= 1.0
        arr[infiltrate] += 95.0
        # Add hazy borders
        haze = ((x - (cx + 90))**2 / (65**2) + (y - (cy + 35))**2 / (55**2)) <= 1.0
        arr[haze] += 35.0

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    img.save(path)
    print(f"Saved {path}")

def create_bone_fracture_xray(path: str):
    w, h = 512, 512
    arr = np.zeros((h, w), dtype=np.float32)
    y, x = np.ogrid[:h, :w]
    cx = w / 2

    # Arm soft tissue silhouette
    arm_soft = ((y >= 0) & (y < h)) & (np.abs(x - cx) < 140)
    arr[arm_soft] = 35.0

    # Radius and Ulna long bones
    radius = (np.abs(x - (cx - 45)) < 24) & (y > 40) & (y < 470)
    ulna = (np.abs(x - (cx + 45)) < 20) & (y > 40) & (y < 470)
    arr[radius] = 160.0
    arr[ulna] = 155.0

    # Cortical margins (dense edges)
    radius_cortex = ((np.abs(x - (cx - 45)) >= 18) & (np.abs(x - (cx - 45)) <= 24)) & (y > 40) & (y < 470)
    ulna_cortex = ((np.abs(x - (cx + 45)) >= 15) & (np.abs(x - (cx + 45)) <= 20)) & (y > 40) & (y < 470)
    arr[radius_cortex] += 60.0
    arr[ulna_cortex] += 55.0

    # Acute Transverse Fracture line with cortical gap on Radius
    frac_y = 260
    fracture_line = (np.abs(y - (frac_y + (x - (cx - 45))*0.4)) < 4) & (np.abs(x - (cx - 45)) < 28)
    arr[fracture_line] = 20.0 # Dark radiolucent gap line
    
    # Displaced cortical step-off
    step_off = (y > frac_y) & (np.abs(x - (cx - 42)) < 24) & (y < 470)
    arr[step_off] = 160.0

    # Add realistic radiographic noise
    np.random.seed(101)
    arr += np.random.normal(0, 5, (h, w))
    arr = np.clip(arr, 0, 255).astype(np.uint8)

    img = Image.fromarray(arr).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    img.save(path)
    print(f"Saved {path}")

def create_brain_mri(path: str, has_stroke: bool = False):
    w, h = 512, 512
    arr = np.zeros((h, w), dtype=np.float32)
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2

    # Calvarium (skull) oval
    skull_outer = ((x - cx)**2 / (175**2) + (y - cy)**2 / (215**2)) <= 1.0
    skull_bone = skull_outer & ~(((x - cx)**2 / (163**2) + (y - cy)**2 / (203**2)) <= 1.0)
    brain_parenchyma = ((x - cx)**2 / (160**2) + (y - cy)**2 / (200**2)) <= 1.0

    arr[skull_bone] = 180.0
    arr[brain_parenchyma] = 85.0 # Gray/White matter baseline

    # Cerebral sulci and gyri texture
    np.random.seed(77)
    texture = np.random.normal(0, 8, (h, w))
    arr[brain_parenchyma] += texture[brain_parenchyma]

    # Interhemispheric fissure (midline)
    midline = (np.abs(x - cx) < 2) & brain_parenchyma
    arr[midline] = 30.0

    # Lateral ventricles (butterfly shape)
    vent_l = ((x - (cx - 26))**2 / (16**2) + (y - (cy - 10))**2 / (45**2)) <= 1.0
    vent_r = ((x - (cx + 26))**2 / (16**2) + (y - (cy - 10))**2 / (45**2)) <= 1.0
    arr[vent_l & brain_parenchyma] = 25.0
    arr[vent_r & brain_parenchyma] = 25.0

    if has_stroke:
        # Acute ischemic infarct / high signal intensity lesion on T2/FLAIR in left MCA territory
        stroke_zone = ((x - (cx - 75))**2 / (38**2) + (y - (cy + 15))**2 / (48**2)) <= 1.0
        arr[stroke_zone & brain_parenchyma] += 80.0
        # Mild mass effect displacing left lateral ventricle slightly
        arr[vent_l] = 45.0

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(radius=1.0))
    img.save(path)
    print(f"Saved {path}")

if __name__ == "__main__":
    create_chest_xray(os.path.join(OUTPUT_DIR, "chest_xray_normal.png"), has_pneumonia=False)
    create_chest_xray(os.path.join(OUTPUT_DIR, "chest_xray_pneumonia.png"), has_pneumonia=True)
    create_bone_fracture_xray(os.path.join(OUTPUT_DIR, "bone_fracture_xray.png"))
    create_brain_mri(os.path.join(OUTPUT_DIR, "brain_mri_normal.png"), has_stroke=False)
    create_brain_mri(os.path.join(OUTPUT_DIR, "brain_mri_acute_lesion.png"), has_stroke=True)
    print("All sample images generated successfully!")

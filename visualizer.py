# visualizer.py

import matplotlib
matplotlib.use('Agg')  # ✅ SAFE headless rendering
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

def draw_sheets_to_files(sheets, output_dir):
    """
    Save each sheet's cut layout as PNG to output_dir.
    Uses Agg backend = no GUI.
    """
    os.makedirs(output_dir, exist_ok=True)

    for sheet_idx, sheet in enumerate(sheets, start=1):
        # ✅ SKIP completely empty sheets (shouldn't happen now but double-check)
        if not sheet['cut_plan']:
            continue

        fig, ax = plt.subplots(figsize=(10, 5))
        panel_w, panel_h = sheet['panel_size']

        # Panel background
        ax.add_patch(
            patches.Rectangle((0, 0), panel_w, panel_h,
                              edgecolor='black', facecolor='lightgray', fill=True)
        )

        # Parts
        for cut in sheet['cut_plan']:
            x, y = cut['position']
            w, h = cut['width'], cut['height']
            rect = patches.Rectangle(
                (x, y), w, h,
                edgecolor='blue', facecolor='skyblue', alpha=0.6
            )
            ax.add_patch(rect)
            ax.text(x + w/2, y + h/2, f"#{cut['part_number']}",
                    ha='center', va='center', fontsize=8, color='black')

        ax.set_xlim(0, panel_w)
        ax.set_ylim(0, panel_h)
        ax.set_aspect('equal')
        ax.set_title(f"Sheet #{sheet_idx}")
        ax.invert_yaxis()

        file_path = os.path.join(output_dir, f"sheet_{sheet_idx}.png")
        plt.savefig(file_path, bbox_inches='tight')
        plt.close(fig)

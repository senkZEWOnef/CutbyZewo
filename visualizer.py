# visualizer.py

import matplotlib
matplotlib.use('Agg')  # ✅ Safe for headless rendering (server)
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

def draw_sheets_to_files(sheets, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for sheet_idx, sheet in enumerate(sheets, start=1):
        if not sheet['cut_plan']:
            continue

        fig, ax = plt.subplots(figsize=(10, 5))
        panel_w, panel_h = sheet['panel_size']

        # ✅ PANEL background covers true sheet dimensions
        ax.add_patch(
            patches.Rectangle(
                (0, 0), panel_w, panel_h,
                edgecolor='black',
                facecolor='lightgray',
                fill=True
            )
        )

        # ✅ PARTS drawn on top of the sheet
        for cut in sheet['cut_plan']:
            x, y = cut['position']
            w, h = cut['width'], cut['height']
            rect = patches.Rectangle(
                (x, y), w, h,
                edgecolor='blue',
                facecolor='skyblue',
                alpha=0.7
            )
            ax.add_patch(rect)
            ax.text(
                x + w/2, y + h/2,
                f"#{cut['part_number']}",
                ha='center',
                va='center',
                fontsize=8
            )

        # ✅ ESSENTIAL: Set correct limits
        ax.set_xlim(0, panel_w)
        ax.set_ylim(0, panel_h)
        ax.set_aspect('equal')

        # ✅ ✅ ✅ NEW: Add grid every 12 inches (1 foot)
        ax.set_xticks(range(0, int(panel_w)+1, 12))
        ax.set_yticks(range(0, int(panel_h)+1, 12))
        ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='gray')

        # ✅ LABELS: clear title, invert Y for normal top-down view
        ax.set_title(f"Sheet #{sheet_idx} — {panel_w} x {panel_h} inches")
        ax.invert_yaxis()

        # ✅ SAVE to PNG
        file_path = os.path.join(output_dir, f"sheet_{sheet_idx}.png")
        plt.savefig(file_path, bbox_inches='tight')
        plt.close(fig)

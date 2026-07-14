# visualizer.py

import matplotlib
matplotlib.use('Agg')  # ✅ Safe for headless rendering (server)
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

def draw_sheets_to_files(sheets, output_dir, start_index=1, label_prefix=None):
    os.makedirs(output_dir, exist_ok=True)

    results = []

    for offset, sheet in enumerate(sheets):
        if not sheet['cut_plan']:
            continue
        sheet_idx = start_index + offset

        fig, ax = plt.subplots(figsize=(10, 5))
        panel_w, panel_h = sheet['panel_size']

        ax.add_patch(
            patches.Rectangle(
                (0, 0), panel_w, panel_h,
                edgecolor='black',
                facecolor='lightgray',
                fill=True
            )
        )

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

        ax.set_xlim(0, panel_w)
        ax.set_ylim(0, panel_h)
        ax.set_aspect('equal')

        ax.set_xticks(range(0, int(panel_w)+1, 12))
        ax.set_yticks(range(0, int(panel_h)+1, 12))
        ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='gray')

        title = f"Sheet #{sheet_idx}"
        if label_prefix:
            title += f" — {label_prefix}"
        title += f" — {panel_w} x {panel_h} inches"
        ax.set_title(title)
        ax.invert_yaxis()

        file_path = os.path.join(output_dir, f"sheet_{sheet_idx}.png")
        plt.savefig(file_path, bbox_inches='tight')
        plt.close(fig)

        # Return path relative to static/ and a label for the template
        relative_path = file_path.replace("static/", "", 1)
        label = f"{int(panel_w)} x {int(panel_h)}"
        if label_prefix:
            label = f"{label_prefix} — {label}"
        results.append((relative_path, label))

    return results

# main.py

from cabinet import generate_parts
from planner import optimize_cuts
from visualizer import draw_sheets

def main():
    # === Define your cabinet module ===
    height = 30  # Cabinet height in inches
    width = 30   # Cabinet width in inches
    depth = 24   # Cabinet depth in inches

    quantity = 2  # How many modules to build

    # === Generate all parts needed ===
    single_parts = generate_parts(height, width, depth)
    all_parts = single_parts * quantity  # Duplicate for all modules

    print("=== Parts List ===")
    for idx, part in enumerate(all_parts, start=1):
        print(f"Part #{idx}: {part[0]} x {part[1]}")

    # === Define raw sheet size ===
    panel_width = 96  # inches
    panel_height = 48  # inches

    # === Plan cuts with kerf, multiple sheets ===
    sheets = optimize_cuts(panel_width, panel_height, all_parts)

    # === Print cut plan for each sheet ===
    for sheet_idx, sheet in enumerate(sheets, start=1):
        print(f"\n=== Sheet #{sheet_idx} ===")
        for cut in sheet['cut_plan']:
            print(f"  Part #{cut['part_number']}: {cut['width']} x {cut['height']} at position {cut['position']}")

    # === Visualize the sheets ===
    draw_sheets(sheets)


if __name__ == "__main__":
    main()

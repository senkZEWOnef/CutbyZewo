# planner.py

KERF = 0.125  # 1/8 inch saw blade

def optimize_cuts(panel_width, panel_height, parts):
    """
    Packs parts into sheets using a simple first-fit decreasing heuristic.
    """
    parts = sorted(parts, key=lambda x: x[0]*x[1], reverse=True)
    sheets = []

    for idx, (w, h) in enumerate(parts, start=1):
        net_w, net_h = w + KERF, h + KERF
        placed = False

        for sheet in sheets:
            spots = sheet['free_rects']
            for spot in spots:
                sx, sy, sw, sh = spot
                if net_w <= sw and net_h <= sh:
                    # Place here
                    sheet['cut_plan'].append({
                        "part_number": idx,
                        "width": w,
                        "height": h,
                        "position": (sx, sy)
                    })
                    spots.remove(spot)
                    spots.append((sx + net_w, sy, sw - net_w, net_h))
                    spots.append((sx, sy + net_h, sw, sh - net_h))
                    placed = True
                    break
            if placed:
                break

        if not placed:
            # Make new sheet
            sheet = {
                "panel_size": (panel_width, panel_height),
                "cut_plan": [],
                "free_rects": [(0, 0, panel_width, panel_height)]
            }
            sheet['cut_plan'].append({
                "part_number": idx,
                "width": w,
                "height": h,
                "position": (0, 0)
            })
            sheet['free_rects'].remove((0, 0, panel_width, panel_height))
            sheet['free_rects'].append((net_w, 0, panel_width - net_w, net_h))
            sheet['free_rects'].append((0, net_h, panel_width, panel_height - net_h))
            sheets.append(sheet)

    # Clean up for drawing
    for sheet in sheets:
        del sheet['free_rects']

    return sheets

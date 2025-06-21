# planner.py

KERF = 0.125  # 1/8 inch

def optimize_cuts(panel_width, panel_height, parts):
    """
    Improved: support multiple sheets.
    Returns a list of sheets, each with its own cut plan.
    """
    sheets = []
    current_sheet = {
        "panel_size": (panel_width, panel_height),
        "cut_plan": []
    }

    x_cursor = 0
    y_cursor = 0
    row_height = 0

    for idx, (w, h) in enumerate(parts, start=1):
        net_w = w + KERF
        net_h = h + KERF

        # If part doesn't fit horizontally, move to new row
        if x_cursor + net_w > panel_width:
            x_cursor = 0
            y_cursor += row_height + KERF
            row_height = 0

        # If part doesn't fit vertically, start new sheet!
        if y_cursor + net_h > panel_height:
            # Save current sheet
            sheets.append(current_sheet)

            # Start new sheet
            current_sheet = {
                "panel_size": (panel_width, panel_height),
                "cut_plan": []
            }
            x_cursor = 0
            y_cursor = 0
            row_height = 0

        # Place the part
        current_sheet["cut_plan"].append({
            "part_number": idx,
            "width": w,
            "height": h,
            "position": (x_cursor, y_cursor)
        })

        x_cursor += net_w
        if net_h > row_height:
            row_height = net_h

    # Save the last sheet
    sheets.append(current_sheet)

    return sheets

# planner.py

KERF = 0.125  # 1/8 inch

def optimize_cuts(panel_width, panel_height, parts):
    """
    Improved: robustly pack parts into as few sheets as possible.
    Returns a list of sheets, each with its own cut plan.
    """
    sheets = []

    # NO pre-made blank sheet: only add when needed
    current_sheet = None
    x_cursor = 0
    y_cursor = 0
    row_height = 0

    for idx, (w, h) in enumerate(parts, start=1):
        net_w = w + KERF
        net_h = h + KERF

        # If no current sheet exists, create the first one
        if current_sheet is None:
            current_sheet = {
                "panel_size": (panel_width, panel_height),
                "cut_plan": []
            }

        # If part won't fit horizontally, wrap to new row
        if x_cursor + net_w > panel_width:
            x_cursor = 0
            y_cursor += row_height + KERF
            row_height = 0

        # If part won't fit vertically, finalize sheet, start a new one
        if y_cursor + net_h > panel_height:
            sheets.append(current_sheet)
            current_sheet = {
                "panel_size": (panel_width, panel_height),
                "cut_plan": []
            }
            x_cursor = 0
            y_cursor = 0
            row_height = 0

        # Place part on sheet
        current_sheet["cut_plan"].append({
            "part_number": idx,
            "width": w,
            "height": h,
            "position": (x_cursor, y_cursor)
        })

        x_cursor += net_w
        if net_h > row_height:
            row_height = net_h

    # Add the last active sheet if it has any parts
    if current_sheet and current_sheet["cut_plan"]:
        sheets.append(current_sheet)

    return sheets

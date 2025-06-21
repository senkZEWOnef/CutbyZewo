# cabinet.py

def generate_parts(height, width, depth):
    """
    Given module dimensions, return list of required panels.
    Adjust dimensions for real building logic: side panels, top/bottom, back, etc.
    All sizes are in inches.
    """

    side_panel_height = height
    side_panel_depth = depth - 1  # subtract back panel thickness

    top_bottom_width = width - 1.5  # subtract side thickness (3/4 + 3/4)
    top_bottom_depth = side_panel_depth

    back_panel_height = height
    back_panel_width = width

    parts = []

    # Sides: 2 pieces
    parts += [(side_panel_depth, side_panel_height)] * 2

    # Top & Bottom: 2 pieces
    parts += [(top_bottom_depth, top_bottom_width)] * 2

    # Back panel: 1 piece (usually 1/4 thick, full back)
    parts += [(back_panel_width, back_panel_height)]

    return parts

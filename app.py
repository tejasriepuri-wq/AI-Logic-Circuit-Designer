
def graph(circuit):
    import html

    inputs = circuit["inputs"]
    gates = circuit["gates"]
    output = circuit["output"]

    gate_map = {g["id"]: g for g in gates}

    # Calculate gate levels
    levels = {}
    for gate in gates:
        parent_levels = [
            levels.get(signal, 0)
            for signal in gate["inputs"]
        ]
        levels[gate["id"]] = max(parent_levels, default=0) + 1

    max_level = max(levels.values(), default=0)
    width = 260 + (max_level + 1) * 190
    height = max(300, (len(inputs) + len(gates) + 1) * 115)

    positions = {}

    # Input positions
    for i, name in enumerate(inputs):
        positions[name] = (70, 90 + i * 110)

    # Gate positions
    for i, gate in enumerate(gates):
        x = 220 + levels[gate["id"]] * 180
        y = 90 + i * 115
        positions[gate["id"]] = (x, y)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="100%" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>'
    ]

    def line(x1, y1, x2, y2):
        return (
            f'<path d="M{x1} {y1} L{x2} {y2}" '
            'stroke="black" stroke-width="2.5" fill="none"/>'
        )

    # Draw input wires and labels
    for name in inputs:
        x, y = positions[name]
        svg.append(
            f'<text x="{x-35}" y="{y+6}" font-size="20">'
            f'{html.escape(name)}</text>'
        )

    # Draw each gate and its connections
    for gate in gates:
        gid = gate["id"]
        kind = gate["type"].upper()
        x, y = positions[gid]
        gx = x
        gy = y - 30

        # Gate dimensions
        w, h = 85, 65

        # Connect input signals
        for j, signal in enumerate(gate["inputs"]):
            sx, sy = positions[signal]
            port_y = y + (j - (len(gate["inputs"]) - 1) / 2) * 18

            svg.append(line(sx + 35, sy, gx, port_y))

        # Gate body paths
        if kind in ("AND", "NAND"):
            path = (
                f"M{gx} {gy} L{gx+35} {gy} "
                f"A32 32 0 0 1 {gx+35} {gy+65} "
                f"L{gx} {gy+65} Z"
            )
            svg.append(
                f'<path d="{path}" fill="#fff0bd" '
                'stroke="black" stroke-width="2.5"/>'
            )

        elif kind in ("OR", "NOR", "XOR", "XNOR"):
            path = (
                f"M{gx} {gy} "
                f'Q{gx+25} {gy+32} {gx} {gy+65} '
                f'Q{gx+48} {gy+65} {gx+85} {gy+32} '
                f'Q{gx+48} {gy} {gx} {gy} Z'
            )
            svg.append(
                f'<path d="{path}" fill="#fff0bd" '
                'stroke="black" stroke-width="2.5"/>'
            )

            if kind in ("XOR", "XNOR"):
                svg.append(
                    f'<path d="M{gx-9} {gy} '
                    f'Q{gx+16} {gy+32} {gx-9} {gy+65}" '
                    'fill="none" stroke="black" stroke-width="2.5"/>'
                )

        elif kind == "NOT":
            svg.append(
                f'<path d="M{gx} {gy} L{gx} {gy+65} '
                f'L{gx+75} {gy+32} Z" '
                'fill="#fff0bd" stroke="black" stroke-width="2.5"/>'
            )

        else:
            svg.append(
                f'<rect x="{gx}" y="{gy}" width="85" height="65" '
                'fill="#fff0bd" stroke="black" stroke-width="2.5"/>'
            )

        # Inversion bubbles
        if kind in ("NAND", "NOR", "XNOR", "NOT"):
            svg.append(
                f'<circle cx="{gx+91}" cy="{y+2}" r="6" '
                'fill="white" stroke="black" stroke-width="2"/>'
            )
            out_x = gx + 97
        else:
            out_x = gx + 85

        # Gate name
        svg.append(
            f'<text x="{gx+38}" y="{y+7}" '
            'font-size="15" text-anchor="middle">'
            f'{html.escape(kind)}</text>'
        )

        positions[gid] = (out_x, y)

    # Final output connection
    ox, oy = positions[output]
    end_x = width - 90

    svg.append(line(ox, oy, end_x, oy))
    svg.append(
        f'<circle cx="{end_x+25}" cy="{oy}" r="25" '
        'fill="#d5f4e3" stroke="black" stroke-width="2.5"/>'
    )
    svg.append(
        f'<text x="{end_x+25}" y="{oy+6}" '
        'font-size="18" text-anchor="middle">'
        f'{html.escape(output)}</text>'
    )

    svg.append('</svg>')
    return "".join(svg)

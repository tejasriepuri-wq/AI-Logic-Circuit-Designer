
def graph(circuit):
    import html
    from collections import defaultdict

    inputs = circuit["inputs"]
    gates = circuit["gates"]
    output = circuit["output"]

    # Calculate logic levels
    levels = {name: 0 for name in inputs}

    for gate in gates:
        levels[gate["id"]] = max(
            levels[s] for s in gate["inputs"]
        ) + 1

    # Group gates according to their logic level
    grouped = defaultdict(list)

    for gate in gates:
        grouped[levels[gate["id"]]].append(gate)

    max_level = max(levels.values(), default=0)

    gate_w = 90
    gate_h = 70
    col_gap = 190
    row_gap = 120
    left = 120
    top = 100

    max_rows = max(
        [len(inputs), len(gates), 1]
    )

    width = left + (max_level + 1) * col_gap + 230
    height = max(300, top * 2 + (max_rows - 1) * row_gap + 80)

    positions = {}

    # Input positions
    for i, name in enumerate(inputs):
        positions[name] = (left, top + i * row_gap)

    # Gate positions
    gate_positions = {}

    for level, level_gates in grouped.items():
        for i, gate in enumerate(level_gates):
            x = left + level * col_gap
            y = top + i * row_gap

            gate_positions[gate["id"]] = (x, y)
            positions[gate["id"]] = (x + gate_w + 15, y)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="100%" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>'
        '.wire{stroke:#202020;stroke-width:2.5;fill:none}'
        '.gate{fill:#fff0bd;stroke:#202020;stroke-width:2.5}'
        '.bubble{fill:white;stroke:#202020;stroke-width:2.5}'
        'text{font-family:Arial,sans-serif;fill:#111}'
        '</style>'
    ]

    # Right-angle connected wires
    def line(x1, y1, x2, y2):
        mid = (x1 + x2) / 2

        return (
            f'<path class="wire" '
            f'd="M{x1},{y1} H{mid} V{y2} H{x2}"/>'
        )

    # Draw primary inputs
    for name in inputs:
        x, y = positions[name]

        svg.append(
            f'<text x="{x-20}" y="{y+6}" '
            f'text-anchor="end" font-size="19" '
            f'font-weight="bold">{html.escape(name)}</text>'
        )

        svg.append(
            f'<circle cx="{x}" cy="{y}" r="4" fill="black"/>'
        )

    # Draw gates
    for gate in gates:

        gid = gate["id"]
        kind = gate["type"].upper()

        gx, cy = gate_positions[gid]

        gy = cy - gate_h / 2
        right = gx + gate_w

        # Calculate gate input port positions
        count = len(gate["inputs"])

        if count == 1:
            ports = [cy]
        else:
            spacing = min(24, 48 / (count - 1))
            ports = [
                cy + (i - (count - 1) / 2) * spacing
                for i in range(count)
            ]

        # Connect all input signals
        for signal, py in zip(gate["inputs"], ports):
            sx, sy = positions[signal]
            line_start = sx + 5

            svg.append(
                line(line_start, sy, gx, py)
            )

        # AND and NAND gate symbols
        if kind in ("AND", "NAND"):

            path = (
                f'M{gx},{gy} '
                f'L{gx+43},{gy} '
                f'A35,35 0 0 1 {gx+43},{gy+70} '
                f'L{gx},{gy+70} Z'
            )

            svg.append(
                f'<path class="gate" d="{path}"/>'
            )

        # NOT gate symbol
        elif kind == "NOT":

            path = (
                f'M{gx},{gy} '
                f'L{gx},{gy+70} '
                f'L{right-10},{cy} Z'
            )

            svg.append(
                f'<path class="gate" d="{path}"/>'
            )

        # OR, NOR, XOR and XNOR symbols
        else:

            path = (
                f'M{gx},{gy} '
                f'Q{gx+25},{cy} {gx},{gy+70} '
                f'Q{gx+55},{gy+70} {right},{cy} '
                f'Q{gx+55},{gy} {gx},{gy} Z'
            )

            svg.append(
                f'<path class="gate" d="{path}"/>'
            )

            # Extra curved line for XOR and XNOR
            if kind in ("XOR", "XNOR"):

                extra = (
                    f'M{gx-11},{gy} '
                    f'Q{gx+13},{cy} {gx-11},{gy+70}'
                )

                svg.append(
                    f'<path d="{extra}" fill="none" '
                    f'stroke="black" stroke-width="2.5"/>'
                )

        # Output inversion bubbles
        inverted = kind in ("NAND", "NOR", "XNOR", "NOT")

        if inverted:

            svg.append(
                f'<circle class="bubble" '
                f'cx="{right+6}" cy="{cy}" r="6"/>'
            )

            output_x = right + 12

        else:
            output_x = right

        # Gate name
        svg.append(
            f'<text x="{gx+43}" y="{cy+5}" '
            f'text-anchor="middle" font-size="11" '
            f'font-weight="bold">{html.escape(kind)}</text>'
        )

        # Store actual gate output position
        positions[gid] = (output_x + 5, cy)

    # Final output
    ox, oy = positions[output]

    end_x = max(width - 120, ox + 70)

    svg.append(
        line(ox, oy, end_x, oy)
    )

    svg.append(
        f'<circle cx="{end_x+28}" cy="{oy}" r="23" '
        f'fill="#d5f4e3" stroke="black" stroke-width="2.5"/>'
    )

    svg.append(
        f'<text x="{end_x+28}" y="{oy+6}" '
        f'text-anchor="middle" font-size="17" '
        f'font-weight="bold">{html.escape(output)}</text>'
    )

    svg.append('</svg>')

    return "".join(svg)

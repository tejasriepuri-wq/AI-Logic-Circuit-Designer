
import os
import re
import json
import itertools
import html

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from google import genai


# --------------------------------------------------
# PAGE SETTINGS
# --------------------------------------------------

st.set_page_config(
    page_title="AI Logic Circuit Designer",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ AI-Based Logic Gate Circuit Designer")
st.write(
    "Describe a digital logic circuit. AI will generate its "
    "logic diagram, truth table, Boolean expressions and Verilog code."
)


# --------------------------------------------------
# GEMINI API
# --------------------------------------------------

def get_api_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass

    return os.getenv("GEMINI_API_KEY", "")


def generate_with_ai(prompt):
    key = get_api_key()

    if not key:
        raise ValueError(
            "GEMINI_API_KEY is missing. Add it in "
            "Streamlit Cloud → App settings → Secrets."
        )

    client = genai.Client(api_key=key)

    instruction = f"""
You are an expert digital logic circuit designer.

Design the circuit requested by the user.

USER REQUEST:
{prompt}

Return ONLY valid JSON. Do not use Markdown fences.

Use this exact JSON structure:

{{
  "inputs": ["A", "B"],
  "gates": [
    {{
      "id": "G1",
      "type": "AND",
      "inputs": ["A", "B"]
    }}
  ],
  "outputs": [
    {{
      "name": "Y",
      "source": "G1"
    }}
  ],
  "explanation": "Explain how the circuit works.",
  "design_steps": [
    "Step 1",
    "Step 2"
  ]
}}

RULES:
1. Supported gate types: AND, OR, NOT, NAND, NOR, XOR, XNOR.
2. Every gate must have a unique ID such as G1, G2, G3.
3. Gate inputs must refer to primary inputs or previously created gates.
4. Use the correct number of inputs for each gate.
5. NOT must have exactly one input.
6. Other gates can have two or more inputs.
7. Outputs must contain a name and a source.
8. Output sources must refer to a primary input or a gate ID.
9. Use separate outputs for circuits such as full adders.
10. Use real logic gates. Do not use arithmetic operators as gates.
11. Do not create unnecessary gates.
12. Ensure the circuit implements the user's request correctly.
13. Use simple explanations.
14. Return JSON only.
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=instruction
    )

    raw = response.text.strip()

    # Remove Markdown code fences if the model returns them.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# --------------------------------------------------
# CIRCUIT VALIDATION
# --------------------------------------------------

VALID_GATES = {
    "AND", "OR", "NOT", "NAND",
    "NOR", "XOR", "XNOR"
}


def validate_circuit(circuit):
    if not isinstance(circuit, dict):
        raise ValueError("AI returned an invalid circuit.")

    inputs = circuit.get("inputs")
    gates = circuit.get("gates")
    outputs = circuit.get("outputs")

    if not isinstance(inputs, list) or not inputs:
        raise ValueError("Circuit must contain at least one input.")

    if len(inputs) > 8:
        raise ValueError("This version supports up to 8 primary inputs.")

    if len(set(inputs)) != len(inputs):
        raise ValueError("Duplicate primary input names were generated.")

    if not all(
        isinstance(name, str) and re.fullmatch(r"[A-Za-z_]\w*", name)
        for name in inputs
    ):
        raise ValueError("Invalid primary input name.")

    if not isinstance(gates, list):
        raise ValueError("Invalid gate list.")

    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Circuit must contain at least one output.")

    available = set(inputs)
    gate_ids = set()

    for gate in gates:
        if not isinstance(gate, dict):
            raise ValueError("Invalid gate information.")

        gid = gate.get("id")
        gate_type = str(gate.get("type", "")).upper()
        gate_inputs = gate.get("inputs")

        if not isinstance(gid, str) or not re.fullmatch(r"[A-Za-z_]\w*", gid):
            raise ValueError("Invalid gate ID.")

        if gid in available or gid in gate_ids:
            raise ValueError("Duplicate gate ID: " + gid)

        if gate_type not in VALID_GATES:
            raise ValueError("Unsupported gate: " + gate_type)

        if not isinstance(gate_inputs, list) or not gate_inputs:
            raise ValueError("Gate " + gid + " has no inputs.")

        if gate_type == "NOT" and len(gate_inputs) != 1:
            raise ValueError("NOT gate must have exactly one input.")

        if gate_type != "NOT" and len(gate_inputs) < 2:
            raise ValueError(gate_type + " gate needs at least two inputs.")

        for signal in gate_inputs:
            if signal not in available:
                raise ValueError(
                    "Gate " + gid + " uses unknown or not-yet-created signal: "
                    + str(signal)
                )

        gate["type"] = gate_type
        available.add(gid)
        gate_ids.add(gid)

    output_names = set()

    for output in outputs:
        if not isinstance(output, dict):
            raise ValueError("Invalid output information.")

        name = output.get("name")
        source = output.get("source")

        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError("Invalid output name.")

        if name in inputs or name in gate_ids or name in output_names:
            raise ValueError("Duplicate output name: " + name)

        if source not in available:
            raise ValueError("Unknown output source: " + str(source))

        output_names.add(name)

    return circuit


# --------------------------------------------------
# LOGIC EVALUATION
# --------------------------------------------------

def evaluate_gate(gate_type, values):
    if gate_type == "AND":
        return int(all(values))

    if gate_type == "OR":
        return int(any(values))

    if gate_type == "NOT":
        return 1 - values[0]

    if gate_type == "NAND":
        return 1 - int(all(values))

    if gate_type == "NOR":
        return 1 - int(any(values))

    if gate_type == "XOR":
        result = 0
        for value in values:
            result ^= value
        return result

    if gate_type == "XNOR":
        result = 0
        for value in values:
            result ^= value
        return 1 - result

    raise ValueError("Unknown gate type: " + gate_type)


def calculate_outputs(circuit, input_values):
    signals = dict(input_values)

    for gate in circuit["gates"]:
        values = [signals[name] for name in gate["inputs"]]

        signals[gate["id"]] = evaluate_gate(
            gate["type"],
            values
        )

    result = {}

    for output in circuit["outputs"]:
        result[output["name"]] = signals[output["source"]]

    return result


# --------------------------------------------------
# TRUTH TABLE
# --------------------------------------------------

def make_truth_table(circuit):
    inputs = circuit["inputs"]
    rows = []

    for combination in itertools.product([0, 1], repeat=len(inputs)):
        input_values = dict(zip(inputs, combination))
        output_values = calculate_outputs(circuit, input_values)

        rows.append({
            **input_values,
            **output_values
        })

    return pd.DataFrame(rows)


# --------------------------------------------------
# BOOLEAN EXPRESSIONS
# --------------------------------------------------

def boolean_expressions(circuit):
    expressions = {
        name: name for name in circuit["inputs"]
    }

    for gate in circuit["gates"]:
        parts = [
            expressions[name]
            for name in gate["inputs"]
        ]

        gate_type = gate["type"]

        if gate_type == "NOT":
            expression = "(~" + parts[0] + ")"

        elif gate_type == "AND":
            expression = "(" + " & ".join(parts) + ")"

        elif gate_type == "NAND":
            expression = "~(" + " & ".join(parts) + ")"

        elif gate_type == "OR":
            expression = "(" + " | ".join(parts) + ")"

        elif gate_type == "NOR":
            expression = "~(" + " | ".join(parts) + ")"

        elif gate_type == "XOR":
            expression = "(" + " ^ ".join(parts) + ")"

        elif gate_type == "XNOR":
            expression = "~(" + " ^ ".join(parts) + ")"

        else:
            raise ValueError("Unsupported gate.")

        expressions[gate["id"]] = expression

    result = {}

    for output in circuit["outputs"]:
        result[output["name"]] = expressions[output["source"]]

    return result


# --------------------------------------------------
# VERILOG: GATE LEVEL
# --------------------------------------------------

def generate_gate_level(circuit):
    inputs = circuit["inputs"]
    outputs = [o["name"] for o in circuit["outputs"]]

    lines = [
        "module logic_circuit(" +
        ", ".join(inputs + outputs) + ");",
        ""
    ]

    lines.append(
        "input " + ", ".join(inputs) + ";"
    )

    lines.append(
        "output " + ", ".join(outputs) + ";"
    )

    internal = [g["id"] for g in circuit["gates"]]

    if internal:
        lines.append("wire " + ", ".join(internal) + ";")

    lines.append("")

    for index, gate in enumerate(circuit["gates"], start=1):
        gate_type = gate["type"].lower()
        connections = ", ".join(
            [gate["id"]] + gate["inputs"]
        )

        lines.append(
            f"{gate_type} gate_{index}({connections});"
        )

    lines.append("")

    for output in circuit["outputs"]:
        lines.append(
            f"assign {output['name']} = {output['source']};"
        )

    lines.extend(["", "endmodule"])

    return "\n".join(lines)


# --------------------------------------------------
# VERILOG: DATAFLOW
# --------------------------------------------------

def generate_dataflow(circuit):
    inputs = circuit["inputs"]
    outputs = [o["name"] for o in circuit["outputs"]]

    expressions = {
        name: name for name in inputs
    }

    lines = [
        "module logic_circuit(" +
        ", ".join(inputs + outputs) + ");",
        "",
        "input " + ", ".join(inputs) + ";",
        "output " + ", ".join(outputs) + ";",
        ""
    ]

    for gate in circuit["gates"]:
        parts = [
            expressions[name]
            for name in gate["inputs"]
        ]

        gate_type = gate["type"]

        if gate_type == "NOT":
            expression = "~" + parts[0]

        elif gate_type == "AND":
            expression = " & ".join(parts)

        elif gate_type == "NAND":
            expression = "~(" + " & ".join(parts) + ")"

        elif gate_type == "OR":
            expression = " | ".join(parts)

        elif gate_type == "NOR":
            expression = "~(" + " | ".join(parts) + ")"

        elif gate_type == "XOR":
            expression = " ^ ".join(parts)

        elif gate_type == "XNOR":
            expression = "~(" + " ^ ".join(parts) + ")"

        else:
            raise ValueError("Unsupported gate.")

        expressions[gate["id"]] = "(" + expression + ")"

    for output in circuit["outputs"]:
        lines.append(
            f"assign {output['name']} = "
            f"{expressions[output['source']]};"
        )

    lines.extend(["", "endmodule"])

    return "\n".join(lines)


# --------------------------------------------------
# VERILOG: BEHAVIORAL
# --------------------------------------------------

def generate_behavioral(circuit):
    inputs = circuit["inputs"]
    outputs = [o["name"] for o in circuit["outputs"]]

    lines = [
        "module logic_circuit(" +
        ", ".join(inputs + outputs) + ");",
        "",
        "input " + ", ".join(inputs) + ";",
        "output reg " + ", ".join(outputs) + ";",
        "",
        "always @(*) begin"
    ]

    table = make_truth_table(circuit)

    selector = "{" + ", ".join(inputs) + "}"

    lines.append("    case (" + selector + ")")

    for _, row in table.iterrows():
        binary = "".join(str(int(row[name])) for name in inputs)

        assignments = " ".join(
            f"{name} = {int(row[name])};"
            for name in outputs
        )

        lines.append(
            f"        {len(inputs)}'b{binary}: begin "
            f"{assignments} end"
        )

    lines.extend([
        "        default: begin",
        *[
            f"            {name} = 1'b0;"
            for name in outputs
        ],
        "        end",
        "    endcase",
        "end",
        "",
        "endmodule"
    ])

    return "\n".join(lines)


# --------------------------------------------------
# SVG LOGIC GATE DIAGRAM
# --------------------------------------------------

def graph(circuit):
    inputs = circuit["inputs"]
    gates = circuit["gates"]
    outputs = circuit["outputs"]

    if not gates:
        return "<p>No gates are required for this circuit.</p>"

    gate_map = {
        gate["id"]: gate for gate in gates
    }

    # Calculate gate levels.
    levels = {}

    for gate in gates:
        levels[gate["id"]] = 1 + max(
            [levels.get(signal, 0) for signal in gate["inputs"]]
        )

    max_level = max(levels.values())

    layers = {}

    for gate in gates:
        level = levels[gate["id"]]
        layers.setdefault(level, []).append(gate)

    left = 270
    col_gap = 190
    gate_width = 105
    gate_height = 62

    max_layer_count = max(
        len(items) for items in layers.values()
    )

    max_rows = max(len(inputs), max_layer_count, len(outputs), 1)
    height = max(340, max_rows * 115 + 100)
    width = left + max_level * col_gap + 300

    positions = {}
    gate_boxes = {}

    def row_y(index, count):
        return 70 + (height - 140) * (index + 1) / (count + 1)

    for index, name in enumerate(inputs):
        positions[name] = (165, row_y(index, len(inputs)))

    for level in range(1, max_level + 1):
        items = layers.get(level, [])

        for index, gate in enumerate(items):
            x = left + (level - 1) * col_gap
            y = row_y(index, len(items))

            positions[gate["id"]] = (
                x + gate_width + 15,
                y
            )

            gate_boxes[gate["id"]] = (x, y)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="100%" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>',
        '.wire{stroke:#222;stroke-width:2;fill:none}',
        '.gate{stroke:#111;stroke-width:2.5;fill:#eaf3ff}',
        '.label{font:15px Arial;fill:#111}',
        '.small{font:12px Arial;fill:#111}',
        '</style>'
    ]

    # Draw primary input labels.
    for name in inputs:
        x, y = positions[name]

        parts.append(
            f'<text class="label" x="{x-55}" y="{y+5}" '
            f'text-anchor="end">{html.escape(name)}</text>'
        )

        parts.append(
            f'<path class="wire" d="M{x-45} {y} H{x}"/>'
        )

    # Draw wires and gates.
    for gate in gates:
        gid = gate["id"]
        gate_type = gate["type"]
        gx, gy = gate_boxes[gid]

        gate_inputs = gate["inputs"]
        count = len(gate_inputs)

        port_positions = [
            gy + (i - (count - 1) / 2) * 22
            for i in range(count)
        ]

        for signal, py in zip(gate_inputs, port_positions):
            sx, sy = positions[signal]
            mid = (sx + gx) / 2

            parts.append(
                f'<path class="wire" '
                f'd="M{sx} {sy} H{mid} V{py} H{gx}"/>'
            )

        # Draw the gate shape.
        if gate_type == "NOT":
            parts.append(
                f'<polygon class="gate" '
                f'points="{gx},{gy-29} {gx},{gy+29} '
                f'{gx+78},{gy}"/>'
            )
            parts.append(
                f'<circle cx="{gx+84}" cy="{gy}" r="6" '
                f'fill="white" stroke="#111" stroke-width="2"/>'
            )
            out_x = gx + 90

        elif gate_type in ("AND", "NAND"):
            parts.append(
                f'<path class="gate" '
                f'd="M{gx} {gy-30} H{gx+45} '
                f'A30 30 0 0 1 {gx+45} {gy+30} '
                f'H{gx} Z"/>'
            )

            if gate_type == "NAND":
                parts.append(
                    f'<circle cx="{gx+80}" cy="{gy}" r="6" '
                    f'fill="white" stroke="#111" stroke-width="2"/>'
                )
                out_x = gx + 86
            else:
                out_x = gx + 75

        elif gate_type in ("OR", "NOR", "XOR", "XNOR"):
            parts.append(
                f'<path class="gate" '
                f'd="M{gx} {gy-30} '
                f'Q{gx+28} {gy} {gx} {gy+30} '
                f'Q{gx+35} {gy+30} {gx+83} {gy} '
                f'Q{gx+35} {gy-30} {gx} {gy-30} Z"/>'
            )

            if gate_type in ("XOR", "XNOR"):
                parts.append(
                    f'<path d="M{gx-9} {gy-30} '
                    f'Q{gx+19} {gy} {gx-9} {gy+30}" '
                    f'fill="none" stroke="#111" stroke-width="2.5"/>'
                )

            if gate_type in ("NOR", "XNOR"):
                parts.append(
                    f'<circle cx="{gx+90}" cy="{gy}" r="6" '
                    f'fill="white" stroke="#111" stroke-width="2"/>'
                )
                out_x = gx + 96
            else:
                out_x = gx + 84

        else:
            out_x = gx + gate_width

        parts.append(
            f'<text class="small" x="{gx+38}" y="{gy+5}" '
            f'text-anchor="middle">{gate_type}</text>'
        )

        # Output wire.
        parts.append(
            f'<path class="wire" '
            f'd="M{out_x} {gy} H{positions[gid][0]}"/>'
        )

    # Draw final output wires.
    for index, output in enumerate(outputs):
        source = output["source"]
        sx, sy = positions[source]

        oy = row_y(index, len(outputs))
        end_x = width - 135

        parts.append(
            f'<path class="wire" '
            f'd="M{sx} {sy} H{end_x} V{oy} H{end_x+30}"/>'
        )

        parts.append(
            f'<text class="label" x="{end_x+38}" y="{oy+5}">'
            f'{html.escape(output["name"])}</text>'
        )

    parts.append("</svg>")

    return "\n".join(parts)


# --------------------------------------------------
# USER INTERFACE
# --------------------------------------------------

prompt = st.text_area(
    "Describe your logic circuit:",
    placeholder=(
        "Example: Design a full adder using AND, OR and XOR gates."
    ),
    height=110
)

if st.button("⚡ Generate Logic Circuit", type="primary"):
    if not prompt.strip():
        st.warning("Please enter a circuit description.")
    else:
        try:
            with st.spinner("AI is designing your circuit..."):
                circuit = generate_with_ai(prompt)
                circuit = validate_circuit(circuit)

            st.session_state["circuit"] = circuit
            st.success("Circuit generated successfully!")

        except Exception as error:
            st.error("Circuit generation failed.")
            st.exception(error)


# --------------------------------------------------
# DISPLAY RESULTS
# --------------------------------------------------

if "circuit" in st.session_state:
    circuit = st.session_state["circuit"]

    st.divider()
    st.header("1. Logic Circuit Diagram")

    try:
        svg = graph(circuit)
        components.html(svg, height=650, scrolling=True)
    except Exception as error:
        st.error("Could not draw the circuit diagram.")
        st.exception(error)

    st.divider()
    st.header("2. Circuit Details")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Primary Inputs**")
        st.write(", ".join(circuit["inputs"]))

    with col2:
        st.write("**Outputs**")
        st.write(", ".join(
            output["name"] for output in circuit["outputs"]
        ))

    st.write("**Gates Used**")

    gate_table = pd.DataFrame([
        {
            "Gate ID": gate["id"],
            "Gate Type": gate["type"],
            "Gate Inputs": ", ".join(gate["inputs"])
        }
        for gate in circuit["gates"]
    ])

    if not gate_table.empty:
        st.dataframe(gate_table, use_container_width=True)

    st.divider()
    st.header("3. Truth Table")

    truth_table = make_truth_table(circuit)
    st.dataframe(truth_table, use_container_width=True)

    st.divider()
    st.header("4. Boolean Expressions")

    expressions = boolean_expressions(circuit)

    for name, expression in expressions.items():
        st.code(f"{name} = {expression}", language="text")

    st.divider()
    st.header("5. Circuit Explanation")

    st.write(circuit.get(
        "explanation",
        "Explanation is not available."
    ))

    st.write("**Design Steps**")

    for index, step in enumerate(
        circuit.get("design_steps", []),
        start=1
    ):
        st.write(f"{index}. {step}")

    st.divider()
    st.header("6. Verilog Code")

    gate_code = generate_gate_level(circuit)
    dataflow_code = generate_dataflow(circuit)
    behavioral_code = generate_behavioral(circuit)

    tab1, tab2, tab3 = st.tabs([
        "Gate Level",
        "Dataflow",
        "Behavioral"
    ])

    with tab1:
        st.subheader("Gate-Level Modelling")
        st.caption("Uses built-in Verilog gate primitives.")
        st.code(gate_code, language="verilog")
        st.download_button(
            "Download Gate-Level Verilog",
            gate_code,
            file_name="gate_level.v",
            mime="text/plain"
        )

    with tab2:
        st.subheader("Dataflow Modelling")
        st.caption("Uses continuous assign statements.")
        st.code(dataflow_code, language="verilog")
        st.download_button(
            "Download Dataflow Verilog",
            dataflow_code,
            file_name="dataflow.v",
            mime="text/plain"
        )

    with tab3:
        st.subheader("Behavioral Modelling")
        st.caption("Uses an always block and case statement.")
        st.code(behavioral_code, language="verilog")
        st.download_button(
            "Download Behavioral Verilog",
            behavioral_code,
            file_name="behavioral.v",
            mime="text/plain"
        )

    st.success("All three Verilog versions are ready.")

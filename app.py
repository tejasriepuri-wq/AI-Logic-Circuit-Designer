
import os
import re
import json
import time
import html
import itertools

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from google import genai


# ==================================================
# 1. PAGE SETTINGS
# ==================================================

st.set_page_config(
    page_title="AI Logic Circuit Designer",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ AI-Based Logic Gate Circuit Designer")
st.write(
    "Describe a digital logic circuit and generate its "
    "logic diagram, truth table, Boolean expressions and Verilog code."
)


# ==================================================
# 2. API KEY
# ==================================================

def get_api_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass

    return os.getenv("GEMINI_API_KEY", "")


# ==================================================
# 3. GEMINI AI WITH MODEL FALLBACK
# ==================================================

def generate_with_ai(prompt):

    api_key = get_api_key()

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. Add your existing key "
            "in Streamlit Cloud → Settings → Secrets."
        )

    client = genai.Client(api_key=api_key)

    instruction = f"""
You are an expert digital logic circuit designer.

Design the digital circuit requested below.

USER REQUEST:
{prompt}

Return ONLY valid JSON. Do not use Markdown or code fences.

Use exactly this structure:

{{
  "inputs": ["A", "B"],
  "gates": [
    {{
      "id": "G1",
      "type": "XOR",
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

IMPORTANT RULES:

1. Supported gates: AND, OR, NOT, NAND, NOR, XOR, XNOR.
2. Give every gate a unique ID: G1, G2, G3, etc.
3. Gate inputs must be primary inputs or previously created gates.
4. Create gates in topological order.
5. NOT gates must have exactly one input.
6. Other gates must have at least two inputs.
7. Outputs must have a name and a source.
8. Output sources must be primary inputs or gate IDs.
9. Use multiple outputs when required, for example Full Adder Sum and Carry.
10. Use actual logic gates, not arithmetic operations.
11. Make sure the circuit implements the requested function correctly.
12. Keep explanations simple.
13. Return valid JSON only.
"""

    # Try these models in order.
    models = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite"
    ]

    errors = []

    for model_name in models:

        # Retry each model up to two times for temporary errors.
        for attempt in range(2):

            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=instruction
                )

                raw = response.text

                if not raw:
                    raise ValueError("Gemini returned an empty response.")

                raw = raw.strip()

                # Remove Markdown fences if present.
                raw = re.sub(
                    r"^```(?:json)?\s*",
                    "",
                    raw,
                    flags=re.IGNORECASE
                )
                raw = re.sub(r"\s*```$", "", raw)

                return json.loads(raw)

            except Exception as error:

                error_text = str(error)
                errors.append(model_name + ": " + error_text)

                temporary_error = any(
                    word in error_text.upper()
                    for word in [
                        "503",
                        "429",
                        "500",
                        "502",
                        "504",
                        "UNAVAILABLE",
                        "RESOURCE_EXHAUSTED",
                        "INTERNAL",
                        "NOT FOUND",
                        "404"
                    ]
                )

                # Try another model for temporary/model availability errors.
                if temporary_error:
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    break

                # Do not retry authentication or other permanent errors.
                raise RuntimeError(
                    f"Gemini request failed using {model_name}: {error_text}"
                )

    raise RuntimeError(
        "All available Gemini model attempts failed. "
        "Google's AI service may be temporarily busy.\n\n"
        + "\n".join(errors[-3:])
    )


# ==================================================
# 4. CIRCUIT VALIDATION
# ==================================================

VALID_GATES = {
    "AND", "OR", "NOT", "NAND",
    "NOR", "XOR", "XNOR"
}


def validate_circuit(circuit):

    if not isinstance(circuit, dict):
        raise ValueError("Invalid circuit response.")

    inputs = circuit.get("inputs")
    gates = circuit.get("gates")
    outputs = circuit.get("outputs")

    if not isinstance(inputs, list) or not inputs:
        raise ValueError("Circuit must contain primary inputs.")

    if len(inputs) > 8:
        raise ValueError("Maximum supported primary inputs: 8.")

    if len(set(inputs)) != len(inputs):
        raise ValueError("Duplicate primary input names.")

    for name in inputs:
        if not isinstance(name, str):
            raise ValueError("Invalid input name.")

        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError("Invalid input name: " + name)

    if not isinstance(gates, list):
        raise ValueError("Invalid gate list.")

    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Circuit must contain outputs.")

    available = set(inputs)
    gate_ids = set()

    for gate in gates:

        if not isinstance(gate, dict):
            raise ValueError("Invalid gate information.")

        gid = gate.get("id")
        gate_type = str(gate.get("type", "")).upper()
        gate_inputs = gate.get("inputs")

        if not isinstance(gid, str):
            raise ValueError("Invalid gate ID.")

        if not re.fullmatch(r"[A-Za-z_]\w*", gid):
            raise ValueError("Invalid gate ID: " + gid)

        if gid in available:
            raise ValueError("Duplicate gate ID: " + gid)

        if gate_type not in VALID_GATES:
            raise ValueError("Unsupported gate: " + gate_type)

        if not isinstance(gate_inputs, list) or not gate_inputs:
            raise ValueError("Gate " + gid + " has no inputs.")

        if gate_type == "NOT" and len(gate_inputs) != 1:
            raise ValueError("NOT gate needs exactly one input.")

        if gate_type != "NOT" and len(gate_inputs) < 2:
            raise ValueError(
                gate_type + " gate needs at least two inputs."
            )

        for signal in gate_inputs:
            if signal not in available:
                raise ValueError(
                    f"Gate {gid} uses unknown or not-yet-created "
                    f"signal: {signal}"
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

        if not isinstance(name, str):
            raise ValueError("Invalid output name.")

        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError("Invalid output name: " + name)

        if name in available or name in output_names:
            raise ValueError("Duplicate output name: " + name)

        if source not in available:
            raise ValueError("Unknown output source: " + str(source))

        output_names.add(name)

    return circuit


# ==================================================
# 5. LOGIC GATE EVALUATION
# ==================================================

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

    raise ValueError("Unknown gate: " + gate_type)


def calculate_outputs(circuit, input_values):

    signals = dict(input_values)

    for gate in circuit["gates"]:

        values = [
            signals[name]
            for name in gate["inputs"]
        ]

        signals[gate["id"]] = evaluate_gate(
            gate["type"],
            values
        )

    result = {}

    for output in circuit["outputs"]:
        result[output["name"]] = signals[output["source"]]

    return result


# ==================================================
# 6. TRUTH TABLE
# ==================================================

def make_truth_table(circuit):

    inputs = circuit["inputs"]
    rows = []

    for combination in itertools.product(
        [0, 1],
        repeat=len(inputs)
    ):

        input_values = dict(zip(inputs, combination))

        output_values = calculate_outputs(
            circuit,
            input_values
        )

        rows.append({
            **input_values,
            **output_values
        })

    return pd.DataFrame(rows)


# ==================================================
# 7. BOOLEAN EXPRESSIONS
# ==================================================

def boolean_expressions(circuit):

    expressions = {
        name: name
        for name in circuit["inputs"]
    }

    for gate in circuit["gates"]:

        parts = [
            expressions[name]
            for name in gate["inputs"]
        ]

        gate_type = gate["type"]

        if gate_type == "NOT":
            expression = "~(" + parts[0] + ")"

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


# ==================================================
# 8. VERILOG GATE LEVEL
# ==================================================

def generate_gate_level(circuit):

    inputs = circuit["inputs"]
    outputs = [o["name"] for o in circuit["outputs"]]

    lines = [
        "module logic_circuit(" +
        ", ".join(inputs + outputs) + ");",
        "",
        "input " + ", ".join(inputs) + ";",
        "output " + ", ".join(outputs) + ";",
        ""
    ]

    internal = [
        gate["id"]
        for gate in circuit["gates"]
    ]

    if internal:
        lines.append("wire " + ", ".join(internal) + ";")
        lines.append("")

    for index, gate in enumerate(circuit["gates"], start=1):

        primitive = gate["type"].lower()

        connections = ", ".join(
            [gate["id"]] + gate["inputs"]
        )

        lines.append(
            f"{primitive} gate_{index}({connections});"
        )

    lines.append("")

    for output in circuit["outputs"]:
        lines.append(
            f"assign {output['name']} = {output['source']};"
        )

    lines.extend(["", "endmodule"])

    return "\n".join(lines)


# ==================================================
# 9. VERILOG DATAFLOW
# ==================================================

def generate_dataflow(circuit):

    inputs = circuit["inputs"]
    outputs = [o["name"] for o in circuit["outputs"]]

    expressions = {
        name: name
        for name in inputs
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
            expression = "~(" + parts[0] + ")"

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


# ==================================================
# 10. VERILOG BEHAVIORAL
# ==================================================

def generate_behavioral(circuit):

    inputs = circuit["inputs"]
    outputs = [o["name"] for o in circuit["outputs"]]

    table = make_truth_table(circuit)

    selector = "{" + ", ".join(inputs) + "}"

    lines = [
        "module logic_circuit(" +
        ", ".join(inputs + outputs) + ");",
        "",
        "input " + ", ".join(inputs) + ";",
        "output reg " + ", ".join(outputs) + ";",
        "",
        "always @(*) begin",
        f"    case ({selector})"
    ]

    for _, row in table.iterrows():

        binary = "".join(
            str(int(row[name]))
            for name in inputs
        )

        assignments = " ".join(
            f"{name} = {int(row[name])};"
            for name in outputs
        )

        lines.append(
            f"        {len(inputs)}'b{binary}: begin "
            f"{assignments} end"
        )

    lines.append("        default: begin")

    for name in outputs:
        lines.append(f"            {name} = 1'b0;")

    lines.extend([
        "        end",
        "    endcase",
        "end",
        "",
        "endmodule"
    ])

    return "\n".join(lines)


# ==================================================
# 11. SVG LOGIC GATE DIAGRAM
# ==================================================

def graph(circuit):

    inputs = circuit["inputs"]
    gates = circuit["gates"]
    outputs = circuit["outputs"]

    if not gates:
        return (
            "<p>This circuit directly connects an input "
            "to an output and does not need a gate.</p>"
        )

    # Calculate gate depth.
    levels = {}

    for gate in gates:
        levels[gate["id"]] = 1 + max(
            [levels.get(signal, 0) for signal in gate["inputs"]]
        )

    layers = {}

    for gate in gates:
        level = levels[gate["id"]]
        layers.setdefault(level, []).append(gate)

    max_level = max(levels.values())
    max_layer_count = max(len(v) for v in layers.values())

    max_rows = max(
        len(inputs),
        len(outputs),
        max_layer_count,
        1
    )

    height = max(380, 120 + max_rows * 115)
    width = 300 + max_level * 210 + 300

    left = 260
    col_gap = 210

    positions = {}
    gate_boxes = {}

    def row_y(index, count):
        return 65 + (height - 130) * (index + 1) / (count + 1)

    # Primary input positions.
    for index, name in enumerate(inputs):
        positions[name] = (145, row_y(index, len(inputs)))

    # Gate positions.
    for level in range(1, max_level + 1):

        items = layers.get(level, [])

        for index, gate in enumerate(items):

            gx = left + (level - 1) * col_gap
            gy = row_y(index, len(items))

            gate_boxes[gate["id"]] = (gx, gy)

            # Output connection position.
            positions[gate["id"]] = (gx + 115, gy)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="100%" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>',
        '.wire{stroke:#222;stroke-width:2;fill:none}',
        '.gate{stroke:#111;stroke-width:2.5;fill:#eaf3ff}',
        '.label{font:15px Arial;fill:#111}',
        '.small{font:12px Arial;fill:#111}',
        '</style>'
    ]

    # Draw input labels and short wires.
    for name in inputs:

        x, y = positions[name]

        svg.append(
            f'<text class="label" x="{x-55}" y="{y+5}" '
            f'text-anchor="end">{html.escape(name)}</text>'
        )

        svg.append(
            f'<path class="wire" d="M{x-45} {y} H{x}"/>'
        )

    # Draw each gate and its input wires.
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

            svg.append(
                f'<path class="wire" '
                f'd="M{sx} {sy} H{mid} V{py} H{gx}"/>'
            )

        # AND and NAND symbols.
        if gate_type in ("AND", "NAND"):

            svg.append(
                f'<path class="gate" '
                f'd="M{gx} {gy-30} H{gx+43} '
                f'A30 30 0 0 1 {gx+43} {gy+30} '
                f'H{gx} Z"/>'
            )

            if gate_type == "NAND":

                svg.append(
                    f'<circle cx="{gx+80}" cy="{gy}" r="6" '
                    f'fill="white" stroke="#111" stroke-width="2"/>'
                )

                out_x = gx + 86

            else:
                out_x = gx + 75

        # NOT symbol.
        elif gate_type == "NOT":

            svg.append(
                f'<polygon class="gate" '
                f'points="{gx},{gy-29} {gx},{gy+29} '
                f'{gx+78},{gy}"/>'
            )

            svg.append(
                f'<circle cx="{gx+84}" cy="{gy}" r="6" '
                f'fill="white" stroke="#111" stroke-width="2"/>'
            )

            out_x = gx + 90

        # OR, NOR, XOR and XNOR symbols.
        else:

            svg.append(
                f'<path class="gate" '
                f'd="M{gx} {gy-30} '
                f'Q{gx+28} {gy} {gx} {gy+30} '
                f'Q{gx+35} {gy+30} {gx+83} {gy} '
                f'Q{gx+35} {gy-30} {gx} {gy-30} Z"/>'
            )

            if gate_type in ("XOR", "XNOR"):

                svg.append(
                    f'<path d="M{gx-9} {gy-30} '
                    f'Q{gx+19} {gy} {gx-9} {gy+30}" '
                    f'fill="none" stroke="#111" stroke-width="2.5"/>'
                )

            if gate_type in ("NOR", "XNOR"):

                svg.append(
                    f'<circle cx="{gx+90}" cy="{gy}" r="6" '
                    f'fill="white" stroke="#111" stroke-width="2"/>'
                )

                out_x = gx + 96

            else:
                out_x = gx + 84

        svg.append(
            f'<text class="small" x="{gx+38}" y="{gy+5}" '
            f'text-anchor="middle">{gate_type}</text>'
        )

        # Connect gate output to its signal position.
        svg.append(
            f'<path class="wire" '
            f'd="M{out_x} {gy} H{positions[gid][0]}"/>'
        )

    # Draw output wires and names.
    for index, output in enumerate(outputs):

        source = output["source"]
        sx, sy = positions[source]

        oy = row_y(index, len(outputs))
        end_x = width - 135

        svg.append(
            f'<path class="wire" '
            f'd="M{sx} {sy} H{end_x} V{oy} H{end_x+30}"/>'
        )

        svg.append(
            f'<text class="label" x="{end_x+38}" y="{oy+5}">'
            f'{html.escape(output["name"])}</text>'
        )

    svg.append("</svg>")

    return "\n".join(svg)


# ==================================================
# 12. PROMPT FORM
# ==================================================

with st.form("circuit_form"):

    prompt = st.text_area(
        "Describe your logic circuit:",
        placeholder=(
            "Example: Design a full adder with inputs A, B and Cin."
        ),
        height=120
    )

    submitted = st.form_submit_button(
        "⚡ Generate Logic Circuit",
        type="primary"
    )


# ==================================================
# 13. GENERATE CIRCUIT
# ==================================================

if submitted:

    if not prompt.strip():

        st.warning("Please enter a circuit description.")

    else:

        try:

            with st.spinner(
                "AI is designing your circuit. Please wait..."
            ):

                circuit = generate_with_ai(prompt)
                circuit = validate_circuit(circuit)

                # Test the circuit calculations before saving.
                make_truth_table(circuit)

                # Test all code generators.
                generate_gate_level(circuit)
                generate_dataflow(circuit)
                generate_behavioral(circuit)

            st.session_state["circuit"] = circuit
            st.success("Circuit generated successfully!")

        except Exception as error:

            st.error("Circuit generation failed.")
            st.write(str(error))

            if "All available Gemini model attempts failed" in str(error):
                st.warning(
                    "This is a temporary AI service availability problem. "
                    "Wait a little and try again. Your project code and "
                    "API key do not need to be recreated."
                )


# ==================================================
# 14. DISPLAY CIRCUIT RESULTS
# ==================================================

if "circuit" in st.session_state:

    circuit = st.session_state["circuit"]

    st.divider()
    st.header("1. Logic Circuit Diagram")

    try:

        svg_code = graph(circuit)

        components.html(
            svg_code,
            height=650,
            scrolling=True
        )

    except Exception as error:

        st.error("Circuit diagram could not be displayed.")
        st.write(str(error))

    st.divider()
    st.header("2. Circuit Details")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Primary Inputs**")
        st.write(", ".join(circuit["inputs"]))

    with col2:
        st.write("**Outputs**")
        st.write(
            ", ".join(
                output["name"]
                for output in circuit["outputs"]
            )
        )

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
        st.dataframe(
            gate_table,
            use_container_width=True
        )

    st.divider()
    st.header("3. Truth Table")

    truth_table = make_truth_table(circuit)

    st.dataframe(
        truth_table,
        use_container_width=True
    )

    st.divider()
    st.header("4. Boolean Expressions")

    expressions = boolean_expressions(circuit)

    for name, expression in expressions.items():

        st.write(f"**Output {name}**")
        st.code(
            f"{name} = {expression}",
            language="text"
        )

    st.divider()
    st.header("5. Circuit Explanation")

    st.write(
        circuit.get(
            "explanation",
            "Explanation is not available."
        )
    )

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

        st.code(
            gate_code,
            language="verilog"
        )

        st.download_button(
            "Download Gate-Level Verilog",
            gate_code,
            file_name="gate_level.v",
            mime="text/plain"
        )

    with tab2:

        st.subheader("Dataflow Modelling")
        st.caption("Uses continuous assign statements.")

        st.code(
            dataflow_code,
            language="verilog"
        )

        st.download_button(
            "Download Dataflow Verilog",
            dataflow_code,
            file_name="dataflow.v",
            mime="text/plain"
        )

    with tab3:

        st.subheader("Behavioral Modelling")
        st.caption("Uses always and case statements.")

        st.code(
            behavioral_code,
            language="verilog"
        )

        st.download_button(
            "Download Behavioral Verilog",
            behavioral_code,
            file_name="behavioral.v",
            mime="text/plain"
        )

    st.success("All three Verilog versions have been generated.")

import os
import re
import json
import itertools
import html
from collections import defaultdict

import pandas as pd
import streamlit as st
from google import genai

# ============================================================
# AI-BASED LOGIC GATE CIRCUIT DESIGNER - UPGRADED APP
# Supports complex COMBINATIONAL circuits represented as
# networks of two-input gates and one-input NOT gates.
# ============================================================

st.set_page_config(
    page_title="Agentic AI Logic Circuit Designer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------- MODERN FRONTEND THEME ---------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root { color-scheme: dark; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: radial-gradient(circle at 12% 0%, #172554 0, #0b1224 36%, #070b16 100%); color: #e5edff; }
[data-testid="stHeader"] { background: rgba(7,11,22,.82); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#101a32 0%,#0b1224 100%); border-right: 1px solid #263657; }
[data-testid="stSidebar"] * { color: #e5edff; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1450px; }
.hero { padding: 28px 30px; border: 1px solid rgba(103,232,249,.28); border-radius: 22px; background: linear-gradient(120deg,rgba(30,64,175,.38),rgba(88,28,135,.25)),rgba(15,23,42,.88); box-shadow: 0 16px 45px rgba(0,0,0,.24); margin-bottom: 22px; }
.hero-kicker { color:#67e8f9; font-size:12px; font-weight:800; letter-spacing:2px; text-transform:uppercase; }
.hero h1 { color:#f8fbff; font-size:clamp(27px,4vw,42px); line-height:1.15; margin:10px 0 9px; font-weight:800; }
.hero p { color:#c4d2ee; font-size:15px; margin:0; max-width:900px; }
.section-card { border:1px solid #263858; background:rgba(15,23,42,.78); border-radius:18px; padding:18px 20px; margin:12px 0; }
div[data-testid="stTextArea"] textarea, div[data-testid="stTextInput"] input { background:#101b31!important; color:#f1f5ff!important; border:1px solid #385078!important; border-radius:12px!important; }
.stButton>button, .stDownloadButton>button { border-radius:12px; border:1px solid #38bdf8; background:linear-gradient(90deg,#0891b2,#6366f1); color:white; font-weight:700; min-height:44px; transition:all .2s ease; }
.stButton>button:hover, .stDownloadButton>button:hover { border-color:#a5f3fc; color:white; box-shadow:0 0 22px rgba(34,211,238,.22); transform:translateY(-1px); }
.stTabs [data-baseweb="tab-list"] { gap:7px; border-bottom:1px solid #2b3d5d; }
.stTabs [data-baseweb="tab"] { background:#111d34; border:1px solid #263858; border-radius:10px 10px 0 0; color:#cbd5e1; padding:10px 14px; }
.stTabs [aria-selected="true"] { background:#164e63!important; color:#ecfeff!important; border-color:#22d3ee!important; }
[data-testid="stDataFrame"] { border:1px solid #2d4265; border-radius:12px; overflow:hidden; }
.stAlert { border-radius:12px; }
h1,h2,h3,h4 { color:#f1f5ff; }
[data-testid="stMetric"] { background:#111d34; border:1px solid #2b4165; padding:14px; border-radius:14px; }
hr { border-color:#263858; }
</style>
<div class="hero">
  <div class="hero-kicker">ECE • DIGITAL DESIGN • AI WORKSPACE</div>
  <h1>⚡ Agentic AI-Based Logic Gate Circuit Designer</h1>
  <p>Describe a digital circuit in simple English. The AI plans and validates the gate connections, calculates the complete truth table, derives Boolean expressions, and generates Verilog in three coding styles.</p>
</div>
""", unsafe_allow_html=True)

ALLOWED_GATES = {"AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR"}
MAX_INPUTS = 8
MAX_GATES = 120
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# --------------------------- API KEY ---------------------------

def get_api_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY", "")


# --------------------------- VALIDATION AGENT ---------------------------

def validate(circuit):
    """Validate the AI netlist before using it in any output generator."""
    if not isinstance(circuit, dict):
        raise ValueError("AI response must be a JSON object.")

    inputs = circuit.get("inputs", [])
    gates = circuit.get("gates", [])
    outputs = circuit.get("outputs", [])

    if not outputs and circuit.get("output"):
        outputs = [circuit["output"]]

    if not isinstance(inputs, list) or not 1 <= len(inputs) <= MAX_INPUTS:
        raise ValueError(f"Use between 1 and {MAX_INPUTS} primary input signals.")

    if any(not isinstance(x, str) or not IDENTIFIER.fullmatch(x) for x in inputs):
        raise ValueError("Input names must be valid Verilog identifiers, e.g. A, B, A0, SEL0.")
    if len(set(inputs)) != len(inputs):
        raise ValueError("Input names must be unique.")

    if not isinstance(gates, list) or not 1 <= len(gates) <= MAX_GATES:
        raise ValueError(f"The circuit must contain between 1 and {MAX_GATES} gates.")

    known = set(inputs)
    gate_ids = set()
    normalized_gates = []

    for index, original in enumerate(gates, start=1):
        if not isinstance(original, dict):
            raise ValueError(f"Gate {index} is not a valid object.")

        gate = dict(original)
        gate_type = str(gate.get("type", "")).upper().strip()
        gate_id = str(gate.get("id", f"G{index}")).strip()
        gate_inputs = gate.get("inputs", [])
        gate_output = gate.get("output", "")

        if gate_type not in ALLOWED_GATES:
            raise ValueError(f"Unsupported gate type: {gate_type}")
        if not IDENTIFIER.fullmatch(gate_id) or gate_id in gate_ids:
            raise ValueError(f"Invalid or duplicate gate ID: {gate_id}")
        if not isinstance(gate_output, str) or not IDENTIFIER.fullmatch(gate_output):
            raise ValueError(f"Gate {gate_id} has an invalid output signal name.")
        if gate_output in known:
            raise ValueError(f"Duplicate signal name: {gate_output}")

        expected = 1 if gate_type == "NOT" else 2
        if not isinstance(gate_inputs, list) or len(gate_inputs) != expected:
            raise ValueError(f"{gate_type} gate {gate_id} must have {expected} input(s).")
        if any(not isinstance(signal, str) or signal not in known for signal in gate_inputs):
            raise ValueError(
                f"Gate {gate_id} refers to an unknown signal. "
                "List gates in execution order: source gates before dependent gates."
            )

        gate["id"] = gate_id
        gate["type"] = gate_type
        gate["inputs"] = gate_inputs
        gate["output"] = gate_output

        normalized_gates.append(gate)
        gate_ids.add(gate_id)
        known.add(gate_output)

    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Provide at least one output signal.")
    if any(not isinstance(x, str) or x not in known for x in outputs):
        raise ValueError("Every output must refer to a declared input or generated gate signal.")
    if len(set(outputs)) != len(outputs):
        raise ValueError("Output signal names must be unique.")

    circuit["inputs"] = inputs
    circuit["gates"] = normalized_gates
    circuit["outputs"] = outputs
    circuit["output"] = outputs[0]
    circuit["explanation"] = str(circuit.get("explanation", "Circuit generated from your requirement."))
    circuit["design_steps"] = circuit.get("design_steps", [])
    return circuit


# --------------------------- AI PLANNING AGENT ---------------------------

def ask_ai(prompt, api_key, model):
    client = genai.Client(api_key=api_key)

    instructions = f"""
You are the circuit-planning agent for an educational digital logic design tool.
Convert the user's request into a combinational digital circuit made from basic gates.

Return ONLY valid JSON. Do not add Markdown fences or extra text.
Use exactly this schema:
{{
  "title": "short circuit title",
  "inputs": ["A", "B"],
  "gates": [
    {{"id": "G1", "type": "AND", "inputs": ["A", "B"], "output": "W1"}},
    {{"id": "G2", "type": "NOT", "inputs": ["W1"], "output": "Y"}}
  ],
  "outputs": ["Y"],
  "explanation": "Explain the circuit in simple words.",
  "design_steps": ["Step 1", "Step 2"]
}}

STRICT DESIGN RULES:
- Allowed gates only: AND, OR, NOT, NAND, NOR, XOR, XNOR.
- NOT has exactly one input. Every other gate has exactly two inputs.
- Use scalar primary input names only, such as A, B, A0, A1, B0, B1, S0.
- Maximum {MAX_INPUTS} primary input signals and maximum {MAX_GATES} gates.
- Do not use bus names, brackets, constants, arithmetic operators, or undefined signals.
- List gates in execution order. A gate can use only primary inputs or earlier gate outputs.
- Give every gate a unique ID and a unique output signal.
- Outputs must be names of primary inputs or gate outputs.
- Use intermediate signals W1, W2, W3, etc.
- Create every output requested by the user.
- For a half adder, outputs should be Sum and Carry.
- For a full adder, outputs should be Sum and Cout.
- For multi-bit adders, use separate scalar bits (A0, A1, ... and B0, B1, ...).
- For a multiplexer, include select inputs and implement the selection logic.
- For a decoder/encoder, provide all required output signals.
- For a comparator, provide the requested comparison outputs (for example GT, EQ, LT).
- For complex circuits, create the complete gate network, not just a high-level block named after the circuit.
- Use no sequential elements, clocks, flip-flops, latches or memories in this version.
- Do not invent unsupported gate types.
- Keep the explanation concise and technically correct.
"""
    response = client.models.generate_content(
        model=model,
        contents=instructions + "\n\nUSER CIRCUIT REQUIREMENT:\n" + prompt,
    )

    raw = (response.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise ValueError("AI did not return valid JSON. Try a clearer circuit description.")
        data = json.loads(match.group(0))

    return validate(data)


# --------------------------- LOGIC EVALUATION AGENT ---------------------------

def evaluate_gate(gate_type, values):
    a = values[0]
    b = values[1] if len(values) > 1 else None

    if gate_type == "NOT":
        return 1 - a
    if gate_type == "AND":
        return a & b
    if gate_type == "OR":
        return a | b
    if gate_type == "NAND":
        return 1 - (a & b)
    if gate_type == "NOR":
        return 1 - (a | b)
    if gate_type == "XOR":
        return a ^ b
    if gate_type == "XNOR":
        return 1 - (a ^ b)
    raise ValueError(f"Unsupported gate: {gate_type}")


def evaluate_circuit(circuit, primary_values):
    values = dict(primary_values)
    for gate in circuit["gates"]:
        gate_inputs = [values[name] for name in gate["inputs"]]
        values[gate["output"]] = evaluate_gate(gate["type"], gate_inputs)
    return values


def make_truth_table(circuit):
    rows = []
    for bits in itertools.product([0, 1], repeat=len(circuit["inputs"])):
        primary = dict(zip(circuit["inputs"], bits))
        values = evaluate_circuit(circuit, primary)
        row = {name: values[name] for name in circuit["inputs"]}
        row.update({name: values[name] for name in circuit["outputs"]})
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------- BOOLEAN EXPRESSION AGENT ---------------------------

VERILOG_OPERATOR = {
    "AND": "&", "OR": "|", "NAND": "~&",
    "NOR": "~|", "XOR": "^", "XNOR": "~^"
}
BOOLEAN_OPERATOR = {
    "AND": "·", "OR": "+", "NAND": " NAND ",
    "NOR": " NOR ", "XOR": " ⊕ ", "XNOR": " XNOR "
}


def make_boolean_expressions(circuit):
    expressions = {name: name for name in circuit["inputs"]}
    for gate in circuit["gates"]:
        if gate["type"] == "NOT":
            expr = f"¬({expressions[gate['inputs'][0]]})"
        else:
            left, right = [expressions[x] for x in gate["inputs"]]
            expr = f"({left}{BOOLEAN_OPERATOR[gate['type']]}{right})"
        expressions[gate["output"]] = expr
    return {out: f"{out} = {expressions[out]}" for out in circuit["outputs"]}


# --------------------------- VERILOG GENERATORS ---------------------------

def verilog_header(circuit, style):
    ports = circuit["inputs"] + circuit["outputs"]
    lines = [
        f"// {style} modeling style",
        "// Generated from the validated gate-level circuit.",
        "module logic_circuit(" + ", ".join(ports) + ");",
        "input " + ", ".join(circuit["inputs"]) + ";",
    ]
    return lines


def make_dataflow_verilog(circuit):
    outputs = set(circuit["outputs"])
    lines = verilog_header(circuit, "DATAFLOW")
    lines.append("output " + ", ".join(circuit["outputs"]) + ";")
    internal = [g["output"] for g in circuit["gates"] if g["output"] not in outputs]
    if internal:
        lines.append("wire " + ", ".join(internal) + ";")

    for gate in circuit["gates"]:
        sig = gate["inputs"]
        typ = gate["type"]
        if typ == "NOT":
            expression = f"~{sig[0]}"
        elif typ in ("NAND", "NOR", "XNOR"):
            expression = f"({sig[0]} {VERILOG_OPERATOR[typ]} {sig[1]})"
        else:
            expression = f"({sig[0]} {VERILOG_OPERATOR[typ]} {sig[1]})"
        lines.append(f"assign {gate['output']} = {expression};")

    lines.append("endmodule")
    return "\n".join(lines)


def make_gatelevel_verilog(circuit):
    outputs = set(circuit["outputs"])
    lines = verilog_header(circuit, "GATE LEVEL")
    lines.append("output " + ", ".join(circuit["outputs"]) + ";")
    internal = [g["output"] for g in circuit["gates"] if g["output"] not in outputs]
    if internal:
        lines.append("wire " + ", ".join(internal) + ";")

    primitive = {
        "AND": "and", "OR": "or", "NOT": "not",
        "NAND": "nand", "NOR": "nor", "XOR": "xor", "XNOR": "xnor"
    }
    for index, gate in enumerate(circuit["gates"], start=1):
        connections = [gate["output"]] + gate["inputs"]
        lines.append(f"{primitive[gate['type']]} gate{index}({', '.join(connections)});")
    lines.append("endmodule")
    return "\n".join(lines)


def make_behavioral_verilog(circuit):
    """Generate a combinational always block implementing the same validated netlist."""
    outputs = set(circuit["outputs"])
    lines = [
        "// BEHAVIORAL modeling style",
        "// Combinational logic using an always @(*) block.",
        "module logic_circuit(" + ", ".join(circuit["inputs"] + circuit["outputs"]) + ");",
        "input " + ", ".join(circuit["inputs"]) + ";",
        "output reg " + ", ".join(circuit["outputs"]) + ";",
    ]
    internal = [g["output"] for g in circuit["gates"] if g["output"] not in outputs]
    if internal:
        lines.append("reg " + ", ".join(internal) + ";")

    lines.append("always @(*) begin")
    for gate in circuit["gates"]:
        sig = gate["inputs"]
        typ = gate["type"]
        if typ == "NOT":
            expression = f"~{sig[0]}"
        else:
            expression = f"({sig[0]} {VERILOG_OPERATOR[typ]} {sig[1]})"
        lines.append(f"    {gate['output']} = {expression};")
    lines.append("end")
    lines.append("endmodule")
    return "\n".join(lines)


# --------------------------- SVG CIRCUIT DIAGRAM ---------------------------

def make_gate_svg(circuit):
    """Render recognizable gate outlines (not rectangular flowchart boxes)."""
    gates = circuit["gates"]
    inputs = circuit["inputs"]
    outputs = circuit["outputs"]

    depth = {}
    for gate in gates:
        depth[gate["output"]] = 1 + max(
            [depth.get(signal, 0) for signal in gate["inputs"]],
            default=0
        )

    layers = defaultdict(list)
    for gate in gates:
        layers[depth[gate["output"]]].append(gate)

    max_depth = max(depth.values(), default=1)
    x_step = 190
    gate_x_start = 220
    max_layer_count = max([len(v) for v in layers.values()] + [1])
    height = max(260, 115 * max(len(inputs), max_layer_count, len(outputs)) + 80)
    width = gate_x_start + max_depth * x_step + 180

    positions = {}
    for level, layer_gates in layers.items():
        for row, gate in enumerate(layer_gates):
            y = 65 + row * 115
            positions[gate["output"]] = (gate_x_start + (level - 1) * x_step, y)

    input_positions = {
        name: (35, 70 + index * 105)
        for index, name in enumerate(inputs)
    }

    signal_points = {
        name: (x + 45, y + 8)
        for name, (x, y) in input_positions.items()
    }

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {width} {height}" role="img" aria-label="Logic gate circuit">',
        """<defs><style>
        .wire{stroke:#334155;stroke-width:2.2;fill:none;stroke-linecap:round;stroke-linejoin:round}
        .gate{stroke:#155e9a;stroke-width:2.4;fill:#eaf4ff}
        .txt{font: bold 13px Arial;fill:#12304a}
        .pin{font:12px Arial;fill:#334155}
        .bubble{stroke:#155e9a;stroke-width:2.2;fill:white}
        </style></defs>""",
        f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="12" fill="#fff" stroke="#dbe4ee"/>'
    ]

    for name, (x, y) in input_positions.items():
        parts.append(f'<text x="{x}" y="{y}" class="txt">{html.escape(name)}</text>')
        parts.append(f'<circle cx="{x+45}" cy="{y+8}" r="3.5" fill="#155e9a"/>')

    for gate in gates:
        gx, gy = positions[gate["output"]]
        typ = gate["type"]
        pin_ys = [gy + 25] if typ == "NOT" else [gy + 20, gy + 50]

        for idx, source in enumerate(gate["inputs"]):
            sx, sy = signal_points[source]
            tx, ty = gx, pin_ys[idx]
            bend = max(sx + 18, tx - 22)
            parts.append(f'<path class="wire" d="M{sx} {sy} H{bend} V{ty} H{tx}"/>')

        if typ in ("AND", "NAND"):
            parts.append(f'<path class="gate" d="M{gx} {gy} L{gx+48} {gy} A35 35 0 0 1 {gx+48} {gy+70} L{gx} {gy+70} Z"/>')
        elif typ in ("OR", "NOR", "XOR", "XNOR"):
            parts.append(f'<path class="gate" d="M{gx} {gy} Q{gx+42} {gy+3} {gx+100} {gy+35} Q{gx+42} {gy+67} {gx} {gy+70} Q{gx+25} {gy+35} {gx} {gy} Z"/>')
            if typ in ("XOR", "XNOR"):
                parts.append(f'<path class="wire" d="M{gx-10} {gy} Q{gx+15} {gy+35} {gx-10} {gy+70}"/>')
        elif typ == "NOT":
            parts.append(f'<path class="gate" d="M{gx} {gy} L{gx+82} {gy+35} L{gx} {gy+70} Z"/>')

        inverted = typ in ("NAND", "NOR", "NOT", "XNOR")
        if inverted:
            parts.append(f'<circle class="bubble" cx="{gx+105}" cy="{gy+35}" r="5"/>')
        out_x = gx + (112 if inverted else 100)
        out_y = gy + 35
        parts.append(f'<text class="txt" x="{gx+45}" y="{gy+40}" text-anchor="middle">{html.escape(typ)}</text>')
        parts.append(f'<text class="pin" x="{gx+48}" y="{gy+91}" text-anchor="middle">{html.escape(gate["id"])}</text>')
        parts.append(f'<circle cx="{out_x}" cy="{out_y}" r="3.5" fill="#155e9a"/>')
        signal_points[gate["output"]] = (out_x, out_y)

    # Draw output labels at the right of their source signals.
    for index, output in enumerate(outputs):
        sx, sy = signal_points[output]
        label_x = width - 85
        # Route output wire to the right edge.
        parts.append(f'<path class="wire" d="M{sx} {sy} H{label_x-10}"/>')
        parts.append(f'<circle cx="{label_x-10}" cy="{sy}" r="3.5" fill="#155e9a"/>')
        parts.append(f'<text class="txt" x="{label_x}" y="{sy+5}">{html.escape(output)}</text>')

    parts.append("</svg>")
    return "".join(parts)


# --------------------------- UI ---------------------------

with st.sidebar:
    st.header("⚙️ AI Settings")
    api_key = st.text_input(
        "Gemini API key",
        value=get_api_key(),
        type="password",
        help="Reuse your existing active Gemini API key. Do not share it."
    )
    model_name = st.text_input("Gemini model", value="gemini-2.5-flash")
    st.caption("If this model is unavailable for your key, enter a model name enabled in your Google AI Studio account.")
    st.divider()
    st.markdown("**Agent workflow**")
    st.markdown(
        "1. Understand prompt\n"
        "2. Plan gate network\n"
        "3. Validate connections\n"
        "4. Calculate truth table\n"
        "5. Generate three Verilog styles"
    )

examples = [
    "Design a half adder with Sum and Carry outputs.",
    "Design a full adder with Sum and Cout outputs.",
    "Design a 2-to-1 multiplexer using logic gates.",
    "Design a 2-to-4 decoder with active-high outputs.",
    "Design a 2-bit magnitude comparator with GT, EQ and LT outputs.",
    "Design a 4-bit ripple carry adder. Use scalar inputs A0 to A3 and B0 to B3."
]

st.markdown("### 🧠 Describe your circuit")
st.caption("Enter the circuit requirement below, or choose one of the example prompts.")
prompt = st.text_area(
    "Circuit requirement",
    value=examples[0],
    height=115,
    placeholder="Example: Design a full adder with inputs A, B, Cin and outputs Sum, Cout."
)

with st.expander("Example circuit prompts"):
    for item in examples:
        st.write("• " + item)

if st.button("⚡ Generate Circuit", type="primary", use_container_width=True):
    if not prompt.strip():
        st.error("Please enter a circuit description.")
    elif not api_key.strip():
        st.error("Gemini API key is missing. Add your existing key in the sidebar or Streamlit Secrets.")
    else:
        with st.spinner("AI agent is planning the circuit and checking its gate connections..."):
            try:
                generated = ask_ai(prompt.strip(), api_key.strip(), model_name.strip())
                st.session_state["circuit"] = generated
                st.session_state["generation_error"] = None
                st.session_state["generation_prompt"] = prompt.strip()
                st.success("Circuit plan generated and passed structural validation.")
            except Exception as error:
                st.session_state["generation_error"] = str(error)
                st.error("Circuit generation failed. No fallback circuit is being shown as if it were your requested answer.")
                with st.expander("Technical error details"):
                    st.code(str(error))

# --------------------------- RESULTS ---------------------------

if st.session_state.get("circuit"):
    circuit = st.session_state["circuit"]
    st.divider()
    st.markdown("### ✨ Your generated design")
    st.subheader(str(circuit.get("title", "Logic Circuit")))
    st.caption(
        f"{len(circuit['inputs'])} primary inputs · "
        f"{len(circuit['gates'])} gates · "
        f"{len(circuit['outputs'])} outputs"
    )

    tabs = st.tabs([
        "Circuit Diagram",
        "Truth Table",
        "Boolean Expression",
        "Behavioral Verilog",
        "Dataflow Verilog",
        "Gate-Level Verilog",
        "Explanation"
    ])

    with tabs[0]:
        st.markdown("**Actual logic gate symbols with connecting wires**")
        svg = make_gate_svg(circuit)
        st.components.v1.html(svg, height=max(300, 115 * max(len(circuit["inputs"]), len(circuit["gates"]))), scrolling=True)
        st.download_button(
            "Download circuit diagram (SVG)",
            data=svg,
            file_name="logic_circuit.svg",
            mime="image/svg+xml"
        )

    with tabs[1]:
        if len(circuit["inputs"]) > 8:
            st.warning("Truth table is limited to 8 input bits to avoid an excessively large table.")
        else:
            truth = make_truth_table(circuit)
            st.dataframe(truth, use_container_width=True, hide_index=True)
            st.caption(f"{len(truth)} input combinations calculated directly from the validated gate network.")

    with tabs[2]:
        expressions = make_boolean_expressions(circuit)
        for output_name, expression in expressions.items():
            st.code(expression, language="text")

    with tabs[3]:
        behavioral = make_behavioral_verilog(circuit)
        st.code(behavioral, language="verilog")
        st.download_button(
            "Download Behavioral Verilog",
            data=behavioral,
            file_name="logic_circuit_behavioral.v",
            mime="text/plain"
        )

    with tabs[4]:
        dataflow = make_dataflow_verilog(circuit)
        st.code(dataflow, language="verilog")
        st.download_button(
            "Download Dataflow Verilog",
            data=dataflow,
            file_name="logic_circuit_dataflow.v",
            mime="text/plain"
        )

    with tabs[5]:
        gatelevel = make_gatelevel_verilog(circuit)
        st.code(gatelevel, language="verilog")
        st.download_button(
            "Download Gate-Level Verilog",
            data=gatelevel,
            file_name="logic_circuit_gatelevel.v",
            mime="text/plain"
        )

    with tabs[6]:
        st.markdown("**Circuit explanation**")
        st.write(circuit.get("explanation", "No explanation was returned."))
        steps = circuit.get("design_steps", [])
        if steps:
            st.markdown("**AI design steps**")
            for number, step in enumerate(steps, start=1):
                st.write(f"{number}. {step}")
        st.markdown("**Validation performed**")
        st.success(
            "All gate types, signal names, gate input counts, execution order, "
            "and output references were checked before generating the results. "
            "The truth table is calculated locally from the same gate network."
        )

    st.info(
        "Scope note: This version supports combinational circuits represented by the listed basic gates. "
        "Sequential circuits such as counters, registers and flip-flops need clock/state modeling and are not "
        "yet supported by this netlist format. For important designs, simulate the downloaded Verilog in a "
        "Verilog simulator before hardware use."
    )
else:
    st.info("Enter a circuit requirement and click Generate Circuit. The app will create the diagram, truth table, Boolean expressions and three Verilog styles.")
    st.markdown("**Supported gate types:** AND, OR, NOT, NAND, NOR, XOR and XNOR.")
    st.markdown("**Try:** half adder, full adder, multiplexer, decoder, encoder, comparator, or a multi-bit combinational circuit.")

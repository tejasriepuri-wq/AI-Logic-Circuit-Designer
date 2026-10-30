
import os
import json
import re
import itertools
import streamlit as st
import pandas as pd
from google import genai

st.set_page_config(
    page_title="AI Logic Circuit Designer",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ AI-Based Logic Gate Circuit Designer")
st.write("Describe a logic circuit and let AI design it automatically.")

MAX_INPUTS = 5
MAX_GATES = 100

ALLOWED_GATES = {
    "AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR"
}

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ---------------- API KEY ----------------

def get_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass

    return os.getenv("GEMINI_API_KEY", "")


# ---------------- VALIDATION ----------------

def validate(circuit):

    if not isinstance(circuit, dict):
        raise ValueError("Invalid circuit response.")

    inputs = circuit.get("inputs")
    gates = circuit.get("gates")
    output = circuit.get("output")

    if not isinstance(inputs, list) or not 1 <= len(inputs) <= MAX_INPUTS:
        raise ValueError("Circuit must contain 1 to 5 inputs.")

    if any(not isinstance(x, str) or not IDENTIFIER.fullmatch(x) for x in inputs):
        raise ValueError("Invalid input names.")

    if len(set(inputs)) != len(inputs):
        raise ValueError("Input names must be unique.")

    if not isinstance(gates, list) or not 1 <= len(gates) <= MAX_GATES:
        raise ValueError("Invalid number of gates.")

    known = set(inputs)
    gate_ids = set()
    normalized = []

    for i, gate in enumerate(gates, 1):

        if not isinstance(gate, dict):
            raise ValueError(f"Invalid gate {i}.")

        typ = str(gate.get("type", "")).upper().strip()
        gid = str(gate.get("id", f"G{i}")).strip()
        gate_inputs = gate.get("inputs")
        gate_output = gate.get("output")

        if typ not in ALLOWED_GATES:
            raise ValueError(f"Unsupported gate: {typ}")

        if not IDENTIFIER.fullmatch(gid) or gid in gate_ids:
            raise ValueError("Invalid or duplicate gate ID.")

        if not isinstance(gate_output, str) or not IDENTIFIER.fullmatch(gate_output):
            raise ValueError("Invalid gate output name.")

        if gate_output in known:
            raise ValueError("Duplicate signal name.")

        expected = 1 if typ == "NOT" else 2

        if not isinstance(gate_inputs, list) or len(gate_inputs) != expected:
            raise ValueError(f"{typ} requires {expected} input(s).")

        if any(not isinstance(x, str) or x not in known for x in gate_inputs):
            raise ValueError("Unknown signal or incorrect gate order.")

        normalized.append({
            "id": gid,
            "type": typ,
            "inputs": gate_inputs,
            "output": gate_output
        })

        gate_ids.add(gid)
        known.add(gate_output)

    if not isinstance(output, str) or output not in known:
        raise ValueError("Invalid final output.")

    circuit["inputs"] = inputs
    circuit["gates"] = normalized
    circuit["output"] = output

    circuit["explanation"] = str(
        circuit.get("explanation", "Circuit generated successfully.")
    )

    circuit["design_steps"] = circuit.get("design_steps", [])

    return circuit


# ---------------- LOGIC EVALUATION ----------------

def evaluate(gate, values):

    a = values[0]
    b = values[1] if len(values) > 1 else None

    if gate == "NOT":
        return 1 - a

    if gate == "AND":
        return a & b

    if gate == "OR":
        return a | b

    if gate == "NAND":
        return 1 - (a & b)

    if gate == "NOR":
        return 1 - (a | b)

    if gate == "XOR":
        return a ^ b

    if gate == "XNOR":
        return 1 - (a ^ b)

    raise ValueError("Unsupported gate: " + gate)


def evaluate_circuit(circuit, primary_values):

    values = dict(primary_values)

    for gate in circuit["gates"]:

        gate_values = [
            values[x] for x in gate["inputs"]
        ]

        values[gate["output"]] = evaluate(
            gate["type"], gate_values
        )

    return values


# ---------------- TRUTH TABLE ----------------

def truth_table(circuit):

    rows = []

    for bits in itertools.product(
        [0, 1], repeat=len(circuit["inputs"])
    ):

        primary = dict(zip(circuit["inputs"], bits))

        values = evaluate_circuit(circuit, primary)

        row = {
            x: values[x] for x in circuit["inputs"]
        }

        row[circuit["output"]] = values[circuit["output"]]

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------- BOOLEAN EXPRESSION ----------------

def boolean_expression(circuit):

    expressions = {
        x: x for x in circuit["inputs"]
    }

    for gate in circuit["gates"]:

        typ = gate["type"]
        names = gate["inputs"]

        a = expressions[names[0]]

        if typ == "NOT":
            expr = f"~({a})"

        else:
            b = expressions[names[1]]

            if typ == "AND":
                expr = f"({a} & {b})"

            elif typ == "OR":
                expr = f"({a} | {b})"

            elif typ == "NAND":
                expr = f"~({a} & {b})"

            elif typ == "NOR":
                expr = f"~({a} | {b})"

            elif typ == "XOR":
                expr = f"({a} ^ {b})"

            elif typ == "XNOR":
                expr = f"~({a} ^ {b})"

        expressions[gate["output"]] = expr

    return (
        f'{circuit["output"]} = '
        f'{expressions[circuit["output"]]}'
    )


# ---------------- GATE LEVEL VERILOG ----------------

def verilog(circuit):

    inputs = circuit["inputs"]
    output = circuit["output"]

    lines = [
        f"module logic_circuit({', '.join(inputs + [output])});",
        "    input " + ", ".join(inputs) + ";",
        "    output " + output + ";"
    ]

    wires = [
        g["output"]
        for g in circuit["gates"]
        if g["output"] != output
    ]

    if wires:
        lines.append("    wire " + ", ".join(wires) + ";")

    gate_names = {
        "AND": "and",
        "OR": "or",
        "NOT": "not",
        "NAND": "nand",
        "NOR": "nor",
        "XOR": "xor",
        "XNOR": "xnor"
    }

    for i, gate in enumerate(circuit["gates"], 1):

        name = gate_names[gate["type"]]

        ports = ", ".join(
            [gate["output"]] + gate["inputs"]
        )

        lines.append(
            f"    {name} gate{i}({ports});"
        )

    lines.append("endmodule")

    return "\n".join(lines)


# ---------------- CIRCUIT DIAGRAM ----------------

def graph(circuit):

    def q(value):
        return json.dumps(str(value))

    symbols = {
        "AND": "&",
        "OR": "≥1",
        "NOT": "1",
        "NAND": "& ○",
        "NOR": "≥1 ○",
        "XOR": "=1",
        "XNOR": "=1 ○"
    }

    lines = [
        "digraph Circuit {",
        "rankdir=LR;",
        'graph [bgcolor="white", nodesep=0.5, ranksep=0.7];',
        'node [fontname="Arial", fontsize=12];',
        'edge [arrowsize=0.8];'
    ]

    # Input signals

    for signal in circuit["inputs"]:

        lines.append(
            f'{q("in_" + signal)} '
            f'[label={q(signal)}, shape=circle, '
            'style=filled, fillcolor="#DCEBFF"];'
        )

    # Logic gates and connected wires

    for i, gate in enumerate(circuit["gates"], 1):

        gate_node = "gate_" + str(i)

        label = (
            gate["type"] + "\n" +
            symbols[gate["type"]]
        )

        lines.append(
            f'{q(gate_node)} '
            f'[label={q(label)}, shape=ellipse, '
            'style=filled, fillcolor="#FFF0C2", penwidth=1.5];'
        )

        # Connect input wires

        for signal in gate["inputs"]:

            source = (
                "in_" + signal
                if signal in circuit["inputs"]
                else "sig_" + signal
            )

            lines.append(
                f'{q(source)} -> {q(gate_node)};'
            )

        # Gate output wire

        output_node = "sig_" + gate["output"]

        if gate["output"] == circuit["output"]:

            lines.append(
                f'{q(output_node)} '
                f'[label={q(gate["output"])}, '
                'shape=doublecircle, style=filled, '
                'fillcolor="#D9F5E5"];'
            )

        else:

            lines.append(
                f'{q(output_node)} '
                f'[label={q(gate["output"])}, shape=plaintext];'
            )

        lines.append(
            f'{q(gate_node)} -> {q(output_node)};'
        )

    # Direct input output connection

    if circuit["output"] in circuit["inputs"]:

        lines.append(
            f'{q("out_direct")} '
            f'[label={q(circuit["output"])}, '
            'shape=doublecircle];'
        )

        lines.append(
            f'{q("in_" + circuit["output"])} '
            f'-> {q("out_direct")};'
        )

    lines.append("}")

    return "\n".join(lines)


# ---------------- AI CIRCUIT GENERATION ----------------

def ask_ai(prompt, api_key):

    client = genai.Client(api_key=api_key)

    instructions = f"""
You are an expert digital logic circuit designer.

Convert the user's requirement into a complete combinational
digital logic gate network.

Return ONLY valid JSON in this format:

{{
 "title": "Circuit name",
 "inputs": ["A", "B"],
 "gates": [
  {{"id":"G1","type":"XOR","inputs":["A","B"],"output":"Y"}}
 ],
 "output": "Y",
 "explanation": "Explain the circuit in simple words.",
 "design_steps": ["First step", "Second step"]
}}

STRICT RULES:

1. Allowed gates: AND, OR, NOT, NAND, NOR, XOR, XNOR.
2. Use 1 to {MAX_INPUTS} primary inputs.
3. Maximum {MAX_GATES} gates.
4. NOT has exactly one input.
5. Every other gate has exactly two inputs.
6. Use valid Verilog identifiers.
7. Use W1, W2, W3 for intermediate signals.
8. Every gate must have a unique ID and output.
9. List gates in execution order.
10. A gate can only use primary inputs or earlier gate outputs.
11. Final output signal must be Y.
12. Create the complete network for complex circuits.
13. Do not use flip-flops, clocks, latches or memories.
14. Ensure the explanation describes the actual circuit.
15. Return only JSON, without Markdown.
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=instructions + "\nUSER REQUIREMENT:\n" + prompt
    )

    raw = (response.text or "").strip()

    raw = re.sub(
        r"^```(?:json)?\s*", "", raw,
        flags=re.IGNORECASE
    )

    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)

    except json.JSONDecodeError:

        match = re.search(
            r"\{.*\}", raw, flags=re.DOTALL
        )

        if not match:
            raise ValueError("AI returned invalid JSON. Try another prompt.")

        data = json.loads(match.group(0))

    return validate(data)


# ---------------- USER INTERFACE ----------------

prompt = st.text_area(
    "Describe your logic circuit",
    "Create an XOR gate using inputs A and B."
)

if st.button("Generate Circuit", type="primary"):

    if not prompt.strip():

        st.warning("Please enter a circuit requirement.")

    else:

        key = get_key()

        if not key:

            st.error("GEMINI_API_KEY not found in Streamlit Secrets.")

        else:

            with st.spinner("AI is designing your circuit..."):

                try:

                    circuit = ask_ai(prompt, key)

                    st.session_state["circuit"] = circuit

                    st.success("Circuit generated successfully!")

                except Exception as e:

                    st.error("Circuit generation failed: " + str(e))


# ---------------- DISPLAY RESULTS ----------------

if "circuit" in st.session_state:

    c = st.session_state["circuit"]

    st.divider()

    st.subheader("1. Logic Gate Circuit Diagram")

    st.graphviz_chart(
        graph(c),
        use_container_width=True
    )

    st.subheader("2. Boolean Expression")

    st.code(
        boolean_expression(c),
        language="text"
    )

    st.subheader("3. Circuit Explanation")

    st.write(c["explanation"])

    if isinstance(c.get("design_steps"), list) and c["design_steps"]:

        st.markdown("**Design Steps**")

        for i, step in enumerate(c["design_steps"], 1):

            st.write(f"{i}. {step}")

    st.subheader("4. Truth Table")

    df = truth_table(c)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        f"Total input combinations: {len(df)}"
    )

    st.subheader("5. Gate-Level Verilog Code")

    code = verilog(c)

    st.code(
        code,
        language="verilog"
    )

    st.download_button(
        "Download Verilog Code",
        data=code,
        file_name="logic_circuit.v",
        mime="text/plain"
    )

    st.subheader("6. Circuit Summary")

    col1, col2, col3 = st.columns(3)

    col1.metric("Inputs", len(c["inputs"]))

    col2.metric("Logic Gates", len(c["gates"]))

    col3.metric("Truth Table Rows", len(df))

    st.info(
        "The generated Verilog uses gate-level modelling "
        "with AND, OR, NOT, NAND, NOR, XOR and XNOR primitives."
    )

else:

    st.info(
        "Enter your circuit requirement and click Generate Circuit."
    )

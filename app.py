
import os
import json
import itertools
import re

import streamlit as st
import pandas as pd
from google import genai

st.set_page_config(
    page_title="AI Logic Circuit Designer",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ AI-Based Logic Gate Circuit Designer")
st.write(
    "Describe any digital logic circuit in simple English. "
    "The AI will try to design it and generate its truth table and Verilog code."
)

ALLOWED_GATES = {"AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR"}


def get_api_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY", "")


def evaluate(gate, inputs):
    a = inputs[0]
    b = inputs[1] if len(inputs) > 1 else None

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

    raise ValueError(f"Unsupported gate: {gate}")


def validate(circuit):
    inputs = circuit.get("inputs", [])
    gates = circuit.get("gates", [])
    outputs = circuit.get("outputs", [])

    # Support older AI responses with a single "output"
    if not outputs and circuit.get("output"):
        outputs = [circuit["output"]]

    if not inputs or len(inputs) > 5:
        raise ValueError("The circuit must have 1 to 5 inputs.")

    if len(set(inputs)) != len(inputs):
        raise ValueError("Input names must be unique.")

    if not gates:
        raise ValueError("The AI did not provide any gates.")

    known = set(inputs)
    used_gate_ids = set()

    for i, gate in enumerate(gates, start=1):
        gate["type"] = str(gate.get("type", "")).upper()
        gate.setdefault("id", f"G{i}")

        gate_inputs = gate.get("inputs", [])
        gate_output = gate.get("output")

        if gate["type"] not in ALLOWED_GATES:
            raise ValueError(f"Unsupported gate: {gate['type']}")

        expected = 1 if gate["type"] == "NOT" else 2
        if len(gate_inputs) != expected:
            raise ValueError(
                f"{gate['type']} gate must have {expected} input(s)."
            )

        if any(signal not in known for signal in gate_inputs):
            raise ValueError(
                f"Gate {gate['id']} uses an undefined signal. "
                "Gates must be listed in execution order."
            )

        if not isinstance(gate_output, str) or not gate_output:
            raise ValueError("Every gate must have an output name.")

        if gate_output in known:
            raise ValueError(f"Duplicate signal name: {gate_output}")

        if gate["id"] in used_gate_ids:
            raise ValueError("Gate IDs must be unique.")

        used_gate_ids.add(gate["id"])
        known.add(gate_output)

    if not outputs:
        raise ValueError("The circuit must have at least one output.")

    if len(set(outputs)) != len(outputs):
        raise ValueError("Output names must be unique.")

    if any(output not in known for output in outputs):
        raise ValueError("An output refers to an undefined signal.")

    circuit["outputs"] = outputs
    circuit["output"] = outputs[0]
    circuit.setdefault("boolean_expression", "See gate connections below.")
    circuit.setdefault("explanation", "Circuit generated from your prompt.")

    return circuit


def fallback_circuit():
    return {
        "inputs": ["A", "B"],
        "gates": [
            {
                "id": "G1",
                "type": "XOR",
                "inputs": ["A", "B"],
                "output": "Y"
            }
        ],
        "outputs": ["Y"],
        "output": "Y",
        "boolean_expression": "Y = A XOR B",
        "explanation": (
            "XOR produces 1 when its two inputs are different. "
            "It produces 0 when the inputs are the same."
        )
    }


def make_truth_table(circuit):
    rows = []

    for bits in itertools.product(
        [0, 1], repeat=len(circuit["inputs"])
    ):
        values = dict(zip(circuit["inputs"], bits))
        row = dict(values)

        for gate in circuit["gates"]:
            gate_values = [values[x] for x in gate["inputs"]]
            result = evaluate(gate["type"], gate_values)

            values[gate["output"]] = result
            row[gate["output"]] = result

        rows.append({
            name: row[name]
            for name in circuit["inputs"]
            + [g["output"] for g in circuit["gates"]]
            if name in row
        } | {
            output: values[output]
            for output in circuit["outputs"]
        })

    return pd.DataFrame(rows)


def make_verilog(circuit):
    inputs = circuit["inputs"]
    outputs = circuit["outputs"]
    output_set = set(outputs)

    ports = inputs + outputs
    lines = [
        "module logic_circuit(" + ", ".join(ports) + ");",
        "input " + ", ".join(inputs) + ";",
        "output " + ", ".join(outputs) + ";"
    ]

    internal_wires = [
        gate["output"]
        for gate in circuit["gates"]
        if gate["output"] not in output_set
    ]

    if internal_wires:
        lines.append("wire " + ", ".join(internal_wires) + ";")

    gate_names = {
        "AND": "and",
        "OR": "or",
        "NOT": "not",
        "NAND": "nand",
        "NOR": "nor",
        "XOR": "xor",
        "XNOR": "xnor"
    }

    for i, gate in enumerate(circuit["gates"], start=1):
        connections = [gate["output"]] + gate["inputs"]
        lines.append(
            f'{gate_names[gate["type"]]} gate{i}'
            f'({", ".join(connections)});'
        )

    lines.append("endmodule")
    return "\n".join(lines)


def make_graph(circuit):
    lines = [
        "digraph Circuit {",
        "rankdir=LR;",
        'node [fontname="Arial"];'
    ]

    for name in circuit["inputs"]:
        lines.append(f'"{name}" [shape=circle];')

    for gate in circuit["gates"]:
        gate_id = gate["id"]
        gate_output = gate["output"]

        lines.append(
            f'"{gate_id}" [label="{gate["type"]}", shape=box];'
        )

        for signal in gate["inputs"]:
            lines.append(f'"{signal}" -> "{gate_id}";')

        lines.append(f'"{gate_id}" -> "{gate_output}";')

        if gate_output not in circuit["outputs"]:
            lines.append(
                f'"{gate_output}" [shape=plaintext];'
            )

    for output in circuit["outputs"]:
        lines.append(
            f'"{output}" [shape=doublecircle, label="{output}"];'
        )

    lines.append("}")
    return "\n".join(lines)


def ask_ai(prompt, api_key):
    client = genai.Client(api_key=api_key)

    instructions = """
You are a digital logic circuit designer.

Convert the user's request into a valid logic circuit.
Return ONLY valid JSON. Do not include Markdown fences.

Use this exact structure:
{
  "inputs": ["A", "B"],
  "gates": [
    {"id": "G1", "type": "XOR", "inputs": ["A", "B"], "output": "Y"}
  ],
  "outputs": ["Y"],
  "boolean_expression": "Y = A XOR B",
  "explanation": "Explain how the circuit works."
}

Rules:
- Allowed gate types: AND, OR, NOT, NAND, NOR, XOR, XNOR.
- Use 1 to 5 unique input names.
- NOT has exactly one input; all other gates have exactly two.
- List gates in execution order.
- Every gate must have a unique output signal.
- Use intermediate names such as W1 and W2 when needed.
- The outputs array may contain multiple outputs.
- Every output must be an input or a defined gate output.
- Build the actual requested circuit, not always XOR.
- For half adders use Sum and Carry outputs.
- For full adders use Sum and Cout outputs.
- Boolean expressions must match the circuit.
- Keep the explanation simple and accurate.
"""

    # Try multiple model names if one is temporarily unavailable.
    models = [
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.8-flash"
    ]

    errors = []

    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=instructions + "\nUSER REQUEST:\n" + prompt
            )

            raw = (response.text or "").strip()

            # Remove optional Markdown code fences.
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            data = json.loads(raw)
            return validate(data), model

        except Exception as error:
            errors.append(f"{model}: {error}")

    raise RuntimeError("\n\n".join(errors))


# ---------------- USER INPUT ----------------

example_prompts = [
    "Create an XOR gate using inputs A and B",
    "Design a half adder with Sum and Carry outputs",
    "Design a full adder with Sum and Cout outputs",
    "Create a circuit using NAND gates only for XOR",
    "Create a circuit that outputs 1 when both inputs are 1"
]

prompt = st.text_area(
    "Describe your circuit",
    value=example_prompts[0],
    height=100,
    help="Describe the inputs, required output, and any gate restrictions."
)

st.caption(
    "Examples: half adder, full adder, NAND-only XOR, "
    "majority circuit, or a circuit based on your Boolean expression."
)

if st.button("⚡ Generate Circuit", type="primary"):
    if not prompt.strip():
        st.error("Please enter a circuit description.")
    else:
        api_key = get_api_key()

        if not api_key:
            st.error(
                "GEMINI_API_KEY is missing. Add it in "
                "Streamlit Cloud → App settings → Secrets."
            )
        else:
            with st.spinner("Asking AI to design your circuit..."):
                try:
                    circuit, model_used = ask_ai(prompt, api_key)

                    st.session_state["circuit"] = circuit
                    st.session_state["demo_mode"] = False
                    st.session_state["generation_note"] = (
                        f"Circuit generated successfully using {model_used}."
                    )
                    st.session_state.pop("generation_error", None)

                except Exception as error:
                    st.session_state["circuit"] = fallback_circuit()
                    st.session_state["demo_mode"] = True
                    st.session_state["generation_note"] = (
                        "AI generation failed. The XOR circuit below is "
                        "only a fallback demonstration, not the answer "
                        "to your prompt."
                    )
                    st.session_state["generation_error"] = str(error)


# ---------------- DISPLAY RESULTS ----------------

if "circuit" in st.session_state:
    circuit = st.session_state["circuit"]

    if st.session_state.get("demo_mode"):
        st.warning(st.session_state["generation_note"])

        with st.expander("View technical error details"):
            st.code(
                st.session_state.get(
                    "generation_error", "No technical details available."
                )
            )
    else:
        st.success(st.session_state["generation_note"])

    st.subheader("1. Circuit Diagram")
    st.graphviz_chart(make_graph(circuit), use_container_width=True)

    st.subheader("2. Boolean Expression")
    st.code(circuit.get("boolean_expression", "Not provided"))

    st.subheader("3. Explanation")
    st.write(circuit.get("explanation", ""))

    st.subheader("4. Truth Table")
    st.dataframe(make_truth_table(circuit), use_container_width=True)

    st.subheader("5. Verilog Code")
    verilog_code = make_verilog(circuit)
    st.code(verilog_code, language="verilog")

    st.download_button(
        "Download Verilog Code",
        data=verilog_code,
        file_name="logic_circuit.v",
        mime="text/plain"
    )

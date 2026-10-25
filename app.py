
import os
import json
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
st.write("Describe a circuit and let AI design it.")

def get_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY", "")

def evaluate(gate, values):
    a = values[0]
    b = values[1] if len(values) > 1 else None
    if gate == "NOT": return 1 - a
    if gate == "AND": return a & b
    if gate == "OR": return a | b
    if gate == "NAND": return 1 - (a & b)
    if gate == "NOR": return 1 - (a | b)
    if gate == "XOR": return a ^ b
    if gate == "XNOR": return 1 - (a ^ b)
    raise ValueError("Unsupported gate: " + gate)

def validate(c):
    inputs = c["inputs"]
    gates = c["gates"]
    if not inputs or len(inputs) > 5 or len(set(inputs)) != len(inputs):
        raise ValueError("Use 1–5 unique inputs.")
    known = set(inputs)
    allowed = {"AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR"}

    for i, g in enumerate(gates, 1):
        g["type"] = g["type"].upper()
        g.setdefault("id", f"G{i}")
        if g["type"] not in allowed:
            raise ValueError("Unsupported gate: " + g["type"])
        expected = 1 if g["type"] == "NOT" else 2
        if len(g["inputs"]) != expected:
            raise ValueError(g["type"] + " has the wrong number of inputs.")
        if any(x not in known for x in g["inputs"]):
            raise ValueError("A gate uses an undefined signal.")
        if g["output"] in known:
            raise ValueError("Duplicate signal name.")
        known.add(g["output"])

    if c["output"] not in known:
        raise ValueError("Final output signal is undefined.")
    return c

def fallback_circuit():
    return {
        "inputs": ["A", "B"],
        "gates": [
            {"id": "G1", "type": "XOR",
             "inputs": ["A", "B"], "output": "Y"}
        ],
        "output": "Y",
        "boolean_expression": "Y = A XOR B",
        "explanation": (
            "The XOR gate outputs 1 when A and B are different. "
            "It outputs 0 when both inputs are the same."
        )
    }

def truth_table(c):
    rows = []
    for bits in itertools.product([0, 1], repeat=len(c["inputs"])):
        values = dict(zip(c["inputs"], bits))
        row = dict(values)
        for g in c["gates"]:
            result = evaluate(
                g["type"], [values[x] for x in g["inputs"]]
            )
            values[g["output"]] = result
            row[g["output"]] = result
        rows.append(row)
    return pd.DataFrame(rows)

def verilog(c):
    ins = c["inputs"]
    wires = [
        g["output"] for g in c["gates"]
        if g["output"] != c["output"]
    ]
    lines = [
        "module logic_circuit(" + ", ".join(ins + [c["output"]]) + ");",
        "input " + ", ".join(ins) + ";",
        "output " + c["output"] + ";"
    ]
    if wires:
        lines.append("wire " + ", ".join(wires) + ";")

    names = {
        "AND": "and", "OR": "or", "NOT": "not",
        "NAND": "nand", "NOR": "nor",
        "XOR": "xor", "XNOR": "xnor"
    }
    for i, g in enumerate(c["gates"], 1):
        lines.append(
            f'{names[g["type"]]} gate{i}'
            f'({g["output"]}, {", ".join(g["inputs"])});'
        )
    lines.append("endmodule")
    return "\n".join(lines)

def graph(c):
    lines = [
        "digraph Circuit {", "rankdir=LR;",
        'node [fontname="Arial"];'
    ]
    for x in c["inputs"]:
        lines.append(f'"{x}" [shape=circle];')

    for i, g in enumerate(c["gates"], 1):
        lines.append(
            f'"{g["id"]}" [label="{g["type"]}", shape=box];'
        )
        for x in g["inputs"]:
            lines.append(f'"{x}" -> "{g["id"]}";')
        lines.append(f'"{g["id"]}" -> "{g["output"]}";')
        if g["output"] != c["output"]:
            lines.append(f'"{g["output"]}" [shape=plaintext];')

    lines.append(
        f'"{c["output"]}" [shape=doublecircle, '
        f'label="{c["output"]}"];'
    )
    lines.append("}")
    return "\n".join(lines)

prompt = st.text_area(
    "Describe your circuit",
    "Create an XOR gate using inputs A and B"
)

if st.button("Generate Circuit", type="primary"):
    key = get_key()
    generated = None
    failure = None

    if key:
        instructions = """
Return ONLY valid JSON:
{
 "inputs":["A","B"],
 "gates":[{"id":"G1","type":"XOR","inputs":["A","B"],"output":"Y"}],
 "output":"Y",
 "boolean_expression":"Y = A XOR B",
 "explanation":"Short explanation"
}
Allowed gates: AND, OR, NOT, NAND, NOR, XOR, XNOR.
Use 1 to 5 unique input names.
NOT takes one input; all other gates take two.
List gates in execution order. Use W1, W2 for intermediate outputs.
Final output must be named Y. Do not use undefined signals.
"""
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=instructions + "\nUser request: " + prompt
            )
            raw = (response.text or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            generated = validate(json.loads(raw))
        except Exception as e:
            failure = str(e)

    if generated:
        st.session_state["circuit"] = generated
        st.session_state["demo_mode"] = False
        st.session_state["generation_note"] = "AI generated this circuit."
    else:
        st.session_state["circuit"] = fallback_circuit()
        st.session_state["demo_mode"] = True
        st.session_state["generation_note"] = (
            "AI was unavailable, so a working XOR demonstration is shown. "
            "This is a fallback example, not an AI-generated answer."
        )
        if failure:
            st.session_state["generation_error"] = failure

if "circuit" in st.session_state:
    c = st.session_state["circuit"]

    if st.session_state.get("demo_mode"):
        st.warning(st.session_state["generation_note"])
        if st.session_state.get("generation_error"):
            with st.expander("Technical error details"):
                st.code(st.session_state["generation_error"])
    else:
        st.success(st.session_state["generation_note"])

    st.subheader("1. Circuit Diagram")
    st.graphviz_chart(graph(c))

    st.subheader("2. Boolean Expression")
    st.code(c.get("boolean_expression", "Not provided"))

    st.subheader("3. Explanation")
    st.write(c.get("explanation", ""))

    st.subheader("4. Truth Table")
    st.dataframe(truth_table(c), use_container_width=True)

    st.subheader("5. Verilog Code")
    st.code(verilog(c), language="verilog")

import os
import json
import itertools
import streamlit as st
import pandas as pd
from google import genai

st.set_page_config(page_title="AI Logic Circuit Designer", page_icon="⚡", layout="wide")
st.title("⚡ AI-Based Logic Gate Circuit Designer")
st.write("Describe a logic circuit and let AI design it.")

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
        raise ValueError("Inputs must be 1–5 unique names.")
    known = set(inputs)
    allowed = {"AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR"}
    for g in gates:
        typ = g["type"].upper()
        g["type"] = typ
        if typ not in allowed:
            raise ValueError("Unsupported gate: " + typ)
        if len(g["inputs"]) != (1 if typ == "NOT" else 2):
            raise ValueError(typ + " has the wrong number of inputs.")
        if any(x not in known for x in g["inputs"]):
            raise ValueError("A gate uses a signal that is not defined yet.")
        if g["output"] in known:
            raise ValueError("Duplicate signal name.")
        known.add(g["output"])
    if c["output"] not in known:
        raise ValueError("Final output signal is not defined.")
    return c

def truth_table(c):
    rows = []
    for bits in itertools.product([0, 1], repeat=len(c["inputs"])):
        values = dict(zip(c["inputs"], bits))
        row = dict(values)
        for g in c["gates"]:
            row[g["output"]] = evaluate(
                g["type"], [values[x] for x in g["inputs"]]
            )
        rows.append(row)
    return pd.DataFrame(rows)

def verilog(c):
    ins = c["inputs"]
    wires = [g["output"] for g in c["gates"]
             if g["output"] != c["output"]]
    lines = ["module logic_circuit(" + ", ".join(ins + [c["output"]]) + ");"]
    lines.append("input " + ", ".join(ins) + ";")
    lines.append("output " + c["output"] + ";")
    if wires:
        lines.append("wire " + ", ".join(wires) + ";")
    names = {"AND":"and", "OR":"or", "NOT":"not", "NAND":"nand",
             "NOR":"nor", "XOR":"xor", "XNOR":"xnor"}
    for i, g in enumerate(c["gates"], 1):
        lines.append(f'{names[g["type"]]} gate{i}({g["output"]}, {", ".join(g["inputs"])});')
    lines.append("endmodule")
    return "\n".join(lines)

def graph(c):
    lines = ["digraph Circuit {", "rankdir=LR;", 'node [fontname="Arial"];']
    for x in c["inputs"]:
        lines.append(f'"{x}" [shape=circle];')
    for i, g in enumerate(c["gates"], 1):
        lines.append(f'"{g["id"]}" [label="{g["type"]}", shape=box];')
        for x in g["inputs"]:
            lines.append(f'"{x}" -> "{g["id"]}";')
        lines.append(f'"{g["id"]}" -> "{g["output"]}";')
        lines.append(f'"{g["output"]}" [shape=plaintext];')
    lines.append(f'"{c["output"]}" [shape=doublecircle, label="{c["output"]}"];')
    lines.append("}")
    return "\n".join(lines)

prompt = st.text_area(
    "Describe your circuit",
    "Create an XOR gate using inputs A and B"
)

if st.button("Generate Circuit", type="primary"):
    key = get_key()
    if not key:
        st.error("Add GEMINI_API_KEY in Streamlit Secrets before running.")
    else:
        instructions = """
Return ONLY valid JSON with this schema:
{
 "inputs":["A","B"],
 "gates":[{"id":"G1","type":"XOR","inputs":["A","B"],"output":"Y"}],
 "output":"Y",
 "boolean_expression":"Y = A XOR B",
 "explanation":"Short explanation"
}
Supported gate types: AND, OR, NOT, NAND, NOR, XOR, XNOR.
Use 1 to 5 input signals. NOT has one input; all other gates have two.
List gates in execution order. Use W1, W2 for intermediate signals.
Final output signal must be Y. Do not use undefined signals.
"""
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=instructions + "\nUser request: " + prompt
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            circuit = validate(json.loads(raw))
            st.session_state["circuit"] = circuit
        except Exception as e:
            st.error("Could not generate the circuit: " + str(e))

if "circuit" in st.session_state:
    c = st.session_state["circuit"]
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

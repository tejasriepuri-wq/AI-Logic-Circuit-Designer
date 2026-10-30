
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

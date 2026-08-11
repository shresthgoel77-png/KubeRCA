"""Standalone test: print raw model output to debug_output.txt"""
import sys
sys.path.insert(0, ".")
from model_runner import ModelRunner

runner = ModelRunner()

telemetry = """Pod: payments-api
Status: CrashLoopBackOff
Restart Count: 17

Events:
Back-off restarting failed container
OOMKilled

Logs:
Java heap space error

Metrics:
Memory usage: 98%
Memory limit: 512Mi"""

# Call generate but catch and dump everything
import json, re, torch

messages = [
    {"role": "system", "content": runner.system_prompt},
    {"role": "user", "content": telemetry}
]

text = runner.tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)

print("=== FORMATTED PROMPT ===")
print(text)
print("=== END PROMPT ===\n")

model_inputs = runner.tokenizer([text], return_tensors="pt").to(runner.device)

with torch.inference_mode():
    generated_ids = runner.model.generate(
        **model_inputs,
        max_new_tokens=512,
        do_sample=False,
        pad_token_id=runner.tokenizer.pad_token_id or runner.tokenizer.eos_token_id,
        eos_token_id=runner.tokenizer.eos_token_id,
    )

generated_ids = [
    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
]

response_text = runner.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

print("=== RAW MODEL OUTPUT ===")
print(repr(response_text))
print("=== END RAW OUTPUT ===\n")
print(f"Output length: {len(response_text)} chars")

# Try extraction
start = response_text.find('{')
end = response_text.rfind('}')
print(f"First '{{' at index: {start}")
print(f"Last '}}' at index: {end}")

if start != -1 and end != -1 and start < end:
    json_str = response_text[start:end+1]
    print("\n=== EXTRACTED JSON STRING ===")
    print(repr(json_str))
    print("=== END EXTRACTED ===\n")
    try:
        parsed = json.loads(json_str)
        print("JSON parsed successfully:")
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
else:
    print("No JSON object found in output")

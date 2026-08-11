import json
import logging
import os
import threading
import torch
import re
from typing import Dict, Any, List
from transformers import AutoModelForCausalLM, AutoTokenizer
# pyrefly: ignore [missing-import]
from peft import PeftModel
from pydantic import ValidationError

from config import settings
from schemas import DiagnosisResponse

logger = logging.getLogger("kuberca")

class ModelRunner:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        if self.device == "cuda":
            self.dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        else:
            self.dtype = torch.float32

        logger.info("Initializing ModelRunner on device: %s", self.device)
        
        base_model_id = settings.BASE_MODEL
        adapter_model_id = settings.ADAPTER_MODEL
        hf_token = os.getenv("HF_TOKEN") or None

        logger.info("Base model : %s", base_model_id)
        logger.info("Adapter    : %s", adapter_model_id)

        self.tokenizer = AutoTokenizer.from_pretrained(base_model_id, token=hf_token)
        
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            dtype=self.dtype,
            device_map=self.device,
            token=hf_token,
        )

        self.model = PeftModel.from_pretrained(base_model, adapter_model_id, token=hf_token)
        self.model.eval()
        
        self.lock = threading.Lock()
        
        self.system_prompt = (
            "You are KubeRCA, a Kubernetes incident diagnosis model.\n\n"
            "Analyze Kubernetes telemetry and produce a strict JSON diagnosis.\n\n"
            "The JSON must contain:\n"
            "- failure: Summary of what failed.\n"
            "- root_cause: The underlying issue (prefer 'unknown/insufficient_evidence' rather than inventing a cause if evidence is insufficient).\n"
            "- confidence: A number from 0.0 to 1.0.\n"
            "- evidence: Array of strings directly grounded in the supplied telemetry. Do not invent logs, events, metrics, Kubernetes resources, or error messages.\n"
            "- severity: Must be exactly SEV-1, SEV-2, or SEV-3.\n\n"
            "Return ONLY valid JSON. Do not add explanations outside the JSON."
        )
        logger.info("Models loaded successfully.")

    def _extract_json(self, text: str) -> str:
        text = text.strip()
        
        # 1. Try to find the exact json code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        # 2. Find the first '{' and the last '}'
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and start < end:
            return text[start:end+1].strip()
        
        # 3. Fallback to raw text
        return text

    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.0) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.device)

        with self.lock:
            with torch.inference_mode():
                generated_ids = self.model.generate(
                    **model_inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature if temperature > 0.0 else None,
                    do_sample=(temperature > 0.0),
                    pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )
                
        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]

        response_text = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        
        logger.debug("=== RAW MODEL OUTPUT START ===")
        logger.debug("%s", response_text)
        logger.debug("=== RAW MODEL OUTPUT END === (length: %d)", len(response_text))
        
        try:
            json_str = self._extract_json(response_text)
            logger.debug("Extracted JSON string: %s", json_str)
            parsed_data = json.loads(json_str)
            validated_data = DiagnosisResponse(**parsed_data)
            return validated_data.model_dump() if hasattr(validated_data, 'model_dump') else validated_data.dict()
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Parse failure. Raw output:\n%s", response_text)
            raise ValueError(f"Failed to extract or validate JSON from model output: {str(e)}\nRaw output: {response_text}")

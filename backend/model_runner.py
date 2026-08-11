import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
# pyrefly: ignore [missing-import]
from peft import PeftModel
from config import settings

class ModelRunner:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Initializing Model Runner on device: {self.device}")
        
        # Configure BitsAndBytes for 4-bit quantization to save VRAM
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        print(f"Loading Base Model: {settings.BASE_MODEL}")
        self.tokenizer = AutoTokenizer.from_pretrained(settings.BASE_MODEL)
        
        base_model = AutoModelForCausalLM.from_pretrained(
            settings.BASE_MODEL,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
        )

        print(f"Loading Adapter Model: {settings.ADAPTER_MODEL}")
        self.model = PeftModel.from_pretrained(base_model, settings.ADAPTER_MODEL)
        self.model.eval()
        print("Models loaded successfully.")

    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.7, top_p: float = 0.9) -> str:
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.device)

        with torch.no_grad():
            generated_ids = self.model.generate(
                **model_inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
            
            # Extract just the generated new tokens
            generated_ids = [
                output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]

            response = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
            
        return response

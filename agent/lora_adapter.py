"""
LoRA Adapter - OpenMythos task-specific adapter

Different task types use different prompt templates.
Switch adapter based on task category.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class LoRAConfig:
    name: str
    description: str
    system_prompt_template: str
    tool_hints: List[str]
    reasoning_strategy: str
    max_iterations: int
    reasoning_effort: str

ADAPTER_CONFIGS = {
    "coding": LoRAConfig(
        name="coding",
        description="Code tasks: functions, scripts, debugging",
        system_prompt_template="You are a senior software engineer.\nWrite clean code with type hints.\nHandle edge cases and errors.\nTest before delivering.",
        tool_hints=["execute_code", "terminal"],
        reasoning_strategy="step_by_step",
        max_iterations=20,
        reasoning_effort="high",
    ),
    "analysis": LoRAConfig(
        name="analysis",
        description="Data analysis: statistics, visualization",
        system_prompt_template="You are a data analyst.\nUnderstand data structure first.\nCheck for outliers.\nUse appropriate statistical methods.",
        tool_hints=["execute_code", "terminal"],
        reasoning_strategy="exploratory",
        max_iterations=15,
        reasoning_effort="medium",
    ),
    "creative": LoRAConfig(
        name="creative",
        description="Creative tasks: writing, design, content",
        system_prompt_template="You are a creative professional.\nUnderstand the brief.\nBrainstorm ideas.\nExecute with attention to detail.",
        tool_hints=["image_generate", "browser_snapshot"],
        reasoning_strategy="divergent",
        max_iterations=10,
        reasoning_effort="medium",
    ),
    "research": LoRAConfig(
        name="research",
        description="Research tasks: search, investigate, synthesize",
        system_prompt_template="You are a research specialist.\nDefine the question.\nSearch multiple sources.\nEvaluate credibility.\nCite sources properly.",
        tool_hints=["browser_navigate", "browser_snapshot", "terminal"],
        reasoning_strategy="systematic",
        max_iterations=20,
        reasoning_effort="high",
    ),
    "file_ops": LoRAConfig(
        name="file_ops",
        description="File operations: read, write, manage",
        system_prompt_template="You are a file operations specialist.\nVerify file exists.\nUse appropriate tools.\nHandle encoding correctly.\nConfirm operations.",
        tool_hints=["terminal", "execute_code"],
        reasoning_strategy="sequential",
        max_iterations=10,
        reasoning_effort="low",
    ),
    "default": LoRAConfig(
        name="default",
        description="General tasks",
        system_prompt_template="You are a helpful AI assistant.\nUnderstand the request.\nBreak down complex tasks.\nVerify your work.",
        tool_hints=[],
        reasoning_strategy="adaptive",
        max_iterations=15,
        reasoning_effort="medium",
    ),
}

class LoRAAdapter:
    def __init__(self):
        self.adapters = ADAPTER_CONFIGS.copy()
        self.current_adapter = None
    
    def select_adapter(self, task_category):
        if task_category == "general" or task_category not in self.adapters:
            adapter_name = "default"
        else:
            adapter_name = task_category
        self.current_adapter = adapter_name
        return adapter_name, self.adapters[adapter_name]
    
    def get_enhanced_system_prompt(self, base_system, task_category, complexity="medium"):
        adapter_name, config = self.select_adapter(task_category)
        
        enhanced = base_system + "\n\n"
        enhanced += "[ADAPTER:" + adapter_name + "]\n"
        enhanced += config.system_prompt_template
        
        if config.tool_hints:
            enhanced += "\n\n[PREFERRED_TOOLS:" + ",".join(config.tool_hints) + "]"
        
        enhanced += "\n\n[REASONING_STRATEGY:" + config.reasoning_strategy + "]"
        enhanced += "\n[REASONING_EFFORT:" + config.reasoning_effort + "]"
        
        metadata = {
            "adapter_name": adapter_name,
            "adapter_description": config.description,
            "tool_hints": config.tool_hints,
            "reasoning_strategy": config.reasoning_strategy,
            "reasoning_effort": config.reasoning_effort,
            "max_iterations": config.max_iterations,
        }
        
        return enhanced, metadata
    
    def get_adapter_config(self, adapter_name):
        return self.adapters.get(adapter_name)
    
    def list_adapters(self):
        return [
            {
                "name": name,
                "description": config.description,
                "tool_hints": config.tool_hints,
                "reasoning_strategy": config.reasoning_strategy,
            }
            for name, config in self.adapters.items()
        ]

_adapter = None

def get_lora_adapter():
    global _adapter
    if _adapter is None:
        _adapter = LoRAAdapter()
    return _adapter

if __name__ == "__main__":
    adapter = LoRAAdapter()
    print("Available Adapters:")
    for info in adapter.list_adapters():
        print(f"  {info['name']}: {info['description']}")
    
    print("\nAdapter Selection Tests:")
    test_cases = [
        ("coding", "Write a Python function"),
        ("analysis", "Analyze this CSV"),
        ("creative", "Generate a poster"),
        ("research", "Search latest papers"),
        ("file_ops", "Read this file"),
        ("general", "Hello"),
    ]
    
    for category, msg in test_cases:
        enhanced, meta = adapter.get_enhanced_system_prompt(
            base_system="You are a helpful assistant.",
            task_category=category,
        )
        print(f"  {category}: adapter={meta['adapter_name']}, tools={meta['tool_hints']}")

#!/usr/bin/env python3
"""
Prompt Optimizer v2 — 基于prompt-ops PDO引擎优化Hermes skill prompts

用法:
    python3 prompt_optimizer.py --skill <name>    # PDO优化单个skill
    python3 prompt_optimizer.py --list             # 列出可优化的skills
    python3 prompt_optimizer.py --evaluate <name>  # 评估优化效果
"""

import os
import sys
import json
import time
import yaml
import subprocess
import argparse
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"
CACHE_DIR = HERMES_HOME / "cache" / "prompt-optimized"


def parse_frontmatter(path: Path) -> tuple:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---"):
            return {}, content
        end = content.index("---", 3)
        return yaml.safe_load(content[3:end].strip()) or {}, content[end+3:].strip()
    except:
        return {}, ""


def extract_skill_prompt(skill_path: Path) -> str:
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return ""
    fm, body = parse_frontmatter(skill_md)
    return body


def find_skill_path(skill_name: str) -> Path:
    path = SKILLS_DIR / skill_name
    if path.exists():
        return path
    for subdir in SKILLS_DIR.iterdir():
        if subdir.is_dir():
            candidate = subdir / skill_name
            if candidate.exists():
                return candidate
    return None


def pdo_optimize(skill_name: str, rounds: int = 3, duels: int = 5) -> dict:
    """使用PDO引擎优化skill prompt"""
    skill_path = find_skill_path(skill_name)
    if not skill_path:
        return {"success": False, "error": f"Skill '{skill_name}' 不存在"}

    prompt_text = extract_skill_prompt(skill_path)
    if not prompt_text or len(prompt_text) < 100:
        return {"success": False, "error": "prompt太短"}

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = CACHE_DIR / f"{skill_name}_prompt.txt"
    config_file = CACHE_DIR / f"{skill_name}_config.yaml"
    output_dir = CACHE_DIR / f"{skill_name}_pdo_output"

    prompt_file.write_text(prompt_text, encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 通用数据集（用于prompt质量评估）
    dataset_path = HERMES_HOME / "cache" / "prompt-optimized" / "eval_dataset.json"
    if not dataset_path.exists():
        # 创建最小评估数据集
        eval_data = [
            {"input": "Implement a new feature", "output": "Mode 1"},
            {"input": "Choose between framework A and B", "output": "Mode 2"},
            {"input": "Refactor the architecture", "output": "Mode 3"},
            {"input": "Fix a typo", "output": "Direct"},
        ]
        dataset_path.write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    config_content = f"""system_prompt:
  file: {prompt_file}
  inputs: [input]
  outputs: [output]
dataset:
  path: {dataset_path}
  input_field: input
  golden_output_field: output
model:
  task_model: openai/mimo-v2.5-pro
  proposer_model: openai/mimo-v2.5-pro
metric:
  class: prompt_ops.core.metrics.StandardJSONMetric
  output_field: answer
optimization:
  strategy: "pdo"
  task_type: close_ended
  answer_choices: ["Mode 1", "Mode 2", "Mode 3", "Direct"]
  total_rounds: {rounds}
  num_duels_per_round: {duels}
  num_eval_examples_per_duel: 1
  num_initial_instructions: 3
  thompson_alpha: 1.0
  ranking_method: copeland
  num_top_prompts_to_combine: 2
  num_new_prompts_to_generate: 3
  num_to_prune_each_round: 2
"""
    config_file.write_text(config_content, encoding="utf-8")

    start = time.time()
    try:
        result = subprocess.run(
            ["prompt-ops", "migrate", "--config", str(config_file),
             "--output-dir", str(output_dir)],
            capture_output=True, text=True, timeout=600,
            cwd="/tmp/prompt-ops"
        )
        elapsed = time.time() - start

        if result.returncode != 0:
            return {"success": False, "error": result.stderr[:300], "elapsed": f"{elapsed:.1f}s"}

        # 提取优化后的prompt
        output_files = sorted(output_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
        if output_files:
            with open(output_files[-1]) as f:
                data = json.load(f)
            optimized = data.get("optimized_prompt", data.get("prompt", ""))
            if optimized:
                out_path = CACHE_DIR / f"{skill_name}.optimized.md"
                out_path.write_text(optimized, encoding="utf-8")
                return {
                    "success": True,
                    "skill": skill_name,
                    "original_chars": len(prompt_text),
                    "optimized_chars": len(optimized),
                    "compression": f"{100 - len(optimized)*100//len(prompt_text)}%",
                    "elapsed": f"{elapsed:.1f}s",
                    "output": str(out_path),
                }
        return {"success": False, "error": "无法提取结果", "elapsed": f"{elapsed:.1f}s"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "超时(600s)", "elapsed": "600s"}
    except Exception as e:
        return {"success": False, "error": str(e), "elapsed": f"{time.time()-start:.1f}s"}


def list_optimizable():
    skills = []
    for item in sorted(SKILLS_DIR.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        if (item / "SKILL.md").exists():
            sub = [d for d in item.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
            if len(sub) == 0:
                prompt = extract_skill_prompt(item)
                if prompt and len(prompt) >= 200:
                    skills.append(item.name)
        for sub in sorted(item.iterdir()):
            if sub.is_dir() and (sub / "SKILL.md").exists():
                prompt = extract_skill_prompt(sub)
                if prompt and len(prompt) >= 200:
                    skills.append(sub.name)
    return skills


def main():
    parser = argparse.ArgumentParser(description="Hermes Prompt Optimizer v2 (PDO)")
    parser.add_argument("--skill", type=str, help="PDO优化单个skill")
    parser.add_argument("--list", action="store_true", help="列出可优化的skills")
    parser.add_argument("--rounds", type=int, default=3, help="PDO轮数")
    parser.add_argument("--duels", type=int, default=5, help="每轮对决数")
    args = parser.parse_args()

    if args.list:
        skills = list_optimizable()
        print(f"可优化的skills: {len(skills)}个")
        for s in skills:
            print(f"  {s}")
        return

    if args.skill:
        print(f"PDO优化: {args.skill} (rounds={args.rounds}, duels={args.duels})")
        result = pdo_optimize(args.skill, rounds=args.rounds, duels=args.duels)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    parser.print_help()


if __name__ == "__main__":
    main()

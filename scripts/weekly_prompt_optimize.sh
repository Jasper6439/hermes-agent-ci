#!/bin/bash
# 每周日凌晨运行，优化top-10高频skills
LOG=~/.hermes/logs/prompt-optimize.log
mkdir -p ~/.hermes/logs

echo "$(date): 开始prompt优化" >> $LOG

for skill in sisterhood-enhanced brainstorming goal-decompose simplify-code okx-trading-v2 risk-manager; do
    echo "$(date): 优化 $skill" >> $LOG
    python3 ~/hermes/scripts/prompt_optimizer.py --skill $skill --rounds 2 --duels 3 >> $LOG 2>&1
done

echo "$(date): prompt优化完成" >> $LOG

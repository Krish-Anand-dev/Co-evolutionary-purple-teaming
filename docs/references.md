# References and links

Titles and arXiv IDs were checked on 26 Oct 2026. Open each paper before citing it; do not trust a title or number
from a summary.

## Papers
1. Zhou et al., *Purple-teaming LLMs with Adversarial Defender Training* (PAD): https://arxiv.org/abs/2407.01850
2. Hemberg et al., *Evolutionary and Coevolutionary Multi-Agent Design Choices and Dynamics*: https://arxiv.org/abs/2507.05534
3. Shaikh, Bastian, Shah, *A Red Teaming Framework for Evaluating Robustness of AI-enabled SOAR Systems*: https://arxiv.org/abs/2605.17075
4. Castro et al., *Large Language Models are Autonomous Cyber Defenders*: https://arxiv.org/abs/2505.04843
5. *Co-RedTeam: Orchestrated Security Discovery and Exploitation with LLM Agents*: https://arxiv.org/abs/2602.02164 (not 2503.07238)
6. Guo et al., *BlueCodeAgent: A Blue Teaming Agent Enabled by Automated Red Teaming for CodeGen AI*: https://arxiv.org/abs/2510.18131
7. Park et al., *Toward an Autonomous Purple Teaming Framework for Security and Safety in Large Language Models* (PRDC 2025): https://yonsei.elsevierpure.com/en/publications/toward-an-autonomous-purple-teaming-framework-for-security-and-sa/

## Environment, rules and ATT&CK
- CAGE Challenge 4: https://github.com/cage-challenge/cage-challenge-4 and https://cage-challenge.github.io/cage-challenge-4/
- CybORG: https://github.com/cage-challenge/CybORG
- Sigma specification: https://github.com/SigmaHQ/sigma-specification, pySigma: https://github.com/SigmaHQ/pySigma
- MITRE ATT&CK: https://attack.mitre.org (technique IDs checked in [attack-mapping-check.md](attack-mapping-check.md))

## Local models used for the Blue-side measurements
- Gemma-4-26B-A4B-it (Unsloth GGUF, Q3_K_M), GLM-4.7-Flash (Q3_K_M), and Qwen3-30B-A3B-Instruct-2507 (Unsloth GGUF, UD-Q3_K_XL): https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF
- llama.cpp (`llama-server`, build b11756, CUDA): https://github.com/ggml-org/llama.cpp
- Model files are not committed (`*.gguf` is gitignored).

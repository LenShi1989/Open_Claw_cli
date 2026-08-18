```powershell
# ==========================================
# OpenClaw + Ollama + Qwen3.5 9B
# Windows / RTX 3060 12GB
# ==========================================

# 1. 確認 NVIDIA
nvidia-smi

# 2. 確認 Ollama
ollama --version

# 3. 測試 Ollama API
curl http://localhost:11434/api/tags

# 4. 下載 Coding Agent 模型
ollama pull qwen3.5:9b

# 5. 測試模型
ollama run qwen3.5:9b

# 離開模型後繼續

# 6. 設定 Ollama local credential marker
[Environment]::SetEnvironmentVariable(
    "OLLAMA_API_KEY",
    "ollama-local",
    "User"
)

$env:OLLAMA_API_KEY="ollama-local"

# 7. 安裝 OpenClaw
iwr -useb https://openclaw.ai/install.ps1 | iex

# 8. 確認 OpenClaw
openclaw --version

# 9. Doctor
openclaw doctor

# 10. 查看 Ollama 模型
openclaw models list --provider ollama

# 11. 設定主要模型
openclaw models set ollama/qwen3.5:9b

# 12. 確認模型
openclaw models list --provider ollama

# 13. 安裝 Gateway
openclaw gateway install

# 14. 查看 Gateway
openclaw gateway status --json
```
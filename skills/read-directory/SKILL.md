---
name: read-directory
description: Windows Node 專案目錄讀取與分析工具。讓 OpenClaw Agent 能透過已配對的 Windows Node，直接查看目前工作目錄、列出目錄、遞迴搜尋檔案、讀取文字檔、搜尋檔案內容、分析專案結構。適用於 Windows + PowerShell + OpenClaw Node 環境。
---

---

# OpenClaw Windows Node Directory Reader

## 1. Skill 目的

本 Skill 的目的是讓 OpenClaw Agent 可以直接讀取 Windows Node 上的專案目錄。

主要用途：

- 查看目前工作目錄
- 列出目錄
- 遞迴列出專案檔案
- 搜尋指定檔案
- 搜尋檔案內容
- 讀取 Markdown
- 讀取 JSON
- 讀取 YAML / YML
- 讀取 TypeScript / JavaScript
- 讀取 Python
- 讀取 C#
- 讀取 ASP.NET Core 專案
- 讀取 Vue / Vite 專案
- 讀取 Docker 專案
- 分析 Git 專案
- 分析整個專案結構

---

# 2. 核心原則

Agent 必須區分：

```text
Gateway / Agent
        │
        │ exec host=node
        ▼
Windows OpenClaw Node
        │
        ▼
PowerShell
        │
        ▼
C:\Users\...
D:\Projects\...
E:\...
```

不要假設：

```text
Agent Workspace
=
Windows Node 專案目錄
```

如果專案位於 Windows Node 上，必須透過：

```text
exec
host=node
```

執行 Windows 命令。

---

# 3. 不要使用錯誤方式

不要使用：

```powershell
openclaw nodes invoke --node <node> --command system.run
```

目前 OpenClaw 的 `nodes invoke` 不提供 `system.run` / `system.run.prepare`。

Shell 執行應使用 Agent 的：

```text
exec
host=node
```

官方文件也明確說明：

```text
system.run
system.run.prepare
```

走 `exec host=node`。

`nodes invoke` 可用於：

```text
system.which
```

等明確 Node RPC。

---

# 4. Node 狀態檢查

當需要讀取 Windows Node 時，先確認 Node 是否存在。

使用：

```powershell
openclaw nodes status
```

需要確認：

```text
Paired
Connected
```

如果 Node 沒有連線：

```text
不要假裝可以讀取 Windows 目錄。
```

應回報：

```text
Windows Node 尚未連線，因此目前無法直接讀取該 Windows 目錄。
```

---

# 5. Node 名稱

不要硬編碼 Node 名稱。

優先使用：

```text
node id
```

或：

```text
node name
```

例如：

```text
LAPTOP-1JM8EAAF
```

但實際使用時必須以：

```powershell
openclaw nodes status
```

取得的最新 Node ID / Name 為準。

---

# 6. 檢查 Windows Node 的 PowerShell

可以使用：

```powershell
openclaw nodes invoke --node "<NODE>" --command system.which --params '{"bins":["powershell.exe"]}'
```

也可以檢查：

```powershell
openclaw nodes invoke --node "<NODE>" --command system.which --params '{"bins":["cmd.exe"]}'
```

檢查 Git：

```powershell
openclaw nodes invoke --node "<NODE>" --command system.which --params '{"bins":["git.exe"]}'
```

---

# 7. system.which JSON 規則

PowerShell 中必須使用合法 JSON。

正確：

```powershell
--params '{"bins":["powershell.exe"]}'
```

正確：

```powershell
--params '{"bins":["git.exe"]}'
```

錯誤：

```powershell
--params '{bins:["git.exe"]}'
```

錯誤：

```powershell
--params "{bins:'git.exe'}"
```

錯誤：

```powershell
--params '{"name":"dir"}'
```

新版 `system.which` 使用：

```json
{
  "bins": ["git"]
}
```

---

# 8. 讀取目前 Windows 專案目錄

當使用者說：

```text
讀取目前目錄
```

Agent 應優先在 Windows Node 上執行：

```powershell
Get-Location
```

然後：

```powershell
Get-ChildItem -Force
```

如果使用者要求完整結構：

```powershell
Get-ChildItem -Recurse -Force
```

---

# 9. 取得目前目錄

PowerShell：

```powershell
Get-Location
```

或：

```powershell
$PWD.Path
```

建議：

```powershell
Write-Output $PWD.Path
```

---

# 10. 讀取第一層目錄

使用：

```powershell
Get-ChildItem -Force |
Select-Object Mode,Length,LastWriteTime,Name
```

---

# 11. 只列出檔案

使用：

```powershell
Get-ChildItem -File -Force
```

---

# 12. 只列出目錄

使用：

```powershell
Get-ChildItem -Directory -Force
```

---

# 13. 遞迴列出所有檔案

使用：

```powershell
Get-ChildItem -Recurse -File -Force |
Select-Object FullName,Length,LastWriteTime
```

---

# 14. 遞迴列出目錄結構

使用：

```powershell
Get-ChildItem -Recurse -Force |
Select-Object FullName
```

大型專案不要直接把所有內容讀入 Context。

先取得：

```text
檔案名稱
路徑
檔案大小
副檔名
```

再決定需要讀取哪些檔案。

---

# 15. 排除大型 / 無關目錄

讀取專案時預設排除：

```text
node_modules
.git
dist
build
coverage
.vscode
.idea
bin
obj
__pycache__
.venv
venv
```

PowerShell：

```powershell
Get-ChildItem -Recurse -File -Force |
Where-Object {
    $_.FullName -notmatch '\\node_modules\\' -and
    $_.FullName -notmatch '\\.git\\' -and
    $_.FullName -notmatch '\\dist\\' -and
    $_.FullName -notmatch '\\build\\' -and
    $_.FullName -notmatch '\\coverage\\' -and
    $_.FullName -notmatch '\\.vscode\\' -and
    $_.FullName -notmatch '\\.idea\\' -and
    $_.FullName -notmatch '\\bin\\' -and
    $_.FullName -notmatch '\\obj\\' -and
    $_.FullName -notmatch '\\__pycache__\\' -and
    $_.FullName -notmatch '\\.venv\\' -and
    $_.FullName -notmatch '\\venv\\'
}
```

---

# 16. 搜尋指定檔案

搜尋 README：

```powershell
Get-ChildItem -Recurse -File -Filter "README.md"
```

搜尋所有 Markdown：

```powershell
Get-ChildItem -Recurse -File -Filter "*.md"
```

搜尋 Python：

```powershell
Get-ChildItem -Recurse -File -Filter "*.py"
```

搜尋 C#：

```powershell
Get-ChildItem -Recurse -File -Filter "*.cs"
```

搜尋 TypeScript：

```powershell
Get-ChildItem -Recurse -File -Filter "*.ts"
```

搜尋 Vue：

```powershell
Get-ChildItem -Recurse -File -Filter "*.vue"
```

---

# 17. 搜尋檔案內容

使用：

```powershell
Get-ChildItem -Recurse -File |
Select-String -Pattern "connectionString"
```

例如搜尋：

```text
connectionString
```

```powershell
Get-ChildItem -Recurse -File |
Select-String -Pattern "connectionString"
```

搜尋：

```text
OpenClaw
```

```powershell
Get-ChildItem -Recurse -File |
Select-String -Pattern "OpenClaw"
```

---

# 18. 排除大型目錄後搜尋

推薦：

```powershell
Get-ChildItem -Recurse -File -Force |
Where-Object {
    $_.FullName -notmatch '\\node_modules\\' -and
    $_.FullName -notmatch '\\.git\\' -and
    $_.FullName -notmatch '\\dist\\' -and
    $_.FullName -notmatch '\\bin\\' -and
    $_.FullName -notmatch '\\obj\\'
} |
Select-String -Pattern "connectionString"
```

---

# 19. 讀取 Markdown

使用：

```powershell
Get-Content ".\README.md" -Encoding UTF8 -Raw
```

---

# 20. 讀取 JSON

使用：

```powershell
Get-Content ".\package.json" -Encoding UTF8 -Raw
```

如果需要解析：

```powershell
Get-Content ".\package.json" -Encoding UTF8 -Raw |
ConvertFrom-Json
```

---

# 21. 讀取 YAML

一般直接：

```powershell
Get-Content ".\config.yml" -Encoding UTF8 -Raw
```

不要假設 Windows PowerShell 內建 YAML parser。

---

# 22. 讀取程式碼

Python：

```powershell
Get-Content ".\main.py" -Encoding UTF8 -Raw
```

TypeScript：

```powershell
Get-Content ".\src\main.ts" -Encoding UTF8 -Raw
```

Vue：

```powershell
Get-Content ".\src\App.vue" -Encoding UTF8 -Raw
```

C#：

```powershell
Get-Content ".\Program.cs" -Encoding UTF8 -Raw
```

---

# 23. 讀取大型檔案

不要直接：

```powershell
Get-Content huge.log -Raw
```

應先取得：

```powershell
Get-Item ".\huge.log" |
Select-Object FullName,Length,LastWriteTime
```

只讀取前面：

```powershell
Get-Content ".\huge.log" -TotalCount 200
```

只讀取最後：

```powershell
Get-Content ".\huge.log" -Tail 200
```

---

# 24. 取得檔案資訊

使用：

```powershell
Get-Item ".\README.md" |
Select-Object FullName,Length,CreationTime,LastWriteTime
```

---

# 25. 專案分析流程

當使用者說：

```text
分析這個專案
```

必須按照以下流程。

## Step 1

取得目前目錄：

```powershell
Get-Location
```

## Step 2

列出第一層：

```powershell
Get-ChildItem -Force
```

## Step 3

取得專案檔案：

```powershell
Get-ChildItem -Recurse -File -Force
```

排除大型目錄。

## Step 4

判斷專案類型。

### Node / Vue

尋找：

```text
package.json
pnpm-lock.yaml
package-lock.json
yarn.lock
vite.config.*
tsconfig.json
src/
```

### ASP.NET Core

尋找：

```text
*.sln
*.csproj
Program.cs
appsettings.json
appsettings.*.json
Controllers/
Services/
Models/
```

### Python

尋找：

```text
requirements.txt
pyproject.toml
setup.py
main.py
app.py
```

### Docker

尋找：

```text
Dockerfile
docker-compose.yml
compose.yml
.dockerignore
```

### Git

尋找：

```text
.gitignore
.gitattributes
.git/
```

---

# 26. Vue / Vite 專案

優先讀取：

```text
package.json
vite.config.*
tsconfig.json
src/main.*
src/App.*
```

然後根據問題讀取：

```text
src/components/
src/views/
src/router/
src/stores/
src/api/
```

不要預設讀取：

```text
node_modules/
dist/
```

---

# 27. ASP.NET Core 專案

優先讀取：

```text
*.sln
*.csproj
Program.cs
appsettings.json
```

然後分析：

```text
Controllers/
Services/
Models/
Repositories/
Data/
DTOs/
```

不要預設讀取：

```text
bin/
obj/
```

---

# 28. Python 專案

優先讀取：

```text
pyproject.toml
requirements.txt
main.py
app.py
```

再依需求讀取：

```text
src/
app/
models/
services/
utils/
```

不要預設讀取：

```text
.venv/
venv/
__pycache__/
```

---

# 29. Git 專案

確認：

```powershell
Get-ChildItem -Force
```

如果存在：

```text
.git
```

可以讀取：

```text
.gitignore
```

但不要直接讀取：

```text
.git/
```

內部大量物件。

如果需要 Git 狀態，可以使用：

```powershell
git status --short
```

如果需要 branch：

```powershell
git branch --show-current
```

---

# 30. 敏感檔案

預設不要主動讀取：

```text
.env
.env.*
*.pem
*.key
id_rsa
id_ed25519
credentials.*
secrets.*
```

尤其不要主動將：

```text
API Key
Token
Password
Private Key
Connection String
```

完整輸出給使用者。

如果使用者明確要求分析設定：

1. 先確認必要性
2. 只讀取必要部分
3. 回應時遮蔽 Secret

例如：

```text
API_KEY=********
PASSWORD=********
TOKEN=********
```

---

# 31. 大型專案 Context 保護

如果專案超過 100 個檔案：

不要全部讀取內容。

先執行：

```powershell
Get-ChildItem -Recurse -File |
Group-Object Extension |
Sort-Object Count -Descending
```

再依副檔名統計。

例如：

```text
.cs     82
.ts     46
.vue    31
.json   12
.md      8
```

然後只讀取與使用者問題相關的檔案。

---

# 32. 避免一次讀取 Binary

以下副檔名不要使用 `Get-Content -Raw`：

```text
.exe
.dll
.zip
7z
rar
png
jpg
jpeg
gif
webp
mp4
avi
mov
pdf
docx
xlsx
```

如果使用者要求分析 Binary：

先取得檔案資訊：

```powershell
Get-Item ".\file.exe" |
Select-Object FullName,Length,LastWriteTime
```

不要把 Binary 當文字讀取。

---

# 33. 目錄不存在

如果：

```powershell
Test-Path "C:\Some\Project"
```

回傳：

```text
False
```

不要假裝目錄存在。

回報：

```text
指定 Windows 目錄不存在：

C:\Some\Project
```

---

# 34. 權限不足

如果 PowerShell 回傳：

```text
Access is denied
```

回報：

```text
Windows Node 已連線，但目前帳號沒有讀取該目錄的權限。
```

不要反覆嘗試繞過 Windows 權限。

---

# 35. Node 未連線

如果 Node 狀態：

```text
Connected: 0
```

回報：

```text
Windows Node 目前未連線，因此無法讀取 Windows 專案目錄。
```

不要把 Gateway 的 Linux / WSL 工作目錄當成 Windows Node。

---

# 36. Workspace 與 Node 路徑

必須區分：

```text
Gateway Workspace
```

與：

```text
Windows Node Workspace
```

例如：

```text
Gateway:
C:\Users\admin\.openclaw\workspace

Windows Node:
C:\Users\admin\Documents\MyProject
```

兩者不是同一個檔案系統。

---

# 37. 建議的 Windows Node Skill 位置

在 Windows Node 上：

```text
%USERPROFILE%\.openclaw\skills\read-directory\SKILL.md
```

例如：

```text
C:\Users\admin\.openclaw\skills\read-directory\SKILL.md
```

目錄名稱：

```text
read-directory
```

必須與：

```yaml
name: read-directory
```

一致。

---

# 38. Skill 安裝

PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.openclaw\skills\read-directory"
```

然後把：

```text
SKILL.md
```

放入：

```text
$HOME\.openclaw\skills\read-directory\
```

---

# 39. 確認 Skill

查看：

```powershell
Get-ChildItem "$HOME\.openclaw\skills\read-directory"
```

應看到：

```text
SKILL.md
```

---

# 40. Node Skill 發布

Node Host 連線後會發布有效的 `SKILL.md`。

修改 Skill 後：

```text
重新啟動 Windows OpenClaw Node
```

例如：

```powershell
openclaw node restart
```

如果目前 Node 是前景執行：

```text
Ctrl+C
```

再重新：

```powershell
openclaw node run ...
```

OpenClaw 官方文件指出 Node Host 不會即時監看 skills 目錄，因此修改後需要重新啟動 Node。

---

# 41. Skill 執行優先順序

使用者要求：

```text
讀取目前目錄
```

Agent：

```text
1. 確認 Windows Node
2. 確認 Node connected
3. 使用 exec host=node
4. 執行 PowerShell
5. 取得目錄
6. 回報結果
```

---

# 42. 讀取專案標準流程

使用者：

```text
讀取這個專案
```

執行：

```powershell
Get-Location
```

接著：

```powershell
Get-ChildItem -Force
```

再：

```powershell
Get-ChildItem -Recurse -File -Force
```

排除：

```text
node_modules
.git
dist
build
coverage
bin
obj
.venv
venv
__pycache__
```

然後尋找：

```text
README.md
package.json
*.sln
*.csproj
requirements.txt
pyproject.toml
docker-compose.yml
compose.yml
Dockerfile
```

最後依使用者需求讀取程式碼。

---

# 43. 不要猜測工作目錄

不要因為使用者之前曾使用：

```text
C:\Users\admin\Desktop\project
```

就假設目前目錄仍然是：

```text
C:\Users\admin\Desktop\project
```

永遠先：

```powershell
Get-Location
```

如果使用者指定：

```text
C:\Users\admin\Desktop\openClaw_Test
```

才使用指定路徑。

---

# 44. 使用者指定目錄

例如：

```text
讀取 C:\Users\admin\Documents\food-ordering-frontend
```

使用：

```powershell
Test-Path "C:\Users\admin\Documents\food-ordering-frontend"
```

確認存在後：

```powershell
Get-ChildItem "C:\Users\admin\Documents\food-ordering-frontend" -Force
```

---

# 45. 指定目錄的完整專案掃描

```powershell
$root = "C:\Users\admin\Documents\food-ordering-frontend"

Get-ChildItem $root -Recurse -File -Force |
Where-Object {
    $_.FullName -notmatch '\\node_modules\\' -and
    $_.FullName -notmatch '\\.git\\' -and
    $_.FullName -notmatch '\\dist\\' -and
    $_.FullName -notmatch '\\coverage\\'
} |
Select-Object FullName,Length,LastWriteTime
```

---

# 46. 使用工作目錄執行

如果 Agent 的 exec 工具支援：

```text
host=node
cwd=<Windows project path>
```

優先設定：

```text
cwd
```

例如：

```text
cwd:
C:\Users\admin\Documents\food-ordering-frontend
```

然後執行：

```powershell
Get-ChildItem -Force
```

這樣比每一個命令都寫完整路徑更可靠。

---

# 47. 讀取目前專案 README

如果 cwd 已經是專案：

```powershell
Get-Content ".\README.md" -Encoding UTF8 -Raw
```

如果不存在：

```powershell
Test-Path ".\README.md"
```

---

# 48. 找出專案入口

Node：

```powershell
Get-ChildItem -Recurse -File |
Where-Object {
    $_.Name -in @(
        "package.json",
        "vite.config.ts",
        "vite.config.js",
        "main.ts",
        "main.js"
    )
}
```

.NET：

```powershell
Get-ChildItem -Recurse -File |
Where-Object {
    $_.Extension -in @(".sln",".csproj") -or
    $_.Name -in @("Program.cs","Startup.cs")
}
```

Python：

```powershell
Get-ChildItem -Recurse -File |
Where-Object {
    $_.Name -in @(
        "main.py",
        "app.py",
        "pyproject.toml",
        "requirements.txt"
    )
}
```

---

# 49. 回應格式

當讀取成功時：

```text
Windows Node 目錄讀取成功。

Node:
<NODE>

工作目錄:
<PATH>

第一層內容:
<FILES>

專案類型:
<Vue / ASP.NET / Python / Docker / ...>
```

如果只是使用者要求查看檔案，不要輸出大量無關說明。

---

# 50. 讀取失敗格式

Node 未連線：

```text
❌ Windows Node 未連線
無法直接讀取 Windows 專案目錄。
```

路徑不存在：

```text
❌ 目錄不存在
<PATH>
```

權限錯誤：

```text
❌ Windows 權限不足
<PATH>
```

命令被 Exec Approval 阻擋：

```text
⚠️ Windows Node 已連線，但 system.run / exec 被 Exec Approval 阻擋。

請先允許此 Node 執行必要的 PowerShell 命令。
```

---

# 51. 安全原則

此 Skill 主要用於：

```text
READ
SEARCH
ANALYZE
```

預設不要進行：

```text
DELETE
FORMAT
REGISTRY MODIFICATION
SERVICE MODIFICATION
FIREWALL MODIFICATION
CREDENTIAL MODIFICATION
```

除非使用者明確要求。

---

# 52. 寫入檔案

本 Skill 主要是讀取。

如果使用者要求：

```text
建立檔案
修改檔案
寫入檔案
```

必須確認使用者明確要求修改。

不要因為「分析專案」而自行修改。

---

# 53. 最重要規則

收到：

```text
讀取目錄
```

不要只回答：

```text
我可以幫你讀取。
```

應該實際執行讀取流程。

收到：

```text
分析專案
```

不要要求使用者逐個提供檔案。

應直接：

```text
取得 Windows Node
→
取得工作目錄
→
取得專案結構
→
判斷專案類型
→
讀取重要設定檔
→
依問題讀取程式碼
```

---

# 54. 最終判斷

Agent 必須遵守：

```text
Windows 專案
    ↓
Windows OpenClaw Node
    ↓
exec host=node
    ↓
PowerShell
    ↓
Get-Location
    ↓
Get-ChildItem
    ↓
Get-Content
    ↓
Select-String
```

不要將：

```text
nodes invoke system.run
```

當成目前版本的標準 Shell 執行方式。

`nodes invoke` 主要用於明確的 Node RPC，例如：

```powershell
system.which
```

Shell / PowerShell 則使用：

```text
exec
host=node
```

---

# 55. 完成條件

只有在實際取得 Windows Node 的檔案系統結果後，才可以說：

```text
已讀取目錄
```

如果沒有成功執行：

```text
Get-Location
Get-ChildItem
```

就不能宣稱已經讀取專案。

如果 Node 不存在、Node 未連線、Exec Approval 被拒絕、路徑不存在或權限不足，必須明確告知使用者。

## 絕對不要虛構檔案或目錄內容。

## End of Skill

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$PromptFile,

    [ValidateRange(1, 3)]
    [int]$MaxRounds = 3,

    [ValidateRange(1, 15)]
    [int]$ClaudeTimeoutMinutes = 10,

    [string[]]$AllowedPath = @(),

    [string[]]$RequiredArtifact = @(),

    [string]$VerificationScript,

    [switch]$AllowDirtyBaseline,

    [switch]$Plan,

    [switch]$Run
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ProjectPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Get-RelativePath {
    param([string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = $RepoRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the repository: $Path"
    }
    return $full.Substring($root.Length).Replace('\', '/')
}

function Invoke-Checked {
    param(
        [string]$Command,
        [string[]]$Arguments,
        [string]$OutputPath,
        [int]$TimeoutSeconds = 300,
        [string]$InputText
    )
    $resolvedCommand = Resolve-Executable $Command
    $stdoutPath = "$OutputPath.stdout"
    $stderrPath = "$OutputPath.stderr"
    $stdinPath = "$OutputPath.stdin"
    $quotedArguments = ($Arguments | ForEach-Object {
        '"' + $_.Replace('"', '\"') + '"'
    }) -join ' '
    $startProcess = @{
        FilePath = $resolvedCommand
        ArgumentList = $quotedArguments
        PassThru = $true
        NoNewWindow = $true
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
    }
    if ($PSBoundParameters.ContainsKey("InputText")) {
        [System.IO.File]::WriteAllText($stdinPath, $InputText, [System.Text.UTF8Encoding]::new($false))
        $startProcess.RedirectStandardInput = $stdinPath
    }
    $process = Start-Process @startProcess
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        & taskkill /PID $process.Id /T /F | Out-Null
        throw "$Command exceeded the $TimeoutSeconds-second timeout; its process tree was terminated."
    }
    $process.Refresh()
    $exitCode = $process.ExitCode
    $text = @(
        if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw }
        if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw }
    ) -join [Environment]::NewLine
    # Claude's Windows .cmd wrapper occasionally leaves Process.ExitCode unset
    # after redirected stdin, even when its only result object says success.
    # Accept that narrow, machine-verifiable case; every other missing exit code
    # remains a failure instead of being silently treated as green.
    if (($null -eq $exitCode -or "$exitCode" -eq "") -and $Command -eq "claude") {
        $claudeSuccess = $false
        $lines = @($text -split "`r?`n")
        [array]::Reverse($lines)
        foreach ($line in $lines) {
            try {
                $result = $line | ConvertFrom-Json -ErrorAction Stop
                if ($result.subtype -eq "success" -and -not $result.is_error) {
                    $claudeSuccess = $true
                }
                break
            } catch {
                continue
            }
        }
        if ($claudeSuccess) { $exitCode = 0 }
    }
    $text | Set-Content -LiteralPath $OutputPath -Encoding utf8
    Remove-Item -LiteralPath $stdoutPath, $stderrPath, $stdinPath -Force -ErrorAction SilentlyContinue
    if ($exitCode -ne 0) {
        throw "$Command failed with exit code $exitCode. See $OutputPath"
    }
    return $text
}

function Resolve-Executable {
    param([string]$Command)

    if ([System.IO.Path]::IsPathRooted($Command) -and (Test-Path -LiteralPath $Command -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $Command).Path
    }

    $resolved = Get-Command $Command -ErrorAction Stop
    if ($resolved.CommandType -eq "ExternalScript" -and $resolved.Path -like "*.ps1") {
        $cmdShim = [System.IO.Path]::ChangeExtension($resolved.Path, ".cmd")
        if (Test-Path -LiteralPath $cmdShim -PathType Leaf) {
            return $cmdShim
        }
    }
    if ($resolved.Path) { return $resolved.Path }
    if ($resolved.Source) { return $resolved.Source }
    throw "Unable to resolve an executable path for $Command."
}

function Get-SourceSnapshot {
    $excluded = @(".git", ".codegraph", ".venv", "node_modules", "outputs", "input")
    $snapshot = [ordered]@{}
    Get-ChildItem -LiteralPath $RepoRoot -Recurse -File | ForEach-Object {
        $relative = Get-RelativePath $_.FullName
        $first = $relative.Split('/')[0]
        if ($excluded -contains $first) { return }
        $stream = [System.IO.File]::OpenRead($_.FullName)
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $snapshot[$relative] = ([System.BitConverter]::ToString($sha256.ComputeHash($stream))).Replace('-', '')
        } finally {
            $sha256.Dispose()
            $stream.Dispose()
        }
    }
    return $snapshot
}

function Compare-Snapshots {
    param($Before, $After)
    $all = @($Before.Keys + $After.Keys | Sort-Object -Unique)
    return @($all | Where-Object { $Before[$_] -ne $After[$_] })
}

function Test-PathAllowed {
    param([string]$RelativePath)
    foreach ($allowed in $AllowedPath) {
        $prefix = $allowed.Trim().Replace('\', '/').TrimEnd('/')
        if ($RelativePath -eq $prefix -or $RelativePath.StartsWith("$prefix/", [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Read-LastJsonObject {
    param([string]$Text, [string]$Label)
    $lines = @($Text -split "`r?`n")
    [array]::Reverse($lines)
    foreach ($line in $lines) {
        try {
            return $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
    }
    throw "$Label did not return a JSON object."
}

function Write-Json {
    param($Value, [string]$Path)
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding utf8
}

if (-not $Run) {
    Write-Output "PLAN ONLY — no agent, test, or review command will run."
    Write-Output "Run requires: -Run -PromptFile <task.md> -AllowedPath <repo-relative paths>."
    Write-Output "A dirty worktree is rejected by default; add -AllowDirtyBaseline only after reviewing the existing changes."
    Write-Output "The execution sequence is: claude -p -> codex exec (read-only JSON review) -> verification -> stop."
    Write-Output "Each Claude round is capped at $ClaudeTimeoutMinutes minute(s); a timeout terminates only its own process tree."
    Write-Output "MaxRounds is capped at 3. The runner never commits, pushes, merges, resets, cleans, or deletes source files."
    exit 0
}

if ($Plan) {
    throw "Choose either the default plan mode or -Run, not both."
}
if (-not (Test-Path -LiteralPath $PromptFile -PathType Leaf)) {
    throw "PromptFile was not found: $PromptFile"
}
if (-not $AllowedPath -or $AllowedPath.Count -eq 0) {
    throw "-AllowedPath is required for a real run so the loop has an explicit source scope."
}
$AllowedPath = @($AllowedPath | ForEach-Object { $_ -split ',' } | ForEach-Object {
    $candidate = $_.Trim().Replace('\\', '/').TrimEnd('/')
    if (-not $candidate -or [System.IO.Path]::IsPathRooted($candidate) -or $candidate.Split('/') -contains '..') {
        throw "Allowed paths must be non-empty repository-relative paths without '..': $_"
    }
    $candidate
})
if (-not (Test-Path -LiteralPath $ProjectPython -PathType Leaf)) {
    throw "Project Python is missing at $ProjectPython. Run slide-system/scripts/setup.ps1 first."
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw "Claude Code CLI was not found on PATH." }
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) { throw "Codex CLI was not found on PATH." }
if ($VerificationScript) {
    $VerificationScript = (Resolve-Path -LiteralPath $VerificationScript).Path
    Get-RelativePath $VerificationScript | Out-Null
}

Push-Location $RepoRoot
try {
    $initialStatus = (& git status --porcelain=v1 --untracked-files=all) -join [Environment]::NewLine
    if ($initialStatus -and -not $AllowDirtyBaseline) {
        throw "Worktree is already dirty. Review it first, then rerun with -AllowDirtyBaseline to record (not discard) the baseline."
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $evidenceRoot = Join-Path $RepoRoot "outputs\agent-qa-loops\$stamp"
    New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null
    $baseline = Get-SourceSnapshot
    $taskPrompt = Get-Content -LiteralPath $PromptFile -Raw -Encoding utf8
    if (-not $taskPrompt.Trim()) { throw "PromptFile is empty: $PromptFile" }

    $reviewSchema = @{ type = "object"; additionalProperties = $false; required = @("verdict", "summary", "findings"); properties = @{
        verdict = @{ type = "string"; enum = @("allow", "block") }
        summary = @{ type = "string" }
        findings = @{ type = "array"; items = @{ type = "object"; additionalProperties = $false; required = @("severity", "path", "message"); properties = @{
            severity = @{ type = "string"; enum = @("P0", "P1", "P2", "P3") }
            path = @{ type = "string" }
            message = @{ type = "string" }
        } } }
    } }
    $schemaPath = Join-Path $evidenceRoot "review-output.schema.json"
    Write-Json $reviewSchema $schemaPath
    Write-Json @{ started_at = (Get-Date).ToString("o"); prompt_file = (Get-RelativePath (Resolve-Path $PromptFile)); allowed_paths = $AllowedPath; dirty_baseline = [bool]$initialStatus; baseline_status = $initialStatus } (Join-Path $evidenceRoot "run-contract.json")

    $sessionId = $null
    $previousReview = $null
    for ($round = 1; $round -le $MaxRounds; $round++) {
        $roundDir = Join-Path $evidenceRoot ("round-{0:d2}" -f $round)
        New-Item -ItemType Directory -Path $roundDir -Force | Out-Null
        $beforeRound = Get-SourceSnapshot
        $roundPrompt = @"
You are in bounded implementation round $round of $MaxRounds.
Work only in these repository-relative paths: $($AllowedPath -join ', ').
Do not commit, push, merge, rebase, reset, clean, delete files, add dependencies, or modify .mcp.json/opencode.jsonc.
Use .venv\Scripts\python.exe for Python checks. Run the task's required tests and leave factual evidence in your response.
Complete one smallest coherent implementation slice in this round, then return control for Codex review. Do not attempt an unrelated refactor or defer a known failing test.

$taskPrompt
"@
        if ($previousReview) {
            $roundPrompt += "`n`nCodex review from the prior round follows. Fix every actionable finding, then rerun the required checks:`n$previousReview"
        }
        $roundPrompt | Set-Content -LiteralPath (Join-Path $roundDir "claude-prompt.md") -Encoding utf8

        $claudeArgs = @("-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--no-session-persistence")
        $claudeText = Invoke-Checked "claude" $claudeArgs (Join-Path $roundDir "claude-output.jsonl") ($ClaudeTimeoutMinutes * 60) $roundPrompt
        $claudeResult = Read-LastJsonObject $claudeText "Claude"
        $afterRound = Get-SourceSnapshot
        $roundChanged = Compare-Snapshots $beforeRound $afterRound
        $allChanged = Compare-Snapshots $baseline $afterRound
        Write-Json @{ round = $round; session_id = $claudeResult.session_id; changed_this_round = $roundChanged; changed_since_baseline = $allChanged } (Join-Path $roundDir "changes.json")
        if (-not $roundChanged) {
            throw "No source changes were made in round $round. Stopping rather than accepting an ALLOW verdict for a status-only turn."
        }
        $outOfScope = @($allChanged | Where-Object { -not (Test-PathAllowed $_) })
        if ($outOfScope) {
            throw "Loop changed paths outside -AllowedPath: $($outOfScope -join ', ')"
        }

        $reviewPrompt = @"
Review the current working tree read-only. Review ONLY these paths changed since this loop started:
$($allChanged | ForEach-Object { "- $_" } | Out-String)

Ignore all pre-existing changes outside that list. Check correctness, regressions, task constraints, test coverage, and whether claimed completion is supported by the actual files. Do not propose broad refactors. Return verdict=allow only when there are no actionable findings. A P0/P1/P2 finding requires verdict=block.
"@
        $reviewArgs = @("exec", "--sandbox", "read-only", "--output-schema", $schemaPath,
                        "--output-last-message", (Join-Path $roundDir "codex-review.json"),
                        "--color", "never")
        $reviewText = Invoke-Checked "codex" $reviewArgs (Join-Path $roundDir "codex-review.log") 300 $reviewPrompt
        $reviewPath = Join-Path $roundDir "codex-review.json"
        if (-not (Test-Path -LiteralPath $reviewPath)) { throw "Codex did not write structured review output: $reviewPath" }
        $review = Get-Content -LiteralPath $reviewPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($review.verdict -eq "block") {
            if ($round -eq $MaxRounds) {
                throw "Codex still found blocking issues after $MaxRounds rounds. See $reviewPath"
            }
            $previousReview = Get-Content -LiteralPath $reviewPath -Raw -Encoding utf8
            continue
        }

        foreach ($artifact in $RequiredArtifact) {
            $fullArtifact = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $artifact))
            Get-RelativePath $fullArtifact | Out-Null
            if (-not (Test-Path -LiteralPath $fullArtifact)) { throw "Required artifact is missing: $artifact" }
        }
        if ($VerificationScript) {
            Invoke-Checked "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $VerificationScript) (Join-Path $roundDir "verification.log") 600 | Out-Null
        } else {
            Invoke-Checked $ProjectPython @("slide-system/scripts/test_gates.py") (Join-Path $roundDir "test-gates.log") 300 | Out-Null
            Invoke-Checked $ProjectPython @("slide-system/scripts/validate_registry.py") (Join-Path $roundDir "validate-registry.log") 120 | Out-Null
            Invoke-Checked $ProjectPython @("slide-system/scripts/build_registry.py", "--check") (Join-Path $roundDir "build-registry.log") 120 | Out-Null
            Invoke-Checked "git" @("diff", "--check") (Join-Path $roundDir "diff-check.log") 60 | Out-Null
        }
        Write-Json @{ completed_at = (Get-Date).ToString("o"); round = $round; verdict = "allow"; evidence = (Get-RelativePath $evidenceRoot) } (Join-Path $evidenceRoot "result.json")
        Write-Output "ALLOW — Codex found no actionable findings and verification passed. Evidence: $evidenceRoot"
        exit 0
    }
} finally {
    Pop-Location
}

param(
    [switch]$Download,
    [string]$Destination = $PSScriptRoot,
    [System.Management.Automation.PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
$manifest = @'
{
  "version": "20260929-r6",
  "filename": "forecast-dispatch-20260929-r6.zip",
  "bytes": 1267514063,
  "sha256": "c02e460db1395d3ba4b858bc6f4bb729b51d919f2ea7131627efd729cf18940d",
  "source_commit": "42236b7e39c052105747bed5816384b6102e77f7",
  "image": "jingneng-fluxcast-all-in-one:20260929-r6",
  "image_id": "sha256:f7152e959c0affae0cc0a5b713ac50bd9a7285f3e6d972eed5546df530ac40ea",
  "parts": [
    {
      "name": "forecast-dispatch-20260929-r6.zip.001",
      "bytes": 67108864,
      "sha256": "6039c5bc35c9e5d5d7db92d9ce30e265a5d19709eb37fb03f8f622db69f6b695"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.002",
      "bytes": 67108864,
      "sha256": "3c4b98014f14053016f0729ba2a81a7d31b79c59f72a362da0d7b2170aa0e376"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.003",
      "bytes": 67108864,
      "sha256": "be851349738a8146505e569c1d797328ce119a7284add8e30dec900f42bf1a93"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.004",
      "bytes": 67108864,
      "sha256": "6bf56338e1249de3b11a3b35ac5dee7388520aceac384495d2fd9f35fed62730"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.005",
      "bytes": 67108864,
      "sha256": "c8400cb0da0c3b1b35182b6f721b4782d79dcfcee5e8d06e751bc91fe2127908"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.006",
      "bytes": 67108864,
      "sha256": "d51de862d7827bad43f68b69639074ab9a0b11496548dee4b88edac946a15081"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.007",
      "bytes": 67108864,
      "sha256": "b7dea0bf5993c3ea3bc2135788fca8762263e4c605a97561ecf5a61039588a06"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.008",
      "bytes": 67108864,
      "sha256": "6a178074cbae6c280e2ea10e0d8378dc9a96ee93525cc984369d2cb85265f0fb"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.009",
      "bytes": 67108864,
      "sha256": "e739472e1f19344c29566da3d71d496caf1211c1f841096e901b3e2efa491eb9"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.010",
      "bytes": 67108864,
      "sha256": "55f54da384f161b09308544f32d23011d9c89b4bca2222a77c89bc3baca93a60"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.011",
      "bytes": 67108864,
      "sha256": "58e2b3553acb17729eba225a1ec759fa2c002f6aabe82e60f6d605c2fc097f50"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.012",
      "bytes": 67108864,
      "sha256": "b400716359f6d06b7a6ef946f2fd6e28f3c266f1de26da1c809f53a52f55957e"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.013",
      "bytes": 67108864,
      "sha256": "20b43baad7a91f0c9ec750066d8f8f774652275614d47293cfce3a4f1b5f2649"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.014",
      "bytes": 67108864,
      "sha256": "2e11a756b3a1f917ef0e608ea347b8cca78ff6b2061ea1a95c3af52daf51a8f6"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.015",
      "bytes": 67108864,
      "sha256": "d9887421dbe4ed6906c83a815f252d43881387201722ff843cdb68a4e7fdc6fe"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.016",
      "bytes": 67108864,
      "sha256": "1f5c0b86b34630005c915f400cb3114c39dd06eb60cbd2b9633d9ff2b61cd7c6"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.017",
      "bytes": 67108864,
      "sha256": "c72c7e15f6cf188c065ee32fe87a27fbf13a83db7f4525634fcacdbe3dc743b2"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.018",
      "bytes": 67108864,
      "sha256": "a2ac128337ea78d6c3a004e878b5d5a9050fabc511d90d2d35d9ee6e86873b35"
    },
    {
      "name": "forecast-dispatch-20260929-r6.zip.019",
      "bytes": 59554511,
      "sha256": "f5e72a90b045e2ed6c14a9c6fa39217f7582a89cd1f475f3865da9fc6458f5af"
    }
  ]
}
'@ | ConvertFrom-Json
$origin = 'http://117.78.35.35'
$baseUrl = "$origin/api/v4/projects/56/packages/generic/forecast-dispatch/20260929-r6"
$directory = [IO.Path]::GetFullPath($Destination)
if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory | Out-Null }
$target = Join-Path $directory $manifest.filename
if (Test-Path -LiteralPath $target) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant() -eq $manifest.sha256) {
        Write-Host "Already verified: $target"
        return
    }
    throw "Output already exists with a different hash: $target"
}
$missing = @($manifest.parts | Where-Object { -not (Test-Path -LiteralPath (Join-Path $directory $_.name)) })
if ($Download -and $missing.Count -gt 0) {
    if (-not $Credential) { $Credential = Get-Credential -Message "Sign in to GitLab at $origin" }
    if (-not $Credential) { throw 'GitLab credentials are required to download this private package.' }
    $page = Invoke-WebRequest -UseBasicParsing -Uri "$origin/users/sign_in" -SessionVariable gitlabSession
    $token = [regex]::Match($page.Content, 'name="authenticity_token"[^>]*value="([^"]+)"').Groups[1].Value
    if (-not $token) { throw 'GitLab sign-in form changed; download the parts in your browser.' }
    $fields = @{'authenticity_token'=$token; 'user[login]'=$Credential.UserName; 'user[password]'=$Credential.GetNetworkCredential().Password}
    try { Invoke-WebRequest -UseBasicParsing -Uri "$origin/users/sign_in" -Method Post -WebSession $gitlabSession -Body $fields | Out-Null }
    finally { $fields.Clear() }
    Invoke-RestMethod -Uri "$origin/api/v4/user" -WebSession $gitlabSession | Out-Null
    foreach ($part in $missing) {
        $path = Join-Path $directory $part.name
        $partial = "$path.download"
        if (Test-Path -LiteralPath $partial) { throw "Partial file exists; remove it before retrying: $partial" }
        Write-Host "Downloading $($part.name)"
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/$($part.name)" -WebSession $gitlabSession -OutFile $partial -TimeoutSec 180
        if ((Get-Item -LiteralPath $partial).Length -ne $part.bytes -or (Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash.ToLowerInvariant() -ne $part.sha256) { throw "Download checksum mismatch: $($part.name)" }
        Move-Item -LiteralPath $partial -Destination $path
    }
}
foreach ($part in $manifest.parts) {
    $path = Join-Path $directory $part.name
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing $($part.name). Download all 19 parts or use -Download." }
    if ((Get-Item -LiteralPath $path).Length -ne $part.bytes -or (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() -ne $part.sha256) { throw "Part checksum mismatch: $($part.name)" }
}
$partial = "$target.assembling"
$stream = [IO.File]::Open($partial, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try {
    foreach ($part in $manifest.parts) {
        $partStream = [IO.File]::OpenRead((Join-Path $directory $part.name))
        try { $partStream.CopyTo($stream) } finally { $partStream.Dispose() }
    }
} finally { $stream.Dispose() }
if ((Get-Item -LiteralPath $partial).Length -ne $manifest.bytes -or (Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash.ToLowerInvariant() -ne $manifest.sha256) { throw 'Combined ZIP checksum mismatch.' }
Move-Item -LiteralPath $partial -Destination $target
Write-Host "Verified delivery: $target"
Write-Host "SHA256: $($manifest.sha256)"
Write-Host 'Extract the ZIP, then run start.ps1 (Windows) or sh start.sh (Linux).'

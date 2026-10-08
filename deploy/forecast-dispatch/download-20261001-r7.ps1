param(
    [switch]$Download,
    [string]$Destination = $PSScriptRoot,
    [System.Management.Automation.PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
$manifest = @'
{
  "version": "20261001-r7",
  "filename": "forecast-dispatch-20261001-r7.zip",
  "bytes": 1267420699,
  "sha256": "21ee6fe2d24f8bad74758ae6211252abe475c009481c7a13919b8fcbf9e95b9f",
  "source_commit": "037c69e017ffe0167b0fd0fd4077049f8485b42c",
  "image": "jingneng-fluxcast-all-in-one:20261001-r7",
  "image_id": "sha256:ec5da34c4ade0a3502bd03f606b5e6d216dc62e137564c039617710a5fe666e1",
  "parts": [
    {
      "name": "forecast-dispatch-20261001-r7.zip.001",
      "bytes": 67108864,
      "sha256": "5e0b2f6fcb50d1c936bc960ecfae02e79d6cfe36b0e48c2a8e2718092dd50086"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.002",
      "bytes": 67108864,
      "sha256": "eb3e7acd39d5d4d2dc68818352badbd963a3c28bcfb2896e563aa9ee6f4b8f7e"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.003",
      "bytes": 67108864,
      "sha256": "c0ac657c9e8f2f5f1957a0e16e8e538157010a0fed7ff0b947878b51b18fb670"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.004",
      "bytes": 67108864,
      "sha256": "c1d6367ebed6fa48156686c7541d91f8077acdc112c70dbacbb31fa3ebae64ed"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.005",
      "bytes": 67108864,
      "sha256": "89a2d54733c2af9650b6f1aa9871cf81d8959603fed93b80f3c40aa96da5f461"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.006",
      "bytes": 67108864,
      "sha256": "efdd976e73860323dd24c590b85d8fd7445008888dffdbd8ffb9608fb950d9b7"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.007",
      "bytes": 67108864,
      "sha256": "feefb5a1c001f279e3038f79dae4968a2b07e40e729e59caa7c07ea1ab0c6797"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.008",
      "bytes": 67108864,
      "sha256": "12fee8720d880d2105cf4d80c439edbdb192e0f1ac6752ed909d5be4491fefae"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.009",
      "bytes": 67108864,
      "sha256": "dd67305589d29cbe369c50954a3b75975d31a4a8abced116f14ae53c5e1a28f5"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.010",
      "bytes": 67108864,
      "sha256": "d25a890154dc902fb8b84722703207e0d1aec91a3e815610123a61630b9af559"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.011",
      "bytes": 67108864,
      "sha256": "fd170586cb629b33599e47c6a9390f4b0ea5c7e0ddc9e85052cb5a8c12f17144"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.012",
      "bytes": 67108864,
      "sha256": "bc55ea1ab217da5aedbbad4871f50a7dc4537973179e9354b648845ff7f65f5b"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.013",
      "bytes": 67108864,
      "sha256": "fc68f090d274e84129d0669efa1cd6bd0dd03e1bd0f90ea4c96612dac0180ce8"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.014",
      "bytes": 67108864,
      "sha256": "cf1e70c0cd615971144d3e80bb53e1a3da92922c7d46307d15eb18ceb170f1d6"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.015",
      "bytes": 67108864,
      "sha256": "cec50d679acbb8ca36d2d83bde6dfb71529109a4dc163126018c44ffdcd8a510"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.016",
      "bytes": 67108864,
      "sha256": "b09ebbf7d582915bbcc075d4df37dc2cede4ed45daf617959b2b9bcebf6f49e1"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.017",
      "bytes": 67108864,
      "sha256": "a86ef3598736b86ccb64dccd3194cc44aefd9f7d4e85e47668a0cc5251540ebf"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.018",
      "bytes": 67108864,
      "sha256": "11e9b2278c906c8961b99a8f463666376a2db551f064c8e0e8b11845e183e7d0"
    },
    {
      "name": "forecast-dispatch-20261001-r7.zip.019",
      "bytes": 59461147,
      "sha256": "10150339e5c4e15d2bc312c50c9cb084ff788221c918a4009ad585655be75645"
    }
  ]
}
'@ | ConvertFrom-Json
$origin = 'http://117.78.35.35'
$baseUrl = "$origin/api/v4/projects/56/packages/generic/forecast-dispatch/20261001-r7"
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

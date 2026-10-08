param(
    [switch]$Download,
    [string]$Destination = $PSScriptRoot,
    [System.Management.Automation.PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
$manifest = @'
{
  "version": "20261006-r9",
  "filename": "forecast-dispatch-20261006-r9.zip",
  "bytes": 1267446793,
  "sha256": "1151731d0553f121726c912ca74aff221fc5a6bfa46b423e45e04008637da6f6",
  "source_commit": "afde10b9ef41c61287ba40feb5eb2684a5f8e092",
  "image": "jingneng-fluxcast-all-in-one:20261006-r9",
  "image_id": "sha256:63d1ce46374617a6aba9905b0e7bbbe08367a71a55834f4f3819c5be162f226f",
  "parts": [
    {
      "name": "forecast-dispatch-20261006-r9.zip.001",
      "bytes": 67108864,
      "sha256": "56356f842098326793879971c4467c89991ffb70b73dbbda380465690149e741"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.002",
      "bytes": 67108864,
      "sha256": "7c55c99148df56d53203b906afb58a8a0851098f04f66c8989442cca5271d0ff"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.003",
      "bytes": 67108864,
      "sha256": "3fa6cc7805082fc5b098a5076a3fa29b7d8ee90a0db6688b408dded5c18bfcb4"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.004",
      "bytes": 67108864,
      "sha256": "03ff7770c192e57797826573d8f10465a688379a914ee7b6af7c3b6c2c41fd34"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.005",
      "bytes": 67108864,
      "sha256": "12b86432b2bf753dec8e4638dac462e2e898d478931dc8339f01c58cdb67c30e"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.006",
      "bytes": 67108864,
      "sha256": "8fa07e76ad4b1650860bdb203498d90251e932a21cc26de0f07e5aa6120cf97a"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.007",
      "bytes": 67108864,
      "sha256": "3505cb0e9aee185a8c330fa58348d9bb3180d7946c833d79923982192dae4975"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.008",
      "bytes": 67108864,
      "sha256": "bc171b499a63ca8b6c61e8ff6b6d8a32f1a5a1763042323d0913dbce4c500f2a"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.009",
      "bytes": 67108864,
      "sha256": "0c246edae4072ac0be3759fa62a7ecdd2162f15ee0f8eaa08e1fe19c03a6a2f8"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.010",
      "bytes": 67108864,
      "sha256": "f1d38877a83d1772547c3bb7d3a071f0be6340253dbe6ce8567587740d83447e"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.011",
      "bytes": 67108864,
      "sha256": "53b606f2c0022cc3f83dc12aace2cce59bf9d93eb67110978d1814cffe22ddb0"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.012",
      "bytes": 67108864,
      "sha256": "8bf9235eb9b7b8f60cd3d215979782986ed864c7657aa81208be129d5aaa673f"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.013",
      "bytes": 67108864,
      "sha256": "914e3783671873c7ddefe8f053ce6499f2613e3954a8e92ad8f1c099522b968e"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.014",
      "bytes": 67108864,
      "sha256": "f2aaaddbbe2de1f516aca0775fec26006fefc24e654f7557782555233aa471f1"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.015",
      "bytes": 67108864,
      "sha256": "602b1a00fd55dc740619a73c7d4e8753141940dda27a65523d9a78e9e54ed792"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.016",
      "bytes": 67108864,
      "sha256": "f8fb0d5e0b130bb6b87d1e3c55610d74bff6d36ae5358eed55ead0562921c8a6"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.017",
      "bytes": 67108864,
      "sha256": "3415145aa3e31a843d82439f6ec66749fd20279f05903bcd5180b9b48896bbbf"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.018",
      "bytes": 67108864,
      "sha256": "6e27d5b1a357da1d4b0018275fa5006d171a796ce999ffefd0b295a583bce3a4"
    },
    {
      "name": "forecast-dispatch-20261006-r9.zip.019",
      "bytes": 59487241,
      "sha256": "e153590490caa6734bbc322b03271c20a21d44956197b78c707343ad79f96b95"
    }
  ]
}
'@ | ConvertFrom-Json
$origin = 'http://117.78.35.35'
$baseUrl = "$origin/api/v4/projects/56/packages/generic/forecast-dispatch/20261006-r9"
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

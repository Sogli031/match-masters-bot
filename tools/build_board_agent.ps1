$ErrorActionPreference = "Stop"
$toolDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $toolDirectory
try {
    npm install --no-audit --no-fund
    frida-compile .\matchmasters_board_dump.ts `
        -o .\matchmasters_board_dump.js `
        -T none `
        -S
    Write-Host "Napravljen: $toolDirectory\matchmasters_board_dump.js"

    # The symbol dumper shares the same bridge dependency, so it is built here
    # rather than in a second script that would need its own npm install.
    frida-compile .\il2cpp_symbols_dump.ts `
        -o .\il2cpp_symbols_dump.js `
        -T none `
        -S
    Write-Host "Napravljen: $toolDirectory\il2cpp_symbols_dump.js"
}
finally {
    Pop-Location
}

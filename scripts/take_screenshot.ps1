Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$screen = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bmp.Size)
$outPath = 'C:\Users\lucng\.gemini\antigravity-ide\brain\8b9862ec-a981-441a-94ce-113c4139cefd\desktop_screenshot.png'
$bmp.Save($outPath)
$g.Dispose()
$bmp.Dispose()
Write-Host "Screenshot saved to: $outPath"
